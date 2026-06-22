# -*- coding: utf-8 -*-
"""Backend output routing for workflow run results."""

from __future__ import annotations

from dataclasses import dataclass

from engine.issue_schema import has_error_issues, make_issue
from engine.models import TableData
from engine.workflow_services import WorkflowServices


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
        "supported": True,
        "requires_target": True,
        "requires_db_path": True,
        "description": "通过 WorkflowServices 写入 SQLite 新表；同名表存在时自动加时间戳。",
    },
    {
        "mode": OUTPUT_OVERWRITE_TABLE,
        "label": OUTPUT_OVERWRITE_TABLE,
        "side_effect": True,
        "supported": True,
        "requires_target": True,
        "requires_db_path": True,
        "description": "通过 WorkflowServices 覆盖 SQLite 表，可在覆盖前备份旧表。",
    },
    {
        "mode": OUTPUT_TO_XLSX,
        "label": OUTPUT_TO_XLSX,
        "side_effect": True,
        "supported": True,
        "requires_target": False,
        "requires_path": True,
        "description": "通过 WorkflowServices 导出 xlsx 文件。",
    },
]


@dataclass
class OutputSettings:
    mode: str = OUTPUT_TO_PREVIEW
    target: str = ""
    backup_before_overwrite: bool = True
    path: str = ""
    db_path: str = ""

    @classmethod
    def from_payload(cls, payload=None, **fallbacks):
        data = dict(payload or {})
        data.update({key: value for key, value in fallbacks.items() if value is not None})
        return cls(
            mode=str(data.get("mode") or data.get("output_mode") or OUTPUT_TO_PREVIEW),
            target=str(data.get("target") or data.get("output_table") or ""),
            backup_before_overwrite=_to_bool(data.get("backup_before_overwrite", True)),
            path=str(data.get("path") or data.get("output_path") or ""),
            db_path=str(data.get("db_path") or data.get("output_db_path") or ""),
        )

    def to_dict(self):
        return {
            "mode": self.mode,
            "target": self.target,
            "backup_before_overwrite": bool(self.backup_before_overwrite),
            "path": self.path,
            "db_path": self.db_path,
        }


class OutputService:
    """Prepare final workflow output without depending on any concrete UI."""

    def __init__(self, services=None):
        self.services = services or WorkflowServices()

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
        if has_error_issues(issues):
            return _output_failure(
                output_settings,
                table,
                logs,
                issues,
                action_type="output_validation_failed",
                message="输出设置校验失败。",
            )

        try:
            if output_settings.mode == OUTPUT_TO_SQLITE_NEW:
                result = self.services.write_table(
                    output_settings.target,
                    table,
                    mode="timestamp",
                    backup=False,
                    db_path=output_settings.db_path,
                )
                return _output_success(
                    output_settings,
                    table,
                    logs,
                    action_type="write_sqlite_table",
                    target=result.get("table_name", output_settings.target),
                    service_result=result,
                    message=f"已输出到 SQLite 表：{result.get('table_name', output_settings.target)}。",
                )
            if output_settings.mode == OUTPUT_OVERWRITE_TABLE:
                result = self.services.write_table(
                    output_settings.target,
                    table,
                    mode="replace",
                    backup=output_settings.backup_before_overwrite,
                    db_path=output_settings.db_path,
                )
                return _output_success(
                    output_settings,
                    table,
                    logs,
                    action_type="write_sqlite_table",
                    target=result.get("table_name", output_settings.target),
                    service_result=result,
                    message=f"已覆盖 SQLite 表：{result.get('table_name', output_settings.target)}。",
                )
            if output_settings.mode == OUTPUT_TO_XLSX:
                result = self.services.export_xlsx(
                    output_settings.path,
                    table,
                    sheet_name=output_settings.target or "结果",
                )
                return _output_success(
                    output_settings,
                    table,
                    logs,
                    action_type="export_xlsx",
                    target=result.get("path", output_settings.path),
                    service_result=result,
                    message=f"已导出 xlsx：{result.get('path', output_settings.path)}。",
                )
        except Exception as exc:
            issues.append(make_issue(
                "error",
                "output_write_failed",
                str(exc),
                path="/output",
                source="OutputService",
            ))
            return _output_failure(
                output_settings,
                table,
                logs,
                issues,
                action_type="output_write_failed",
                message="输出写入失败。",
            )

        issues.append(make_issue(
            "error",
            "unknown_output_mode",
            f"未知输出方式：{output_settings.mode}",
            path="/output_mode",
            source="OutputService",
        ))
        return _output_failure(
            output_settings,
            table,
            logs,
            issues,
            action_type="unknown_output_mode",
            message="未知输出方式。",
        )


def _output_success(settings, table, logs, *, action_type, target, service_result, message):
    return {
        "ok": True,
        "mode": settings.mode,
        "settings": settings.to_dict(),
        "table": table,
        "logs": list(logs or []),
        "issues": [],
        "action": {
            "type": action_type,
            "target": target,
        },
        "service_result": service_result,
        "message": message,
    }


def _output_failure(settings, table, logs, issues, *, action_type, message):
    return {
        "ok": False,
        "mode": settings.mode,
        "settings": settings.to_dict(),
        "table": table,
        "logs": list(logs or []),
        "issues": issues,
        "action": {
            "type": action_type,
            "target": settings.target or settings.path,
        },
        "message": message,
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
    if settings.mode in {OUTPUT_TO_SQLITE_NEW, OUTPUT_OVERWRITE_TABLE} and not settings.db_path.strip():
        issues.append(make_issue(
            "error",
            "missing_db_path",
            "SQLite 输出需要数据库路径。",
            path="/db_path",
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


def _to_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in {"", "0", "false", "no", "off", "否", "不"}
    return bool(value)
