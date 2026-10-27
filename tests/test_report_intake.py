import os
import sqlite3
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import create_app
from app.baseline import proximity_baseline
from app.candidates import discover_report_candidates
from app.tools import SQLiteEvidenceTools
from evals.scenarios import create_scenario_database


ROOT = Path(__file__).resolve().parents[1]
HEADERS = {"X-Review-Token": "intake-test-token"}
RECEIVED_AT = datetime(2026, 9, 28, 1, 15, tzinfo=timezone.utc)


class ReportIntakeTest(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.db = Path(temporary.name) / "case.db"
        create_scenario_database(
            self.db, ROOT / "data/demo_case.json", "base"
        )
        environment = patch.dict(
            os.environ, {"PROPERTY_REVIEW_TOKEN": "intake-test-token"}
        )
        environment.start()
        self.addCleanup(environment.stop)
        self.client = TestClient(create_app(self.db))
        self.addCleanup(self.client.close)

    def payload(self, **changes):
        return {
            "request_id": str(uuid4()),
            "building": "3栋",
            "text": "整套房突然没有水，原因待核实",
            "source": "phone",
            "occurred_at": "2026-09-28T09:05:00+08:00",
            "risk_status": "no_immediate_risk_reported",
            **changes,
        }

    def post(self, body):
        with patch("app.report_store.utc_now", return_value=RECEIVED_AT):
            return self.client.post("/v1/reports", headers=HEADERS, json=body)

    def test_create_survives_app_restart_and_does_not_call_model(self):
        body = self.payload()
        with patch("google.genai.Client") as model:
            response = self.post(body)
        self.assertEqual(response.status_code, 201, response.text)
        model.assert_not_called()
        created = response.json()
        self.assertEqual(created["reported_at"], "2026-09-28T01:15:00Z")
        self.assertEqual(created["intake"]["occurred_at"], "2026-09-28T01:05:00Z")
        self.assertEqual(created["intake"]["received_by"], "demo_manager")
        self.assertEqual(created["intake"]["triage_route"], "ready_for_investigation")
        with TestClient(create_app(self.db)) as restarted:
            fetched = restarted.get(f"/v1/reports/{created['id']}")
        self.assertEqual(fetched.json(), created)
        with closing(sqlite3.connect(self.db)) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM review_proposals").fetchone()[0], 0)

    def test_same_request_replays_and_conflicting_reuse_is_rejected(self):
        body = self.payload()
        first, repeated = self.post(body), self.post(body)
        self.assertEqual((first.status_code, repeated.status_code), (201, 200))
        self.assertEqual(first.json(), repeated.json())
        conflict = self.post({**body, "text": "改成另一条报事"})
        self.assertEqual(conflict.status_code, 409, conflict.text)
        with closing(sqlite3.connect(self.db)) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM report_intakes").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM reports").fetchone()[0], 5)

    def test_new_report_feeds_existing_candidate_tools_and_baseline(self):
        created = self.post(self.payload()).json()
        with closing(sqlite3.connect(self.db)) as conn:
            simple = proximity_baseline(conn, created["id"])
            discovery = discover_report_candidates(SQLiteEvidenceTools(conn), created["id"])
        self.assertEqual(set(simple["possible_same_event"]), {"R-01", "R-02", "R-03"})
        candidates = {item["evidence"]["source_id"] for item in discovery["candidates"]}
        self.assertEqual(candidates, {"R-01", "R-02", "R-03", "R-04"})
        self.assertEqual(discovery["seed"]["source_id"], created["id"])
        # This verifies candidate coverage, not a live model's classification.

    def test_concurrent_retries_create_one_report(self):
        body = self.payload()
        def submit(_):
            with TestClient(create_app(self.db)) as client:
                return client.post("/v1/reports", headers=HEADERS, json=body)
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(submit, range(2)))
        self.assertEqual(sorted(r.status_code for r in results), [200, 201])
        self.assertEqual(results[0].json()["id"], results[1].json()["id"])

    def test_invalid_input_does_not_write_reports(self):
        cases = [
            {"text": "  "}, {"building": "不存在的楼栋"},
            {"occurred_at": "2026-09-28T09:05:00"},
            {"occurred_at": "2026-99-99T09:00:00+08:00"},
            {"occurred_at": "2026-09-29T09:00:00+08:00"},
            {"text": "x" * 2001}, {"risk_status": "safe"},
            {"request_id": "not-a-uuid"}, {"version": 99},
        ]
        for changes in cases:
            with self.subTest(changes=changes):
                response = self.post(self.payload(**changes))
                self.assertEqual(response.status_code, 422, response.text)
        with closing(sqlite3.connect(self.db)) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM reports").fetchone()[0], 4)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM report_intakes").fetchone()[0], 0)

    def test_urgent_and_unknown_risk_are_saved_but_block_model_investigation(self):
        for risk in ("urgent", "unknown"):
            with self.subTest(risk=risk):
                created = self.post(self.payload(risk_status=risk, occurred_at=None))
                self.assertEqual(created.status_code, 201, created.text)
                report = created.json()
                self.assertEqual(report["intake"]["triage_route"], "manual_attention")
                self.assertIsNone(report["intake"]["occurred_at"])
                with patch("google.genai.Client") as model:
                    response = self.client.post(
                        "/v1/reviews/report", headers=HEADERS,
                        json={"report_id": report["id"]},
                    )
                self.assertEqual(response.status_code, 409, response.text)
                model.assert_not_called()

    def test_insert_failure_rolls_back_report_and_receipt(self):
        with closing(sqlite3.connect(self.db)) as conn:
            conn.execute("""CREATE TRIGGER reject_receipt BEFORE INSERT ON report_intakes
                            BEGIN SELECT RAISE(ABORT, 'simulated write failure'); END""")
        with TestClient(create_app(self.db), raise_server_exceptions=False) as client:
            response = client.post("/v1/reports", headers=HEADERS, json=self.payload())
        self.assertEqual(response.status_code, 500)
        with closing(sqlite3.connect(self.db)) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM reports").fetchone()[0], 4)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM report_intakes").fetchone()[0], 0)

    def test_auth_and_missing_database_fail_without_writing(self):
        denied = self.client.post("/v1/reports", json=self.payload())
        self.assertEqual(denied.status_code, 401, denied.text)
        with patch.dict(os.environ, {"PROPERTY_REVIEW_TOKEN": ""}):
            unconfigured = self.post(self.payload())
        self.assertEqual(unconfigured.status_code, 503, unconfigured.text)
        missing = self.db.parent / "missing.db"
        with patch("app.main.DEFAULT_DB", missing):
            with TestClient(create_app()) as client:
                response = client.post("/v1/reports", headers=HEADERS, json=self.payload())
        self.assertEqual(response.status_code, 503, response.text)
        self.assertFalse(missing.exists())

    def test_legacy_seed_reports_remain_readable(self):
        response = self.client.get("/v1/reports/R-01")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIsNone(response.json()["intake"])


if __name__ == "__main__":
    unittest.main()
