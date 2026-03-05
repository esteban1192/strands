"""
MCP Session Cache — keeps MCP client sessions alive across chat turns.

Problem
───────
Each call to ``AgentExecutor.invoke()`` used to create fresh ``MCPClient``
instances, which meant the MCP server session (and any server-side state
such as database connections) was destroyed after every turn.

Solution
────────
This module maintains an **in-memory cache** of started ``MCPClient``
instances, keyed by ``(chat_id, mcp_id)``.  When the ``AgentExecutor``
needs clients for a chat, it pulls them from the cache (or creates new
ones).  The cache registers itself as a **consumer** on each client so
that the ``Agent``'s normal cleanup (``remove_consumer``) does NOT stop
the background thread — the cache's consumer keeps it alive.

Lifecycle
─────────
- **Created** the first time a chat needs an MCP client for a given MCP.
- **Reused** on subsequent turns within the same chat.
- **Evicted** when:
  - The chat is explicitly deleted (``evict_chat``).
  - The session has been idle longer than ``TTL_SECONDS`` (periodic sweep).
  - The server is shutting down (``shutdown``).

Limitations (see tech-debt-notes/)
──────────────────────────────────
- In-memory only — sessions are lost if the container restarts.
- Does not scale horizontally — each container holds its own cache.
"""

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# How long an idle session survives before being evicted (seconds).
TTL_SECONDS = 30 * 60  # 30 minutes

# How often the background sweeper checks for stale sessions.
SWEEP_INTERVAL_SECONDS = 5 * 60  # 5 minutes

# Sentinel consumer ID used by the cache to keep clients alive.
_CACHE_CONSUMER_ID = "__mcp_session_cache__"


@dataclass
class _CachedSession:
    """Internal bookkeeping for a single cached MCP client."""
    client: object  # MCPClient — typed as object to avoid import at module level
    mcp_id: uuid.UUID
    chat_id: uuid.UUID
    allowed_tools: List[str]
    last_used: float = field(default_factory=time.monotonic)


class MCPSessionCache:
    """Process-global cache of live MCP client sessions, keyed by (chat_id, mcp_id)."""

    def __init__(self) -> None:
        self._sessions: Dict[Tuple[uuid.UUID, uuid.UUID], _CachedSession] = {}
        self._lock = threading.Lock()
        self._sweeper: Optional[threading.Thread] = None
        self._shutdown_event = threading.Event()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_or_create_clients(
        self,
        chat_id: uuid.UUID,
        mcp_configs: List[Dict],
    ) -> list:
        """Return a list of started MCPClient instances for the given chat.

        ``mcp_configs`` is a list of dicts, each with:
          - ``mcp_id``: UUID
          - ``transport_callable``: callable that returns an MCP transport
          - ``allowed_tools``: list of tool name strings

        Clients already cached for this ``(chat_id, mcp_id)`` are reused;
        new ones are created and started as needed.

        Returns:
            List of MCPClient instances (ready to use).
        """
        from strands.tools.mcp import MCPClient

        self._ensure_sweeper_running()
        clients: list = []

        for cfg in mcp_configs:
            mcp_id = cfg["mcp_id"]
            key = (chat_id, mcp_id)

            with self._lock:
                cached = self._sessions.get(key)

            if cached is not None:
                # Touch last_used
                cached.last_used = time.monotonic()
                clients.append(cached.client)
                logger.debug(
                    "cache hit for chat=%s mcp=%s", chat_id, mcp_id,
                )
                continue

            # Create, start, and cache a new client
            allowed = cfg["allowed_tools"]
            transport_callable = cfg["transport_callable"]

            client = MCPClient(
                transport_callable,
                tool_filters={"allowed": allowed} if allowed else None,
            )
            client.start()

            # Register ourselves as a consumer so the Agent's cleanup
            # does NOT stop the background thread.
            client.add_consumer(_CACHE_CONSUMER_ID)

            session = _CachedSession(
                client=client,
                mcp_id=mcp_id,
                chat_id=chat_id,
                allowed_tools=allowed,
            )

            with self._lock:
                self._sessions[key] = session

            clients.append(client)
            logger.info(
                "created & cached MCP session for chat=%s mcp=%s",
                chat_id, mcp_id,
            )

        return clients

    def evict_chat(self, chat_id: uuid.UUID) -> None:
        """Remove and stop all cached sessions for a chat."""
        to_remove: List[Tuple[uuid.UUID, uuid.UUID]] = []

        with self._lock:
            for key, session in self._sessions.items():
                if session.chat_id == chat_id:
                    to_remove.append(key)

        for key in to_remove:
            self._evict(key)

        if to_remove:
            logger.info(
                "evicted %d cached session(s) for chat=%s",
                len(to_remove), chat_id,
            )

    def shutdown(self) -> None:
        """Stop all cached sessions and the sweeper thread."""
        self._shutdown_event.set()

        with self._lock:
            keys = list(self._sessions.keys())

        for key in keys:
            self._evict(key)

        logger.info("MCP session cache shut down (%d sessions closed)", len(keys))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _evict(self, key: Tuple[uuid.UUID, uuid.UUID]) -> None:
        """Remove a single session from the cache and stop its client."""
        with self._lock:
            session = self._sessions.pop(key, None)

        if session is None:
            return

        try:
            session.client.remove_consumer(_CACHE_CONSUMER_ID)
        except Exception:
            logger.debug(
                "error stopping cached MCP client for %s (ignored)",
                key, exc_info=True,
            )

    def _sweep(self) -> None:
        """Background thread that evicts idle sessions."""
        while not self._shutdown_event.is_set():
            self._shutdown_event.wait(timeout=SWEEP_INTERVAL_SECONDS)
            if self._shutdown_event.is_set():
                break

            now = time.monotonic()
            stale: List[Tuple[uuid.UUID, uuid.UUID]] = []

            with self._lock:
                for key, session in self._sessions.items():
                    if now - session.last_used > TTL_SECONDS:
                        stale.append(key)

            for key in stale:
                logger.info("evicting stale session %s (idle > %ds)", key, TTL_SECONDS)
                self._evict(key)

    def _ensure_sweeper_running(self) -> None:
        """Start the sweeper thread if it isn't running yet."""
        if self._sweeper is not None and self._sweeper.is_alive():
            return
        self._sweeper = threading.Thread(
            target=self._sweep, daemon=True, name="mcp-session-sweeper",
        )
        self._sweeper.start()


# ------------------------------------------------------------------
# Module-level singleton
# ------------------------------------------------------------------
session_cache = MCPSessionCache()
