# -*- coding: utf-8 -*-
"""UI-free plugin discovery and metadata service."""

from __future__ import annotations

import copy
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from db.table_manager import TableAccessManager
from engine.issue_schema import has_error_issues, make_issue
from plugin_runtime.scanner import scan_plugins
from workflow import plugin_runtime_services
from workflow.nodes.plugin_nodes import (
    is_external_plugin_mode,
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
    db_path: str = ""
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
        default_config = self.make_plugin_default_config(key, plugins_dir=plugins_dir)
        capabilities = _plugin_capabilities(item, plugin)
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
            "capabilities": capabilities,
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
        external_mode = _plugin_should_run_external(config, item)
        if not _plugin_is_headless_runnable(item):
            return _plugin_failure(
                "plugin_not_headless_runnable",
                f"插件暂不支持 headless 执行：{key}",
                "/plugin_id",
            )
        params = dict(params if params is not None else (config or {}).get("params", {}))
        input_data = _make_plugin_service_input_data(key, input_table, context)
        plugin_context = _make_plugin_service_context(key, config=config, context=context)
        if external_mode:
            return {"ok": True, "plugin_id": key, "issues": []}
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
        external_mode = _plugin_should_run_external(config, item)
        if not _plugin_is_headless_runnable(item):
            return _plugin_failure(
                "plugin_not_headless_runnable",
                f"插件暂不支持 headless 执行：{key}",
                "/plugin_id",
            )
        params = dict(params if params is not None else (config or {}).get("params", {}))
        runtime_context = context if isinstance(context, dict) else {}
        self._ensure_runtime_context_snapshot(runtime_context)
        input_data = _make_plugin_service_input_data(key, input_table, runtime_context)
        plugin_context = _make_plugin_service_context(
            key,
            config=config,
            context=runtime_context,
            execute_actions=execute_actions,
        )
        validation = self.validate_plugin_config(
            key,
            params,
            input_table=input_table,
            context=runtime_context,
            config=config,
            plugins_dir=plugins_dir,
        )
        if not validation.get("ok"):
            return validation
        try:
            if external_mode:
                adapter = _PluginServiceExternalAdapter(self)
                result = plugin_runtime_services.run_external_plugin_process(
                    adapter,
                    item,
                    input_data,
                    params,
                    _normalize_external_plugin_config(key, item, config),
                    runtime_context,
                    execute_actions=execute_actions,
                )
            else:
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

    def run_plugin_custom_config_window(self, plugin_id, *, config=None, input_table=None, context=None, parent=None, plugins_dir=None):
        self._ensure_loaded(plugins_dir)
        key = self._resolve_plugin_key(plugin_id)
        if not key:
            return _plugin_failure("plugin_not_found", f"未找到插件：{plugin_id}", "/plugin_id")
        item = self.registry.get(key, {})
        module = item.get("module")
        opener = getattr(module, "open_config_window", None)
        if not callable(opener):
            return _plugin_failure(
                "plugin_custom_config_unavailable",
                f"插件未提供旧版自定义设置窗口：{key}",
                "/plugin_id",
            )

        current_config = copy.deepcopy(config or self.make_plugin_default_config(key))
        params = dict(current_config.get("params", {}) or {})
        runtime_context = context if isinstance(context, dict) else {}
        self._ensure_runtime_context_snapshot(runtime_context)
        input_data = _make_plugin_service_input_data(key, input_table, runtime_context)
        plugin_context = _make_plugin_service_context(
            key,
            config=current_config,
            context=runtime_context,
            execute_actions=False,
        )
        adapter = _PluginServiceExternalAdapter(self)
        plugin_context.update({
            "input_tables": input_data.get("tables", {}) or {},
            "plugin_input_table_specs": copy.deepcopy(current_config.get("input_tables", [])),
            "plugin_data_dir": adapter.get_plugin_data_dir(key),
            "log_dir": adapter.get_plugin_log_dir(),
            "db_path": adapter.get_workflow_db_path(runtime_context),
        })

        try:
            result = opener(parent, dict(params), plugin_context)
        except Exception as exc:
            return _plugin_failure("plugin_custom_config_error", str(exc), "/params")
        if not isinstance(result, dict):
            return {
                "ok": True,
                "plugin_id": key,
                "changed": False,
                "params": params,
                "config": current_config,
                "issues": [],
            }
        updated_config = copy.deepcopy(current_config)
        updated_config["params"] = copy.deepcopy(result)
        return {
            "ok": True,
            "plugin_id": key,
            "changed": result != params,
            "params": copy.deepcopy(result),
            "config": updated_config,
            "issues": [],
        }

    def validate_plugin_config_patch(self, plugin_id, *, patch=None, config=None, input_table=None, context=None, plugins_dir=None):
        schema_result = self.get_plugin_schema(plugin_id, plugins_dir=plugins_dir)
        if not schema_result.get("ok"):
            return schema_result
        key = self._resolve_plugin_key(plugin_id)
        item = self.registry.get(key, {})
        module = item.get("module")
        validator = getattr(module, "validate_config_patch", None)
        if not callable(validator):
            return _plugin_failure(
                "plugin_config_patch_unsupported",
                f"插件未提供配置修改校验接口：{key}",
                "/patch",
            )
        current_config = copy.deepcopy(config or schema_result.get("default_config") or {})
        if not isinstance(current_config, dict):
            current_config = copy.deepcopy(schema_result.get("default_config") or {})
        params = copy.deepcopy(current_config.get("params", {}) or {})
        runtime_context = context if isinstance(context, dict) else {}
        _input_data, plugin_context = self._make_plugin_config_probe_context(
            key,
            current_config,
            input_table,
            runtime_context,
        )
        patch_payload = copy.deepcopy(patch or {})
        try:
            result = validator(copy.deepcopy(params), copy.deepcopy(plugin_context), patch_payload)
        except Exception as exc:
            return _plugin_failure("plugin_config_patch_validation_error", str(exc), "/patch")
        return _normalize_plugin_config_patch_validation_result(key, result, patch_payload)

    def apply_plugin_config_patch(self, plugin_id, *, patch=None, config=None, input_table=None, context=None, plugins_dir=None):
        schema_result = self.get_plugin_schema(plugin_id, plugins_dir=plugins_dir)
        if not schema_result.get("ok"):
            return schema_result
        key = self._resolve_plugin_key(plugin_id)
        item = self.registry.get(key, {})
        module = item.get("module")
        applier = getattr(module, "apply_config_patch", None)
        if not callable(applier):
            return _plugin_failure(
                "plugin_config_patch_unsupported",
                f"插件未提供配置修改写回接口：{key}",
                "/patch",
            )
        validation = self.validate_plugin_config_patch(
            key,
            patch=patch,
            config=config,
            input_table=input_table,
            context=context,
            plugins_dir=plugins_dir,
        )
        if not validation.get("ok"):
            return validation
        current_config = copy.deepcopy(config or schema_result.get("default_config") or {})
        if not isinstance(current_config, dict):
            current_config = copy.deepcopy(schema_result.get("default_config") or {})
        params = copy.deepcopy(current_config.get("params", {}) or {})
        runtime_context = context if isinstance(context, dict) else {}
        _input_data, plugin_context = self._make_plugin_config_probe_context(
            key,
            current_config,
            input_table,
            runtime_context,
        )
        patch_payload = copy.deepcopy(patch or {})
        try:
            result = applier(copy.deepcopy(params), copy.deepcopy(plugin_context), patch_payload)
        except Exception as exc:
            return _plugin_failure("plugin_config_patch_apply_error", str(exc), "/patch")
        if not isinstance(result, dict):
            return _plugin_failure(
                "plugin_config_patch_apply_invalid",
                "插件配置写回接口必须返回 dict。",
                "/patch",
            )
        if result.get("ok") is False:
            if result.get("issues"):
                payload = copy.deepcopy(result)
                payload.setdefault("plugin_id", key)
                return payload
            return _plugin_failure(
                "plugin_config_patch_apply_failed",
                str(result.get("message") or "插件配置写回失败"),
                "/patch",
            )
        updated_config = copy.deepcopy(result.get("config") or current_config)
        updated_params = copy.deepcopy(result.get("params") if "params" in result else updated_config.get("params", params))
        if not isinstance(updated_config, dict):
            updated_config = copy.deepcopy(current_config)
        updated_config["params"] = copy.deepcopy(updated_params or {})
        described = self.describe_plugin_config(
            key,
            config=updated_config,
            input_table=input_table,
            context=runtime_context,
            plugins_dir=plugins_dir,
        )
        applied_patch = copy.deepcopy(result.get("patch") or validation.get("patch") or patch_payload)
        return {
            "ok": True,
            "plugin_id": key,
            "patch": applied_patch,
            "changed": bool(result.get("changed", updated_config != current_config)),
            "message": str(result.get("message") or "插件配置已更新"),
            "params": copy.deepcopy(updated_config.get("params", {}) or {}),
            "config": updated_config,
            "description": described,
            "issues": copy.deepcopy(result.get("issues") or []),
        }

    def describe_plugin_config(self, plugin_id, *, config=None, input_table=None, context=None, plugins_dir=None):
        schema_result = self.get_plugin_schema(plugin_id, plugins_dir=plugins_dir)
        if not schema_result.get("ok"):
            return schema_result
        key = self._resolve_plugin_key(plugin_id)
        item = self.registry.get(key, {})
        plugin = copy.deepcopy(schema_result.get("plugin") or {})
        schema = copy.deepcopy(schema_result.get("schema") or {})
        current_config = copy.deepcopy(config or schema_result.get("default_config") or {})
        if not isinstance(current_config, dict):
            current_config = copy.deepcopy(schema_result.get("default_config") or {})
        params = copy.deepcopy(current_config.get("params", {}) or {})
        runtime_context = context if isinstance(context, dict) else {}
        input_data, plugin_context = self._make_plugin_config_probe_context(
            key,
            current_config,
            input_table,
            runtime_context,
        )

        resources = []
        module = item.get("module")
        _enrich_plugin_dynamic_choices(schema, module, params, plugin_context)
        settings_file = str(getattr(module, "SETTINGS_FILE", "") or "").strip()
        if settings_file:
            resources.append({
                "resource_id": "plugin_settings",
                "label": "插件设置",
                "kind": "json_file",
                "storage": "plugin_data",
                "file": settings_file,
                "portable": False,
            })
        plugin_extension = _describe_plugin_config_extension(module, params, plugin_context)
        resources = _merge_plugin_config_items(resources, plugin_extension.get("resources"), "resource_id")

        actions = []
        custom_window = plugin.get("custom_config_window") if isinstance(plugin.get("custom_config_window"), dict) else {}
        if custom_window.get("available"):
            legacy_warning = str(
                custom_window.get("warning")
                or "旧版插件设置窗口仅作为兼容 fallback；标准配置请优先使用 schema/patch 协议。"
            )
            actions.append({
                "action_id": "open_legacy_config",
                "label": str(custom_window.get("label") or "打开旧版插件设置"),
                "kind": "compatibility",
                "compatibility": str(custom_window.get("compatibility") or "legacy"),
                "fallback": True,
                "deprecated": True,
                "warning": legacy_warning,
            })
        actions = _merge_plugin_config_items(actions, plugin_extension.get("actions"), "action_id")

        views = [{
            "view_id": "plugin.params",
            "title": "插件参数",
            "kind": "form",
            "form": copy.deepcopy((schema.get("form") or {})),
            "config_path": [],
        }]
        views = _merge_plugin_config_items(views, plugin_extension.get("views"), "view_id")
        if resources:
            views.append({
                "view_id": "plugin.resources",
                "title": "插件资源",
                "kind": "resource_list",
                "resource_ids": [item["resource_id"] for item in resources],
            })

        schema_warning_items = _normalize_plugin_config_warning_items(
            schema.get("warnings") or [],
            plugin_id=key,
            source="plugin_schema",
        )
        extension_warning_items = _normalize_plugin_config_warning_items(
            plugin_extension.get("warnings") or [],
            plugin_id=key,
            source="plugin_config",
        )
        warning_items = schema_warning_items + extension_warning_items
        warning_messages = [
            str(item.get("message") or "").strip()
            for item in warning_items
            if str(item.get("message") or "").strip()
        ]

        extension_schema_version = str(plugin_extension.get("schema_version") or "").strip()
        protocol_family = str(plugin_extension.get("protocol_family") or "plugin_form_config").strip() or "plugin_form_config"
        config_key = str(plugin_extension.get("config_key") or params.get("config_name") or "").strip()
        extension_capabilities = copy.deepcopy(plugin_extension.get("capabilities") or {})
        combined_capabilities = copy.deepcopy(schema.get("capabilities") or {})
        combined_capabilities.update(extension_capabilities)

        return {
            "ok": True,
            "schema_version": "plugin_config.v1",
            "config_schema_version": extension_schema_version or "plugin_config.v1",
            "protocol_family": protocol_family,
            "plugin_id": key,
            "config_key": config_key,
            "plugin": plugin,
            "config": current_config,
            "params": params,
            "node_ui_schema": schema,
            "input_data": {
                "headers": list(input_data.get("headers", []) or []),
                "row_count": len(input_data.get("rows", []) or []),
                "tables": sorted((input_data.get("tables") or {}).keys()),
            },
            "views": views,
            "resources": resources,
            "actions": actions,
            "summary": copy.deepcopy(plugin_extension.get("summary") or {}),
            "context": copy.deepcopy(plugin_extension.get("context") or {}),
            "models": copy.deepcopy(plugin_extension.get("models") or {}),
            "capabilities": combined_capabilities,
            "warnings": warning_messages,
            "warning_items": warning_items,
            "issues": copy.deepcopy(plugin_extension.get("issues") or []),
            "plugin_extension": plugin_extension,
        }

    def _make_plugin_config_probe_context(self, key, current_config, input_table, runtime_context):
        self._ensure_runtime_context_snapshot(runtime_context)
        input_data = _make_plugin_service_input_data(key, input_table, runtime_context)
        adapter = _PluginServiceExternalAdapter(self)
        plugin_context = _make_plugin_service_context(
            key,
            config=current_config,
            context=runtime_context,
            execute_actions=False,
        )
        plugin_context.update({
            "input_tables": input_data.get("tables", {}) or {},
            "plugin_input_table_specs": copy.deepcopy(current_config.get("input_tables", [])),
            "plugin_data_dir": adapter.get_plugin_data_dir(key),
            "log_dir": adapter.get_plugin_log_dir(),
            "db_path": adapter.get_workflow_db_path(runtime_context),
        })
        return input_data, plugin_context

    def _ensure_runtime_context_snapshot(self, context):
        if not isinstance(context, dict):
            return
        snapshot = context.setdefault("workflow_snapshot", {})
        if self.db_path and not snapshot.get("db_path"):
            snapshot["db_path"] = self.db_path
        if not snapshot.get("app_dir"):
            snapshot["app_dir"] = self._resolve_app_dir()

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
        has_custom_config = callable(getattr(item.get("module"), "open_config_window", None))
        warnings = []
        if load_status == "仅独立环境运行":
            warnings.append("插件当前仅能通过独立环境运行。")
        if item.get("import_error"):
            warnings.append(str(item.get("import_error")))
        if has_custom_config:
            warnings.append("该插件提供旧版自定义设置窗口，仅建议作为兼容 fallback 使用。")
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
            "has_custom_config_window": has_custom_config,
            "custom_config_window": {
                "available": has_custom_config,
                "label": "打开旧版插件设置",
                "compatibility": "legacy_tk",
                "fallback": True,
                "deprecated": True,
                "warning": "旧版 Tk 设置窗口仅作为兼容 fallback；标准配置请优先使用 schema/patch 协议。",
            },
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
    return bool((item.get("import_ok") and item.get("module") is not None) or item.get("external_entry") or item.get("path"))


def _plugin_capabilities(item, plugin=None):
    item = item or {}
    plugin = plugin or {}
    module = item.get("module")
    schema = item.get("schema") or []
    has_dynamic_options = callable(getattr(module, "get_dynamic_parameter_options", None)) or any(
        str((field or {}).get("type") or "").strip().lower() == "dynamic_select"
        for field in schema
        if isinstance(field, dict)
    )
    has_config_description = callable(getattr(module, "describe_config", None))
    has_config_patch = callable(getattr(module, "validate_config_patch", None)) and callable(getattr(module, "apply_config_patch", None))
    load_status = str(plugin.get("load_status") or item.get("load_status") or "")
    return {
        "headless_preview": _plugin_is_headless_runnable(item),
        "headless_run": _plugin_is_headless_runnable(item),
        "execute_actions": True,
        "plugin": True,
        "import_ok": bool(plugin.get("import_ok", item.get("import_ok"))),
        "available_run_modes": list(plugin.get("available_run_modes") or item.get("available_run_modes") or []),
        "schema_config": bool(schema),
        "dynamic_options": bool(has_dynamic_options),
        "config_description": bool(has_config_description),
        "config_patch": bool(has_config_patch),
        "legacy_custom_config": bool(plugin.get("has_custom_config_window") or callable(getattr(module, "open_config_window", None))),
        "external_only": load_status == "仅独立环境运行",
    }


def _plugin_should_run_external(config, item):
    item = item or {}
    config = config or {}
    return bool(
        is_external_plugin_mode(config, item)
        or item.get("module") is None
        or not item.get("import_ok")
    )


def _normalize_external_plugin_config(plugin_id, item, config):
    result = copy.deepcopy(config or {})
    result["plugin_id"] = result.get("plugin_id") or plugin_id
    result["run_mode"] = "插件独立环境"
    result.setdefault("external_entry", item.get("external_entry") or item.get("path") or "")
    result.setdefault("external_env_dir", "")
    result.setdefault("external_python", "")
    result.setdefault("external_timeout", "0")
    return result


class _PluginServiceApp:
    def __init__(self, app_dir):
        self.app_dir = app_dir

    @staticmethod
    def sanitize_sql_name(value, default="plugin"):
        return _sanitize_path_segment(value, default)


class _PluginServiceExternalAdapter:
    def __init__(self, service):
        self.service = service
        self.app = _PluginServiceApp(service._resolve_app_dir())

    def find_external_python(self, config, item=None, allow_current=False, return_info=False):
        return plugin_runtime_services.find_external_python(
            config,
            item=item,
            allow_current=allow_current,
            return_info=return_info,
        )

    def get_plugins_dir(self):
        path = self.service._resolve_plugins_dir()
        os.makedirs(path, exist_ok=True)
        return path

    def get_plugin_data_dir(self, plugin_id=None):
        base = Path(self.service._resolve_app_dir()) / "plugin_data"
        if plugin_id:
            base = base / _sanitize_path_segment(plugin_id, "plugin")
        base.mkdir(parents=True, exist_ok=True)
        return str(base)

    def get_plugin_log_dir(self):
        path = Path(self.service._resolve_app_dir()) / "logs" / "plugins"
        path.mkdir(parents=True, exist_ok=True)
        return str(path)

    def get_workflow_db_path(self, context=None):
        context = context or {}
        snapshot = context.get("workflow_snapshot", {}) if isinstance(context, dict) else {}
        return str(snapshot.get("db_path") or context.get("db_path") or self.service.db_path or "")

    def get_workflow_output_table(self, context=None):
        context = context or {}
        snapshot = context.get("workflow_snapshot", {}) if isinstance(context, dict) else {}
        return str(snapshot.get("workflow_name") or context.get("workflow_name") or "")

    def make_external_plugin_json_context(self, config, context=None, execute_actions=False):
        return plugin_runtime_services.make_external_plugin_json_context(
            self,
            config,
            context=context,
            execute_actions=execute_actions,
        )

    def execute_external_plugin_database_requests(self, result, config, context=None, execute_actions=False):
        return plugin_runtime_services.execute_external_plugin_database_requests(
            self,
            result,
            config,
            context=context,
            execute_actions=execute_actions,
        )

    def get_table_manager(self, context=None, node_type="插件节点", node_name="插件节点"):
        db_path = self.get_workflow_db_path(context)
        if not db_path:
            raise ValueError("SQLite 数据库路径为空，无法执行外部插件数据库请求。")
        current = (context or {}).get("current_node_info", {}) if isinstance(context, dict) else {}
        return TableAccessManager(
            db_path,
            node_id=current.get("node_id", ""),
            node_name=node_name or current.get("node_name", ""),
            node_type=node_type,
            context=context if isinstance(context, dict) else None,
            table_access=current.get("table_access") if isinstance(current, dict) else None,
            permission_policy=(context or {}).get("table_access_policy") if isinstance(context, dict) else None,
        )


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


def _enrich_plugin_dynamic_choices(schema, module, params, context):
    provider = getattr(module, "get_dynamic_parameter_options", None)
    if not callable(provider):
        return
    for group in ((schema.get("form") or {}).get("groups") or []):
        for field in group.get("fields") or []:
            if not isinstance(field, dict):
                continue
            options_source = field.get("options_source") or {}
            if str(options_source.get("type") or "") != "plugin_dynamic_choices":
                continue
            param_key = str(field.get("param_key") or options_source.get("param_key") or "").strip()
            if not param_key:
                continue
            try:
                choices = provider(param_key, copy.deepcopy(params or {}), copy.deepcopy(context or {}))
            except Exception as exc:
                field["dynamic_choice_error"] = str(exc)
                choices = []
            values = [str(item) for item in (choices or []) if str(item).strip()]
            field["choices"] = values
            source = dict(options_source)
            source["choices"] = values
            field["options_source"] = source


def _describe_plugin_config_extension(module, params, context):
    descriptor = getattr(module, "describe_config", None)
    if not callable(descriptor):
        return {}
    try:
        result = descriptor(copy.deepcopy(params or {}), copy.deepcopy(context or {}))
    except Exception as exc:
        return {
            "warnings": [f"插件配置描述失败：{exc}"],
            "issues": [
                make_issue(
                    "warning",
                    "plugin_config_descriptor_error",
                    f"插件配置描述失败：{exc}",
                    path="/plugin_extension",
                    source="PluginService",
                )
            ],
        }
    if not isinstance(result, dict):
        return {}
    return copy.deepcopy(result)


def _normalize_plugin_config_warning_items(warnings, *, plugin_id="", source="plugin_config"):
    result = []
    source_text = str(source or "plugin_config").strip() or "plugin_config"
    plugin_text = str(plugin_id or "").strip()
    for index, warning in enumerate(warnings or [], start=1):
        if isinstance(warning, dict):
            item = copy.deepcopy(warning)
            message = str(item.get("message") or item.get("text") or "").strip()
            if not message:
                continue
            item["message"] = message
            item.setdefault("level", "warning")
            item.setdefault("code", f"{source_text}_warning_{index}")
        else:
            message = str(warning or "").strip()
            if not message:
                continue
            item = {
                "code": f"{source_text}_warning_{index}",
                "level": "warning",
                "message": message,
            }
        item.setdefault("source", source_text)
        if plugin_text:
            item.setdefault("plugin_id", plugin_text)
        result.append(item)
    return result


def _normalize_plugin_config_patch_validation_result(plugin_id, result, patch):
    if isinstance(result, dict):
        payload = copy.deepcopy(result)
        if payload.get("ok") is False:
            if payload.get("issues"):
                payload.setdefault("plugin_id", plugin_id)
                return payload
            return _plugin_failure(
                "plugin_config_patch_invalid",
                str(payload.get("message") or "插件配置修改校验失败"),
                "/patch",
            )
        payload["ok"] = True
        payload.setdefault("plugin_id", plugin_id)
        payload.setdefault("patch", copy.deepcopy(patch or {}))
        payload.setdefault("issues", [])
        return payload
    if isinstance(result, tuple):
        ok = bool(result[0]) if result else True
        message = str(result[1]) if len(result) > 1 else ""
        if not ok:
            return _plugin_failure("plugin_config_patch_invalid", message or "插件配置修改校验失败", "/patch")
    elif result is False:
        return _plugin_failure("plugin_config_patch_invalid", "插件配置修改校验失败", "/patch")
    return {
        "ok": True,
        "plugin_id": plugin_id,
        "patch": copy.deepcopy(patch or {}),
        "issues": [],
    }


def _merge_plugin_config_items(base, extra, key):
    result = [copy.deepcopy(item) for item in (base or []) if isinstance(item, dict)]
    seen = {str(item.get(key) or "") for item in result if str(item.get(key) or "")}
    for item in extra or []:
        if not isinstance(item, dict):
            continue
        item_key = str(item.get(key) or "").strip()
        if item_key and item_key in seen:
            continue
        result.append(copy.deepcopy(item))
        if item_key:
            seen.add(item_key)
    return result


def _plugin_config_form_groups(default_config, parameter_schema):
    parameter_fields = []
    plugin_id = str((default_config or {}).get("plugin_id") or "")
    for field in parameter_schema or []:
        if not isinstance(field, dict):
            continue
        field_schema = _parameter_field_schema(field, plugin_id=plugin_id)
        if field_schema:
            parameter_fields.append(field_schema)
    parameter_fields.sort(key=_plugin_parameter_field_sort_key)
    parameter_help = "插件参数 JSON。具体参数 schema 已在 parameters 字段中返回。"
    if parameter_fields:
        names = "、".join(field.get("label") or field.get("key", "") for field in parameter_fields[:8])
        parameter_help = f"插件参数 JSON。已声明参数：{names}" + ("..." if len(parameter_fields) > 8 else "")

    parameter_group_map = _plugin_parameter_group_map(parameter_fields)
    base_parameter_fields = [
        {"key": "params", "label": "参数 JSON", "type": "json", "help": parameter_help},
        *parameter_group_map.pop("插件参数", []),
    ]
    groups = [
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
            "group_key": "plugin.parameters",
            "fields": base_parameter_fields,
            "parameters": parameter_fields,
        },
    ]

    for title, fields in sorted(parameter_group_map.items(), key=lambda item: _plugin_parameter_group_sort_key(item[0], item[1])):
        groups.append({
            "title": title,
            "group_key": "plugin.parameters." + _sanitize_path_segment(title, "group"),
            "advanced": title.startswith("高级参数"),
            "fields": fields,
            "parameters": fields,
        })

    groups.extend([
        {
            "title": "插件输入",
            "group_key": "plugin.inputs",
            "fields": [
                {"key": "input_tables", "label": "输入表", "type": "json", "help": "插件多输入表配置。"},
            ],
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
            "advanced": True,
            "fields": [
                {"key": "external_python", "label": "Python 路径", "type": "path"},
                {"key": "external_env_dir", "label": "环境目录", "type": "directory"},
                {"key": "external_entry", "label": "入口文件", "type": "path"},
                {"key": "external_timeout", "label": "超时秒数", "type": "number"},
            ],
        },
    ])
    return groups


def _plugin_parameter_group_map(parameter_fields):
    groups = {}
    for field in parameter_fields or []:
        if not isinstance(field, dict):
            continue
        title = _plugin_parameter_group_title(field)
        groups.setdefault(title, []).append(field)
    for fields in groups.values():
        fields.sort(key=_plugin_parameter_field_sort_key)
    return groups


def _plugin_parameter_group_title(field):
    group = str((field or {}).get("group") or "").strip()
    advanced = bool((field or {}).get("advanced"))
    if advanced:
        return f"高级参数 / {group}" if group else "高级参数"
    if group:
        return f"插件参数 / {group}"
    return "插件参数"


def _plugin_parameter_group_sort_key(title, fields):
    first = (fields or [{}])[0] if fields else {}
    advanced = str(title or "").startswith("高级参数")
    group_order = _optional_number(first.get("group_order"), default=1000)
    return (1 if advanced else 0, group_order, str(title or ""))


def _plugin_parameter_field_sort_key(field):
    return (
        1 if bool((field or {}).get("advanced")) else 0,
        _optional_number((field or {}).get("group_order"), default=1000),
        _optional_number((field or {}).get("order"), default=1000),
        str((field or {}).get("label") or (field or {}).get("key") or ""),
    )


def _optional_number(value, default=0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _parameter_field_schema(field, *, plugin_id=""):
    key = str(field.get("name") or "").strip()
    if not key:
        return {}
    raw_type = str(field.get("type") or "text").strip().lower()
    field_type = _normalize_parameter_type(field.get("type"))
    schema = {
        "key": f"params.{key}",
        "param_key": key,
        "plugin_id": str(plugin_id or ""),
        "plugin_param_type": raw_type,
        "config_path": ["params", key],
        "label": str(field.get("label") or field.get("title") or key),
        "type": field_type,
        "choices": list(field.get("choices") or field.get("options") or []),
        "default": copy.deepcopy(field.get("default", "")),
        "help": str(field.get("help") or field.get("description") or ""),
        "required": bool(field.get("required", False)),
        "allow_custom": bool(field.get("allow_custom", True)),
    }
    _copy_parameter_ui_metadata(schema, field)
    if field_type == "field_select":
        schema.setdefault("options_source", {"type": "preview_headers"})
        schema.setdefault("action", {
            "key": "pick_preview_header",
            "label": "选择字段",
            "style": "picker",
            "source": "preview_headers",
        })
    elif field_type == "field_multi_select":
        schema.setdefault("options_source", {"type": "preview_headers"})
        schema.setdefault("action", {
            "key": "pick_preview_headers",
            "label": "选择字段",
            "style": "picker",
            "source": "preview_headers",
            "multiple": True,
        })
    elif raw_type == "table_select":
        schema.setdefault("options_source", {"type": "table_names"})
        schema.setdefault("action", {
            "key": "pick_table_name",
            "label": "选择表",
            "style": "picker",
            "source": "table_names",
        })
    elif raw_type == "input_table_select":
        schema.setdefault("options_source", {"type": "plugin_input_tables"})
        schema.setdefault("action", {
            "key": "pick_plugin_input_table",
            "label": "选择输入表",
            "style": "picker",
            "source": "plugin_input_tables",
        })
    elif raw_type == "dynamic_select":
        schema.setdefault("options_source", {
            "type": "plugin_dynamic_choices",
            "plugin_id": str(plugin_id or ""),
            "param_key": key,
        })
    elif field_type == "directory":
        schema.setdefault("action", {
            "key": "browse_directory",
            "label": "选择目录",
            "style": "picker",
        })
    if raw_type == "dynamic_select" and str((schema.get("options_source") or {}).get("type") or "") == "plugin_dynamic_choices":
        source = dict(schema.get("options_source") or {})
        source.setdefault("plugin_id", str(plugin_id or ""))
        source.setdefault("param_key", key)
        schema["options_source"] = source
    return schema


def _copy_parameter_ui_metadata(schema, field):
    passthrough_keys = [
        "group",
        "group_order",
        "order",
        "placeholder",
        "warning",
        "empty_text",
        "invalid_value_text",
        "options_source",
        "advanced",
        "width_hint",
        "min",
        "max",
        "step",
        "unit",
    ]
    for key in passthrough_keys:
        if key in field:
            schema[key] = copy.deepcopy(field.get(key))
    if "action" in field:
        schema["action"] = copy.deepcopy(field.get("action") or {})
    if "visible_when" in field:
        schema["visible_when"] = _normalize_parameter_condition_refs(field.get("visible_when"))
    if "enabled_when" in field:
        schema["enabled_when"] = _normalize_parameter_condition_refs(field.get("enabled_when"))
    for key in ("depends_on", "refresh_on_change"):
        if key not in field:
            continue
        values = field.get(key)
        if isinstance(values, str):
            values = [values]
        schema[key] = [_normalize_parameter_field_ref(value) for value in (values or []) if str(value or "").strip()]


def _normalize_parameter_condition_refs(condition):
    if not isinstance(condition, dict):
        return copy.deepcopy(condition)
    result = {}
    for key, value in condition.items():
        if key in ("all", "any") and isinstance(value, list):
            result[key] = [_normalize_parameter_condition_refs(item) for item in value]
        elif key == "not":
            result[key] = _normalize_parameter_condition_refs(value)
        elif key == "field":
            result[key] = _normalize_parameter_field_ref(value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def _normalize_parameter_field_ref(value):
    text = str(value or "").strip()
    if not text or "." in text:
        return text
    return f"params.{text}"


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
        "dynamic_select": "select",
        "input_table_select": "select",
        "table_select": "table_select",
        "field": "field_select",
        "field_select": "field_select",
        "multi_field_select": "field_multi_select",
        "field_multi_select": "field_multi_select",
        "file": "path",
        "path": "path",
        "folder": "directory",
        "folder_path": "directory",
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
