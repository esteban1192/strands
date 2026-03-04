"""
Chat service for CRUD operations on chats and chat messages.

Message storage model
─────────────────────
Each Strands message (``{role, content: [...blocks]}``) is *exploded* into
individual ``chat_messages`` rows — one row per content block.  Each row is
classified via ``message_type``:

  * ``text``        — a plain text block
  * ``tool_call``   — a toolUse block  → also written to ``chat_tool_calls``
  * ``tool_result`` — a toolResult block → also written to ``chat_tool_results``

When the Strands Agent needs the conversation back, ``get_messages_as_dicts``
re-groups consecutive same-role rows into the original Strands format.
"""
import uuid
from itertools import groupby
from typing import Any, Dict, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func as sa_func
from sqlalchemy.orm import selectinload

from ..db_models import ChatModel, ChatMessageModel, ChatToolCallModel, ChatToolResultModel
from ..models import (
    ChatResponse,
    ChatMessageResponse,
    ChatDetailResponse,
    ChatToolCallResponse,
    ChatToolResultResponse,
)


# ------------------------------------------------------------------
# Helpers — classify and extract content blocks
# ------------------------------------------------------------------

def _classify_block(block: Dict[str, Any]) -> str:
    """Return the message_type for a single content block dict."""
    if "toolUse" in block:
        return "tool_call"
    if "toolResult" in block:
        return "tool_result"
    return "text"


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
        """Return all messages for a chat, ordered by ordinal.

        Eagerly loads ``tool_call`` and ``tool_result`` relationships.
        """
        stmt = (
            select(ChatMessageModel)
            .options(
                selectinload(ChatMessageModel.tool_call),
                selectinload(ChatMessageModel.tool_result),
            )
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
        """Re-assemble individual rows into grouped Strands messages.

        Groups consecutive same-role rows and merges their ``content``
        blocks into a single content array per Strands message.

        Returns a list of ``{role, content: [...]}`` dicts ready for the
        Strands ``Agent(messages=...)`` constructor.
        """
        stmt = (
            select(ChatMessageModel)
            .where(ChatMessageModel.chat_id == chat_id)
            .order_by(ChatMessageModel.ordinal)
        )
        result = await db.execute(stmt)
        rows = result.scalars().all()

        if not rows:
            return []

        # Group consecutive rows by role
        grouped: List[Dict[str, Any]] = []
        for role, group in groupby(rows, key=lambda r: r.role):
            content_blocks = [r.content for r in group]
            grouped.append({"role": role, "content": content_blocks})

        return grouped

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
        """Explode Strands messages into individual chat_messages rows.

        Each Strands message ``{role, content: [...blocks]}`` is split so
        that every content block becomes its own row with the appropriate
        ``message_type``.  For ``tool_call`` and ``tool_result`` types,
        structured child records are also created.

        Returns the newly-inserted messages as response models.
        """
        next_ordinal = await ChatService.get_next_ordinal(db, chat_id)
        new_rows: List[ChatMessageModel] = []
        ordinal = next_ordinal

        for msg in messages:
            role = msg["role"]
            content_blocks = msg.get("content", [])

            for block in content_blocks:
                msg_type = _classify_block(block)

                row = ChatMessageModel(
                    chat_id=chat_id,
                    role=role,
                    message_type=msg_type,
                    content=block,
                    ordinal=ordinal,
                )
                db.add(row)
                # Flush to get the generated id for child records
                await db.flush()

                # Create structured child record
                if msg_type == "tool_call":
                    tool_use = block.get("toolUse", {})
                    child = ChatToolCallModel(
                        message_id=row.id,
                        tool_use_id=tool_use.get("toolUseId", ""),
                        tool_name=tool_use.get("name", ""),
                        input=tool_use.get("input"),
                    )
                    db.add(child)
                elif msg_type == "tool_result":
                    tool_result = block.get("toolResult", {})
                    child = ChatToolResultModel(
                        message_id=row.id,
                        tool_use_id=tool_result.get("toolUseId", ""),
                        status=tool_result.get("status", "success"),
                        result=tool_result.get("content"),
                    )
                    db.add(child)

                new_rows.append(row)
                ordinal += 1

        await db.commit()

        # Refresh to pick up server-generated fields + relationships
        for row in new_rows:
            await db.refresh(row, attribute_names=["id", "created_at", "tool_call", "tool_result"])

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
        tool_call_resp = None
        if msg.tool_call:
            tc = msg.tool_call
            tool_call_resp = ChatToolCallResponse(
                id=tc.id,
                message_id=tc.message_id,
                tool_use_id=tc.tool_use_id,
                tool_name=tc.tool_name,
                input=tc.input,
                created_at=tc.created_at,
            )

        tool_result_resp = None
        if msg.tool_result:
            tr = msg.tool_result
            tool_result_resp = ChatToolResultResponse(
                id=tr.id,
                message_id=tr.message_id,
                tool_use_id=tr.tool_use_id,
                status=tr.status,
                result=tr.result,
                created_at=tr.created_at,
            )

        return ChatMessageResponse(
            id=msg.id,
            chat_id=msg.chat_id,
            role=msg.role,
            message_type=msg.message_type,
            content=msg.content,
            ordinal=msg.ordinal,
            created_at=msg.created_at,
            tool_call=tool_call_resp,
            tool_result=tool_result_resp,
        )
