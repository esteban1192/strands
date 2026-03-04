"""
Core module — business logic and orchestration layer.

This package contains domain logic that goes beyond simple CRUD,
such as connecting to external MCP servers, syncing tools,
and running Strands agents.

Services (api/services/) handle pure DB operations.
Core modules orchestrate services + external SDKs.
"""

from .mcp_manager import MCPManager
from .agent_executor import AgentExecutor, AgentExecutionError, AgentInvocationResult
from .exceptions import (
    CoreException,
    MCPConnectionError,
    MCPSyncError,
    UnsupportedTransportError,
)

__all__ = [
    "MCPManager",
    "AgentExecutor",
    "AgentExecutionError",
    "AgentInvocationResult",
    "CoreException",
    "MCPConnectionError",
    "MCPSyncError",
    "UnsupportedTransportError",
]
