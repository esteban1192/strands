"""
Service for Agent Sub-Agent relationship CRUD operations.
"""
import uuid
from typing import List, Optional

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..db_models import AgentSubAgentModel, AgentModel
from ..models import AgentSubAgentResponse


class AgentSubAgentService:
    """CRUD operations for agent-to-agent (sub-agent) relationships."""

    @staticmethod
    async def list_sub_agents(
        db: AsyncSession,
        parent_agent_id: uuid.UUID,
    ) -> List[AgentSubAgentResponse]:
        """Return all sub-agents linked to a parent agent."""
        stmt = (
            select(AgentSubAgentModel)
            .options(selectinload(AgentSubAgentModel.child_agent))
            .where(AgentSubAgentModel.parent_agent_id == parent_agent_id)
            .order_by(AgentSubAgentModel.added_at)
        )
        result = await db.execute(stmt)
        rows = result.scalars().all()
        return [AgentSubAgentService._to_response(r) for r in rows]

    @staticmethod
    async def add_sub_agent(
        db: AsyncSession,
        parent_agent_id: uuid.UUID,
        child_agent_id: uuid.UUID,
    ) -> AgentSubAgentResponse:
        """Link a child agent to a parent agent.

        Raises ValueError if:
          - parent and child are the same agent
          - the child agent does not exist
          - the relationship already exists
        """
        if parent_agent_id == child_agent_id:
            raise ValueError("An agent cannot be its own sub-agent")

        # Verify child exists
        child_stmt = select(AgentModel).where(AgentModel.id == child_agent_id)
        child_result = await db.execute(child_stmt)
        child = child_result.scalar_one_or_none()
        if not child:
            raise ValueError(f"Child agent {child_agent_id} not found")

        # Check for duplicate
        dup_stmt = select(AgentSubAgentModel).where(
            AgentSubAgentModel.parent_agent_id == parent_agent_id,
            AgentSubAgentModel.child_agent_id == child_agent_id,
        )
        dup_result = await db.execute(dup_stmt)
        if dup_result.scalar_one_or_none():
            raise ValueError("Sub-agent relationship already exists")

        row = AgentSubAgentModel(
            parent_agent_id=parent_agent_id,
            child_agent_id=child_agent_id,
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)

        # Eager-load child for the response
        stmt = (
            select(AgentSubAgentModel)
            .options(selectinload(AgentSubAgentModel.child_agent))
            .where(AgentSubAgentModel.id == row.id)
        )
        result = await db.execute(stmt)
        row = result.scalar_one()
        return AgentSubAgentService._to_response(row)

    @staticmethod
    async def remove_sub_agent(
        db: AsyncSession,
        parent_agent_id: uuid.UUID,
        child_agent_id: uuid.UUID,
    ) -> bool:
        """Remove a sub-agent link. Returns True if a row was deleted."""
        stmt = delete(AgentSubAgentModel).where(
            AgentSubAgentModel.parent_agent_id == parent_agent_id,
            AgentSubAgentModel.child_agent_id == child_agent_id,
        )
        result = await db.execute(stmt)
        await db.commit()
        return result.rowcount > 0

    @staticmethod
    async def get_enabled_sub_agents(
        db: AsyncSession,
        parent_agent_id: uuid.UUID,
    ) -> List[AgentModel]:
        """Return full AgentModel objects for all enabled sub-agents of a parent.

        Used by AgentExecutor to build virtual tools.
        """
        stmt = (
            select(AgentModel)
            .join(
                AgentSubAgentModel,
                AgentSubAgentModel.child_agent_id == AgentModel.id,
            )
            .where(
                AgentSubAgentModel.parent_agent_id == parent_agent_id,
                AgentSubAgentModel.is_enabled == True,
            )
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_response(row: AgentSubAgentModel) -> AgentSubAgentResponse:
        child = row.child_agent
        return AgentSubAgentResponse(
            id=row.id,
            parent_agent_id=row.parent_agent_id,
            child_agent_id=row.child_agent_id,
            child_agent_name=child.name if child else "Unknown",
            child_agent_description=child.description if child else None,
            child_agent_status=child.status if child else "unknown",
            is_enabled=row.is_enabled,
            added_at=row.added_at,
        )
