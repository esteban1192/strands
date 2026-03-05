"""
Chat resource — endpoints for managing agent conversations.

Delegation-chain architecture
─────────────────────────────
When a parent agent delegates to a sub-agent, a ``ChatDelegation`` row is
created tracking the session.  The delegation chain can be nested:
A → B → C → …  Each agent's messages are stored with ``agent_id`` set so
that ``get_messages_as_dicts(…, agent_id=X)`` retrieves only that agent's
conversation slice.

Approve/reject logic detects which agent *owns* the tool call (via
``msg.agent_id``) and operates on that agent — *not* the root agent.
After a child completes, **try_resume_chain** walks up the delegation
stack, resuming each parent in turn until a parent itself has pending
approvals or is the root and produces its final answer.
"""
import logging
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.models import (
    ChatResponse,
    ChatDetailResponse,
    ChatSendMessageRequest,
    ChatSendMessageResponse,
    ChatMessageResponse,
)
from api.services import ChatService
from core.agent_executor import AgentExecutor, AgentExecutionError, SUB_AGENT_TOOL_PREFIX
from core.exceptions import MCPConnectionError
from core.mcp_manager import MCPManager
from core.mcp_session_cache import session_cache

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agents/{agent_id}/chats", tags=["chats"])


# ------------------------------------------------------------------
# List chats for an agent
# ------------------------------------------------------------------

@router.get("", response_model=List[ChatResponse])
async def list_chats(agent_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Return all chats for an agent, most recent first."""
    return await ChatService.list_chats_by_agent(db, agent_id)


# ------------------------------------------------------------------
# Get a single chat (with all messages)
# ------------------------------------------------------------------

@router.get("/{chat_id}", response_model=ChatDetailResponse)
async def get_chat(
    agent_id: uuid.UUID,
    chat_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get a chat together with all its messages."""
    detail = await ChatService.get_chat_detail(db, chat_id)
    if not detail or detail.agent_id != agent_id:
        raise HTTPException(status_code=404, detail="Chat not found")
    return detail


# ------------------------------------------------------------------
# Create chat (first message)
# ------------------------------------------------------------------

@router.post("", response_model=ChatSendMessageResponse, status_code=201)
async def create_chat(
    agent_id: uuid.UUID,
    request: ChatSendMessageRequest,
    db: AsyncSession = Depends(get_db),
):
    """Create a new chat by sending the first message.

    Creates the chat record, a root delegation for the agent, invokes the
    agent, and persists both the user message and the model response.
    """
    # Auto-title from the first prompt (truncated)
    title = request.prompt[:100].strip() or "New chat"

    chat = await ChatService.create_chat(db, agent_id, title)

    # Create root delegation for this chat's agent
    root_deleg = await ChatService.create_delegation(db, chat.id, agent_id)

    # Invoke the agent (no prior history on the first message)
    try:
        result = await AgentExecutor.invoke(db, agent_id, request.prompt, chat_id=chat.id)
    except AgentExecutionError as e:
        await ChatService.delete_chat(db, chat.id)
        raise _map_agent_error(e)
    except MCPConnectionError as e:
        await ChatService.delete_chat(db, chat.id)
        raise HTTPException(status_code=502, detail=e.message)

    # Persist the new messages returned by the executor
    stored = await ChatService.add_messages(
        db, chat.id, result.messages,
        tools_requiring_approval=result.tools_requiring_approval,
        agent_id=agent_id,
    )

    # If no pending approvals, the root delegation completed this turn
    pending = await ChatService.get_pending_tool_calls(db, chat.id, agent_id=agent_id)
    if not pending and not result.cancelled_tool_use_ids:
        await ChatService.complete_delegation(db, root_deleg.id)

    await ChatService.touch_updated_at(db, chat.id)

    return ChatSendMessageResponse(
        chat_id=chat.id,
        response=result.response,
        messages=stored,
    )


# ------------------------------------------------------------------
# Send a follow-up message to an existing chat
# ------------------------------------------------------------------

@router.post("/{chat_id}/messages", response_model=ChatSendMessageResponse)
async def send_message(
    agent_id: uuid.UUID,
    chat_id: uuid.UUID,
    request: ChatSendMessageRequest,
    db: AsyncSession = Depends(get_db),
):
    """Send a follow-up message in an existing chat."""
    chat = await ChatService.get_chat(db, chat_id)
    if not chat or chat.agent_id != agent_id:
        raise HTTPException(status_code=404, detail="Chat not found")

    # Ensure there's an active root delegation (create one if prior chat
    # was created before delegation tracking was added, or the previous
    # root delegation completed).
    root_deleg = await ChatService.get_active_delegation(db, chat_id, agent_id)
    if not root_deleg:
        root_deleg = await ChatService.create_delegation(db, chat_id, agent_id)

    # Load root agent's conversation history
    history = await ChatService.get_messages_as_dicts(db, chat_id, agent_id=agent_id)

    try:
        result = await AgentExecutor.invoke(
            db, agent_id, request.prompt, history=history, chat_id=chat_id,
        )
    except AgentExecutionError as e:
        raise _map_agent_error(e)
    except MCPConnectionError as e:
        raise HTTPException(status_code=502, detail=e.message)

    # Persist only the new messages (delta)
    await ChatService.add_messages(
        db, chat_id, result.messages,
        tools_requiring_approval=result.tools_requiring_approval,
        agent_id=agent_id,
    )

    # Check if root completed
    pending = await ChatService.get_pending_tool_calls(db, chat_id, agent_id=agent_id)
    if not pending and not result.cancelled_tool_use_ids:
        await ChatService.complete_delegation(db, root_deleg.id)

    await ChatService.touch_updated_at(db, chat_id)

    all_messages = await ChatService.get_messages(db, chat_id)

    return ChatSendMessageResponse(
        chat_id=chat_id,
        response=result.response,
        messages=all_messages,
    )


# ------------------------------------------------------------------
# Approve a pending tool call
# ------------------------------------------------------------------

@router.post(
    "/{chat_id}/messages/{message_id}/approve",
    response_model=ChatSendMessageResponse,
)
async def approve_tool_call(
    agent_id: uuid.UUID,
    chat_id: uuid.UUID,
    message_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Approve a pending tool call and resume the delegation chain.

    Key insight: the tool call's ``agent_id`` tells us *which* agent in
    the chain owns this call.  We operate on that agent — not the root.

    For **regular tools**: execute via MCP, then ``try_resume_chain``.
    For **sub-agent tools**: create a child delegation, invoke the child
    agent, persist its messages, and propagate upward.
    """
    chat = await ChatService.get_chat(db, chat_id)
    if not chat or chat.agent_id != agent_id:
        raise HTTPException(status_code=404, detail="Chat not found")

    approved = await ChatService.approve_tool_call(db, message_id)
    if not approved:
        raise HTTPException(status_code=404, detail="Tool call message not found or already approved")

    tool_name = approved.tool_call.tool_name if approved.tool_call else None
    tool_input = approved.tool_call.input if approved.tool_call else {}
    tool_use_id = approved.tool_call.tool_use_id if approved.tool_call else None
    owning_agent_id = approved.agent_id  # which agent made this call

    if not tool_name:
        raise HTTPException(status_code=400, detail="No tool call data found")

    if not owning_agent_id:
        # Fallback for legacy messages without agent_id
        owning_agent_id = agent_id

    is_sub_agent = AgentExecutor.is_sub_agent_tool(tool_name)

    if is_sub_agent:
        # ---- Sub-agent invocation path ----
        child_prompt = (tool_input or {}).get("prompt", "")
        if not child_prompt:
            raise HTTPException(status_code=400, detail="Sub-agent tool call missing 'prompt' input")

        # Resolve child agent ID
        from api.services import AgentSubAgentService
        child_agents = await AgentSubAgentService.get_enabled_sub_agents(db, owning_agent_id)
        child_agent_id: Optional[uuid.UUID] = None
        for child in child_agents:
            if AgentExecutor.sub_agent_tool_name(child.name) == tool_name:
                child_agent_id = child.id
                break

        if child_agent_id is None:
            raise HTTPException(status_code=404, detail=f"Sub-agent for tool '{tool_name}' not found")

        # Find the owning agent's delegation
        owner_deleg = await ChatService.get_active_delegation(db, chat_id, owning_agent_id)
        if not owner_deleg:
            raise HTTPException(status_code=400, detail="No active delegation found for owning agent")

        # Cycle detection — walk up the chain
        has_cycle = await ChatService.check_delegation_cycle(
            db, chat_id, owner_deleg.id, child_agent_id,
        )
        if has_cycle:
            # Treat as error tool_result for the parent
            await ChatService.update_tool_result(
                db, chat_id, tool_use_id,
                {"error": "Delegation cycle detected — this agent is already in the chain."},
            )
        else:
            # Create child delegation
            child_deleg = await ChatService.create_delegation(
                db, chat_id, child_agent_id,
                parent_delegation_id=owner_deleg.id,
                tool_use_id=tool_use_id,
            )

            # Invoke child
            try:
                child_result = await AgentExecutor.invoke(db, child_agent_id, child_prompt, chat_id=chat_id)
            except (AgentExecutionError, MCPConnectionError) as e:
                err_msg = e.message if hasattr(e, "message") else str(e)
                await ChatService.update_tool_result(
                    db, chat_id, tool_use_id, {"error": err_msg},
                )
                await ChatService.complete_delegation(db, child_deleg.id, status="failed")
                child_result = None

            if child_result is not None:
                # Persist child's messages
                if child_result.messages:
                    await ChatService.add_messages(
                        db, chat_id, child_result.messages,
                        tools_requiring_approval=child_result.tools_requiring_approval,
                        agent_id=child_agent_id,
                    )

                # Does the child have pending approvals?
                child_pending = await ChatService.get_pending_tool_calls(
                    db, chat_id, agent_id=child_agent_id,
                )
                if child_pending:
                    # Child is paused — user must resolve its tools first
                    await ChatService.touch_updated_at(db, chat_id)
                    all_messages = await ChatService.get_messages(db, chat_id)
                    return ChatSendMessageResponse(
                        chat_id=chat_id, response="", messages=all_messages,
                    )

                # Child completed — use its response as parent's tool_result
                await ChatService.update_tool_result(
                    db, chat_id, tool_use_id, child_result.response,
                )
                await ChatService.complete_delegation(db, child_deleg.id)
    else:
        # ---- Regular MCP tool execution path ----
        try:
            real_result = await MCPManager.execute_tool(
                db, owning_agent_id, tool_name, tool_input or {},
                chat_id=chat_id,
            )
        except Exception as exc:
            logger.error("Tool execution failed for '%s': %s", tool_name, exc)
            real_result = {"error": str(exc)}

        await ChatService.update_tool_result(
            db, chat_id, tool_use_id, real_result,
        )

    # Try to resume the delegation chain upward
    final_response = await _try_resume_chain(
        db, chat_id, owning_agent_id, agent_id,
    )

    await ChatService.touch_updated_at(db, chat_id)
    all_messages = await ChatService.get_messages(db, chat_id)

    return ChatSendMessageResponse(
        chat_id=chat_id,
        response=final_response,
        messages=all_messages,
    )


# ------------------------------------------------------------------
# Reject a pending tool call
# ------------------------------------------------------------------

@router.post(
    "/{chat_id}/messages/{message_id}/reject",
    response_model=ChatSendMessageResponse,
)
async def reject_tool_call(
    agent_id: uuid.UUID,
    chat_id: uuid.UUID,
    message_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Reject a pending tool call.

    Marks the tool call as resolved and feeds a rejection message back
    to the owning agent.  Then tries to resume the delegation chain.
    """
    chat = await ChatService.get_chat(db, chat_id)
    if not chat or chat.agent_id != agent_id:
        raise HTTPException(status_code=404, detail="Chat not found")

    rejected = await ChatService.reject_tool_call(db, message_id)
    if not rejected:
        raise HTTPException(status_code=404, detail="Tool call message not found or already resolved")

    owning_agent_id = rejected.agent_id or agent_id

    # Try to resume the chain
    final_response = await _try_resume_chain(
        db, chat_id, owning_agent_id, agent_id,
    )

    await ChatService.touch_updated_at(db, chat_id)
    all_messages = await ChatService.get_messages(db, chat_id)

    return ChatSendMessageResponse(
        chat_id=chat_id,
        response=final_response,
        messages=all_messages,
    )


# ------------------------------------------------------------------
# Delete a chat
# ------------------------------------------------------------------

@router.delete("/{chat_id}")
async def delete_chat(
    agent_id: uuid.UUID,
    chat_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Delete a chat and all its messages."""
    chat = await ChatService.get_chat(db, chat_id)
    if not chat or chat.agent_id != agent_id:
        raise HTTPException(status_code=404, detail="Chat not found")
    session_cache.evict_chat(chat_id)
    await ChatService.delete_chat(db, chat_id)
    return {"message": f"Chat {chat_id} deleted"}


# ------------------------------------------------------------------
# Delegation chain helpers
# ------------------------------------------------------------------

async def _try_resume_chain(
    db: AsyncSession,
    chat_id: uuid.UUID,
    current_agent_id: uuid.UUID,
    root_agent_id: uuid.UUID,
) -> str:
    """Recursively resume agents up the delegation chain.

    Starting from ``current_agent_id``, checks if all pending tool calls
    for that agent are resolved.  If so, re-invokes it with its filtered
    history.  If the agent completes (no new pending calls), its response
    is propagated up to the parent delegation and the process repeats.

    Returns the final text response (from the root) or "" if the chain
    is still paused.
    """
    agent_id = current_agent_id

    while True:
        # Any remaining pending calls for THIS agent?
        pending = await ChatService.get_pending_tool_calls(
            db, chat_id, agent_id=agent_id,
        )
        if pending:
            return ""  # Still waiting on this agent

        # Re-invoke with this agent's filtered history
        history = await ChatService.get_messages_as_dicts(
            db, chat_id, agent_id=agent_id,
        )

        try:
            result = await AgentExecutor.invoke(
                db, agent_id, None, history=history, chat_id=chat_id,
            )
        except AgentExecutionError as e:
            raise _map_agent_error(e)
        except MCPConnectionError as e:
            raise HTTPException(status_code=502, detail=e.message)

        # Persist new messages
        if result.messages:
            await ChatService.add_messages(
                db, chat_id, result.messages,
                tools_requiring_approval=result.tools_requiring_approval,
                agent_id=agent_id,
            )

        # Does this agent now have new pending approvals?
        new_pending = await ChatService.get_pending_tool_calls(
            db, chat_id, agent_id=agent_id,
        )
        if new_pending:
            return ""  # Agent paused on new tool calls

        # Agent completed this turn.  Is it the root?
        if agent_id == root_agent_id:
            # Mark root delegation completed
            root_deleg = await ChatService.get_active_delegation(
                db, chat_id, root_agent_id,
            )
            if root_deleg:
                await ChatService.complete_delegation(db, root_deleg.id)
            return result.response

        # It's a child — find its delegation to get the parent info
        deleg = await ChatService.get_active_delegation(db, chat_id, agent_id)
        if not deleg or not deleg.parent_delegation_id:
            # Orphaned delegation — treat as if root
            return result.response

        parent_deleg = await ChatService.get_delegation_by_id(
            db, deleg.parent_delegation_id,
        )
        if not parent_deleg:
            return result.response

        # Complete the child delegation
        await ChatService.complete_delegation(db, deleg.id)

        # Feed child's response as the parent's tool_result
        if deleg.tool_use_id:
            await ChatService.update_tool_result(
                db, chat_id, deleg.tool_use_id, result.response,
            )

        # Move up to the parent agent
        agent_id = parent_deleg.agent_id


# ------------------------------------------------------------------
# Error mapping
# ------------------------------------------------------------------

def _map_agent_error(e: AgentExecutionError) -> HTTPException:
    """Map an AgentExecutionError to the appropriate HTTPException."""
    msg = e.message
    if "not found" in msg:
        return HTTPException(status_code=404, detail=msg)
    if "not active" in msg:
        return HTTPException(status_code=400, detail=msg)
    if "no enabled tools" in msg.lower() or "no mcp" in msg.lower():
        return HTTPException(status_code=400, detail=msg)
    return HTTPException(status_code=500, detail=msg)
