# -*- coding: utf-8 -*-
"""UI-free plugin discovery and metadata service."""

from __future__ import annotations

import copy
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from engine.issue_schema import has_error_issues, make_issue
from plugin_runtime.scanner import scan_plugins
from workflow.nodes.plugin_nodes import (
    make_plugin_input_data,
    normalize_plugin_run_result,
)
from workflow.protocol_nodes import DEFAULT_NODE_VERSION


PLUGIN_FORM_SCHEMA_VERSION = "2.0"


@dataclass
class PluginService:
    """Expose plugin registry metadata without leaking Python module objects."""

    plugins_dir: str = ""
    app_dir: str = ""
    scanner: object = scan_plugins
    registry: dict = field(default_factory=dict)
    errors: list = field(default_factory=list)
    display_map: dict = field(default_factory=dict)
    loaded_plugins_dir: str = ""

    def list_plugins(self, plugins_dir=None, *, refresh=None):
        if refresh is None:
            refresh = not self.registry or self._resolve_plugins_dir(plugins_dir) != self.loaded_plugins_dir
        if refresh:
            self.refresh_plugins(plugins_dir=plugins_dir)
        plugins = [
            self._public_plugin(plugin_id, item)
            for plugin_id, item in sorted(self.registry.items(), key=lambda kv: self._plugin_sort_key(kv[0], kv[1]))
        ]
        return {
            "ok": True,
            "plugins_dir": self.loaded_plugins_dir or self._resolve_plugins_dir(plugins_dir),
            "plugins": plugins,
            "display_map": dict(self.display_map),
            "errors": copy.deepcopy(self.errors),
            "count": len(plugins),
            "external_only_count": sum(1 for item in plugins if item.get("load_status") == "仅独立环境运行"),
        }

    def refresh_plugins(self, plugins_dir=None):
        target = self._resolve_plugins_dir(plugins_dir)
        registry, errors = self.scanner(target)
        self.registry = registry
        self.errors = errors
        self.display_map = _build_plugin_display_map(registry)
        self.loaded_plugins_dir = target
        return self.list_plugins(plugins_dir=target, refresh=False)

    def get_plugin_schema(self, plugin_id, *, plugins_dir=None, preview_headers=None, table_names=None, table_columns=None):
        self._ensure_loaded(plugins_dir)
        key = self._resolve_plugin_key(plugin_id)
        if not key:
            issue = make_issue(
                "error",
                "plugin_not_found",
                f"未找到插件：{plugin_id}",
                path="/plugin_id",
                source="PluginService",
            )
            return {"ok": False, "plugin": {}, "schema": {}, "issues": [issue]}
        item = self.registry[key]
        plugin = self._public_plugin(key, item)
        default_config = self.make_plugin_default_config(key)
        schema = {
            "schema_version": "2.0",
            "node_type_id": plugin["node_type_id"],
            "node_version": DEFAULT_NODE_VERSION,
            "display_name": plugin["display_name"],
            "category": "插件",
            "category_label": "插件",
            "menu": {
                "path": ["插件", plugin["display_name"]],
                "order": 9000,
            },
            "summary": plugin["summary"],
            "description": plugin["description"],
            "badges": plugin["badges"],
            "warnings": plugin["warnings"],
            "risk": plugin["risk"],
            "capabilities": {
                "headless_preview": _plugin_is_headless_runnable(item),
                "headless_run": _plugin_is_headless_runnable(item),
                "execute_actions": True,
                "plugin": True,
                "import_ok": bool(plugin.get("import_ok")),
                "available_run_modes": list(plugin.get("available_run_modes") or []),
            },
            "form": {
                "schema_version": PLUGIN_FORM_SCHEMA_VERSION,
                "dynamic_rules": True,
                "groups": _plugin_config_form_groups(default_config, item.get("schema", [])),
            },
            "default_config": default_config,
            "parameters": copy.deepcopy(item.get("schema", [])),
            "plugin": plugin,
        }
        return {
            "ok": True,
            "plugin": plugin,
            "schema": schema,
            "default_config": default_config,
            "issues": [],
        }

    def list_plugin_node_catalog(self, plugins_dir=None):
        listed = self.list_plugins(plugins_dir=plugins_dir)
        return {
            "ok": listed["ok"],
            "plugins": [
                {
                    "node_type_id": plugin["node_type_id"],
                    "display_name": plugin["display_name"],
                    "category": "插件",
                    "supported_headless": _plugin_is_headless_runnable(self.registry.get(plugin["plugin_id"], {})),
                    "plugin_id": plugin["plugin_id"],
                    "load_status": plugin["load_status"],
                }
                for plugin in listed.get("plugins", [])
            ],
            "errors": listed.get("errors", []),
        }

    def is_plugin_headless_runnable(self, plugin_id, *, plugins_dir=None):
        self._ensure_loaded(plugins_dir)
        key = self._resolve_plugin_key(plugin_id)
        return bool(key and _plugin_is_headless_runnable(self.registry.get(key, {})))

    def validate_plugin_config(self, plugin_id, params=None, *, input_table=None, context=None, config=None, plugins_dir=None):
        self._ensure_loaded(plugins_dir)
        key = self._resolve_plugin_key(plugin_id)
        if not key:
            return _plugin_failure("plugin_not_found", f"未找到插件：{plugin_id}", "/plugin_id")
        item = self.registry.get(key, {})
        module = item.get("module")
        if not _plugin_is_headless_runnable(item):
            return _plugin_failure(
                "plugin_not_headless_runnable",
                f"插件暂不支持 headless 内置执行：{key}",
                "/plugin_id",
            )
        params = dict(params if params is not None else (config or {}).get("params", {}))
        input_data = _make_plugin_service_input_data(key, input_table, context)
        plugin_context = _make_plugin_service_context(key, config=config, context=context)
        validate = getattr(module, "validate_params", None)
        if callable(validate):
            try:
                ok_msg = validate(params, input_data, plugin_context)
            except Exception as exc:
                return _plugin_failure("plugin_config_error", str(exc), "/params")
            if isinstance(ok_msg, tuple):
                ok, message = ok_msg
                if not ok:
                    return _plugin_failure("plugin_config_invalid", message or "插件参数校验失败", "/params")
            elif ok_msg is False:
                return _plugin_failure("plugin_config_invalid", "插件参数校验失败", "/params")
        return {"ok": True, "plugin_id": key, "issues": []}

    def run_plugin(self, plugin_id, input_table=None, params=None, *, context=None, config=None, execute_actions=False, plugins_dir=None):
        self._ensure_loaded(plugins_dir)
        key = self._resolve_plugin_key(plugin_id)
        if not key:
            return _plugin_failure("plugin_not_found", f"未找到插件：{plugin_id}", "/plugin_id")
        item = self.registry.get(key, {})
        module = item.get("module")
        if not _plugin_is_headless_runnable(item):
            return _plugin_failure(
                "plugin_not_headless_runnable",
                f"插件暂不支持 headless 内置执行：{key}",
                "/plugin_id",
            )
        params = dict(params if params is not None else (config or {}).get("params", {}))
        input_data = _make_plugin_service_input_data(key, input_table, context)
        plugin_context = _make_plugin_service_context(
            key,
            config=config,
            context=context,
            execute_actions=execute_actions,
        )
        validation = self.validate_plugin_config(
            key,
            params,
            input_table=input_table,
            context=context,
            config=config,
            plugins_dir=plugins_dir,
        )
        if not validation.get("ok"):
            return validation
        try:
            result = module.run(input_data, params, plugin_context)
            normalized = normalize_plugin_run_result(
                result,
                input_data,
                input_data.get("headers", []),
                input_data.get("rows", []),
            )
        except Exception as exc:
            return _plugin_failure("plugin_run_error", str(exc), "/run")
        return {
            "ok": True,
            "plugin_id": key,
            "plugin": self._public_plugin(key, item),
            "result": normalized,
            "input_data": input_data,
            "context": plugin_context,
            "issues": [],
        }

    def list_plugin_node_ui_schemas(self, plugins_dir=None, *, preview_headers=None, table_names=None, table_columns=None):
        listed = self.list_plugins(plugins_dir=plugins_dir)
        schemas = []
        for plugin in listed.get("plugins", []):
            schema = self.get_plugin_schema(
                plugin["plugin_id"],
                plugins_dir=plugins_dir,
                preview_headers=preview_headers,
                table_names=table_names,
                table_columns=table_columns,
            )
            if schema.get("ok"):
                schemas.append(schema["schema"])
        return {
            "ok": True,
            "node_ui_schemas": schemas,
            "errors": listed.get("errors", []),
        }

    def make_plugin_default_config(self, plugin_id, *, plugins_dir=None):
        self._ensure_loaded(plugins_dir)
        key = self._resolve_plugin_key(plugin_id)
        item = self.registry.get(key or "", {})
        schema = item.get("schema", [])
        params = {}
        for field in schema:
            if not isinstance(field, dict):
                continue
            name = field.get("name")
            if not name:
                continue
            default = field.get("default", "")
            if field.get("type") == "multi_field_select" and default == "":
                default = []
            params[name] = copy.deepcopy(default)
        info = item.get("info", {})
        default_run_mode = info.get("run_mode") or item.get("run_mode_default") or "主程序内置环境"
        if default_run_mode in ("external_python", "独立环境", "插件独立环境"):
            default_run_mode = "插件独立环境"
        else:
            default_run_mode = "主程序内置环境"
        name = info.get("name", key or plugin_id)
        return {
            "plugin_id": key or str(plugin_id or ""),
            "params": params,
            "input_tables": [],
            "run_mode": default_run_mode,
            "external_python": "",
            "external_env_dir": self.get_plugin_env_dir(key or plugin_id),
            "external_entry": item.get("external_entry", item.get("path", "")),
            "external_timeout": "0",
            "output_mode": "使用插件返回结果",
            "save_output_as_transit": False,
            "transit_name": name,
            "transit_conflict_mode": "覆盖",
            "save_plugin_log_file": True,
            "save_plugin_log_sqlite": False,
            "save_plugin_log_transit": False,
            "plugin_log_transit_name": f"{name}_日志",
            "plugin_log_in_preview": False,
            "plugin_failure_policy": "停止工作流",
        }

    def make_default_plugin_node(self, plugin_id, *, node_id="", name="", include_legacy_type=True):
        self._ensure_loaded()
        key = self._resolve_plugin_key(plugin_id) or str(plugin_id or "")
        item = self.registry.get(key, {})
        info = item.get("info", {})
        display_name = str(name or info.get("name") or key or "插件节点")
        node = {
            "node_id": node_id,
            "node_type_id": plugin_node_type_id(key),
            "node_version": DEFAULT_NODE_VERSION,
            "name": display_name,
            "enabled": True,
            "config": self.make_plugin_default_config(key),
        }
        if include_legacy_type:
            node["type"] = "插件节点"
        return node

    def get_plugin_env_dir(self, plugin_id=None):
        base = Path(self._resolve_app_dir()) / "plugin_envs"
        if plugin_id:
            base = base / _sanitize_path_segment(plugin_id, "plugin")
        return str(base)

    def _public_plugin(self, plugin_id, item):
        item = item or {}
        info = copy.deepcopy(item.get("info") or {})
        name = str(info.get("name") or plugin_id).strip() or plugin_id
        load_status = str(item.get("load_status") or ("可内置运行" if item.get("import_ok") else "仅独立环境运行"))
        warnings = []
        if load_status == "仅独立环境运行":
            warnings.append("插件当前仅能通过独立环境运行。")
        if item.get("import_error"):
            warnings.append(str(item.get("import_error")))
        return {
            "plugin_id": plugin_id,
            "node_type_id": plugin_node_type_id(plugin_id),
            "display_name": f"插件 / {name}",
            "name": name,
            "summary": str(info.get("summary") or info.get("description") or name),
            "description": str(info.get("description") or info.get("summary") or name),
            "version": str(info.get("version") or ""),
            "api_version": str(info.get("api_version") or "1.0"),
            "author": str(info.get("author") or ""),
            "danger_level": str(info.get("danger_level") or ""),
            "risk": str(info.get("danger_level") or "plugin_external"),
            "badges": _plugin_badges(item),
            "warnings": warnings,
            "load_status": load_status,
            "run_mode_default": item.get("run_mode_default", ""),
            "available_run_modes": list(item.get("available_run_modes") or []),
            "import_ok": bool(item.get("import_ok")),
            "import_error": str(item.get("import_error") or ""),
            "metadata_source": str(item.get("metadata_source") or ""),
            "path": str(item.get("path") or ""),
            "external_entry": str(item.get("external_entry") or item.get("path") or ""),
            "requirements_path": str(item.get("requirements_path") or ""),
            "manifest_path": str(item.get("manifest_path") or ""),
            "parameter_count": len(item.get("schema") or []),
            "info": info,
        }

    def _resolve_plugin_key(self, plugin_id):
        text = str(plugin_id or "").strip()
        if not text:
            return ""
        if text in self.registry:
            return text
        if text.startswith("plugin."):
            suffix = text.split(".", 1)[1]
            if suffix in self.registry:
                return suffix
        else:
            prefixed = "plugin." + text
            if prefixed in self.registry:
                return prefixed
        return ""

    def _ensure_loaded(self, plugins_dir=None):
        target = self._resolve_plugins_dir(plugins_dir)
        if not self.loaded_plugins_dir or target != self.loaded_plugins_dir:
            self.refresh_plugins(plugins_dir=target)

    def _resolve_plugins_dir(self, plugins_dir=None):
        return str(plugins_dir or self.plugins_dir or (Path(self._resolve_app_dir()) / "plugins"))

    def _resolve_app_dir(self):
        if self.app_dir:
            return str(self.app_dir)
        return str(Path(__file__).resolve().parents[1])

    @staticmethod
    def _plugin_sort_key(plugin_id, item):
        return str((item or {}).get("info", {}).get("name") or plugin_id)


def plugin_node_type_id(plugin_id):
    text = str(plugin_id or "").strip()
    if not text:
        return "core.plugin"
    return text if text.startswith("plugin.") else "plugin." + text


def _build_plugin_display_map(registry):
    display_map = {}
    used_names = {}
    for plugin_id, item in sorted(registry.items(), key=lambda kv: PluginService._plugin_sort_key(kv[0], kv[1])):
        name = str(item.get("info", {}).get("name", plugin_id)).strip() or plugin_id
        suffix = " [仅独立]" if item.get("load_status") == "仅独立环境运行" else ""
        display = f"插件 / {name}{suffix}"
        if display in used_names:
            used_names[display] += 1
            display = f"插件 / {name} ({plugin_id}){suffix}"
        else:
            used_names[display] = 1
        display_map[display] = plugin_id
    return display_map


def _plugin_badges(item):
    badges = ["插件"]
    if item.get("load_status"):
        badges.append(str(item.get("load_status")))
    if item.get("import_ok"):
        badges.append("可内置运行")
    else:
        badges.append("独立环境")
    return badges


def _plugin_is_headless_runnable(item):
    item = item or {}
    return bool(item.get("import_ok") and item.get("module") is not None)


def _make_plugin_service_input_data(plugin_id, input_table=None, context=None):
    input_table = input_table or {}
    headers = list(input_table.get("headers", []) or [])
    rows = [list(row) for row in (input_table.get("rows", []) or [])]
    input_tables = {}
    if isinstance(context, dict):
        input_tables.update(context.get("input_tables", {}) or {})
        for name, table in (context.get("transit_tables", {}) or {}).items():
            input_tables.setdefault(f"中转:{name}", {
                "type": "table",
                "headers": list((table or {}).get("headers", []) or []),
                "rows": [list(row) for row in ((table or {}).get("rows", []) or [])],
            })
    input_tables.setdefault("当前表", {"type": "table", "headers": headers, "rows": rows})
    input_tables.setdefault("workflow_current", {"type": "table", "headers": headers, "rows": rows})
    input_tables.setdefault("primary", {"type": "table", "headers": headers, "rows": rows})
    return make_plugin_input_data(plugin_id, headers, rows, input_tables)


def _make_plugin_service_context(plugin_id, *, config=None, context=None, execute_actions=False):
    context = context or {}
    return {
        "plugin_id": plugin_id,
        "node_name": (config or {}).get("name") or (config or {}).get("node_name") or "插件节点",
        "is_preview": not bool(execute_actions),
        "execute_actions": bool(execute_actions),
        "is_config_probe": bool(context.get("is_config_probe")) if isinstance(context, dict) else False,
        "transit_tables": (context or {}).get("transit_tables", {}) if isinstance(context, dict) else {},
        "input_tables": (context or {}).get("input_tables", {}) if isinstance(context, dict) else {},
        "safety_policy": (context or {}).get("safety_policy", {}) if isinstance(context, dict) else {},
    }


def _plugin_failure(code, message, path):
    return {
        "ok": False,
        "issues": [make_issue("error", code, message, path=path, source="PluginService")],
    }


def _plugin_config_form_groups(default_config, parameter_schema):
    parameter_fields = [_parameter_field_schema(field) for field in parameter_schema or [] if isinstance(field, dict)]
    parameter_help = "插件参数 JSON。具体参数 schema 已在 parameters 字段中返回。"
    if parameter_fields:
        names = "、".join(field.get("label") or field.get("key", "") for field in parameter_fields[:8])
        parameter_help = f"插件参数 JSON。已声明参数：{names}" + ("..." if len(parameter_fields) > 8 else "")
    return [
        {
            "title": "插件",
            "fields": [
                {"key": "plugin_id", "label": "插件 ID", "type": "text", "help": "由后端插件注册表生成。"},
                {
                    "key": "run_mode",
                    "label": "运行环境",
                    "type": "select",
                    "choices": ["主程序内置环境", "插件独立环境"],
                    "help": "选择插件运行方式。",
                },
            ],
        },
        {
            "title": "插件参数",
            "fields": [
                {"key": "params", "label": "参数 JSON", "type": "json", "help": parameter_help},
                {"key": "input_tables", "label": "输入表", "type": "json", "help": "插件多输入表配置。"},
            ],
            "parameters": parameter_fields,
        },
        {
            "title": "输出与日志",
            "fields": [
                {
                    "key": "output_mode",
                    "label": "输出方式",
                    "type": "select",
                    "choices": ["使用插件返回结果", "保存为中转副表", "追加到中转副表"],
                },
                {"key": "save_output_as_transit", "label": "保存为中转", "type": "bool"},
                {"key": "transit_name", "label": "中转名称", "type": "text"},
                {
                    "key": "transit_conflict_mode",
                    "label": "中转冲突",
                    "type": "select",
                    "choices": ["覆盖", "追加"],
                },
                {"key": "save_plugin_log_file", "label": "保存日志文件", "type": "bool"},
                {"key": "save_plugin_log_sqlite", "label": "日志写入 SQLite", "type": "bool"},
                {"key": "save_plugin_log_transit", "label": "日志写入中转", "type": "bool"},
                {"key": "plugin_log_transit_name", "label": "日志中转名", "type": "text"},
            ],
        },
        {
            "title": "独立环境",
            "fields": [
                {"key": "external_python", "label": "Python 路径", "type": "path"},
                {"key": "external_env_dir", "label": "环境目录", "type": "directory"},
                {"key": "external_entry", "label": "入口文件", "type": "path"},
                {"key": "external_timeout", "label": "超时秒数", "type": "number"},
            ],
        },
    ]


def _parameter_field_schema(field):
    key = str(field.get("name") or "").strip()
    field_type = _normalize_parameter_type(field.get("type"))
    return {
        "key": key,
        "label": str(field.get("label") or field.get("title") or key),
        "type": field_type,
        "choices": list(field.get("choices") or field.get("options") or []),
        "default": copy.deepcopy(field.get("default", "")),
        "help": str(field.get("help") or field.get("description") or ""),
        "required": bool(field.get("required", False)),
    }


def _normalize_parameter_type(value):
    text = str(value or "text").strip().lower()
    mapping = {
        "str": "text",
        "string": "text",
        "text": "text",
        "textarea": "textarea",
        "int": "number",
        "integer": "number",
        "float": "number",
        "number": "number",
        "bool": "bool",
        "boolean": "bool",
        "select": "select",
        "choice": "select",
        "field": "field_select",
        "field_select": "field_select",
        "multi_field_select": "field_multi_select",
        "field_multi_select": "field_multi_select",
        "file": "path",
        "path": "path",
        "directory": "directory",
        "dir": "directory",
        "json": "json",
    }
    return mapping.get(text, "text")


def _sanitize_path_segment(value, default):
    text = str(value or "").strip() or default
    text = re.sub(r'[<>:"/\\|?*\s]+', "_", text)
    text = text.strip("._")
    return text or default
