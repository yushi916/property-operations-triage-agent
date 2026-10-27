"""Staff intake storage; recording a report never calls the model."""

import hashlib
import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


INTAKE_SCHEMA = """
CREATE TABLE IF NOT EXISTS report_intakes (
    report_id TEXT PRIMARY KEY REFERENCES reports(id),
    request_id TEXT NOT NULL UNIQUE,
    payload_hash TEXT NOT NULL,
    source TEXT NOT NULL CHECK (source IN ('staff_entry', 'phone')),
    occurred_at TEXT,
    received_at TEXT NOT NULL,
    received_by TEXT NOT NULL,
    risk_status TEXT NOT NULL CHECK (
        risk_status IN ('no_immediate_risk_reported', 'urgent', 'unknown')
    )
);
"""


class IntakeConflict(ValueError):
    pass


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def initialize_report_store(db_path: Path) -> None:
    if not db_path.is_file():
        raise FileNotFoundError(db_path)
    with closing(sqlite3.connect(db_path)) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(INTAKE_SCHEMA)


def get_report_intake(conn: sqlite3.Connection, report_id: str) -> dict | None:
    row = conn.execute("""
        SELECT request_id, source, occurred_at, received_at, received_by, risk_status
        FROM report_intakes WHERE report_id = ?
    """, (report_id,)).fetchone()
    if row is None:
        return None  # Legacy synthetic fixtures have no staff-intake receipt.
    result = dict(zip(
        ("request_id", "source", "occurred_at", "received_at", "received_by", "risk_status"),
        row,
    ))
    manual = result["risk_status"] != "no_immediate_risk_reported"
    result["triage_route"] = "manual_attention" if manual else "ready_for_investigation"
    result["next_action"] = (
        "请立即联系值班负责人进行人工处置；本系统未自动联系任何人员。"
        if manual else "报事已记录，可另行提交证据研判；当前未调用模型或创建维修工单。"
    )
    return result


def create_report(db_path: Path, payload: dict) -> tuple[dict, bool]:
    """Return the stored report and whether it was created by this request.

    Caller supplies validated, normalized fields. A transaction serializes
    competing retries and commits the report together with its intake receipt.
    """
    if not db_path.is_file():
        raise FileNotFoundError(db_path)
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    payload_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    with closing(sqlite3.connect(db_path)) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        with conn:
            conn.execute("BEGIN IMMEDIATE")
            previous = conn.execute("""
                SELECT report_id, payload_hash FROM report_intakes WHERE request_id = ?
            """, (payload["request_id"],)).fetchone()
            if previous is not None:
                if previous[1] != payload_hash:
                    raise IntakeConflict("同一 request_id 已用于不同报事内容，请使用新的提交编号")
                report_id, created = previous[0], False
            else:
                known = conn.execute("""
                    SELECT building FROM reports WHERE building = ?
                    UNION SELECT building FROM asset_buildings WHERE building = ?
                """, (payload["building"], payload["building"])).fetchone()
                if known is None:
                    raise ValueError("楼栋不在当前演示台账中，请先核实楼栋名称")
                received = utc_now()
                if payload["occurred_at"] is not None:
                    if datetime.fromisoformat(payload["occurred_at"]) > received:
                        raise ValueError("发生时间不能晚于系统接收时间；不确定时请留空")
                report_id, created = f"R-{uuid4().hex}", True
                received_at = received.isoformat()
                conn.execute("""
                    INSERT INTO reports (id, reported_at, building, text, version)
                    VALUES (?, ?, ?, ?, 1)
                """, (report_id, received_at, payload["building"], payload["text"]))
                conn.execute("""
                    INSERT INTO report_intakes
                        (report_id, request_id, payload_hash, source, occurred_at,
                         received_at, received_by, risk_status)
                    VALUES (?, ?, ?, ?, ?, ?, 'demo_manager', ?)
                """, (
                    report_id, payload["request_id"], payload_hash, payload["source"],
                    payload["occurred_at"], received_at, payload["risk_status"],
                ))
            row = conn.execute("""
                SELECT id, version, reported_at, building, text FROM reports WHERE id = ?
            """, (report_id,)).fetchone()
            report = dict(zip(("id", "version", "reported_at", "building", "text"), row))
            report["intake"] = get_report_intake(conn, report_id)
    return report, created
