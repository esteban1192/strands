"""
MCP-related API models
"""
import uuid
from datetime import datetime
from typing import Optional, Literal, List

from pydantic import BaseModel, Field


# Supported transport types — extend this union as new transports are added
MCPTransportType = Literal["streamable_http", "stdio"]


class MCPResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: Optional[str] = None
    transport_type: str
    url: Optional[str] = None
    command: Optional[str] = None
    args: Optional[List[str]] = None
    env: Optional[List[str]] = None
    tools_count: int = 0
    synced_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class MCPCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    transport_type: MCPTransportType = Field(default="streamable_http")
    url: Optional[str] = Field(None, max_length=2048)
    command: Optional[str] = Field(None, max_length=1024)
    args: Optional[List[str]] = None
    env: Optional[List[str]] = None


class MCPUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    transport_type: Optional[MCPTransportType] = None
    url: Optional[str] = Field(None, max_length=2048)
    command: Optional[str] = Field(None, max_length=1024)
    args: Optional[List[str]] = None
    env: Optional[List[str]] = None


class MCPSyncToolsResponse(BaseModel):
    """Response for the sync-tools operation"""
    mcp_id: uuid.UUID
    tools_synced: int
    message: str