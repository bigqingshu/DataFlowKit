# -*- coding: utf-8 -*-
"""UI-free table-access policy and precheck service."""

from __future__ import annotations

import copy
import os
from dataclasses import dataclass, field
from datetime import datetime

from db import TableAccessManager
from engine.issue_schema import has_error_issues, normalize_issue
from workflow.nodes.group_nodes import normalize_group_transit_conflict_mode
from workflow.nodes.selected_columns_nodes import normalize_selected_columns_write_mode
from workflow.protocol_nodes import (
    display_type_for_node,
    stable_node_type_id_for_node,
)
from workflow.table_access_defaults import build_default_table_access_for_node
from workflow.table_access_precheck import (
    evaluate_node_table_access_precheck,
    evaluate_workflow_output_precheck,
    table_access_precheck_actionable,
    table_access_precheck_blocking,
    table_access_precheck_sort_key,
    table_access_precheck_summary_text,
)


TABLE_ACCESS_PERMISSION_ITEMS = [
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

WRITE_MODE_DISPLAY_LABELS = {
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


@dataclass
class AccessPolicyService:
    """Backend service for table-access defaults, precheck and audit logs."""

    db_path: str = ""
    plugin_registry: dict = field(default_factory=dict)
    now_factory: object = datetime.now
    audit_logs: list = field(default_factory=list)

    def normalize_table_access_policy(self, value=None):
        return TableAccessManager.normalize_permission_policy(value)

    def normalize_table_access_write_mode(self, mode):
        return TableAccessManager.normalize_write_mode(mode)

    def write_mode_display_text(self, mode):
        standard = self.normalize_table_access_write_mode(mode)
        return WRITE_MODE_DISPLAY_LABELS.get(standard, str(mode or ""))

    def table_access_permission_items(self):
        return list(TABLE_ACCESS_PERMISSION_ITEMS)

    def table_permission_set(
        self,
        read=False,
        write=False,
        create=False,
        append=False,
        update=False,
        clear=False,
        replace=False,
        alter=False,
        delete=False,
        drop=False,
    ):
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

    def make_table_access_entry(
        self,
        role,
        table,
        source_type="SQLite表",
        is_current_table=False,
        permissions=None,
        write_mode="",
        field_mapping=None,
        log_only=False,
        table_pattern="",
        pattern_type="glob",
        declared_by="",
    ):
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
            "field_mapping": copy.deepcopy(field_mapping or {}),
            "log_only": bool(log_only),
        }

    def build_table_access(self, node):
        legacy_node = self._legacy_node(node)
        access = self.default_table_access_for_node(legacy_node)
        return {
            "ok": True,
            "node_type_id": stable_node_type_id_for_node(legacy_node),
            "node_type": display_type_for_node(legacy_node),
            "table_access": access,
            "issues": [],
        }

    def default_table_access_for_node(self, node):
        return build_default_table_access_for_node(
            self._legacy_node(node),
            self.make_table_access_entry,
            self.table_permission_set,
            normalize_selected_columns_write_mode=normalize_selected_columns_write_mode,
            normalize_group_transit_conflict_mode=normalize_group_transit_conflict_mode,
            get_plugin_table_access_specs=self.get_plugin_table_access_specs,
            make_plugin_declared_access_entry=self.make_plugin_declared_access_entry,
        )

    def get_node_table_access(self, node, default_access=None):
        access = (node or {}).get("table_access") if isinstance(node, dict) else None
        if not isinstance(access, dict) or bool(access.get("auto_generated", True)):
            return copy.deepcopy(default_access or self.default_table_access_for_node(node))
        result = copy.deepcopy(access)
        result.setdefault("version", 1)
        if not isinstance(result.get("tables"), list):
            result["tables"] = []
        return result

    def precheck_access(
        self,
        plan=None,
        *,
        nodes=None,
        execute_actions=True,
        stop_index=None,
        db_path=None,
        sqlite_tables=None,
        output_mode=None,
        output_table=None,
        table_access_policy=None,
        current_transit_tables=None,
        confirmed=False,
    ):
        plan = plan if isinstance(plan, dict) else {}
        policy = self.normalize_table_access_policy(
            table_access_policy if table_access_policy is not None else plan.get("table_access_policy", "audit")
        )
        if policy == "off":
            return self._precheck_result([], [], policy=policy, skipped=True)

        node_list = [self._legacy_node(node) for node in _extract_nodes(plan, nodes)]
        db_path = self._resolve_db_path(db_path if db_path is not None else plan.get("db_path") or plan.get("output_db_path"))
        output_mode = output_mode if output_mode is not None else plan.get("output_mode", "")
        output_table = output_table if output_table is not None else plan.get("output_table", "")
        sqlite_table_set = self._resolve_sqlite_tables(db_path, sqlite_tables)
        db_exists = os.path.exists(db_path) if db_path else None
        produced_transit = set((current_transit_tables or plan.get("current_transit_tables") or {}).keys())
        permission_label_map = dict(self.table_access_permission_items())

        issues = []
        if execute_actions:
            output_issues = evaluate_workflow_output_precheck(
                output_mode,
                output_table,
                db_path=db_path,
                write_mode_formatter=self.write_mode_display_text,
            )
            issues.extend(self._normalize_access_issues(output_issues, node_index=None, node=None))

        for node_label, node, node_index in _iter_legacy_nodes(node_list, stop_index=stop_index):
            if not isinstance(node, dict) or not node.get("enabled", True):
                continue
            config = node.get("config", {}) or {}
            expected_access = self.default_table_access_for_node(node)
            actual_access = self.get_node_table_access(node, default_access=expected_access)
            node_result = evaluate_node_table_access_precheck(
                node_label,
                node,
                expected_access,
                actual_access,
                permission_label_map=permission_label_map,
                execute_actions=execute_actions,
                db_path=db_path,
                db_exists=db_exists,
                sqlite_tables=sqlite_table_set,
                produced_transit=produced_transit,
                needs_plugin_declaration=(
                    node.get("type") == "插件节点"
                    and self.plugin_needs_table_access_declaration(config)
                ),
                has_plugin_declaration=(
                    node.get("type") == "插件节点"
                    and self.plugin_has_table_access_declaration(config)
                ),
                write_mode_formatter=self.write_mode_display_text,
            )
            issues.extend(self._normalize_access_issues(
                node_result.get("issues", []),
                node_index=node_index,
                node=node,
            ))
            for transit_name in node_result.get("produced_transit", []) or []:
                produced_transit.add(transit_name)

        issues.sort(key=table_access_precheck_sort_key)
        return self._precheck_result(issues, node_list, policy=policy, confirmed=confirmed)

    def format_access_issue(self, issue):
        issue = issue or {}
        lines = [
            f"级别：{issue.get('severity', '')}",
            f"问题：{issue.get('message', '')}",
        ]
        if issue.get("node"):
            lines.append(f"节点：{issue.get('node')}")
        if issue.get("table"):
            lines.append(f"表：{issue.get('table')}")
        if issue.get("operation"):
            lines.append(f"操作：{issue.get('operation')}")
        if issue.get("suggestion"):
            lines.append(f"建议：{issue.get('suggestion')}")
        return "\n".join(line for line in lines if line)

    def record_access_audit(self, event):
        payload = copy.deepcopy(event or {})
        payload.setdefault("time", self._now_text())
        self.audit_logs.append(payload)
        return {
            "ok": True,
            "event": copy.deepcopy(payload),
            "count": len(self.audit_logs),
        }

    def list_access_audit_logs(self, *, selected_status="全部", keyword=""):
        logs = [copy.deepcopy(item) for item in self.audit_logs]
        return {
            "ok": True,
            "logs": logs,
            **_filter_access_audit_logs(logs, selected_status=selected_status, keyword=keyword),
        }

    def format_access_audit_event(self, event):
        return _access_audit_log_text(event)

    def get_plugin_table_access_specs(self, config):
        config = config or {}
        plugin_id = str(config.get("plugin_id", "") or "").strip()
        item = self.plugin_registry.get(plugin_id, {}) if isinstance(self.plugin_registry, dict) else {}
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
        item = self.plugin_registry.get(plugin_id, {}) if isinstance(self.plugin_registry, dict) else {}
        module = item.get("module")
        if callable(getattr(module, "get_table_access_spec", None)):
            return True
        info = item.get("info", {}) or {}
        return bool(info.get("table_access") or info.get("table_access_spec"))

    def plugin_needs_table_access_declaration(self, config):
        config = config or {}
        plugin_id = str(config.get("plugin_id", "") or "").strip()
        item = self.plugin_registry.get(plugin_id, {}) if isinstance(self.plugin_registry, dict) else {}
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

    def _legacy_node(self, node):
        item = copy.deepcopy(node) if isinstance(node, dict) else {}
        node_type_id = stable_node_type_id_for_node(item)
        display_type = display_type_for_node(item)
        if display_type:
            item["type"] = display_type
        if node_type_id and not item.get("node_type_id"):
            item["node_type_id"] = node_type_id
        if node_type_id.startswith("plugin."):
            config = item.setdefault("config", {})
            if isinstance(config, dict):
                config.setdefault("plugin_id", node_type_id.split(".", 1)[1])
            item["type"] = "插件节点"
        return item

    def _resolve_db_path(self, db_path=None):
        return str(db_path or self.db_path or "").strip()

    def _resolve_sqlite_tables(self, db_path, sqlite_tables):
        if sqlite_tables is not None:
            return set(sqlite_tables or [])
        if not db_path or not os.path.exists(db_path):
            return None
        try:
            return set(TableAccessManager(db_path, node_type="AccessPolicyService").list_tables())
        except Exception:
            return None

    def _normalize_access_issues(self, issues, *, node_index=None, node=None):
        normalized = []
        node_type_id = stable_node_type_id_for_node(node) if isinstance(node, dict) else ""
        for issue in issues or []:
            payload = normalize_issue(issue)
            category = str(payload.get("category") or "permission").strip() or "permission"
            if not payload.get("code") or payload.get("code") == "unknown_issue":
                payload["code"] = f"table_access_{category}_{payload.get('severity', 'issue')}"
            payload.setdefault("source", "AccessPolicyService")
            if node_index is not None:
                payload.setdefault("node_index", node_index)
                payload.setdefault("path", f"/nodes/{node_index}/table_access")
            else:
                payload.setdefault("path", "/output/table_access")
            if node_type_id:
                payload.setdefault("node_type_id", node_type_id)
            normalized.append(payload)
        return normalized

    def _precheck_result(self, issues, node_list, *, policy, confirmed=False, skipped=False):
        actionable = table_access_precheck_actionable(issues)
        blocking = table_access_precheck_blocking(actionable)
        requires_confirmation = policy == "prompt" and bool(actionable) and not confirmed
        can_continue = True
        if policy == "strict" and blocking:
            can_continue = False
        elif requires_confirmation:
            can_continue = False
        summary = "权限预检已关闭。" if skipped else table_access_precheck_summary_text(issues)
        return {
            "ok": not has_error_issues(issues),
            "can_continue": bool(can_continue),
            "requires_confirmation": bool(requires_confirmation),
            "skipped": bool(skipped),
            "policy": policy,
            "issues": issues,
            "actionable_issues": actionable,
            "blocking_issues": blocking,
            "summary": summary,
            "counts": _issue_counts(issues),
            "blocking_count": len(blocking),
            "node_count": len(node_list or []),
        }

    def _now_text(self):
        value = self.now_factory() if callable(self.now_factory) else datetime.now()
        try:
            return value.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return str(value)


def _extract_nodes(plan, nodes):
    if nodes is not None:
        return list(nodes or [])
    if isinstance(plan, dict):
        return list(plan.get("nodes") or [])
    if isinstance(plan, list):
        return list(plan)
    return []


def _iter_legacy_nodes(nodes, stop_index=None, prefix=""):
    for idx, node in enumerate(nodes or []):
        if stop_index is not None and not prefix and idx > int(stop_index):
            break
        node = copy.deepcopy(node) if isinstance(node, dict) else {}
        node_type = display_type_for_node(node)
        if node_type:
            node["type"] = node_type
        node_type_id = stable_node_type_id_for_node(node)
        if node_type_id and not node.get("node_type_id"):
            node["node_type_id"] = node_type_id
        label = f"{prefix}{idx + 1}.{node_type}"
        yield label, node, idx if not prefix else None
        cfg = (node or {}).get("config", {}) if isinstance(node, dict) else {}
        child_nodes = cfg.get("nodes") if isinstance(cfg, dict) else None
        if isinstance(child_nodes, list):
            child_legacy = [copy.deepcopy(child) for child in child_nodes]
            yield from _iter_legacy_nodes(child_legacy, stop_index=None, prefix=f"{label} > ")


def _issue_counts(issues):
    counts = {"error": 0, "warning": 0, "info": 0}
    for issue in issues or []:
        severity = issue.get("severity", "info")
        counts[severity] = counts.get(severity, 0) + 1
    return counts


def _access_audit_log_text(event):
    try:
        import json
        return json.dumps(event, ensure_ascii=False, default=str)
    except Exception:
        return str(event)


def _access_audit_log_row(event):
    node = event.get("node_name") or event.get("node_type") or event.get("node_id") or ""
    source = event.get("source_type") or event.get("access_source_type") or ""
    mode = event.get("write_mode") or event.get("mode") or ""
    return (
        event.get("time", ""),
        node,
        source,
        event.get("table_name", ""),
        event.get("operation_checked") or event.get("operation", ""),
        event.get("status", ""),
        mode,
        event.get("policy", ""),
        event.get("message", ""),
    )


def _filter_access_audit_logs(logs, *, selected_status="全部", keyword=""):
    keyword = str(keyword or "").strip().lower()
    selected_status = str(selected_status or "全部")
    visible = []
    counts = {}
    for idx, event in enumerate(logs or []):
        status = str((event or {}).get("status", "") or "")
        counts[status] = counts.get(status, 0) + 1
        if selected_status != "全部" and status != selected_status:
            continue
        text = _access_audit_log_text(event).lower()
        if keyword and keyword not in text:
            continue
        visible.append({
            "index": idx,
            "event": event,
            "row": _access_audit_log_row(event),
            "tag": status,
        })
    count_text = "，".join(f"{key or '无状态'} {value}" for key, value in sorted(counts.items()))
    summary = f"最近日志 {len(logs or [])} 条，当前显示 {len(visible)} 条" + (f"（{count_text}）" if count_text else "")
    return {
        "visible": visible,
        "counts": counts,
        "summary": summary,
    }
