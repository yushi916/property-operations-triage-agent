from app.agent_tools import execute_read_tool


def discover_report_candidates(tools, report_id, window_minutes=30):
    """收集时间邻近及共用设备覆盖范围内的候选，不判定事件关系。"""
    trace = []

    def read(name, arguments):
        outcome = execute_read_tool(tools, name, arguments)
        if not outcome["ok"]:
            raise ValueError(
                f"候选发现查询失败：{name}: {outcome['error']}"
            )
        trace.append({
            "tool": name,
            "arguments": arguments,
            "outcome": outcome,
            "origin": "candidate_discovery",
        })
        return outcome["result"]

    seed = read("get_report", {"report_id": report_id})
    nearby = read("find_nearby_reports", {
        "seed_report_id": report_id,
        "window_minutes": window_minutes,
    })
    assets = read("lookup_assets_for_building", {
        "building": seed["record"]["building"],
    })

    found = {}

    def add(item, path):
        if item["source_id"] == report_id:
            return
        entry = found.setdefault(item["source_id"], {
            "evidence": item,
            "paths": [],
        })
        if path not in entry["paths"]:
            entry["paths"].append(path)

    for item in nearby["evidence"]:
        add(item, {"kind": "same_building"})

    for asset in assets["evidence"]:
        related = read("find_reports_for_asset", {
            "asset_id": asset["source_id"],
            "around_at": seed["record"]["reported_at"],
            "window_minutes": window_minutes,
        })
        for item in related["evidence"]:
            add(item, {
                "kind": "shared_asset",
                "asset_id": asset["source_id"],
            })

    candidates = sorted(
        found.values(),
        key=lambda entry: (
            entry["evidence"]["record"]["reported_at"],
            entry["evidence"]["source_id"],
        ),
    )
    return {
        "seed": seed,
        "candidates": candidates,
        "trace": trace,
    }
