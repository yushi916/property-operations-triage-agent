import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator, Literal

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.review import review_plan_pair
from app.tools import SQLiteEvidenceTools


DEFAULT_DB = Path(__file__).resolve().parents[1] / "data" / "property.db"


class PlanReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    plan_id: str = Field(min_length=1)
    order_id: str = Field(min_length=1)
    inspection_id: str = Field(min_length=1)


class EvidenceRef(BaseModel):
    id: str
    version: int


class PlanReviewResponse(BaseModel):
    plan_id: str
    status: Literal[
        "record_conflict", "needs_new_inspection",
        "needs_manual_review", "no_conflict_detected",
    ]
    evidence_refs: list[EvidenceRef]
    next_action: str


class ReportOut(BaseModel):
    id: str
    version: int
    reported_at: datetime
    building: str
    text: str


class AssetOut(BaseModel):
    id: str
    version: int
    name: str
    serves: list[str]


class WorkOrderOut(BaseModel):
    id: str
    version: int
    report_id: str | None
    plan_id: str | None
    asset_id: str | None
    status: str
    opened_at: datetime | None
    completed_at: datetime | None
    description: str | None


def create_app(db_path: Path | None = None) -> FastAPI:
    database = db_path if db_path is not None else DEFAULT_DB
    api = FastAPI(
        title="Property Operations Triage",
        version="0.2.0",
    )

    @contextmanager
    def db_connection() -> Iterator[sqlite3.Connection]:
        if not database.is_file():
            raise HTTPException(503, "数据库尚未初始化")
        conn = sqlite3.connect(database)
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
        finally:
            conn.close()

    @api.get("/v1/reports/{report_id}", response_model=ReportOut)
    def get_report(report_id: str) -> ReportOut:
        with db_connection() as conn:
            evidence = SQLiteEvidenceTools(conn).get_report(report_id)
        if evidence is None:
            raise HTTPException(404, "报事不存在")
        return ReportOut(**evidence["record"])

    @api.get(
        "/v1/buildings/{building}/assets",
        response_model=list[AssetOut],
    )
    def get_building_assets(building: str) -> list[AssetOut]:
        with db_connection() as conn:
            result = SQLiteEvidenceTools(
                conn
            ).lookup_assets_for_building(building)
        return [
            AssetOut(**item["record"])
            for item in result["evidence"]
        ]

    @api.get(
        "/v1/assets/{asset_id}/work-orders",
        response_model=list[WorkOrderOut],
    )
    def get_asset_work_orders(
        asset_id: str,
    ) -> list[WorkOrderOut]:
        with db_connection() as conn:
            exists = conn.execute(
                "SELECT 1 FROM assets WHERE id = ?",
                (asset_id,),
            ).fetchone()
            if exists is None:
                raise HTTPException(404, "设备不存在")
            result = SQLiteEvidenceTools(
                conn
            ).lookup_work_orders(asset_id=asset_id)
        return [
            WorkOrderOut(**item["record"])
            for item in result["evidence"]
        ]

    @api.post(
        "/v1/plan-reviews/preview",
        response_model=PlanReviewResponse,
    )
    def preview_plan_review(
        request: PlanReviewRequest,
    ) -> PlanReviewResponse:
        with db_connection() as conn:
            try:
                result = review_plan_pair(
                    conn, request.plan_id,
                    request.order_id, request.inspection_id,
                )
            except ValueError as exc:
                raise HTTPException(404, str(exc)) from exc
        return PlanReviewResponse(**result)

    from app.review_store import initialize_review_store
    from app.tasks import initialize_task_store
    from app.review_api import create_review_router

    if database.is_file():
        initialize_review_store(database)
        initialize_task_store(database)
    elif db_path is not None:
        raise FileNotFoundError(f"数据库不存在：{database}")

    def require_existing_database():
        if not database.is_file():
            raise HTTPException(503, "数据库尚未初始化")

    api.include_router(
        create_review_router(database),
        dependencies=[Depends(require_existing_database)],
    )

    return api


app = create_app()
