# -*- coding: utf-8 -*-
"""UI-free workflow engine adapter for DataFlowKit.

The first version deliberately supports only nodes that can run without a
Tkinter window or UI-owned services.  Nodes that still depend on window state,
database write services, plugins, or multi-table UI adapters are reported by
validate_plan() as unsupported instead of being partially emulated.
"""

from __future__ import annotations

import copy
import csv
import os
import time
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
from engine.plugin_service import PluginService
from engine.safety_policy import resolve_safety_policy
from engine.table_data_service import TableDataService
from engine.workflow_services import WorkflowServices
from db.table_manager import TableAccessManager
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
    apply_match_value_output_field_name_node,
    apply_move_columns_node,
    apply_new_columns_node,
    apply_numeric_column_node,
    apply_rename_columns_node,
    apply_replace_node,
    apply_row_data_mapping_node,
    apply_sequence_fill_node,
)
from workflow.nodes.filter_execution_nodes import apply_filter_node
from workflow.nodes.filter_plan_nodes import (
    build_filter_config_probe_result,
    build_filter_runtime_plan,
    get_required_columns_for_plan_table,
)
from workflow.nodes.file_nodes import (
    BATCH_RENAME_LOG_HEADERS,
    apply_batch_rename_node,
    apply_file_list_node,
    make_numbered_path,
)
from workflow.nodes.group_nodes import (
    build_empty_group_stat,
    build_group_final_output,
    build_group_input_table,
    build_group_status_text,
    ensure_group_parent_context,
    make_group_child_context,
    merge_group_child_audit_logs,
    normalize_group_sqlite_mode,
    normalize_group_transit_conflict_mode,
)
from workflow.nodes.loop_nodes import (
    apply_loop_judge_to_state,
    build_loop_judge_output,
    build_loop_start_output,
    init_loop_state_from_source,
    take_next_loop_item,
)
from workflow.nodes.plugin_nodes import (
    build_plugin_failure_output,
    build_plugin_final_output,
    build_plugin_status_text,
    normalize_plugin_logs,
    plugin_log_items_to_table,
    should_save_plugin_output_as_transit,
)
from workflow.nodes.selected_columns_nodes import (
    apply_selected_columns_to_memory_table,
    build_selected_columns_write_payload,
    get_selected_columns_write_skip_stat,
    normalize_selected_columns_write_mode,
    resolve_selected_columns_write_target,
)
from workflow.nodes.transit_nodes import (
    append_headers_rows,
    apply_save_transit_node,
    make_unique_transit_name,
)
from workflow.nodes.writeback_nodes import (
    apply_external_table_to_current_node,
    build_writeback_actions as build_writeback_actions_from_records,
    build_writeback_execute_stat,
    build_writeback_full_structure_execute_stat,
    build_writeback_full_structure_rows_for_sqlite,
    build_writeback_preview_stat,
    count_writeback_actions,
    finish_writeback_node_output,
    get_writeback_non_execute_suffix,
    get_writeback_target_fields,
    should_execute_writeback_update,
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
        self.plugins = PluginService(db_path=getattr(self.services, "db_path", ""))
        self.jobs = JobService(self)
        self.outputs = OutputService(self.services)

    def list_node_types(self, include_unsupported=True):
        return [
            item["display_name"]
            for item in self.list_node_catalog(include_unsupported=include_unsupported)
        ]

    def list_node_type_ids(self, include_unsupported=True):
        return [
            item["node_type_id"]
            for item in self.list_node_catalog(include_unsupported=include_unsupported)
        ]

    def list_node_catalog(self, include_unsupported=True):
        catalog = list_node_type_definitions(include_unsupported=include_unsupported)
        if include_unsupported:
            catalog.extend(self.plugins.list_plugin_node_catalog().get("plugins", []))
        return catalog

    def list_node_ui_schemas(
        self,
        include_unsupported=True,
        preview_headers=None,
        table_names=None,
        table_columns=None,
    ):
        schemas = list_node_ui_schemas(
            include_unsupported=include_unsupported,
            preview_headers=preview_headers,
            table_names=table_names,
            table_columns=table_columns,
        )
        if include_unsupported:
            schemas.extend(self.plugins.list_plugin_node_ui_schemas(
                preview_headers=preview_headers,
                table_names=table_names,
                table_columns=table_columns,
            ).get("node_ui_schemas", []))
        return schemas

    def get_node_ui_schema(self, node_type, preview_headers=None, table_names=None, table_columns=None):
        node_type_id = self._node_type_id_from_value(node_type)
        if node_type_id.startswith("plugin."):
            schema = self.plugins.get_plugin_schema(
                node_type_id,
                preview_headers=preview_headers,
                table_names=table_names,
                table_columns=table_columns,
            )
            if schema.get("ok"):
                return schema["schema"]
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

    def create_table_handle(self, table_or_source=None, **kwargs):
        return self.tables.create_table_handle(table_or_source, **kwargs)

    def get_table_handle_page(self, handle, *, limit=None, offset=0):
        return self.tables.get_table_handle_page(handle, limit=limit, offset=offset)

    def list_table_handles(self):
        return self.tables.list_table_handles()

    def release_table_handle(self, handle):
        return self.tables.release_table_handle(handle)

    def parse_clipboard_table(self, text, *, first_row_header=True):
        return self.tables.parse_clipboard_table(text, first_row_header=first_row_header)

    def normalize_table_headers(self, headers):
        return self.tables.normalize_table_headers(headers)

    def promote_first_row_to_headers(self, table):
        return self.tables.promote_first_row_to_headers(table)

    def patch_table_cell(self, table, *, row=None, column=None, value=""):
        return self.tables.patch_table_cell(table, row=row, column=column, value=value)

    def search_table(self, table, keyword, *, current_index=-1, offset=0, reset=True):
        return self.tables.search_table(
            table,
            keyword,
            current_index=current_index,
            offset=offset,
            reset=reset,
        )

    def build_table_search_navigation(self, matches, *, current_index=-1, offset=0, reset=False):
        return self.tables.build_table_search_navigation(
            matches,
            current_index=current_index,
            offset=offset,
            reset=reset,
        )

    def build_data_source_state(self, table=None, *, source=None, dirty=False, display_name=""):
        return self.tables.build_data_source_state(
            table,
            source=source,
            dirty=dirty,
            display_name=display_name,
        )

    def describe_table_save_modes(self):
        return self.tables.describe_table_save_modes()

    def normalize_table_save_mode(self, mode):
        return self.tables.normalize_table_save_mode(mode)

    def save_table(self, table=None, *, db_path=None, table_name=None, mode="replace"):
        return self.tables.save_table(table, db_path=db_path, table_name=table_name, mode=mode)

    def delete_table(self, *, db_path=None, table_name=None, backup=True, confirmed=False):
        return self.tables.delete_table(
            db_path=db_path,
            table_name=table_name,
            backup=backup,
            confirmed=confirmed,
        )

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

    def list_plugins(self, plugins_dir=None, *, refresh=None):
        return self.plugins.list_plugins(plugins_dir=plugins_dir, refresh=refresh)

    def get_plugin_schema(self, plugin_id, **kwargs):
        return self.plugins.get_plugin_schema(plugin_id, **kwargs)

    def describe_plugin_config(self, plugin_id, **kwargs):
        return self.plugins.describe_plugin_config(plugin_id, **kwargs)

    def preview_plugin_config_effect(self, plugin_id, **kwargs):
        return self.plugins.preview_plugin_config_effect(plugin_id, **kwargs)

    def validate_plugin_config_patch(self, plugin_id, **kwargs):
        return self.plugins.validate_plugin_config_patch(plugin_id, **kwargs)

    def apply_plugin_config_patch(self, plugin_id, **kwargs):
        return self.plugins.apply_plugin_config_patch(plugin_id, **kwargs)

    def make_plugin_default_config(self, plugin_id, **kwargs):
        return {
            "ok": True,
            "plugin_id": plugin_id,
            "config": self.plugins.make_plugin_default_config(plugin_id, **kwargs),
            "issues": [],
        }

    def validate_plugin_config(self, plugin_id, **kwargs):
        return self.plugins.validate_plugin_config(plugin_id, **kwargs)

    def run_plugin(self, plugin_id, **kwargs):
        return self.plugins.run_plugin(plugin_id, **kwargs)

    def run_plugin_custom_config_window(self, plugin_id, **kwargs):
        return self.plugins.run_plugin_custom_config_window(plugin_id, **kwargs)

    def analyze_jumps(self, plan=None, *, nodes=None):
        return self.jumps.analyze_plan(plan, nodes=nodes)

    def validate_jumps(self, plan=None, *, nodes=None):
        return self.jumps.validate_jumps(plan, nodes=nodes)

    def format_jump_issue(self, issue):
        return self.jumps.format_issue(issue)

    def apply_plan_command(self, plan, command, preview_headers=None, table_names=None, table_columns=None):
        command = self._prepare_plan_command(command)
        return apply_workflow_plan_command(
            plan,
            command,
            preview_headers=preview_headers,
            table_names=table_names,
            table_columns=table_columns,
            node_id_factory=self.node_id_factory,
        )

    def _prepare_plan_command(self, command):
        if not isinstance(command, dict):
            return command
        command_type = str(command.get("type") or command.get("command") or "").strip()
        if command_type != "insert_node" or isinstance(command.get("node"), dict):
            return command
        node_type = command.get("node_type_id") or command.get("node_type") or command.get("type")
        node_type_id = self._node_type_id_from_value(node_type)
        if not node_type_id.startswith("plugin."):
            return command
        prepared = copy.deepcopy(command)
        prepared["node"] = self.make_default_node(
            node_type_id,
            name=command.get("name"),
            include_legacy_type=bool(command.get("include_legacy_type", True)),
        )
        return prepared

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
        node_type_id = self._node_type_id_from_value(node_type)
        if node_type_id.startswith("plugin."):
            return self.plugins.is_plugin_headless_runnable(node_type_id)
        return is_headless_supported_node_type(node_type)

    def get_node_schema(self, node_type, preview_headers=None, table_names=None, table_columns=None):
        node_type_id = self._node_type_id_from_value(node_type)
        if node_type_id.startswith("plugin."):
            schema = self.plugins.get_plugin_schema(
                node_type_id,
                preview_headers=preview_headers,
                table_names=table_names,
                table_columns=table_columns,
            )
            if schema.get("ok"):
                plugin_schema = schema["schema"]
                return {
                    "node_type_id": node_type_id,
                    "node_version": DEFAULT_NODE_VERSION,
                    "display_name": plugin_schema.get("display_name", "插件节点"),
                    "node_type": "插件节点",
                    "type": "插件节点",
                    "supported": self.is_node_supported(node_type_id),
                    "default_name": schema["plugin"].get("name", "插件节点"),
                    "default_config": schema["default_config"],
                    "plugin": schema["plugin"],
                }
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
        if node_type_id.startswith("plugin."):
            return self.plugins.make_default_plugin_node(
                node_type_id,
                node_id=self.node_id_factory(),
                name=name or "",
                include_legacy_type=include_legacy_type,
            )
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
            if enabled and node_type_id == "core.group":
                self._append_group_validation_issues(config, idx, node_label, issues)

        ok = not has_error_issues(issues)
        return {
            "ok": ok,
            "issues": issues,
            "node_count": len(nodes),
            "supported_node_type_ids": sorted(SUPPORTED_HEADLESS_NODE_TYPE_IDS),
            "supported_node_types": sorted(SUPPORTED_HEADLESS_NODES),
        }

    def _append_group_validation_issues(self, config, node_index, node_label, issues, *, path=""):
        nodes = (config or {}).get("nodes", [])
        group_name = str((config or {}).get("group_name", "") or node_label or "节点组").strip()
        group_path = path or group_name
        if nodes in (None, ""):
            return
        if not isinstance(nodes, list):
            issues.append(self._issue(
                "error",
                "invalid_group_nodes",
                node_index,
                node_label,
                f"节点组【{group_path}】的 config.nodes 必须是 list",
                node_type_id="core.group",
            ))
            return
        for inner_idx, inner in enumerate(nodes):
            prefix = f"节点组【{group_path}】内第 {inner_idx + 1} 个节点"
            if not isinstance(inner, dict):
                issues.append(self._issue(
                    "error",
                    "invalid_group_inner_node",
                    node_index,
                    node_label,
                    f"{prefix}必须是 dict",
                    node_type_id="core.group",
                ))
                continue
            inner_type_id = self._node_type_id_from_node(inner)
            inner_label = self._node_label(inner, inner_type_id)
            if not inner_type_id:
                issues.append(self._issue(
                    "error",
                    "missing_group_inner_node_type",
                    node_index,
                    node_label,
                    f"{prefix}缺少 node_type_id/type",
                    node_type_id="core.group",
                ))
                continue
            enabled = bool(inner.get("enabled", True))
            if inner_type_id in ("core.loop_start", "core.loop_judge"):
                issues.append(self._issue(
                    "error",
                    "unsupported_group_loop_node",
                    node_index,
                    node_label,
                    f"{prefix}【{inner_label}】暂不支持放在节点组内部",
                    node_type_id=inner_type_id,
                ))
                continue
            if enabled and not self.is_node_supported(inner_type_id):
                issues.append(self._issue(
                    "error",
                    "unsupported_group_inner_node",
                    node_index,
                    node_label,
                    f"{prefix}【{inner_label}】暂不支持 headless 执行",
                    node_type_id=inner_type_id,
                ))
            elif not enabled and not self.is_node_supported(inner_type_id):
                issues.append(self._issue(
                    "warning",
                    "disabled_unsupported_group_inner_node",
                    node_index,
                    node_label,
                    f"{prefix}【{inner_label}】暂不支持但执行时会跳过",
                    node_type_id=inner_type_id,
                ))
            if enabled and inner_type_id == "core.group":
                nested_path = f"{group_path}/{str((inner.get('config') or {}).get('group_name', '') or inner_label)}"
                self._append_group_validation_issues(
                    inner.get("config", {}) or {},
                    node_index,
                    node_label,
                    issues,
                    path=nested_path,
                )

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

        workflow_started_at = time.perf_counter()
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
            node_started_at = time.perf_counter()
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
                    node_index=idx,
                    end_index=end,
                    execute_actions=execute_actions,
                    cancel_event=cancel_event,
                )
            except Exception as exc:
                node_elapsed = time.perf_counter() - node_started_at
                self._emit(progress_callback, {
                    "type": "node_error",
                    "node_index": idx,
                    "node_total": len(nodes),
                    "node_name": node_label,
                    "node_type_id": node_type_id,
                    "elapsed_seconds": node_elapsed,
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
                "elapsed_seconds": time.perf_counter() - node_started_at,
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
            "elapsed_seconds": time.perf_counter() - workflow_started_at,
            "message": "headless workflow done" if not cancelled else "headless workflow cancelled",
        })
        return result

    def _apply_node(
        self,
        headers,
        rows,
        node,
        context,
        anchors,
        nodes,
        *,
        node_index=0,
        end_index=None,
        execute_actions=False,
        cancel_event=None,
    ):
        node_type_id = self._node_type_id_from_node(node)
        node_label = self._node_label(node, node_type_id)
        config = node.get("config", {}) or {}
        if node_type_id.startswith("plugin."):
            h, r, stat = self._apply_plugin_node(headers, rows, node_type_id, config, context, execute_actions)
            return h, r, stat, None
        if node_type_id in SUPPORTED_DATA_NODE_TYPE_IDS:
            if node_type_id == "core.save_transit":
                h, r, stat = self._apply_save_transit_node(headers, rows, config, context, execute_actions)
                return h, r, stat, None
            if node_type_id == "core.selected_columns_write":
                h, r, stat = self._apply_selected_columns_write_node(headers, rows, config, context, execute_actions)
                return h, r, stat, None
            if node_type_id == "core.writeback":
                h, r, stat = self._apply_writeback_node(headers, rows, config, context, execute_actions)
                return h, r, stat, None
            if node_type_id == "core.batch_rename":
                h, r, stat = self._apply_batch_rename_node(headers, rows, config, context, execute_actions, cancel_event)
                return h, r, stat, None
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
        if node_type_id == "core.group":
            h, r, stat = self._apply_group_node(
                headers,
                rows,
                config,
                context,
                execute_actions,
                cancel_event,
            )
            return h, r, stat, None
        if node_type_id == "core.loop_start":
            h, r, stat, jump_to = self._apply_loop_start_node(
                headers,
                rows,
                config,
                context,
                nodes,
                node_index=node_index,
                end_index=end_index,
            )
            return h, r, stat, jump_to
        if node_type_id == "core.loop_judge":
            h, r, stat, jump_to = self._apply_loop_judge_node(
                headers,
                rows,
                config,
                context,
                nodes,
                node_index=node_index,
            )
            return h, r, stat, jump_to
        raise ValueError(f"HeadlessWorkflowEngine 暂不支持节点：{node_label}")

    def _apply_data_node(self, headers, rows, node_type_id, config, context, cancel_event):
        node_context = self._make_node_context(context, cancel_event)
        if node_type_id == "core.file_list":
            file_context = self._make_file_node_context(context, cancel_event)
            return apply_file_list_node(headers, rows, config, context=file_context)
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
        if node_type_id == "core.match_value_output":
            match_context = self._make_match_value_output_context(config, context, cancel_event)
            return apply_match_value_output_field_name_node(headers, rows, config, context=match_context)
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
        if node_type_id == "core.filter":
            return self._apply_filter_node(headers, rows, config, context, cancel_event)
        raise ValueError(f"HeadlessWorkflowEngine 暂不支持节点：{display_type_for_node_type_id(node_type_id)}")

    def _make_match_value_output_context(self, config, context, cancel_event):
        lookup_source_type = str(config.get("lookup_source_type", "SQLite表") or "SQLite表").strip()
        lookup_table = str(config.get("lookup_table", "") or "").strip()
        if not lookup_table:
            raise ValueError("请选择匹配表或中转副表。")

        if lookup_source_type == "中转副表":
            lookup_columns, lookup_rows = self._load_transit_table(context, lookup_table)
        else:
            lookup_columns, lookup_rows = self._load_named_table(lookup_table, context)

        lookup_records = []
        normalized_rows = normalize_rows(lookup_rows, len(lookup_columns))
        for index, row in enumerate(normalized_rows, start=1):
            record = {"__rowid__": "", "__row_index__": index}
            for col_index, col in enumerate(lookup_columns):
                record[col] = safe_cell(row, col_index)
            lookup_records.append(record)

        node_context = self._make_node_context(context, cancel_event)
        node_context["lookup_columns"] = lookup_columns
        node_context["lookup_records"] = lookup_records
        return node_context

    def _apply_filter_node(self, headers, rows, config, context, cancel_event):
        extra_tables = list((config or {}).get("extra_tables", []) or [])
        available_fields = self._filter_available_fields(headers, extra_tables, context) if extra_tables else None
        runtime_plan = build_filter_runtime_plan(headers, config, available_fields=available_fields)
        if context.get("is_config_probe") and extra_tables:
            return build_filter_config_probe_result(runtime_plan["output_headers"])

        table_records = {}
        for table in runtime_plan["extra_tables"]:
            table_records[table] = self._load_plan_table_records(
                table,
                context,
                runtime_plan["table_required"].get(table),
            )

        node_context = self._make_node_context(context, cancel_event)
        node_context.update({
            "lookup_fields": runtime_plan["lookup_fields"],
            "output_headers": runtime_plan["output_headers"],
            "current_required": runtime_plan["current_required"],
            "table_required": runtime_plan["table_required"],
            "table_records": table_records,
        })
        return apply_filter_node(headers, rows, runtime_plan["runtime_config"], context=node_context)

    def _filter_available_fields(self, headers, extra_tables, context):
        fields = [f"当前表.{header}" for header in headers]
        for table in extra_tables:
            try:
                table_headers, _table_rows = self._load_table_for_filter_source(table, context)
            except Exception:
                continue
            for col in table_headers:
                fields.append(f"{table}.{col}")
        return fields

    def _load_plan_table_records(self, table_name, context, required_fields=None):
        all_columns, table_rows = self._load_table_for_filter_source(table_name, context)
        columns = get_required_columns_for_plan_table(table_name, all_columns, required_fields)
        column_indexes = [(all_columns.index(col), col) for col in columns if col in all_columns]
        records = []
        for row in normalize_rows(table_rows, len(all_columns)):
            record = {}
            for index, col in column_indexes:
                record[f"{table_name}.{col}"] = safe_cell(row, index)
            records.append(record)
        return records

    def _load_table_for_filter_source(self, table_name, context):
        text = str(table_name or "").strip()
        if text.startswith("中转:"):
            return self._load_transit_table(context, text.split(":", 1)[1])
        return self._load_named_table(text, context)

    def _load_transit_table(self, context, table_name):
        name = str(table_name or "").strip()
        transit_tables = (context or {}).get("transit_tables", {}) or {}
        if name not in transit_tables:
            raise ValueError(f"中转副表不存在或尚未生成：{name}")
        item = transit_tables.get(name) or {}
        return list(item.get("headers", []) or []), [list(row) for row in (item.get("rows", []) or [])]

    def _load_named_table(self, table_name, context):
        name = str(table_name or "").strip()
        table_sources = (context or {}).get("table_sources", {}) or {}
        inline_tables = (context or {}).get("tables", {}) or {}
        source = None
        if isinstance(table_sources, dict):
            source = table_sources.get(name)
        if source is None and isinstance(inline_tables, dict):
            source = inline_tables.get(name)

        if source is None:
            loaded = self.tables.load_sqlite_table(name, db_path=self._context_db_path(context))
        else:
            loaded = self._load_context_table_source(source)
        if not loaded.get("ok"):
            issues = loaded.get("issues") or []
            if issues:
                raise ValueError(issues[0].get("message") or "读取表失败。")
            raise ValueError(f"读取表失败：{name}")
        table = TableData.from_payload(loaded.get("table") or {})
        return list(table.headers), [list(row) for row in table.rows]

    def _load_context_table_source(self, source):
        if isinstance(source, dict) and str(source.get("type") or "").strip() == "handle":
            return self.tables.get_table_handle_page(
                source.get("handle") or source.get("id"),
                limit=source.get("limit"),
                offset=source.get("offset", 0),
            )
        return self.tables.load_table(source)

    def _apply_selected_columns_write_node(self, headers, rows, config, context, execute_actions):
        context.setdefault("transit_tables", {})
        source_headers, source_rows, source_name = self._read_selected_columns_source_table(
            config,
            headers,
            rows,
            context,
        )
        selected_fields, target_fields, selected_rows = build_selected_columns_write_payload(
            config,
            source_headers,
            source_rows,
        )
        target_type, target_name = resolve_selected_columns_write_target(config)
        allow_preview_write = bool(context.get("allow_selected_columns_write_in_preview", False))
        config_preview_only = bool(context.get("selected_columns_config_preview_only", False))
        skip_stat = get_selected_columns_write_skip_stat(
            config,
            source_name,
            selected_fields,
            selected_rows,
            execute_actions=execute_actions,
            allow_preview_write=allow_preview_write,
            config_preview_only=config_preview_only,
        )
        if skip_stat:
            return list(headers), [list(row) for row in rows], skip_stat

        if target_type == "当前工作表":
            new_headers, new_rows = apply_selected_columns_to_memory_table(
                headers,
                rows,
                target_fields,
                selected_rows,
                config,
            )
            return (
                new_headers,
                new_rows,
                f"已写入当前工作表：{len(new_rows)} 行 × {len(new_headers)} 列，结果继续传给后续节点",
            )
        if target_type == "中转副表":
            return self._apply_selected_columns_write_transit_table(
                headers,
                rows,
                config,
                context,
                target_name,
                target_fields,
                selected_rows,
            )
        if target_type == "SQLite表":
            return self._apply_selected_columns_write_sqlite_table(
                headers,
                rows,
                config,
                target_name,
                target_fields,
                selected_rows,
            )
        raise ValueError(f"未知目标类型：{target_type}")

    def _read_selected_columns_source_table(self, config, current_headers, current_rows, context):
        source_type = str(config.get("source_type", "当前工作流表") or "当前工作流表").strip()
        if source_type == "当前工作流表":
            headers = list(current_headers)
            return headers, normalize_rows(current_rows, len(headers)), "当前工作流表"
        if source_type == "SQLite表":
            table = str(config.get("source_sqlite_table", "") or "").strip()
            if not table:
                raise ValueError("请选择 SQLite 来源表。")
            headers, rows = self._load_named_table(table, context)
            return headers, rows, f"SQLite:{table}"
        if source_type == "中转副表":
            name = str(config.get("source_transit_table", "") or "").strip()
            if not name:
                raise ValueError("请选择中转来源表。")
            headers, rows = self._load_transit_table(context, name)
            return headers, rows, f"中转:{name}"
        raise ValueError(f"未知来源类型：{source_type}")

    def _read_selected_columns_target_table(self, config, context, current_headers=None, current_rows=None):
        target_type = str(config.get("target_type", "SQLite表") or "SQLite表").strip()
        if target_type == "当前工作表":
            headers = list(current_headers or [])
            return headers, normalize_rows(current_rows or [], len(headers)), "当前工作表"
        if target_type == "SQLite表":
            table = str(config.get("target_table", "") or "").strip()
            if not table:
                raise ValueError("请输入 SQLite 目标表。")
            try:
                headers, rows = self._load_named_table(table, context)
            except ValueError:
                return [], [], f"SQLite:{table}"
            return headers, rows, f"SQLite:{table}"
        if target_type == "中转副表":
            name = str(config.get("target_transit_table", "") or "").strip() or "选定列结果"
            item = (context.get("transit_tables", {}) or {}).get(name)
            if not item:
                return [], [], f"中转:{name}"
            return list(item.get("headers", []) or []), [list(row) for row in (item.get("rows", []) or [])], f"中转:{name}"
        raise ValueError(f"未知目标类型：{target_type}")

    def _apply_selected_columns_write_transit_table(self, headers, rows, config, context, target_name, target_fields, selected_rows):
        old = (context.get("transit_tables", {}) or {}).get(target_name, {}) or {}
        old_headers = list(old.get("headers", []) or [])
        old_rows = [list(row) for row in (old.get("rows", []) or [])]
        new_headers, new_rows = apply_selected_columns_to_memory_table(
            old_headers,
            old_rows,
            target_fields,
            selected_rows,
            config,
        )
        context.setdefault("transit_tables", {})[target_name] = {
            "headers": new_headers,
            "rows": [list(row) for row in new_rows],
            "source": "选定列写入指定表",
        }
        mode = normalize_selected_columns_write_mode(config.get("write_mode", "局部覆盖，保留目标原行数"))
        context.setdefault("table_access_logs", []).append({
            "time": self.now_factory().strftime("%Y-%m-%d %H:%M:%S"),
            "operation": "write_transit_table",
            "table_name": target_name,
            "status": "ok",
            "source_type": "中转副表",
            "write_mode": mode,
            "message": f"写入中转副表 {target_name}：{len(new_rows)} 行 × {len(new_headers)} 列，模式 {mode}",
        })
        return (
            list(headers),
            [list(row) for row in rows],
            f"已写入中转副表：{target_name}（{len(new_rows)} 行 × {len(new_headers)} 列），主流程数据透传",
        )

    def _apply_selected_columns_write_sqlite_table(self, headers, rows, config, target_name, target_fields, selected_rows):
        mode = normalize_selected_columns_write_mode(config.get("write_mode", "复制列到目标表新建字段"))
        if mode == "覆盖重建目标表":
            result = self.services.write_table(
                target_name,
                {"headers": target_fields, "rows": selected_rows},
                mode="replace",
                backup=bool(config.get("backup_before_write", True)),
            )
            return (
                list(headers),
                [list(row) for row in rows],
                f"已覆盖重建 SQLite 表：{result.get('table_name', target_name)}（{len(selected_rows)} 行 × {len(target_fields)} 列），主流程数据透传",
            )

        target_headers, target_rows, _target_label = self._read_selected_columns_target_table(
            {**config, "target_type": "SQLite表", "target_table": target_name},
            {},
        )
        new_headers, new_rows = apply_selected_columns_to_memory_table(
            target_headers,
            target_rows,
            target_fields,
            selected_rows,
            config,
        )
        result = self.services.write_table(
            target_name,
            {"headers": new_headers, "rows": new_rows},
            mode="replace",
            backup=bool(config.get("backup_before_write", True)),
        )
        return (
            list(headers),
            [list(row) for row in rows],
            f"已复制选定列到 SQLite 表字段：{result.get('table_name', target_name)}（{len(new_rows)} 行 × {len(new_headers)} 列），主流程数据透传",
        )

    def _apply_writeback_node(self, headers, rows, config, context, execute_actions):
        direction = config.get("writeback_direction", "当前表写入SQLite目标表")
        if direction == "其他表写入当前表":
            source_table = str(config.get("source_table", "") or "").strip()
            if not source_table:
                raise ValueError("请选择来源表。")
            source_columns, source_records = self._read_writeback_records(source_table, context)
            return apply_external_table_to_current_node(headers, rows, config, source_columns, source_records)

        table_name = str(config.get("target_table", "") or "").strip()
        if not table_name:
            raise ValueError("请选择目标表。")
        write_range_mode = config.get("write_range_mode", "局部覆盖，保留目标原行数")
        enable_write = bool(config.get("enable_write", False))
        backup_before_write = bool(config.get("backup_before_write", True))
        output_preview = bool(config.get("output_preview_table", True))
        manager = self._make_sqlite_table_manager(context, node_type="字段映射写入表")

        if write_range_mode == "按来源完整结构覆盖":
            target_columns = manager.get_columns(table_name)
            if not target_columns and not manager.table_exists(table_name):
                raise ValueError(f"表不存在：{table_name}")
            actions, full_rows = build_writeback_full_structure_rows_for_sqlite(
                headers,
                rows,
                config,
                target_columns,
            )
            stat = build_writeback_preview_stat(
                write_range_mode,
                actions,
                full_rows=full_rows,
                target_columns=target_columns,
            )
            if execute_actions and enable_write:
                if backup_before_write and manager.table_exists(table_name):
                    manager.backup_table(table_name)
                info = manager.write_table(table_name, target_columns, full_rows, mode="replace")
                stat = build_writeback_full_structure_execute_stat(
                    info.get("table_name", table_name),
                    full_rows,
                    target_columns,
                )
            else:
                stat += get_writeback_non_execute_suffix(execute_actions, enable_write)
            return finish_writeback_node_output(headers, rows, actions, stat, output_preview)

        target_columns, target_records = self._read_writeback_records(table_name, context)
        actions = build_writeback_actions_from_records(headers, rows, config, target_columns, target_records)
        action_counts = count_writeback_actions(actions)
        target_fields = get_writeback_target_fields(config)
        stat = build_writeback_preview_stat(write_range_mode, actions, target_fields=target_fields)

        if should_execute_writeback_update(execute_actions, enable_write, action_counts, write_range_mode):
            backup_name = ""
            if backup_before_write:
                backup_name = manager.backup_table(table_name)
            cleared = 0
            if write_range_mode == "清空目标字段后覆盖，保留目标原行数":
                result = manager.apply_writeback_transaction(
                    table_name,
                    actions,
                    clear_fields=target_fields,
                    cancel_event=context.get("cancel_event"),
                )
                cleared = result.get("cleared_fields", 0)
                actual = result.get("cells", 0)
            else:
                actual = (
                    manager.apply_cell_actions(table_name, actions, cancel_event=context.get("cancel_event"))
                    if action_counts["write_count"] > 0
                    else 0
                )
            stat = build_writeback_execute_stat(table_name, actual, cleared=cleared, backup_name=backup_name)
        else:
            stat += get_writeback_non_execute_suffix(execute_actions, enable_write)
        return finish_writeback_node_output(headers, rows, actions, stat, output_preview)

    def _read_writeback_records(self, table_name, context):
        manager = self._make_sqlite_table_manager(context, node_type="字段映射写入表")
        return manager.read_records(table_name, include_rowid=True, include_row_index=True)

    def _make_sqlite_table_manager(self, context, node_type="HeadlessWorkflowEngine"):
        db_path = self._context_db_path(context) or str(getattr(self.services, "db_path", "") or "").strip()
        if not db_path:
            raise ValueError("请先设置 SQLite 数据库路径。")
        current = (context or {}).get("current_node_info", {}) if isinstance(context, dict) else {}
        return TableAccessManager(
            db_path,
            node_id=current.get("node_id", ""),
            node_name=current.get("node_name", ""),
            node_type=node_type,
            context=context if isinstance(context, dict) else None,
            table_access=current.get("table_access") if isinstance(current, dict) else None,
            permission_policy=(context or {}).get("table_access_policy") if isinstance(context, dict) else None,
        )

    def _context_db_path(self, context):
        if not isinstance(context, dict):
            return ""
        snapshot = context.get("workflow_snapshot") or {}
        if isinstance(snapshot, dict):
            for key in ("db_path", "input_db_path"):
                db_path = str(snapshot.get(key) or "").strip()
                if db_path:
                    return db_path
        for key in ("db_path", "input_db_path"):
            db_path = str(context.get(key) or "").strip()
            if db_path:
                return db_path
        source = context.get("input_source") or context.get("source") or {}
        if isinstance(source, dict):
            return str(source.get("db_path") or "").strip()
        return ""

    def _make_file_node_context(self, context, cancel_event):
        node_context = self._make_node_context(context, cancel_event)
        node_context.setdefault("default_directory", os.getcwd())

        def report_progress(current=None, total=None, message="", node_name="获取文件列表"):
            callback = (context or {}).get("progress_callback") if isinstance(context, dict) else None
            self._emit(callback, {
                "type": "node_progress",
                "current": current,
                "total": total,
                "message": message,
                "node_name": node_name,
            })

        node_context["report_progress"] = report_progress
        return node_context

    def _make_batch_rename_context(self, context, cancel_event):
        node_context = self._make_file_node_context(context, cancel_event)
        node_context.update({
            "path_exists": os.path.exists,
            "path_is_dir": os.path.isdir,
            "make_dirs": lambda path: os.makedirs(path, exist_ok=True),
            "rename_file": os.rename,
            "replace_file": os.replace,
            "make_numbered_path": make_numbered_path,
        })
        return node_context

    def _apply_batch_rename_node(self, headers, rows, config, context, execute_actions, cancel_event):
        node_context = self._make_batch_rename_context(context, cancel_event)
        result_headers, result_rows, message = apply_batch_rename_node(
            headers,
            rows,
            config,
            execute_actions=execute_actions,
            context=node_context,
        )
        if node_context.get("batch_rename_do_rename") and bool(config.get("write_log", True)):
            try:
                self._write_batch_rename_log(config, node_context)
            except Exception as exc:
                changed = node_context.get("batch_rename_changed", 0)
                message = f"重命名完成 {changed} 项，但日志写入失败：{exc}"
        if isinstance(context, dict):
            context["batch_rename_log_rows"] = list(node_context.get("batch_rename_log_rows", []))
            context["batch_rename_changed"] = node_context.get("batch_rename_changed", 0)
            context["batch_rename_preview_ok"] = node_context.get("batch_rename_preview_ok", 0)
            context["batch_rename_skipped"] = node_context.get("batch_rename_skipped", 0)
            context["batch_rename_do_rename"] = bool(node_context.get("batch_rename_do_rename"))
        return result_headers, result_rows, message

    def _write_batch_rename_log(self, config, node_context):
        log_path = config.get("log_path") or os.path.abspath("rename_log.csv")
        os.makedirs(os.path.dirname(os.path.abspath(log_path)), exist_ok=True)
        with open(log_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(BATCH_RENAME_LOG_HEADERS)
            writer.writerows(node_context.get("batch_rename_log_rows", []))

    def _apply_plugin_node(self, headers, rows, node_type_id, config, context, execute_actions):
        plugin_id = str(config.get("plugin_id") or node_type_id.split(".", 1)[1]).strip()
        params = dict(config.get("params", {}) or {})
        failure_policy = config.get("plugin_failure_policy", "停止工作流")
        result = self.plugins.run_plugin(
            plugin_id,
            input_table={"headers": headers, "rows": rows},
            params=params,
            context=context,
            config=config,
            execute_actions=execute_actions,
        )
        plugin_name = plugin_id
        plugin = result.get("plugin") if isinstance(result, dict) else None
        if isinstance(plugin, dict):
            plugin_name = plugin.get("name") or plugin_id

        if not result.get("ok"):
            issue = (result.get("issues") or [{}])[0]
            message = issue.get("message") or "插件执行失败"
            log_items = normalize_plugin_logs(
                [{"level": "ERROR", "message": message}],
                plugin_id=plugin_id,
                node_name=config.get("name") or "插件节点",
                now_text=self.now_factory().strftime("%Y-%m-%d %H:%M:%S"),
            )
            self._save_plugin_log_outputs(plugin_id, plugin_name, config, log_items, context, execute_actions)
            if failure_policy == "停止工作流":
                raise ValueError(message)
            new_headers, new_rows = build_plugin_failure_output(
                plugin_id,
                message,
                "",
                headers,
                rows,
                failure_policy,
            )
            stat = build_plugin_status_text(
                plugin_name,
                plugin_id,
                False,
                failure_policy,
                message,
                {"ok": False},
                [],
                [],
                log_items,
            )
            return new_headers, new_rows, stat

        normalized = result["result"]
        new_headers = list(normalized.get("headers", headers))
        new_rows = [list(row) for row in normalized.get("rows", rows)]
        log_items = normalize_plugin_logs(
            normalized.get("logs", []),
            plugin_id=plugin_id,
            node_name=config.get("name") or "插件节点",
            now_text=self.now_factory().strftime("%Y-%m-%d %H:%M:%S"),
        )
        log_saved_parts = self._save_plugin_log_outputs(plugin_id, plugin_name, config, log_items, context, execute_actions)
        transit_parts = self._save_plugin_result_transit_output(config, plugin_id, context, new_headers, new_rows)
        output_mode = config.get("output_mode", "使用插件返回结果")
        final_headers, final_rows = build_plugin_final_output(
            headers,
            rows,
            new_headers,
            new_rows,
            output_mode,
        )
        stat = build_plugin_status_text(
            plugin_name,
            plugin_id,
            True,
            failure_policy,
            normalized.get("message", ""),
            normalized.get("summary", {}),
            transit_parts,
            log_saved_parts,
            log_items,
        )
        return final_headers, final_rows, stat

    def _save_plugin_result_transit_output(self, config, plugin_id, context, headers, rows):
        if not should_save_plugin_output_as_transit(config):
            return []
        name = str(config.get("transit_name") or plugin_id or "插件输出").strip() or "插件输出"
        mode = str(config.get("transit_conflict_mode") or "覆盖").strip()
        old = (context.get("transit_tables", {}) or {}).get(name, {}) if isinstance(context, dict) else {}
        if mode == "追加" and old:
            from workflow.nodes.transit_nodes import append_headers_rows

            new_headers, new_rows = append_headers_rows(
                old.get("headers", []) or [],
                old.get("rows", []) or [],
                headers,
                rows,
            )
        else:
            new_headers = list(headers)
            new_rows = [list(row) for row in rows]
        if isinstance(context, dict):
            context.setdefault("transit_tables", {})[name] = {
                "headers": new_headers,
                "rows": [list(row) for row in new_rows],
                "source": "插件输出",
            }
        return [f"中转副表：{name}"]

    def _save_plugin_log_outputs(self, plugin_id, plugin_name, config, log_items, context, execute_actions):
        if not log_items:
            return []
        saved = []
        if bool(config.get("save_plugin_log_transit", False)) and (execute_actions or bool(config.get("plugin_log_in_preview", False))):
            name = str(config.get("plugin_log_transit_name") or f"{plugin_name}_日志").strip() or f"{plugin_name}_日志"
            log_headers, log_rows = plugin_log_items_to_table(log_items)
            if isinstance(context, dict):
                context.setdefault("transit_tables", {})[name] = {
                    "headers": log_headers,
                    "rows": [list(row) for row in log_rows],
                    "source": "插件日志",
                }
            saved.append(f"中转副表：{name}")
        if bool(config.get("save_plugin_log_sqlite", False)) and execute_actions:
            log_headers, log_rows = plugin_log_items_to_table(log_items)
            table_name = str(config.get("plugin_log_table") or f"{plugin_id}_日志").strip() or "插件日志"
            self.services.write_table(table_name, {"headers": log_headers, "rows": log_rows}, mode="append", backup=False)
            saved.append(f"SQLite日志：{len(log_rows)}条")
        return saved

    def _apply_save_transit_node(self, headers, rows, config, context, execute_actions):
        context.setdefault("transit_tables", {})
        result_headers, result_rows, stat = apply_save_transit_node(
            headers,
            rows,
            config,
            context=context,
            execute_actions=execute_actions,
        )
        options = context.get("save_transit_options", {}) or {}
        headers_copy = context.get("save_transit_headers") or list(headers)
        rows_copy = context.get("save_transit_rows") or [list(row) for row in rows]
        saved_parts = stat.split("；") if stat else []
        memory_part = self._apply_save_transit_memory_plan(context, headers_copy, rows_copy)
        if memory_part and memory_part not in saved_parts:
            saved_parts.insert(0, memory_part)
        if execute_actions and options.get("save_sqlite"):
            saved_parts.append(self._execute_save_transit_sqlite(options, headers_copy, rows_copy))
        if execute_actions and options.get("save_xlsx"):
            saved_parts.append(self._execute_save_transit_xlsx(options, headers_copy, rows_copy))
        if not saved_parts:
            saved_parts.append("未选择保存位置，仅透传数据")
        return result_headers, result_rows, "；".join(saved_parts)

    def _apply_save_transit_memory_plan(self, context, headers_copy, rows_copy):
        memory_plan = context.get("save_transit_memory_plan")
        if not memory_plan:
            return ""
        table_name = memory_plan["table_name"]
        context.setdefault("transit_tables", {})[table_name] = {
            "headers": list(memory_plan.get("headers", headers_copy)),
            "rows": [list(row) for row in memory_plan.get("rows", rows_copy)],
            "source": memory_plan.get("source", "保存中转数据:覆盖"),
        }
        context.setdefault("table_access_logs", []).append({
            "time": self.now_factory().strftime("%Y-%m-%d %H:%M:%S"),
            "operation": memory_plan.get("operation", "write_transit_table"),
            "table_name": table_name,
            "status": "ok",
            "source_type": "中转副表",
            "write_mode": memory_plan.get("write_mode", ""),
            "message": memory_plan.get("log_message", ""),
        })
        return memory_plan.get("status", "")

    def _execute_save_transit_sqlite(self, options, headers, rows):
        mode_text = str(options.get("sqlite_mode", "自动加时间戳") or "")
        if mode_text == "覆盖同名表":
            mode = "replace"
        elif mode_text == "追加写入":
            mode = "append"
        elif mode_text == "报错停止":
            mode = "fail"
        else:
            mode = "timestamp"
        result = self.services.write_table(
            options.get("sqlite_table_raw") or options.get("base_name") or "中转数据",
            {"headers": headers, "rows": rows},
            mode=mode,
            backup=True,
        )
        suffix = "（追加写入）" if mode == "append" else ""
        return f"SQLite表：{result.get('table_name', '')}{suffix}"

    def _execute_save_transit_xlsx(self, options, headers, rows):
        path = str(options.get("xlsx_path", "") or "").strip()
        if not path:
            path = f"{options.get('base_name', '中转数据')}.xlsx"
        result = self.services.export_xlsx(path, {"headers": headers, "rows": rows}, sheet_name=options.get("base_name", "中转数据"))
        return f"xlsx：{result.get('path', path)}"

    def _apply_group_node(self, headers, rows, config, context, execute_actions, cancel_event):
        parent_context = ensure_group_parent_context(context)
        nodes = config.get("nodes", []) or []
        if not isinstance(nodes, list):
            raise ValueError("节点组 config.nodes 必须是 list。")
        self._ensure_group_inner_nodes_supported(nodes)
        group_name = str(config.get("group_name") or "节点组").strip() or "节点组"

        source_headers, source_rows, source_name = self._read_group_source_table(
            headers,
            rows,
            config,
            parent_context,
        )
        cur_headers, cur_rows, input_stat = build_group_input_table(
            source_headers,
            source_rows,
            config,
        )

        if not nodes:
            output_parts = self._write_group_outputs(
                cur_headers,
                cur_rows,
                config,
                parent_context,
                execute_actions=execute_actions,
            )
            if config.get("main_output_mode", "输出为当前工作表") == "透传原当前表":
                stat = build_empty_group_stat(
                    group_name,
                    source_name,
                    input_stat,
                    output_parts,
                    passthrough_current=True,
                )
                return list(headers), [list(row) for row in rows], stat
            stat = build_empty_group_stat(group_name, source_name, input_stat, output_parts)
            return cur_headers, cur_rows, stat

        child_context = make_group_child_context(parent_context, config)
        self._prepare_group_child_context(parent_context, child_context)
        child_plan = {"nodes": copy.deepcopy(nodes), "headers": cur_headers, "rows": cur_rows}
        child_result = self.run_plan(
            child_plan,
            execute_actions=execute_actions,
            dry_run=bool(parent_context.get("dry_run", False)),
            initial_context=child_context,
            progress_callback=parent_context.get("progress_callback"),
            cancel_event=cancel_event or parent_context.get("cancel_event"),
            return_context=True,
        )
        cur_headers = list(child_result.headers)
        cur_rows = [list(row) for row in child_result.rows]
        self._merge_group_child_context(parent_context, child_result.context, config)

        output_parts = self._write_group_outputs(
            cur_headers,
            cur_rows,
            config,
            parent_context,
            execute_actions=execute_actions,
        )
        final_headers, final_rows, main_stat = build_group_final_output(
            headers,
            rows,
            cur_headers,
            cur_rows,
            config,
        )
        stat = build_group_status_text(
            group_name,
            source_name,
            input_stat,
            main_stat,
            logs=child_result.logs,
            output_parts=output_parts,
        )
        return final_headers, final_rows, stat

    def _ensure_group_inner_nodes_supported(self, nodes):
        for index, node in enumerate(nodes or [], start=1):
            if not isinstance(node, dict):
                raise ValueError(f"节点组内第 {index} 个节点必须是 dict。")
            if not node.get("enabled", True):
                continue
            node_type_id = self._node_type_id_from_node(node)
            node_label = self._node_label(node, node_type_id)
            if node_type_id in ("core.loop_start", "core.loop_judge"):
                raise ValueError(f"第一版节点组暂不支持组内循环节点：{node_label}")
            if not self.is_node_supported(node_type_id):
                raise ValueError(f"节点组内节点暂不支持 headless 执行：{node_label}")
            if node_type_id == "core.group":
                self._ensure_group_inner_nodes_supported((node.get("config") or {}).get("nodes", []) or [])

    def _read_group_source_table(self, headers, rows, config, context):
        source_type = str(config.get("input_source_type", "当前工作表") or "当前工作表").strip()
        if source_type == "当前工作表":
            fixed_headers = list(headers)
            return fixed_headers, normalize_rows(rows, len(fixed_headers)), "当前工作表"
        if source_type == "中转副表":
            name = str(config.get("input_transit_table", "") or "").strip()
            if not name:
                raise ValueError("节点组入口选择了中转副表，但没有填写中转副表名。")
            source_headers, source_rows = self._load_transit_table(context, name)
            self._record_table_access_log(
                context,
                "read_transit_table",
                name,
                "ok",
                "中转副表",
                "",
                f"节点组入口读取中转副表 {name}：{len(source_rows)} 行 × {len(source_headers)} 列",
            )
            return source_headers, source_rows, f"中转副表:{name}"
        if source_type == "SQLite表":
            name = str(config.get("input_sqlite_table", "") or "").strip()
            if not name:
                raise ValueError("节点组入口选择了 SQLite 表，但没有填写表名。")
            source_headers, source_rows = self._load_named_table(name, context)
            return source_headers, source_rows, f"SQLite:{name}"
        fixed_headers = list(headers)
        return fixed_headers, normalize_rows(rows, len(fixed_headers)), "当前工作表"

    def _prepare_group_child_context(self, parent_context, child_context):
        for key in (
            "execute_actions",
            "dry_run",
            "safety_policy",
            "table_sources",
            "tables",
            "table_access_policy",
            "selected_columns_config_preview_only",
            "allow_selected_columns_write_in_preview",
        ):
            if key in parent_context and key not in child_context:
                child_context[key] = copy.deepcopy(parent_context[key])

    def _merge_group_child_context(self, parent_context, child_context, config):
        if config.get("transit_scope", "组内中转私有") == "允许输出到外部":
            parent_context["transit_tables"] = copy.deepcopy(child_context.get("transit_tables", {}) or {})
        merge_group_child_audit_logs(parent_context, child_context)
        if child_context.get("ui_refresh_requests"):
            requests = parent_context.setdefault("ui_refresh_requests", [])
            for item in child_context.get("ui_refresh_requests", []) or []:
                if item not in requests:
                    requests.append(item)

    def _write_group_outputs(self, result_headers, result_rows, config, parent_context, *, execute_actions=False):
        parts = []
        parent_context = ensure_group_parent_context(parent_context)
        if config.get("save_to_transit", False):
            name = str(config.get("output_transit_name") or config.get("group_name") or "节点组结果").strip() or "节点组结果"
            conflict = normalize_group_transit_conflict_mode(config.get("output_transit_conflict_mode", "覆盖整表"))
            parts.append(self._save_group_output_to_transit(
                parent_context,
                name,
                result_headers,
                result_rows,
                conflict,
                source=f"节点组:{config.get('group_name', '节点组')}",
            ))

        sqlite_preview_only = bool(parent_context.get("selected_columns_config_preview_only", False))
        if config.get("save_to_sqlite", False) and (not execute_actions or sqlite_preview_only):
            parts.append("SQLite保存已跳过：仅执行计划时保存")
        elif config.get("save_to_sqlite", False):
            table_name = str(config.get("output_sqlite_table") or config.get("group_name") or "节点组结果").strip()
            if not table_name:
                raise ValueError("节点组已启用 SQLite 输出，但未填写 SQLite 表名。")
            mode = normalize_group_sqlite_mode(config.get("output_sqlite_mode", "自动加时间戳新表"))
            info = self.services.write_table(
                table_name,
                {"headers": result_headers, "rows": result_rows},
                mode=mode,
                backup=True,
            )
            parts.append(f"SQLite表：{info.get('table_name')}（{info.get('rows')}行）")
            requests = parent_context.setdefault("ui_refresh_requests", [])
            if "table_list" not in requests:
                requests.append("table_list")
        return parts

    def _save_group_output_to_transit(self, context, name, headers, rows, conflict_mode="覆盖", source="节点组"):
        transit_tables = context.setdefault("transit_tables", {})
        base_name = str(name or "节点组结果").strip() or "节点组结果"
        headers = list(headers or [])
        rows = [list(row) for row in (rows or [])]
        exists_before = base_name in transit_tables
        if conflict_mode == "自动加时间戳":
            final_name = make_unique_transit_name(base_name, transit_tables)
            self._write_context_transit_table(
                context,
                final_name,
                headers,
                rows,
                source=source,
                operation="write_transit_table",
                write_mode=conflict_mode,
                message=f"写入中转副表 {final_name}：{len(rows)} 行 × {len(headers)} 列",
            )
            return f"中转副表：{final_name}"
        if conflict_mode == "追加" and exists_before:
            old = transit_tables.get(base_name, {}) or {}
            merged_headers, merged_rows = append_headers_rows(
                old.get("headers", []) or [],
                old.get("rows", []) or [],
                headers,
                rows,
            )
            self._write_context_transit_table(
                context,
                base_name,
                merged_headers,
                merged_rows,
                source=f"{source}:追加",
                operation="append_transit_table",
                write_mode=conflict_mode,
                message=f"追加中转副表 {base_name}：新增 {len(rows)} 行，累计 {len(merged_rows)} 行",
            )
            return f"中转副表追加：{base_name}（新增 {len(rows)} 行，累计 {len(merged_rows)} 行）"
        self._write_context_transit_table(
            context,
            base_name,
            headers,
            rows,
            source=source,
            operation="write_transit_table",
            write_mode=conflict_mode or "覆盖",
            message=f"写入中转副表 {base_name}：{len(rows)} 行 × {len(headers)} 列",
        )
        return f"中转副表：{base_name}"

    def _apply_loop_start_node(self, headers, rows, config, context, nodes, *, node_index=0, end_index=None):
        context.setdefault("loop_states", {})
        context.setdefault("transit_tables", {})
        loop_id = str(config.get("loop_id", "loop") or "loop").strip() or "loop"
        state = context["loop_states"].get(loop_id)
        if state is None:
            source_headers, source_rows, source_name = self._read_loop_source_table(
                headers,
                rows,
                config,
                context,
            )
            state = init_loop_state_from_source(source_headers, source_rows, source_name, config)
            context["loop_states"][loop_id] = state

        start_result = take_next_loop_item(state)
        table_name = start_result.get("table_name", "当前循环项") or "当前循环项"
        current_headers = list(start_result.get("current_headers", []) or [])
        transit_rows = [list(row) for row in (start_result.get("transit_rows", []) or [])]
        self._write_context_transit_table(
            context,
            table_name,
            current_headers,
            transit_rows,
            source=start_result.get("transit_source", f"循环:{loop_id}:当前项"),
            operation="write_transit_table",
            write_mode="覆盖当前循环项",
            message=(
                f"循环执行起点写入空当前项中转副表 {table_name}"
                if start_result.get("no_pending")
                else f"循环执行起点写入当前项中转副表 {table_name}：1 行 × {len(current_headers)} 列"
            ),
        )
        result_headers, result_rows, stat, ctrl = build_loop_start_output(
            headers,
            rows,
            start_result,
            output_current_as_table=config.get("output_current_as_table", True),
        )
        jump_to = None
        if ctrl.get("no_pending"):
            judge_idx = self._find_loop_judge_index(loop_id, node_index, end_index, nodes)
            if judge_idx is not None:
                jump_to = judge_idx + 1
                target_text = f"节点 {jump_to + 1}" if end_index is None or jump_to <= end_index else "结束"
                stat += f"；无待执行项，跳过循环体到{target_text}"
        return result_headers, result_rows, stat, jump_to

    def _read_loop_source_table(self, headers, rows, config, context):
        source_type = str(config.get("source_type", "当前表") or "当前表").strip()
        if source_type == "当前表":
            fixed_headers = list(headers)
            return fixed_headers, normalize_rows(rows, len(fixed_headers)), "当前表"
        if source_type == "SQLite表":
            table_name = str(config.get("source_table", "") or "").strip()
            if not table_name:
                raise ValueError("循环执行起点未选择 SQLite 来源表。")
            source_headers, source_rows = self._load_named_table(table_name, context)
            return source_headers, source_rows, f"SQLite:{table_name}"
        if source_type == "中转副表":
            name = str(config.get("transit_table", "") or "").strip()
            if not name:
                raise ValueError("循环执行起点未选择中转副表。")
            source_headers, source_rows = self._load_transit_table(context, name)
            self._record_table_access_log(
                context,
                "read_transit_table",
                name,
                "ok",
                "中转副表",
                "",
                f"循环执行起点读取中转副表 {name}：{len(source_rows)} 行 × {len(source_headers)} 列",
            )
            return source_headers, source_rows, f"中转:{name}"
        fixed_headers = list(headers)
        return fixed_headers, normalize_rows(rows, len(fixed_headers)), "当前表"

    def _apply_loop_judge_node(self, headers, rows, config, context, nodes, *, node_index=0):
        loop_id = str(config.get("loop_id", "") or "").strip()
        if not loop_id:
            raise ValueError("循环判断回跳节点未绑定循环执行起点。")
        state = context.setdefault("loop_states", {}).get(loop_id)
        if not state:
            raise ValueError(f"未找到循环状态：{loop_id}。请确认循环执行起点在本节点之前。")
        judge_result = apply_loop_judge_to_state(
            headers,
            rows,
            config,
            state,
            now_text=self.now_factory().strftime("%Y-%m-%d %H:%M:%S"),
        )
        if judge_result.get("no_current"):
            ctrl = judge_result.get("ctrl", {}) or {}
            return list(headers), [list(row) for row in rows], judge_result["stat"], ctrl.get("jump_to")

        result_headers = judge_result["result_headers"]
        result_row = judge_result["result_row"]
        results = context.setdefault("loop_results", {}).setdefault(
            loop_id,
            {"headers": list(result_headers), "rows": []},
        )
        results["headers"] = list(result_headers)
        results["rows"].append(list(result_row))

        result_name = str(config.get("result_table_name", "循环结果") or "循环结果").strip() or "循环结果"
        result_rows = [list(row) for row in results["rows"]]
        self._write_context_transit_table(
            context,
            result_name,
            result_headers,
            result_rows,
            source=f"循环:{loop_id}:结果",
            operation="write_transit_table",
            write_mode="覆盖循环结果",
            message=f"循环判断回跳写入结果中转副表 {result_name}：{len(result_rows)} 行 × {len(result_headers)} 列",
        )

        queue_name = judge_result["queue_name"]
        queue_headers = judge_result["queue_headers"]
        queue_rows = judge_result["queue_rows"]
        self._write_context_transit_table(
            context,
            queue_name,
            queue_headers,
            queue_rows,
            source=f"循环:{loop_id}:队列",
            operation="write_transit_table",
            write_mode="覆盖循环队列",
            message=f"循环判断回跳写入队列中转副表 {queue_name}：{len(queue_rows)} 行 × {len(queue_headers)} 列",
        )

        result_headers, result_rows, stat, ctrl = build_loop_judge_output(
            headers,
            rows,
            config,
            state,
            judge_result,
            results["rows"],
        )
        jump_to = ctrl.get("jump_to") if isinstance(ctrl, dict) else None
        if jump_to == "__LOOP_START__":
            jump_to = self._find_loop_start_index(loop_id, node_index, nodes)
            if jump_to is None:
                raise RuntimeError(f"未找到循环起点：{loop_id}")
        return result_headers, result_rows, stat, jump_to

    def _write_context_transit_table(
        self,
        context,
        table_name,
        headers,
        rows,
        *,
        source="",
        operation="write_transit_table",
        write_mode="",
        message="",
    ):
        context.setdefault("transit_tables", {})[table_name] = {
            "headers": list(headers or []),
            "rows": [list(row) for row in (rows or [])],
            "source": source,
        }
        self._record_table_access_log(
            context,
            operation,
            table_name,
            "ok",
            "中转副表",
            write_mode,
            message,
        )

    def _record_table_access_log(self, context, operation, table_name, status, source_type, write_mode, message):
        context.setdefault("table_access_logs", []).append({
            "time": self.now_factory().strftime("%Y-%m-%d %H:%M:%S"),
            "operation": operation,
            "table_name": table_name,
            "status": status,
            "source_type": source_type,
            "write_mode": write_mode,
            "message": message,
        })

    def _find_loop_start_index(self, loop_id, current_idx, nodes):
        for idx in range(int(current_idx) - 1, -1, -1):
            node = nodes[idx]
            if (
                isinstance(node, dict)
                and node.get("enabled", True)
                and self._node_type_id_from_node(node) == "core.loop_start"
                and str((node.get("config") or {}).get("loop_id", "") or "").strip() == loop_id
            ):
                return idx
        return None

    def _find_loop_judge_index(self, loop_id, start_idx, end_idx, nodes):
        last_idx = len(nodes) - 1 if end_idx is None else min(int(end_idx), len(nodes) - 1)
        for idx in range(int(start_idx) + 1, last_idx + 1):
            node = nodes[idx]
            if (
                isinstance(node, dict)
                and node.get("enabled", True)
                and self._node_type_id_from_node(node) == "core.loop_judge"
                and str((node.get("config") or {}).get("loop_id", "") or "").strip() == loop_id
            ):
                return idx
        return None

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
