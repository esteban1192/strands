"""Clean up stale tasks and inspect DB state."""
import subprocess

DB = "postgresql://strands_user:strands_password@localhost:5433/strands"

def q(sql, label=""):
    if label:
        print(f"\n=== {label} ===")
    result = subprocess.run(
        ["psql", DB, "-t", "-A", "-c", sql],
        capture_output=True, text=True,
    )
    out = result.stdout.strip()
    if out:
        for line in out.split("\n"):
            print(f"  {line}")
    else:
        print("  (none)")
    return out

def run(sql, label=""):
    if label:
        print(f"\n--- {label} ---")
    result = subprocess.run(
        ["psql", DB, "-c", sql],
        capture_output=True, text=True,
    )
    print(f"  {result.stdout.strip()}")


# Show current state
q("SELECT id, status, instruction FROM strands.chat_tasks ORDER BY created_at", "CURRENT TASKS")

q("SELECT id, task_id, title FROM strands.chats WHERE task_id IS NOT NULL", "TASK CHATS")

# Clean up: delete task chats first (FK), then tasks
run("DELETE FROM strands.chats WHERE task_id IS NOT NULL", "Deleting task chats")
run("DELETE FROM strands.chat_tasks", "Deleting all tasks")

# Also clean the problematic chat messages (from ordinal 9 onward — the agent's task loop)
run("""
    DELETE FROM strands.chat_messages
    WHERE chat_id = 'ed560544-57f7-43d6-b979-c46f918b6473'
    AND ordinal >= 9
""", "Deleting stale messages from test chat (ordinal >= 9)")

# Verify clean state
q("SELECT count(*) FROM strands.chat_tasks", "Tasks remaining")
q("SELECT count(*) FROM strands.chats WHERE task_id IS NOT NULL", "Task chats remaining")
q("""
    SELECT ordinal, role, message_type, substring(content::text, 1, 100)
    FROM strands.chat_messages
    WHERE chat_id = 'ed560544-57f7-43d6-b979-c46f918b6473'
    ORDER BY ordinal
""", "Messages in test chat after cleanup")
