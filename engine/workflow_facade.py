# -*- coding: utf-8 -*-
"""Unified backend facade for UI-facing workflow operations."""

from __future__ import annotations

import copy

from engine.headless import HeadlessWorkflowEngine
from engine.output_service import OutputSettings
from engine.plan_templates import PlanTemplateService
from engine.table_io import load_table_file
from workflow.plan_commands import apply_plan_command as apply_workflow_plan_command
from workflow.node_ui_schema import build_node_ui_catalog


class WorkflowFacade:
    """Collect UI-neutral workflow operations for desktop and worker clients."""

    def __init__(self, engine=None, *, node_id_factory=None):
        self.engine = engine or HeadlessWorkflowEngine()
        self.plan_templates = PlanTemplateService(
            node_id_factory=node_id_factory or getattr(self.engine, "node_id_factory", None)
        )

    def import_table_file(self, path):
        headers, rows = load_table_file(path)
        return {
            "ok": True,
            "path": str(path),
            "table": {
                "type": "table",
                "headers": list(headers or []),
                "rows": [list(row) for row in (rows or [])],
            },
        }

    def list_plan_templates(self, plan_dir):
        return self.plan_templates.list_templates(plan_dir)

    def load_plan_template(self, path, *, migrate=True, target_version=None):
        return self.plan_templates.load_template(
            path,
            migrate=migrate,
            target_version=target_version,
        )

    def save_plan_template(self, path, plan, **options):
        return self.plan_templates.save_template(path, copy.deepcopy(plan), **options)

    def validate_plan_template(self, plan):
        return self.plan_templates.validate_template(copy.deepcopy(plan))

    def apply_plan_command(self, plan, command, **kwargs):
        return apply_workflow_plan_command(copy.deepcopy(plan), command, **kwargs)

    def list_node_ui_catalog(self, *, include_unsupported=True, preview_headers=None, table_names=None, table_columns=None):
        catalog = build_node_ui_catalog(
            include_unsupported=include_unsupported,
            preview_headers=preview_headers,
            table_names=table_names,
            table_columns=table_columns,
        )
        return {
            "ok": True,
            "catalog": catalog,
        }

    def build_output_settings(self, payload=None, **fallbacks):
        settings = OutputSettings.from_payload(payload, **fallbacks)
        return {
            "ok": True,
            "settings": settings.to_dict(),
        }

    def list_preview_sources(self, *, current_headers=None, current_rows=None, preview_headers=None, preview_rows=None, db_path=None):
        items = [
            {
                "key": "input",
                "label": "输入表格",
                "source": {"type": "memory", "table_role": "input"},
                "table": {
                    "headers": list(current_headers or []),
                    "rows": [list(row) for row in (current_rows or [])],
                },
            },
            {
                "key": "preview",
                "label": "Headless 预览结果",
                "source": {"type": "memory", "table_role": "preview"},
                "table": {
                    "headers": list(preview_headers or []),
                    "rows": [list(row) for row in (preview_rows or [])],
                },
            },
        ]
        issues = []
        db_path = str(db_path or "").strip()
        if db_path:
            try:
                table_result = self.engine.list_tables(db_path=db_path)
                for table_name in table_result.get("tables", []) or []:
                    items.append({
                        "key": f"sqlite:{table_name}",
                        "label": f"SQLite：{table_name}",
                        "source": {"type": "sqlite", "db_path": db_path, "table_name": table_name},
                    })
            except Exception as exc:
                issues.append({
                    "severity": "warning",
                    "code": "preview_source_list_failed",
                    "message": f"读取 SQLite 表列表失败：{exc}",
                })
        return {
            "ok": not issues,
            "sources": items,
            "issues": issues,
        }

    def load_preview_source(self, source, *, current_headers=None, current_rows=None, preview_headers=None, preview_rows=None):
        source = copy.deepcopy(source or {})
        kind = source.get("type")
        table_role = source.get("table_role")
        if kind == "memory" and table_role == "input":
            return {
                "ok": True,
                "source": source,
                "table": {
                    "headers": list(current_headers or []),
                    "rows": [list(row) for row in (current_rows or [])],
                },
                "title": "输入表格",
                "message": "已切换到输入表格。",
            }
        if kind == "memory" and table_role == "preview":
            headers = list(preview_headers or [])
            rows = [list(row) for row in (preview_rows or [])]
            if not headers and not rows:
                return {
                    "ok": False,
                    "source": source,
                    "issues": [{
                        "severity": "warning",
                        "code": "preview_table_missing",
                        "message": "还没有预览结果。",
                    }],
                    "message": "暂无预览结果",
                }
            return {
                "ok": True,
                "source": source,
                "table": {"headers": headers, "rows": rows},
                "title": "Headless 预览结果",
                "message": "已切换到预览结果。",
            }
        if kind == "sqlite":
            loaded = self.engine.load_table(
                db_path=source.get("db_path"),
                table_name=source.get("table_name"),
            )
            if not loaded.get("ok"):
                return loaded
            table = loaded.get("table") or {}
            table_name = source.get("table_name", "")
            return {
                "ok": True,
                "source": source,
                "table": {
                    "headers": list(table.get("headers") or []),
                    "rows": [list(row) for row in (table.get("rows") or [])],
                },
                "title": f"SQLite：{table_name}",
                "message": f"已读取 SQLite 表：{table_name}",
            }
        return {
            "ok": False,
            "source": source,
            "issues": [{
                "severity": "error",
                "code": "unsupported_preview_source",
                "message": f"不支持的预览来源：{kind or 'unknown'}",
            }],
            "message": "读取预览来源失败",
        }

    def build_run_options(self, plan=None, *, stop_index=None, execute_actions=False, output_settings=None, confirmed=False):
        plan_copy = copy.deepcopy(plan or {})
        settings = OutputSettings.from_payload(output_settings or {})
        return {
            "ok": True,
            "plan": plan_copy,
            "stop_index": stop_index,
            "execute_actions": bool(execute_actions),
            "confirmed": bool(confirmed),
            "output_settings": settings.to_dict(),
            "table_access_policy": (plan_copy or {}).get("table_access_policy", "audit"),
        }

    def validate_workflow_request(self, plan=None, *, execute_actions=False, stop_index=None, output_settings=None, confirmed=False):
        plan_copy = copy.deepcopy(plan or {})
        settings = OutputSettings.from_payload(output_settings or {})
        validation = self.engine.validate_plan(plan_copy, stop_index=stop_index)
        jump_validation = self.engine.validate_jumps(plan_copy)
        access_precheck = self.engine.precheck_access(
            plan_copy,
            execute_actions=execute_actions,
            stop_index=stop_index,
            db_path=settings.db_path,
            output_mode=settings.mode,
            output_table=settings.target,
            table_access_policy=(plan_copy or {}).get("table_access_policy", "audit"),
            confirmed=confirmed,
        )
        ok = (
            bool(validation.get("ok"))
            and bool(jump_validation.get("ok"))
            and bool(access_precheck.get("can_continue", True))
        )
        return {
            "ok": ok,
            "validation": validation,
            "jump_validation": jump_validation,
            "access_precheck": access_precheck,
            "output_settings": settings.to_dict(),
        }

    def start_workflow_job(self, job_action, plan, *, input_table=None, stop_index=None, execute_actions=False, output_settings=None, confirmed=False, **options):
        request = self.build_run_options(
            plan,
            stop_index=stop_index,
            execute_actions=execute_actions,
            output_settings=output_settings,
            confirmed=confirmed,
        )
        payload = {
            "job_action": job_action,
            "plan": request["plan"],
            "input_data": copy.deepcopy(input_table),
            "stop_index": request["stop_index"],
            "execute_actions": request["execute_actions"],
            "output_settings": request["output_settings"],
            "confirmed": request["confirmed"],
        }
        payload.update({key: value for key, value in options.items() if value is not None})
        return self.engine.start_job(job_action, payload)

    def finalize_job_result(self, status, *, job_action="", logs=None, output_settings=None):
        status = copy.deepcopy(status or {})
        result = copy.deepcopy(status.get("result") or {})
        table = result.get("table") or {}
        headers = list(table.get("headers") or [])
        rows = [list(row) for row in (table.get("rows") or [])]
        merged_logs = list(result.get("logs") or logs or [])
        payload = {
            "ok": status.get("status") != "failed",
            "status": status.get("status") or "unknown",
            "job_action": job_action,
            "table": {"headers": headers, "rows": rows},
            "logs": merged_logs,
            "steps": int(result.get("steps", 0) or 0),
            "cancelled": bool(result.get("cancelled")),
            "message": status.get("message") or "",
        }
        if status.get("status") == "failed":
            error = status.get("error") or {}
            payload["ok"] = False
            payload["error"] = error
            payload["display_message"] = error.get("message") or status.get("message") or "后台任务失败。"
            return payload
        if job_action == "run_plan" and (headers or rows):
            output = self.engine.apply_output(
                headers=headers,
                rows=rows,
                logs=merged_logs,
                settings=output_settings,
            )
            output_table = output.get("table") or {}
            payload["table"] = {
                "headers": list(output_table.get("headers") or headers),
                "rows": [list(row) for row in (output_table.get("rows") or rows)],
            }
            payload["output"] = output
            payload["ok"] = bool(output.get("ok"))
            payload["display_message"] = output.get("message") or ("输出完成。" if output.get("ok") else "执行完成，但输出未落地")
            return payload
        payload["display_message"] = status.get("message") or "任务完成。"
        return payload
