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


class ChatMessageResponse(BaseModel):
    """Single message within a chat."""
    id: uuid.UUID
    chat_id: uuid.UUID
    role: str
    content: List[Dict[str, Any]]
    ordinal: int
    created_at: datetime


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
