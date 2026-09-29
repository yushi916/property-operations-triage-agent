from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EvidenceRef(StrictModel):
    id: str = Field(description="实际读取过的记录 ID")
    version: int = Field(ge=1, description="读取时的记录版本")


class ReportAssessment(StrictModel):
    report_id: str
    relation: Literal[
        "possible_same_event",
        "hold_separate",
        "needs_verification",
    ]
    reason: str
    evidence_refs: list[EvidenceRef]


class NoticeAssessment(StrictModel):
    notice_id: str
    time_relation: Literal["active", "expired", "upcoming"]
    evidence_refs: list[EvidenceRef]


class UnknownItem(StrictModel):
    code: Literal[
        "fault_cause",
        "impact_scope",
        "restoration_time",
        "other",
    ] = Field(description="未知事项类别")
    detail: str = Field(description="具体还需要核实什么")


class TriageProposal(StrictModel):
    seed_report_id: str
    reports: list[ReportAssessment] = Field(
        description="逐条研判其他相关报事，不包括起始报事"
    )
    notices: list[NoticeAssessment]
    unknowns: list[UnknownItem]
    next_actions: list[str]
