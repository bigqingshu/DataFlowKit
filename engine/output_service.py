# -*- coding: utf-8 -*-
"""Backend output routing for workflow run results."""

from __future__ import annotations

from dataclasses import dataclass

from engine.issue_schema import has_error_issues, make_issue
from engine.models import TableData


OUTPUT_TO_PREVIEW = "输出到主界面预览区"
OUTPUT_TO_SQLITE_NEW = "保存为SQLite新表"
OUTPUT_OVERWRITE_TABLE = "覆盖当前表"
OUTPUT_TO_XLSX = "导出为xlsx"

OUTPUT_MODES = [
    {
        "mode": OUTPUT_TO_PREVIEW,
        "label": OUTPUT_TO_PREVIEW,
        "side_effect": False,
        "supported": True,
        "requires_target": False,
        "description": "把结果交给前端显示为当前预览表。",
    },
    {
        "mode": OUTPUT_TO_SQLITE_NEW,
        "label": OUTPUT_TO_SQLITE_NEW,
        "side_effect": True,
        "supported": False,
        "requires_target": True,
        "description": "后续通过 WorkflowServices 写入 SQLite 新表。",
    },
    {
        "mode": OUTPUT_OVERWRITE_TABLE,
        "label": OUTPUT_OVERWRITE_TABLE,
        "side_effect": True,
        "supported": False,
        "requires_target": True,
        "description": "后续通过 WorkflowServices 覆盖 SQLite 表。",
    },
    {
        "mode": OUTPUT_TO_XLSX,
        "label": OUTPUT_TO_XLSX,
        "side_effect": True,
        "supported": False,
        "requires_target": True,
        "description": "后续通过 OutputService 文件 writer 导出 xlsx。",
    },
]


@dataclass
class OutputSettings:
    mode: str = OUTPUT_TO_PREVIEW
    target: str = ""
    backup_before_overwrite: bool = True
    path: str = ""

    @classmethod
    def from_payload(cls, payload=None, **fallbacks):
        data = dict(payload or {})
        data.update({key: value for key, value in fallbacks.items() if value is not None})
        return cls(
            mode=str(data.get("mode") or data.get("output_mode") or OUTPUT_TO_PREVIEW),
            target=str(data.get("target") or data.get("output_table") or ""),
            backup_before_overwrite=bool(data.get("backup_before_overwrite", True)),
            path=str(data.get("path") or data.get("output_path") or ""),
        )

    def to_dict(self):
        return {
            "mode": self.mode,
            "target": self.target,
            "backup_before_overwrite": bool(self.backup_before_overwrite),
            "path": self.path,
        }


class OutputService:
    """Prepare final workflow output without depending on any concrete UI."""

    def list_output_modes(self):
        return {
            "ok": True,
            "modes": [dict(item) for item in OUTPUT_MODES],
        }

    def apply_output(self, headers=None, rows=None, logs=None, settings=None, **settings_kwargs):
        output_settings = OutputSettings.from_payload(settings, **settings_kwargs)
        table = TableData.from_payload({"headers": headers or [], "rows": rows or []}).to_dict()
        issues = _validate_settings(output_settings)
        if output_settings.mode == OUTPUT_TO_PREVIEW:
            return {
                "ok": True,
                "mode": output_settings.mode,
                "settings": output_settings.to_dict(),
                "table": table,
                "logs": list(logs or []),
                "issues": issues,
                "action": {
                    "type": "update_frontend_table",
                    "target": "preview",
                },
                "message": f"已准备输出到界面预览区：{len(table['rows'])} 行 x {len(table['headers'])} 列。",
            }

        issues.append(make_issue(
            "error",
            "output_writer_not_connected",
            f"{output_settings.mode} 需要后端写入服务，当前 OutputService 第一版尚未接入。",
            path="/output_mode",
            source="OutputService",
            suggestion="后续接入 WorkflowServices/数据库 writer/xlsx writer 后再启用该输出方式。",
        ))
        return {
            "ok": not has_error_issues(issues),
            "mode": output_settings.mode,
            "settings": output_settings.to_dict(),
            "table": table,
            "logs": list(logs or []),
            "issues": issues,
            "action": {
                "type": "unsupported_output",
                "target": output_settings.target or output_settings.path,
            },
            "message": "输出方式暂未接入后端写入服务。",
        }


def _validate_settings(settings):
    issues = []
    known_modes = {item["mode"] for item in OUTPUT_MODES}
    if settings.mode not in known_modes:
        issues.append(make_issue(
            "error",
            "unknown_output_mode",
            f"未知输出方式：{settings.mode}",
            path="/output_mode",
            source="OutputService",
        ))
        return issues
    if settings.mode in {OUTPUT_TO_SQLITE_NEW, OUTPUT_OVERWRITE_TABLE} and not settings.target.strip():
        issues.append(make_issue(
            "error",
            "missing_output_table",
            "该输出方式需要填写输出表名。",
            path="/output_table",
            source="OutputService",
        ))
    if settings.mode == OUTPUT_TO_XLSX and not settings.path.strip():
        issues.append(make_issue(
            "error",
            "missing_output_path",
            "导出为 xlsx 需要输出文件路径。",
            path="/output_path",
            source="OutputService",
        ))
    return issues

