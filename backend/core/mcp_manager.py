"""
MCP Manager — orchestrates MCP server interactions.

Responsibilities:
  - Connect to a remote MCP server (via its transport_type + url)
  - Discover available tools (list_tools)
  - Persist / sync discovered tools and their parameters into the DB

This module intentionally does NOT contain CRUD logic; it delegates
all database writes to the service layer (ToolService, MCPService, etc.).
"""
import json
import logging
import os
import uuid
from typing import List, Dict, Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from api.services import MCPService, ToolService, ToolParametersService
from api.models import ToolResponse
from .exceptions import MCPConnectionError, MCPSyncError, UnsupportedTransportError

logger = logging.getLogger(__name__)


class MCPManager:
    """Orchestrates MCP server interactions — tool discovery and sync."""

    # ------------------------------------------------------------------
    # Transport builders
    # ------------------------------------------------------------------
    # Each supported transport_type has a corresponding static method
    # that returns a (tool_list, cleanup) pair.  Adding stdio support
    # later is just a matter of adding a builder + a new branch in
    # _get_transport_callable().
    # ------------------------------------------------------------------

    @staticmethod
    def _get_transport_callable(transport_type: str, url: str | None,
                                 command: str | None = None,
                                 args: str | None = None,
                                 env: str | None = None):
        """Return the appropriate transport callable for the given type.

        Returns:
            A callable suitable for ``MCPClient(transport_callable)``.

        Raises:
            UnsupportedTransportError: if the transport is not yet implemented.
            MCPConnectionError: if required config (e.g. url) is missing.
        """
        if transport_type == "streamable_http":
            if not url:
                raise MCPConnectionError(
                    "URL is required for streamable_http transport"
                )
            return MCPManager._build_streamable_http_transport(url)

        if transport_type == "stdio":
            if not command:
                raise MCPConnectionError(
                    "Command is required for stdio transport"
                )
            parsed_args = json.loads(args) if args else []
            # env is stored as JSON — either a list of key names (new)
            # or a dict of key-value pairs (legacy).
            parsed_env = None
            if env:
                raw_env = json.loads(env)
                if isinstance(raw_env, list):
                    parsed_env = MCPManager._resolve_env_keys(raw_env)
                elif isinstance(raw_env, dict):
                    # Legacy format — keys already have values
                    parsed_env = raw_env
            return MCPManager._build_stdio_transport(command, parsed_args, parsed_env)

        raise UnsupportedTransportError(
            f"Transport type '{transport_type}' is not supported yet"
        )

    @staticmethod
    def _build_streamable_http_transport(url: str):
        """Build a transport callable for Streamable HTTP / SSE based MCP servers."""
        from mcp.client.streamable_http import streamable_http_client

        def transport():
            return streamable_http_client(url)

        return transport

    @staticmethod
    def _build_stdio_transport(command: str, args: List[str], env: Optional[Dict[str, str]] = None):
        """Build a transport callable for stdio-based MCP servers."""
        from mcp.client.stdio import stdio_client, StdioServerParameters

        server_params = StdioServerParameters(
            command=command,
            args=args,
            env=env,
        )

        def transport():
            return stdio_client(server_params)

        return transport

    @staticmethod
    def _resolve_env_keys(keys: List[str]) -> Dict[str, str]:
        """Resolve a list of env var names to their values from os.environ.

        Args:
            keys: List of environment variable names, e.g. ["AWS_ACCESS_KEY_ID", "AWS_DEFAULT_REGION"]

        Returns:
            Dict mapping each key to its value from the container environment.

        Raises:
            MCPConnectionError: if a required env var is not set.
        """
        resolved = {}
        missing = []
        for key in keys:
            value = os.environ.get(key)
            if value is None:
                missing.append(key)
            else:
                resolved[key] = value
        if missing:
            raise MCPConnectionError(
                f"Required environment variables not set in container: {', '.join(missing)}"
            )
        return resolved

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @staticmethod
    async def execute_tool(
        db: AsyncSession,
        agent_id: uuid.UUID,
        tool_name: str,
        tool_input: Dict[str, Any],
    ) -> Any:
        """Execute a single tool call via its MCP server.

        Looks up the tool by name, finds the MCP it belongs to, connects,
        calls the tool, and returns the raw result text.

        Args:
            db: Async database session.
            agent_id: UUID of the agent (used to resolve tool→MCP mapping).
            tool_name: Name of the tool to call.
            tool_input: Input arguments for the tool call.

        Returns:
            The tool result as a string.

        Raises:
            MCPConnectionError: if something goes wrong connecting to the MCP.
        """
        from strands.tools.mcp import MCPClient
        from api.db_models import ToolModel as ToolDBModel

        # Find the tool and its MCP
        stmt = (
            select(ToolDBModel)
            .where(ToolDBModel.name == tool_name)
        )
        result = await db.execute(stmt)
        tool = result.scalar_one_or_none()

        if not tool or not tool.mcp_id:
            raise MCPConnectionError(f"Tool '{tool_name}' not found or has no MCP server")

        mcp = await MCPService.get_model_by_id(db, tool.mcp_id)
        if mcp is None:
            raise MCPConnectionError(f"MCP server for tool '{tool_name}' not found")

        transport_callable = MCPManager._get_transport_callable(
            mcp.transport_type, mcp.url,
            command=mcp.command,
            args=mcp.args,
            env=mcp.env,
        )

        try:
            client = MCPClient(transport_callable)
            client.start()
        except Exception as exc:
            raise MCPConnectionError(
                f"Could not connect to MCP server '{mcp.name}': {exc}"
            ) from exc

        try:
            # Use the MCP client to call the tool directly
            result = client.call_tool_sync(tool_name, tool_input)
            # Extract text from the result
            if hasattr(result, "content"):
                texts = []
                for block in result.content:
                    if hasattr(block, "text"):
                        texts.append(block.text)
                return "\n".join(texts) if texts else str(result)
            return str(result)
        except Exception as exc:
            logger.error("Tool execution failed for '%s': %s", tool_name, exc)
            raise MCPConnectionError(
                f"Tool execution failed for '{tool_name}': {exc}"
            ) from exc
        finally:
            try:
                client.stop(None, None, None)
            except Exception:
                logger.debug("Error closing MCP client (ignored)", exc_info=True)

    @staticmethod
    async def sync_tools(db: AsyncSession, mcp_id: uuid.UUID) -> List[ToolResponse]:
        """Connect to an MCP server, discover its tools, and persist them.

        High-level flow:
          1. Load the MCP record from the DB.
          2. Open a connection via the correct transport.
          3. Call ``list_tools`` to discover available tools.
          4. Upsert each tool (and its parameters) into the DB, linked to this MCP.
          5. Remove any previously-synced tools that are no longer reported by the server.
          6. Update MCP.synced_at.
          7. Return the list of synced tools.

        Args:
            db: Async database session.
            mcp_id: UUID of the MCP to sync.

        Returns:
            List of ToolResponse for the synced tools.

        Raises:
            MCPConnectionError: could not reach the MCP server.
            MCPSyncError: something went wrong during sync.
        """
        from strands.tools.mcp import MCPClient

        # 1. Load MCP
        mcp = await MCPService.get_model_by_id(db, mcp_id)
        if mcp is None:
            raise MCPSyncError(f"MCP with id {mcp_id} not found")

        # 2. Build transport
        transport_callable = MCPManager._get_transport_callable(
            mcp.transport_type, mcp.url,
            command=mcp.command,
            args=mcp.args,
            env=mcp.env,
        )

        # 3. Connect and discover tools
        try:
            client = MCPClient(transport_callable)
            client.start()
        except Exception as exc:
            logger.error("Failed to connect to MCP server %s: %s", mcp.name, exc)
            raise MCPConnectionError(
                f"Could not connect to MCP server '{mcp.name}': {exc}"
            ) from exc

        try:
            raw_tools = client.list_tools_sync()
            logger.info(
                "Discovered %d tools from MCP '%s'", len(raw_tools), mcp.name
            )

            # 4. Upsert tools + parameters
            synced_tool_names: List[str] = []
            synced_tools: List[ToolResponse] = []

            for agent_tool in raw_tools:
                tool_def = agent_tool.tool_spec
                tool_name = tool_def.get("name", "unknown")
                tool_description = tool_def.get("description", "")
                input_schema: Dict[str, Any] = tool_def.get("inputSchema", {})

                synced_tool_names.append(tool_name)

                # Upsert the tool
                tool_response = await MCPManager._upsert_tool(
                    db, mcp_id, tool_name, tool_description
                )
                synced_tools.append(tool_response)

                # Upsert the tool's parameters from its input schema
                await MCPManager._sync_tool_parameters(
                    db, tool_response.id, input_schema
                )

            # 5. Remove tools that the MCP server no longer exposes
            await MCPManager._remove_stale_tools(db, mcp_id, synced_tool_names)

            # 6. Update synced_at
            await MCPService.update_synced_at(db, mcp_id)

            return synced_tools

        except (MCPConnectionError, MCPSyncError):
            raise
        except Exception as exc:
            await db.rollback()
            mcp_name = getattr(mcp, 'name', str(mcp_id))
            logger.exception("Tool sync failed for MCP '%s'", mcp_name)
            raise MCPSyncError(
                f"Failed to sync tools from MCP '{mcp_name}': {exc}"
            ) from exc
        finally:
            # Always clean up the connection
            try:
                client.stop(None, None, None)
            except Exception:
                logger.debug("Error closing MCP client (ignored)", exc_info=True)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    async def _upsert_tool(
        db: AsyncSession,
        mcp_id: uuid.UUID,
        name: str,
        description: str,
    ) -> ToolResponse:
        """Create or update a tool linked to the MCP."""
        from sqlalchemy import select
        from api.db_models import ToolModel

        # Look up by name only — the DB has a unique constraint on name
        stmt = select(ToolModel).where(ToolModel.name == name)
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            existing.description = description
            existing.is_active = True
            existing.mcp_id = mcp_id
            await db.commit()
            await db.refresh(existing)
            return ToolResponse(
                id=existing.id,
                name=existing.name,
                description=existing.description,
                is_active=existing.is_active,
                requires_approval=existing.requires_approval,
                mcp_id=existing.mcp_id,
                mcp_assigned=True,
                parameters_count=0,
                created_at=existing.created_at,
                updated_at=existing.updated_at,
            )

        new_tool = ToolModel(
            name=name,
            description=description,
            is_active=True,
            mcp_id=mcp_id,
        )
        db.add(new_tool)
        await db.commit()
        await db.refresh(new_tool)
        return ToolResponse(
            id=new_tool.id,
            name=new_tool.name,
            description=new_tool.description,
            is_active=new_tool.is_active,
            requires_approval=new_tool.requires_approval,
            mcp_id=new_tool.mcp_id,
            mcp_assigned=True,
            parameters_count=0,
            created_at=new_tool.created_at,
            updated_at=new_tool.updated_at,
        )

    @staticmethod
    async def _sync_tool_parameters(
        db: AsyncSession,
        tool_id: uuid.UUID,
        input_schema: Dict[str, Any],
    ) -> None:
        """Sync tool parameters from the input schema returned by the MCP server.

        Replaces all existing parameters for the tool with the new set.
        """
        from sqlalchemy import delete as sql_delete
        from api.db_models import ToolParameterModel

        # Clear existing parameters for a clean sync
        await db.execute(
            sql_delete(ToolParameterModel).where(
                ToolParameterModel.tool_id == tool_id
            )
        )

        properties: Dict[str, Any] = input_schema.get("properties", {})
        required_params: List[str] = input_schema.get("required", [])

        for param_name, param_def in properties.items():
            param = ToolParameterModel(
                tool_id=tool_id,
                name=param_name,
                parameter_type=param_def.get("type", "string"),
                description=param_def.get("description"),
                is_required=param_name in required_params,
                default_value=str(param_def["default"]) if "default" in param_def else None,
            )
            db.add(param)

        await db.commit()

    @staticmethod
    async def _remove_stale_tools(
        db: AsyncSession,
        mcp_id: uuid.UUID,
        current_tool_names: List[str],
    ) -> None:
        """Delete tools attached to this MCP that are no longer reported by the server."""
        from sqlalchemy import delete as sql_delete
        from api.db_models import ToolModel

        if current_tool_names:
            stmt = sql_delete(ToolModel).where(
                ToolModel.mcp_id == mcp_id,
                ToolModel.name.notin_(current_tool_names),
            )
        else:
            # Server returned zero tools — remove all
            stmt = sql_delete(ToolModel).where(ToolModel.mcp_id == mcp_id)

        await db.execute(stmt)
        await db.commit()
