"""
Agent-related API models
"""
import uuid
from datetime import datetime
from pydantic import BaseModel, Field
from typing import Optional


class AgentResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: Optional[str] = None
    model: str
    system_prompt: Optional[str] = None
    status: str = "active"
    tools_count: int = 0
    created_at: datetime
    updated_at: datetime


class AgentCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    model: str = Field(..., min_length=1, max_length=255)
    system_prompt: Optional[str] = None
    status: str = Field(default="active", pattern="^(active|inactive|paused)$")


class AgentUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    model: Optional[str] = Field(None, min_length=1, max_length=255)
    system_prompt: Optional[str] = None
    status: Optional[str] = Field(None, pattern="^(active|inactive|paused)$")


class AgentToolRelationResponse(BaseModel):
    id: uuid.UUID
    agent_id: uuid.UUID
    tool_id: uuid.UUID
    added_at: datetime
    is_enabled: bool = True


class AgentInvokeRequest(BaseModel):
    prompt: str = Field(..., min_length=1)


class AgentInvokeResponse(BaseModel):
    agent_id: uuid.UUID
    response: str