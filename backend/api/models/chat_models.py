"""
Chat-related API models
"""
import uuid
from datetime import datetime
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional


class ChatResponse(BaseModel):
    """Chat metadata (without messages)."""
    id: uuid.UUID
    agent_id: uuid.UUID
    title: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class ChatToolCallResponse(BaseModel):
    """Structured data extracted from a tool_call message."""
    id: uuid.UUID
    message_id: uuid.UUID
    tool_use_id: str
    tool_name: str
    input: Optional[Dict[str, Any]] = None
    created_at: datetime


class ChatToolResultResponse(BaseModel):
    """Structured data extracted from a tool_result message."""
    id: uuid.UUID
    message_id: uuid.UUID
    tool_use_id: str
    status: str
    result: Optional[Any] = None
    created_at: datetime


class ChatMessageResponse(BaseModel):
    """Single message within a chat (one content block per row)."""
    id: uuid.UUID
    chat_id: uuid.UUID
    agent_id: Optional[uuid.UUID] = None
    role: str
    message_type: str
    content: Dict[str, Any]
    ordinal: int
    is_approved: bool = False
    created_at: datetime
    tool_call: Optional[ChatToolCallResponse] = None
    tool_result: Optional[ChatToolResultResponse] = None


class ChatDelegationResponse(BaseModel):
    """A delegation session within a chat."""
    id: uuid.UUID
    chat_id: uuid.UUID
    parent_delegation_id: Optional[uuid.UUID] = None
    agent_id: uuid.UUID
    tool_use_id: Optional[str] = None
    status: str
    created_at: datetime
    completed_at: Optional[datetime] = None


class ChatDetailResponse(BaseModel):
    """Chat metadata together with its messages."""
    id: uuid.UUID
    agent_id: uuid.UUID
    title: Optional[str] = None
    messages: List[ChatMessageResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class ChatSendMessageRequest(BaseModel):
    """Request body for sending a message to a chat."""
    prompt: str = Field(..., min_length=1)


class ChatSendMessageResponse(BaseModel):
    """Response after sending a message — includes the new chat_id and the agent response."""
    chat_id: uuid.UUID
    response: str
    messages: List[ChatMessageResponse] = Field(
        default_factory=list,
        description="All messages in the chat after this turn",
    )
