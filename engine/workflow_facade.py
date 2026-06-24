# -*- coding: utf-8 -*-
"""Unified backend facade for UI-facing workflow operations."""

from __future__ import annotations

import copy

from engine.headless import HeadlessWorkflowEngine
from engine.output_service import OutputSettings
from engine.plan_templates import PlanTemplateService
from engine.table_io import load_table_file
from workflow.plan_commands import apply_plan_command as apply_workflow_plan_command
from workflow.node_ui_schema import (
    build_field_help_payload,
    build_node_detail_payload,
    build_node_ui_catalog_from_schemas,
    normalize_node_type_id,
    plan_reference_choices,
    runtime_reference_choices,
)


def _plugin_config_capability_labels(capabilities):
    capabilities = capabilities or {}
    labels = []
    mapping = [
        ("schema_config", "schema配置"),
        ("dynamic_options", "动态候选"),
        ("config_description", "配置描述"),
        ("config_patch", "结构化patch"),
        ("config_effect_preview", "配置效果预览"),
        ("legacy_custom_config", "旧版窗口fallback"),
        ("external_only", "仅独立环境"),
    ]
    for key, label in mapping:
        if capabilities.get(key):
            labels.append(label)
    return labels


class WorkflowFacade:
    """Collect UI-neutral workflow operations for desktop and worker clients."""

    def __init__(self, engine=None, *, node_id_factory=None):
        self.engine = engine or HeadlessWorkflowEngine()
        self.node_id_factory = node_id_factory or getattr(self.engine, "node_id_factory", None)
        self.plan_templates = PlanTemplateService(
            node_id_factory=self.node_id_factory
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

    def describe_file_action(self, action, *, current_plan_path=None, plan_dir=None):
        action = str(action or "")
        plan_dir_value = str(plan_dir or "")
        current_plan_path_value = str(current_plan_path or "")
        actions = {
            "import_table": {
                "dialog": "open_file",
                "title": "导入输入表格",
                "initial_path": "",
                "filters": [
                    {"label": "表格文件", "pattern": "*.json *.csv *.tsv *.tab"},
                    {"label": "JSON 文件", "pattern": "*.json"},
                    {"label": "CSV 文件", "pattern": "*.csv"},
                    {"label": "TSV 文件", "pattern": "*.tsv *.tab"},
                    {"label": "所有文件", "pattern": "*.*"},
                ],
            },
            "open_plan": {
                "dialog": "open_file",
                "title": "打开 workflow_plan",
                "initial_path": plan_dir_value,
                "filters": [
                    {"label": "JSON 文件", "pattern": "*.json"},
                    {"label": "所有文件", "pattern": "*.*"},
                ],
            },
            "save_plan": {
                "dialog": "save_file",
                "title": "保存 workflow_plan",
                "initial_path": current_plan_path_value or (plan_dir_value + "\\工作流计划.json" if plan_dir_value else "工作流计划.json"),
                "filters": [
                    {"label": "JSON 文件", "pattern": "*.json"},
                    {"label": "所有文件", "pattern": "*.*"},
                ],
            },
        }
        payload = actions.get(action, {
            "dialog": "open_file",
            "title": "选择文件",
            "initial_path": "",
            "filters": [{"label": "所有文件", "pattern": "*.*"}],
        })
        return {
            "ok": True,
            "action": action,
            "file_dialog": payload,
        }

    def build_import_table_state(self, imported):
        imported = copy.deepcopy(imported or {})
        table = imported.get("table") or {}
        headers = list(table.get("headers") or [])
        rows = [list(row) for row in (table.get("rows") or [])]
        path = str(imported.get("path") or "")
        message = f"已导入输入表格：{path}" if path else "已导入输入表格。"
        return {
            "ok": True,
            "state": {
                "headers": headers,
                "rows": rows,
                "table_title": "输入表格",
                "status_message": message,
                "issue_message": message,
                "message_panel": self.build_message_panel_state(
                    mode="success",
                    title="导入输入表格",
                    body=message,
                ).get("panel") or {},
            },
        }

    def build_loaded_plan_state(self, loaded):
        loaded = copy.deepcopy(loaded or {})
        plan = copy.deepcopy(loaded.get("plan") or {})
        path = str(loaded.get("path") or "")
        warning = str(loaded.get("warning") or "")
        message = warning or (f"已打开计划：{path}" if path else "已打开计划。")
        input_source = copy.deepcopy(plan.get("input_source") or {})
        if not isinstance(input_source, dict):
            input_source = {}
        input_db_path = str(plan.get("input_db_path") or input_source.get("db_path") or "").strip()
        return {
            "ok": True,
            "state": {
                "plan": plan,
                "plan_path": path,
                "headers": list(plan.get("headers") or []),
                "rows": [list(row) for row in (plan.get("rows") or [])],
                "input_source": input_source,
                "input_db_path": input_db_path,
                "output_settings": OutputSettings.from_payload(plan).to_dict(),
                "status_message": f"已打开计划：{path}" if path else "已打开计划。",
                "issue_message": message,
                "message_panel": self.build_message_panel_state(
                    mode="warning" if warning else "info",
                    title="打开计划",
                    body=message,
                ).get("panel") or {},
            },
        }

    def build_saved_plan_state(self, saved, plan):
        saved = copy.deepcopy(saved or {})
        plan = copy.deepcopy(saved.get("plan") or plan or {})
        path = str(saved.get("path") or "")
        message = f"已保存：{path}" if path else "已保存计划。"
        return {
            "ok": True,
            "state": {
                "plan": plan,
                "plan_path": path,
                "status_message": message,
                "message_panel": self.build_message_panel_state(
                    mode="success",
                    title="保存计划",
                    body=message,
                ).get("panel") or {},
            },
        }

    def list_plan_templates(self, plan_dir):
        return self.plan_templates.list_templates(plan_dir)

    def build_template_list_state(self, listed, *, show_status=True):
        listed = copy.deepcopy(listed or {})
        templates = [item for item in (listed.get("templates") or []) if isinstance(item, dict)]
        count = len(templates)
        status_message = f"模板刷新完成：{count} 个。" if show_status else ""
        info_body = f"当前可用计划模板：{count} 个。"
        if count:
            info_body = info_body + "\n\n" + "\n".join(
                f"- {str(item.get('name') or item.get('path') or '')}" for item in templates
            )
        return {
            "ok": True,
            "state": {
                "templates": templates,
                "template_count": count,
                "status_message": status_message,
                "message_panel": self.build_message_panel_state(
                    mode="info",
                    title="计划模板",
                    info_body=info_body,
                    preferred_tab="info",
                ).get("panel") or {},
            },
        }

    def build_plugin_list_state(self, listed, *, show_status=True):
        listed = copy.deepcopy(listed or {})
        plugins = [item for item in (listed.get("plugins") or []) if isinstance(item, dict)]
        errors = [item for item in (listed.get("errors") or []) if isinstance(item, dict)]
        count = int(listed.get("count", len(plugins)) or 0)
        external_only_count = int(listed.get("external_only_count", 0) or 0)
        plugins_dir = str(listed.get("plugins_dir") or "")
        status_parts = [f"插件刷新完成：已注册 {count} 个插件"]
        if external_only_count:
            status_parts.append(f"仅独立环境 {external_only_count} 个")
        if errors:
            status_parts.append(f"扫描错误 {len(errors)} 个")
        status_message = "，".join(status_parts) + "。" if show_status else ""

        lines = [f"已注册插件：{count} 个。"]
        if plugins_dir:
            lines.append(f"插件目录：{plugins_dir}")
        if external_only_count:
            lines.append(f"仅独立环境插件：{external_only_count} 个。")
        if plugins:
            lines.append("")
            for item in plugins[:12]:
                name = str(item.get("name") or item.get("display_name") or item.get("plugin_id") or "")
                plugin_id = str(item.get("plugin_id") or "")
                load_status = str(item.get("load_status") or "")
                suffix = f" / {load_status}" if load_status else ""
                lines.append(f"- {name} ({plugin_id}){suffix}")
            if len(plugins) > 12:
                lines.append(f"- ... 其余 {len(plugins) - 12} 个插件")

        issues = []
        for error in errors:
            file_name = str(error.get("file") or error.get("path") or "插件")
            message = str(error.get("error") or "插件扫描失败")
            issues.append({
                "severity": "warning",
                "code": "plugin_scan_failed",
                "path": str(error.get("path") or ""),
                "message": f"{file_name}：{message}",
            })

        return {
            "ok": not issues,
            "state": {
                "plugins": plugins,
                "errors": errors,
                "issues": issues,
                "plugin_count": count,
                "external_only_count": external_only_count,
                "plugins_dir": plugins_dir,
                "status_message": status_message,
                "message_panel": self.build_message_panel_state(
                    mode="warning" if issues else "info",
                    title="插件",
                    info_body="\n".join(lines),
                    issues=issues,
                    preferred_tab="issues" if issues else "info",
                ).get("panel") or {},
            },
        }

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
        engine_apply = getattr(self.engine, "apply_plan_command", None)
        if callable(engine_apply):
            return engine_apply(copy.deepcopy(plan), copy.deepcopy(command), **kwargs)
        return apply_workflow_plan_command(
            copy.deepcopy(plan),
            copy.deepcopy(command),
            node_id_factory=self.node_id_factory,
            **kwargs,
        )

    def describe_plan_command_feedback(self, result, *, success_status="", success_title="计划编辑", failure_status="计划编辑失败"):
        result = copy.deepcopy(result or {})
        issues = copy.deepcopy(result.get("issues") or [])
        if result.get("ok"):
            return self.build_user_feedback(
                level="success",
                code="plan_command_applied",
                title=str(success_title or "计划编辑"),
                status_message=str(success_status or "计划编辑已完成。"),
            )
        return self.build_user_feedback(
            level="warning",
            code="plan_command_failed",
            title=str(success_title or "计划编辑"),
            status_message=str(failure_status or "计划编辑失败"),
            issue_message=self.format_issues_text(issues),
            issues=issues,
        )

    def describe_plan_file_failure(self, *, action="", issues=None):
        action_text = str(action or "计划操作")
        issues = copy.deepcopy(issues or [])
        return self.build_user_feedback(
            level="warning",
            code="plan_file_invalid",
            title=action_text,
            status_message=f"{action_text}失败：计划模板校验未通过",
            issue_message=self.format_issues_text(issues),
            issues=issues,
        )

    def build_user_feedback(self, *,
        status_message="",
        issue_message="",
        issues=None,
        logs=None,
        level="info",
        code="",
        title="",
    ):
        issues = list(issues or [])
        logs = [str(item) for item in (logs or []) if str(item).strip()]
        panel = self.build_message_panel_state(
            mode=level,
            title=title,
            body=issue_message,
            issues=issues,
            logs=logs,
        ).get("panel") or {}
        feedback = {
            "ok": level not in {"error"},
            "feedback": {
                "level": str(level or "info"),
                "code": str(code or ""),
                "title": str(title or ""),
                "status_message": str(status_message or ""),
                "issue_message": str(issue_message or ""),
                "issues": issues,
                "logs": logs,
                "message_panel": panel,
            },
        }
        return feedback

    def build_message_panel_state(
        self,
        *,
        mode="info",
        title="",
        body="",
        info_body="",
        issue_body="",
        issues=None,
        logs=None,
        preferred_tab="",
    ):
        issues = copy.deepcopy(issues or [])
        logs = [str(item) for item in (logs or []) if str(item).strip()]
        body_text = str(body or "")
        if not body_text and issues:
            body_text = self.format_issues_text(issues)
        if not body_text and logs:
            body_text = "\n".join(logs)
        info_text = str(info_body or "").strip()
        issue_text = str(issue_body or "").strip()
        mode_text = str(mode or "info")
        if not issue_text and issues:
            issue_text = self.format_issues_text(issues)
        if not info_text and mode_text not in {"warning", "error"}:
            info_text = body_text
        if not issue_text and mode_text in {"warning", "error"}:
            issue_text = body_text
        preferred = str(preferred_tab or "").strip().lower()
        if preferred not in {"info", "issues", "logs"}:
            if issues:
                preferred = "issues"
            elif logs:
                preferred = "logs"
            else:
                preferred = "info"
        return {
            "ok": True,
            "panel": {
                "mode": mode_text,
                "title": str(title or ""),
                "body": body_text,
                "info_body": info_text,
                "issue_body": issue_text,
                "issues": issues,
                "logs": logs,
                "preferred_tab": preferred,
            },
        }

    def describe_selection_feedback(self, *, selected_index=None, purpose=""):
        if selected_index is not None and int(selected_index) >= 0:
            return self.build_user_feedback()
        purpose = str(purpose or "操作")
        return self.build_user_feedback(
            level="warning",
            code="selection_required",
            status_message=f"{purpose}前需要先选择节点",
            issue_message="请先选择一个节点。",
            issues=[{
                "severity": "warning",
                "code": "selection_required",
                "message": "请先选择一个节点。",
            }],
        )

    def describe_picker_feedback(self, *, action_key="", field_key="", table_name="", table_field="", candidates=None, ref_kind=""):
        action_key = str(action_key or "").strip()
        field_key = str(field_key or "").strip()
        table_name = str(table_name or "").strip()
        table_field = str(table_field or "").strip()
        ref_kind = str(ref_kind or "").strip()
        candidates = [str(item) for item in (candidates or []) if str(item).strip()]

        title = "字段选择"
        status_message = "当前没有可选项。"
        issue_message = status_message
        code = "picker_candidates_missing"

        if action_key == "pick_table_name":
            title = "数据表选择"
            status_message = "当前没有可选数据表。"
            issue_message = status_message
            code = "table_names_missing"
        elif action_key in {"pick_preview_header", "pick_preview_headers"}:
            title = "字段选择"
            status_message = "当前没有可选字段。"
            issue_message = status_message
            code = "preview_headers_missing"
        elif action_key in {"pick_table_field", "pick_table_fields"}:
            title = "表字段选择"
            if not table_name:
                label = table_field or "关联数据表"
                status_message = "请先选择关联数据表。"
                issue_message = f"字段 {field_key or label} 依赖数据表上下文，请先设置 {label}。"
                code = "table_context_required"
            else:
                status_message = f"数据表 {table_name} 暂无可选字段。"
                issue_message = status_message
                code = "table_columns_missing"
        elif action_key == "pick_plan_ref":
            title = "计划引用选择"
            label = "循环" if ref_kind == "loop_id" else "锚点" if ref_kind == "anchor_id" else "计划引用"
            status_message = f"当前计划没有可用{label}。"
            issue_message = f"字段 {field_key or label} 依赖当前计划中的{label}，请先添加对应节点或填写自定义值。"
            code = "plan_refs_missing"
        elif action_key == "pick_runtime_ref":
            title = "运行时引用选择"
            label = "中转表" if ref_kind == "transit_table" else "中转名称" if ref_kind == "transit_name" else "运行时引用"
            status_message = f"当前计划没有可用{label}。"
            issue_message = f"字段 {field_key or label} 依赖前序节点产生的{label}，请先配置相关节点或填写自定义值。"
            code = "runtime_refs_missing"

        if candidates:
            return self.build_user_feedback()
        return self.build_user_feedback(
            level="warning",
            code=code,
            title=title,
            status_message=status_message,
            issue_message=issue_message,
            issues=[{
                "severity": "warning",
                "code": code,
                "message": issue_message,
                "field": field_key,
                "table_name": table_name,
                "table_field": table_field,
                "ref_kind": ref_kind,
                "action": action_key,
            }],
        )

    def describe_picker_context(self, *, plan=None, field_key="", action_key="", ref_kind="", options_source=None, table_names=None, table_columns=None, current_values=None):
        field_key = str(field_key or "").strip()
        action_key = str(action_key or "").strip()
        ref_kind = str(ref_kind or "").strip()
        options_source = dict(options_source or {})
        table_names = [str(item) for item in (table_names or []) if str(item).strip()]
        table_columns = {
            str(key): [str(item) for item in (values or []) if str(item).strip()]
            for key, values in dict(table_columns or {}).items()
            if str(key).strip()
        }
        current_values = dict(current_values or {})

        source_type = str(options_source.get("type") or "").strip()
        if not ref_kind:
            ref_kind = str(options_source.get("ref_kind") or "").strip()

        source = ""
        label = ""
        empty_code = "picker_candidates_missing"
        candidates = []
        dependency_field = ""
        dependency_value = ""

        if action_key == "pick_plan_ref" or source_type == "plan_refs":
            source = "plan_refs"
            candidates = plan_reference_choices(plan, ref_kind)
            if ref_kind == "loop_id":
                label = "循环"
            elif ref_kind == "anchor_id":
                label = "锚点"
            else:
                label = "计划引用"
            empty_code = "plan_refs_missing"
        elif action_key == "pick_runtime_ref" or source_type == "runtime_refs":
            source = "runtime_refs"
            candidates = runtime_reference_choices(plan, ref_kind)
            if ref_kind == "transit_table":
                label = "中转表"
            elif ref_kind == "transit_name":
                label = "中转名称"
            else:
                label = "运行时引用"
            empty_code = "runtime_refs_missing"
        elif action_key in {"pick_table_name", "pick_table_names"} or source_type == "table_names":
            source = "table_names"
            label = "数据表"
            empty_code = "table_names_missing"
            candidates = list(table_names)
        elif action_key in {"pick_table_field", "pick_table_fields"} or source_type == "table_columns":
            source = "table_columns"
            label = "表字段"
            empty_code = "table_columns_missing"
            dependency_field = str(options_source.get("table_field") or "").strip()
            if dependency_field:
                dependency_value = str(current_values.get(dependency_field) or "").strip()
            if dependency_value:
                candidates = list(table_columns.get(dependency_value, []) or [])
        elif source_type == "field_values":
            dependency_field = str(options_source.get("field") or "").strip()
            dependency_value = current_values.get(dependency_field)
            if isinstance(dependency_value, (list, tuple, set)):
                candidates = [str(item) for item in dependency_value if str(item).strip()]
            elif str(dependency_value or "").strip():
                candidates = [str(dependency_value)]
            if str(options_source.get("value_kind") or "") == "table_names":
                source = "field_values"
                label = "数据表"
                empty_code = "table_names_missing"
                allowed = set(table_names)
                candidates = [item for item in candidates if item in allowed]
        elif source_type == "plugin_input_tables":
            source = "plugin_input_tables"
            label = "插件输入表"
            empty_code = "plugin_input_tables_missing"
            aliases = ["当前表", "workflow_current", "primary"]
            specs = current_values.get("input_tables") or []
            if isinstance(specs, list):
                for spec in specs:
                    if not isinstance(spec, dict):
                        continue
                    alias = str(spec.get("alias") or spec.get("name") or spec.get("table_alias") or "").strip()
                    if alias:
                        aliases.append(alias)
            candidates = aliases
        elif source_type == "plugin_dynamic_choices":
            source = "plugin_dynamic_choices"
            label = "插件动态选项"
            empty_code = "plugin_dynamic_choices_missing"
            candidates = list(options_source.get("choices") or [])

        candidates = [str(item) for item in (candidates or []) if str(item).strip()]
        return {
            "ok": True,
            "picker_context": {
                "field_key": field_key,
                "action_key": action_key,
                "source": source,
                "ref_kind": ref_kind,
                "label": label,
                "candidates": candidates,
                "candidate_count": len(candidates),
                "empty_code": empty_code,
                "table_field": dependency_field,
                "table_name": dependency_value,
            },
        }

    def describe_job_run_conflict(self, *, current_job_id=""):
        job_id = str(current_job_id or "")
        return self.build_user_feedback(
            level="warning",
            code="job_already_running",
            status_message="后台任务运行中",
            issue_message="当前已有后台任务运行，请等待完成或先取消。",
            logs=[f"当前任务：{job_id}"] if job_id else [],
            issues=[{
                "severity": "warning",
                "code": "job_already_running",
                "message": "当前已有后台任务运行，请等待完成或先取消。",
            }],
        )

    def describe_job_start_failure(self, *, status_prefix="任务", error=None):
        message = str(error or "任务启动失败")
        prefix = str(status_prefix or "任务")
        return self.build_user_feedback(
            level="error",
            code="job_start_failed",
            status_message=f"{prefix}启动失败",
            issue_message=message,
            issues=[{
                "severity": "error",
                "code": "job_start_failed",
                "message": message,
            }],
        )

    def describe_job_started(self, *, status_prefix="任务"):
        prefix = str(status_prefix or "任务")
        return {
            "ok": True,
            "status_message": f"{prefix}已启动",
            "message_panel": self.build_message_panel_state(
                mode="info",
                title=prefix,
                body=f"{prefix}已启动。",
            ).get("panel") or {},
        }

    def describe_job_poll_failure(self, *, error=None):
        message = str(error or "后台任务状态读取失败")
        return {
            "ok": False,
            "status_message": "后台任务状态读取失败",
            "message_panel": self.build_message_panel_state(
                mode="error",
                title="后台任务状态读取失败",
                body=message,
            ).get("panel") or {},
        }

    def describe_job_cancel_failure(self, *, error=None):
        message = str(error or "取消任务失败")
        return {
            "ok": False,
            "status_message": "取消任务失败",
            "message_panel": self.build_message_panel_state(
                mode="error",
                title="取消任务失败",
                body=message,
            ).get("panel") or {},
        }

    def describe_confirmation_prompt(self, *, action="", plan=None, output_settings=None, access_precheck=None):
        action = str(action or "")
        plan = copy.deepcopy(plan or {})
        output_settings = OutputSettings.from_payload(output_settings or {}).to_dict()
        nodes = plan.get("nodes", []) or []

        if action == "clear_nodes":
            node_count = len(nodes)
            return {
                "ok": True,
                "prompt": {
                    "required": node_count > 0,
                    "kind": "confirm",
                    "code": "confirm_clear_nodes",
                    "title": "确认清空节点",
                    "message": f"当前计划共有 {node_count} 个节点，确认要全部清空吗？" if node_count else "当前没有节点可清空。",
                    "details": [
                        "该操作只影响当前工作流节点列表。",
                        "输入表格与预览结果不会被删除。",
                    ],
                    "confirm_label": "清空节点",
                    "cancel_label": "取消",
                    "severity": "warning",
                },
            }

        if action == "run_plan":
            access_precheck = copy.deepcopy(access_precheck or {})
            issues = access_precheck.get("issues", []) or []
            summary = str(access_precheck.get("summary") or "")
            mode = str(output_settings.get("mode") or "输出到主界面预览区")
            requires_confirm = bool(issues) or mode == "覆盖当前表"
            details = []
            if summary:
                details.append(summary)
            if mode == "覆盖当前表":
                details.append("将直接写回当前表，建议确认目标表和备份设置。")
            if output_settings.get("backup_before_overwrite"):
                details.append("已启用覆盖前自动备份旧表。")
            details.extend([
                issue.get("message", "")
                for issue in issues
                if str(issue.get("message", "")).strip()
            ])
            return {
                "ok": True,
                "prompt": {
                    "required": requires_confirm,
                    "kind": "confirm",
                    "code": "confirm_run_plan",
                    "title": "确认执行计划",
                    "message": "执行计划会按当前输出设置落地结果，确认继续吗？" if requires_confirm else "",
                    "details": details,
                    "confirm_label": "继续执行",
                    "cancel_label": "取消",
                    "severity": "warning" if issues or mode == "覆盖当前表" else "info",
                },
            }

        return {
            "ok": True,
            "prompt": {
                "required": False,
                "kind": "confirm",
                "code": "",
                "title": "",
                "message": "",
                "details": [],
                "confirm_label": "确定",
                "cancel_label": "取消",
                "severity": "info",
            },
        }

    def describe_validation_feedback(self, combined):
        combined = copy.deepcopy(combined or {})
        validation = combined.get("validation") or {}
        jump_validation = combined.get("jump_validation") or {}
        access_precheck = combined.get("access_precheck") or {}
        sections = []
        text = self.format_validation_text(validation)
        sections.append({
            "title": "基础校验",
            "body": text,
            "issues": copy.deepcopy(validation.get("issues", []) or []),
        })
        jump_issues = jump_validation.get("issues", []) or []
        if jump_issues:
            text = text + "\n\n跳转校验：\n" + self.format_issues_text(jump_issues)
            sections.append({
                "title": "跳转校验",
                "body": self.format_issues_text(jump_issues),
                "summary": str(jump_validation.get("summary") or ""),
                "issues": copy.deepcopy(jump_issues),
            })
        access_issues = access_precheck.get("issues", []) or []
        if access_issues:
            access_body = (
                str(access_precheck.get("summary", "") or "")
                + "\n"
                + self.format_issues_text(access_issues)
            ).strip()
            text = (
                text
                + "\n\n权限预检：\n"
                + str(access_precheck.get("summary", "") or "")
                + "\n"
                + self.format_issues_text(access_issues)
            )
            sections.append({
                "title": "权限预检",
                "body": access_body,
                "summary": str(access_precheck.get("summary") or ""),
                "issues": copy.deepcopy(access_issues),
            })
        if not combined.get("ok"):
            status = "校验发现问题"
            level = "warning"
        elif jump_issues or access_issues:
            status = "校验发现提示"
            level = "info"
        else:
            status = "校验通过"
            level = "success"
        feedback = self.build_user_feedback(
            level=level,
            code="workflow_validation",
            status_message=status,
            issue_message=text,
            issues=(validation.get("issues", []) or []) + jump_issues + access_issues,
            title="计划校验",
        )
        payload = feedback.get("feedback") or {}
        payload["sections"] = sections
        payload["summary_lines"] = [
            str(item)
            for item in [status, jump_validation.get("summary"), access_precheck.get("summary")]
            if str(item or "").strip()
        ]
        info_blocks = []
        issue_blocks = []
        for section in sections:
            section_title = str(section.get("title") or "").strip()
            section_body = str(section.get("body") or "").strip()
            block = "\n".join(item for item in [section_title, section_body] if item)
            if not block:
                continue
            if section.get("issues"):
                issue_blocks.append(block)
            else:
                info_blocks.append(block)
        info_message = "\n\n".join(info_blocks)
        if payload["summary_lines"]:
            info_message = "\n".join(payload["summary_lines"]) + (("\n\n" + info_message) if info_message else "")
        issue_message = "\n\n".join(issue_blocks) if issue_blocks else (text if level in {"warning", "error"} else "")
        payload["message_panel"] = self.build_message_panel_state(
            mode=level,
            title=str(payload.get("title") or ""),
            body=issue_message or info_message,
            info_body=info_message,
            issue_body=issue_message,
            issues=payload.get("issues") or [],
            logs=payload.get("logs") or [],
            preferred_tab="issues" if issue_blocks else "info",
        ).get("panel") or {}
        return feedback

    def format_issues_text(self, issues):
        issues = issues or []
        if not issues:
            return "无问题。"
        lines = []
        for issue in issues:
            severity = issue.get("severity", "")
            code = issue.get("code", "")
            path = issue.get("path", "")
            message = issue.get("message", "")
            lines.append(f"[{severity}] {code} {path}".strip())
            if message:
                lines.append(message)
        return "\n".join(lines)

    def format_validation_text(self, validation):
        validation = validation or {}
        lines = [
            "OK: " + ("true" if validation.get("ok") else "false"),
            f"节点数: {validation.get('node_count', 0)}",
        ]
        issues = validation.get("issues", []) or []
        if not issues:
            lines.append("无校验问题。")
            return "\n".join(lines)
        lines.append("")
        for issue in issues:
            node_index = issue.get("node_index")
            code = issue.get("code", "")
            severity = issue.get("severity", "")
            node_type_id = issue.get("node_type_id", "")
            message = issue.get("message", "")
            lines.append(f"[{severity}] #{node_index} {code} {node_type_id}")
            lines.append(message)
        return "\n".join(lines)

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
        table_names=None,
        table_columns=None,
    ):
        plan = copy.deepcopy(plan or {})
        current_headers = list(current_headers or [])
        current_rows = [list(row) for row in (current_rows or [])]
        preview_headers = list(preview_headers or [])
        preview_rows = [list(row) for row in (preview_rows or [])]
        catalog = self.list_node_ui_catalog(
            include_unsupported=include_unsupported,
            preview_headers=current_headers,
            table_names=table_names,
            table_columns=table_columns,
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
            "refresh_plugins": {"enabled": not is_running},
            "legacy_plugin_config": {"enabled": selected_index is not None and not is_running},
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

    def describe_node_detail(self, node_type_id, *, preview_headers=None, table_names=None, table_columns=None):
        schema = self.engine.get_node_ui_schema(
            node_type_id,
            preview_headers=preview_headers,
            table_names=table_names,
            table_columns=table_columns,
        )
        detail = self._build_schema_node_detail(node_type_id, schema)
        return {
            "ok": True,
            "schema": schema,
            "detail": detail,
        }

    def describe_node_config_context(
        self,
        node_type_id="",
        *,
        node=None,
        config=None,
        preview_headers=None,
        table_names=None,
        table_columns=None,
        transit_context=None,
    ):
        node = copy.deepcopy(node or {}) if isinstance(node, dict) else {}
        if not node_type_id and node:
            node_type_id = node.get("node_type_id") or node.get("type") or ""
        config_source = config
        if config_source is None and node:
            config_source = node.get("config")
        schema = self.engine.get_node_ui_schema(
            node_type_id,
            preview_headers=preview_headers,
            table_names=table_names,
            table_columns=table_columns,
        )
        fields = []
        help_sections = []
        for group in (schema.get("form") or {}).get("groups", []):
            for field in group.get("fields") or []:
                help_payload = build_field_help_payload(field.get("key"), field)
                field_payload = copy.deepcopy(field)
                field_payload["help_payload"] = help_payload
                fields.append(field_payload)
                section_lines = [
                    str(item) for item in (help_payload.get("sections") or [])
                    if isinstance(item, dict)
                ]
                if section_lines:
                    help_sections.append({
                        "key": str(field.get("key") or ""),
                        "label": str(field.get("label") or field.get("key") or ""),
                        "sections": copy.deepcopy(help_payload.get("sections") or []),
                    })
        shared_config_context = {}
        if normalize_node_type_id(node_type_id) == "core.filter":
            from workflow.filter_config_helpers import describe_filter_config_context

            if not isinstance(config_source, dict):
                config_source = schema.get("default_config") or {}
            shared_config_context = describe_filter_config_context(
                config_source,
                preview_headers,
                table_names=table_names,
                table_columns=table_columns,
                transit_context=transit_context,
            )
        shared_config_sections = self._shared_config_context_sections(shared_config_context)
        return {
            "ok": True,
            "schema": schema,
            "fields": fields,
            "help_sections": help_sections,
            "warning_items": copy.deepcopy(schema.get("warning_items") or []),
            "shared_config_context": shared_config_context,
            "shared_config_sections": shared_config_sections,
        }

    def _shared_config_context_sections(self, shared_config_context):
        context = shared_config_context if isinstance(shared_config_context, dict) else {}
        if not context:
            return []
        schema_version = str(context.get("schema_version") or "").strip()
        if schema_version == "filter_config_context.v1":
            lines = []
            selected_tables = [str(item) for item in (context.get("selected_tables") or []) if str(item).strip()]
            if selected_tables:
                lines.append("已选表：" + "、".join(selected_tables))
            available_fields = [str(item) for item in (context.get("available_fields") or []) if str(item).strip()]
            lines.append(f"可用字段：{len(available_fields)} 个")
            output_text = str(context.get("output_text") or "").strip()
            if output_text:
                lines.append(output_text)
            risk_text = str((context.get("risk_state") or {}).get("text") or "").strip()
            if risk_text:
                lines.append(risk_text)
            return [{
                "title": "共享配置状态",
                "source": schema_version,
                "lines": lines,
            }]
        protocol = str(context.get("protocol_family") or "").strip()
        lines = []
        if schema_version:
            lines.append(f"协议版本：{schema_version}")
        if protocol:
            lines.append(f"协议族：{protocol}")
        return [{"title": "共享配置状态", "source": schema_version, "lines": lines}] if lines else []

    def plan_status_text(self, plan=None, *, current_plan_path=None):
        plan = plan or {}
        name = plan.get("plan_name", "未命名计划")
        path = str(current_plan_path) if current_plan_path else "未保存"
        return f"{name} · {path}"

    def list_node_ui_catalog(self, *, include_unsupported=True, preview_headers=None, table_names=None, table_columns=None):
        schemas = self.engine.list_node_ui_schemas(
            include_unsupported=include_unsupported,
            preview_headers=preview_headers,
            table_names=table_names,
            table_columns=table_columns,
        )
        catalog = build_node_ui_catalog_from_schemas(schemas)
        return {
            "ok": True,
            "catalog": catalog,
        }

    def _build_schema_node_detail(self, node_type_id, schema):
        schema = copy.deepcopy(schema or {})
        detail = build_node_detail_payload(
            node_type_id,
            display_name=schema.get("display_name", ""),
            category=schema.get("category", ""),
            supported_headless=((schema.get("capabilities") or {}).get("headless_preview")),
        )
        for key in ["summary", "description", "badges", "warnings", "risk"]:
            if key in schema:
                detail[key] = copy.deepcopy(schema.get(key))

        sections = []
        description = str(schema.get("description") or schema.get("summary") or "").strip()
        if description:
            sections.append({"title": "说明", "lines": [description]})
        warnings = [str(item) for item in (schema.get("warnings") or []) if str(item).strip()]
        if warnings:
            sections.append({"title": "注意", "lines": warnings})
        config_lines = self._schema_config_summary(schema)
        if config_lines:
            sections.append({"title": "配置项", "lines": config_lines})
        plugin = schema.get("plugin") if isinstance(schema.get("plugin"), dict) else {}
        plugin_lines = self._plugin_detail_lines(plugin, schema)
        if plugin_lines:
            sections.append({"title": "插件", "lines": plugin_lines})
        if sections:
            detail["sections"] = sections
        return detail

    def _schema_config_summary(self, schema):
        lines = []
        for group in (schema.get("form") or {}).get("groups", []):
            fields = group.get("fields") or []
            labels = []
            for field in fields:
                if not isinstance(field, dict):
                    continue
                label = str(field.get("label") or field.get("key") or "").strip()
                if not label:
                    continue
                tags = []
                validation = field.get("validation") or {}
                if field.get("required") or validation.get("required"):
                    tags.append("必填")
                if field.get("visible_when"):
                    tags.append("动态显示")
                if field.get("enabled_when"):
                    tags.append("动态启用")
                if (field.get("action") or {}).get("key"):
                    tags.append("可选取")
                labels.append(label + (f"({','.join(tags)})" if tags else ""))
            if labels:
                lines.append(f"{group.get('title', '参数')}：" + "、".join(labels[:6]))
        return lines

    def _plugin_detail_lines(self, plugin, schema):
        lines = []
        plugin_id = str(plugin.get("plugin_id") or "").strip()
        if plugin_id:
            lines.append(f"插件 ID：{plugin_id}")
        load_status = str(plugin.get("load_status") or "").strip()
        if load_status:
            lines.append(f"加载状态：{load_status}")
        run_modes = [str(item) for item in (plugin.get("available_run_modes") or []) if str(item).strip()]
        if run_modes:
            lines.append("可用运行环境：" + "、".join(run_modes))
        parameter_count = plugin.get("parameter_count")
        if parameter_count is not None:
            lines.append(f"声明参数：{parameter_count} 个")
        custom_window = plugin.get("custom_config_window") if isinstance(plugin.get("custom_config_window"), dict) else {}
        if custom_window.get("available"):
            lines.append("旧版设置窗口：可通过兼容入口打开。")
        capabilities = schema.get("capabilities") or {}
        capability_labels = _plugin_config_capability_labels(capabilities)
        if capability_labels:
            lines.append("配置能力：" + "、".join(capability_labels))
        if capabilities.get("plugin"):
            lines.append("插件节点可按普通工作流节点配置、预览和执行。")
        return lines

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
                "action": {
                    "key": "browse_output_db_path",
                    "label": "选择数据库",
                    "dialog": "save_file",
                    "title": "选择 SQLite 数据库",
                    "filters": [
                        {"label": "SQLite 文件", "pattern": "*.db *.sqlite *.sqlite3"},
                        {"label": "所有文件", "pattern": "*.*"},
                    ],
                },
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
                "action": {
                    "key": "browse_output_path",
                    "label": "选择输出文件",
                    "dialog": "save_file",
                    "title": "选择 xlsx 输出文件",
                    "filters": [
                        {"label": "Excel 文件", "pattern": "*.xlsx"},
                        {"label": "所有文件", "pattern": "*.*"},
                    ],
                },
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

    def build_output_panel_state(self, payload=None, **fallbacks):
        described = self.describe_output_form(payload, **fallbacks)
        settings = copy.deepcopy(described.get("settings") or {})
        fields = []
        visible_field_keys = []
        values = {
            "mode": settings.get("mode", ""),
            "target": settings.get("target", ""),
            "db_path": settings.get("db_path", ""),
            "path": settings.get("path", ""),
            "backup_before_overwrite": bool(settings.get("backup_before_overwrite", False)),
        }
        for field in (described.get("form") or {}).get("fields", []):
            visible = self._condition_matches(field.get("visible_when"), values)
            field_payload = copy.deepcopy(field)
            field_payload["visible"] = bool(visible)
            field_payload["value"] = values.get(field.get("key"))
            fields.append(field_payload)
            if visible:
                visible_field_keys.append(str(field.get("key") or ""))
        refresh_preview_sources = "db_path" in visible_field_keys
        return {
            "ok": True,
            "settings": settings,
            "fields": fields,
            "mode_meta": copy.deepcopy(described.get("mode_meta") or {}),
            "view_state": {
                "visible_field_keys": visible_field_keys,
                "refresh_preview_sources": refresh_preview_sources,
            },
            "message_panel": self.build_message_panel_state(
                mode="info",
                title="输出设置",
                info_body="当前输出方式已更新。",
                preferred_tab="info",
            ).get("panel") or {},
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

    def build_preview_panel_state(self, *, current_source=None, current_headers=None, current_rows=None, preview_headers=None, preview_rows=None, db_path=None):
        listed = self.list_preview_sources(
            current_headers=current_headers,
            current_rows=current_rows,
            preview_headers=preview_headers,
            preview_rows=preview_rows,
            db_path=db_path,
        )
        sources = copy.deepcopy(listed.get("sources") or [])
        selected_key = self._preview_source_key(current_source)
        if not selected_key and sources:
            selected_key = self._preview_source_key((sources[0].get("source") or {}))
        title = "表格预览"
        if current_source:
            for item in sources:
                if self._preview_source_key(item.get("source") or {}) == selected_key:
                    title = item.get("label") or title
                    break
        return {
            "ok": listed.get("ok", False),
            "sources": sources,
            "issues": copy.deepcopy(listed.get("issues") or []),
            "selected_key": selected_key,
            "title": title,
        }

    def apply_node_config_state(self, plan, *, index=None, node=None, preview_headers=None, table_names=None, table_columns=None):
        plan = copy.deepcopy(plan or {})
        node = copy.deepcopy(node or {})
        selected_index = None if index is None else int(index)
        if selected_index is None or selected_index < 0:
            return {
                "ok": False,
                "issues": [{
                    "severity": "warning",
                    "code": "selection_required",
                    "message": "请先选择一个节点。",
                }],
                "feedback": self.build_user_feedback(
                    level="warning",
                    code="selection_required",
                    title="节点配置",
                    status_message="应用节点配置前需要先选择节点",
                    issue_message="请先选择一个节点。",
                    issues=[{
                        "severity": "warning",
                        "code": "selection_required",
                        "message": "请先选择一个节点。",
                    }],
                ).get("feedback") or {},
            }
        if not isinstance(node, dict):
            raise ValueError("节点配置必须是 JSON object。")
        if not node.get("node_type_id") and not node.get("type"):
            raise ValueError("节点必须包含 node_type_id 或 legacy type。")

        validation = self.engine.validate_config(
            node,
            preview_headers=preview_headers,
            table_names=table_names,
            table_columns=table_columns,
        )
        issues = copy.deepcopy(validation.get("issues") or [])
        if not validation.get("ok"):
            return {
                "ok": False,
                "validation": validation,
                "issues": issues,
                "feedback": self.build_user_feedback(
                    level="warning",
                    code="node_config_invalid",
                    title="节点配置校验失败",
                    status_message="节点配置校验失败",
                    issue_message=self.format_issues_text(issues),
                    issues=issues,
                ).get("feedback") or {},
            }

        apply_result = self.apply_plan_command(
            plan,
            {"type": "replace_node", "index": selected_index, "node": node},
            preview_headers=preview_headers,
            table_names=table_names,
            table_columns=table_columns,
        )
        feedback_level = "info" if issues else "success"
        feedback_title = "节点配置提示" if issues else "节点配置已应用"
        feedback_status = "节点配置已应用。"
        feedback_issue_message = self.format_issues_text(issues) if issues else ""
        return {
            "ok": bool(apply_result.get("ok")),
            "validation": validation,
            "issues": issues,
            "apply_result": copy.deepcopy(apply_result),
            "node_config_context": self.describe_node_config_context(
                node.get("node_type_id") or node.get("type"),
                node=node,
                config=node.get("config"),
                preview_headers=preview_headers,
                table_names=table_names,
                table_columns=table_columns,
            ),
            "feedback": self.build_user_feedback(
                level=feedback_level,
                code="node_config_applied",
                title=feedback_title,
                status_message=feedback_status,
                issue_message=feedback_issue_message,
                issues=issues,
            ).get("feedback") or {},
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
                "view_state": {
                    "table_title": "输入表格",
                    "table_kind": "input",
                    "status_message": "已切换到输入表格。",
                    "has_table": True,
                },
                "message_panel": self.build_message_panel_state(
                    mode="info",
                    title="预览来源",
                    body="已切换到输入表格。",
                ).get("panel") or {},
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
                    "view_state": {
                        "table_title": "Headless 预览结果",
                        "table_kind": "preview",
                        "status_message": "暂无预览结果",
                        "has_table": False,
                    },
                    "message_panel": self.build_message_panel_state(
                        mode="warning",
                        title="读取预览来源失败",
                        issues=[{
                            "severity": "warning",
                            "code": "preview_table_missing",
                            "message": "还没有预览结果。",
                        }],
                    ).get("panel") or {},
                }
            return {
                "ok": True,
                "source": source,
                "table": {"headers": headers, "rows": rows},
                "title": "Headless 预览结果",
                "message": "已切换到预览结果。",
                "view_state": {
                    "table_title": "Headless 预览结果",
                    "table_kind": "preview",
                    "status_message": "已切换到预览结果。",
                    "has_table": True,
                },
                "message_panel": self.build_message_panel_state(
                    mode="info",
                    title="预览来源",
                    body="已切换到预览结果。",
                ).get("panel") or {},
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
                "view_state": {
                    "table_title": f"SQLite：{table_name}",
                    "table_kind": "sqlite",
                    "status_message": f"已读取 SQLite 表：{table_name}",
                    "has_table": True,
                },
                "message_panel": self.build_message_panel_state(
                    mode="info",
                    title="预览来源",
                    body=f"已读取 SQLite 表：{table_name}",
                ).get("panel") or {},
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
            "view_state": {
                "table_title": "表格预览",
                "table_kind": "preview",
                "status_message": "读取预览来源失败",
                "has_table": False,
            },
            "message_panel": self.build_message_panel_state(
                mode="warning",
                title="读取预览来源失败",
                issues=[{
                    "severity": "error",
                    "code": "unsupported_preview_source",
                    "message": f"不支持的预览来源：{kind or 'unknown'}",
                }],
            ).get("panel") or {},
        }

    def _condition_matches(self, condition, values):
        if not condition or not isinstance(condition, dict):
            return True
        field = condition.get("field")
        actual = values.get(field)
        if "equals" in condition:
            return str(actual) == str(condition.get("equals"))
        if "in" in condition:
            return any(str(actual) == str(item) for item in (condition.get("in") or []))
        return True

    def _preview_source_key(self, source):
        if not isinstance(source, dict):
            return ""
        return f"{source.get('type', '')}:{source.get('table_role', '')}:{source.get('table_name', '')}"

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

    def validate_workflow_request(
        self,
        plan=None,
        *,
        execute_actions=False,
        stop_index=None,
        output_settings=None,
        workflow_db_path=None,
        confirmed=False,
    ):
        plan_copy = copy.deepcopy(plan or {})
        settings = OutputSettings.from_payload(output_settings or {})
        precheck_db_path = settings.db_path or str(workflow_db_path or "").strip()
        validation = self.engine.validate_plan(plan_copy, stop_index=stop_index)
        jump_validation = self.engine.validate_jumps(plan_copy)
        access_precheck = self.engine.precheck_access(
            plan_copy,
            execute_actions=execute_actions,
            stop_index=stop_index,
            db_path=precheck_db_path,
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
        merged_logs = list(logs or result.get("logs") or [])
        payload = {
            "ok": status.get("status") != "failed",
            "status": status.get("status") or "unknown",
            "job_action": job_action,
            "table": {"headers": headers, "rows": rows},
            "logs": merged_logs,
            "steps": int(result.get("steps", 0) or 0),
            "cancelled": bool(result.get("cancelled")),
            "message": status.get("message") or "",
            "view_state": {
                "table_title": "",
                "table_kind": "preview",
                "should_refresh_preview_sources": False,
                "status_message": "",
                "has_table": bool(headers or rows),
            },
        }
        if status.get("status") == "failed":
            error = status.get("error") or {}
            payload["ok"] = False
            payload["error"] = error
            payload["display_message"] = error.get("message") or status.get("message") or "后台任务失败。"
            payload["message_panel"] = self.build_message_panel_state(
                mode="error",
                title="后台任务失败",
                body=payload["display_message"],
                logs=merged_logs,
            ).get("panel")
            payload["view_state"].update({
                "status_message": "后台任务失败",
                "table_kind": "preview",
            })
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
            if output.get("ok"):
                payload["message_panel"] = self.build_message_panel_state(
                    mode="success",
                    title="输出结果",
                    body=payload["display_message"],
                    logs=output.get("logs") or merged_logs,
                ).get("panel")
            else:
                payload["message_panel"] = self.build_message_panel_state(
                    mode="warning",
                    title="输出结果",
                    issues=output.get("issues") or [],
                    logs=merged_logs,
                ).get("panel")
            payload["view_state"].update({
                "table_title": "执行结果" if output.get("ok") else "执行结果（输出未落地）",
                "table_kind": "preview",
                "should_refresh_preview_sources": True,
                "status_message": payload["display_message"],
                "has_table": True,
            })
            return payload
        payload["display_message"] = status.get("message") or "任务完成。"
        payload["message_panel"] = self.build_message_panel_state(
            mode="info",
            title="任务结果",
            body=payload["display_message"],
            logs=merged_logs,
        ).get("panel")
        payload["view_state"].update({
            "table_title": "执行结果" if headers or rows else "",
            "table_kind": "preview",
            "should_refresh_preview_sources": bool(headers or rows),
            "status_message": payload["display_message"] if headers or rows else (status.get("message") or "后台任务已结束。"),
            "has_table": bool(headers or rows),
        })
        return payload
