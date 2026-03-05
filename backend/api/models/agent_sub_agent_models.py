"""
Agent Sub-Agent relationship API models
"""
import uuid
from datetime import datetime
from pydantic import BaseModel


class AgentSubAgentResponse(BaseModel):
    """Response model for an agent-to-agent (sub-agent) relationship."""
    id: uuid.UUID
    parent_agent_id: uuid.UUID
    child_agent_id: uuid.UUID
    child_agent_name: str
    child_agent_description: str | None = None
    child_agent_status: str = "active"
    is_enabled: bool = True
    added_at: datetime


class AgentSubAgentCreateRequest(BaseModel):
    """Request to link a child agent to a parent agent."""
    child_agent_id: uuid.UUID
