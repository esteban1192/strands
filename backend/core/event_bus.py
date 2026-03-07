"""
In-memory pub/sub event bus keyed by chat_id.

Used to push agent invocation results from background tasks to SSE
subscribers.  Each chat can have multiple subscribers (e.g. multiple
browser tabs).  The bus buffers the last event per chat so that late
subscribers (race between POST response and SSE connect) don't miss it.
"""
import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Set

logger = logging.getLogger(__name__)


@dataclass
class _ChatChannel:
    subscribers: Set[asyncio.Queue] = field(default_factory=set)
    last_event: Optional[Dict[str, Any]] = None


class EventBus:
    def __init__(self) -> None:
        self._channels: Dict[uuid.UUID, _ChatChannel] = {}
        self._lock = asyncio.Lock()

    def _get_channel(self, chat_id: uuid.UUID) -> _ChatChannel:
        if chat_id not in self._channels:
            self._channels[chat_id] = _ChatChannel()
        return self._channels[chat_id]

    async def subscribe(self, chat_id: uuid.UUID) -> asyncio.Queue:
        """Create a queue for this chat and return it.

        If a buffered event exists, it's placed in the queue immediately
        so the subscriber doesn't miss results that arrived before
        the SSE connection was established.
        """
        async with self._lock:
            channel = self._get_channel(chat_id)
            queue: asyncio.Queue = asyncio.Queue()
            channel.subscribers.add(queue)
            if channel.last_event is not None:
                queue.put_nowait(channel.last_event)
            return queue

    async def unsubscribe(self, chat_id: uuid.UUID, queue: asyncio.Queue) -> None:
        async with self._lock:
            channel = self._channels.get(chat_id)
            if channel:
                channel.subscribers.discard(queue)
                if not channel.subscribers:
                    del self._channels[chat_id]

    async def publish(self, chat_id: uuid.UUID, event: Dict[str, Any]) -> None:
        """Send *event* to all subscribers of *chat_id* and buffer it."""
        async with self._lock:
            channel = self._get_channel(chat_id)
            channel.last_event = event
            for q in channel.subscribers:
                try:
                    q.put_nowait(event)
                except asyncio.QueueFull:
                    logger.warning("Subscriber queue full for chat %s, dropping event", chat_id)

    async def clear_buffer(self, chat_id: uuid.UUID) -> None:
        """Remove the buffered event for a chat (e.g. after it's consumed)."""
        async with self._lock:
            channel = self._channels.get(chat_id)
            if channel:
                channel.last_event = None


event_bus = EventBus()
