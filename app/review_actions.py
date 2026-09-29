import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


from app.proposal import TriageProposal


TABLE_BY_PREFIX = {
    "R": "reports",
    "A": "assets",
    "P": "plans",
    "W": "work_orders",
    "I": "inspections",
    "N": "notices",
}


def _read_refs(value):
    refs = set()
    if isinstance(value, dict):
        if "source_id" in value and "source_version" in value:
            refs.add((value["source_id"], value["source_version"]))
        for child in value.values():
            refs.update(_read_refs(child))
    elif isinstance(value, list):
        for child in value:
            refs.update(_read_refs(child))
    return refs


def save_report_proposal(db_path, run: dict) -> dict:
    if run.get("status") != "proposal" or not run.get("proposal"):
        raise ValueError("只能保存已形成的结构化建议")

    body = run["proposal"]
    case_ref = body["seed_report_id"]
    trace = run["trace"]
    if case_ref != run["report_id"]:
        raise ValueError("建议与起始报事不一致")

    read_refs = set()
    for call in trace:
        if call["outcome"]["ok"]:
            read_refs.update(_read_refs(call["outcome"]["result"]))

    # 被研判的报事必须引用自身已读取的证据版本。
    for item in body["reports"]:
        own_refs = {
            (ref["id"], ref["version"])
            for ref in item["evidence_refs"]
            if ref["id"] == item["report_id"]
        }
        if not own_refs or not own_refs <= read_refs:
            raise ValueError(f"报事 {item['report_id']} 缺少自身证据")

    # 对每条被研判报事核查既有工单；空结果也必须来自一次成功查询。
    for item in body["reports"]:
        lookups = [
            call["outcome"]["result"]
            for call in trace
            if call.get("tool") == "lookup_report_work_orders"
            and call.get("arguments", {}).get("report_id") == item["report_id"]
            and call.get("outcome", {}).get("ok") is True
            and call["outcome"]["result"].get("query") == {
                "report_id": item["report_id"]
            }
        ]
        if not lookups:
            raise ValueError(f"报事 {item['report_id']} 未核查既有工单")

        cited = {
            (ref["id"], ref["version"])
            for ref in item["evidence_refs"]
        }
        for lookup in lookups:
            for order in lookup["evidence"]:
                if order["record"]["report_id"] != item["report_id"]:
                    raise ValueError("工单查询结果与报事不匹配")
                order_ref = (order["source_id"], order["source_version"])
                if order_ref not in cited:
                    raise ValueError(
                        f"报事 {item['report_id']} 未引用既有工单 {order_ref[0]}"
                    )

    cited_refs = {
        (ref["id"], ref["version"])
        for item in body["reports"] + body["notices"]
        for ref in item["evidence_refs"]
    }
    if not cited_refs or not cited_refs <= read_refs:
        raise ValueError("建议引用了未读取的证据或缺少证据")

    seed_refs = {
        ref for ref in read_refs if ref[0] == case_ref
    }
    if len(seed_refs) != 1:
        raise ValueError("缺少唯一的起始报事版本")

    all_refs = cited_refs | seed_refs
    db_path = Path(db_path)
    if not db_path.is_file():
        raise FileNotFoundError(db_path)

    proposal_id = uuid4().hex
    event_id = uuid4().hex
    now = datetime.now(timezone.utc).isoformat()
    saved_refs = [
        {"id": record_id, "version": version}
        for record_id, version in sorted(all_refs)
    ]

    with closing(sqlite3.connect(str(db_path))) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        with conn:
            conn.execute("BEGIN IMMEDIATE")

            # 在同一事务中重新核对当前数据库版本
            for record_id, expected_version in sorted(all_refs):
                prefix = record_id.split("-", 1)[0]
                table = TABLE_BY_PREFIX.get(prefix)
                if table is None:
                    raise ValueError(f"未知证据类型：{record_id}")
                row = conn.execute(
                    f"SELECT version FROM {table} WHERE id = ?",
                    (record_id,),
                ).fetchone()
                if row is None or row[0] != expected_version:
                    raise ValueError(
                        f"证据 {record_id} 已不存在或版本已变化"
                    )

            conn.execute("""
                INSERT INTO review_proposals
                    (id, kind, case_ref, state, version,
                     proposal_json, evidence_refs_json,
                     trace_json, created_at)
                VALUES (?, 'report_triage', ?, 'pending', 1,
                        ?, ?, ?, ?)
            """, (
                proposal_id,
                case_ref,
                json.dumps(body, ensure_ascii=False),
                json.dumps(saved_refs, ensure_ascii=False),
                json.dumps(trace, ensure_ascii=False),
                now,
            ))
            conn.execute("""
                INSERT INTO review_events
                    (id, proposal_id, event_type, actor,
                     reason, proposal_version, occurred_at)
                VALUES (?, ?, 'proposed', 'system',
                        '提交建议供人工审核', 1, ?)
            """, (event_id, proposal_id, now))

    return {
        "id": proposal_id,
        "case_ref": case_ref,
        "state": "pending",
        "version": 1,
        "evidence_refs": saved_refs,
    }


def decide_review_proposal(
    db_path,
    proposal_id: str,
    expected_version: int,
    decision: str,
    reviewer: str,
    reason: str,
) -> dict:
    if decision not in {"approved", "rejected"}:
        raise ValueError("决定只能是 approved 或 rejected")
    if type(expected_version) is not int or expected_version < 1:
        raise ValueError("建议版本无效")
    reviewer = reviewer.strip()
    reason = reason.strip()
    if not reviewer or not reason:
        raise ValueError("审核人和审核理由不能为空")

    db_path = Path(db_path)
    if not db_path.is_file():
        raise FileNotFoundError(db_path)

    now = datetime.now(timezone.utc).isoformat()

    with closing(sqlite3.connect(str(db_path))) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        with conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("""
                SELECT state, version, evidence_refs_json
                FROM review_proposals
                WHERE id = ?
            """, (proposal_id,)).fetchone()

            if row is None:
                raise ValueError("待审建议不存在")

            state, current_version, refs_json = row
            if state != "pending" or current_version != expected_version:
                raise ValueError("建议已处理，或建议版本不匹配")

            # 拒绝可以关闭过时建议；批准必须使用当前证据版本。
            if decision == "approved":
                for ref in json.loads(refs_json):
                    record_id = ref["id"]
                    table = TABLE_BY_PREFIX.get(
                        record_id.split("-", 1)[0]
                    )
                    if table is None:
                        raise ValueError(f"未知证据类型：{record_id}")
                    current = conn.execute(
                        f"SELECT version FROM {table} WHERE id = ?",
                        (record_id,),
                    ).fetchone()
                    if current is None or current[0] != ref["version"]:
                        raise ValueError(
                            f"证据 {record_id} 版本已变化，不能批准旧建议"
                        )

            changed = conn.execute("""
                UPDATE review_proposals
                SET state = ?,
                    version = version + 1,
                    decided_at = ?,
                    decided_by = ?,
                    decision_reason = ?
                WHERE id = ? AND state = 'pending' AND version = ?
            """, (
                decision, now, reviewer, reason,
                proposal_id, expected_version,
            ))
            if changed.rowcount != 1:
                raise ValueError("审核状态已变化，请重新读取")

            new_version = expected_version + 1
            conn.execute("""
                INSERT INTO review_events
                    (id, proposal_id, event_type, actor,
                     reason, proposal_version, occurred_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                uuid4().hex, proposal_id, decision,
                reviewer, reason, new_version, now,
            ))

            if decision == "approved":
                from app.tasks import ensure_task_for_approved
                ensure_task_for_approved(conn, proposal_id)

    return {
        "id": proposal_id,
        "state": decision,
        "version": new_version,
        "decided_by": reviewer,
    }


def save_plan_review(
    db_path,
    plan_id: str,
    order_id: str,
    inspection_id: str,
) -> dict:
    from app.review import review_plan_pair

    db_path = Path(db_path)
    if not db_path.is_file():
        raise FileNotFoundError(db_path)

    proposal_id = uuid4().hex
    now = datetime.now(timezone.utc).isoformat()

    with closing(sqlite3.connect(str(db_path))) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        with conn:
            conn.execute("BEGIN IMMEDIATE")

            # 在写入事务内重新读取计划、工单和巡查记录
            review = review_plan_pair(
                conn, plan_id, order_id, inspection_id
            )
            if review["status"] not in {
                "record_conflict",
                "needs_new_inspection",
                "needs_manual_review",
            }:
                raise ValueError("没有需要提交审核的计划异常")

            refs = review["evidence_refs"]
            trace = [{
                "rule": "review_plan_pair",
                "input": {
                    "plan_id": plan_id,
                    "order_id": order_id,
                    "inspection_id": inspection_id,
                },
                "output": review,
            }]

            conn.execute("""
                INSERT INTO review_proposals
                    (id, kind, case_ref, state, version,
                     proposal_json, evidence_refs_json,
                     trace_json, created_at)
                VALUES (?, 'plan_review', ?, 'pending', 1,
                        ?, ?, ?, ?)
            """, (
                proposal_id,
                plan_id,
                json.dumps(review, ensure_ascii=False),
                json.dumps(refs, ensure_ascii=False),
                json.dumps(trace, ensure_ascii=False),
                now,
            ))
            conn.execute("""
                INSERT INTO review_events
                    (id, proposal_id, event_type, actor,
                     reason, proposal_version, occurred_at)
                VALUES (?, ?, 'proposed', 'system', ?, 1, ?)
            """, (
                uuid4().hex,
                proposal_id,
                "发现计划、工单与巡查记录需要人工核对",
                now,
            ))

    return {
        "id": proposal_id,
        "case_ref": plan_id,
        "state": "pending",
        "version": 1,
        "review": review,
    }


def revise_report_proposal(
    db_path,
    proposal_id: str,
    expected_version: int,
    changes: list[dict],
    reviewer: str,
    reason: str,
) -> dict:
    """修正已有报事的分类和说明，并保留前后快照。"""
    if type(expected_version) is not int or expected_version < 1:
        raise ValueError("建议版本无效")
    if not isinstance(reviewer, str) or not reviewer.strip():
        raise ValueError("审核人不能为空")
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("修正理由不能为空")
    if not isinstance(changes, list) or not changes:
        raise ValueError("至少修改一条已有报事")

    normalized = {}
    for change in changes:
        if not isinstance(change, dict) or set(change) != {
            "report_id", "relation", "reason"
        }:
            raise ValueError("只能修改报事分类和说明")

        report_id = change["report_id"]
        relation = change["relation"]
        detail = change["reason"]
        if (
            not isinstance(report_id, str) or not report_id.strip()
            or not isinstance(relation, str)
            or relation not in {
                "possible_same_event",
                "hold_separate",
                "needs_verification",
            }
            or not isinstance(detail, str) or not detail.strip()
        ):
            raise ValueError("报事修正内容无效")

        report_id = report_id.strip()
        if report_id in normalized:
            raise ValueError("不能重复修改同一报事")
        normalized[report_id] = (relation, detail.strip())

    db_path = Path(db_path)
    if not db_path.is_file():
        raise FileNotFoundError(db_path)

    now = datetime.now(timezone.utc).isoformat()
    with closing(sqlite3.connect(str(db_path))) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        with conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("""
                SELECT kind, state, version, proposal_json,
                       evidence_refs_json
                FROM review_proposals WHERE id = ?
            """, (proposal_id,)).fetchone()

            if row is None:
                raise ValueError("待审建议不存在")
            kind, state, version, before_json, refs_json = row
            if kind != "report_triage" or state != "pending":
                raise ValueError("只有待审的报事建议可修正")
            if version != expected_version:
                raise ValueError("建议版本不匹配")

            # 修正不能让过期证据继续支撑建议。
            for ref in json.loads(refs_json):
                record_id = ref["id"]
                table = TABLE_BY_PREFIX.get(
                    record_id.split("-", 1)[0]
                )
                if table is None:
                    raise ValueError(f"未知证据类型：{record_id}")
                current = conn.execute(
                    f"SELECT version FROM {table} WHERE id = ?",
                    (record_id,),
                ).fetchone()
                if current is None or current[0] != ref["version"]:
                    raise ValueError(
                        f"证据 {record_id} 版本已变化，不能修正旧建议"
                    )

            before = json.loads(before_json)
            after = json.loads(before_json)
            by_id = {
                item["report_id"]: item
                for item in after["reports"]
            }
            if not normalized.keys() <= by_id.keys():
                raise ValueError("只能修正原建议中的报事")

            for report_id, (relation, detail) in normalized.items():
                by_id[report_id]["relation"] = relation
                by_id[report_id]["reason"] = detail

            if after == before:
                raise ValueError("修正内容没有变化")
            after = TriageProposal.model_validate(after).model_dump()
            after_json = json.dumps(after, ensure_ascii=False)

            changed = conn.execute("""
                UPDATE review_proposals
                SET proposal_json = ?, version = version + 1
                WHERE id = ? AND kind = 'report_triage'
                  AND state = 'pending' AND version = ?
            """, (after_json, proposal_id, expected_version))
            if changed.rowcount != 1:
                raise ValueError("审核状态已变化，请重新读取")

            new_version = expected_version + 1
            conn.execute("""
                INSERT INTO review_revisions
                    (id, proposal_id, from_version, to_version,
                     actor, reason, before_json, after_json,
                     occurred_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                uuid4().hex, proposal_id,
                expected_version, new_version,
                reviewer.strip(), reason.strip(),
                before_json, after_json, now,
            ))

    return {
        "id": proposal_id,
        "state": "pending",
        "version": new_version,
        "revised_report_ids": sorted(normalized),
    }
