import sqlite3
from datetime import datetime


class SQLiteEvidenceTools:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    @staticmethod
    def _evidence_rows(cursor: sqlite3.Cursor) -> list[dict]:
        columns = [column[0] for column in cursor.description]
        records = [
            dict(zip(columns, row))
            for row in cursor.fetchall()
        ]
        return [
            {
                "source_id": record["id"],
                "source_version": record["version"],
                "record": record,
            }
            for record in records
        ]

    def get_report(self, report_id: str) -> dict | None:
        if not report_id.strip():
            raise ValueError("报事 ID 不能为空")

        cursor = self.conn.execute("""
            SELECT id, version, reported_at, building, text
            FROM reports
            WHERE id = ?
        """, (report_id,))
        evidence = self._evidence_rows(cursor)
        return evidence[0] if evidence else None

    def lookup_assets_for_building(self, building: str) -> dict:
        if not building.strip():
            raise ValueError("楼栋不能为空")

        cursor = self.conn.execute("""
            SELECT a.id, a.version, a.name
            FROM assets AS a
            JOIN asset_buildings AS ab ON ab.asset_id = a.id
            WHERE ab.building = ?
            ORDER BY a.id
        """, (building,))
        evidence = self._evidence_rows(cursor)

        for item in evidence:
            asset_id = item["source_id"]
            item["record"]["serves"] = [
                row[0] for row in self.conn.execute("""
                    SELECT building
                    FROM asset_buildings
                    WHERE asset_id = ?
                    ORDER BY building
                """, (asset_id,))
            ]

        return {
            "query": {"building": building},
            "evidence": evidence,
        }

    def find_nearby_reports(
        self, seed_report_id: str, window_minutes: int = 30
    ) -> dict:
        if type(window_minutes) is not int or not 1 <= window_minutes <= 120:
            raise ValueError("时间窗口必须是 1 到 120 分钟的整数")

        seed = self.get_report(seed_report_id)
        if seed is None:
            raise ValueError("起点报事不存在")

        seed_time = datetime.fromisoformat(
            seed["record"]["reported_at"]
        )
        cursor = self.conn.execute("""
            SELECT id, version, reported_at, building, text
            FROM reports
            WHERE building = ? AND id != ?
            ORDER BY reported_at, id
        """, (seed["record"]["building"], seed_report_id))

        nearby = [
            item for item in self._evidence_rows(cursor)
            if abs((
                datetime.fromisoformat(
                    item["record"]["reported_at"]
                ) - seed_time
            ).total_seconds()) <= window_minutes * 60
        ]
        return {
            "query": {
                "seed_report_id": seed_report_id,
                "window_minutes": window_minutes,
            },
            "evidence": nearby,
        }

    def lookup_notices(self, *, building: str, at: str) -> dict:
        if not building.strip():
            raise ValueError("楼栋不能为空")
        try:
            requested_at = datetime.fromisoformat(at)
        except ValueError as exc:
            raise ValueError("at 必须是 ISO 格式时间") from exc
        if requested_at.tzinfo is None:
            raise ValueError("at 必须包含时区")

        cursor = self.conn.execute("""
            SELECT id, version, building, starts_at, ends_at, text
            FROM notices
            WHERE building = ?
            ORDER BY starts_at, id
        """, (building,))
        evidence = self._evidence_rows(cursor)

        for item in evidence:
            record = item["record"]
            starts = datetime.fromisoformat(record["starts_at"])
            ends = datetime.fromisoformat(record["ends_at"])
            item["time_relation"] = (
                "active" if starts <= requested_at <= ends
                else "expired" if ends < requested_at
                else "upcoming"
            )

        return {
            "query": {"building": building, "at": at},
            "evidence": evidence,
        }

    def find_reports_for_asset(
        self,
        *,
        asset_id: str,
        around_at: str,
        window_minutes: int = 30,
    ) -> dict:
        if not asset_id.strip():
            raise ValueError("设备 ID 不能为空")
        if type(window_minutes) is not int or not 1 <= window_minutes <= 120:
            raise ValueError("时间窗口必须是 1 到 120 分钟的整数")

        try:
            center = datetime.fromisoformat(around_at)
        except ValueError as exc:
            raise ValueError("around_at 必须是 ISO 格式时间") from exc
        if center.tzinfo is None:
            raise ValueError("around_at 必须包含时区")

        exists = self.conn.execute(
            "SELECT 1 FROM assets WHERE id = ?", (asset_id,)
        ).fetchone()
        if exists is None:
            raise ValueError("设备不存在")

        cursor = self.conn.execute("""
            SELECT DISTINCT r.id, r.version, r.reported_at,
                            r.building, r.text
            FROM reports AS r
            JOIN asset_buildings AS ab
                ON ab.building = r.building
            WHERE ab.asset_id = ?
            ORDER BY r.reported_at, r.id
        """, (asset_id,))

        evidence = [
            item for item in self._evidence_rows(cursor)
            if abs((
                datetime.fromisoformat(
                    item["record"]["reported_at"]
                ) - center
            ).total_seconds()) <= window_minutes * 60
        ]
        return {
            "query": {
                "asset_id": asset_id,
                "around_at": around_at,
                "window_minutes": window_minutes,
            },
            "evidence": evidence,
        }

    def lookup_work_orders(
        self,
        *,
        report_id: str | None = None,
        plan_id: str | None = None,
        asset_id: str | None = None,
    ) -> dict:
        query = {
            key: value
            for key, value in {
                "report_id": report_id,
                "plan_id": plan_id,
                "asset_id": asset_id,
            }.items()
            if value is not None
        }
        if len(query) != 1 or not all(
            isinstance(value, str) and value.strip()
            for value in query.values()
        ):
            raise ValueError("必须提供且仅提供一个非空查询 ID")

        column, value = next(iter(query.items()))
        # column 只可能取自上面三个固定字段；查询值使用 SQL 参数
        cursor = self.conn.execute(f"""
            SELECT id, version, report_id, plan_id, asset_id,
                   status, opened_at, completed_at, description
            FROM work_orders
            WHERE {column} = ?
            ORDER BY id
        """, (value,))
        return {
            "query": query,
            "evidence": self._evidence_rows(cursor),
        }
