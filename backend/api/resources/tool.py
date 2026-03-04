"""
Tool endpoints for the Strands API
"""
import uuid
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import (
    ToolResponse, ToolCreateRequest, ToolUpdateRequest
)
from ..models.tool_models import PaginatedToolsResponse
from ..database import get_db
from ..services import ToolService

router = APIRouter(prefix="/tools", tags=["tools"])


@router.get("", response_model=PaginatedToolsResponse)
async def get_tools(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    mcp_id: Optional[uuid.UUID] = Query(None, description="Filter by MCP ID"),
    db: AsyncSession = Depends(get_db),
):
    """Get tools with pagination and optional MCP filter"""
    return await ToolService.get_all(db, page=page, page_size=page_size, mcp_id=mcp_id)


@router.post("", response_model=ToolResponse, status_code=201)
async def create_tool(request: ToolCreateRequest, db: AsyncSession = Depends(get_db)):
    """Create a new tool"""
    try:
        return await ToolService.create(db, request)
    except Exception as e:
        # Handle unique constraint violations, etc.
        if "unique" in str(e).lower():
            raise HTTPException(status_code=409, detail="Tool name already exists")
        raise HTTPException(status_code=500, detail=f"Failed to create tool: {str(e)}")


@router.get("/{tool_id}", response_model=ToolResponse)
async def get_tool(tool_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Get a specific tool"""
    tool = await ToolService.get_by_id(db, tool_id)
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")
    return tool


@router.put("/{tool_id}", response_model=ToolResponse)
async def update_tool(tool_id: uuid.UUID, request: ToolUpdateRequest, db: AsyncSession = Depends(get_db)):
    """Update a tool"""
    try:
        tool = await ToolService.update(db, tool_id, request)
        if not tool:
            raise HTTPException(status_code=404, detail="Tool not found")
        return tool
    except Exception as e:
        if "unique" in str(e).lower():
            raise HTTPException(status_code=409, detail="Tool name already exists")
        raise HTTPException(status_code=500, detail=f"Failed to update tool: {str(e)}")


@router.delete("/{tool_id}")
async def delete_tool(tool_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Delete a tool"""
    success = await ToolService.delete(db, tool_id)
    if not success:
        raise HTTPException(status_code=404, detail="Tool not found")
    return {"message": f"Tool {tool_id} deleted successfully"}