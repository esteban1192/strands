"""
SQLAlchemy database models for Strands API
"""
import uuid
from datetime import datetime
from typing import Optional, List
from sqlalchemy import Column, String, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, Mapped
from sqlalchemy.sql import func

from .database import Base


class AgentModel(Base):
    """SQLAlchemy model for Agents table"""
    __tablename__ = "agents"
    __table_args__ = {"schema": "strands"}

    id: Mapped[UUID] = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = Column(String(255), nullable=False, unique=True)
    description: Mapped[Optional[str]] = Column(Text, nullable=True)
    model: Mapped[str] = Column(String(255), nullable=False)
    system_prompt: Mapped[Optional[str]] = Column(Text, nullable=True)
    status: Mapped[str] = Column(String(50), nullable=False, default="active")
    created_at: Mapped[datetime] = Column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    agent_tools: Mapped[List["AgentToolModel"]] = relationship("AgentToolModel", back_populates="agent", cascade="all, delete-orphan")


class ToolModel(Base):
    """SQLAlchemy model for Tools table"""
    __tablename__ = "tools"
    __table_args__ = {"schema": "strands"}

    id: Mapped[UUID] = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mcp_id: Mapped[Optional[UUID]] = Column(UUID(as_uuid=True), ForeignKey("strands.mcps.id"), nullable=True)
    name: Mapped[str] = Column(String(255), nullable=False, unique=True)
    description: Mapped[Optional[str]] = Column(Text, nullable=True)
    is_active: Mapped[bool] = Column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = Column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    mcp: Mapped[Optional["MCPModel"]] = relationship("MCPModel", back_populates="tools")
    tool_parameters: Mapped[List["ToolParameterModel"]] = relationship("ToolParameterModel", back_populates="tool", cascade="all, delete-orphan")
    agent_tools: Mapped[List["AgentToolModel"]] = relationship("AgentToolModel", back_populates="tool", cascade="all, delete-orphan")


class MCPModel(Base):
    """SQLAlchemy model for MCPs table"""
    __tablename__ = "mcps"
    __table_args__ = {"schema": "strands"}

    id: Mapped[UUID] = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = Column(String(255), nullable=False, unique=True)
    description: Mapped[Optional[str]] = Column(Text, nullable=True)
    transport_type: Mapped[str] = Column(String(50), nullable=False, default="streamable_http")
    url: Mapped[Optional[str]] = Column(String(2048), nullable=True)
    command: Mapped[Optional[str]] = Column(String(1024), nullable=True)
    args: Mapped[Optional[str]] = Column(Text, nullable=True)       # JSON-encoded list of strings
    env: Mapped[Optional[str]] = Column(Text, nullable=True)        # JSON-encoded list of env var names to forward
    synced_at: Mapped[Optional[datetime]] = Column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = Column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    tools: Mapped[List["ToolModel"]] = relationship("ToolModel", back_populates="mcp", cascade="all, delete-orphan")


class ToolParameterModel(Base):
    """SQLAlchemy model for Tool Parameters table"""
    __tablename__ = "tool_parameters"
    __table_args__ = {"schema": "strands"}

    id: Mapped[UUID] = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tool_id: Mapped[UUID] = Column(UUID(as_uuid=True), ForeignKey("strands.tools.id"), nullable=False)
    name: Mapped[str] = Column(String(255), nullable=False)
    parameter_type: Mapped[str] = Column(String(50), nullable=False)
    default_value: Mapped[Optional[str]] = Column(Text, nullable=True)
    is_required: Mapped[bool] = Column(Boolean, nullable=False, default=False)
    description: Mapped[Optional[str]] = Column(Text, nullable=True)
    created_at: Mapped[datetime] = Column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    tool: Mapped["ToolModel"] = relationship("ToolModel", back_populates="tool_parameters")


class AgentToolModel(Base):
    """SQLAlchemy model for Agent-Tool relationship table"""
    __tablename__ = "agent_tools"
    __table_args__ = {"schema": "strands"}

    id: Mapped[UUID] = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id: Mapped[UUID] = Column(UUID(as_uuid=True), ForeignKey("strands.agents.id"), nullable=False)
    tool_id: Mapped[UUID] = Column(UUID(as_uuid=True), ForeignKey("strands.tools.id"), nullable=False)
    added_at: Mapped[datetime] = Column(DateTime(timezone=True), server_default=func.now())
    is_enabled: Mapped[bool] = Column(Boolean, nullable=False, default=True)

    # Relationships
    agent: Mapped["AgentModel"] = relationship("AgentModel", back_populates="agent_tools")
    tool: Mapped["ToolModel"] = relationship("ToolModel", back_populates="agent_tools")