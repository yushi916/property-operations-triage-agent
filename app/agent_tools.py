from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.tools import SQLiteEvidenceTools


class StrictArgs(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        str_strip_whitespace=True,
    )


class ReportArgs(StrictArgs):
    report_id: str = Field(min_length=1)


class NearbyArgs(StrictArgs):
    seed_report_id: str = Field(min_length=1)
    window_minutes: int = Field(default=30, ge=1, le=120)


class BuildingArgs(StrictArgs):
    building: str = Field(min_length=1)


class AssetArgs(StrictArgs):
    asset_id: str = Field(min_length=1)


class AssetReportsArgs(AssetArgs):
    around_at: str = Field(min_length=1)
    window_minutes: int = Field(default=30, ge=1, le=120)


class NoticeArgs(BuildingArgs):
    at: str = Field(min_length=1)


ARG_MODELS = {
    "get_report": ReportArgs,
    "find_nearby_reports": NearbyArgs,
    "lookup_assets_for_building": BuildingArgs,
    "find_reports_for_asset": AssetReportsArgs,
    "lookup_report_work_orders": ReportArgs,
    "lookup_asset_work_orders": AssetArgs,
    "lookup_notices": NoticeArgs,
}


def _tool(name, description, properties, required):
    return {
        "type": "function",
        "name": name,
        "description": description,
        "parameters": {
            "type": "object",
            "properties": properties,
            "required": required,
        },
    }


def _string(description):
    return {"type": "string", "description": description}


WINDOW = {"type": "integer", "description": "时间窗口，默认30分钟"}

TOOL_DEFINITIONS = [
    _tool(
        "get_report", "按ID读取原始报事及来源版本。",
        {"report_id": _string("报事ID，例如R-01")},
        ["report_id"],
    ),
    _tool(
        "find_nearby_reports",
        "找同楼栋、临近时间的其他报事；结果只是候选。",
        {
            "seed_report_id": _string("起点报事ID"),
            "window_minutes": WINDOW,
        },
        ["seed_report_id"],
    ),
    _tool(
        "lookup_assets_for_building",
        "查覆盖某楼栋的共用设备及其覆盖楼栋。",
        {"building": _string("楼栋，例如3栋")},
        ["building"],
    ),
    _tool(
        "find_reports_for_asset",
        "在设备覆盖楼栋中找临近报事；不证明同一事件。",
        {
            "asset_id": _string("设备ID"),
            "around_at": _string("含时区的ISO时间"),
            "window_minutes": WINDOW,
        },
        ["asset_id", "around_at"],
    ),
    _tool(
        "lookup_report_work_orders",
        "查某条报事已有的独立维修工单。",
        {"report_id": _string("报事ID")},
        ["report_id"],
    ),
    _tool(
        "lookup_asset_work_orders",
        "查共用设备的调查或维修工单。",
        {"asset_id": _string("设备ID")},
        ["asset_id"],
    ),
    _tool(
        "lookup_notices",
        "查指定楼栋通知，并标明通知在指定时间是否有效。",
        {
            "building": _string("楼栋"),
            "at": _string("报事时间，含时区的ISO格式"),
        },
        ["building", "at"],
    ),
]


def execute_read_tool(
    tools: SQLiteEvidenceTools,
    name: str,
    arguments: dict,
) -> dict:
    model = ARG_MODELS.get(name)
    if model is None:
        return {"ok": False, "error": "工具不在白名单中"}
    try:
        args = model.model_validate(arguments).model_dump()
        handlers = {
            "get_report": tools.get_report,
            "find_nearby_reports": tools.find_nearby_reports,
            "lookup_assets_for_building":
                tools.lookup_assets_for_building,
            "find_reports_for_asset": tools.find_reports_for_asset,
            "lookup_report_work_orders":
                lambda report_id: tools.lookup_work_orders(
                    report_id=report_id
                ),
            "lookup_asset_work_orders":
                lambda asset_id: tools.lookup_work_orders(
                    asset_id=asset_id
                ),
            "lookup_notices": tools.lookup_notices,
        }
        result = handlers[name](**args)
        if result is None:
            return {"ok": False, "error": "记录不存在"}
        return {"ok": True, "result": result}
    except (ValidationError, ValueError, TypeError) as exc:
        return {"ok": False, "error": str(exc)}
