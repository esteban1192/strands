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

Async architecture
──────────────────
Agent invocations run in background tasks.  POST endpoints return ``202
Accepted`` immediately.  Results are pushed to the frontend through a
per-chat SSE channel at ``GET /agents/{agent_id}/chats/{chat_id}/events``.
"""
import asyncio
import json
import logging
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db, get_db_session
from api.models import (
    ChatResponse,
    ChatDetailResponse,
    ChatSendMessageRequest,
    ChatSendMessageResponse,
    ChatAcceptedResponse,
    ChatMessageResponse,
)
from api.services import ChatService
from core.agent_executor import AgentExecutor, AgentExecutionError, SUB_AGENT_TOOL_PREFIX
from core.exceptions import MCPConnectionError
from core.mcp_manager import MCPManager
from core.mcp_session_cache import session_cache
from core.event_bus import event_bus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agents/{agent_id}/chats", tags=["chats"])


# ------------------------------------------------------------------
# SSE event stream for a chat
# ------------------------------------------------------------------

@router.get("/{chat_id}/events")
async def chat_events(agent_id: uuid.UUID, chat_id: uuid.UUID):
    """Server-Sent Events stream for a chat.

    The client subscribes once per chat session.  All background agent
    results (from send_message, approve, reject) are pushed here.
    """
    queue = await event_bus.subscribe(chat_id)

    async def _generate():
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    continue

                if event is None:
                    break

                event_type = event.get("type", "message")
                payload = {k: v for k, v in event.items() if k != "type"}
                yield f"event: {event_type}\ndata: {json.dumps(payload, default=str)}\n\n"

                if event_type in ("complete", "error"):
                    await event_bus.clear_buffer(chat_id)
        except asyncio.CancelledError:
            pass
        finally:
            await event_bus.unsubscribe(chat_id, queue)

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


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

@router.post("", response_model=ChatAcceptedResponse, status_code=202)
async def create_chat(
    agent_id: uuid.UUID,
    request: ChatSendMessageRequest,
    db: AsyncSession = Depends(get_db),
):
    """Create a new chat and start processing the first message.

    Returns immediately with the new chat_id.  The agent result will
    arrive via the SSE channel.
    """
    title = request.prompt[:100].strip() or "New chat"
    chat = await ChatService.create_chat(db, agent_id, title)
    await ChatService.create_delegation(db, chat.id, agent_id)

    asyncio.create_task(
        _background_create_chat(chat.id, agent_id, request.prompt)
    )

    return ChatAcceptedResponse(chat_id=chat.id)


async def _background_create_chat(
    chat_id: uuid.UUID,
    agent_id: uuid.UUID,
    prompt: str,
):
    """Background task: invoke agent for the first message in a chat."""
    await event_bus.publish(chat_id, {"type": "thinking"})

    async with get_db_session() as db:
        try:
            result = await AgentExecutor.invoke(db, agent_id, prompt, chat_id=chat_id)

            stored = await ChatService.add_messages(
                db, chat_id, result.messages,
                tools_requiring_approval=result.tools_requiring_approval,
                agent_id=agent_id,
            )

            pending = await ChatService.get_pending_tool_calls(db, chat_id, agent_id=agent_id)
            if not pending and not result.cancelled_tool_use_ids:
                root_deleg = await ChatService.get_active_delegation(db, chat_id, agent_id)
                if root_deleg:
                    await ChatService.complete_delegation(db, root_deleg.id)

            await ChatService.touch_updated_at(db, chat_id)

            all_messages = await ChatService.get_messages(db, chat_id)
            await event_bus.publish(chat_id, {
                "type": "complete",
                "response": result.response,
                "messages": _serialize_messages(all_messages),
            })

        except (AgentExecutionError, MCPConnectionError, Exception) as exc:
            logger.exception("Background create_chat failed for chat %s", chat_id)
            await event_bus.publish(chat_id, {
                "type": "error",
                "message": str(exc),
            })


# ------------------------------------------------------------------
# Send a follow-up message to an existing chat
# ------------------------------------------------------------------

@router.post("/{chat_id}/messages", response_model=ChatAcceptedResponse, status_code=202)
async def send_message(
    agent_id: uuid.UUID,
    chat_id: uuid.UUID,
    request: ChatSendMessageRequest,
    db: AsyncSession = Depends(get_db),
):
    """Send a follow-up message.  Returns immediately; result via SSE."""
    chat = await ChatService.get_chat(db, chat_id)
    if not chat or chat.agent_id != agent_id:
        raise HTTPException(status_code=404, detail="Chat not found")

    asyncio.create_task(
        _background_send_message(chat_id, agent_id, request.prompt)
    )

    return ChatAcceptedResponse(chat_id=chat_id)


async def _background_send_message(
    chat_id: uuid.UUID,
    agent_id: uuid.UUID,
    prompt: str,
):
    """Background task: invoke agent for a follow-up message."""
    await event_bus.publish(chat_id, {"type": "thinking"})

    async with get_db_session() as db:
        try:
            root_deleg = await ChatService.get_active_delegation(db, chat_id, agent_id)
            if not root_deleg:
                root_deleg = await ChatService.create_delegation(db, chat_id, agent_id)

            history = await ChatService.get_messages_as_dicts(db, chat_id, agent_id=agent_id)

            result = await AgentExecutor.invoke(
                db, agent_id, prompt, history=history, chat_id=chat_id,
            )

            await ChatService.add_messages(
                db, chat_id, result.messages,
                tools_requiring_approval=result.tools_requiring_approval,
                agent_id=agent_id,
            )

            pending = await ChatService.get_pending_tool_calls(db, chat_id, agent_id=agent_id)
            if not pending and not result.cancelled_tool_use_ids:
                await ChatService.complete_delegation(db, root_deleg.id)

            await ChatService.touch_updated_at(db, chat_id)

            all_messages = await ChatService.get_messages(db, chat_id)
            await event_bus.publish(chat_id, {
                "type": "complete",
                "response": result.response,
                "messages": _serialize_messages(all_messages),
            })

        except (AgentExecutionError, MCPConnectionError, Exception) as exc:
            logger.exception("Background send_message failed for chat %s", chat_id)
            await event_bus.publish(chat_id, {
                "type": "error",
                "message": str(exc),
            })


# ------------------------------------------------------------------
# Approve a pending tool call
# ------------------------------------------------------------------

@router.post(
    "/{chat_id}/messages/{message_id}/approve",
    response_model=ChatAcceptedResponse,
    status_code=202,
)
async def approve_tool_call(
    agent_id: uuid.UUID,
    chat_id: uuid.UUID,
    message_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Approve a pending tool call.  Returns immediately; result via SSE."""
    chat = await ChatService.get_chat(db, chat_id)
    if not chat or chat.agent_id != agent_id:
        raise HTTPException(status_code=404, detail="Chat not found")

    approved = await ChatService.approve_tool_call(db, message_id)
    if not approved:
        raise HTTPException(status_code=404, detail="Tool call message not found or already approved")

    tool_name = approved.tool_call.tool_name if approved.tool_call else None
    tool_input = approved.tool_call.input if approved.tool_call else {}
    tool_use_id = approved.tool_call.tool_use_id if approved.tool_call else None
    owning_agent_id = approved.agent_id or agent_id

    if not tool_name:
        raise HTTPException(status_code=400, detail="No tool call data found")

    asyncio.create_task(
        _background_approve(
            chat_id, agent_id, owning_agent_id,
            tool_name, tool_input, tool_use_id,
        )
    )

    return ChatAcceptedResponse(chat_id=chat_id)


async def _background_approve(
    chat_id: uuid.UUID,
    root_agent_id: uuid.UUID,
    owning_agent_id: uuid.UUID,
    tool_name: str,
    tool_input: dict,
    tool_use_id: Optional[str],
):
    """Background task: execute approved tool, then resume the chain."""
    await event_bus.publish(chat_id, {"type": "thinking"})

    async with get_db_session() as db:
        try:
            is_sub_agent = AgentExecutor.is_sub_agent_tool(tool_name)

            if is_sub_agent:
                await _handle_sub_agent_approval(
                    db, chat_id, root_agent_id, owning_agent_id,
                    tool_name, tool_input, tool_use_id,
                )
            else:
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

            final_response = await _try_resume_chain(
                db, chat_id, owning_agent_id, root_agent_id,
            )

            await ChatService.touch_updated_at(db, chat_id)
            all_messages = await ChatService.get_messages(db, chat_id)

            await event_bus.publish(chat_id, {
                "type": "complete",
                "response": final_response,
                "messages": _serialize_messages(all_messages),
            })

        except _ChildPausedException:
            pass  # Already published "complete" with child's pending state

        except Exception as exc:
            logger.exception("Background approve failed for chat %s", chat_id)
            await event_bus.publish(chat_id, {
                "type": "error",
                "message": str(exc),
            })


async def _handle_sub_agent_approval(
    db: AsyncSession,
    chat_id: uuid.UUID,
    root_agent_id: uuid.UUID,
    owning_agent_id: uuid.UUID,
    tool_name: str,
    tool_input: dict,
    tool_use_id: Optional[str],
):
    """Execute the sub-agent delegation path (extracted from approve)."""
    child_prompt = (tool_input or {}).get("prompt", "")
    if not child_prompt:
        raise AgentExecutionError("Sub-agent tool call missing 'prompt' input")

    from api.services import AgentSubAgentService
    child_agents = await AgentSubAgentService.get_enabled_sub_agents(db, owning_agent_id)
    child_agent_id: Optional[uuid.UUID] = None
    for child in child_agents:
        if AgentExecutor.sub_agent_tool_name(child.name) == tool_name:
            child_agent_id = child.id
            break

    if child_agent_id is None:
        raise AgentExecutionError(f"Sub-agent for tool '{tool_name}' not found")

    owner_deleg = await ChatService.get_active_delegation(db, chat_id, owning_agent_id)
    if not owner_deleg:
        raise AgentExecutionError("No active delegation found for owning agent")

    has_cycle = await ChatService.check_delegation_cycle(
        db, chat_id, owner_deleg.id, child_agent_id,
    )
    if has_cycle:
        await ChatService.update_tool_result(
            db, chat_id, tool_use_id,
            {"error": "Delegation cycle detected — this agent is already in the chain."},
        )
        return

    child_deleg = await ChatService.create_delegation(
        db, chat_id, child_agent_id,
        parent_delegation_id=owner_deleg.id,
        tool_use_id=tool_use_id,
    )

    try:
        child_result = await AgentExecutor.invoke(db, child_agent_id, child_prompt, chat_id=chat_id)
    except (AgentExecutionError, MCPConnectionError) as e:
        err_msg = e.message if hasattr(e, "message") else str(e)
        await ChatService.update_tool_result(
            db, chat_id, tool_use_id, {"error": err_msg},
        )
        await ChatService.complete_delegation(db, child_deleg.id, status="failed")
        return

    if child_result.messages:
        await ChatService.add_messages(
            db, chat_id, child_result.messages,
            tools_requiring_approval=child_result.tools_requiring_approval,
            agent_id=child_agent_id,
        )

    child_pending = await ChatService.get_pending_tool_calls(
        db, chat_id, agent_id=child_agent_id,
    )
    if child_pending:
        await ChatService.touch_updated_at(db, chat_id)
        all_messages = await ChatService.get_messages(db, chat_id)
        await event_bus.publish(chat_id, {
            "type": "complete",
            "response": "",
            "messages": _serialize_messages(all_messages),
        })
        raise _ChildPausedException()

    await ChatService.update_tool_result(
        db, chat_id, tool_use_id, child_result.response,
    )
    await ChatService.complete_delegation(db, child_deleg.id)


class _ChildPausedException(Exception):
    """Sentinel — child agent is paused waiting for approvals."""
    pass


# ------------------------------------------------------------------
# Reject a pending tool call
# ------------------------------------------------------------------

@router.post(
    "/{chat_id}/messages/{message_id}/reject",
    response_model=ChatAcceptedResponse,
    status_code=202,
)
async def reject_tool_call(
    agent_id: uuid.UUID,
    chat_id: uuid.UUID,
    message_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Reject a pending tool call.  Returns immediately; result via SSE."""
    chat = await ChatService.get_chat(db, chat_id)
    if not chat or chat.agent_id != agent_id:
        raise HTTPException(status_code=404, detail="Chat not found")

    rejected = await ChatService.reject_tool_call(db, message_id)
    if not rejected:
        raise HTTPException(status_code=404, detail="Tool call message not found or already resolved")

    owning_agent_id = rejected.agent_id or agent_id

    asyncio.create_task(
        _background_reject(chat_id, agent_id, owning_agent_id)
    )

    return ChatAcceptedResponse(chat_id=chat_id)


async def _background_reject(
    chat_id: uuid.UUID,
    root_agent_id: uuid.UUID,
    owning_agent_id: uuid.UUID,
):
    """Background task: resume the chain after a rejection."""
    await event_bus.publish(chat_id, {"type": "thinking"})

    async with get_db_session() as db:
        try:
            final_response = await _try_resume_chain(
                db, chat_id, owning_agent_id, root_agent_id,
            )

            await ChatService.touch_updated_at(db, chat_id)
            all_messages = await ChatService.get_messages(db, chat_id)

            await event_bus.publish(chat_id, {
                "type": "complete",
                "response": final_response,
                "messages": _serialize_messages(all_messages),
            })

        except (AgentExecutionError, MCPConnectionError, Exception) as exc:
            logger.exception("Background reject failed for chat %s", chat_id)
            await event_bus.publish(chat_id, {
                "type": "error",
                "message": str(exc),
            })


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
        pending = await ChatService.get_pending_tool_calls(
            db, chat_id, agent_id=agent_id,
        )
        if pending:
            return ""

        history = await ChatService.get_messages_as_dicts(
            db, chat_id, agent_id=agent_id,
        )

        result = await AgentExecutor.invoke(
            db, agent_id, None, history=history, chat_id=chat_id,
        )

        if result.messages:
            await ChatService.add_messages(
                db, chat_id, result.messages,
                tools_requiring_approval=result.tools_requiring_approval,
                agent_id=agent_id,
            )

        new_pending = await ChatService.get_pending_tool_calls(
            db, chat_id, agent_id=agent_id,
        )
        if new_pending:
            return ""

        if agent_id == root_agent_id:
            root_deleg = await ChatService.get_active_delegation(
                db, chat_id, root_agent_id,
            )
            if root_deleg:
                await ChatService.complete_delegation(db, root_deleg.id)
            return result.response

        deleg = await ChatService.get_active_delegation(db, chat_id, agent_id)
        if not deleg or not deleg.parent_delegation_id:
            return result.response

        parent_deleg = await ChatService.get_delegation_by_id(
            db, deleg.parent_delegation_id,
        )
        if not parent_deleg:
            return result.response

        await ChatService.complete_delegation(db, deleg.id)

        if deleg.tool_use_id:
            await ChatService.update_tool_result(
                db, chat_id, deleg.tool_use_id, result.response,
            )

        agent_id = parent_deleg.agent_id


# ------------------------------------------------------------------
# Serialization helpers
# ------------------------------------------------------------------

def _serialize_messages(messages: list) -> list:
    """Convert a list of ChatMessageResponse (or ORM models) to plain dicts
    that are JSON-serializable for the SSE payload."""
    result = []
    for m in messages:
        if isinstance(m, dict):
            result.append(m)
        elif hasattr(m, "model_dump"):
            result.append(m.model_dump(mode="json"))
        else:
            result.append(ChatMessageResponse.model_validate(m).model_dump(mode="json"))
    return result


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
