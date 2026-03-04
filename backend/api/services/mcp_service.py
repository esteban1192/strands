"""
MCP service for CRUD operations
"""
import json
import uuid
from datetime import datetime
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete
from sqlalchemy.orm import selectinload

from ..db_models import MCPModel
from ..models import MCPCreateRequest, MCPUpdateRequest, MCPResponse


class MCPService:
    """Service for MCP CRUD operations"""

    @staticmethod
    def _to_response(mcp: MCPModel) -> MCPResponse:
        """Map ORM model to Pydantic response"""
        # Parse env — handle both old dict format and new list format
        env = None
        if mcp.env:
            parsed = json.loads(mcp.env)
            if isinstance(parsed, dict):
                # Legacy format: {"KEY": "value"} → extract just the keys
                env = list(parsed.keys())
            elif isinstance(parsed, list):
                env = parsed

        return MCPResponse(
            id=mcp.id,
            name=mcp.name,
            description=mcp.description,
            transport_type=mcp.transport_type,
            url=mcp.url,
            command=mcp.command,
            args=json.loads(mcp.args) if mcp.args else None,
            env=env,
            tools_count=len(mcp.tools) if mcp.tools else 0,
            synced_at=mcp.synced_at,
            created_at=mcp.created_at,
            updated_at=mcp.updated_at
        )

    @staticmethod
    async def get_all(db: AsyncSession) -> List[MCPResponse]:
        """Get all MCPs with tool count"""
        stmt = select(MCPModel).options(selectinload(MCPModel.tools))
        result = await db.execute(stmt)
        mcps = result.scalars().all()
        return [MCPService._to_response(mcp) for mcp in mcps]

    @staticmethod
    async def get_by_id(db: AsyncSession, mcp_id: uuid.UUID) -> Optional[MCPResponse]:
        """Get MCP by ID"""
        stmt = select(MCPModel).options(selectinload(MCPModel.tools)).where(MCPModel.id == mcp_id)
        result = await db.execute(stmt)
        mcp = result.scalar_one_or_none()
        if not mcp:
            return None
        return MCPService._to_response(mcp)

    @staticmethod
    async def get_model_by_id(db: AsyncSession, mcp_id: uuid.UUID) -> Optional[MCPModel]:
        """Get raw ORM model by ID (for use by core layer)"""
        stmt = select(MCPModel).where(MCPModel.id == mcp_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def create(db: AsyncSession, mcp_data: MCPCreateRequest) -> MCPResponse:
        """Create a new MCP"""
        mcp = MCPModel(
            name=mcp_data.name,
            description=mcp_data.description,
            transport_type=mcp_data.transport_type,
            url=mcp_data.url,
            command=mcp_data.command,
            args=json.dumps(mcp_data.args) if mcp_data.args else None,
            env=json.dumps(mcp_data.env) if mcp_data.env else None,
        )
        db.add(mcp)
        await db.commit()
        await db.refresh(mcp)

        return MCPResponse(
            id=mcp.id,
            name=mcp.name,
            description=mcp.description,
            transport_type=mcp.transport_type,
            url=mcp.url,
            command=mcp.command,
            args=json.loads(mcp.args) if mcp.args else None,
            env=mcp_data.env,
            tools_count=0,
            synced_at=mcp.synced_at,
            created_at=mcp.created_at,
            updated_at=mcp.updated_at
        )

    @staticmethod
    async def update(db: AsyncSession, mcp_id: uuid.UUID, mcp_data: MCPUpdateRequest) -> Optional[MCPResponse]:
        """Update an MCP"""
        update_data = {}
        if mcp_data.name is not None:
            update_data["name"] = mcp_data.name
        if mcp_data.description is not None:
            update_data["description"] = mcp_data.description
        if mcp_data.transport_type is not None:
            update_data["transport_type"] = mcp_data.transport_type
        if mcp_data.url is not None:
            update_data["url"] = mcp_data.url
        if mcp_data.command is not None:
            update_data["command"] = mcp_data.command
        if mcp_data.args is not None:
            update_data["args"] = json.dumps(mcp_data.args)
        if mcp_data.env is not None:
            update_data["env"] = json.dumps(mcp_data.env)

        if update_data:
            update_data["updated_at"] = datetime.utcnow()
            stmt = update(MCPModel).where(MCPModel.id == mcp_id).values(**update_data)
            result = await db.execute(stmt)

            if result.rowcount == 0:
                return None

            await db.commit()

        return await MCPService.get_by_id(db, mcp_id)

    @staticmethod
    async def update_synced_at(db: AsyncSession, mcp_id: uuid.UUID) -> None:
        """Set synced_at to now (called after successful tool sync)"""
        stmt = (
            update(MCPModel)
            .where(MCPModel.id == mcp_id)
            .values(synced_at=datetime.utcnow(), updated_at=datetime.utcnow())
        )
        await db.execute(stmt)
        await db.commit()

    @staticmethod
    async def delete(db: AsyncSession, mcp_id: uuid.UUID) -> bool:
        """Delete an MCP"""
        stmt = delete(MCPModel).where(MCPModel.id == mcp_id)
        result = await db.execute(stmt)
        await db.commit()
        return result.rowcount > 0