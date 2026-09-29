import json
import sqlite3
from pathlib import Path

from app.schema import open_database


COLUMNS = {
    "reports": ("id", "reported_at", "building", "text", "version"),
    "assets": ("id", "name", "version"),
    "plans": ("id", "area", "due_at", "work", "version"),
    "work_orders": (
        "id", "report_id", "plan_id", "asset_id", "status",
        "opened_at", "completed_at", "description", "version",
    ),
    "inspections": (
        "id", "plan_id", "inspected_at", "result", "text", "version",
    ),
    "notices": (
        "id", "building", "starts_at", "ends_at", "text", "version",
    ),
}


def _upsert(
    conn: sqlite3.Connection, table: str, values: dict
) -> None:
    columns = COLUMNS[table]  # 表名和列名只取自代码中的白名单
    if set(values) != set(columns):
        raise ValueError(f"{table} 的字段不符合数据库定义")

    names = ", ".join(columns)
    placeholders = ", ".join("?" for _ in columns)
    updates = ", ".join(
        f"{name} = excluded.{name}"
        for name in columns if name != "id"
    )
    conn.execute(
        f"INSERT INTO {table} ({names}) VALUES ({placeholders}) "
        f"ON CONFLICT(id) DO UPDATE SET {updates}",
        tuple(values[name] for name in columns),
    )


def seed_demo(db_path: Path, fixture_path: Path) -> None:
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    conn = open_database(db_path)

    try:
        with conn:
            for item in fixture["reports"]:
                _upsert(conn, "reports", {
                    "id": item["id"],
                    "reported_at": item["at"],
                    "building": item["building"],
                    "text": item["text"],
                    "version": item["version"],
                })

            for item in fixture["assets"]:
                _upsert(conn, "assets", {
                    "id": item["id"],
                    "name": item["name"],
                    "version": item["version"],
                })
                conn.execute(
                    "DELETE FROM asset_buildings WHERE asset_id = ?",
                    (item["id"],),
                )
                conn.executemany(
                    "INSERT INTO asset_buildings "
                    "(asset_id, building) VALUES (?, ?)",
                    [(item["id"], building)
                     for building in item["serves"]],
                )

            for item in fixture["plans"]:
                _upsert(conn, "plans", {
                    "id": item["id"],
                    "area": item["area"],
                    "due_at": item["due_at"],
                    "work": item["work"],
                    "version": item["version"],
                })

            for item in fixture["work_orders"]:
                _upsert(conn, "work_orders", {
                    "id": item["id"],
                    "report_id": item.get("report_id"),
                    "plan_id": item.get("plan_id"),
                    "asset_id": item.get("asset_id"),
                    "status": item["status"],
                    "opened_at": item.get("opened_at"),
                    "completed_at": (
                        item.get("at")
                        if item["status"] == "completed" else None
                    ),
                    "description": (
                        item.get("issue") or item.get("symptom")
                    ),
                    "version": item["version"],
                })

            for item in fixture["inspections"]:
                _upsert(conn, "inspections", {
                    "id": item["id"],
                    "plan_id": item["plan_id"],
                    "inspected_at": item["at"],
                    "result": item["result"],
                    "text": item["text"],
                    "version": item["version"],
                })

            for item in fixture["notices"]:
                _upsert(conn, "notices", {
                    "id": item["id"],
                    "building": item["building"],
                    "starts_at": item["starts_at"],
                    "ends_at": item["ends_at"],
                    "text": item["text"],
                    "version": item["version"],
                })
    finally:
        conn.close()
