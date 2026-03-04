"""
MCP endpoints for the Strands API
"""
import uuid
import logging
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from ..models import (
    MCPResponse, MCPCreateRequest, MCPUpdateRequest, MCPSyncToolsResponse
)
from ..models.tool_models import ToolResponse
from ..database import get_db
from ..services import MCPService
from core import MCPManager, MCPConnectionError, MCPSyncError, UnsupportedTransportError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mcps", tags=["mcps"])


@router.get("", response_model=List[MCPResponse])
async def get_mcps(db: AsyncSession = Depends(get_db)):
    """Get all MCPs"""
    return await MCPService.get_all(db)


@router.post("", response_model=MCPResponse, status_code=201)
async def create_mcp(request: MCPCreateRequest, db: AsyncSession = Depends(get_db)):
    """Create a new MCP"""
    try:
        return await MCPService.create(db, request)
    except Exception as e:
        # Handle unique constraint violations, etc.
        if "unique" in str(e).lower():
            raise HTTPException(status_code=409, detail="MCP name already exists")
        raise HTTPException(status_code=500, detail=f"Failed to create MCP: {str(e)}")


@router.get("/{mcp_id}", response_model=MCPResponse)
async def get_mcp(mcp_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Get a specific MCP"""
    mcp = await MCPService.get_by_id(db, mcp_id)
    if not mcp:
        raise HTTPException(status_code=404, detail="MCP not found")
    return mcp


@router.put("/{mcp_id}", response_model=MCPResponse)
async def update_mcp(mcp_id: uuid.UUID, request: MCPUpdateRequest, db: AsyncSession = Depends(get_db)):
    """Update an MCP"""
    try:
        mcp = await MCPService.update(db, mcp_id, request)
        if not mcp:
            raise HTTPException(status_code=404, detail="MCP not found")
        return mcp
    except Exception as e:
        if "unique" in str(e).lower():
            raise HTTPException(status_code=409, detail="MCP name already exists")
        raise HTTPException(status_code=500, detail=f"Failed to update MCP: {str(e)}")


@router.delete("/{mcp_id}")
async def delete_mcp(mcp_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Delete an MCP"""
    success = await MCPService.delete(db, mcp_id)
    if not success:
        raise HTTPException(status_code=404, detail="MCP not found")
    return {"message": f"MCP {mcp_id} deleted successfully"}


# ------------------------------------------------------------------
# Tool sync endpoints
# ------------------------------------------------------------------

@router.post("/{mcp_id}/sync-tools", response_model=MCPSyncToolsResponse)
async def sync_mcp_tools(mcp_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Connect to the MCP server and sync its tools into the database."""
    try:
        synced_tools = await MCPManager.sync_tools(db, mcp_id)
        return MCPSyncToolsResponse(
            mcp_id=mcp_id,
            tools_synced=len(synced_tools),
            message=f"Successfully synced {len(synced_tools)} tools",
        )
    except UnsupportedTransportError as e:
        raise HTTPException(status_code=400, detail=e.message)
    except MCPConnectionError as e:
        raise HTTPException(status_code=502, detail=e.message)
    except MCPSyncError as e:
        raise HTTPException(status_code=500, detail=e.message)


@router.get("/{mcp_id}/tools", response_model=List[ToolResponse])
async def get_mcp_tools(mcp_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Get all tools that belong to a specific MCP."""
    # Verify MCP exists
    mcp = await MCPService.get_by_id(db, mcp_id)
    if not mcp:
        raise HTTPException(status_code=404, detail="MCP not found")

    from ..services import ToolService
    result = await ToolService.get_all(db, page=1, page_size=1000, mcp_id=mcp_id)
    return result.items