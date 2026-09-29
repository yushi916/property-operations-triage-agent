import json
import os
import sqlite3
from contextlib import closing
from hmac import compare_digest
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from fastapi import (
    APIRouter, Depends, HTTPException, Query,
)
from fastapi.security import APIKeyHeader


class ReportRevisionChange(BaseModel):
    model_config = ConfigDict(
        extra="forbid", str_strip_whitespace=True
    )
    report_id: str = Field(min_length=1)
    relation: Literal[
        "possible_same_event",
        "hold_separate",
        "needs_verification",
    ]
    reason: str = Field(min_length=1, max_length=500)


class ReportRevisionBody(BaseModel):
    model_config = ConfigDict(
        extra="forbid", str_strip_whitespace=True
    )
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=500)
    changes: list[ReportRevisionChange] = Field(
        min_length=1, max_length=20
    )


class ReviewDecisionBody(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )
    decision: Literal["approved", "rejected"]
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=500)



class PlanSubmitBody(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )
    plan_id: str = Field(min_length=1)
    order_id: str = Field(min_length=1)
    inspection_id: str = Field(min_length=1)



class ReportSubmitBody(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )
    report_id: str = Field(min_length=1)


review_key = APIKeyHeader(
    name="X-Review-Token",
    auto_error=False,
)


def require_review_token(key: str | None = Depends(review_key)):
    expected = os.environ.get("PROPERTY_REVIEW_TOKEN")
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="审核接口尚未配置演示令牌",
        )
    if key is None or not compare_digest(key, expected):
        raise HTTPException(
            status_code=401,
            detail="审核令牌无效",
        )


def create_review_router(db_path):
    db_path = Path(db_path)
    router = APIRouter(
        prefix="/v1/reviews",
        tags=["reviews"],
        dependencies=[Depends(require_review_token)],
    )

    @router.get("")
    def list_reviews(
        state: Literal[
            "pending", "approved", "rejected"
        ] | None = None,
        limit: int = Query(default=20, ge=1, le=100),
    ):
        sql = """
            SELECT id, kind, case_ref, state, version, created_at
            FROM review_proposals
        """
        params = []
        if state is not None:
            sql += " WHERE state = ?"
            params.append(state)
        sql += " ORDER BY created_at DESC, id DESC LIMIT ?"
        params.append(limit)

        with closing(sqlite3.connect(str(db_path))) as conn:
            rows = conn.execute(sql, params).fetchall()

        return [
            {
                "id": row[0],
                "kind": row[1],
                "case_ref": row[2],
                "state": row[3],
                "version": row[4],
                "created_at": row[5],
            }
            for row in rows
        ]

    @router.get("/{proposal_id}")
    def get_review(proposal_id: str):
        with closing(sqlite3.connect(str(db_path))) as conn:
            row = conn.execute("""
                SELECT id, kind, case_ref, state, version,
                       proposal_json, evidence_refs_json,
                       trace_json, created_at,
                       decided_at, decided_by, decision_reason
                FROM review_proposals
                WHERE id = ?
            """, (proposal_id,)).fetchone()

            if row is None:
                raise HTTPException(
                    status_code=404,
                    detail="审核建议不存在",
                )

            events = conn.execute("""
                SELECT event_type, actor, reason,
                       proposal_version, occurred_at
                FROM review_events
                WHERE proposal_id = ?
                ORDER BY rowid
            """, (proposal_id,)).fetchall()

            revisions = conn.execute("""
                SELECT from_version, to_version, actor, reason,
                       before_json, after_json, occurred_at
                FROM review_revisions
                WHERE proposal_id = ?
                ORDER BY to_version
            """, (proposal_id,)).fetchall()

            tasks = conn.execute("""
                SELECT id, kind, case_ref, title,
                       state, version, created_at
                FROM internal_tasks
                WHERE proposal_id = ?
            """, (proposal_id,)).fetchall()

        return {
            "id": row[0],
            "kind": row[1],
            "case_ref": row[2],
            "state": row[3],
            "version": row[4],
            "proposal": json.loads(row[5]),
            "evidence_refs": json.loads(row[6]),
            "trace": json.loads(row[7]),
            "created_at": row[8],
            "decided_at": row[9],
            "decided_by": row[10],
            "decision_reason": row[11],
            "revisions": [
                {
                    "from_version": r[0],
                    "to_version": r[1],
                    "actor": r[2],
                    "reason": r[3],
                    "before": json.loads(r[4]),
                    "after": json.loads(r[5]),
                    "occurred_at": r[6],
                }
                for r in revisions
            ],
            "events": [
                {
                    "event_type": e[0],
                    "actor": e[1],
                    "reason": e[2],
                    "proposal_version": e[3],
                    "occurred_at": e[4],
                }
                for e in events
            ],
            "tasks": [
                {
                    "id": t[0],
                    "kind": t[1],
                    "case_ref": t[2],
                    "title": t[3],
                    "state": t[4],
                    "version": t[5],
                    "created_at": t[6],
                }
                for t in tasks
            ],
        }

    @router.post("/{proposal_id}/revisions")
    def revise_review(proposal_id: str, body: ReportRevisionBody):
        from app.review_actions import revise_report_proposal

        try:
            return revise_report_proposal(
                db_path,
                proposal_id=proposal_id,
                expected_version=body.expected_version,
                changes=[
                    item.model_dump() for item in body.changes
                ],
                reviewer="demo_manager",
                reason=body.reason,
            )
        except ValueError as exc:
            code = 404 if str(exc) == "待审建议不存在" else 409
            raise HTTPException(
                status_code=code,
                detail=str(exc),
            ) from exc

    @router.post("/{proposal_id}/decision")
    def decide_review(proposal_id: str, body: ReviewDecisionBody):
        from app.review_actions import decide_review_proposal

        try:
            return decide_review_proposal(
                db_path,
                proposal_id=proposal_id,
                expected_version=body.expected_version,
                decision=body.decision,
                reviewer="demo_manager",
                reason=body.reason,
            )
        except ValueError as exc:
            code = 404 if str(exc) == "待审建议不存在" else 409
            raise HTTPException(
                status_code=code,
                detail=str(exc),
            ) from exc

    @router.post("/plan", status_code=201)
    def submit_plan(body: PlanSubmitBody):
        from app.review_actions import save_plan_review

        try:
            return save_plan_review(
                db_path,
                body.plan_id,
                body.order_id,
                body.inspection_id,
            )
        except sqlite3.IntegrityError as exc:
            raise HTTPException(
                status_code=409,
                detail="该计划已有待审核建议",
            ) from exc
        except ValueError as exc:
            code = 404 if "记录不存在" in str(exc) else 409
            raise HTTPException(
                status_code=code,
                detail=str(exc),
            ) from exc

    @router.post("/report", status_code=201)
    def submit_report(body: ReportSubmitBody):
        from google import genai
        from app.agent import investigate_report
        from app.review_actions import save_report_proposal

        with closing(sqlite3.connect(str(db_path))) as conn:
            exists = conn.execute(
                "SELECT 1 FROM reports WHERE id = ?",
                (body.report_id,),
            ).fetchone()
            pending = conn.execute("""
                SELECT 1 FROM review_proposals
                WHERE kind = 'report_triage'
                  AND case_ref = ?
                  AND state = 'pending'
            """, (body.report_id,)).fetchone()

        if exists is None:
            raise HTTPException(404, "起始报事不存在")
        if pending is not None:
            raise HTTPException(409, "该报事已有待审核建议")

        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise HTTPException(503, "尚未配置 Gemini API Key")

        try:
            with genai.Client(api_key=api_key) as client:
                run = investigate_report(
                    client,
                    db_path,
                    body.report_id,
                    max_rounds=16,
                    max_tool_calls=14,
                )
        except Exception as exc:
            raise HTTPException(
                502, "模型研判调用失败"
            ) from exc

        if run["status"] != "proposal":
            raise HTTPException(
                502,
                {
                    "message": f"模型未形成可保存草案：{run['status']}",
                    "run_status": run["status"],
                    "rounds": run.get("rounds"),
                    "trace": run.get("trace", []),
                    "validation_error": run.get("validation_error"),
                },
            )

        try:
            saved = save_report_proposal(db_path, run)
        except sqlite3.IntegrityError as exc:
            raise HTTPException(
                409,
                {
                    "message": "该报事已有待审核建议",
                    "run_status": run["status"],
                    "rounds": run.get("rounds"),
                    "trace": run.get("trace", []),
                    "validation_error": run.get("validation_error"),
                },
            ) from exc
        except ValueError as exc:
            raise HTTPException(
                409,
                {
                    "message": str(exc),
                    "run_status": run["status"],
                    "rounds": run.get("rounds"),
                    "trace": run.get("trace", []),
                    "validation_error": run.get("validation_error"),
                },
            ) from exc

        return {
            "id": saved["id"],
            "state": saved["state"],
            "version": saved["version"],
            "case_ref": saved["case_ref"],
            "proposal": run["proposal"],
            "candidate_discovery_calls": [
                item["tool"] for item in run["trace"]
                if item.get("origin") == "candidate_discovery"
            ],
            "model_tool_calls": [
                item["tool"] for item in run["trace"]
                if item.get("origin") != "candidate_discovery"
            ],
        }

    return router
