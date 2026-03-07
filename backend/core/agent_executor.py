"""
Agent Executor — builds and runs a Strands agent with its MCP tools.

Responsibilities:
  - Load an agent and its linked MCPs from the DB
  - Build MCPClient instances for each MCP (stdio or streamable_http)
  - Load linked sub-agents and expose them as virtual tools
  - Create a Strands Agent, run a prompt, and return the response
  - Manage MCP client lifecycle (start/stop)
  - Gate tool execution behind user approval via ToolApprovalHook
"""
import asyncio
import logging
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.db_models import AgentModel, ToolModel, MCPModel
from api.services.agent_sub_agent_service import AgentSubAgentService
from .mcp_manager import MCPManager
from .mcp_session_cache import session_cache
from .hooks import ToolApprovalHook
from .exceptions import MCPConnectionError, CoreException

logger = logging.getLogger(__name__)

# Prefix applied to every sub-agent virtual tool name so the approval /
# execution path can distinguish them from regular MCP tools.
SUB_AGENT_TOOL_PREFIX = "invoke_agent_"


def _slugify(name: str) -> str:
    """Turn a human-readable agent name into a valid tool-name slug."""
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return slug or "unnamed"


@dataclass
class AgentInvocationResult:
    """Structured result from an agent invocation.

    Attributes:
        response: The final text-only response from the agent.
        messages: The complete conversation including tool_use / tool_result blocks.
        tools_requiring_approval: Set of tool names that require user approval.
        cancelled_tool_use_ids: Set of toolUseId values that were blocked
            because they require approval.  Empty when no tools were gated.
        sub_agent_map: Mapping of virtual sub-agent tool names to child agent
            UUIDs.  Used by the chat resource to determine which child agent
            to invoke when a sub-agent tool call is approved.
    """
    response: str
    messages: List[Dict[str, Any]] = field(default_factory=list)
    tools_requiring_approval: set = field(default_factory=set)
    cancelled_tool_use_ids: Set[str] = field(default_factory=set)
    sub_agent_map: Dict[str, uuid.UUID] = field(default_factory=dict)


class AgentExecutionError(CoreException):
    """Raised when agent execution fails."""
    pass


class AgentExecutor:
    """Builds and runs a Strands agent with its configured MCP tools."""

    @staticmethod
    def sub_agent_tool_name(agent_name: str) -> str:
        """Return the virtual tool name for a sub-agent."""
        return f"{SUB_AGENT_TOOL_PREFIX}{_slugify(agent_name)}"

    @staticmethod
    def is_sub_agent_tool(tool_name: str) -> bool:
        """Return True if ``tool_name`` is a virtual sub-agent tool."""
        return tool_name.startswith(SUB_AGENT_TOOL_PREFIX)

    @staticmethod
    async def invoke(
        db: AsyncSession,
        agent_id: uuid.UUID,
        prompt: Optional[str],
        history: List[Dict[str, Any]] | None = None,
        chat_id: Optional[uuid.UUID] = None,
    ) -> AgentInvocationResult:
        """Run a prompt against an agent, using its linked MCP tools.

        Flow:
          1. Load the agent from the DB.
          2. Find all distinct MCPs linked to the agent's tools.
          3. Obtain MCPClient instances (from session cache when ``chat_id``
             is provided, or ephemeral otherwise).
          4. Create a Strands Agent, run the prompt.
          5. Return the response.  Cached clients stay alive for the next
             turn; ephemeral clients are cleaned up by the Agent.

        Tools that require approval are **not** executed.  Instead, the hook
        cancels their calls and returns a placeholder error result to the
        model.  When any tools are cancelled, the messages returned are
        truncated so that trailing assistant turns (which were generated
        based on incomplete/cancelled results) are removed.

        Args:
            db: Async database session.
            agent_id: UUID of the agent to invoke.
            prompt: User prompt to send to the agent.  Pass ``None`` when
                resuming from an approval (the conversation already ends
                with a tool-result message and the model should continue
                from there).
            history: Optional list of prior conversation messages to pre-load
                into the agent.  Each dict must have ``role`` and ``content``
                keys matching the Strands message format.
            chat_id: Optional chat UUID.  When provided, MCP sessions are
                cached and reused across turns so that server-side state
                (e.g. database connections) is preserved.

        Returns:
            AgentInvocationResult with the text response and the *new* messages
            produced by this invocation (delta — excludes pre-loaded history).

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

        # Load the assigned tool models so we know their names and MCP ids.
        assigned_tools: List[ToolModel] = []
        mcp_allowed_tools: Dict[uuid.UUID, List[str]] = {}
        clients: list = []

        if tool_ids:
            tool_stmt = select(ToolModel).where(ToolModel.id.in_(tool_ids))
            tool_result = await db.execute(tool_stmt)
            assigned_tools = list(tool_result.scalars().all())

            # Build a mapping: mcp_id → set of allowed tool names
            for t in assigned_tools:
                mcp_allowed_tools.setdefault(t.mcp_id, []).append(t.name)

            # Distinct MCPs that own at least one assigned tool
            mcp_ids = list(mcp_allowed_tools.keys())
            stmt = select(MCPModel).where(MCPModel.id.in_(mcp_ids))
            result = await db.execute(stmt)
            mcps = result.scalars().all()

            # 3. Obtain MCPClient instances — cached when chat_id is provided,
            #    ephemeral otherwise.
            if chat_id is not None:
                mcp_configs = []
                for mcp in mcps:
                    try:
                        transport_callable = MCPManager._get_transport_callable(
                            mcp.transport_type,
                            mcp.url,
                            command=mcp.command,
                            args=mcp.args,
                            env=mcp.env,
                        )
                        allowed = mcp_allowed_tools.get(mcp.id, [])
                        mcp_configs.append({
                            "mcp_id": mcp.id,
                            "transport_callable": transport_callable,
                            "allowed_tools": allowed,
                        })
                    except (MCPConnectionError, Exception) as exc:
                        logger.error("Failed to build MCP client for '%s': %s", mcp.name, exc)
                        raise AgentExecutionError(
                            f"Failed to configure MCP '{mcp.name}': {exc}"
                        ) from exc

                try:
                    clients = session_cache.get_or_create_clients(chat_id, mcp_configs)
                except Exception as exc:
                    logger.error("Failed to obtain cached MCP clients: %s", exc)
                    raise AgentExecutionError(
                        f"Failed to start MCP sessions: {exc}"
                    ) from exc
            else:
                # No chat_id — create ephemeral clients (Agent manages lifecycle)
                for mcp in mcps:
                    try:
                        transport_callable = MCPManager._get_transport_callable(
                            mcp.transport_type,
                            mcp.url,
                            command=mcp.command,
                            args=mcp.args,
                            env=mcp.env,
                        )
                        allowed = mcp_allowed_tools.get(mcp.id, [])
                        clients.append(
                            MCPClient(
                                transport_callable,
                                tool_filters={"allowed": allowed} if allowed else None,
                            )
                        )
                    except (MCPConnectionError, Exception) as exc:
                        logger.error("Failed to build MCP client for '%s': %s", mcp.name, exc)
                        raise AgentExecutionError(
                            f"Failed to configure MCP '{mcp.name}': {exc}"
                        ) from exc

        # 2b. Determine which tools require approval
        tools_requiring_approval: set[str] = {
            t.name for t in assigned_tools if t.requires_approval
        }

        # 2c. Load linked sub-agents and build virtual tool functions.
        #     Sub-agent invocations ALWAYS require approval.
        sub_agent_models = await AgentSubAgentService.get_enabled_sub_agents(db, agent_id)
        sub_agent_tool_functions = []
        # Map: virtual tool name → child agent UUID (stored on the result
        # so the chat resource can look up which child to invoke).
        sub_agent_map: Dict[str, uuid.UUID] = {}

        for child in sub_agent_models:
            vt_name = AgentExecutor.sub_agent_tool_name(child.name)
            sub_agent_map[vt_name] = child.id
            tools_requiring_approval.add(vt_name)

            # Build a Strands @tool-decorated function for this sub-agent
            sub_agent_tool_functions.append(
                AgentExecutor._build_sub_agent_tool(vt_name, child)
            )

        # An agent must have at least one tool (MCP or sub-agent)
        if not clients and not sub_agent_tool_functions:
            raise AgentExecutionError(
                f"Agent '{agent_model.name}' has no enabled tools or sub-agents assigned"
            )

        # 4. Create Strands Agent and run the prompt
        # The Agent handles MCPClient lifecycle (start/stop) internally.
        all_tools: list = clients + sub_agent_tool_functions
        prior_messages = history or []
        history_len = len(prior_messages)

        try:
            # Install the approval hook so that tools requiring approval are
            # cancelled before execution (the model still receives a
            # tool_result with status "error").
            approval_hook: Optional[ToolApprovalHook] = None
            hooks = []
            if tools_requiring_approval:
                approval_hook = ToolApprovalHook(tools_requiring_approval)
                hooks.append(approval_hook)

            agent = Agent(
                model=agent_model.model,
                tools=all_tools,
                system_prompt=agent_model.system_prompt or None,
                messages=prior_messages if prior_messages else None,
                hooks=hooks if hooks else None,
            )

            logger.info(
                "Invoking agent '%s' (model=%s) with %d MCP(s), %d sub-agent(s), %d history msgs",
                agent_model.name, agent_model.model, len(clients),
                len(sub_agent_tool_functions), history_len,
            )

            result = await asyncio.to_thread(agent, prompt)

            # Extract the full conversation messages (user + assistant turns
            # including tool_use / tool_result blocks)
            raw_messages = getattr(agent, "messages", [])

            all_messages = [
                {"role": m.get("role", "unknown"), "content": m.get("content", [])}
                for m in raw_messages
            ]

            # Return only the NEW messages (delta) — skip the pre-loaded history
            new_messages = all_messages[history_len:]

            # Determine which toolUseIds were cancelled by the approval hook
            cancelled_ids: Set[str] = set()
            if approval_hook:
                cancelled_ids = approval_hook.cancelled_tool_use_ids

            # When tools were cancelled, the model's follow-up response is
            # based on incomplete data (it saw "tool cancelled" errors).
            # Truncate trailing assistant messages so the stored conversation
            # ends at the tool-result turn.  When the user later approves,
            # the agent is re-invoked and produces a fresh response.
            if cancelled_ids:
                new_messages = AgentExecutor._truncate_after_cancelled_results(
                    new_messages, cancelled_ids,
                )

            return AgentInvocationResult(
                response=str(result),
                messages=new_messages,
                tools_requiring_approval=tools_requiring_approval,
                cancelled_tool_use_ids=cancelled_ids,
                sub_agent_map=sub_agent_map,
            )

        except AgentExecutionError:
            raise
        except Exception as exc:
            logger.exception("Agent execution failed for '%s'", agent_model.name)
            raise AgentExecutionError(
                f"Agent execution failed: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _truncate_after_cancelled_results(
        messages: List[Dict[str, Any]],
        cancelled_ids: Set[str],
    ) -> List[Dict[str, Any]]:
        """Remove trailing assistant messages that follow cancelled tool results.

        When a tool call is cancelled for approval, the model still generates
        a text response (e.g. "I couldn't run the tool").  That response is
        stale — we don't want to persist it.  This helper finds the *first*
        ``user`` message containing a cancelled ``toolResult`` and strips
        everything that comes after it.

        We truncate at the first (not last) cancelled result because the
        model may retry the same tool after seeing the cancellation error,
        producing duplicate pending calls that block the resume chain.
        Only the first cancelled attempt is kept; when the user approves it
        the agent is re-invoked and can decide what to do next.
        """
        # Find the index of the first user message containing a cancelled
        # tool result.
        first_cancelled_idx = -1
        for idx, msg in enumerate(messages):
            if msg.get("role") != "user":
                continue
            for block in msg.get("content", []):
                tr = block.get("toolResult") if isinstance(block, dict) else None
                if tr and tr.get("toolUseId") in cancelled_ids:
                    first_cancelled_idx = idx
                    break  # found one in this message — that's enough
            if first_cancelled_idx != -1:
                break  # stop at the first match

        if first_cancelled_idx == -1:
            return messages  # nothing to truncate

        # Keep everything up to and including the message with the cancelled
        # result, dropping any subsequent messages (stale retries).
        return messages[: first_cancelled_idx + 1]

    @staticmethod
    def _build_sub_agent_tool(tool_name: str, child_agent: AgentModel):
        """Build a Strands ``@tool``-decorated function for a sub-agent.

        The returned function is a placeholder — it will never actually
        execute because sub-agent tools always require approval and are
        therefore cancelled by the ``ToolApprovalHook`` before execution.
        When the user later approves, the chat resource handles the real
        invocation of the child agent via ``AgentExecutor.invoke``.

        The function's docstring becomes the tool description visible to the
        parent model, containing the child agent's name and description.
        """
        from strands import tool as strands_tool

        description = child_agent.description or "A sub-agent"
        doc = (
            f"Delegate a task to the '{child_agent.name}' agent. "
            f"{description}. "
            f"Pass a 'prompt' string describing what you need this agent to do."
        )

        @strands_tool(name=tool_name)
        def sub_agent_tool(prompt: str) -> str:
            # This body should never run — the approval hook cancels it.
            return "Sub-agent invocation requires approval."

        sub_agent_tool.__doc__ = doc
        return sub_agent_tool
