"""
Tool-related API models
"""
import uuid
from datetime import datetime
from pydantic import BaseModel, Field
from typing import Optional, List


class ToolResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: Optional[str] = None
    is_active: bool = True
    requires_approval: bool = True
    mcp_id: Optional[uuid.UUID] = None
    mcp_name: Optional[str] = None
    mcp_assigned: bool = False
    parameters_count: int = 0
    created_at: datetime
    updated_at: datetime


class PaginatedToolsResponse(BaseModel):
    items: List[ToolResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class ToolCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    is_active: bool = True
    requires_approval: bool = True
    mcp_id: Optional[uuid.UUID] = None


class ToolUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    is_active: Optional[bool] = None
    requires_approval: Optional[bool] = None
    mcp_id: Optional[uuid.UUID] = None