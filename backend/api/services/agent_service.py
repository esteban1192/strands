"""
Agent service for CRUD operations
"""
import uuid
from datetime import datetime
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, and_
from sqlalchemy.orm import selectinload

from ..db_models import AgentModel, AgentToolModel
from ..models import AgentCreateRequest, AgentUpdateRequest, AgentResponse, AgentToolRelationResponse


class AgentService:
    """Service for Agent CRUD operations"""

    @staticmethod
    async def get_all(db: AsyncSession) -> List[AgentResponse]:
        """Get all agents with tool count"""
        stmt = select(AgentModel).options(selectinload(AgentModel.agent_tools))
        result = await db.execute(stmt)
        agents = result.scalars().all()
        
        return [
            AgentResponse(
                id=agent.id,
                name=agent.name,
                description=agent.description,
                model=agent.model,
                status=agent.status,
                tools_count=len(agent.agent_tools),
                created_at=agent.created_at,
                updated_at=agent.updated_at
            )
            for agent in agents
        ]

    @staticmethod
    async def get_by_id(db: AsyncSession, agent_id: uuid.UUID) -> Optional[AgentResponse]:
        """Get agent by ID"""
        stmt = select(AgentModel).options(selectinload(AgentModel.agent_tools)).where(AgentModel.id == agent_id)
        result = await db.execute(stmt)
        agent = result.scalar_one_or_none()
        
        if not agent:
            return None
            
        return AgentResponse(
            id=agent.id,
            name=agent.name,
            description=agent.description,
            model=agent.model,
            status=agent.status,
            tools_count=len(agent.agent_tools),
            created_at=agent.created_at,
            updated_at=agent.updated_at
        )

    @staticmethod
    async def create(db: AsyncSession, agent_data: AgentCreateRequest) -> AgentResponse:
        """Create a new agent"""
        agent = AgentModel(
            name=agent_data.name,
            description=agent_data.description,
            model=agent_data.model,
            status=agent_data.status
        )
        db.add(agent)
        await db.commit()
        await db.refresh(agent)
        
        return AgentResponse(
            id=agent.id,
            name=agent.name,
            description=agent.description,
            model=agent.model,
            status=agent.status,
            tools_count=0,
            created_at=agent.created_at,
            updated_at=agent.updated_at
        )

    @staticmethod
    async def update(db: AsyncSession, agent_id: uuid.UUID, agent_data: AgentUpdateRequest) -> Optional[AgentResponse]:
        """Update an agent"""
        # Prepare update data, excluding None values
        update_data = {}
        if agent_data.name is not None:
            update_data["name"] = agent_data.name
        if agent_data.description is not None:
            update_data["description"] = agent_data.description
        if agent_data.model is not None:
            update_data["model"] = agent_data.model
        if agent_data.status is not None:
            update_data["status"] = agent_data.status
        
        if update_data:
            update_data["updated_at"] = datetime.utcnow()
            stmt = update(AgentModel).where(AgentModel.id == agent_id).values(**update_data)
            result = await db.execute(stmt)
            
            if result.rowcount == 0:
                return None
            
            await db.commit()
        
        return await AgentService.get_by_id(db, agent_id)

    @staticmethod
    async def delete(db: AsyncSession, agent_id: uuid.UUID) -> bool:
        """Delete an agent"""
        stmt = delete(AgentModel).where(AgentModel.id == agent_id)
        result = await db.execute(stmt)
        await db.commit()
        return result.rowcount > 0

    @staticmethod
    async def get_tools(db: AsyncSession, agent_id: uuid.UUID) -> List[dict]:
        """Get all tools assigned to an agent with tool details"""
        from ..db_models import ToolModel
        stmt = (
            select(AgentToolModel, ToolModel)
            .join(ToolModel, AgentToolModel.tool_id == ToolModel.id)
            .where(AgentToolModel.agent_id == agent_id)
        )
        result = await db.execute(stmt)
        rows = result.all()
        return [
            {
                "tool_id": str(at.tool_id),
                "tool_name": tool.name,
                "mcp_id": str(tool.mcp_id) if tool.mcp_id else None,
                "is_enabled": at.is_enabled,
                "added_at": at.added_at.isoformat(),
            }
            for at, tool in rows
        ]

    @staticmethod
    async def add_tool(db: AsyncSession, agent_id: uuid.UUID, tool_id: uuid.UUID) -> Optional[AgentToolRelationResponse]:
        """Add a tool to an agent"""
        # Check if relationship already exists
        stmt = select(AgentToolModel).where(
            and_(AgentToolModel.agent_id == agent_id, AgentToolModel.tool_id == tool_id)
        )
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()
        
        if existing:
            return None  # Relationship already exists
            
        agent_tool = AgentToolModel(agent_id=agent_id, tool_id=tool_id)
        db.add(agent_tool)
        await db.commit()
        await db.refresh(agent_tool)
        
        return AgentToolRelationResponse(
            id=agent_tool.id,
            agent_id=agent_tool.agent_id,
            tool_id=agent_tool.tool_id,
            added_at=agent_tool.added_at,
            is_enabled=agent_tool.is_enabled
        )

    @staticmethod
    async def remove_tool(db: AsyncSession, agent_id: uuid.UUID, tool_id: uuid.UUID) -> bool:
        """Remove a tool from an agent"""
        stmt = delete(AgentToolModel).where(
            and_(AgentToolModel.agent_id == agent_id, AgentToolModel.tool_id == tool_id)
        )
        result = await db.execute(stmt)
        await db.commit()
        return result.rowcount > 0