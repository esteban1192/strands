"""
Tool Parameters service for CRUD operations
"""
import uuid
from datetime import datetime
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete

from ..db_models import ToolParameterModel
from ..models import ToolParametersCreateRequest, ToolParametersUpdateRequest, ToolParametersResponse


class ToolParametersService:
    """Service for Tool Parameters CRUD operations"""

    @staticmethod
    async def get_by_tool_id(db: AsyncSession, tool_id: uuid.UUID) -> List[ToolParametersResponse]:
        """Get all parameters for a tool"""
        stmt = select(ToolParameterModel).where(ToolParameterModel.tool_id == tool_id)
        result = await db.execute(stmt)
        parameters = result.scalars().all()
        
        return [
            ToolParametersResponse(
                id=param.id,
                tool_id=param.tool_id,
                name=param.name,
                parameter_type=param.parameter_type,
                default_value=param.default_value,
                is_required=param.is_required,
                description=param.description,
                created_at=param.created_at,
                updated_at=param.updated_at
            )
            for param in parameters
        ]

    @staticmethod
    async def get_by_id(db: AsyncSession, param_id: uuid.UUID) -> Optional[ToolParametersResponse]:
        """Get parameter by ID"""
        stmt = select(ToolParameterModel).where(ToolParameterModel.id == param_id)
        result = await db.execute(stmt)
        param = result.scalar_one_or_none()
        
        if not param:
            return None
            
        return ToolParametersResponse(
            id=param.id,
            tool_id=param.tool_id,
            name=param.name,
            parameter_type=param.parameter_type,
            default_value=param.default_value,
            is_required=param.is_required,
            description=param.description,
            created_at=param.created_at,
            updated_at=param.updated_at
        )

    @staticmethod
    async def create(db: AsyncSession, param_data: ToolParametersCreateRequest) -> ToolParametersResponse:
        """Create a new tool parameter"""
        param = ToolParameterModel(
            tool_id=param_data.tool_id,
            name=param_data.name,
            parameter_type=param_data.parameter_type,
            default_value=param_data.default_value,
            is_required=param_data.is_required,
            description=param_data.description
        )
        db.add(param)
        await db.commit()
        await db.refresh(param)
        
        return ToolParametersResponse(
            id=param.id,
            tool_id=param.tool_id,
            name=param.name,
            parameter_type=param.parameter_type,
            default_value=param.default_value,
            is_required=param.is_required,
            description=param.description,
            created_at=param.created_at,
            updated_at=param.updated_at
        )

    @staticmethod
    async def update(db: AsyncSession, param_id: uuid.UUID, param_data: ToolParametersUpdateRequest) -> Optional[ToolParametersResponse]:
        """Update a tool parameter"""
        update_data = {}
        if param_data.name is not None:
            update_data["name"] = param_data.name
        if param_data.parameter_type is not None:
            update_data["parameter_type"] = param_data.parameter_type
        if param_data.default_value is not None:
            update_data["default_value"] = param_data.default_value
        if param_data.is_required is not None:
            update_data["is_required"] = param_data.is_required
        if param_data.description is not None:
            update_data["description"] = param_data.description
        
        if update_data:
            update_data["updated_at"] = datetime.utcnow()
            stmt = update(ToolParameterModel).where(ToolParameterModel.id == param_id).values(**update_data)
            result = await db.execute(stmt)
            
            if result.rowcount == 0:
                return None
            
            await db.commit()
        
        return await ToolParametersService.get_by_id(db, param_id)

    @staticmethod
    async def delete(db: AsyncSession, param_id: uuid.UUID) -> bool:
        """Delete a tool parameter"""
        stmt = delete(ToolParameterModel).where(ToolParameterModel.id == param_id)
        result = await db.execute(stmt)
        await db.commit()
        return result.rowcount > 0