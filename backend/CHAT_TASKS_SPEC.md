# Chat Tasks — Feature Spec

## Summary

Agents can spawn **parallel background tasks** during a chat conversation. Each
task is an isolated, focused investigation that runs asynchronously — using the
same tools and sub-agents the parent agent has access to. Tasks are persisted in
the database, survive backend restarts, and support tool-approval gates.

---

## User-Facing Behavior

### The Flow

1. User sends a message in a chat (e.g., *"Why can't user_x access the S3 bucket?"*).
2. The orchestrating agent analyzes the request, decides to parallelize, and
   calls the `create_tasks` tool with a list of focused instructions.
3. The chat input becomes **disabled** — no new user messages until all tasks
   resolve.
4. A **task table** appears inline in the chat (rendered from the assistant
   message that spawned the tasks). Each row shows a task with its current
   status.
5. Tasks execute in the background, in parallel.
6. The user can **click a task row** to open a **Task Detail UI** showing:
   - The task's full message thread (same rendering as a normal chat).
   - Approve / Reject buttons when the task is in `waiting_approval`.
   - A Cancel button for `pending` or `running` tasks.
   - The user can also **send messages** into the task's chat to intervene or
     guide the running agent.
   - If the task spawned sub-tasks, they appear as a nested task table.
7. When all top-level tasks reach a terminal state, the orchestrating agent is
   **automatically resumed** via callback. It reads task results and posts a
   synthesis message.
8. The chat input is **re-enabled**.

### Chat Blocking Rules

- When a chat has tasks in non-terminal states (`pending`, `running`,
  `waiting_approval`), the chat input is **disabled**.
- The user can still view the chat, browse the task table, click into tasks,
  approve tool calls, cancel tasks, and send messages into task chats.
- Blocking is **derived state**: the frontend checks whether non-terminal tasks
  exist for the current chat. No extra column on the `chats` table.

---

## Task Lifecycle

### Statuses

| Status              | Terminal? | Meaning                                            |
|---------------------|-----------|----------------------------------------------------|
| `pending`           | No        | Created, waiting to be picked up                   |
| `running`           | No        | Agent is actively working on it                    |
| `waiting_approval`  | No        | Blocked on a tool call that requires user approval  |
| `completed`         | Yes       | Done — result summary is available                 |
| `failed`            | Yes       | Unrecoverable error                                |
| `cancelled`         | Yes       | Cancelled by the user or the orchestrating agent    |

### State Machine

```
pending ──────► running ──────► completed
   │               │
   │               ├──────────► failed
   │               │
   │               ├──────────► cancelled
   │               │
   │               └──► waiting_approval ──► running  (on approve/reject)
   │
   └──────────► cancelled  (before it ever starts)
```

### Sub-Tasks

- Tasks can spawn sub-tasks. A sub-task has `parent_task_id` pointing to its
  parent.
- Sub-tasks follow the exact same lifecycle.
- A parent task is not `completed` until all its sub-tasks are in terminal
  states.
- In the UI, sub-tasks appear as a nested task table inside the parent task's
  detail view.

---

## Data Model

### New table: `chat_tasks`

| Column           | Type                        | Constraints / Default     | Description                                        |
|------------------|-----------------------------|---------------------------|----------------------------------------------------|
| `id`             | UUID                        | PK, default uuid4         |                                                    |
| `source_chat_id` | UUID                        | FK → `chats.id`, NOT NULL | The originating chat (always known at creation)     |
| `message_id`     | UUID, nullable              | FK → `chat_messages.id`   | Resolved post-hoc — the tool-call message           |
| `tool_use_id`    | String(255), nullable       |                           | The toolUseId from the create_tasks call            |
| `parent_task_id` | UUID, nullable              | FK → `chat_tasks.id`      | NULL for top-level; points to parent for sub-tasks  |
| `agent_id`       | UUID                        | FK → `agents.id`          | Which agent runs this task                          |
| `instruction`    | Text                        | NOT NULL                  | What the agent should do                            |
| `status`         | String(50)                  | NOT NULL, default pending | Current lifecycle status                            |
| `result_summary` | Text, nullable              |                           | Text summary produced on completion                 |
| `error`          | Text, nullable              |                           | Error details if `failed`                           |
| `created_at`     | Timestamp w/ tz             | server default now()      |                                                    |
| `started_at`     | Timestamp w/ tz, nullable   |                           | When execution began                                |
| `completed_at`   | Timestamp w/ tz, nullable   |                           | When it reached a terminal state                    |

**Note on `message_id` resolution:** Tasks are created during agent tool
execution, before messages are persisted.  `source_chat_id` is set immediately;
`message_id` is filled in after the agent turn completes by matching
`tool_use_id` to the persisted `chat_tool_calls` row.

### Modified table: `chats`

Add one nullable column:

| Column    | Type           | Constraints / Default    | Description                                     |
|-----------|----------------|--------------------------|-------------------------------------------------|
| `task_id` | UUID, nullable | FK → `chat_tasks.id`     | When set, this chat is a task's conversation thread |

### Relationship Chain

```
Chat (top-level, task_id = NULL)
  └─ ChatMessage (assistant: "Let me investigate from several angles...")
       │
       ├─ ChatTask 1 (instruction: "Check user_x identity policies")
       │    └─ Chat (task_id = ChatTask 1)
       │         └─ ChatMessages (the task agent's full thread)
       │         └─ ChatMessage (sub-task spawning)
       │              ├─ ChatTask 1a
       │              │    └─ Chat (task_id = ChatTask 1a)
       │              └─ ChatTask 1b
       │                   └─ Chat (task_id = ChatTask 1b)
       │
       ├─ ChatTask 2 (instruction: "Check permission boundaries")
       │    └─ Chat (task_id = ChatTask 2)
       │
       └─ ChatTask 3 (instruction: "Check CloudTrail logs")
            └─ Chat (task_id = ChatTask 3)
```

---

## Architecture

### Component Overview

| Concern                     | Location                                  | Role                                                    |
|-----------------------------|-------------------------------------------|---------------------------------------------------------|
| Task DB model               | `api/db_models.py`                        | `ChatTaskModel` SQLAlchemy model                        |
| Task Pydantic models        | `api/models/task_models.py`               | Request/response schemas                                |
| Task service (CRUD)         | `api/services/task_service.py`            | DB operations for tasks                                 |
| Task REST endpoints         | `api/resources/task.py`                   | Frontend API: list, approve, cancel                     |
| Task Management MCP server  | `mcps/task_management/server.py`          | Agent-facing tools: create, poll, read results          |
| Task runner                 | `core/task_runner.py`                     | asyncio background executor for tasks                   |
| Liquibase migration         | `liquibase/`                              | DDL for `chat_tasks` + `chats.task_id`                  |

### Task Management MCP (in-process)

The MCP server runs **inside the same backend process** and shares the
SQLAlchemy async session factory. It is registered as an MCP that agents can
use, exposing these tools:

| Tool                | Input                                         | Output                            | Description                                                 |
|---------------------|-----------------------------------------------|-----------------------------------|-------------------------------------------------------------|
| `create_tasks`      | `[{instruction, agent_id?}]`                  | `[{task_id, instruction}]`        | Create tasks in `pending` state, schedule for execution     |
| `get_task_statuses` | `[task_id, ...]`                              | `[{task_id, status}]`             | Check current status of given tasks                          |
| `get_task_results`  | `[task_id, ...]`                              | `[{task_id, status, result_summary, error}]` | Read results of completed/failed tasks           |

When the agent calls `create_tasks`:
1. Task records are inserted into DB with status `pending`.
2. A `Chat` is created for each task (with `task_id` set).
3. Each task is submitted to the **task runner** (asyncio).
4. The tool returns the task IDs immediately — the agent's turn ends here.

### Task Runner (`core/task_runner.py`)

An asyncio-based background executor that lives in the backend process.

**Responsibilities:**
- Execute tasks by invoking `AgentExecutor.invoke` for each task, in its own
  task chat context.
- Update task status in the DB as it progresses.
- On task completion: call the **completion callback**.
- On backend startup: scan DB for `running` → reset to `pending`;
  scan for `pending` → schedule them.

**Execution per task:**
1. Set status to `running`, record `started_at`.
2. Call `AgentExecutor.invoke(db, agent_id, instruction, chat_id=task_chat_id)`.
3. Store resulting messages into the task's chat.
4. If the agent hit an approval gate (cancelled tool calls detected):
   - Set status to `waiting_approval`.
5. Else if successful:
   - Set status to `completed`, store `result_summary`, record `completed_at`.
6. On exception:
   - Set status to `failed`, store error, record `completed_at`.
7. Call the completion callback.

**Completion callback:**
1. Determine the originating top-level chat (walk up: task → message → chat).
2. Query: are ALL tasks attached to that chat's messages in a terminal state?
3. If yes → resume the orchestrating agent:
   - Re-invoke `AgentExecutor.invoke` on the top-level chat with no new prompt
     (the agent continues from its existing messages, which include the
     `create_tasks` tool result).
   - The agent calls `get_task_results`, reads summaries, and produces a
     synthesis message.
4. If no → do nothing (wait for more callbacks).

### Crash Resilience

On backend startup (in `main.py` lifespan):

1. **`running` tasks** → reset to `pending` (they were interrupted mid-flight).
2. **`pending` tasks** → schedule them in the task runner.
3. **`waiting_approval` tasks** → leave as-is (user must act).

After recovering pending tasks, also check: for any top-level chat that has ALL
tasks in terminal states but was never resumed (crash during synthesis), trigger
the orchestrating agent resumption.

---

## REST API (Frontend-Facing)

These endpoints let the frontend display and interact with tasks.

### Endpoints

| Method   | Path                                            | Description                                  |
|----------|-------------------------------------------------|----------------------------------------------|
| `GET`    | `/agents/{agent_id}/chats/{chat_id}/tasks`      | List all top-level tasks for a chat           |
| `GET`    | `/tasks/{task_id}`                               | Get task detail (status, result, sub-tasks)   |
| `GET`    | `/tasks/{task_id}/chat`                          | Get the task's chat (messages thread)          |
| `POST`   | `/tasks/{task_id}/cancel`                        | Cancel a pending or running task              |
| `GET`    | `/tasks/{task_id}/subtasks`                      | List sub-tasks of a task                      |

Tool approval/rejection within a task's chat uses the **existing** chat
approval endpoints (since each task has a real chat).

---

## Frontend Behavior (Summary)

### Task Table (inline in chat)

- Rendered as part of the assistant message that created the tasks.
- Columns: task instruction (truncated), status badge.
- Each row is clickable → opens Task Detail UI.
- Live-updates via polling or SSE.

### Task Detail UI

- Displays the task's full chat thread (reuses the existing chat message
  renderer).
- Shows Approve / Reject buttons for `waiting_approval` tasks.
- Shows a Cancel button for `pending` / `running` tasks.
- Allows the user to send messages into the task's chat.
- If the task spawned sub-tasks, shows a nested task table.

### Chat Blocking

- The frontend checks: does this chat have any tasks in non-terminal state?
- If yes: disable the message input, show a status indicator.
- Derived from task data — no extra field on chat.
