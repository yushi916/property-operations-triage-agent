import sqlite3
from contextlib import closing
from pathlib import Path

from app.db import seed_demo
from app.review_store import initialize_review_store
from app.tasks import initialize_task_store


SCENARIOS = {"base", "active_notice"}


def create_scenario_database(
    db_path,
    fixture_path,
    scenario: str,
) -> Path:
    if scenario not in SCENARIOS:
        raise ValueError(f"未知场景：{scenario}")

    db_path = Path(db_path)
    if db_path.exists():
        raise FileExistsError(
            f"场景数据库必须从空文件开始：{db_path}"
        )

    seed_demo(db_path, Path(fixture_path))
    initialize_review_store(db_path)
    initialize_task_store(db_path)

    if scenario == "active_notice":
        with closing(sqlite3.connect(str(db_path))) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            with conn:
                conn.execute("""
                    INSERT INTO notices
                        (id, building, starts_at, ends_at,
                         text, version)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    "N-02",
                    "3栋",
                    "2026-09-28T09:00:00+08:00",
                    "2026-09-28T10:00:00+08:00",
                    "3栋计划停水通知；仅覆盖3栋，"
                    "实际恢复情况以现场核实为准",
                    1,
                ))

    return db_path
