import sqlite3

from app.tools import SQLiteEvidenceTools


def proximity_baseline(
    conn: sqlite3.Connection,
    seed_report_id: str,
    window_minutes: int = 30,
) -> dict:
    """仅按同楼栋和时间窗口提出关联候选。"""
    tools = SQLiteEvidenceTools(conn)
    seed = tools.get_report(seed_report_id)
    if seed is None:
        raise ValueError("起始报事不存在")

    nearby = tools.find_nearby_reports(
        seed_report_id,
        window_minutes=window_minutes,
    )
    candidate_ids = [
        item["source_id"]
        for item in nearby["evidence"]
    ]

    return {
        "seed_report_id": seed_report_id,
        "possible_same_event": candidate_ids,
        "method": "same_building_and_time_window",
        "window_minutes": window_minutes,
    }
