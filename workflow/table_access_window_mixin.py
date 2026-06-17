# -*- coding: utf-8 -*-
"""PlanWorkflowWindow mixin for table-access window wrappers."""

import copy
import os

from db import TableAccessManager
from workflow import plan_workflow_ui
from workflow import table_access_audit_ui
from workflow import table_access_window_ui
from workflow.table_access_defaults import (
    build_default_table_access_for_node as workflow_build_default_table_access_for_node,
)
from workflow.table_access_precheck import (
    evaluate_node_table_access_precheck,
    evaluate_workflow_output_precheck,
    find_matching_table_access_entry as workflow_find_matching_table_access_entry,
    find_table_access_field_rule as workflow_find_table_access_field_rule,
    iter_nodes_for_table_access_precheck,
    make_table_access_precheck_issue as workflow_make_table_access_precheck_issue,
    normalize_precheck_transit_name as workflow_normalize_precheck_transit_name,
    table_access_entry_match_score as workflow_table_access_entry_match_score,
    table_access_entry_status as workflow_table_access_entry_status,
    table_access_entry_table_label as workflow_table_access_entry_table_label,
    table_access_field_items as workflow_table_access_field_items,
    table_access_operation_summary as workflow_table_access_operation_summary,
    table_access_precheck_actionable as workflow_table_access_precheck_actionable,
    table_access_precheck_blocking as workflow_table_access_precheck_blocking,
    table_access_precheck_summary_text as workflow_table_access_precheck_summary_text,
    table_access_precheck_sort_key,
)
from workflow.table_access_window_ui import (
    apply_auto_field_mapping_by_name as workflow_apply_auto_field_mapping_by_name,
    apply_auto_field_mapping_by_order as workflow_apply_auto_field_mapping_by_order,
    make_table_access_field_key as workflow_make_table_access_field_key,
    table_access_preset_config as workflow_table_access_preset_config,
)


class TableAccessWindowMixin:
    """Compatibility methods used by table-access UI modules."""

    def normalize_table_access_policy(self, value=None):
        if value is None:
            value = self.table_access_policy_var.get()
        return TableAccessManager.normalize_permission_policy(value)

    def table_access_policy_display(self, value=None):
        policy = self.normalize_table_access_policy(value)
        return self.TABLE_ACCESS_POLICY_DISPLAY.get(policy, "只审计")

    def set_table_access_policy(self, value):
        self.table_access_policy_var.set(self.table_access_policy_display(value))

    def normalize_table_access_write_mode(self, mode):
        return TableAccessManager.normalize_write_mode(mode)

    def write_mode_permission_set(self, mode, exists=False, read=False, partial=False):
        perms = {key: False for key, _ in self.table_access_permission_items()}
        for key in TableAccessManager.required_permissions_for_write_mode(mode, exists=exists, partial=partial):
            if key in perms:
                perms[key] = True
        if read:
            perms["read_table"] = True
        return perms

    def write_mode_display_text(self, mode):
        standard = self.normalize_table_access_write_mode(mode)
        labels = {
            "": "",
            "current_table_default": "当前表默认",
            "create_new": "新建表写入",
            "append": "追加行",
            "overlay_by_order": "按顺序覆盖",
            "update_by_key": "按键更新",
            "upsert_by_key": "匹配更新或追加",
            "clear_keep_schema": "清空保留结构写入",
            "keep_schema_insert": "保留结构写入",
            "replace_table": "替换整表",
            "timestamp_new": "自动时间戳新表",
            "fail_if_exists": "存在则报错",
            "write_fields_only": "指定字段写入",
            "fill_blank_fields": "字段空缺补齐",
        }
        return labels.get(standard, str(mode or ""))

    def table_permission_set(self, read=False, write=False, create=False, append=False, update=False,
                             clear=False, replace=False, alter=False, delete=False, drop=False):
        return {
            "read_table": bool(read),
            "write_table": bool(write),
            "create_table": bool(create),
            "append_rows": bool(append),
            "update_rows": bool(update),
            "clear_table": bool(clear),
            "replace_table": bool(replace),
            "alter_schema": bool(alter),
            "delete_rows": bool(delete),
            "drop_table": bool(drop),
        }

    def make_table_access_entry(self, role, table, source_type="SQLite表", is_current_table=False,
                                permissions=None, write_mode="", field_mapping=None, log_only=False,
                                table_pattern="", pattern_type="glob", declared_by=""):
        return {
            "role": role,
            "table": table,
            "table_pattern": str(table_pattern or "").strip(),
            "pattern_type": str(pattern_type or "glob").strip(),
            "declared_by": str(declared_by or "").strip(),
            "source_type": source_type,
            "is_current_table": bool(is_current_table),
            "permissions": permissions or self.table_permission_set(read=True),
            "write_mode": self.normalize_table_access_write_mode(write_mode),
            "field_mapping_mode": "by_name",
            "field_mapping": field_mapping or {},
            "log_only": bool(log_only),
        }

    def get_plugin_table_access_specs(self, config):
        config = config or {}
        plugin_id = str(config.get("plugin_id", "") or "").strip()
        item = self.plugin_registry.get(plugin_id, {}) if hasattr(self, "plugin_registry") else {}
        module = item.get("module")
        params = dict(config.get("params", {}) or {})
        specs = None
        provider = getattr(module, "get_table_access_spec", None) if module is not None else None
        if callable(provider):
            try:
                specs = provider(params, {"plugin_id": plugin_id, "config_probe": True})
            except TypeError:
                specs = provider(params)
            except Exception:
                specs = None
        if specs is None:
            info = item.get("info", {}) or {}
            specs = info.get("table_access") or info.get("table_access_spec") or []
        if isinstance(specs, dict):
            specs = specs.get("tables") or [specs]
        return [spec for spec in (specs or []) if isinstance(spec, dict)]

    def plugin_has_table_access_declaration(self, config):
        config = config or {}
        plugin_id = str(config.get("plugin_id", "") or "").strip()
        item = self.plugin_registry.get(plugin_id, {}) if hasattr(self, "plugin_registry") else {}
        module = item.get("module")
        if callable(getattr(module, "get_table_access_spec", None)):
            return True
        info = item.get("info", {}) or {}
        return bool(info.get("table_access") or info.get("table_access_spec"))

    def plugin_needs_table_access_declaration(self, config):
        config = config or {}
        plugin_id = str(config.get("plugin_id", "") or "").strip()
        item = self.plugin_registry.get(plugin_id, {}) if hasattr(self, "plugin_registry") else {}
        info = item.get("info", {}) or {}
        danger = str(info.get("danger_level", "") or "").strip().lower()
        return danger in {"db_write", "database_write"} or bool(info.get("database_requests"))

    def make_plugin_declared_access_entry(self, plugin_id, spec):
        spec = spec or {}
        permissions = {key: False for key, _ in self.table_access_permission_items()}
        permissions.update({
            key: bool(value)
            for key, value in (spec.get("permissions") or {}).items()
            if key in permissions
        })
        return self.make_table_access_entry(
            spec.get("role") or "plugin_declared",
            spec.get("table") or "",
            source_type=spec.get("source_type") or "SQLite表",
            is_current_table=bool(spec.get("is_current_table")),
            permissions=permissions,
            write_mode=spec.get("write_mode") or "",
            field_mapping=copy.deepcopy(spec.get("field_mapping") or {}),
            log_only=bool(spec.get("log_only")),
            table_pattern=spec.get("table_pattern") or "",
            pattern_type=spec.get("pattern_type") or "glob",
            declared_by=plugin_id,
        )

    def default_table_access_for_node(self, node):
        return workflow_build_default_table_access_for_node(
            node,
            self.make_table_access_entry,
            self.table_permission_set,
            normalize_selected_columns_write_mode=getattr(self, "normalize_selected_columns_write_mode", None),
            normalize_group_transit_conflict_mode=getattr(self, "normalize_group_transit_conflict_mode", None),
            get_plugin_table_access_specs=self.get_plugin_table_access_specs,
            make_plugin_declared_access_entry=self.make_plugin_declared_access_entry,
        )

    def ensure_node_identity(self, node, force_new=False):
        if not isinstance(node, dict):
            return node
        if force_new or not str(node.get("node_id", "")).strip():
            node["node_id"] = self.make_node_id()
        if not isinstance(node.get("table_access"), dict):
            node["table_access"] = self.default_table_access_for_node(node)
        return node

    def ensure_node_tree_identity(self, nodes, force_new=False):
        for node in nodes or []:
            self.ensure_node_identity(node, force_new=force_new)
            cfg = node.get("config", {}) if isinstance(node, dict) else {}
            child_nodes = cfg.get("nodes") if isinstance(cfg, dict) else None
            if isinstance(child_nodes, list):
                self.ensure_node_tree_identity(child_nodes, force_new=force_new)

    def refresh_node_table_access(self, node):
        if isinstance(node, dict) and (
            not isinstance(node.get("table_access"), dict)
            or bool(node.get("table_access", {}).get("auto_generated", True))
        ):
            node["table_access"] = self.default_table_access_for_node(node)
        return node

    def refresh_node_tree_table_access(self, nodes):
        for node in nodes or []:
            self.ensure_node_identity(node)
            self.refresh_node_table_access(node)
            cfg = node.get("config", {}) if isinstance(node, dict) else {}
            child_nodes = cfg.get("nodes") if isinstance(cfg, dict) else None
            if isinstance(child_nodes, list):
                self.refresh_node_tree_table_access(child_nodes)

    def table_access_permission_items(self):
        return [
            ("read_table", "读表"),
            ("write_table", "写表"),
            ("create_table", "新建表"),
            ("append_rows", "追加行"),
            ("update_rows", "更新行"),
            ("clear_table", "清空表"),
            ("replace_table", "替换表"),
            ("alter_schema", "改结构"),
            ("delete_rows", "删行"),
            ("drop_table", "删表"),
        ]

    def field_permission_items(self):
        return [
            ("read_field", "可读"),
            ("write_field", "可写"),
            ("create_field", "可创建"),
            ("protect_field", "保护"),
        ]

    def get_node_table_access(self, node):
        self.ensure_node_identity(node)
        access = node.get("table_access")
        if not isinstance(access, dict):
            access = self.default_table_access_for_node(node)
            node["table_access"] = access
        access.setdefault("version", 1)
        tables = access.get("tables")
        if not isinstance(tables, list):
            access["tables"] = []
        return access

    def mark_node_table_access_manual(self, node):
        access = self.get_node_table_access(node)
        access["auto_generated"] = False
        return access

    def table_access_table_choices(self, node=None):
        values = ["__CURRENT_TABLE__"]
        try:
            values.extend(self.app.get_table_names())
        except Exception:
            pass
        if isinstance(node, dict):
            for entry in self.get_node_table_access(node).get("tables", []):
                table = str((entry or {}).get("table", "") or "").strip()
                if table:
                    values.append(table)
        result = []
        for value in values:
            if value not in result:
                result.append(value)
        return result

    def table_permission_summary(self, entry):
        perms = (entry or {}).get("permissions") or {}
        labels = []
        label_map = dict(self.table_access_permission_items())
        for key, _ in self.table_access_permission_items():
            if perms.get(key):
                labels.append(label_map.get(key, key))
        if not labels:
            return "无权限"
        return "/".join(labels[:4]) + ("..." if len(labels) > 4 else "")

    def table_access_entry_table_label(self, entry):
        return workflow_table_access_entry_table_label(entry)

    def table_access_operation_summary(self, entry):
        return workflow_table_access_operation_summary(
            entry,
            write_mode_formatter=self.write_mode_display_text,
        )

    def table_access_entry_status(self, entry):
        return workflow_table_access_entry_status(entry)

    def table_access_node_status(self, node):
        access = self.get_node_table_access(node)
        tables = access.get("tables", [])
        if not tables:
            return "未配置"
        statuses = [self.table_access_entry_status(entry) for entry in tables]
        if any(s in ("未绑定", "未授权") for s in statuses):
            return "待配置"
        if any(s == "危险写入" for s in statuses):
            return "需确认"
        if any(s == "已授权" for s in statuses):
            return "已授权"
        if all(s in ("只读", "只记录", "当前表") for s in statuses):
            return "只读/记录"
        return "OK"

    def table_access_field_items(self, entry):
        return workflow_table_access_field_items(entry)

    def find_table_access_field_rule(self, entry, target="", source="", field_index=None):
        return workflow_find_table_access_field_rule(entry, target=target, source=source, field_index=field_index)

    def make_table_access_field_key(self, mapping, source_field, target_field):
        return workflow_make_table_access_field_key(mapping, source_field, target_field)

    def field_permission_status(self, item):
        item = item or {}
        perms = item.get("permissions") or {}
        if perms.get("protect_field"):
            return "保护"
        if perms.get("write_field"):
            return "可写"
        if perms.get("read_field"):
            return "只读"
        return "未授权"

    def field_bool_text(self, value):
        return "是" if bool(value) else "否"

    def get_table_access_field_choices(self, node_index, entry):
        entry = entry or {}
        table = str(entry.get("table", "") or "").strip()
        choices = []
        try:
            headers, _ = self.get_headers_rows_before(node_index)
            choices.extend(headers or [])
        except Exception:
            choices.extend(self.preview_headers or [])
        if table and table != "__CURRENT_TABLE__" and entry.get("source_type", "SQLite表") == "SQLite表":
            try:
                choices.extend(self.app.get_table_columns(table))
            except Exception:
                pass
        for _, item in self.table_access_field_items(entry):
            for key in ("source_field", "target_field", "field", "name"):
                value = str(item.get(key, "") or "").strip()
                if value:
                    choices.append(value)
        result = []
        for value in choices:
            if value and value not in result:
                result.append(value)
        return result

    def auto_match_table_access_fields(self, node_index, entry):
        entry = entry or {}
        source_fields = []
        try:
            source_fields, _ = self.get_headers_rows_before(node_index)
        except Exception:
            source_fields = list(self.preview_headers or [])

        table = str(entry.get("table", "") or "").strip()
        target_fields = []
        if table and table != "__CURRENT_TABLE__" and entry.get("source_type", "SQLite表") == "SQLite表":
            try:
                target_fields = self.app.get_table_columns(table)
            except Exception:
                target_fields = []
        return workflow_apply_auto_field_mapping_by_name(
            entry,
            source_fields,
            target_fields,
            lambda value: self.app.sanitize_sql_name(value, ""),
            make_key=self.make_table_access_field_key,
        )

    def auto_match_table_access_fields_by_order(self, node_index, entry):
        entry = entry or {}
        try:
            source_fields, _ = self.get_headers_rows_before(node_index)
        except Exception:
            source_fields = list(self.preview_headers or [])

        table = str(entry.get("table", "") or "").strip()
        target_fields = []
        if table and table != "__CURRENT_TABLE__" and entry.get("source_type", "SQLite表") == "SQLite表":
            try:
                target_fields = self.app.get_table_columns(table)
            except Exception:
                target_fields = []
        return workflow_apply_auto_field_mapping_by_order(entry, source_fields, target_fields)

    def apply_table_access_preset_to_vars(self, preset, permission_vars, log_only_var=None):
        config = workflow_table_access_preset_config(
            preset,
            [key for key, _ in self.table_access_permission_items()],
        )
        if config is None:
            return
        for key, var in permission_vars.items():
            var.set(bool(config["permissions"].get(key)))
        if log_only_var is not None:
            log_only_var.set(bool(config["log_only"]))

    def table_access_entry_match_score(self, actual, expected):
        return workflow_table_access_entry_match_score(actual, expected)

    def find_matching_table_access_entry(self, actual_tables, expected):
        return workflow_find_matching_table_access_entry(actual_tables, expected)

    def normalize_precheck_transit_name(self, table_name):
        return workflow_normalize_precheck_transit_name(table_name)

    def add_table_access_precheck_issue(self, issues, severity, node_label, node, entry, message,
                                        suggestion="", category="permission", blocking=None):
        issues.append(workflow_make_table_access_precheck_issue(
            severity,
            node_label,
            node,
            entry,
            message,
            suggestion=suggestion,
            category=category,
            blocking=blocking,
            write_mode_formatter=self.write_mode_display_text,
        ))

    def table_access_precheck_summary_text(self, issues):
        return workflow_table_access_precheck_summary_text(issues)

    def table_access_precheck_actionable(self, issues):
        return workflow_table_access_precheck_actionable(issues)

    def table_access_precheck_blocking(self, issues):
        return workflow_table_access_precheck_blocking(issues)

    def get_precheck_sqlite_tables(self):
        db_path = self.get_workflow_db_path()
        if not db_path or not os.path.exists(db_path):
            return None
        try:
            return set(TableAccessManager(db_path, node_type="权限预检").list_tables())
        except Exception:
            return None

    def confirm_table_access_precheck(self, execute_actions=True, stop_index=None):
        issues = self.build_table_access_precheck(execute_actions=execute_actions, stop_index=stop_index)
        self.last_table_access_precheck = list(issues or [])
        actionable = self.table_access_precheck_actionable(issues)
        if not actionable:
            self.status_var.set(self.table_access_precheck_summary_text(issues))
            return True
        policy = self.normalize_table_access_policy()
        if policy == "audit":
            self.status_var.set(self.table_access_precheck_summary_text(actionable) + " 当前策略为只审计，执行不会因预检提示而中断。")
            return True
        if policy == "strict":
            blocking = self.table_access_precheck_blocking(actionable)
            if not blocking:
                self.status_var.set(self.table_access_precheck_summary_text(actionable) + " 当前仅有风险提醒，强制模式允许继续执行。")
                return True
            self.show_table_access_precheck_dialog(
                blocking,
                title="执行前权限预检 - 强制拦截",
                allow_continue=False,
            )
            self.status_var.set("执行计划已拦截：当前权限策略为强制拦截，请先处理权限预检项。")
            return False
        return self.show_table_access_precheck_dialog(
            actionable,
            title="执行前权限预检",
            allow_continue=True,
        )

    def show_table_access_precheck_dialog(self, issues, title="权限预检", allow_continue=False):
        return plan_workflow_ui.show_table_access_precheck_dialog(
            self,
            issues,
            title=title,
            allow_continue=allow_continue,
        )

    def open_table_access_precheck_window(self):
        issues = self.build_table_access_precheck(execute_actions=True)
        self.show_table_access_precheck_dialog(issues, title="权限预检", allow_continue=False)

    def table_access_precheck_sort_key(self, issue):
        return table_access_precheck_sort_key(issue)

    def iter_nodes_for_table_access_precheck(self, nodes=None, stop_index=None, prefix=""):
        node_list = nodes if nodes is not None else self.nodes
        yield from iter_nodes_for_table_access_precheck(node_list, stop_index=stop_index, prefix=prefix)

    def build_table_access_precheck(self, execute_actions=True, stop_index=None, nodes=None):
        """Build table-access precheck issues from the current workflow configuration."""
        node_list = nodes if nodes is not None else self.nodes
        self.ensure_node_tree_identity(node_list)
        self.refresh_node_tree_table_access(node_list)

        issues = []
        db_path = self.get_workflow_db_path()
        sqlite_tables = self.get_precheck_sqlite_tables()
        produced_transit = set((self.current_transit_tables or {}).keys())
        permission_label_map = dict(self.table_access_permission_items())
        db_exists = os.path.exists(db_path) if db_path else None

        if execute_actions:
            output_mode = self.output_mode_var.get()
            output_table = self.output_table_var.get().strip()
            issues.extend(
                evaluate_workflow_output_precheck(
                    output_mode,
                    output_table,
                    db_path=db_path,
                    write_mode_formatter=self.write_mode_display_text,
                )
            )

        for node_label, node in self.iter_nodes_for_table_access_precheck(node_list, stop_index=stop_index):
            if not isinstance(node, dict):
                continue
            if not node.get("enabled", True):
                continue

            node_type = node.get("type", "")
            config = node.get("config", {}) or {}
            expected_access = self.default_table_access_for_node(node)
            actual_access = self.get_node_table_access(node)
            node_result = evaluate_node_table_access_precheck(
                node_label,
                node,
                expected_access,
                actual_access,
                permission_label_map=permission_label_map,
                execute_actions=execute_actions,
                db_path=db_path,
                db_exists=db_exists,
                sqlite_tables=sqlite_tables,
                produced_transit=produced_transit,
                needs_plugin_declaration=node_type == "插件节点" and self.plugin_needs_table_access_declaration(config),
                has_plugin_declaration=node_type == "插件节点" and self.plugin_has_table_access_declaration(config),
                write_mode_formatter=self.write_mode_display_text,
            )
            issues.extend(node_result.get("issues", []))
            for transit_name in node_result.get("produced_transit", []) or []:
                produced_transit.add(transit_name)

        issues.sort(key=self.table_access_precheck_sort_key)
        self.last_table_access_precheck = issues
        return issues

    def table_access_log_text(self, event):
        return table_access_audit_ui.table_access_log_text(event)

    def open_table_access_audit_window(self):
        return table_access_audit_ui.open_table_access_audit_window(self)

    def build_table_access_window_shell(self):
        return table_access_window_ui.build_table_access_window_shell(self)

    def build_table_access_list_section(self, parent):
        return table_access_window_ui.build_table_access_list_section(self, parent)

    def build_table_access_table_form_section(self, parent):
        return table_access_window_ui.build_table_access_table_form_section(self, parent)

    def build_table_access_field_form_section(self, parent):
        return table_access_window_ui.build_table_access_field_form_section(self, parent)

    def build_table_access_table_action_buttons(self, table_form, commands):
        return table_access_window_ui.build_table_access_table_action_buttons(self, table_form, commands)

    def build_table_access_field_action_buttons(self, field_form, commands):
        return table_access_window_ui.build_table_access_field_action_buttons(self, field_form, commands)

    def build_table_access_bottom_buttons(self, win, commands):
        return table_access_window_ui.build_table_access_bottom_buttons(self, win, commands)

    def current_table_access_window_node(self, state):
        return table_access_window_ui.current_table_access_window_node(self, state)

    def refresh_table_access_node_tree(self, node_tree, state):
        return table_access_window_ui.refresh_table_access_node_tree(self, node_tree, state)

    def load_table_access_table_form(self, table_section, entry, table_choices):
        return table_access_window_ui.load_table_access_table_form(self, table_section, entry, table_choices)

    def refresh_table_access_field_choices(self, field_section, choices):
        return table_access_window_ui.refresh_table_access_field_choices(self, field_section, choices)

    def refresh_table_access_field_tree(self, state, field_tree, entry, field_section, choices):
        return table_access_window_ui.refresh_table_access_field_tree(
            self,
            state,
            field_tree,
            entry,
            field_section,
            choices,
        )

    def current_table_access_window_access(self, state):
        return table_access_window_ui.current_table_access_window_access(self, state)

    def current_table_access_window_table_entry(self, state):
        return table_access_window_ui.current_table_access_window_table_entry(self, state)

    def load_table_access_window_table_form(self, state, table_section, entry):
        return table_access_window_ui.load_table_access_window_table_form(self, state, table_section, entry)

    def collect_table_access_window_table_form(self, table_section):
        return table_access_window_ui.collect_table_access_window_table_form(self, table_section)

    def refresh_table_access_window_field_tree(self, state, field_section, field_tree):
        return table_access_window_ui.refresh_table_access_window_field_tree(self, state, field_section, field_tree)

    def refresh_table_access_window_table_tree(
        self,
        state,
        table_section,
        field_section,
        node_tree,
        table_tree,
        field_tree,
        select_index=None,
    ):
        return table_access_window_ui.refresh_table_access_window_table_tree(
            self,
            state,
            table_section,
            field_section,
            node_tree,
            table_tree,
            field_tree,
            select_index=select_index,
        )

    def on_table_access_window_node_selected(
        self,
        state,
        table_section,
        field_section,
        node_tree,
        table_tree,
        field_tree,
        status_var,
        event=None,
        force=False,
    ):
        return table_access_window_ui.on_table_access_window_node_selected(
            self,
            state,
            table_section,
            field_section,
            node_tree,
            table_tree,
            field_tree,
            status_var,
            event=event,
            force=force,
        )

    def on_table_access_window_table_selected(
        self,
        state,
        table_section,
        field_section,
        table_tree,
        field_tree,
        event=None,
    ):
        return table_access_window_ui.on_table_access_window_table_selected(
            self,
            state,
            table_section,
            field_section,
            table_tree,
            field_tree,
            event=event,
        )

    def on_table_access_window_field_selected(self, state, field_section, field_tree, event=None):
        return table_access_window_ui.on_table_access_window_field_selected(
            self,
            state,
            field_section,
            field_tree,
            event=event,
        )

    def save_table_access_window_table_entry(
        self,
        state,
        table_section,
        field_section,
        node_tree,
        table_tree,
        field_tree,
        status_var,
    ):
        return table_access_window_ui.save_table_access_window_table_entry(
            self,
            state,
            table_section,
            field_section,
            node_tree,
            table_tree,
            field_tree,
            status_var,
        )

    def add_table_access_window_table_entry(
        self,
        state,
        table_section,
        field_section,
        node_tree,
        table_tree,
        field_tree,
    ):
        return table_access_window_ui.add_table_access_window_table_entry(
            self,
            state,
            table_section,
            field_section,
            node_tree,
            table_tree,
            field_tree,
        )

    def delete_table_access_window_table_entry(
        self,
        state,
        table_section,
        field_section,
        node_tree,
        table_tree,
        field_tree,
        status_var,
    ):
        return table_access_window_ui.delete_table_access_window_table_entry(
            self,
            state,
            table_section,
            field_section,
            node_tree,
            table_tree,
            field_tree,
            status_var,
        )

    def rebuild_table_access_window_default_access(
        self,
        win,
        state,
        table_section,
        field_section,
        node_tree,
        table_tree,
        field_tree,
        status_var,
    ):
        return table_access_window_ui.rebuild_table_access_window_default_access(
            self,
            win,
            state,
            table_section,
            field_section,
            node_tree,
            table_tree,
            field_tree,
            status_var,
        )

    def check_table_access_window_permissions(self, win, status_var):
        return table_access_window_ui.check_table_access_window_permissions(self, win, status_var)

    def preview_table_access_window_impact(self, win, state):
        return table_access_window_ui.preview_table_access_window_impact(self, win, state)

    def apply_table_access_window_table_preset(self, table_section, event=None):
        return table_access_window_ui.apply_table_access_window_table_preset(self, table_section, event=event)

    def save_table_access_window_field_entry(self, state, table_section, field_section, field_tree, status_var):
        return table_access_window_ui.save_table_access_window_field_entry(
            self,
            state,
            table_section,
            field_section,
            field_tree,
            status_var,
        )

    def add_table_access_window_field_entry(self, table_section, field_section, field_tree):
        return table_access_window_ui.add_table_access_window_field_entry(self, table_section, field_section, field_tree)

    def delete_table_access_window_field_entry(self, state, field_section, field_tree, status_var):
        return table_access_window_ui.delete_table_access_window_field_entry(
            self,
            state,
            field_section,
            field_tree,
            status_var,
        )

    def auto_match_table_access_window_fields(self, state, field_section, field_tree, status_var):
        return table_access_window_ui.auto_match_table_access_window_fields(
            self,
            state,
            field_section,
            field_tree,
            status_var,
        )

    def auto_match_table_access_window_fields_by_order(self, state, table_section, field_section, field_tree, status_var):
        return table_access_window_ui.auto_match_table_access_window_fields_by_order(
            self,
            state,
            table_section,
            field_section,
            field_tree,
            status_var,
        )

    def clear_table_access_window_fields(self, state, field_section, field_tree, status_var):
        return table_access_window_ui.clear_table_access_window_fields(self, state, field_section, field_tree, status_var)

    def create_table_access_selection_callbacks(
        self,
        state,
        table_section,
        field_section,
        node_tree,
        table_tree,
        field_tree,
        status_var,
    ):
        return table_access_window_ui.create_table_access_selection_callbacks(
            self,
            state,
            table_section,
            field_section,
            node_tree,
            table_tree,
            field_tree,
            status_var,
        )

    def create_table_access_table_action_callbacks(
        self,
        win,
        state,
        table_section,
        field_section,
        node_tree,
        table_tree,
        field_tree,
        status_var,
    ):
        return table_access_window_ui.create_table_access_table_action_callbacks(
            self,
            win,
            state,
            table_section,
            field_section,
            node_tree,
            table_tree,
            field_tree,
            status_var,
        )

    def create_table_access_field_action_callbacks(
        self,
        state,
        table_section,
        field_section,
        field_tree,
        status_var,
    ):
        return table_access_window_ui.create_table_access_field_action_callbacks(
            self,
            state,
            table_section,
            field_section,
            field_tree,
            status_var,
        )

    def create_table_access_window_callbacks(
        self,
        win,
        state,
        table_section,
        field_section,
        node_tree,
        table_tree,
        field_tree,
        status_var,
    ):
        return table_access_window_ui.create_table_access_window_callbacks(
            self,
            win,
            state,
            table_section,
            field_section,
            node_tree,
            table_tree,
            field_tree,
            status_var,
        )

    def open_table_access_window(self, initial_index=None):
        return table_access_window_ui.open_table_access_window(self, initial_index=initial_index)
