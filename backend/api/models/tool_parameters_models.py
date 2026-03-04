"""
Tool Parameters-related API models
"""
import uuid
from datetime import datetime
from pydantic import BaseModel, Field
from typing import Optional


class ToolParametersResponse(BaseModel):
    id: uuid.UUID
    tool_id: uuid.UUID
    name: str
    parameter_type: str
    default_value: Optional[str] = None
    is_required: bool = False
    description: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class ToolParametersCreateRequest(BaseModel):
    tool_id: uuid.UUID
    name: str = Field(..., min_length=1, max_length=255)
    parameter_type: str = Field(..., min_length=1, max_length=50)
    default_value: Optional[str] = None
    is_required: bool = False
    description: Optional[str] = None


class ToolParametersUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    parameter_type: Optional[str] = Field(None, min_length=1, max_length=50)
    default_value: Optional[str] = None
    is_required: Optional[bool] = None
    description: Optional[str] = None