"""
Agent Executor — builds and runs a Strands agent with its MCP tools.

Responsibilities:
  - Load an agent and its linked MCPs from the DB
  - Build MCPClient instances for each MCP (stdio or streamable_http)
  - Create a Strands Agent, run a prompt, and return the response
  - Manage MCP client lifecycle (start/stop)
"""
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.db_models import AgentModel, AgentToolModel, ToolModel, MCPModel
from .mcp_manager import MCPManager
from .exceptions import MCPConnectionError, CoreException

logger = logging.getLogger(__name__)


class AgentExecutionError(CoreException):
    """Raised when agent execution fails."""
    pass


@dataclass
class AgentInvocationResult:
    """Holds the agent text response and the full message trace."""
    response: str
    messages: List[dict[str, Any]] = field(default_factory=list)


class AgentExecutor:
    """Builds and runs a Strands agent with its configured MCP tools."""

    @staticmethod
    async def invoke(db: AsyncSession, agent_id: uuid.UUID, prompt: str) -> AgentInvocationResult:
        """Run a prompt against an agent, using its linked MCP tools.

        Flow:
          1. Load the agent from the DB.
          2. Find all distinct MCPs linked to the agent's tools.
          3. Build an MCPClient for each MCP.
          4. Start all clients, create a Strands Agent, run the prompt.
          5. Stop all clients and return the response.

        Args:
            db: Async database session.
            agent_id: UUID of the agent to invoke.
            prompt: User prompt to send to the agent.

        Returns:
            AgentInvocationResult containing the text response and full message trace.

        Raises:
            AgentExecutionError: if something goes wrong.
        """
        from strands import Agent
        from strands.tools.mcp import MCPClient

        # 1. Load agent
        stmt = (
            select(AgentModel)
            .options(selectinload(AgentModel.agent_tools))
            .where(AgentModel.id == agent_id)
        )
        result = await db.execute(stmt)
        agent_model = result.scalar_one_or_none()

        if agent_model is None:
            raise AgentExecutionError(f"Agent with id {agent_id} not found")

        if agent_model.status != "active":
            raise AgentExecutionError(
                f"Agent '{agent_model.name}' is not active (status: {agent_model.status})"
            )

        # 2. Find distinct MCPs linked through the agent's tools
        tool_ids = [at.tool_id for at in agent_model.agent_tools if at.is_enabled]
        if not tool_ids:
            raise AgentExecutionError(
                f"Agent '{agent_model.name}' has no enabled tools assigned"
            )

        stmt = (
            select(MCPModel)
            .join(ToolModel, ToolModel.mcp_id == MCPModel.id)
            .where(ToolModel.id.in_(tool_ids))
            .distinct()
        )
        result = await db.execute(stmt)
        mcps = result.scalars().all()

        if not mcps:
            raise AgentExecutionError(
                f"No MCP servers found for agent '{agent_model.name}' tools"
            )

        # 3. Build MCPClient for each MCP
        clients: List[MCPClient] = []
        for mcp in mcps:
            try:
                transport_callable = MCPManager._get_transport_callable(
                    mcp.transport_type,
                    mcp.url,
                    command=mcp.command,
                    args=mcp.args,
                    env=mcp.env,
                )
                clients.append(MCPClient(transport_callable))
            except (MCPConnectionError, Exception) as exc:
                # Clean up any clients we already built
                logger.error("Failed to build MCP client for '%s': %s", mcp.name, exc)
                raise AgentExecutionError(
                    f"Failed to configure MCP '{mcp.name}': {exc}"
                ) from exc

        # 4. Create Strands Agent and run the prompt
        # The Agent handles MCPClient lifecycle (start/stop) internally.
        try:
            agent_kwargs = dict(
                model=agent_model.model,
                tools=clients,
            )
            if agent_model.system_prompt:
                agent_kwargs["system_prompt"] = agent_model.system_prompt

            agent = Agent(**agent_kwargs)

            logger.info(
                "Invoking agent '%s' (model=%s) with %d MCP(s)",
                agent_model.name, agent_model.model, len(clients),
            )

            response = agent(prompt)

            # Extract full message trace from the agent
            raw_messages = list(agent.messages) if hasattr(agent, 'messages') else []

            return AgentInvocationResult(
                response=str(response),
                messages=raw_messages,
            )

        except AgentExecutionError:
            raise
        except Exception as exc:
            logger.exception("Agent execution failed for '%s'", agent_model.name)
            raise AgentExecutionError(
                f"Agent execution failed: {exc}"
            ) from exc
