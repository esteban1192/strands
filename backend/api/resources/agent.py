"""
Agent endpoints for the Strands API
"""
import uuid
import logging
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from ..models import (
    AgentResponse, AgentCreateRequest, AgentUpdateRequest,
    AgentInvokeRequest, AgentInvokeResponse
)
from ..database import get_db
from ..services import AgentService
from core import AgentExecutor, AgentExecutionError, MCPConnectionError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("", response_model=List[AgentResponse])
async def get_agents(db: AsyncSession = Depends(get_db)):
    """Get all agents"""
    return await AgentService.get_all(db)


@router.post("", response_model=AgentResponse, status_code=201)
async def create_agent(request: AgentCreateRequest, db: AsyncSession = Depends(get_db)):
    """Create a new agent"""
    try:
        return await AgentService.create(db, request)
    except Exception as e:
        # Handle unique constraint violations, etc.
        if "unique" in str(e).lower():
            raise HTTPException(status_code=409, detail="Agent name already exists")
        raise HTTPException(status_code=500, detail=f"Failed to create agent: {str(e)}")


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(agent_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Get a specific agent"""
    agent = await AgentService.get_by_id(db, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.put("/{agent_id}", response_model=AgentResponse)
async def update_agent(agent_id: uuid.UUID, request: AgentUpdateRequest, db: AsyncSession = Depends(get_db)):
    """Update an agent"""
    try:
        agent = await AgentService.update(db, agent_id, request)
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
        return agent
    except Exception as e:
        if "unique" in str(e).lower():
            raise HTTPException(status_code=409, detail="Agent name already exists")
        raise HTTPException(status_code=500, detail=f"Failed to update agent: {str(e)}")


@router.delete("/{agent_id}")
async def delete_agent(agent_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Delete an agent"""
    success = await AgentService.delete(db, agent_id)
    if not success:
        raise HTTPException(status_code=404, detail="Agent not found")
    return {"message": f"Agent {agent_id} deleted successfully"}


@router.get("/{agent_id}/tools")
async def get_agent_tools(agent_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Get all tools assigned to an agent"""
    agent = await AgentService.get_by_id(db, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    tools = await AgentService.get_tools(db, agent_id)
    return tools


@router.post("/{agent_id}/tools/{tool_id}")
async def assign_tool_to_agent(agent_id: uuid.UUID, tool_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Assign a tool to an agent"""
    # First check if both agent and tool exist
    agent = await AgentService.get_by_id(db, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    from ..services import ToolService
    tool = await ToolService.get_by_id(db, tool_id)
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")
    
    relation = await AgentService.add_tool(db, agent_id, tool_id)
    if not relation:
        raise HTTPException(status_code=409, detail="Tool is already assigned to this agent")
    
    return {"message": f"Tool {tool_id} assigned to agent {agent_id}"}


@router.delete("/{agent_id}/tools/{tool_id}")
async def remove_tool_from_agent(agent_id: uuid.UUID, tool_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Remove a tool from an agent"""
    # Check if agent exists
    agent = await AgentService.get_by_id(db, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    success = await AgentService.remove_tool(db, agent_id, tool_id)
    if not success:
        raise HTTPException(status_code=404, detail="Tool not assigned to this agent")
    
    return {"message": f"Tool {tool_id} removed from agent {agent_id}"}


# ------------------------------------------------------------------
# Agent invocation
# ------------------------------------------------------------------

@router.post("/{agent_id}/invoke", response_model=AgentInvokeResponse)
async def invoke_agent(agent_id: uuid.UUID, request: AgentInvokeRequest, db: AsyncSession = Depends(get_db)):
    """Invoke an agent with a prompt. The agent will use its linked MCP tools."""
    try:
        result = await AgentExecutor.invoke(db, agent_id, request.prompt)
        return AgentInvokeResponse(
            agent_id=agent_id,
            response=result.response,
            messages=result.messages,
        )
    except AgentExecutionError as e:
        logger.error("Agent invocation failed: %s", e.message)
        if "not found" in e.message:
            raise HTTPException(status_code=404, detail=e.message)
        if "not active" in e.message:
            raise HTTPException(status_code=400, detail=e.message)
        if "no enabled tools" in e.message.lower() or "no mcp" in e.message.lower():
            raise HTTPException(status_code=400, detail=e.message)
        raise HTTPException(status_code=500, detail=e.message)
    except MCPConnectionError as e:
        raise HTTPException(status_code=502, detail=e.message)