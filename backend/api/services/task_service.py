"""
Task service — CRUD operations for background chat tasks.
"""
import uuid
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql import func as sa_func

from ..db_models import ChatTaskModel, ChatModel, ChatMessageModel, ChatToolCallModel
from ..models import ChatTaskResponse


TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled"})


class TaskService:
    """Service for ChatTask operations."""

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    @staticmethod
    async def create_task(
        db: AsyncSession,
        source_chat_id: uuid.UUID,
        agent_id: uuid.UUID,
        instruction: str,
        tool_use_id: Optional[str] = None,
        parent_task_id: Optional[uuid.UUID] = None,
    ) -> ChatTaskModel:
        """Insert a new task in ``pending`` state and return the ORM row."""
        task = ChatTaskModel(
            source_chat_id=source_chat_id,
            agent_id=agent_id,
            instruction=instruction,
            tool_use_id=tool_use_id,
            parent_task_id=parent_task_id,
            status="pending",
        )
        db.add(task)
        await db.flush()
        await db.refresh(task)
        return task

    @staticmethod
    async def create_task_chat(
        db: AsyncSession,
        task: ChatTaskModel,
    ) -> ChatModel:
        """Create the child chat that will hold the task's message thread."""
        chat = ChatModel(
            agent_id=task.agent_id,
            task_id=task.id,
            title=task.instruction[:100],
        )
        db.add(chat)
        await db.flush()
        await db.refresh(chat)
        return chat

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    @staticmethod
    async def get_task(
        db: AsyncSession,
        task_id: uuid.UUID,
    ) -> Optional[ChatTaskModel]:
        stmt = (
            select(ChatTaskModel)
            .options(selectinload(ChatTaskModel.sub_tasks), selectinload(ChatTaskModel.chat))
            .where(ChatTaskModel.id == task_id)
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_tasks_for_chat(
        db: AsyncSession,
        chat_id: uuid.UUID,
    ) -> List[ChatTaskModel]:
        """Return all top-level tasks whose originating chat is *chat_id*."""
        stmt = (
            select(ChatTaskModel)
            .options(selectinload(ChatTaskModel.sub_tasks), selectinload(ChatTaskModel.chat))
            .where(
                ChatTaskModel.source_chat_id == chat_id,
                ChatTaskModel.parent_task_id == None,
            )
            .order_by(ChatTaskModel.created_at)
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def get_sub_tasks(
        db: AsyncSession,
        parent_task_id: uuid.UUID,
    ) -> List[ChatTaskModel]:
        stmt = (
            select(ChatTaskModel)
            .options(selectinload(ChatTaskModel.sub_tasks), selectinload(ChatTaskModel.chat))
            .where(ChatTaskModel.parent_task_id == parent_task_id)
            .order_by(ChatTaskModel.created_at)
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def get_non_terminal_tasks(
        db: AsyncSession,
    ) -> List[ChatTaskModel]:
        """Return all tasks that are not in a terminal state (for crash recovery)."""
        stmt = (
            select(ChatTaskModel)
            .options(selectinload(ChatTaskModel.chat))
            .where(ChatTaskModel.status.notin_(TERMINAL_STATUSES))
            .order_by(ChatTaskModel.created_at)
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    @staticmethod
    async def update_status(
        db: AsyncSession,
        task_id: uuid.UUID,
        status: str,
        *,
        result_summary: Optional[str] = None,
        error: Optional[str] = None,
    ) -> Optional[ChatTaskModel]:
        """Transition a task to a new status.

        Automatically sets ``started_at`` when moving to ``running`` and
        ``completed_at`` when moving to a terminal state.
        """
        stmt = select(ChatTaskModel).where(ChatTaskModel.id == task_id)
        result = await db.execute(stmt)
        task = result.scalar_one_or_none()
        if not task:
            return None

        task.status = status

        if status == "running" and task.started_at is None:
            task.started_at = sa_func.now()

        if status in TERMINAL_STATUSES:
            task.completed_at = sa_func.now()

        if result_summary is not None:
            task.result_summary = result_summary
        if error is not None:
            task.error = error

        await db.flush()
        return task

    @staticmethod
    async def cancel_task(
        db: AsyncSession,
        task_id: uuid.UUID,
    ) -> Optional[ChatTaskModel]:
        """Cancel a task (and its non-terminal sub-tasks recursively)."""
        task = await TaskService.get_task(db, task_id)
        if not task:
            return None
        if task.status in TERMINAL_STATUSES:
            return task

        await TaskService.update_status(db, task_id, "cancelled")

        for sub in task.sub_tasks:
            if sub.status not in TERMINAL_STATUSES:
                await TaskService.cancel_task(db, sub.id)

        return task

    @staticmethod
    async def resolve_message_ids(
        db: AsyncSession,
        chat_id: uuid.UUID,
    ) -> None:
        """Link unresolved tasks to their corresponding tool-call message.

        After an agent turn is persisted, tasks created during that turn
        have ``message_id = NULL`` but carry a ``tool_use_id``.  This
        method finds the matching ``chat_tool_calls`` row and fills in
        the ``message_id``.
        """
        stmt = (
            select(ChatTaskModel)
            .where(
                ChatTaskModel.source_chat_id == chat_id,
                ChatTaskModel.message_id == None,
                ChatTaskModel.tool_use_id != None,
            )
        )
        result = await db.execute(stmt)
        tasks = result.scalars().all()

        for task in tasks:
            tc_stmt = (
                select(ChatToolCallModel)
                .where(ChatToolCallModel.tool_use_id == task.tool_use_id)
            )
            tc_result = await db.execute(tc_stmt)
            tc = tc_result.scalar_one_or_none()
            if tc:
                task.message_id = tc.message_id

        if tasks:
            await db.flush()

    # ------------------------------------------------------------------
    # Queries for orchestration
    # ------------------------------------------------------------------

    @staticmethod
    async def all_tasks_terminal_for_chat(
        db: AsyncSession,
        chat_id: uuid.UUID,
    ) -> bool:
        """Return True when every top-level task in *chat_id* is terminal."""
        stmt = (
            select(sa_func.count())
            .select_from(ChatTaskModel)
            .where(
                ChatTaskModel.source_chat_id == chat_id,
                ChatTaskModel.parent_task_id == None,
                ChatTaskModel.status.notin_(TERMINAL_STATUSES),
            )
        )
        result = await db.execute(stmt)
        return result.scalar() == 0

    @staticmethod
    async def has_non_terminal_tasks(
        db: AsyncSession,
        chat_id: uuid.UUID,
    ) -> bool:
        """Return True if the chat has any task not in a terminal state."""
        stmt = (
            select(sa_func.count())
            .select_from(ChatTaskModel)
            .where(
                ChatTaskModel.source_chat_id == chat_id,
                ChatTaskModel.status.notin_(TERMINAL_STATUSES),
            )
        )
        result = await db.execute(stmt)
        return result.scalar() > 0

    # ------------------------------------------------------------------
    # Conversion helpers
    # ------------------------------------------------------------------

    @staticmethod
    def to_response(task: ChatTaskModel) -> ChatTaskResponse:
        task_chat_id = None
        if task.chat:
            task_chat_id = task.chat.id

        sub_task_responses = []
        if task.sub_tasks:
            sub_task_responses = [TaskService.to_response(st) for st in task.sub_tasks]

        return ChatTaskResponse(
            id=task.id,
            source_chat_id=task.source_chat_id,
            message_id=task.message_id,
            tool_use_id=task.tool_use_id,
            parent_task_id=task.parent_task_id,
            agent_id=task.agent_id,
            instruction=task.instruction,
            status=task.status,
            result_summary=task.result_summary,
            error=task.error,
            chat_id=task_chat_id,
            created_at=task.created_at,
            started_at=task.started_at,
            completed_at=task.completed_at,
            sub_tasks=sub_task_responses,
        )
