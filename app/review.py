import sqlite3
from datetime import datetime


def review_plan_pair(
    conn: sqlite3.Connection,
    plan_id: str,
    order_id: str,
    inspection_id: str,
) -> dict:
    row = conn.execute("""
        SELECT p.id, p.version,
               w.id, w.version, w.status, w.completed_at,
               i.id, i.version, i.result, i.inspected_at
        FROM plans AS p
        JOIN work_orders AS w ON w.plan_id = p.id
        JOIN inspections AS i ON i.plan_id = p.id
        WHERE p.id = ? AND w.id = ? AND i.id = ?
    """, (plan_id, order_id, inspection_id)).fetchone()

    if row is None:
        raise ValueError("记录不存在，或工单、巡查不属于该计划")

    (pid, pver, wid, wver, status, completed_at,
     iid, iver, result, inspected_at) = row

    if status == "completed" and result == "not_complete":
        if completed_at is None:
            outcome = "needs_manual_review"
            next_action = "完工时间缺失，先核实记录"
        elif datetime.fromisoformat(inspected_at) > datetime.fromisoformat(
            completed_at
        ):
            outcome = "record_conflict"
            next_action = "现场复核，不能直接判为完成"
        else:
            outcome = "needs_new_inspection"
            next_action = "巡查早于或等于完工，需要完工后的复查"
    else:
        outcome = "no_conflict_detected"
        next_action = "继续核对实际完成情况"

    return {
        "plan_id": pid,
        "status": outcome,
        "evidence_refs": [
            {"id": pid, "version": pver},
            {"id": wid, "version": wver},
            {"id": iid, "version": iver},
        ],
        "next_action": next_action,
    }
