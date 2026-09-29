import argparse
import json
from pathlib import Path

from evals.triage_eval import evaluate_public_outage


ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = ("base", "active_notice")


def replay_recorded(scenario: str) -> dict:
    path = ROOT / "evals" / "recorded_runs" / f"{scenario}_2026-09-29.json"
    recorded = json.loads(path.read_text(encoding="utf-8"))
    if recorded["scenario"] != scenario:
        raise ValueError(f"录制场景与文件名不一致：{path.name}")

    run = recorded["run"]
    evaluation = evaluate_public_outage(
        run, ROOT / "evals" / "gold_case.json"
    )

    if scenario == "active_notice":
        identified = any(
            item["notice_id"] == "N-02"
            and item["time_relation"] == "active"
            for item in (run.get("proposal") or {}).get("notices", [])
        )
        evaluation["checks"]["active_notice_identified"] = identified
        evaluation["case_pass"] = all(evaluation["checks"].values())

    trace = run["trace"]
    return {
        "scenario": scenario,
        "recorded_on": recorded["recorded_on"],
        "run_status": run["status"],
        "trace_calls": len(trace),
        "candidate_discovery_calls": sum(
            item.get("origin") == "candidate_discovery" for item in trace
        ),
        "model_tool_calls": sum(
            item.get("origin") != "candidate_discovery" for item in trace
        ),
        "case_pass": evaluation["case_pass"],
        "failed_checks": [
            name for name, passed in evaluation["checks"].items()
            if not passed
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--scenario", choices=(*SCENARIOS, "all"), default="all"
    )
    args = parser.parse_args()
    scenarios = SCENARIOS if args.scenario == "all" else (args.scenario,)
    results = [replay_recorded(name) for name in scenarios]
    print(json.dumps(results, ensure_ascii=False, indent=2))
    if not all(item["case_pass"] for item in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
