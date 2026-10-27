from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.report_store import IntakeConflict, create_report
from app.review_api import require_review_token


RiskStatus = Literal["no_immediate_risk_reported", "urgent", "unknown"]
IntakeSource = Literal["staff_entry", "phone"]


class ReportCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    request_id: UUID = Field(description="一次提交的UUID；网络重试必须沿用同一编号")
    building: str = Field(min_length=1, max_length=40)
    text: str = Field(min_length=1, max_length=2000)
    source: IntakeSource = "staff_entry"
    occurred_at: AwareDatetime | None = Field(
        default=None, description="居民报告的发生时间（带时区）；未知时留空"
    )
    risk_status: RiskStatus = Field(
        description="录入人员声明，不代表AI已判断安全；urgent/unknown转人工"
    )


class IntakeOut(BaseModel):
    request_id: UUID
    source: IntakeSource
    occurred_at: AwareDatetime | None
    received_at: AwareDatetime
    received_by: str
    risk_status: RiskStatus
    triage_route: Literal["manual_attention", "ready_for_investigation"]
    next_action: str


class ReportOut(BaseModel):
    id: str
    version: int
    reported_at: datetime
    building: str
    text: str
    intake: IntakeOut | None = None


def create_report_router(db_path: Path) -> APIRouter:
    router = APIRouter(tags=["report intake"])

    @router.post(
        "/v1/reports", status_code=201, response_model=ReportOut,
        dependencies=[Depends(require_review_token)],
        responses={200: {"model": ReportOut, "description": "同一次提交的重试"}},
    )
    def submit_report(body: ReportCreate, response: Response) -> ReportOut:
        if not db_path.is_file():
            raise HTTPException(503, "数据库尚未初始化")
        payload = body.model_dump(mode="json")
        if body.occurred_at is not None:
            payload["occurred_at"] = body.occurred_at.astimezone(timezone.utc).isoformat()
        try:
            report, created = create_report(db_path, payload)
        except IntakeConflict as exc:
            raise HTTPException(409, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        if not created:
            response.status_code = 200
        return ReportOut(**report)

    return router
