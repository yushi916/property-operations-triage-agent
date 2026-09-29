import sqlite3
from pathlib import Path


SCHEMA = """
CREATE TABLE IF NOT EXISTS reports (
    id TEXT PRIMARY KEY,
    reported_at TEXT NOT NULL,
    building TEXT NOT NULL,
    text TEXT NOT NULL,
    version INTEGER NOT NULL CHECK (version > 0)
);

CREATE TABLE IF NOT EXISTS assets (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    version INTEGER NOT NULL CHECK (version > 0)
);

CREATE TABLE IF NOT EXISTS asset_buildings (
    asset_id TEXT NOT NULL REFERENCES assets(id),
    building TEXT NOT NULL,
    PRIMARY KEY (asset_id, building)
);

CREATE TABLE IF NOT EXISTS plans (
    id TEXT PRIMARY KEY,
    area TEXT NOT NULL,
    due_at TEXT NOT NULL,
    work TEXT NOT NULL,
    version INTEGER NOT NULL CHECK (version > 0)
);

CREATE TABLE IF NOT EXISTS work_orders (
    id TEXT PRIMARY KEY,
    report_id TEXT REFERENCES reports(id),
    plan_id TEXT REFERENCES plans(id),
    asset_id TEXT REFERENCES assets(id),
    status TEXT NOT NULL,
    opened_at TEXT,
    completed_at TEXT,
    description TEXT,
    version INTEGER NOT NULL CHECK (version > 0),
    CHECK (
        (report_id IS NOT NULL)
        + (plan_id IS NOT NULL)
        + (asset_id IS NOT NULL) = 1
    )
);

CREATE TABLE IF NOT EXISTS inspections (
    id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL REFERENCES plans(id),
    inspected_at TEXT NOT NULL,
    result TEXT NOT NULL,
    text TEXT NOT NULL,
    version INTEGER NOT NULL CHECK (version > 0)
);

CREATE TABLE IF NOT EXISTS notices (
    id TEXT PRIMARY KEY,
    building TEXT NOT NULL,
    starts_at TEXT NOT NULL,
    ends_at TEXT NOT NULL,
    text TEXT NOT NULL,
    version INTEGER NOT NULL CHECK (version > 0)
);

CREATE INDEX IF NOT EXISTS idx_asset_buildings_building
    ON asset_buildings(building, asset_id);
CREATE INDEX IF NOT EXISTS idx_work_orders_asset
    ON work_orders(asset_id);
CREATE INDEX IF NOT EXISTS idx_work_orders_plan
    ON work_orders(plan_id);
"""


def open_database(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn
