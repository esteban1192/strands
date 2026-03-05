"""
Agent Sub-Agents resource — endpoints for managing agent-to-agent relationships.
"""
import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.models import AgentSubAgentResponse
from api.services import AgentSubAgentService

router = APIRouter(prefix="/agents/{agent_id}/sub-agents", tags=["agent-sub-agents"])


@router.get("", response_model=List[AgentSubAgentResponse])
async def list_sub_agents(
    agent_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Return all sub-agents linked to this agent."""
    return await AgentSubAgentService.list_sub_agents(db, agent_id)


@router.post("/{child_agent_id}", response_model=AgentSubAgentResponse, status_code=201)
async def add_sub_agent(
    agent_id: uuid.UUID,
    child_agent_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Link a child agent as a sub-agent of this agent."""
    try:
        return await AgentSubAgentService.add_sub_agent(db, agent_id, child_agent_id)
    except ValueError as e:
        msg = str(e)
        if "not found" in msg:
            raise HTTPException(status_code=404, detail=msg)
        if "already exists" in msg:
            raise HTTPException(status_code=409, detail=msg)
        raise HTTPException(status_code=400, detail=msg)


@router.delete("/{child_agent_id}")
async def remove_sub_agent(
    agent_id: uuid.UUID,
    child_agent_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Remove a sub-agent link."""
    deleted = await AgentSubAgentService.remove_sub_agent(db, agent_id, child_agent_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Sub-agent relationship not found")
    return {"message": f"Sub-agent {child_agent_id} removed from agent {agent_id}"}
