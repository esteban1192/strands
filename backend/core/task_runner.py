"""
Task runner — asyncio background executor for chat tasks.

Responsibilities:
  - Execute tasks by invoking ``AgentExecutor.invoke`` in each task's own chat.
  - Update task status in the DB as it progresses.
  - On task completion, fire a callback that checks whether *all* sibling
    tasks for the originating chat are terminal; if so, resume the
    orchestrating agent so it can synthesise results.
  - On backend startup, recover interrupted tasks from the DB.
"""
import asyncio
import logging
import uuid
from typing import Dict

from api.database import get_db_session
from api.services.task_service import TaskService, TERMINAL_STATUSES
from api.services.chat_service import ChatService
from core.agent_executor import AgentExecutor
from core.event_bus import event_bus

logger = logging.getLogger(__name__)


class TaskRunner:
    """Singleton asyncio task executor for background chat tasks."""

    def __init__(self) -> None:
        self._running: Dict[uuid.UUID, asyncio.Task] = {}
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def schedule(self, task_id: uuid.UUID) -> None:
        """Schedule a task for background execution.

        Safe to call multiple times for the same task_id — duplicates are
        ignored.
        """
        async with self._lock:
            if task_id in self._running:
                return
            handle = asyncio.create_task(self._execute(task_id))
            self._running[task_id] = handle
            handle.add_done_callback(lambda _: self._cleanup(task_id))

    async def cancel(self, task_id: uuid.UUID) -> None:
        """Cancel a running asyncio task if one exists."""
        async with self._lock:
            handle = self._running.pop(task_id, None)
        if handle and not handle.done():
            handle.cancel()

    async def recover(self) -> None:
        """Recover tasks after a backend restart.

        - ``running`` tasks are reset to ``pending`` (they were interrupted).
        - ``pending`` tasks are scheduled.
        - ``waiting_approval`` tasks are left for the user.
        """
        async with get_db_session() as db:
            tasks = await TaskService.get_non_terminal_tasks(db)

            for task in tasks:
                if task.status == "running":
                    await TaskService.update_status(db, task.id, "pending")
            await db.commit()

        # Schedule pending tasks (use fresh sessions per task)
        async with get_db_session() as db:
            tasks = await TaskService.get_non_terminal_tasks(db)
            pending_count = 0
            seen_chats = set()

            for task in tasks:
                if task.status == "pending":
                    await self.schedule(task.id)
                    pending_count += 1
                    seen_chats.add(task.source_chat_id)

            # Check if any chats have all tasks terminal but were never
            # resumed (crash during synthesis).
            for chat_id in seen_chats:
                all_done = await TaskService.all_tasks_terminal_for_chat(db, chat_id)
                if all_done:
                    logger.info(
                        "All tasks terminal for chat %s — triggering synthesis",
                        chat_id,
                    )
                    asyncio.create_task(self._resume_orchestrator(chat_id))

        logger.info(
            "Task recovery complete — %d tasks recovered, %d scheduled",
            len(tasks), pending_count,
        )

    # ------------------------------------------------------------------
    # Internal: single task execution
    # ------------------------------------------------------------------

    async def _execute(self, task_id: uuid.UUID) -> None:
        """Run a single task to completion."""
        logger.info("Starting task execution: %s", task_id)

        async with get_db_session() as db:
            task = await TaskService.get_task(db, task_id)
            if not task:
                logger.error("Task %s not found — skipping", task_id)
                return

            if task.status in TERMINAL_STATUSES:
                logger.info("Task %s already terminal (%s) — skipping", task_id, task.status)
                return

            task_chat = task.chat
            if not task_chat:
                logger.error("Task %s has no associated chat — marking failed", task_id)
                await TaskService.update_status(db, task_id, "failed", error="No task chat found")
                await db.commit()
                await self._on_task_finished(task_id, task.source_chat_id)
                return

            task_chat_id = task_chat.id
            agent_id = task.agent_id
            instruction = task.instruction
            source_chat_id = task.source_chat_id

            await TaskService.update_status(db, task_id, "running")
            await db.commit()

        # Publish running status to the originating chat
        await self._publish_task_update(source_chat_id)

        try:
            async with get_db_session() as db:
                existing = await ChatService.get_messages_as_dicts(db, task_chat_id)
                if not existing:
                    ancestor_ctx = await ChatService.get_ancestor_context(
                        db, task_chat_id,
                    )
                    if ancestor_ctx:
                        enriched = (
                            f"{ancestor_ctx}\n\n"
                            f"<task_instruction>\n{instruction}\n</task_instruction>"
                        )
                    else:
                        enriched = instruction

                    user_msg = [{"role": "user", "content": [{"text": enriched}]}]
                    await ChatService.add_messages(
                        db, task_chat_id, user_msg, agent_id=agent_id,
                    )
                    await db.commit()

                root_deleg = await ChatService.get_active_delegation(db, task_chat_id, agent_id)
                if not root_deleg:
                    await ChatService.create_delegation(db, task_chat_id, agent_id)

                history = await ChatService.get_messages_as_dicts(
                    db, task_chat_id, agent_id=agent_id,
                )

                result = await AgentExecutor.invoke(
                    db, agent_id, None,
                    history=history, chat_id=task_chat_id,
                )

                if result.messages:
                    await ChatService.add_messages(
                        db, task_chat_id, result.messages,
                        tools_requiring_approval=result.tools_requiring_approval,
                        agent_id=agent_id,
                    )

                pending_approvals = await ChatService.get_pending_tool_calls(
                    db, task_chat_id, agent_id=agent_id,
                )

                remaining_pending = pending_approvals
                if pending_approvals:
                    from api.resources.chat import (
                        _split_task_calls, _auto_process_create_tasks,
                    )
                    task_calls, remaining_pending = _split_task_calls(pending_approvals)
                    if task_calls:
                        await _auto_process_create_tasks(
                            db, task_chat_id, agent_id, task_calls, self,
                        )

                if remaining_pending or pending_approvals:
                    await TaskService.update_status(db, task_id, "waiting_approval")
                else:
                    summary = result.response[:2000] if result.response else ""
                    await TaskService.update_status(
                        db, task_id, "completed", result_summary=summary,
                    )

                await db.commit()

        except asyncio.CancelledError:
            logger.info("Task %s was cancelled", task_id)
            async with get_db_session() as db:
                await TaskService.update_status(db, task_id, "cancelled")
                await db.commit()

        except Exception as exc:
            logger.exception("Task %s failed", task_id)
            async with get_db_session() as db:
                await TaskService.update_status(
                    db, task_id, "failed", error=str(exc)[:2000],
                )
                await db.commit()

        await self._on_task_finished(task_id, source_chat_id)

    # ------------------------------------------------------------------
    # Internal: post-completion callback
    # ------------------------------------------------------------------

    async def _on_task_finished(
        self,
        task_id: uuid.UUID,
        source_chat_id: uuid.UUID,
    ) -> None:
        """Called after a task reaches a terminal or waiting state.

        Publishes a task-update SSE event, and if all sibling tasks are
        terminal, triggers synthesis resumption.
        """
        await self._publish_task_update(source_chat_id)

        async with get_db_session() as db:
            task = await TaskService.get_task(db, task_id)
            if task and task.status in TERMINAL_STATUSES:
                all_done = await TaskService.all_tasks_terminal_for_chat(
                    db, source_chat_id,
                )
                if all_done:
                    logger.info(
                        "All tasks for chat %s are terminal — resuming orchestrator",
                        source_chat_id,
                    )
                    asyncio.create_task(self._resume_orchestrator(source_chat_id))

    # ------------------------------------------------------------------
    # Internal: resume the orchestrating agent
    # ------------------------------------------------------------------

    async def _resume_orchestrator(self, chat_id: uuid.UUID) -> None:
        """Re-invoke the agent chain so it can read task results
        and synthesise a final answer.

        Finds the deepest active delegation and uses ``_try_resume_chain``
        to walk back up, re-invoking each agent in turn.
        """
        await event_bus.publish(chat_id, {"type": "thinking"})

        async with get_db_session() as db:
            try:
                from api.db_models import ChatModel
                from api.resources.chat import _try_resume_chain, _serialize_messages
                from sqlalchemy import select

                stmt = select(ChatModel).where(ChatModel.id == chat_id)
                result = await db.execute(stmt)
                chat = result.scalar_one_or_none()
                if not chat:
                    logger.error("Cannot resume — chat %s not found", chat_id)
                    return

                root_agent_id = chat.agent_id

                deepest = await ChatService.get_deepest_active_delegation(db, chat_id)
                start_agent_id = deepest.agent_id if deepest else root_agent_id

                final_response = await _try_resume_chain(
                    db, chat_id, start_agent_id, root_agent_id,
                )

                await ChatService.touch_updated_at(db, chat_id)

                all_messages = await ChatService.get_messages(db, chat_id)
                await event_bus.publish(chat_id, {
                    "type": "complete",
                    "response": final_response,
                    "messages": _serialize_messages(all_messages),
                })

            except Exception as exc:
                logger.exception("Orchestrator resumption failed for chat %s", chat_id)
                await event_bus.publish(chat_id, {
                    "type": "error",
                    "message": str(exc),
                })

    # ------------------------------------------------------------------
    # Internal: SSE updates
    # ------------------------------------------------------------------

    async def _publish_task_update(self, source_chat_id: uuid.UUID) -> None:
        """Push a task_update event so the frontend can refresh the task table."""
        async with get_db_session() as db:
            tasks = await TaskService.get_tasks_for_chat(db, source_chat_id)
            await event_bus.publish(source_chat_id, {
                "type": "task_update",
                "tasks": [
                    TaskService.to_response(t).model_dump(mode="json")
                    for t in tasks
                ],
            })

    # ------------------------------------------------------------------
    # Internal: cleanup
    # ------------------------------------------------------------------

    def _cleanup(self, task_id: uuid.UUID) -> None:
        """Remove a finished asyncio task handle (sync callback)."""
        self._running.pop(task_id, None)


# Module-level singleton
task_runner = TaskRunner()
