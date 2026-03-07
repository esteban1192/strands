"""
Task management tools — Strands @tool functions exposed to agents.

``create_tasks`` is approval-gated: it never actually executes during the
agent's turn.  Instead, the chat resource detects the pending tool call,
auto-processes it (creates + schedules the real tasks), and waits for the
task runner callback before resuming the orchestrating agent.

``get_task_statuses`` and ``get_task_results`` execute normally (used
during the synthesis phase when the orchestrator is resumed).
"""
import asyncio
import json
import logging
import uuid
from typing import List

logger = logging.getLogger(__name__)

# Tool name constant used to detect task-creation calls in the chat resource.
CREATE_TASKS_TOOL_NAME = "create_tasks"


def _run_async(coro, loop: asyncio.AbstractEventLoop):
    """Run an async coroutine from a sync thread and return the result."""
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result(timeout=60)


def build_task_tools(
    loop: asyncio.AbstractEventLoop,
    source_chat_id: uuid.UUID,
    agent_id: uuid.UUID,
) -> List:
    """Return a list of Strands @tool functions for task management.

    Args:
        loop: The running asyncio event loop (for sync→async bridging).
        source_chat_id: The chat the agent is currently operating in.
        agent_id: The agent that is creating the tasks.

    Returns:
        List of tool functions.  The caller should add ``create_tasks``
        to ``tools_requiring_approval`` so the approval hook blocks it.
    """
    from strands import tool as strands_tool

    @strands_tool(name=CREATE_TASKS_TOOL_NAME)
    def create_tasks(tasks: list) -> str:
        """Create background investigation tasks that run in parallel.

        Each task is executed by a copy of yourself with the same tools and
        sub-agents, focused solely on the given instruction.  Use this when
        you need to investigate multiple things at once.

        IMPORTANT: After calling this tool, STOP.  Do not call any other
        tools.  The results will be delivered to you automatically once
        all tasks complete.

        Args:
            tasks: A list of objects, each with an "instruction" key
                describing what to investigate.  Example:
                [{"instruction": "Check user_x identity-based policies"},
                 {"instruction": "Check S3 bucket resource policy"}]
        """
        # Placeholder — never actually executed (approval-gated).
        return "Task creation requires processing — this call has been queued."

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
