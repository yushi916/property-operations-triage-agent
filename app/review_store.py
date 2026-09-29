import sqlite3
from contextlib import closing
from pathlib import Path


REVIEW_SCHEMA = """
CREATE TABLE IF NOT EXISTS review_proposals (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL CHECK (
        kind IN ('report_triage', 'plan_review')
    ),
    case_ref TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'pending' CHECK (
        state IN ('pending', 'approved', 'rejected')
    ),
    version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
    proposal_json TEXT NOT NULL,
    evidence_refs_json TEXT NOT NULL,
    trace_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    decided_at TEXT,
    decided_by TEXT,
    decision_reason TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_pending_review_case
    ON review_proposals(kind, case_ref)
    WHERE state = 'pending';

    CREATE TABLE IF NOT EXISTS review_events (
    id TEXT PRIMARY KEY,
    proposal_id TEXT NOT NULL
        REFERENCES review_proposals(id),
    event_type TEXT NOT NULL CHECK (
        event_type IN ('proposed', 'approved', 'rejected')
    ),
    actor TEXT NOT NULL,
    reason TEXT NOT NULL,
    proposal_version INTEGER NOT NULL,
    occurred_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS review_revisions (
    id TEXT PRIMARY KEY,
    proposal_id TEXT NOT NULL
        REFERENCES review_proposals(id),
    from_version INTEGER NOT NULL CHECK (from_version >= 1),
    to_version INTEGER NOT NULL
        CHECK (to_version = from_version + 1),
    actor TEXT NOT NULL,
    reason TEXT NOT NULL,
    before_json TEXT NOT NULL,
    after_json TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    UNIQUE (proposal_id, to_version)
);
"""


def initialize_review_store(db_path) -> None:
    db_path = Path(db_path)
    if not db_path.is_file():
        raise FileNotFoundError(f"数据库不存在：{db_path}")

    with closing(sqlite3.connect(str(db_path))) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(REVIEW_SCHEMA)
