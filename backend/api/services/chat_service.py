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

from ..db_models import (
    ChatModel, ChatMessageModel, ChatToolCallModel, ChatToolResultModel,
    ChatDelegationModel,
)
from ..models import (
    ChatResponse,
    ChatMessageResponse,
    ChatDetailResponse,
    ChatDelegationResponse,
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
        from sqlalchemy.orm import selectinload
        stmt = (
            select(ChatModel)
            .options(selectinload(ChatModel.task))
            .where(ChatModel.id == chat_id)
        )
        result = await db.execute(stmt)
        chat = result.scalar_one_or_none()
        if not chat:
            return None

        messages = await ChatService.get_messages(db, chat_id)
        return ChatDetailResponse(
            id=chat.id,
            agent_id=chat.agent_id,
            title=chat.title,
            task_id=chat.task_id,
            source_chat_id=chat.task.source_chat_id if chat.task else None,
            messages=messages,
            created_at=chat.created_at,
            updated_at=chat.updated_at,
        )

    @staticmethod
    async def list_chats_by_agent(
        db: AsyncSession,
        agent_id: uuid.UUID,
    ) -> List[ChatResponse]:
        """List top-level chats for an agent (excludes task chats)."""
        stmt = (
            select(ChatModel)
            .where(ChatModel.agent_id == agent_id)
            .where(ChatModel.task_id.is_(None))
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
        agent_id: Optional[uuid.UUID] = None,
    ) -> List[Dict[str, Any]]:
        """Re-assemble individual rows into grouped Strands messages.

        Groups consecutive same-role rows and merges their ``content``
        blocks into a single content array per Strands message.

        Args:
            chat_id: The chat whose messages to load.
            agent_id: When provided, only messages attributed to this
                agent are included.  This is essential for the delegation
                chain so that each agent sees only its own conversation.

        Returns a list of ``{role, content: [...]}`` dicts ready for the
        Strands ``Agent(messages=...)`` constructor.
        """
        stmt = (
            select(ChatMessageModel)
            .where(ChatMessageModel.chat_id == chat_id)
            .order_by(ChatMessageModel.ordinal)
        )
        if agent_id is not None:
            stmt = stmt.where(ChatMessageModel.agent_id == agent_id)

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
        tools_requiring_approval: Optional[set[str]] = None,
        agent_id: Optional[uuid.UUID] = None,
    ) -> List[ChatMessageResponse]:
        """Explode Strands messages into individual chat_messages rows.

        Each Strands message ``{role, content: [...blocks]}`` is split so
        that every content block becomes its own row with the appropriate
        ``message_type``.  For ``tool_call`` and ``tool_result`` types,
        structured child records are also created.

        Args:
            tools_requiring_approval: Optional set of tool names whose
                tool_call (and corresponding tool_result) rows should be
                stored with ``is_approved=False``.  Everything else is
                stored as ``is_approved=True``.
            agent_id: Optional UUID of the agent that produced these messages.
                Used for agent-to-agent attribution.

        Returns the newly-inserted messages as response models.
        """
        approval_tools = tools_requiring_approval or set()

        # Collect tool_use_ids that need approval so we can also mark
        # their corresponding tool_result rows.
        pending_tool_use_ids: set[str] = set()

        next_ordinal = await ChatService.get_next_ordinal(db, chat_id)
        new_rows: List[ChatMessageModel] = []
        ordinal = next_ordinal

        for msg in messages:
            role = msg["role"]
            content_blocks = msg.get("content", [])

            for block in content_blocks:
                msg_type = _classify_block(block)

                # Determine approval state
                is_approved = True
                if msg_type == "tool_call":
                    tool_name = block.get("toolUse", {}).get("name", "")
                    tool_use_id = block.get("toolUse", {}).get("toolUseId", "")
                    if tool_name in approval_tools:
                        is_approved = False
                        pending_tool_use_ids.add(tool_use_id)
                elif msg_type == "tool_result":
                    tool_use_id = block.get("toolResult", {}).get("toolUseId", "")
                    if tool_use_id in pending_tool_use_ids:
                        is_approved = False

                row = ChatMessageModel(
                    chat_id=chat_id,
                    agent_id=agent_id,
                    role=role,
                    message_type=msg_type,
                    content=block,
                    ordinal=ordinal,
                    is_approved=is_approved,
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

    @staticmethod
    async def approve_tool_call(
        db: AsyncSession,
        message_id: uuid.UUID,
    ) -> Optional[ChatMessageResponse]:
        """Mark a tool_call message as approved.

        Returns the updated message, or None if not found / not a tool_call.
        """
        stmt = (
            select(ChatMessageModel)
            .options(
                selectinload(ChatMessageModel.tool_call),
                selectinload(ChatMessageModel.tool_result),
            )
            .where(ChatMessageModel.id == message_id)
        )
        result = await db.execute(stmt)
        msg = result.scalar_one_or_none()

        if not msg or msg.message_type != "tool_call":
            return None

        msg.is_approved = True
        await db.commit()
        await db.refresh(msg, attribute_names=["is_approved"])
        return ChatService._to_message_response(msg)

    @staticmethod
    async def reject_tool_call(
        db: AsyncSession,
        message_id: uuid.UUID,
    ) -> Optional[ChatMessageResponse]:
        """Mark a tool_call message (and its companion tool_result) as rejected.

        Sets ``is_approved = True`` so the message is no longer pending, and
        updates the companion tool_result content to indicate rejection.

        Returns the updated message, or None if not found / not a tool_call.
        """
        stmt = (
            select(ChatMessageModel)
            .options(
                selectinload(ChatMessageModel.tool_call),
                selectinload(ChatMessageModel.tool_result),
            )
            .where(ChatMessageModel.id == message_id)
        )
        result = await db.execute(stmt)
        msg = result.scalar_one_or_none()

        if not msg or msg.message_type != "tool_call":
            return None

        tool_use_id = msg.tool_call.tool_use_id if msg.tool_call else None

        # Mark the tool_call row as "resolved" (no longer pending).
        # We set is_approved = True so it is not shown as pending again,
        # but the companion tool_result will carry the rejection payload.
        msg.is_approved = True

        # Find and update the companion tool_result row
        if tool_use_id:
            tr_stmt = (
                select(ChatMessageModel)
                .options(selectinload(ChatMessageModel.tool_result))
                .join(ChatToolResultModel, ChatToolResultModel.message_id == ChatMessageModel.id)
                .where(
                    ChatMessageModel.chat_id == msg.chat_id,
                    ChatToolResultModel.tool_use_id == tool_use_id,
                )
            )
            tr_result = await db.execute(tr_stmt)
            tr_msg = tr_result.scalar_one_or_none()
            if tr_msg:
                tr_msg.is_approved = True
                tr_msg.content = {
                    "toolResult": {
                        "toolUseId": tool_use_id,
                        "status": "error",
                        "content": [{"text": "Tool call was rejected by the user."}],
                    }
                }
                if tr_msg.tool_result:
                    tr_msg.tool_result.status = "error"
                    tr_msg.tool_result.result = [{"text": "Tool call was rejected by the user."}]

        await db.commit()
        await db.refresh(msg, attribute_names=["is_approved"])
        return ChatService._to_message_response(msg)

    @staticmethod
    async def get_pending_tool_calls(
        db: AsyncSession,
        chat_id: uuid.UUID,
        agent_id: Optional[uuid.UUID] = None,
    ) -> List[ChatMessageResponse]:
        """Return unapproved tool_call messages for a chat.

        Args:
            agent_id: When provided, only pending calls attributed to this
                agent are returned.
        """
        stmt = (
            select(ChatMessageModel)
            .options(
                selectinload(ChatMessageModel.tool_call),
                selectinload(ChatMessageModel.tool_result),
            )
            .where(
                ChatMessageModel.chat_id == chat_id,
                ChatMessageModel.message_type == "tool_call",
                ChatMessageModel.is_approved == False,
            )
            .order_by(ChatMessageModel.ordinal)
        )
        if agent_id is not None:
            stmt = stmt.where(ChatMessageModel.agent_id == agent_id)

        result = await db.execute(stmt)
        rows = result.scalars().all()
        return [ChatService._to_message_response(r) for r in rows]

    @staticmethod
    async def update_tool_result(
        db: AsyncSession,
        chat_id: uuid.UUID,
        tool_use_id: str,
        real_result: Any,
    ) -> None:
        """Replace placeholder tool_result content with the real execution result.

        Finds the tool_result row matching ``tool_use_id`` and updates both
        the JSONB ``content`` column and the structured ``ChatToolResultModel``.
        Also marks the row as approved.
        """
        tr_stmt = (
            select(ChatMessageModel)
            .options(selectinload(ChatMessageModel.tool_result))
            .join(ChatToolResultModel, ChatToolResultModel.message_id == ChatMessageModel.id)
            .where(
                ChatMessageModel.chat_id == chat_id,
                ChatToolResultModel.tool_use_id == tool_use_id,
            )
        )
        result = await db.execute(tr_stmt)
        tr_msg = result.scalar_one_or_none()

        if not tr_msg:
            return

        # Build the result content in Strands format
        if isinstance(real_result, dict) and "error" in real_result:
            result_content = [{"text": real_result["error"]}]
            status = "error"
        else:
            result_text = real_result if isinstance(real_result, str) else str(real_result)
            result_content = [{"text": result_text}]
            status = "success"

        tr_msg.is_approved = True
        tr_msg.content = {
            "toolResult": {
                "toolUseId": tool_use_id,
                "status": status,
                "content": result_content,
            }
        }
        if tr_msg.tool_result:
            tr_msg.tool_result.status = status
            tr_msg.tool_result.result = result_content

        await db.commit()

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
            agent_id=msg.agent_id,
            role=msg.role,
            message_type=msg.message_type,
            content=msg.content,
            ordinal=msg.ordinal,
            is_approved=msg.is_approved,
            created_at=msg.created_at,
            tool_call=tool_call_resp,
            tool_result=tool_result_resp,
        )

    # ------------------------------------------------------------------
    # Delegation operations
    # ------------------------------------------------------------------

    @staticmethod
    async def create_delegation(
        db: AsyncSession,
        chat_id: uuid.UUID,
        agent_id: uuid.UUID,
        parent_delegation_id: Optional[uuid.UUID] = None,
        tool_use_id: Optional[str] = None,
    ) -> ChatDelegationResponse:
        """Create a new delegation session.

        Args:
            chat_id: The chat this delegation belongs to.
            agent_id: The agent that will run in this delegation.
            parent_delegation_id: The parent delegation (None for root).
            tool_use_id: The tool_use_id from the parent that triggered
                this delegation (None for root).
        """
        deleg = ChatDelegationModel(
            chat_id=chat_id,
            agent_id=agent_id,
            parent_delegation_id=parent_delegation_id,
            tool_use_id=tool_use_id,
            status="active",
        )
        db.add(deleg)
        await db.commit()
        await db.refresh(deleg)
        return ChatService._to_delegation_response(deleg)

    @staticmethod
    async def complete_delegation(
        db: AsyncSession,
        delegation_id: uuid.UUID,
        status: str = "completed",
    ) -> None:
        """Mark a delegation as completed (or failed)."""
        stmt = select(ChatDelegationModel).where(ChatDelegationModel.id == delegation_id)
        result = await db.execute(stmt)
        deleg = result.scalar_one_or_none()
        if deleg:
            deleg.status = status
            deleg.completed_at = sa_func.now()
            await db.commit()

    @staticmethod
    async def get_active_delegation(
        db: AsyncSession,
        chat_id: uuid.UUID,
        agent_id: uuid.UUID,
    ) -> Optional[ChatDelegationResponse]:
        """Find the active delegation for an agent in a chat."""
        stmt = (
            select(ChatDelegationModel)
            .where(
                ChatDelegationModel.chat_id == chat_id,
                ChatDelegationModel.agent_id == agent_id,
                ChatDelegationModel.status == "active",
            )
            .order_by(ChatDelegationModel.created_at.desc())
            .limit(1)
        )
        result = await db.execute(stmt)
        deleg = result.scalar_one_or_none()
        if not deleg:
            return None
        return ChatService._to_delegation_response(deleg)

    @staticmethod
    async def get_delegation_by_id(
        db: AsyncSession,
        delegation_id: uuid.UUID,
    ) -> Optional[ChatDelegationResponse]:
        """Get a single delegation by ID."""
        stmt = select(ChatDelegationModel).where(ChatDelegationModel.id == delegation_id)
        result = await db.execute(stmt)
        deleg = result.scalar_one_or_none()
        if not deleg:
            return None
        return ChatService._to_delegation_response(deleg)

    @staticmethod
    async def get_root_delegation(
        db: AsyncSession,
        chat_id: uuid.UUID,
    ) -> Optional[ChatDelegationResponse]:
        """Get the root delegation (parent_delegation_id is NULL)."""
        stmt = (
            select(ChatDelegationModel)
            .where(
                ChatDelegationModel.chat_id == chat_id,
                ChatDelegationModel.parent_delegation_id == None,
            )
            .limit(1)
        )
        result = await db.execute(stmt)
        deleg = result.scalar_one_or_none()
        if not deleg:
            return None
        return ChatService._to_delegation_response(deleg)

    @staticmethod
    async def check_delegation_cycle(
        db: AsyncSession,
        chat_id: uuid.UUID,
        parent_delegation_id: uuid.UUID,
        child_agent_id: uuid.UUID,
    ) -> bool:
        """Return True if adding child_agent_id would create a cycle.

        Walks up the parent chain from parent_delegation_id and checks
        if child_agent_id already appears.
        """
        current_id: Optional[uuid.UUID] = parent_delegation_id
        while current_id is not None:
            stmt = select(ChatDelegationModel).where(ChatDelegationModel.id == current_id)
            result = await db.execute(stmt)
            deleg = result.scalar_one_or_none()
            if deleg is None:
                break
            if deleg.agent_id == child_agent_id:
                return True
            current_id = deleg.parent_delegation_id
        return False

    @staticmethod
    def _to_delegation_response(deleg: ChatDelegationModel) -> ChatDelegationResponse:
        return ChatDelegationResponse(
            id=deleg.id,
            chat_id=deleg.chat_id,
            parent_delegation_id=deleg.parent_delegation_id,
            agent_id=deleg.agent_id,
            tool_use_id=deleg.tool_use_id,
            status=deleg.status,
            created_at=deleg.created_at,
            completed_at=deleg.completed_at,
        )
