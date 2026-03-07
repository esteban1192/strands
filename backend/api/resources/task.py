"""
Task resource — endpoints for the frontend to inspect and interact with
background chat tasks (list, cancel, get detail / sub-tasks).

Tool approval/rejection within a task's chat reuses the existing chat
approval endpoints since each task has a real chat.
"""
import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.models import ChatTaskResponse
from api.services import TaskService

router = APIRouter(tags=["tasks"])


# ------------------------------------------------------------------
# Tasks scoped to a chat
# ------------------------------------------------------------------

@router.get(
    "/agents/{agent_id}/chats/{chat_id}/tasks",
    response_model=List[ChatTaskResponse],
)
async def list_tasks_for_chat(
    agent_id: uuid.UUID,
    chat_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Return all top-level tasks spawned within a chat."""
    tasks = await TaskService.get_tasks_for_chat(db, chat_id)
    return [TaskService.to_response(t) for t in tasks]


# ------------------------------------------------------------------
# Single-task operations
# ------------------------------------------------------------------

@router.get("/tasks/{task_id}", response_model=ChatTaskResponse)
async def get_task(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get a single task including its sub-tasks."""
    task = await TaskService.get_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return TaskService.to_response(task)


@router.post("/tasks/{task_id}/cancel", response_model=ChatTaskResponse)
async def cancel_task(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Cancel a pending or running task (and its sub-tasks)."""
    task = await TaskService.get_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if task.status in ("completed", "failed", "cancelled"):
        raise HTTPException(
            status_code=400,
            detail=f"Task is already in terminal state: {task.status}",
        )

    await TaskService.cancel_task(db, task_id)
    await db.commit()

    refreshed = await TaskService.get_task(db, task_id)
    return TaskService.to_response(refreshed)


@router.get("/tasks/{task_id}/subtasks", response_model=List[ChatTaskResponse])
async def list_sub_tasks(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Return direct sub-tasks of a task."""
    sub = await TaskService.get_sub_tasks(db, task_id)
    return [TaskService.to_response(t) for t in sub]
