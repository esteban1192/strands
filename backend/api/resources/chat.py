"""
Chat resource — endpoints for managing agent conversations.
"""
import logging
import uuid
from typing import List

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
from core.agent_executor import AgentExecutor, AgentExecutionError
from core.exceptions import MCPConnectionError
from core.mcp_manager import MCPManager

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

    Creates the chat record, invokes the agent, and persists both the
    user message and the model response messages.
    """
    # Auto-title from the first prompt (truncated)
    title = request.prompt[:100].strip() or "New chat"

    chat = await ChatService.create_chat(db, agent_id, title)

    # Invoke the agent (no prior history on the first message)
    try:
        result = await AgentExecutor.invoke(db, agent_id, request.prompt)
    except AgentExecutionError as e:
        # Clean up the just-created chat on failure
        await ChatService.delete_chat(db, chat.id)
        raise _map_agent_error(e)
    except MCPConnectionError as e:
        await ChatService.delete_chat(db, chat.id)
        raise HTTPException(status_code=502, detail=e.message)

    # Persist the new messages returned by the executor
    stored = await ChatService.add_messages(
        db, chat.id, result.messages,
        tools_requiring_approval=result.tools_requiring_approval,
    )
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
    """Send a follow-up message in an existing chat.

    Loads all previous messages from the DB, passes them as history to the
    agent, then persists the new messages produced by this turn.
    """
    chat = await ChatService.get_chat(db, chat_id)
    if not chat or chat.agent_id != agent_id:
        raise HTTPException(status_code=404, detail="Chat not found")

    # Load conversation history from DB
    history = await ChatService.get_messages_as_dicts(db, chat_id)

    try:
        result = await AgentExecutor.invoke(
            db, agent_id, request.prompt, history=history,
        )
    except AgentExecutionError as e:
        raise _map_agent_error(e)
    except MCPConnectionError as e:
        raise HTTPException(status_code=502, detail=e.message)

    # Persist only the new messages (delta)
    stored = await ChatService.add_messages(
        db, chat_id, result.messages,
        tools_requiring_approval=result.tools_requiring_approval,
    )
    await ChatService.touch_updated_at(db, chat_id)

    # Return ALL messages so the frontend has the full picture
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
    """Approve a pending tool call, execute it via MCP, and resume the agent.

    Flow:
      1. Mark the tool_call message as approved.
      2. Execute the real tool call through the MCP server.
      3. Replace the placeholder tool_result with the real result.
      4. If no more pending tool calls remain, re-invoke the agent with the
         corrected history so it can continue.
    """
    chat = await ChatService.get_chat(db, chat_id)
    if not chat or chat.agent_id != agent_id:
        raise HTTPException(status_code=404, detail="Chat not found")

    approved = await ChatService.approve_tool_call(db, message_id)
    if not approved:
        raise HTTPException(status_code=404, detail="Tool call message not found or already approved")

    # Execute the real tool call
    tool_name = approved.tool_call.tool_name if approved.tool_call else None
    tool_input = approved.tool_call.input if approved.tool_call else {}
    tool_use_id = approved.tool_call.tool_use_id if approved.tool_call else None

    if not tool_name:
        raise HTTPException(status_code=400, detail="No tool call data found")

    # Execute tool via MCP and get real result
    try:
        real_result = await MCPManager.execute_tool(db, agent_id, tool_name, tool_input or {})
    except Exception as exc:
        logger.error("Tool execution failed for '%s': %s", tool_name, exc)
        real_result = {"error": str(exc)}

    # Update the companion tool_result row with the real result
    await ChatService.update_tool_result(
        db, chat_id, tool_use_id, real_result,
    )

    # Only re-invoke the agent when ALL pending tool calls have been resolved.
    # If other tool calls are still awaiting approval, return the current
    # messages without invoking the model.
    pending = await ChatService.get_pending_tool_calls(db, chat_id)
    if not pending:
        # All resolved — let the agent continue from the tool results.
        # Pass prompt=None so no empty user message is injected.
        history = await ChatService.get_messages_as_dicts(db, chat_id)
        try:
            result = await AgentExecutor.invoke(
                db, agent_id, None, history=history,
            )
        except AgentExecutionError as e:
            raise _map_agent_error(e)
        except MCPConnectionError as e:
            raise HTTPException(status_code=502, detail=e.message)

        # Persist new messages from the continued conversation
        if result.messages:
            await ChatService.add_messages(
                db, chat_id, result.messages,
                tools_requiring_approval=result.tools_requiring_approval,
            )

    await ChatService.touch_updated_at(db, chat_id)

    all_messages = await ChatService.get_messages(db, chat_id)

    return ChatSendMessageResponse(
        chat_id=chat_id,
        response=result.response if not pending else "",
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
    to the agent so it can adapt its response.  The agent is only
    re-invoked once all pending tool calls have been resolved.
    """
    chat = await ChatService.get_chat(db, chat_id)
    if not chat or chat.agent_id != agent_id:
        raise HTTPException(status_code=404, detail="Chat not found")

    rejected = await ChatService.reject_tool_call(db, message_id)
    if not rejected:
        raise HTTPException(status_code=404, detail="Tool call message not found or already resolved")

    # Only re-invoke when ALL pending tool calls have been resolved.
    pending = await ChatService.get_pending_tool_calls(db, chat_id)
    if not pending:
        # All resolved — let the agent continue.
        # Pass prompt=None so no empty user message is injected.
        history = await ChatService.get_messages_as_dicts(db, chat_id)
        try:
            result = await AgentExecutor.invoke(
                db, agent_id, None, history=history,
            )
        except AgentExecutionError as e:
            raise _map_agent_error(e)
        except MCPConnectionError as e:
            raise HTTPException(status_code=502, detail=e.message)

        if result.messages:
            await ChatService.add_messages(
                db, chat_id, result.messages,
                tools_requiring_approval=result.tools_requiring_approval,
            )

    await ChatService.touch_updated_at(db, chat_id)

    all_messages = await ChatService.get_messages(db, chat_id)

    return ChatSendMessageResponse(
        chat_id=chat_id,
        response=result.response if not pending else "",
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
    await ChatService.delete_chat(db, chat_id)
    return {"message": f"Chat {chat_id} deleted"}


# ------------------------------------------------------------------
# Helpers
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
