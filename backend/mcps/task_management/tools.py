"""
Task management tools — Strands @tool functions that let an agent
create and monitor background tasks.

These tools run inside the agent's thread (via ``asyncio.to_thread``),
so they bridge back to the async event loop using
``asyncio.run_coroutine_threadsafe``.
"""
import asyncio
import json
import logging
import uuid
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


def _run_async(coro, loop: asyncio.AbstractEventLoop):
    """Run an async coroutine from a sync thread and return the result."""
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result(timeout=60)


def build_task_tools(
    loop: asyncio.AbstractEventLoop,
    source_chat_id: uuid.UUID,
    agent_id: uuid.UUID,
) -> list:
    """Return a list of Strands @tool functions for task management.

    Args:
        loop: The running asyncio event loop (for sync→async bridging).
        source_chat_id: The chat the agent is currently operating in.
        agent_id: The agent that is creating the tasks.
    """
    from strands import tool as strands_tool

    @strands_tool(name="create_tasks")
    def create_tasks(tasks: list, tool_use_id: str = "") -> str:
        """Create background investigation tasks that run in parallel.

        Each task is executed by a copy of yourself with the same tools and
        sub-agents, focused solely on the given instruction.  Use this when
        you need to investigate multiple things at once.

        Args:
            tasks: A list of objects, each with an "instruction" key
                describing what to investigate.  Example:
                [{"instruction": "Check user_x identity-based policies"},
                 {"instruction": "Check S3 bucket resource policy"}]
            tool_use_id: (auto-populated) The toolUseId of this call.
        """
        from api.database import get_db_session
        from api.services.task_service import TaskService
        from core.task_runner import task_runner

        async def _create():
            created = []
            async with get_db_session() as db:
                for item in tasks:
                    instruction = item if isinstance(item, str) else item.get("instruction", str(item))
                    task_agent_id = agent_id
                    if isinstance(item, dict) and item.get("agent_id"):
                        task_agent_id = uuid.UUID(item["agent_id"])

                    task = await TaskService.create_task(
                        db,
                        source_chat_id=source_chat_id,
                        agent_id=task_agent_id,
                        instruction=instruction,
                        tool_use_id=tool_use_id or None,
                    )
                    task_chat = await TaskService.create_task_chat(db, task)
                    created.append({
                        "task_id": str(task.id),
                        "chat_id": str(task_chat.id),
                        "instruction": instruction,
                        "status": "pending",
                    })
                await db.commit()

                for item in created:
                    await task_runner.schedule(uuid.UUID(item["task_id"]))

            return created

        results = _run_async(_create(), loop)
        return json.dumps(results, indent=2)

    @strands_tool(name="get_task_statuses")
    def get_task_statuses(task_ids: list) -> str:
        """Check the current status of previously created tasks.

        Args:
            task_ids: List of task_id strings to check.
        """
        from api.database import get_db_session
        from api.services.task_service import TaskService

        async def _check():
            async with get_db_session() as db:
                statuses = []
                for tid in task_ids:
                    task = await TaskService.get_task(db, uuid.UUID(tid))
                    if task:
                        statuses.append({
                            "task_id": str(task.id),
                            "instruction": task.instruction[:100],
                            "status": task.status,
                        })
                    else:
                        statuses.append({"task_id": tid, "status": "not_found"})
                return statuses

        results = _run_async(_check(), loop)
        return json.dumps(results, indent=2)

    @strands_tool(name="get_task_results")
    def get_task_results(task_ids: list) -> str:
        """Read the results of completed tasks.

        Args:
            task_ids: List of task_id strings to read results from.
        """
        from api.database import get_db_session
        from api.services.task_service import TaskService

        async def _results():
            async with get_db_session() as db:
                out = []
                for tid in task_ids:
                    task = await TaskService.get_task(db, uuid.UUID(tid))
                    if task:
                        out.append({
                            "task_id": str(task.id),
                            "instruction": task.instruction,
                            "status": task.status,
                            "result_summary": task.result_summary,
                            "error": task.error,
                        })
                    else:
                        out.append({"task_id": tid, "status": "not_found"})
                return out

        results = _run_async(_results(), loop)
        return json.dumps(results, indent=2)

    return [create_tasks, get_task_statuses, get_task_results]
