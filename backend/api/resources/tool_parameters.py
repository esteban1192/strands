"""
Tool Parameters endpoints for the Strands API
"""
import uuid
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from ..models import (
    ToolParametersResponse, ToolParametersCreateRequest, ToolParametersUpdateRequest
)
from ..database import get_db
from ..services import ToolParametersService, ToolService

router = APIRouter(prefix="/tool-parameters", tags=["tool-parameters"])


@router.get("/tool/{tool_id}", response_model=List[ToolParametersResponse])
async def get_tool_parameters_by_tool(tool_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Get all parameters for a specific tool"""
    # Check if tool exists
    tool = await ToolService.get_by_id(db, tool_id)
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")
    
    return await ToolParametersService.get_by_tool_id(db, tool_id)


@router.post("", response_model=ToolParametersResponse, status_code=201)
async def create_tool_parameter(request: ToolParametersCreateRequest, db: AsyncSession = Depends(get_db)):
    """Create a new tool parameter"""
    # Check if tool exists
    tool = await ToolService.get_by_id(db, request.tool_id)
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")
    
    try:
        return await ToolParametersService.create(db, request)
    except Exception as e:
        # Handle unique constraint violations, etc.
        if "unique" in str(e).lower():
            raise HTTPException(status_code=409, detail="Parameter name already exists for this tool")
        raise HTTPException(status_code=500, detail=f"Failed to create tool parameter: {str(e)}")


@router.get("/{param_id}", response_model=ToolParametersResponse)
async def get_tool_parameter(param_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Get a specific tool parameter"""
    param = await ToolParametersService.get_by_id(db, param_id)
    if not param:
        raise HTTPException(status_code=404, detail="Tool parameter not found")
    return param


@router.put("/{param_id}", response_model=ToolParametersResponse)
async def update_tool_parameter(param_id: uuid.UUID, request: ToolParametersUpdateRequest, db: AsyncSession = Depends(get_db)):
    """Update a tool parameter"""
    try:
        param = await ToolParametersService.update(db, param_id, request)
        if not param:
            raise HTTPException(status_code=404, detail="Tool parameter not found")
        return param
    except Exception as e:
        if "unique" in str(e).lower():
            raise HTTPException(status_code=409, detail="Parameter name already exists for this tool")
        raise HTTPException(status_code=500, detail=f"Failed to update tool parameter: {str(e)}")


@router.delete("/{param_id}")
async def delete_tool_parameter(param_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Delete a tool parameter"""
    success = await ToolParametersService.delete(db, param_id)
    if not success:
        raise HTTPException(status_code=404, detail="Tool parameter not found")
    return {"message": f"Tool parameter {param_id} deleted successfully"}