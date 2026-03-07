"""
Chat-task API models
"""
import uuid
from datetime import datetime
from pydantic import BaseModel, Field
from typing import List, Optional


class ChatTaskResponse(BaseModel):
    """Public representation of a background task."""
    id: uuid.UUID
    source_chat_id: uuid.UUID
    message_id: Optional[uuid.UUID] = None
    tool_use_id: Optional[str] = None
    parent_task_id: Optional[uuid.UUID] = None
    agent_id: uuid.UUID
    instruction: str
    status: str
    result_summary: Optional[str] = None
    error: Optional[str] = None
    chat_id: Optional[uuid.UUID] = Field(
        None, description="The task's own conversation-thread chat",
    )
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    sub_tasks: List["ChatTaskResponse"] = Field(default_factory=list)


class ChatTaskCreateRequest(BaseModel):
    """Single task instruction (used inside a batch create)."""
    instruction: str = Field(..., min_length=1)
    agent_id: Optional[uuid.UUID] = Field(
        None, description="Override agent; defaults to the chat's own agent",
    )


class ChatTaskBatchCreateRequest(BaseModel):
    """Request body for creating multiple tasks at once."""
    tasks: List[ChatTaskCreateRequest] = Field(..., min_length=1)


class ChatTaskBatchCreateResponse(BaseModel):
    """Returned after batch-creating tasks."""
    tasks: List[ChatTaskResponse]
