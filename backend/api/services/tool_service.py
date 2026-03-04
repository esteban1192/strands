"""
Tool service for CRUD operations
"""
import math
import uuid
from datetime import datetime
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, func as sa_func
from sqlalchemy.orm import selectinload, joinedload

from ..db_models import ToolModel, MCPModel
from ..models import ToolCreateRequest, ToolUpdateRequest, ToolResponse
from ..models.tool_models import PaginatedToolsResponse


class ToolService:
    """Service for Tool CRUD operations"""

    @staticmethod
    def _to_response(tool: ToolModel) -> ToolResponse:
        """Map ORM model to response, expects mcp relationship loaded."""
        return ToolResponse(
            id=tool.id,
            name=tool.name,
            description=tool.description,
            is_active=tool.is_active,
            requires_approval=tool.requires_approval,
            mcp_id=tool.mcp_id,
            mcp_name=tool.mcp.name if tool.mcp else None,
            mcp_assigned=tool.mcp_id is not None,
            parameters_count=len(tool.tool_parameters),
            created_at=tool.created_at,
            updated_at=tool.updated_at,
        )

    @staticmethod
    async def get_all(
        db: AsyncSession,
        page: int = 1,
        page_size: int = 20,
        mcp_id: Optional[uuid.UUID] = None,
    ) -> PaginatedToolsResponse:
        """Get tools with pagination and optional MCP filter"""
        # Base filter
        conditions = []
        if mcp_id is not None:
            conditions.append(ToolModel.mcp_id == mcp_id)

        # Count
        count_stmt = select(sa_func.count(ToolModel.id))
        for cond in conditions:
            count_stmt = count_stmt.where(cond)
        total = (await db.execute(count_stmt)).scalar() or 0

        # Query
        stmt = (
            select(ToolModel)
            .options(selectinload(ToolModel.tool_parameters), joinedload(ToolModel.mcp))
        )
        for cond in conditions:
            stmt = stmt.where(cond)
        stmt = stmt.order_by(ToolModel.name).offset((page - 1) * page_size).limit(page_size)

        result = await db.execute(stmt)
        tools = result.unique().scalars().all()

        return PaginatedToolsResponse(
            items=[ToolService._to_response(t) for t in tools],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=math.ceil(total / page_size) if total > 0 else 1,
        )

    @staticmethod
    async def get_by_id(db: AsyncSession, tool_id: uuid.UUID) -> Optional[ToolResponse]:
        """Get tool by ID"""
        stmt = (
            select(ToolModel)
            .options(selectinload(ToolModel.tool_parameters), joinedload(ToolModel.mcp))
            .where(ToolModel.id == tool_id)
        )
        result = await db.execute(stmt)
        tool = result.unique().scalar_one_or_none()
        
        if not tool:
            return None
            
        return ToolService._to_response(tool)

    @staticmethod
    async def create(db: AsyncSession, tool_data: ToolCreateRequest) -> ToolResponse:
        """Create a new tool"""
        tool = ToolModel(
            name=tool_data.name,
            description=tool_data.description,
            is_active=tool_data.is_active,
            requires_approval=tool_data.requires_approval,
            mcp_id=tool_data.mcp_id
        )
        db.add(tool)
        await db.commit()
        
        # Re-fetch with relationships eagerly loaded
        return await ToolService.get_by_id(db, tool.id)

    @staticmethod
    async def update(db: AsyncSession, tool_id: uuid.UUID, tool_data: ToolUpdateRequest) -> Optional[ToolResponse]:
        """Update a tool"""
        update_data = {}
        if tool_data.name is not None:
            update_data["name"] = tool_data.name
        if tool_data.description is not None:
            update_data["description"] = tool_data.description
        if tool_data.is_active is not None:
            update_data["is_active"] = tool_data.is_active
        if tool_data.requires_approval is not None:
            update_data["requires_approval"] = tool_data.requires_approval
        if tool_data.mcp_id is not None:
            update_data["mcp_id"] = tool_data.mcp_id
        
        if update_data:
            update_data["updated_at"] = datetime.utcnow()
            stmt = update(ToolModel).where(ToolModel.id == tool_id).values(**update_data)
            result = await db.execute(stmt)
            
            if result.rowcount == 0:
                return None
            
            await db.commit()
        
        return await ToolService.get_by_id(db, tool_id)

    @staticmethod
    async def delete(db: AsyncSession, tool_id: uuid.UUID) -> bool:
        """Delete a tool"""
        stmt = delete(ToolModel).where(ToolModel.id == tool_id)
        result = await db.execute(stmt)
        await db.commit()
        return result.rowcount > 0