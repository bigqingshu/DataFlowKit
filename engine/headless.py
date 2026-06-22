# -*- coding: utf-8 -*-
"""UI-free workflow engine adapter for DataFlowKit.

The first version deliberately supports only nodes that can run without a
Tkinter window or UI-owned services.  Nodes that still depend on window state,
database write services, plugins, or multi-table UI adapters are reported by
validate_plan() as unsupported instead of being partially emulated.
"""

from __future__ import annotations

import copy
import uuid
from datetime import datetime

from core.data_utils import normalize_rows, safe_cell
from engine.access_policy_service import AccessPolicyService
from engine.errors import EngineCancelled, PlanValidationError
from engine.issue_schema import has_error_issues, make_issue
from engine.jump_analysis_service import JumpAnalysisService
from engine.job_service import JobService
from engine.models import EngineRunResult, TableData
from engine.output_service import OutputService
from engine.plan_templates import PlanTemplateService
from engine.safety_policy import resolve_safety_policy
from engine.table_data_service import TableDataService
from engine.workflow_services import WorkflowServices
from workflow.default_configs import default_config_for_type, default_name_for_node
from workflow.config_validation import (
    validate_node_config,
    validate_plan_configs,
)
from workflow.nodes.data_common import (
    MAX_EXPANDED_ROWS,
    MAX_TARGET_CELLS,
    compare_values,
)
from workflow.nodes.data_nodes import (
    apply_area_fill_node,
    apply_copy_column_node,
    apply_copy_row_node,
    apply_current_datetime_column_node,
    apply_dedupe_node,
    apply_delete_columns_node,
    apply_delete_rows_node,
    apply_extract_node,
    apply_fill_value_node,
    apply_format_datetime_node,
    apply_merge_node,
    apply_move_columns_node,
    apply_new_columns_node,
    apply_numeric_column_node,
    apply_rename_columns_node,
    apply_replace_node,
    apply_row_data_mapping_node,
    apply_sequence_fill_node,
)
from workflow.protocol_nodes import (
    DEFAULT_NODE_VERSION,
    HEADLESS_CONTROL_NODE_TYPE_IDS,
    HEADLESS_DATA_NODE_TYPE_IDS,
    HEADLESS_NODE_TYPE_IDS,
    display_type_for_node,
    display_type_for_node_type_id,
    is_headless_supported_node_type,
    list_node_type_definitions,
    list_node_type_ids,
    normalize_node_type_id,
    stable_node_type_id_for_node,
)
from workflow.node_ui_schema import (
    get_node_ui_schema,
    list_node_ui_schemas,
)
from workflow.plan_commands import apply_plan_command as apply_workflow_plan_command
from workflow.plan_migration import migrate_plan as migrate_workflow_plan


SUPPORTED_DATA_NODE_TYPE_IDS = set(HEADLESS_DATA_NODE_TYPE_IDS)
SUPPORTED_CONTROL_NODE_TYPE_IDS = set(HEADLESS_CONTROL_NODE_TYPE_IDS)
SUPPORTED_HEADLESS_NODE_TYPE_IDS = set(HEADLESS_NODE_TYPE_IDS)

# Backward-compatible display-name sets for older callers/tests that imported
# these module constants directly.  New code should use the *_NODE_TYPE_IDS sets.
SUPPORTED_DATA_NODES = {
    display_type_for_node_type_id(node_type_id)
    for node_type_id in SUPPORTED_DATA_NODE_TYPE_IDS
}
SUPPORTED_CONTROL_NODES = {
    display_type_for_node_type_id(node_type_id)
    for node_type_id in SUPPORTED_CONTROL_NODE_TYPE_IDS
}
SUPPORTED_HEADLESS_NODES = SUPPORTED_DATA_NODES | SUPPORTED_CONTROL_NODES


class HeadlessWorkflowEngine:
    """Run a subset of DataFlowKit workflows without importing any UI module."""

    def __init__(
        self,
        *,
        max_expanded_rows=MAX_EXPANDED_ROWS,
        max_target_cells=MAX_TARGET_CELLS,
        node_id_factory=None,
        now_factory=None,
        services=None,
    ):
        self.max_expanded_rows = int(max_expanded_rows or MAX_EXPANDED_ROWS)
        self.max_target_cells = int(max_target_cells or MAX_TARGET_CELLS)
        self.node_id_factory = node_id_factory or (lambda: "node_" + uuid.uuid4().hex)
        self.now_factory = now_factory or datetime.now
        self.services = services or WorkflowServices()
        self.access = AccessPolicyService(db_path=getattr(self.services, "db_path", ""))
        self.jumps = JumpAnalysisService()
        self.tables = TableDataService(db_path=getattr(self.services, "db_path", ""))
        self.plan_templates = PlanTemplateService(node_id_factory=self.node_id_factory)
        self.jobs = JobService(self)
        self.outputs = OutputService(self.services)

    def list_node_types(self, include_unsupported=True):
        return [
            item["display_name"]
            for item in list_node_type_definitions(include_unsupported=include_unsupported)
        ]

    def list_node_type_ids(self, include_unsupported=True):
        return list_node_type_ids(include_unsupported=include_unsupported)

    def list_node_catalog(self, include_unsupported=True):
        return list_node_type_definitions(include_unsupported=include_unsupported)

    def list_node_ui_schemas(
        self,
        include_unsupported=True,
        preview_headers=None,
        table_names=None,
        table_columns=None,
    ):
        return list_node_ui_schemas(
            include_unsupported=include_unsupported,
            preview_headers=preview_headers,
            table_names=table_names,
            table_columns=table_columns,
        )

    def get_node_ui_schema(self, node_type, preview_headers=None, table_names=None, table_columns=None):
        return get_node_ui_schema(
            node_type,
            preview_headers=preview_headers,
            table_names=table_names,
            table_columns=table_columns,
        )

    def migrate_plan(self, plan, *, target_version=None):
        return migrate_workflow_plan(
            plan,
            target_version=target_version,
            node_id_factory=self.node_id_factory,
        )

    def list_plan_templates(self, plan_dir):
        return self.plan_templates.list_templates(plan_dir)

    def load_plan_template(self, path, *, migrate=True, target_version=None):
        return self.plan_templates.load_template(
            path,
            migrate=migrate,
            target_version=target_version,
        )

    def save_plan_template(self, path, plan, **options):
        return self.plan_templates.save_template(path, plan, **options)

    def validate_plan_template(self, plan):
        return self.plan_templates.validate_template(plan)

    def start_job(self, job_action, payload=None):
        return self.jobs.start_job(job_action, payload)

    def get_job_status(self, job_id, *, include_result=True):
        return self.jobs.get_job_status(job_id, include_result=include_result)

    def get_job_events(self, job_id, *, since=0):
        return self.jobs.get_job_events(job_id, since=since)

    def cancel_job(self, job_id):
        return self.jobs.cancel_job(job_id)

    def list_output_modes(self):
        return self.outputs.list_output_modes()

    def apply_output(self, headers=None, rows=None, logs=None, settings=None, **settings_kwargs):
        return self.outputs.apply_output(
            headers=headers,
            rows=rows,
            logs=logs,
            settings=settings,
            **settings_kwargs,
        )

    def list_tables(self, db_path=None):
        return self.tables.list_tables(db_path=db_path)

    def load_table(self, source=None, **kwargs):
        return self.tables.load_table(source, **kwargs)

    def get_table_page(self, table, *, limit=None, offset=0, source=None):
        return self.tables.get_table_page(table, limit=limit, offset=offset, source=source)

    def build_table_access(self, node):
        return self.access.build_table_access(node)

    def precheck_access(self, plan=None, **kwargs):
        return self.access.precheck_access(plan, **kwargs)

    def format_access_issue(self, issue):
        return self.access.format_access_issue(issue)

    def record_access_audit(self, event):
        return self.access.record_access_audit(event)

    def list_access_audit_logs(self, *, selected_status="全部", keyword=""):
        return self.access.list_access_audit_logs(
            selected_status=selected_status,
            keyword=keyword,
        )

    def format_access_audit_event(self, event):
        return self.access.format_access_audit_event(event)

    def analyze_jumps(self, plan=None, *, nodes=None):
        return self.jumps.analyze_plan(plan, nodes=nodes)

    def validate_jumps(self, plan=None, *, nodes=None):
        return self.jumps.validate_jumps(plan, nodes=nodes)

    def format_jump_issue(self, issue):
        return self.jumps.format_issue(issue)

    def apply_plan_command(self, plan, command, preview_headers=None, table_names=None, table_columns=None):
        return apply_workflow_plan_command(
            plan,
            command,
            preview_headers=preview_headers,
            table_names=table_names,
            table_columns=table_columns,
            node_id_factory=self.node_id_factory,
        )

    def validate_config(self, node_or_type, config=None, preview_headers=None, table_names=None, table_columns=None):
        return validate_node_config(
            node_or_type,
            config,
            headers=preview_headers,
            table_names=table_names,
            table_columns=table_columns,
        )

    def validate_plan_configs(self, plan, preview_headers=None, table_names=None, table_columns=None):
        return validate_plan_configs(
            plan,
            headers=preview_headers,
            table_names=table_names,
            table_columns=table_columns,
        )

    def is_node_supported(self, node_type):
        return is_headless_supported_node_type(node_type)

    def get_node_schema(self, node_type, preview_headers=None, table_names=None, table_columns=None):
        node_type_id = self._node_type_id_from_value(node_type)
        display_name = display_type_for_node_type_id(node_type_id)
        return {
            "node_type_id": node_type_id,
            "node_version": DEFAULT_NODE_VERSION,
            "display_name": display_name,
            "node_type": display_name,
            "type": display_name,
            "supported": self.is_node_supported(node_type_id),
            "default_name": default_name_for_node(display_name),
            "default_config": default_config_for_type(
                display_name,
                preview_headers=preview_headers,
                table_names=table_names,
                table_columns=table_columns,
            ),
        }

    def get_node_type(self, node_type, preview_headers=None, table_names=None, table_columns=None):
        """Protocol-name alias for get_node_schema()."""

        return self.get_node_schema(
            node_type,
            preview_headers=preview_headers,
            table_names=table_names,
            table_columns=table_columns,
        )

    def make_default_node(
        self,
        node_type,
        preview_headers=None,
        table_names=None,
        table_columns=None,
        *,
        name=None,
        include_legacy_type=True,
    ):
        node_type_id = self._node_type_id_from_value(node_type)
        display_name = display_type_for_node_type_id(node_type_id)
        node = {
            "node_id": self.node_id_factory(),
            "node_type_id": node_type_id,
            "node_version": DEFAULT_NODE_VERSION,
            "name": name or default_name_for_node(display_name),
            "enabled": True,
            "config": default_config_for_type(
                display_name,
                preview_headers=preview_headers,
                table_names=table_names,
                table_columns=table_columns,
            ),
        }
        if include_legacy_type:
            node["type"] = display_name
        return node

    def validate_plan(self, plan, *, stop_index=None, start_index=0):
        issues = []
        nodes = self._extract_nodes(plan, issues)
        if start_index < 0:
            issues.append(self._issue("error", "invalid_start_index", -1, "", "start_index 不能小于 0"))
        if nodes and start_index >= len(nodes):
            issues.append(self._issue("error", "invalid_start_index", -1, "", "start_index 超出节点范围"))
        if stop_index is not None and nodes:
            if stop_index < 0 or stop_index >= len(nodes):
                issues.append(self._issue("error", "invalid_stop_index", -1, "", "stop_index 超出节点范围"))

        anchor_ids = {}
        for idx, node in enumerate(nodes):
            if not isinstance(node, dict):
                issues.append(self._issue("error", "invalid_node", idx, "", "节点必须是 dict"))
                continue
            node_type_id = self._node_type_id_from_node(node)
            node_label = self._node_label(node, node_type_id)
            if not node_type_id:
                issues.append(self._issue(
                    "error",
                    "missing_node_type",
                    idx,
                    "",
                    "节点缺少 node_type_id/type",
                ))
                continue
            enabled = bool(node.get("enabled", True))
            if enabled and not self.is_node_supported(node_type_id):
                issues.append(self._issue(
                    "error",
                    "unsupported_node",
                    idx,
                    node_label,
                    f"HeadlessWorkflowEngine 第一版暂不支持节点：{node_label}",
                    node_type_id=node_type_id,
                ))
            elif not enabled and not self.is_node_supported(node_type_id):
                issues.append(self._issue(
                    "warning",
                    "disabled_unsupported_node",
                    idx,
                    node_label,
                    f"禁用节点暂不支持但执行时会跳过：{node_label}",
                    node_type_id=node_type_id,
                ))

            config = node.get("config", {})
            if node_type_id == "core.jump_anchor":
                anchor_id = str((config or {}).get("anchor_id", "") or "").strip()
                if not anchor_id:
                    issues.append(self._issue(
                        "error",
                        "missing_anchor_id",
                        idx,
                        node_label,
                        "跳转锚点缺少 anchor_id",
                        node_type_id=node_type_id,
                    ))
                elif anchor_id in anchor_ids:
                    issues.append(self._issue(
                        "error",
                        "duplicate_anchor_id",
                        idx,
                        node_label,
                        f"锚点 ID 重复：{anchor_id}，首次出现在节点 {anchor_ids[anchor_id] + 1}",
                        node_type_id=node_type_id,
                    ))
                else:
                    anchor_ids[anchor_id] = idx

        ok = not has_error_issues(issues)
        return {
            "ok": ok,
            "issues": issues,
            "node_count": len(nodes),
            "supported_node_type_ids": sorted(SUPPORTED_HEADLESS_NODE_TYPE_IDS),
            "supported_node_types": sorted(SUPPORTED_HEADLESS_NODES),
        }

    def preview_plan(self, plan, input_table=None, *, stop_index=None, **kwargs):
        kwargs.pop("execute_actions", None)
        kwargs.pop("dry_run", None)
        kwargs.pop("safety_mode", None)
        return self.run_plan(
            plan,
            input_table=input_table,
            stop_index=stop_index,
            execute_actions=False,
            dry_run=True,
            safety_mode="preview",
            **kwargs,
        )

    def run_plan(
        self,
        plan,
        input_table=None,
        *,
        execute_actions=False,
        dry_run=False,
        safety_mode=None,
        stop_index=None,
        start_index=0,
        initial_context=None,
        progress_callback=None,
        cancel_event=None,
        raise_error=True,
        max_steps=None,
        return_context=True,
    ):
        policy = resolve_safety_policy(
            safety_mode,
            execute_actions=execute_actions,
            dry_run=dry_run,
        )
        execute_actions = policy.execute_actions

        validation = self.validate_plan(plan, stop_index=stop_index, start_index=start_index)
        if not validation["ok"]:
            raise PlanValidationError("计划包含 headless 引擎无法执行的问题", validation["issues"])

        nodes = copy.deepcopy(self._extract_nodes(plan))
        table = self._resolve_input_table(plan, input_table)
        headers = list(table.headers)
        rows = [list(row) for row in table.rows]
        context = self._make_context(initial_context, progress_callback, cancel_event, policy)
        logs = []
        anchors = self._collect_jump_anchors(nodes)
        end = len(nodes) - 1 if stop_index is None else int(stop_index)
        pc = int(start_index or 0)
        steps = 0
        max_steps = int(max_steps or max(1000, len(nodes) * 2000))
        cancelled = False

        self._emit(progress_callback, {"type": "workflow_start", "message": "headless workflow start"})
        while pc < len(nodes) and pc <= end:
            try:
                self._check_cancelled(cancel_event)
            except EngineCancelled:
                logs.append("用户取消后台执行，工作流已安全停止。")
                cancelled = True
                break

            steps += 1
            if steps > max_steps:
                raise RuntimeError("工作流执行步数超过安全上限，疑似循环未正确结束。")

            idx = pc
            node = nodes[idx]
            node_type_id = self._node_type_id_from_node(node)
            node_label = self._node_label(node, node_type_id)
            if not node.get("enabled", True):
                logs.append(f"跳过 {idx + 1}.{node_label}")
                pc = idx + 1
                continue

            self._ensure_node_identity(node)
            self._set_current_node_info(context, node, idx)
            before_shape = (len(rows), len(headers))
            self._emit(progress_callback, {
                "type": "node_start",
                "node_index": idx,
                "node_total": len(nodes),
                "step": steps,
                "node_name": node_label,
                "node_type_id": node_type_id,
                "message": f"开始执行节点 {idx + 1}.{node_label}",
            })

            try:
                headers, rows, stat, jump_to = self._apply_node(
                    headers,
                    rows,
                    node,
                    context,
                    anchors,
                    nodes,
                    execute_actions=execute_actions,
                    cancel_event=cancel_event,
                )
            except Exception as exc:
                self._emit(progress_callback, {
                    "type": "node_error",
                    "node_index": idx,
                    "node_total": len(nodes),
                    "node_name": node_label,
                    "node_type_id": node_type_id,
                    "message": f"节点 {idx + 1}.{node_label} 执行失败：{exc}",
                })
                if raise_error:
                    raise RuntimeError(f"第 {idx + 1} 个节点【{node_label}】执行失败：{exc}") from exc
                logs.append(f"失败 {idx + 1}.{node_label}：{exc}")
                pc = idx + 1
                continue

            logs.append(self._build_node_log(idx, node_label, before_shape, headers, rows, stat))
            self._emit(progress_callback, {
                "type": "node_done",
                "node_index": idx,
                "node_total": len(nodes),
                "step": steps,
                "node_name": node_label,
                "node_type_id": node_type_id,
                "rows": len(rows),
                "cols": len(headers),
                "message": f"完成节点 {idx + 1}.{node_label}：{len(rows)} 行 × {len(headers)} 列",
            })
            pc = self._resolve_next_pc(idx, jump_to, len(nodes))

        result = EngineRunResult(
            headers=headers,
            rows=rows,
            logs=logs,
            context=context if return_context else {},
            steps=steps,
            pc=pc,
            cancelled=cancelled,
        )
        self._emit(progress_callback, {
            "type": "workflow_done" if not cancelled else "workflow_cancelled",
            "rows": len(rows),
            "cols": len(headers),
            "message": "headless workflow done" if not cancelled else "headless workflow cancelled",
        })
        return result

    def _apply_node(self, headers, rows, node, context, anchors, nodes, *, execute_actions=False, cancel_event=None):
        node_type_id = self._node_type_id_from_node(node)
        node_label = self._node_label(node, node_type_id)
        config = node.get("config", {}) or {}
        if node_type_id in SUPPORTED_DATA_NODE_TYPE_IDS:
            h, r, stat = self._apply_data_node(headers, rows, node_type_id, config, context, cancel_event)
            return h, r, stat, None
        if node_type_id == "core.jump_anchor":
            stat = self._append_jump_log(context, "anchor", config, "定位锚点：" + str(config.get("anchor_id", "") or "未命名"))
            return list(headers), [list(row) for row in rows], stat, None
        if node_type_id == "core.unconditional_jump":
            target = str(config.get("target_anchor_id", "") or "").strip()
            jump_to, message = self._resolve_anchor(target, anchors)
            self._append_jump_log(context, "unconditional_jump", config, message, target_index=jump_to)
            return list(headers), [list(row) for row in rows], "无条件跳转：" + message, jump_to
        if node_type_id == "core.condition_check":
            h, r, stat = self._apply_condition_check(headers, rows, config, context)
            return h, r, stat, None
        if node_type_id == "core.conditional_jump":
            headers, rows, stat, jump_to = self._apply_conditional_jump(headers, rows, config, context, anchors)
            return headers, rows, stat, jump_to
        raise ValueError(f"HeadlessWorkflowEngine 暂不支持节点：{node_label}")

    def _apply_data_node(self, headers, rows, node_type_id, config, context, cancel_event):
        node_context = self._make_node_context(context, cancel_event)
        if node_type_id == "core.replace":
            return apply_replace_node(headers, rows, config, context=node_context)
        if node_type_id == "core.extract":
            return apply_extract_node(headers, rows, config)
        if node_type_id == "core.datetime_format":
            return apply_format_datetime_node(headers, rows, config)
        if node_type_id == "core.current_datetime_column":
            return apply_current_datetime_column_node(headers, rows, config)
        if node_type_id == "core.new_columns":
            return apply_new_columns_node(headers, rows, config)
        if node_type_id == "core.merge_columns":
            return apply_merge_node(headers, rows, config, context=node_context)
        if node_type_id == "core.rename_columns":
            return apply_rename_columns_node(headers, rows, config)
        if node_type_id == "core.dedupe":
            return apply_dedupe_node(headers, rows, config, context=node_context)
        if node_type_id == "core.numeric_column":
            return apply_numeric_column_node(headers, rows, config, context=node_context)
        if node_type_id == "core.copy_column":
            return apply_copy_column_node(headers, rows, config)
        if node_type_id == "core.copy_row":
            return apply_copy_row_node(headers, rows, config)
        if node_type_id == "core.delete_rows":
            return apply_delete_rows_node(headers, rows, config)
        if node_type_id == "core.fill_value":
            return apply_fill_value_node(headers, rows, config, context=node_context)
        if node_type_id == "core.sequence_fill":
            return apply_sequence_fill_node(headers, rows, config, context=node_context)
        if node_type_id == "core.area_fill":
            return apply_area_fill_node(headers, rows, config, context=node_context)
        if node_type_id == "core.row_data_mapping":
            return apply_row_data_mapping_node(headers, rows, config)
        if node_type_id == "core.delete_columns":
            return apply_delete_columns_node(headers, rows, config)
        if node_type_id == "core.move_columns":
            return apply_move_columns_node(headers, rows, config)
        raise ValueError(f"HeadlessWorkflowEngine 暂不支持节点：{display_type_for_node_type_id(node_type_id)}")

    def _apply_condition_check(self, headers, rows, config, context):
        flag_name = str(config.get("flag_name", "") or "").strip()
        if not flag_name:
            raise ValueError("条件判断节点未填写输出标志。")
        passed, actual, detail = self._evaluate_condition(headers, rows, config)
        output_value = str(config.get("true_value", "TRUE") if passed else config.get("false_value", "FALSE"))
        item = {
            "value": output_value,
            "passed": bool(passed),
            "actual": actual,
            "detail": detail,
            "source_node": copy.deepcopy(context.get("current_node_info", {})),
            "time": self.now_factory().strftime("%Y-%m-%d %H:%M:%S"),
        }
        context.setdefault("condition_flags", {})[flag_name] = item
        self._append_jump_log(context, "condition_check", config, detail, flag_name=flag_name, value=output_value)
        return list(headers), [list(row) for row in rows], f"条件判断：{flag_name}={output_value}；{detail}"

    def _apply_conditional_jump(self, headers, rows, config, context, anchors):
        flag_name = str(config.get("flag_name", "") or "").strip()
        if not flag_name:
            message = "条件跳转未填写读取标志，默认不跳转"
            self._append_jump_log(context, "conditional_jump", config, message, status="warning")
            return list(headers), [list(row) for row in rows], message, None
        flags = context.setdefault("condition_flags", {})
        if flag_name not in flags:
            message = f"条件标志未产生：{flag_name}，默认不跳转"
            self._append_jump_log(context, "conditional_jump", config, message, status="warning")
            return list(headers), [list(row) for row in rows], message, None
        flag_value = str((flags.get(flag_name) or {}).get("value", "") or "").strip()
        target, rule_message = self._find_conditional_jump_target(flag_value, config)
        if not target:
            message = f"条件跳转：{flag_name}={flag_value or '-'}；{rule_message}，默认不跳转"
            self._append_jump_log(context, "conditional_jump", config, message, status="warning")
            return list(headers), [list(row) for row in rows], message, None
        jump_to, anchor_message = self._resolve_anchor(target, anchors)
        self._append_jump_log(context, "conditional_jump", config, anchor_message, target_index=jump_to)
        return list(headers), [list(row) for row in rows], (
            f"条件跳转：{flag_name}={flag_value or '-'}；{rule_message}；{anchor_message}"
        ), jump_to

    def _evaluate_condition(self, headers, rows, config):
        condition_type = str(config.get("condition_type", "表行数") or "表行数").strip()
        field = str(config.get("field", "") or "").strip()
        op = str(config.get("op", "大于") or "大于").strip()
        value = str(config.get("value", "") or "")
        case_sensitive = bool(config.get("case_sensitive", True))
        fixed_rows = normalize_rows(rows, len(headers))

        if condition_type == "表行数":
            actual = len(fixed_rows)
            return compare_values(str(actual), op, value, case_sensitive=True), actual, f"表行数 {actual} {op} {value}"
        if condition_type == "字段是否存在":
            exists = field in headers
            passed = not exists if op in ("不等于", "不包含") else exists
            return passed, "TRUE" if exists else "FALSE", f"字段 {field or '-'} {'存在' if exists else '不存在'}"
        if condition_type == "字段值":
            if field not in headers:
                raise ValueError(f"字段不存在：{field}")
            idx = headers.index(field)
            matched = sum(
                1 for row in fixed_rows
                if compare_values(safe_cell(row, idx), op, value, case_sensitive=case_sensitive)
            )
            return matched > 0, matched, f"字段值任意行满足：{field} {op} {value}，命中 {matched} 行"
        if condition_type == "字段空值数量":
            actual = self._count_empty_cells(headers, fixed_rows, field)
            return compare_values(str(actual), op, value, case_sensitive=True), actual, f"字段空值数量：{field}={actual}，条件 {op} {value}"
        if condition_type == "字段包含值数量":
            actual = self._count_contains_cells(headers, fixed_rows, field, value, case_sensitive=case_sensitive)
            return compare_values(str(actual), op, value, case_sensitive=True), actual, f"字段包含值数量：{field} 包含 {value} 的行数={actual}，条件 {op} {value}"
        raise ValueError(f"未知条件判断类型：{condition_type}")

    def _count_empty_cells(self, headers, rows, field):
        if field not in headers:
            raise ValueError(f"字段不存在：{field}")
        idx = headers.index(field)
        return sum(1 for row in normalize_rows(rows, len(headers)) if safe_cell(row, idx).strip() == "")

    def _count_contains_cells(self, headers, rows, field, value, case_sensitive=True):
        if field not in headers:
            raise ValueError(f"字段不存在：{field}")
        idx = headers.index(field)
        needle = str(value or "")
        if not case_sensitive:
            needle = needle.lower()
        count = 0
        for row in normalize_rows(rows, len(headers)):
            text = safe_cell(row, idx)
            haystack = text if case_sensitive else text.lower()
            if needle in haystack:
                count += 1
        return count

    def _find_conditional_jump_target(self, flag_value, config):
        value_text = str(flag_value or "").strip()
        rules = config.get("jump_rules", [])
        if not isinstance(rules, list):
            rules = []
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            expected = str(rule.get("value", "") or "").strip()
            if expected == value_text:
                return str(rule.get("target_anchor_id", "") or "").strip(), f"命中条件值 {value_text}"
        default_anchor = str(config.get("default_anchor_id", "") or "").strip()
        if default_anchor:
            return default_anchor, f"条件值 {value_text or '-'} 未映射，使用默认锚点"
        return "", f"条件值 {value_text or '-'} 未映射"

    def _extract_nodes(self, plan, issues=None):
        if isinstance(plan, list):
            return plan
        if isinstance(plan, dict):
            nodes = plan.get("nodes", [])
            if isinstance(nodes, list):
                return nodes
            if issues is not None:
                issues.append(self._issue("error", "invalid_nodes", -1, "", "plan.nodes 必须是 list"))
            return []
        if issues is not None:
            issues.append(self._issue("error", "invalid_plan", -1, "", "plan 必须是 dict 或节点 list"))
            return []
        raise ValueError("plan must be a dict or node list")

    def _resolve_input_table(self, plan, input_table):
        if input_table is not None:
            return TableData.from_payload(input_table)
        if isinstance(plan, dict):
            if isinstance(plan.get("input"), dict):
                return TableData.from_payload(plan.get("input"))
            return TableData.from_payload(headers=plan.get("headers", []), rows=plan.get("rows", []))
        return TableData()

    def _make_context(self, initial_context, progress_callback, cancel_event, safety_policy=None):
        context = copy.deepcopy(initial_context) if isinstance(initial_context, dict) else {}
        context.setdefault("transit_tables", {})
        context.setdefault("loop_states", {})
        context.setdefault("loop_results", {})
        context.setdefault("condition_flags", {})
        context.setdefault("jump_logs", [])
        context.setdefault("table_access_policy", "audit")
        policy = safety_policy or resolve_safety_policy()
        context["execute_actions"] = bool(policy.execute_actions)
        context["dry_run"] = bool(policy.dry_run)
        context["safety_policy"] = policy.to_dict()
        if progress_callback is not None:
            context["progress_callback"] = progress_callback
        if cancel_event is not None:
            context["cancel_event"] = cancel_event
        return context

    def _make_node_context(self, context, cancel_event):
        node_context = dict(context or {})
        node_context["max_expanded_rows"] = self.max_expanded_rows
        node_context["max_target_cells"] = self.max_target_cells
        node_context["check_cancelled"] = lambda index=None: self._check_cancelled(cancel_event)
        return node_context

    def _collect_jump_anchors(self, nodes):
        result = {}
        for idx, node in enumerate(nodes or []):
            if not isinstance(node, dict) or self._node_type_id_from_node(node) != "core.jump_anchor":
                continue
            anchor_id = str((node.get("config") or {}).get("anchor_id", "") or "").strip()
            if anchor_id and anchor_id not in result:
                result[anchor_id] = idx
        return result

    def _resolve_anchor(self, anchor_id, anchors):
        anchor_id = str(anchor_id or "").strip()
        if not anchor_id:
            return None, "目标锚点为空，默认不跳转"
        if anchor_id not in anchors:
            return None, f"未找到锚点：{anchor_id}，默认不跳转"
        target = anchors[anchor_id]
        return target, f"跳转到锚点 {anchor_id}（节点 {target + 1}）"

    def _resolve_next_pc(self, idx, jump_to, node_total):
        if jump_to is None:
            return idx + 1
        jump_to = int(jump_to)
        if jump_to < 0 or jump_to > node_total:
            raise RuntimeError(f"循环跳转目标越界：{jump_to}")
        return jump_to

    def _ensure_node_identity(self, node):
        if not node.get("node_id"):
            node["node_id"] = self.node_id_factory()
        return node["node_id"]

    def _node_type_id_from_value(self, value):
        return normalize_node_type_id(value)

    def _node_type_id_from_node(self, node):
        return stable_node_type_id_for_node(node)

    def _node_label(self, node, node_type_id=None):
        if isinstance(node, dict):
            label = display_type_for_node(node)
            if label:
                return label
        if node_type_id:
            return display_type_for_node_type_id(node_type_id)
        return ""

    def _set_current_node_info(self, context, node, idx):
        node_type_id = self._node_type_id_from_node(node)
        node_label = self._node_label(node, node_type_id)
        context["current_node_info"] = {
            "node_id": node.get("node_id", ""),
            "node_name": node.get("name", ""),
            "node_type": node_label,
            "node_type_id": node_type_id,
            "display_name": node_label,
            "node_index": idx,
            "table_access": copy.deepcopy(node.get("table_access", {})),
        }

    def _append_jump_log(self, context, event, config, message, status="ok", **extra):
        payload = {
            "time": self.now_factory().strftime("%Y-%m-%d %H:%M:%S"),
            "event": event,
            "status": status,
            "message": message,
        }
        payload.update(extra)
        payload.update(copy.deepcopy(context.get("current_node_info", {})))
        if isinstance(config, dict):
            if config.get("anchor_id"):
                payload.setdefault("anchor_id", config.get("anchor_id"))
            if config.get("target_anchor_id"):
                payload.setdefault("target_anchor_id", config.get("target_anchor_id"))
        context.setdefault("jump_logs", []).append(payload)
        return message

    def _build_node_log(self, idx, node_type, before_shape, headers, rows, stat):
        after_shape = (len(rows), len(headers))
        return f"{idx + 1}.{node_type} {before_shape[0]}×{before_shape[1]}→{after_shape[0]}×{after_shape[1]} {stat}"

    def _check_cancelled(self, cancel_event):
        if cancel_event is not None and cancel_event.is_set():
            raise EngineCancelled("headless workflow cancelled")

    def _emit(self, callback, payload):
        if callable(callback):
            callback(payload)
        return payload

    def _issue(self, severity, code, node_index, node_type, message, *, node_type_id=""):
        return make_issue(
            severity,
            code,
            message,
            node_index=node_index,
            node_type=node_type,
            node_type_id=node_type_id,
        )
