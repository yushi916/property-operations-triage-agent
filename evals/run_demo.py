import argparse
import json
import os
import secrets
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path

from app.baseline import proximity_baseline
from app.review import review_plan_pair
from evals.scenarios import (
    SCENARIOS,
    create_scenario_database,
)
from evals.triage_eval import evaluate_public_outage


ROOT = Path(__file__).resolve().parents[1]


def run_demo(scenario: str, with_model: bool) -> dict:
    if with_model and not os.environ.get("GEMINI_API_KEY"):
        raise ValueError(
            "使用 --with-model 前须设置 GEMINI_API_KEY"
        )

    with tempfile.TemporaryDirectory() as temp_dir:
        case_db = Path(temp_dir) / "property.db"
        create_scenario_database(
            case_db,
            ROOT / "data" / "demo_case.json",
            scenario,
        )

        with closing(sqlite3.connect(case_db)) as conn:
            baseline = proximity_baseline(conn, "R-01")
            plan = review_plan_pair(
                conn, "P-01", "W-01", "I-01"
            )
            notices = [
                row[0] for row in conn.execute(
                    "SELECT id FROM notices ORDER BY id"
                )
            ]

        result = {
            "scenario": scenario,
            "baseline_candidates": (
                baseline["possible_same_event"]
            ),
            "plan_status": plan["status"],
            "notices": notices,
        }

        if with_model:
            from fastapi.testclient import TestClient
            from app.main import create_app

            # 临时演示令牌只存在于这个进程
            token = secrets.token_urlsafe(32)
            previous_token = os.environ.get(
                "PROPERTY_REVIEW_TOKEN"
            )
            os.environ["PROPERTY_REVIEW_TOKEN"] = token

            try:
                headers = {"X-Review-Token": token}
                with TestClient(create_app(case_db)) as client:
                    submitted = client.post(
                        "/v1/reviews/report",
                        headers=headers,
                        json={"report_id": "R-01"},
                    )
                    if submitted.status_code != 201:
                        try:
                            error_detail = submitted.json().get("detail")
                        except ValueError:
                            error_detail = submitted.text
                        if not isinstance(error_detail, dict):
                            error_detail = {"message": str(error_detail)}

                        failure_trace = error_detail.get("trace") or []
                        result["submission_failure"] = {
                            "status_code": submitted.status_code,
                            "message": error_detail.get("message"),
                            "run_status": error_detail.get("run_status"),
                            "rounds": error_detail.get("rounds"),
                            "error_type": error_detail.get("error_type"),
                            "validation_error": error_detail.get(
                                "validation_error"
                            ),
                        }
                        result["trace"] = failure_trace
                        result["candidate_discovery_calls"] = [
                            item["tool"] for item in failure_trace
                            if item.get("origin") == "candidate_discovery"
                        ]
                        result["model_tool_calls"] = [
                            item["tool"] for item in failure_trace
                            if item.get("origin") != "candidate_discovery"
                        ]
                        result["review_state"] = None
                        result["evaluation"] = {
                            "case_pass": False,
                            "checks": {},
                            "error": "proposal_not_submitted",
                        }
                        return result

                    proposal_id = submitted.json()["id"]
                    detail_response = client.get(
                        f"/v1/reviews/{proposal_id}",
                        headers=headers,
                    )
                    detail_response.raise_for_status()
                    detail = detail_response.json()
            finally:
                if previous_token is None:
                    os.environ.pop(
                        "PROPERTY_REVIEW_TOKEN", None
                    )
                else:
                    os.environ[
                        "PROPERTY_REVIEW_TOKEN"
                    ] = previous_token

            replayed_run = {
                "status": "proposal",
                "report_id": "R-01",
                "proposal": detail["proposal"],
                "trace": detail["trace"],
            }
            evaluation = evaluate_public_outage(
                replayed_run,
                ROOT / "evals" / "gold_case.json",
            )

            if scenario == "active_notice":
                evaluation["checks"][
                    "active_notice_identified"
                ] = any(
                    item["notice_id"] == "N-02"
                    and item["time_relation"] == "active"
                    for item in detail["proposal"]["notices"]
                )
                evaluation["case_pass"] = all(
                    evaluation["checks"].values()
                )

            result["agent_labels"] = {
                item["report_id"]: item["relation"]
                for item in detail["proposal"]["reports"]
            }
            result["candidate_discovery_calls"] = [
                item["tool"] for item in detail["trace"]
                if item.get("origin") == "candidate_discovery"
            ]
            result["model_tool_calls"] = [
                item["tool"] for item in detail["trace"]
                if item.get("origin") != "candidate_discovery"
            ]
            result["review_state"] = detail["state"]
            result["evaluation"] = evaluation

        return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--scenario",
        choices=sorted(SCENARIOS),
        default="base",
    )
    parser.add_argument(
        "--with-model",
        action="store_true",
        help="通过 FastAPI 调用 Gemini Agent",
    )
    args = parser.parse_args()

    result = run_demo(args.scenario, args.with_model)

    expected_notices = {
        "base": {"N-01"},
        "active_notice": {"N-01", "N-02"},
    }
    offline_checks = {
        "plan_conflict": result["plan_status"] == "record_conflict",
        "baseline_candidates": set(result["baseline_candidates"]) == {
            "R-02", "R-03"
        },
        "scenario_notices": set(result["notices"]) == expected_notices[
            args.scenario
        ],
    }
    result["offline_checks"] = offline_checks
    print(json.dumps(
        result, ensure_ascii=False, indent=2
    ))

    if not all(offline_checks.values()) or (
        args.with_model and not result["evaluation"]["case_pass"]
    ):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
