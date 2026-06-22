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

    def build_workflow_panel_state(
        self,
        *,
        plan=None,
        current_headers=None,
        current_rows=None,
        selected_index=None,
        preview_headers=None,
        preview_rows=None,
        current_plan_path=None,
        include_unsupported=True,
    ):
        plan = copy.deepcopy(plan or {})
        current_headers = list(current_headers or [])
        current_rows = [list(row) for row in (current_rows or [])]
        preview_headers = list(preview_headers or [])
        preview_rows = [list(row) for row in (preview_rows or [])]
        catalog = self.list_node_ui_catalog(
            include_unsupported=include_unsupported,
            preview_headers=current_headers,
        ).get("catalog") or {}
        schemas = catalog.get("items") or []
        schema_by_id = {item.get("node_type_id"): item for item in schemas}
        nodes = plan.get("nodes", []) or []
        node_items = []
        for index, node in enumerate(nodes):
            node_type_id = str(node.get("node_type_id") or node.get("type") or "")
            schema = schema_by_id.get(node_type_id, {})
            display = schema.get("display_name") or node.get("type") or node_type_id
            name = node.get("name") or display or "未命名节点"
            enabled = bool(node.get("enabled", True))
            mark = "√" if enabled else "×"
            node_items.append({
                "index": index,
                "node_type_id": node_type_id,
                "display_name": display,
                "name": name,
                "enabled": enabled,
                "summary_text": f"[{mark}] {index + 1}. {display}：{name}\n{node_type_id}",
            })

        selected_node = None
        selected_schema = {}
        if selected_index is not None and 0 <= int(selected_index) < len(nodes):
            selected_node = copy.deepcopy(nodes[int(selected_index)])
            selected_schema = schema_by_id.get(str(selected_node.get("node_type_id") or selected_node.get("type") or ""), {})

        action_state = self.describe_workflow_actions(
            plan=plan,
            selected_indexes=[int(selected_index)] if selected_index is not None and 0 <= int(selected_index) < len(nodes) else [],
            is_running=False,
        )

        return {
            "ok": True,
            "catalog": catalog,
            "schemas": schemas,
            "selected_index": selected_index,
            "selected_node": selected_node,
            "selected_schema": selected_schema,
            "node_items": node_items,
            "actions": action_state.get("actions") or {},
            "input_summary": f"当前输入：{len(current_rows)} 行 x {len(current_headers)} 列",
            "plan_status": self.plan_status_text(plan, current_plan_path=current_plan_path),
            "table_state": {
                "input": {"headers": current_headers, "rows": current_rows},
                "preview": {"headers": preview_headers, "rows": preview_rows},
            },
        }

    def describe_workflow_actions(self, *, plan=None, selected_indexes=None, is_running=False):
        plan = copy.deepcopy(plan or {})
        nodes = plan.get("nodes", []) or []
        selected = sorted({int(index) for index in (selected_indexes or []) if 0 <= int(index) < len(nodes)})
        selected_index = selected[0] if len(selected) == 1 else None
        has_nodes = bool(nodes)
        has_selection = bool(selected)

        actions = {
            "add_node": {"enabled": not is_running},
            "refresh_catalog": {"enabled": not is_running},
            "delete_nodes": {"enabled": has_selection and not is_running},
            "move_node_up": {"enabled": selected_index is not None and selected_index > 0 and not is_running},
            "move_node_down": {"enabled": selected_index is not None and selected_index < len(nodes) - 1 and not is_running},
            "toggle_node_enabled": {"enabled": selected_index is not None and not is_running},
            "duplicate_node": {"enabled": selected_index is not None and not is_running},
            "clear_nodes": {"enabled": has_nodes and not is_running},
            "preview_selected": {"enabled": selected_index is not None and not is_running},
            "preview_full": {"enabled": has_nodes and not is_running},
            "execute_plan": {"enabled": has_nodes and not is_running},
            "validate_plan": {"enabled": has_nodes and not is_running},
            "apply_node_config": {"enabled": selected_index is not None and not is_running},
            "cancel_job": {"enabled": bool(is_running)},
        }
        return {
            "ok": True,
            "actions": actions,
        }

    def build_job_progress_state(self, *, current_job_id="", title="", event=None, final=None, running=False):
        current_job_id = str(current_job_id or "")
        title = str(title or "任务")
        workflow_label = "等待执行"
        node_label = "节点进度"
        workflow_value = 0
        node_value = 0

        if running and current_job_id:
            workflow_label = f"任务已启动：{current_job_id}"
            node_label = "节点进度：等待事件"

        event = copy.deepcopy(event or {})
        event_type = event.get("type", "")
        if event_type == "node_start":
            node_index = int(event.get("node_index", 0) or 0)
            node_total = max(1, int(event.get("node_total", 1) or 1))
            workflow_value = int(node_index * 100 / node_total)
            workflow_label = f"总进度：节点 {node_index + 1} / {node_total}"
            node_label = f"当前节点：{event.get('node_name', '')} - 开始"
        elif event_type == "node_progress":
            current = event.get("current")
            total = event.get("total")
            if total:
                node_value = int(float(current or 0) * 100 / max(1.0, float(total)))
            node_label = event.get("message") or "当前节点：处理中"
        elif event_type == "node_done":
            node_index = int(event.get("node_index", 0) or 0)
            node_total = max(1, int(event.get("node_total", 1) or 1))
            workflow_value = int((node_index + 1) * 100 / node_total)
            node_value = 100
            workflow_label = f"总进度：节点 {node_index + 1} / {node_total}"
            node_label = f"当前节点：{event.get('node_name', '')} - 完成"
        elif event_type == "job_cancel_requested":
            node_label = "当前节点：正在取消"

        final = copy.deepcopy(final or {})
        if final:
            rows = list((final.get("table") or {}).get("rows") or [])
            headers = list((final.get("table") or {}).get("headers") or [])
            workflow_value = 100
            node_value = 100
            workflow_label = f"{title}完成：{len(rows)} 行 x {len(headers)} 列"
            node_label = f"执行步数：{final.get('steps', 0)}"

        return {
            "ok": True,
            "progress": {
                "workflow_label": workflow_label,
                "workflow_value": workflow_value,
                "node_label": node_label,
                "node_value": node_value,
            },
        }

    def describe_node_detail(self, node_type_id, *, preview_headers=None):
        schema = self.engine.get_node_ui_schema(node_type_id, preview_headers=preview_headers)
        return {
            "ok": True,
            "schema": schema,
        }

    def plan_status_text(self, plan=None, *, current_plan_path=None):
        plan = plan or {}
        name = plan.get("plan_name", "未命名计划")
        path = str(current_plan_path) if current_plan_path else "未保存"
        return f"{name} · {path}"

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

    def describe_output_form(self, payload=None, **fallbacks):
        settings = OutputSettings.from_payload(payload, **fallbacks)
        modes = self.engine.list_output_modes().get("modes", []) or []
        mode_choices = [item.get("label") or item.get("mode") for item in modes]
        mode_meta = {
            str(item.get("label") or item.get("mode") or ""): dict(item)
            for item in modes
        }
        fields = [
            {
                "key": "mode",
                "label": "输出方式",
                "type": "select",
                "choices": mode_choices,
                "required": True,
            },
            {
                "key": "target",
                "label": "输出表名",
                "type": "text",
                "visible_when": {
                    "field": "mode",
                    "in": [
                        item.get("label") or item.get("mode")
                        for item in modes
                        if item.get("requires_target")
                    ],
                },
            },
            {
                "key": "db_path",
                "label": "数据库路径",
                "type": "text",
                "visible_when": {
                    "field": "mode",
                    "in": [
                        item.get("label") or item.get("mode")
                        for item in modes
                        if item.get("requires_db_path")
                    ],
                },
            },
            {
                "key": "path",
                "label": "输出文件",
                "type": "text",
                "visible_when": {
                    "field": "mode",
                    "in": [
                        item.get("label") or item.get("mode")
                        for item in modes
                        if item.get("requires_path")
                    ],
                },
            },
            {
                "key": "backup_before_overwrite",
                "label": "覆盖前自动备份旧表",
                "type": "bool",
                "visible_when": {
                    "field": "mode",
                    "equals": "覆盖当前表",
                },
            },
        ]
        return {
            "ok": True,
            "settings": settings.to_dict(),
            "form": {
                "schema_version": "1.0",
                "fields": fields,
            },
            "mode_meta": mode_meta,
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
