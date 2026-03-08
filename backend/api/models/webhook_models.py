"""
Webhook-related API models
"""
import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class WebhookSourceType(str, Enum):
    AWS_SNS = "AWS_SNS"


class WebhookResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: Optional[str] = None
    agent_id: uuid.UUID
    agent_name: Optional[str] = None
    source_type: WebhookSourceType
    is_active: bool = True
    invoke_url: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class WebhookCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    agent_id: uuid.UUID
    source_type: WebhookSourceType = Field(default=WebhookSourceType.AWS_SNS)
    is_active: bool = True


class WebhookUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    agent_id: Optional[uuid.UUID] = None
    source_type: Optional[WebhookSourceType] = None
    is_active: Optional[bool] = None


class WebhookInvocationResponse(BaseModel):
    id: uuid.UUID
    webhook_id: uuid.UUID
    chat_id: Optional[uuid.UUID] = None
    source_ip: Optional[str] = None
    raw_payload: Optional[Dict[str, Any]] = None
    status: str
    error_message: Optional[str] = None
    created_at: datetime


class WebhookInvokeResponse(BaseModel):
    """Returned immediately when a webhook invocation is accepted."""
    invocation_id: uuid.UUID
    chat_id: Optional[uuid.UUID] = None
    status: str = "received"
