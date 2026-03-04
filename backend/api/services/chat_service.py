"""
Chat service for CRUD operations on chats and chat messages
"""
import uuid
from typing import Any, Dict, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func as sa_func

from ..db_models import ChatModel, ChatMessageModel
from ..models import (
    ChatResponse,
    ChatMessageResponse,
    ChatDetailResponse,
)


class ChatService:
    """Service for Chat and ChatMessage operations"""

    # ------------------------------------------------------------------
    # Chat CRUD
    # ------------------------------------------------------------------

    @staticmethod
    async def create_chat(
        db: AsyncSession,
        agent_id: uuid.UUID,
        title: Optional[str] = None,
    ) -> ChatResponse:
        """Create a new chat for an agent."""
        chat = ChatModel(agent_id=agent_id, title=title)
        db.add(chat)
        await db.commit()
        await db.refresh(chat)
        return ChatService._to_chat_response(chat)

    @staticmethod
    async def get_chat(db: AsyncSession, chat_id: uuid.UUID) -> Optional[ChatResponse]:
        """Get chat metadata by ID."""
        stmt = select(ChatModel).where(ChatModel.id == chat_id)
        result = await db.execute(stmt)
        chat = result.scalar_one_or_none()
        if not chat:
            return None
        return ChatService._to_chat_response(chat)

    @staticmethod
    async def get_chat_detail(db: AsyncSession, chat_id: uuid.UUID) -> Optional[ChatDetailResponse]:
        """Get chat metadata together with all its messages (ordered by ordinal)."""
        stmt = select(ChatModel).where(ChatModel.id == chat_id)
        result = await db.execute(stmt)
        chat = result.scalar_one_or_none()
        if not chat:
            return None

        messages = await ChatService.get_messages(db, chat_id)
        return ChatDetailResponse(
            id=chat.id,
            agent_id=chat.agent_id,
            title=chat.title,
            messages=messages,
            created_at=chat.created_at,
            updated_at=chat.updated_at,
        )

    @staticmethod
    async def list_chats_by_agent(
        db: AsyncSession,
        agent_id: uuid.UUID,
    ) -> List[ChatResponse]:
        """List all chats for a given agent, most recent first."""
        stmt = (
            select(ChatModel)
            .where(ChatModel.agent_id == agent_id)
            .order_by(ChatModel.updated_at.desc())
        )
        result = await db.execute(stmt)
        chats = result.scalars().all()
        return [ChatService._to_chat_response(c) for c in chats]

    @staticmethod
    async def delete_chat(db: AsyncSession, chat_id: uuid.UUID) -> bool:
        """Delete a chat and all its messages (cascade). Returns True if found."""
        stmt = delete(ChatModel).where(ChatModel.id == chat_id)
        result = await db.execute(stmt)
        await db.commit()
        return result.rowcount > 0

    @staticmethod
    async def touch_updated_at(db: AsyncSession, chat_id: uuid.UUID) -> None:
        """Bump updated_at to now (e.g. after adding messages)."""
        stmt = select(ChatModel).where(ChatModel.id == chat_id)
        result = await db.execute(stmt)
        chat = result.scalar_one_or_none()
        if chat:
            chat.updated_at = sa_func.now()
            await db.commit()

    # ------------------------------------------------------------------
    # Message operations
    # ------------------------------------------------------------------

    @staticmethod
    async def get_messages(
        db: AsyncSession,
        chat_id: uuid.UUID,
    ) -> List[ChatMessageResponse]:
        """Return all messages for a chat, ordered by ordinal."""
        stmt = (
            select(ChatMessageModel)
            .where(ChatMessageModel.chat_id == chat_id)
            .order_by(ChatMessageModel.ordinal)
        )
        result = await db.execute(stmt)
        rows = result.scalars().all()
        return [ChatService._to_message_response(m) for m in rows]

    @staticmethod
    async def get_messages_as_dicts(
        db: AsyncSession,
        chat_id: uuid.UUID,
    ) -> List[Dict[str, Any]]:
        """Return all messages for a chat as plain dicts (role + content).

        This is the format expected by the Strands Agent ``messages`` parameter.
        """
        stmt = (
            select(ChatMessageModel)
            .where(ChatMessageModel.chat_id == chat_id)
            .order_by(ChatMessageModel.ordinal)
        )
        result = await db.execute(stmt)
        rows = result.scalars().all()
        return [{"role": m.role, "content": m.content} for m in rows]

    @staticmethod
    async def get_next_ordinal(db: AsyncSession, chat_id: uuid.UUID) -> int:
        """Return the next ordinal value for a new message in this chat."""
        stmt = (
            select(sa_func.coalesce(sa_func.max(ChatMessageModel.ordinal), -1))
            .where(ChatMessageModel.chat_id == chat_id)
        )
        result = await db.execute(stmt)
        current_max = result.scalar()
        return current_max + 1

    @staticmethod
    async def add_messages(
        db: AsyncSession,
        chat_id: uuid.UUID,
        messages: List[Dict[str, Any]],
    ) -> List[ChatMessageResponse]:
        """Bulk-insert messages into a chat.

        Each dict must have ``role`` (str) and ``content`` (list of content blocks).
        Messages are assigned sequential ordinals starting from the current max + 1.

        Returns the newly-inserted messages as response models.
        """
        next_ordinal = await ChatService.get_next_ordinal(db, chat_id)
        new_rows: List[ChatMessageModel] = []

        for i, msg in enumerate(messages):
            row = ChatMessageModel(
                chat_id=chat_id,
                role=msg["role"],
                content=msg["content"],
                ordinal=next_ordinal + i,
            )
            db.add(row)
            new_rows.append(row)

        await db.commit()

        # Refresh to pick up server-generated fields (id, created_at)
        for row in new_rows:
            await db.refresh(row)

        return [ChatService._to_message_response(r) for r in new_rows]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_chat_response(chat: ChatModel) -> ChatResponse:
        return ChatResponse(
            id=chat.id,
            agent_id=chat.agent_id,
            title=chat.title,
            created_at=chat.created_at,
            updated_at=chat.updated_at,
        )

    @staticmethod
    def _to_message_response(msg: ChatMessageModel) -> ChatMessageResponse:
        return ChatMessageResponse(
            id=msg.id,
            chat_id=msg.chat_id,
            role=msg.role,
            content=msg.content,
            ordinal=msg.ordinal,
            created_at=msg.created_at,
        )
