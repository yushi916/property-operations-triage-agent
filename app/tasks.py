import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


TASK_SCHEMA = """
CREATE TABLE IF NOT EXISTS internal_tasks (
    id TEXT PRIMARY KEY,
    proposal_id TEXT NOT NULL UNIQUE
        REFERENCES review_proposals(id),
    kind TEXT NOT NULL CHECK (
        kind IN ('investigate_report', 'verify_plan')
    ),
    case_ref TEXT NOT NULL,
    title TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'open' CHECK (
        state IN ('open', 'in_progress', 'done')
    ),
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);
"""


def initialize_task_store(db_path) -> None:
    db_path = Path(db_path)
    if not db_path.is_file():
        raise FileNotFoundError(db_path)

    with closing(sqlite3.connect(str(db_path))) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(TASK_SCHEMA)


def ensure_task_for_approved(conn, proposal_id: str) -> dict:
    """在调用方的写入事务内创建待办；重复调用返回同一条。"""
    row = conn.execute("""
        SELECT kind, case_ref, state
        FROM review_proposals WHERE id = ?
    """, (proposal_id,)).fetchone()
    if row is None or row[2] != "approved":
        raise ValueError("只有已批准建议才能生成内部待办")

    proposal_kind, case_ref, _ = row
    mapping = {
        "report_triage": (
            "investigate_report",
            "核实报事关联及实际影响范围",
        ),
        "plan_review": (
            "verify_plan",
            "现场复核计划、工单与巡查冲突",
        ),
    }
    task_kind, title = mapping[proposal_kind]

    existing = conn.execute("""
        SELECT id, kind, case_ref, state
        FROM internal_tasks WHERE proposal_id = ?
    """, (proposal_id,)).fetchone()
    if existing:
        return {
            "id": existing[0],
            "kind": existing[1],
            "case_ref": existing[2],
            "state": existing[3],
        }

    task_id = uuid4().hex
    now = datetime.now(timezone.utc).isoformat()
    conn.execute("""
        INSERT INTO internal_tasks
            (id, proposal_id, kind, case_ref,
             title, state, version, created_at)
        VALUES (?, ?, ?, ?, ?, 'open', 1, ?)
    """, (
        task_id, proposal_id, task_kind,
        case_ref, title, now,
    ))
    return {
        "id": task_id,
        "kind": task_kind,
        "case_ref": case_ref,
        "state": "open",
    }
