"""
SQLAlchemy database models for Strands API
"""
import uuid
from datetime import datetime
from typing import Optional, List
from sqlalchemy import Column, String, Text, Boolean, DateTime, Integer, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
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
    sub_agents: Mapped[List["AgentSubAgentModel"]] = relationship(
        "AgentSubAgentModel", foreign_keys="AgentSubAgentModel.parent_agent_id",
        back_populates="parent_agent", cascade="all, delete-orphan",
    )
    parent_agents: Mapped[List["AgentSubAgentModel"]] = relationship(
        "AgentSubAgentModel", foreign_keys="AgentSubAgentModel.child_agent_id",
        back_populates="child_agent", cascade="all, delete-orphan",
    )
    chats: Mapped[List["ChatModel"]] = relationship("ChatModel", back_populates="agent", cascade="all, delete-orphan")


class ToolModel(Base):
    """SQLAlchemy model for Tools table"""
    __tablename__ = "tools"
    __table_args__ = {"schema": "strands"}

    id: Mapped[UUID] = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mcp_id: Mapped[Optional[UUID]] = Column(UUID(as_uuid=True), ForeignKey("strands.mcps.id"), nullable=True)
    name: Mapped[str] = Column(String(255), nullable=False, unique=True)
    description: Mapped[Optional[str]] = Column(Text, nullable=True)
    is_active: Mapped[bool] = Column(Boolean, nullable=False, default=True)
    requires_approval: Mapped[bool] = Column(Boolean, nullable=False, default=True)
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


class AgentSubAgentModel(Base):
    """SQLAlchemy model for Agent-to-Agent (sub-agent) relationship table"""
    __tablename__ = "agent_sub_agents"
    __table_args__ = {"schema": "strands"}

    id: Mapped[UUID] = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    parent_agent_id: Mapped[UUID] = Column(UUID(as_uuid=True), ForeignKey("strands.agents.id"), nullable=False)
    child_agent_id: Mapped[UUID] = Column(UUID(as_uuid=True), ForeignKey("strands.agents.id"), nullable=False)
    is_enabled: Mapped[bool] = Column(Boolean, nullable=False, default=True)
    added_at: Mapped[datetime] = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    parent_agent: Mapped["AgentModel"] = relationship("AgentModel", foreign_keys=[parent_agent_id], back_populates="sub_agents")
    child_agent: Mapped["AgentModel"] = relationship("AgentModel", foreign_keys=[child_agent_id], back_populates="parent_agents")


class ChatModel(Base):
    """SQLAlchemy model for Chats table"""
    __tablename__ = "chats"
    __table_args__ = {"schema": "strands"}

    id: Mapped[UUID] = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id: Mapped[UUID] = Column(UUID(as_uuid=True), ForeignKey("strands.agents.id"), nullable=False)
    title: Mapped[Optional[str]] = Column(String(255), nullable=True)
    created_at: Mapped[datetime] = Column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    agent: Mapped["AgentModel"] = relationship("AgentModel", back_populates="chats")
    messages: Mapped[List["ChatMessageModel"]] = relationship(
        "ChatMessageModel", back_populates="chat", cascade="all, delete-orphan",
        order_by="ChatMessageModel.ordinal",
    )
    delegations: Mapped[List["ChatDelegationModel"]] = relationship(
        "ChatDelegationModel", back_populates="chat", cascade="all, delete-orphan",
    )


class ChatMessageModel(Base):
    """SQLAlchemy model for Chat Messages table.

    Each row represents a single content block — one text, one tool_call,
    or one tool_result.  The ``message_type`` column classifies it.
    """
    __tablename__ = "chat_messages"
    __table_args__ = {"schema": "strands"}

    id: Mapped[UUID] = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    chat_id: Mapped[UUID] = Column(UUID(as_uuid=True), ForeignKey("strands.chats.id"), nullable=False)
    agent_id: Mapped[Optional[UUID]] = Column(UUID(as_uuid=True), ForeignKey("strands.agents.id"), nullable=True)
    role: Mapped[str] = Column(String(50), nullable=False)
    message_type: Mapped[str] = Column(String(50), nullable=False, default="text")
    content: Mapped[dict] = Column(JSONB, nullable=False)
    ordinal: Mapped[int] = Column(Integer, nullable=False)
    is_approved: Mapped[bool] = Column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    chat: Mapped["ChatModel"] = relationship("ChatModel", back_populates="messages")
    agent: Mapped[Optional["AgentModel"]] = relationship("AgentModel")
    tool_call: Mapped[Optional["ChatToolCallModel"]] = relationship(
        "ChatToolCallModel", back_populates="message", uselist=False, cascade="all, delete-orphan",
    )
    tool_result: Mapped[Optional["ChatToolResultModel"]] = relationship(
        "ChatToolResultModel", back_populates="message", uselist=False, cascade="all, delete-orphan",
    )


class ChatToolCallModel(Base):
    """Structured data for a tool_call message (1:1 with ChatMessageModel)."""
    __tablename__ = "chat_tool_calls"
    __table_args__ = {"schema": "strands"}

    id: Mapped[UUID] = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    message_id: Mapped[UUID] = Column(UUID(as_uuid=True), ForeignKey("strands.chat_messages.id"), nullable=False, unique=True)
    tool_use_id: Mapped[str] = Column(String(255), nullable=False)
    tool_name: Mapped[str] = Column(String(255), nullable=False)
    input: Mapped[Optional[dict]] = Column(JSONB, nullable=True)
    created_at: Mapped[datetime] = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    message: Mapped["ChatMessageModel"] = relationship("ChatMessageModel", back_populates="tool_call")


class ChatToolResultModel(Base):
    """Structured data for a tool_result message (1:1 with ChatMessageModel)."""
    __tablename__ = "chat_tool_results"
    __table_args__ = {"schema": "strands"}

    id: Mapped[UUID] = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    message_id: Mapped[UUID] = Column(UUID(as_uuid=True), ForeignKey("strands.chat_messages.id"), nullable=False, unique=True)
    tool_use_id: Mapped[str] = Column(String(255), nullable=False)
    status: Mapped[str] = Column(String(50), nullable=False)
    result: Mapped[Optional[dict]] = Column(JSONB, nullable=True)
    created_at: Mapped[datetime] = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    message: Mapped["ChatMessageModel"] = relationship("ChatMessageModel", back_populates="tool_result")


class ChatDelegationModel(Base):
    """Tracks a delegation session within a chat.

    Each row represents one agent's involvement in a delegation chain.
    The root agent (the chat's own agent) has ``parent_delegation_id = NULL``
    and ``tool_use_id = NULL``.  Each sub-agent invocation creates a child
    row pointing at its parent delegation via ``parent_delegation_id`` and
    recording which ``tool_use_id`` in the parent triggered it.
    """
    __tablename__ = "chat_delegations"
    __table_args__ = {"schema": "strands"}

    id: Mapped[UUID] = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    chat_id: Mapped[UUID] = Column(UUID(as_uuid=True), ForeignKey("strands.chats.id"), nullable=False)
    parent_delegation_id: Mapped[Optional[UUID]] = Column(
        UUID(as_uuid=True), ForeignKey("strands.chat_delegations.id"), nullable=True,
    )
    agent_id: Mapped[UUID] = Column(UUID(as_uuid=True), ForeignKey("strands.agents.id"), nullable=False)
    tool_use_id: Mapped[Optional[str]] = Column(String(255), nullable=True)
    status: Mapped[str] = Column(String(50), nullable=False, default="active")
    created_at: Mapped[datetime] = Column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[Optional[datetime]] = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    chat: Mapped["ChatModel"] = relationship("ChatModel", back_populates="delegations")
    agent: Mapped["AgentModel"] = relationship("AgentModel")
    parent_delegation: Mapped[Optional["ChatDelegationModel"]] = relationship(
        "ChatDelegationModel", remote_side="ChatDelegationModel.id",
        back_populates="child_delegations",
    )
    child_delegations: Mapped[List["ChatDelegationModel"]] = relationship(
        "ChatDelegationModel", back_populates="parent_delegation",
    )