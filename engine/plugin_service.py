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
        parameter_metadata = _plugin_parameter_metadata(default_config, item.get("schema", []))
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
            "config_compatibility": copy.deepcopy(plugin.get("config_compatibility") or {}),
            "legacy_config_state": copy.deepcopy(plugin.get("legacy_config_state") or {}),
            "form": {
                "schema_version": PLUGIN_FORM_SCHEMA_VERSION,
                "dynamic_rules": True,
                "groups": _plugin_config_form_groups(default_config, item.get("schema", [])),
            },
            "parameter_metadata": parameter_metadata,
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
        patch_result = _plugin_config_patch_result(
            plugin_id=key,
            patch=applied_patch,
            changed=bool(result.get("changed", updated_config != current_config)),
            message=str(result.get("message") or "插件配置已更新"),
            description=described,
            issues=result.get("issues") or [],
        )
        return {
            "ok": True,
            "plugin_id": key,
            "patch": applied_patch,
            "changed": patch_result["changed"],
            "message": patch_result["message"],
            "patch_result": patch_result,
            "params": copy.deepcopy(updated_config.get("params", {}) or {}),
            "config": updated_config,
            "description": described,
            "issues": copy.deepcopy(result.get("issues") or []),
        }

    def preview_plugin_config_effect(self, plugin_id, *, config=None, input_table=None, context=None, plugins_dir=None):
        schema_result = self.get_plugin_schema(plugin_id, plugins_dir=plugins_dir)
        if not schema_result.get("ok"):
            return schema_result
        key = self._resolve_plugin_key(plugin_id)
        item = self.registry.get(key, {})
        module = item.get("module")
        previewer = getattr(module, "preview_config_effect", None)
        if not callable(previewer):
            return _plugin_failure(
                "plugin_config_effect_unsupported",
                f"插件未提供配置效果预览接口：{key}",
                "/preview_config_effect",
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
        return _preview_plugin_config_effect_extension(module, params, plugin_context, plugin_id=key)

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
        config_effect = _preview_plugin_config_effect_extension(module, params, plugin_context, plugin_id=key)
        resources = _merge_plugin_config_items(resources, plugin_extension.get("resources"), "resource_id")

        actions = []
        custom_window = plugin.get("custom_config_window") if isinstance(plugin.get("custom_config_window"), dict) else {}
        legacy_config_state = plugin.get("legacy_config_state") if isinstance(plugin.get("legacy_config_state"), dict) else {}
        if legacy_config_state.get("available") or custom_window.get("available"):
            legacy_warning = str(
                legacy_config_state.get("warning")
                or custom_window.get("warning")
                or "旧版插件设置窗口仅作为兼容 fallback；标准配置请优先使用 schema/patch 协议。"
            )
            actions.append({
                "action_id": str(legacy_config_state.get("action_id") or "open_legacy_config"),
                "label": str(legacy_config_state.get("label") or custom_window.get("label") or "打开旧版插件设置"),
                "kind": "compatibility",
                "compatibility": str(legacy_config_state.get("compatibility") or custom_window.get("compatibility") or "legacy"),
                "mode": str(legacy_config_state.get("mode") or ""),
                "fallback": bool(legacy_config_state.get("fallback", True)),
                "deprecated": bool(legacy_config_state.get("deprecated", True)),
                "lifecycle": str(legacy_config_state.get("lifecycle") or "legacy_fallback"),
                "preferred": bool(legacy_config_state.get("preferred", False)),
                "ui_role": str(legacy_config_state.get("ui_role") or custom_window.get("ui_role") or "fallback_action"),
                "ui_prominence": str(legacy_config_state.get("ui_prominence") or custom_window.get("ui_prominence") or "low"),
                "ui_placement": str(legacy_config_state.get("ui_placement") or custom_window.get("ui_placement") or "compatibility_menu"),
                "requires_confirmation": bool(legacy_config_state.get("requires_confirmation", custom_window.get("requires_confirmation", True))),
                "migration_target": str(legacy_config_state.get("migration_target") or "describe_config + parameter_metadata + config_patch"),
                "remove_when": str(legacy_config_state.get("remove_when") or "插件已提供等价 schema/patch 配置能力且目标 UI 已完成承接。"),
                "warning": legacy_warning,
                "legacy_config_state": copy.deepcopy(legacy_config_state),
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
        if config_effect.get("ok"):
            views = _merge_plugin_config_items(views, [{
                "view_id": "plugin.config_effect",
                "title": "配置效果",
                "kind": "summary",
                "summary": _plugin_config_effect_summary(config_effect),
                "state": copy.deepcopy(config_effect.get("effect_state") or {}),
            }], "view_id")
        if resources:
            views.append({
                "view_id": "plugin.resources",
                "title": "插件资源",
                "kind": "resource_list",
                "resource_ids": [item["resource_id"] for item in resources],
            })
        views = _plugin_config_views_with_action_state(views, actions)

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
        if config_effect.get("ok"):
            combined_capabilities["config_effect_preview"] = True
            combined_capabilities["preview_config_effect"] = True
        config_sections = _plugin_config_sections(
            views=views,
            resources=resources,
            actions=actions,
            protocol_manifest=plugin_extension.get("protocol_manifest"),
            patch_schema=plugin_extension.get("patch_schema"),
            warning_schema=plugin_extension.get("warning_schema"),
            warning_items=warning_items,
            parameter_metadata=schema.get("parameter_metadata"),
            config_compatibility=plugin.get("config_compatibility"),
            capabilities=combined_capabilities,
        )

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
            "parameter_metadata": copy.deepcopy(schema.get("parameter_metadata") or {}),
            "input_data": {
                "headers": list(input_data.get("headers", []) or []),
                "row_count": len(input_data.get("rows", []) or []),
                "tables": sorted((input_data.get("tables") or {}).keys()),
            },
            "views": views,
            "resources": resources,
            "actions": actions,
            "config_sections": config_sections,
            "summary": copy.deepcopy(plugin_extension.get("summary") or {}),
            "context": copy.deepcopy(plugin_extension.get("context") or {}),
            "models": copy.deepcopy(plugin_extension.get("models") or {}),
            "protocol_manifest": copy.deepcopy(plugin_extension.get("protocol_manifest") or {}),
            "config_compatibility": copy.deepcopy(plugin.get("config_compatibility") or {}),
            "legacy_config_state": copy.deepcopy(plugin.get("legacy_config_state") or {}),
            "capabilities": combined_capabilities,
            "warnings": warning_messages,
            "warning_items": warning_items,
            "issues": copy.deepcopy(plugin_extension.get("issues") or []),
            "config_effect": config_effect if config_effect.get("ok") else {},
            "plugin_extension": plugin_extension,
        }

    def resolve_plugin_parameter_options(
        self,
        plugin_id,
        *,
        field_key="",
        param_key="",
        config=None,
        input_table=None,
        context=None,
        plugins_dir=None,
    ):
        schema_result = self.get_plugin_schema(plugin_id, plugins_dir=plugins_dir)
        if not schema_result.get("ok"):
            return schema_result
        key = self._resolve_plugin_key(plugin_id)
        item = self.registry.get(key, {})
        module = item.get("module")
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
        metadata = (schema_result.get("schema") or {}).get("parameter_metadata") or {}
        field = _plugin_parameter_field_for_options(
            metadata,
            field_key=field_key,
            param_key=param_key,
        )
        if not field:
            return _plugin_failure(
                "plugin_parameter_options_field_not_found",
                f"未找到插件参数字段：{field_key or param_key}",
                "/field_key",
            )
        result = _resolve_plugin_parameter_options_field(
            module,
            field,
            params=params,
            context=plugin_context,
            input_table=input_table,
        )
        return {
            "ok": result.get("ok", True),
            "schema_version": "plugin_parameter_options.v1",
            "plugin_id": key,
            "field_key": field.get("key"),
            "param_key": field.get("param_key"),
            "label": field.get("label"),
            "options_source": copy.deepcopy(field.get("options_source") or {}),
            "choices": list(result.get("choices") or []),
            "candidate_count": len(result.get("choices") or []),
            "empty_text": str(field.get("empty_text") or result.get("empty_text") or ""),
            "allow_custom": bool(field.get("allow_custom", True)),
            "dynamic": bool(result.get("dynamic")),
            "issues": copy.deepcopy(result.get("issues") or []),
        }

    def resolve_plugin_config_options(
        self,
        plugin_id,
        *,
        field_key="",
        current_values=None,
        view_id="",
        section="",
        config=None,
        input_table=None,
        context=None,
        plugins_dir=None,
    ):
        schema_result = self.get_plugin_schema(plugin_id, plugins_dir=plugins_dir)
        if not schema_result.get("ok"):
            return schema_result
        key = self._resolve_plugin_key(plugin_id)
        item = self.registry.get(key, {})
        module = item.get("module")
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
        resolver = getattr(module, "resolve_config_options", None)
        if callable(resolver):
            try:
                result = resolver(
                    copy.deepcopy(params),
                    copy.deepcopy(plugin_context),
                    field_key=field_key,
                    current_values=copy.deepcopy(current_values or {}),
                    view_id=view_id,
                    section=section,
                )
            except Exception as exc:
                return _plugin_failure("plugin_config_options_error", str(exc), "/field_key")
            return _normalize_plugin_config_options_result(
                key,
                result,
                field_key=field_key,
                current_values=current_values,
                view_id=view_id,
                section=section,
            )
        described = self.describe_plugin_config(
            key,
            config=current_config,
            input_table=input_table,
            context=runtime_context,
            plugins_dir=plugins_dir,
        )
        return _resolve_plugin_config_options_from_description(
            key,
            described,
            field_key=field_key,
            current_values=current_values,
            view_id=view_id,
            section=section,
        )

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
        config_compatibility = _plugin_config_compatibility(
            item,
            has_custom_config=has_custom_config,
            load_status=load_status,
        )
        legacy_config_state = _plugin_legacy_config_state(config_compatibility, has_custom_config=has_custom_config)
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
                "label": "兼容旧版设置",
                "compatibility": "legacy_tk",
                "fallback": True,
                "deprecated": True,
                "lifecycle": "legacy_fallback",
                "preferred": False,
                "ui_role": "fallback_action",
                "ui_prominence": "low",
                "ui_placement": "compatibility_menu",
                "requires_confirmation": True,
                "migration_target": "describe_config + parameter_metadata + config_patch",
                "remove_when": "插件已提供等价 schema/patch 配置能力且目标 UI 已完成承接。",
                "warning": "旧版 Tk 设置窗口仅作为兼容 fallback；标准配置请优先使用 schema/patch 协议。",
            },
            "config_compatibility": config_compatibility,
            "legacy_config_state": legacy_config_state,
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


def _plugin_config_compatibility(item, *, has_custom_config=None, load_status=""):
    item = item or {}
    module = item.get("module")
    schema = item.get("schema") or []
    has_schema = bool(schema)
    has_description = callable(getattr(module, "describe_config", None))
    has_patch = callable(getattr(module, "validate_config_patch", None)) and callable(getattr(module, "apply_config_patch", None))
    has_effect_preview = callable(getattr(module, "preview_config_effect", None))
    if has_custom_config is None:
        has_custom_config = callable(getattr(module, "open_config_window", None))
    if has_description and has_patch:
        primary_path = "schema_patch"
        recommendation = "prefer_schema_patch"
    elif has_description:
        primary_path = "describe_config"
        recommendation = "prefer_describe_config"
    elif has_schema:
        primary_path = "schema_form"
        recommendation = "prefer_schema_form"
    elif has_custom_config:
        primary_path = "legacy_custom_config"
        recommendation = "migrate_to_schema"
    else:
        primary_path = "none"
        recommendation = "metadata_required"

    legacy_required = bool(has_custom_config and primary_path == "legacy_custom_config")
    legacy_fallback = bool(has_custom_config and not legacy_required)
    migration_target = "describe_config + parameter_metadata + config_patch" if has_custom_config else ""
    remove_when = "插件已提供等价 schema/patch 配置能力且目标 UI 已完成承接。" if has_custom_config else ""
    compatibility_tier = _plugin_config_compatibility_tier(
        primary_path,
        schema_config=has_schema,
        config_description=has_description,
        config_patch=has_patch,
        legacy_required=legacy_required,
    )
    return {
        "schema_version": "plugin_config_compatibility.v1",
        "compatibility_tier": compatibility_tier,
        "primary_config_path": primary_path,
        "ui_recommendation": recommendation,
        "ui_support": _plugin_config_ui_support(
            compatibility_tier,
            schema_config=has_schema,
            config_description=has_description,
            config_patch=has_patch,
            legacy_custom_config=has_custom_config,
            legacy_required=legacy_required,
        ),
        "schema_config": has_schema,
        "config_description": has_description,
        "config_patch": has_patch,
        "config_effect_preview": has_effect_preview,
        "legacy_custom_config": bool(has_custom_config),
        "legacy_ui_required": legacy_required,
        "legacy_fallback_available": legacy_fallback,
        "legacy_lifecycle": "legacy_fallback" if has_custom_config else "",
        "migration_target": migration_target,
        "remove_when": remove_when,
        "external_only": str(load_status or item.get("load_status") or "") == "仅独立环境运行",
    }


def _plugin_config_compatibility_tier(
    primary_path,
    *,
    schema_config=False,
    config_description=False,
    config_patch=False,
    legacy_required=False,
):
    if config_patch and config_description:
        return "A_SCHEMA_PATCH"
    if config_description:
        return "A_DESCRIBE_CONFIG"
    if schema_config:
        return "B_SCHEMA_FORM"
    if legacy_required or primary_path == "legacy_custom_config":
        return "C_LEGACY_REQUIRED"
    return "D_METADATA_REQUIRED"


def _plugin_config_ui_support(
    compatibility_tier,
    *,
    schema_config=False,
    config_description=False,
    config_patch=False,
    legacy_custom_config=False,
    legacy_required=False,
):
    standard_supported = bool(schema_config or config_description or config_patch)
    direct_ui = {
        "tk": bool(standard_supported or legacy_custom_config),
        "qt": bool(standard_supported or legacy_custom_config),
        "dotnet": bool(standard_supported),
        "web": bool(standard_supported),
        "electron": bool(standard_supported),
    }
    return {
        "schema_version": "plugin_config_ui_support.v1",
        "compatibility_tier": compatibility_tier,
        "standard_supported": standard_supported,
        "legacy_supported": bool(legacy_custom_config),
        "legacy_required": bool(legacy_required),
        "direct_ui": direct_ui,
        "recommended_entry": "standard_protocol" if standard_supported else ("legacy_window" if legacy_required else "unavailable"),
        "unsupported_ui_reason": "" if standard_supported else "插件缺少 schema/describe_config/patch 配置协议。",
    }


def _plugin_legacy_config_state(compatibility=None, *, has_custom_config=False):
    compatibility = compatibility if isinstance(compatibility, dict) else {}
    available = bool(has_custom_config or compatibility.get("legacy_custom_config"))
    legacy_required = bool(compatibility.get("legacy_ui_required"))
    legacy_fallback = bool(compatibility.get("legacy_fallback_available"))
    primary_path = str(compatibility.get("primary_config_path") or "").strip()
    if not available:
        mode = "hidden"
        status = "unavailable"
        recommendation = "hide"
    elif legacy_required:
        mode = "legacy_required"
        status = "required"
        recommendation = "migrate_to_schema"
    else:
        mode = "legacy_fallback"
        status = "fallback"
        recommendation = "prefer_schema_patch" if primary_path == "schema_patch" else "prefer_standard_config"
    migration_target = str(compatibility.get("migration_target") or "").strip()
    remove_when = str(compatibility.get("remove_when") or "").strip()
    warning = ""
    if available:
        warning = (
            "旧版 Tk 设置窗口仅作为兼容 fallback；标准配置请优先使用 schema/patch 协议。"
            if legacy_fallback else
            "该插件仍依赖旧版设置窗口；建议迁移到 describe_config + parameter_metadata + config_patch。"
        )
    return {
        "schema_version": "plugin_legacy_config_state.v1",
        "action_id": "open_legacy_config",
        "available": available,
        "ui_visible": available,
        "ui_enabled_default": available,
        "mode": mode,
        "status": status,
        "compatibility": "legacy_tk" if available else "",
        "label": "兼容旧版设置" if available else "",
        "fallback": bool(legacy_fallback),
        "required": bool(legacy_required),
        "deprecated": available,
        "lifecycle": "legacy_fallback" if available else "",
        "preferred": False,
        "ui_role": "fallback_action" if available else "",
        "ui_prominence": "low" if available else "",
        "ui_placement": "compatibility_menu" if available else "",
        "requires_confirmation": available,
        "primary_config_path": primary_path,
        "ui_recommendation": recommendation,
        "migration_target": migration_target,
        "remove_when": remove_when,
        "warning": warning,
    }


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
    has_config_effect_preview = callable(getattr(module, "preview_config_effect", None))
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
        "config_effect_preview": bool(has_config_effect_preview),
        "preview_config_effect": bool(has_config_effect_preview),
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
        "table_names": (context or {}).get("table_names", []) if isinstance(context, dict) else [],
        "table_columns": (context or {}).get("table_columns", {}) if isinstance(context, dict) else {},
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
    resolved = {}

    def enrich_field(field):
        if not isinstance(field, dict):
            return
        options_source = field.get("options_source") or {}
        if str(options_source.get("type") or "") != "plugin_dynamic_choices":
            return
        param_key = str(field.get("param_key") or options_source.get("param_key") or "").strip()
        if not param_key:
            return
        if param_key not in resolved:
            try:
                choices = provider(param_key, copy.deepcopy(params or {}), copy.deepcopy(context or {}))
                resolved[param_key] = {
                    "choices": [str(item) for item in (choices or []) if str(item).strip()],
                    "error": "",
                }
            except Exception as exc:
                resolved[param_key] = {"choices": [], "error": str(exc)}
        result = resolved[param_key]
        if result.get("error"):
            field["dynamic_choice_error"] = result["error"]
        values = list(result.get("choices") or [])
        field["choices"] = values
        source = dict(options_source)
        source["choices"] = values
        field["options_source"] = source

    for group in ((schema.get("form") or {}).get("groups") or []):
        for field in group.get("fields") or []:
            enrich_field(field)
    parameter_metadata = schema.get("parameter_metadata") if isinstance(schema.get("parameter_metadata"), dict) else {}
    for field in parameter_metadata.get("fields") or []:
        enrich_field(field)


def _plugin_parameter_field_for_options(metadata, *, field_key="", param_key=""):
    fields = [field for field in (metadata.get("fields") or []) if isinstance(field, dict)]
    field_key = str(field_key or "").strip()
    param_key = str(param_key or "").strip()
    if field_key:
        for field in fields:
            if str(field.get("key") or "") == field_key:
                return copy.deepcopy(field)
    if param_key:
        for field in fields:
            if str(field.get("param_key") or "") == param_key:
                return copy.deepcopy(field)
    return {}


def _resolve_plugin_parameter_options_field(module, field, *, params=None, context=None, input_table=None):
    options_source = field.get("options_source") if isinstance(field.get("options_source"), dict) else {}
    source_type = str(options_source.get("type") or "").strip()
    choices = [str(item) for item in (field.get("choices") or []) if str(item).strip()]
    issues = []
    dynamic = False
    if source_type == "preview_headers":
        table = input_table if isinstance(input_table, dict) else {}
        choices = [str(item) for item in (table.get("headers") or []) if str(item).strip()]
    elif source_type == "table_names":
        choices = [str(item) for item in ((context or {}).get("table_names") or []) if str(item).strip()]
    elif source_type == "plugin_input_tables":
        input_tables = (context or {}).get("input_tables") or {}
        aliases = ["当前表", "workflow_current", "primary"]
        aliases.extend(str(key) for key in input_tables.keys() if str(key).strip())
        seen = set()
        choices = []
        for alias in aliases:
            if alias not in seen:
                choices.append(alias)
                seen.add(alias)
    elif source_type == "plugin_dynamic_choices":
        dynamic = True
        provider = getattr(module, "get_dynamic_parameter_options", None)
        param_key = str(field.get("param_key") or options_source.get("param_key") or "").strip()
        if callable(provider) and param_key:
            try:
                choices = [str(item) for item in (provider(param_key, copy.deepcopy(params or {}), copy.deepcopy(context or {})) or []) if str(item).strip()]
            except Exception as exc:
                issues.append(make_issue(
                    "warning",
                    "plugin_parameter_options_failed",
                    f"插件动态候选解析失败：{exc}",
                    path="/options_source",
                    source="PluginService",
                ))
                choices = []
        else:
            choices = [str(item) for item in (options_source.get("choices") or choices) if str(item).strip()]
    return {
        "ok": not has_error_issues(issues),
        "choices": choices,
        "dynamic": dynamic,
        "empty_text": str(field.get("empty_text") or ""),
        "issues": issues,
    }


def _normalize_plugin_config_options_result(
    plugin_id,
    result,
    *,
    field_key="",
    current_values=None,
    view_id="",
    section="",
):
    if not isinstance(result, dict):
        return _plugin_failure(
            "plugin_config_options_invalid",
            "插件配置候选接口必须返回 dict。",
            "/field_key",
        )
    payload = copy.deepcopy(result)
    if payload.get("ok") is False:
        if payload.get("issues"):
            payload.setdefault("plugin_id", plugin_id)
            return payload
        return _plugin_failure(
            "plugin_config_options_failed",
            str(payload.get("message") or "插件配置候选解析失败。"),
            "/field_key",
        )
    choices = _unique_string_values(payload.get("choices") or [])
    payload["ok"] = True
    payload.setdefault("schema_version", "DataFlowKit.plugin_config_options.v1")
    payload.setdefault("plugin_id", plugin_id)
    payload.setdefault("field_key", str(field_key or ""))
    payload.setdefault("view_id", str(view_id or ""))
    payload.setdefault("section", str(section or ""))
    payload.setdefault("source", "plugin_config")
    payload["choices"] = choices
    payload["candidate_count"] = len(choices)
    payload.setdefault("empty_text", "当前没有可选项。")
    payload.setdefault("allow_custom", True)
    payload.setdefault("current_values", copy.deepcopy(current_values or {}))
    payload.setdefault("issues", [])
    return payload


def _resolve_plugin_config_options_from_description(
    plugin_id,
    described,
    *,
    field_key="",
    current_values=None,
    view_id="",
    section="",
):
    if not described.get("ok"):
        return described
    field = _plugin_config_option_field_from_views(
        described.get("views") or [],
        field_key=field_key,
        view_id=view_id,
        section=section,
    )
    context = described.get("context") if isinstance(described.get("context"), dict) else {}
    options_source = field.get("options_source") if isinstance(field.get("options_source"), dict) else {}
    source_type = str(options_source.get("type") or "").strip()
    source_key = str(options_source.get("key") or "").strip()
    source = "unknown"
    choices = []
    empty_text = "字段暂不支持共享候选。"
    if source_type in {"plugin_config_context", "visual_mapping_context"} and source_key:
        source = source_key
        choices = context.get(source_key) or []
        empty_text = _plugin_config_options_empty_text(source_key)
    elif field.get("choices") is not None:
        source = "field_choices"
        choices = field.get("choices") or []
        empty_text = "当前字段没有可选项。"
    return _normalize_plugin_config_options_result(
        plugin_id,
        {
            "ok": True,
            "schema_version": "DataFlowKit.plugin_config_options.v1",
            "protocol_family": str(described.get("protocol_family") or ""),
            "config_key": str(described.get("config_key") or ""),
            "field_key": str(field_key or ""),
            "view_id": str(view_id or field.get("view_id") or ""),
            "section": str(section or field.get("section") or ""),
            "source": source,
            "options_source": copy.deepcopy(options_source),
            "choices": choices,
            "empty_text": empty_text,
            "allow_custom": bool(field.get("allow_custom", True)),
        },
        field_key=field_key,
        current_values=current_values,
        view_id=view_id,
        section=section,
    )


def _plugin_config_option_field_from_views(views, *, field_key="", view_id="", section=""):
    field_key = str(field_key or "").strip()
    view_id = str(view_id or "").strip()
    section = str(section or "").strip()
    if not field_key:
        return {}
    for view in views or []:
        if not isinstance(view, dict):
            continue
        current_view_id = str(view.get("view_id") or "").strip()
        current_section = str(view.get("section") or "").strip()
        if view_id and current_view_id != view_id:
            continue
        if section and current_section != section:
            continue
        item_schema = view.get("item_schema") if isinstance(view.get("item_schema"), dict) else {}
        candidates = []
        candidates.extend(_plugin_config_option_fields(item_schema.get("columns") or []))
        for detail in item_schema.get("detail_sections") or []:
            if not isinstance(detail, dict):
                continue
            candidates.extend(_plugin_config_option_fields(detail.get("fields") or []))
            detail_schema = detail.get("item_schema") if isinstance(detail.get("item_schema"), dict) else {}
            candidates.extend(_plugin_config_option_fields(detail_schema.get("columns") or []))
        for field in candidates:
            if str(field.get("key") or "").strip() == field_key:
                result = copy.deepcopy(field)
                result.setdefault("view_id", current_view_id)
                result.setdefault("section", current_section)
                return result
    return {}


def _plugin_config_option_fields(fields):
    return [field for field in (fields or []) if isinstance(field, dict)]


def _plugin_config_options_empty_text(source_key):
    return {
        "table_names": "当前没有可用输入表。",
        "content_fields": "当前没有可选内容字段。",
        "aux_fields": "当前没有可选辅助字段。",
        "sheet_names": "当前没有可选工作表。",
        "feature_names": "当前没有可选表特征。",
        "rule_names": "当前没有可选规则。",
        "linked_trigger_options": "当前没有可选触发规则。",
    }.get(str(source_key or "").strip(), "当前没有可选项。")


def _unique_string_values(values):
    result = []
    seen = set()
    for value in values or []:
        text = str(value).strip()
        if text and text not in seen:
            result.append(text)
            seen.add(text)
    return result


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


def _preview_plugin_config_effect_extension(module, params, context, *, plugin_id=""):
    previewer = getattr(module, "preview_config_effect", None)
    if not callable(previewer):
        return {}
    try:
        result = previewer(copy.deepcopy(params or {}), copy.deepcopy(context or {}))
    except Exception as exc:
        return _plugin_failure("plugin_config_effect_error", str(exc), "/preview_config_effect")
    if not isinstance(result, dict):
        return _plugin_failure(
            "plugin_config_effect_invalid",
            "插件配置效果预览接口必须返回 dict。",
            "/preview_config_effect",
        )
    payload = copy.deepcopy(result)
    if payload.get("ok") is False:
        if payload.get("issues"):
            payload.setdefault("plugin_id", plugin_id)
            return payload
        return _plugin_failure(
            "plugin_config_effect_failed",
            str(payload.get("message") or "插件配置效果预览失败"),
            "/preview_config_effect",
        )
    payload["ok"] = True
    payload.setdefault("schema_version", "plugin_config_effect.v1")
    payload.setdefault("plugin_id", plugin_id)
    payload.setdefault("summary", {})
    payload.setdefault("warnings", [])
    payload.setdefault("issues", [])
    payload.setdefault("required_input_tables", [])
    payload.setdefault("expected_output_fields", [])
    payload.setdefault("side_effects", [])
    payload["effect_state"] = _plugin_config_effect_state(payload)
    return payload


def _plugin_config_sections(
    *,
    views=None,
    resources=None,
    actions=None,
    protocol_manifest=None,
    patch_schema=None,
    warning_schema=None,
    warning_items=None,
    parameter_metadata=None,
    config_compatibility=None,
    capabilities=None,
):
    sections = []
    protocol_lines = []
    view_items = [item for item in (views or []) if isinstance(item, dict)]
    resource_items = [item for item in (resources or []) if isinstance(item, dict)]
    action_items = [item for item in (actions or []) if isinstance(item, dict)]
    if view_items:
        protocol_lines.append("配置视图：" + "、".join(
            str(item.get("title") or item.get("view_id") or "")
            for item in view_items[:6]
            if str(item.get("title") or item.get("view_id") or "").strip()
        ))
    if resource_items:
        protocol_lines.append("配置资源：" + "、".join(
            str(item.get("label") or item.get("resource_id") or "")
            for item in resource_items[:6]
            if str(item.get("label") or item.get("resource_id") or "").strip()
        ))
    manifest_line = _plugin_protocol_manifest_summary(protocol_manifest)
    if manifest_line:
        protocol_lines.append(manifest_line)
    patch_schema_line = _plugin_protocol_schema_summary(patch_schema, "Patch协议")
    if patch_schema_line:
        protocol_lines.append(patch_schema_line)
    warning_schema_line = _plugin_protocol_schema_summary(warning_schema, "警告协议")
    if warning_schema_line:
        protocol_lines.append(warning_schema_line)

    warning_lines = []
    for item in [item for item in (warning_items or []) if isinstance(item, dict)][:4]:
        line = _format_plugin_warning_item(item)
        if line:
            warning_lines.append(line)
    if warning_lines:
        protocol_lines.append("配置警告：" + "；".join(warning_lines))

    compatibility_actions = [item for item in action_items if str(item.get("kind") or "") == "compatibility"]
    config_actions = [item for item in action_items if str(item.get("kind") or "") != "compatibility"]
    if compatibility_actions:
        protocol_lines.append("兼容动作：" + "、".join(
            str(item.get("label") or item.get("action_id") or "")
            for item in compatibility_actions[:6]
            if str(item.get("label") or item.get("action_id") or "").strip()
        ))
        lifecycle_lines = []
        for item in compatibility_actions[:3]:
            line = _plugin_compatibility_lifecycle_summary(item)
            if line:
                lifecycle_lines.append(line)
        if lifecycle_lines:
            protocol_lines.append("兼容状态：" + "；".join(lifecycle_lines))
        compatibility_warnings = [
            str(item.get("warning") or "").strip()
            for item in compatibility_actions
            if str(item.get("warning") or "").strip()
        ]
        if compatibility_warnings:
            protocol_lines.append("兼容提示：" + "；".join(compatibility_warnings[:3]))
    if config_actions:
        protocol_lines.append("配置动作：" + "、".join(
            str(item.get("label") or item.get("action_id") or "")
            for item in config_actions[:6]
            if str(item.get("label") or item.get("action_id") or "").strip()
        ))
    if any(protocol_lines):
        sections.append({
            "section_id": "plugin.config_protocol",
            "title": "配置协议",
            "schema_version": "plugin_config_section.v1",
            "kind": "summary_lines",
            "lines": [line for line in protocol_lines if line],
        })

    metadata_lines = _plugin_parameter_metadata_lines(parameter_metadata, capabilities=capabilities)
    if metadata_lines:
        sections.append({
            "section_id": "plugin.parameter_metadata",
            "title": "参数元数据",
            "schema_version": "plugin_config_section.v1",
            "kind": "summary_lines",
            "lines": metadata_lines,
        })

    compatibility_lines = _plugin_config_compatibility_lines(config_compatibility)
    if compatibility_lines:
        sections.append({
            "section_id": "plugin.config_compatibility",
            "title": "配置兼容性",
            "schema_version": "plugin_config_section.v1",
            "kind": "summary_lines",
            "lines": compatibility_lines,
        })
    return sections


def _plugin_config_patch_result(*, plugin_id="", patch=None, changed=False, message="", description=None, issues=None):
    patch_payload = copy.deepcopy(patch or {})
    description_payload = description if isinstance(description, dict) else {}
    config_effect = description_payload.get("config_effect") if isinstance(description_payload.get("config_effect"), dict) else {}
    status_message = str(message or "插件配置已更新").strip() or "插件配置已更新"
    operation = str(patch_payload.get("operation") or "").strip()
    view_id = str(patch_payload.get("view_id") or "").strip()
    editor_kind = str(patch_payload.get("editor_kind") or "").strip()
    section = str(patch_payload.get("section") or "").strip()
    target_index = patch_payload.get("target_index")
    target_id = str(patch_payload.get("target_id") or "").strip()
    target = _plugin_config_patch_target_payload(patch_payload)
    result = {
        "schema_version": "plugin_config_patch_result.v1",
        "plugin_id": str(plugin_id or "").strip(),
        "ok": True,
        "changed": bool(changed),
        "message": status_message,
        "status_message": status_message,
        "patch": patch_payload,
        "patch_summary": {
            "operation": operation,
            "view_id": view_id,
            "editor_kind": editor_kind,
            "section": section,
            "target_index": target_index,
            "target_id": target_id,
            "to_index": patch_payload.get("to_index"),
            "path": copy.deepcopy(patch_payload.get("path") or []),
            "action_id": str(patch_payload.get("action_id") or "").strip(),
        },
        "target": target,
        "description_summary": {
            "schema_version": str(description_payload.get("config_schema_version") or description_payload.get("schema_version") or ""),
            "protocol_family": str(description_payload.get("protocol_family") or ""),
            "config_key": str(description_payload.get("config_key") or ""),
            "view_count": len(description_payload.get("views") or []),
            "action_count": len(description_payload.get("actions") or []),
            "warning_count": len(description_payload.get("warning_items") or []),
            "section_count": len(description_payload.get("config_sections") or []),
            "summary": copy.deepcopy(description_payload.get("summary") or {}),
        },
        "config_effect_summary": _plugin_config_effect_summary(config_effect) if config_effect.get("ok") else {},
        "issues": copy.deepcopy(issues or []),
    }
    if operation:
        operation_label = _plugin_patch_operation_label(operation)
        target_parts = []
        if section:
            target_parts.append(section)
        if target_index is not None:
            target_parts.append(f"第 {target_index} 项")
        elif target_id:
            target_parts.append(f"目标 {target_id}")
        if patch_payload.get("to_index") is not None:
            target_parts.append(f"移至 {patch_payload.get('to_index')}")
        if target_parts:
            result["display_summary"] = f"{operation_label}：{' / '.join(str(part) for part in target_parts)}"
        else:
            result["display_summary"] = operation_label
    else:
        result["display_summary"] = status_message
    return result


def _plugin_config_patch_target_payload(patch):
    patch_payload = patch if isinstance(patch, dict) else {}
    view_id = str(patch_payload.get("view_id") or "").strip()
    editor_kind = str(patch_payload.get("editor_kind") or "").strip()
    action_id = str(patch_payload.get("action_id") or "").strip()
    section = str(patch_payload.get("section") or "").strip()
    operation = str(patch_payload.get("operation") or "").strip()
    path = patch_payload.get("path")
    if not isinstance(path, (list, tuple)):
        path = patch_payload.get("target") if isinstance(patch_payload.get("target"), (list, tuple)) else []
    path = list(path)
    target_index = patch_payload.get("target_index")
    if target_index is None:
        target_index = patch_payload.get("index")
    target_id = str(patch_payload.get("target_id") or "").strip()
    target = {
        "schema_version": "plugin_config_patch_target.v1",
        "kind": "plugin_config_patch_target",
        "operation": operation,
        "view_id": view_id,
        "editor_kind": editor_kind,
        "action_id": action_id,
        "section": section,
        "path": copy.deepcopy(path),
        "path_text": _format_plugin_config_path(path),
        "target_index": target_index,
        "target_id": target_id,
        "to_index": patch_payload.get("to_index"),
        "can_focus_view": bool(view_id),
        "can_focus_item": bool(view_id and (target_id or target_index is not None or path)),
    }
    focus_path = ""
    if view_id and section and target_index is not None:
        focus_path = f"/views/{view_id}/sections/{section}/items/{target_index}"
    elif view_id and target_id:
        focus_path = f"/views/{view_id}/items/{target_id}"
    elif view_id:
        focus_path = f"/views/{view_id}"
    target["focus_path"] = focus_path
    return target


def _plugin_patch_operation_label(operation):
    return {
        "append_item": "新增配置项",
        "update_item": "更新配置项",
        "replace_item": "替换配置项",
        "delete_item": "删除配置项",
        "remove_item": "移除配置项",
        "set_enabled": "切换启用状态",
        "move_item": "移动配置项",
        "set_param": "更新参数",
    }.get(str(operation or "").strip(), str(operation or "").strip() or "配置修改")


def _plugin_config_views_with_action_state(views, actions=None):
    result = []
    for view in views or []:
        if not isinstance(view, dict):
            continue
        item = copy.deepcopy(view)
        if str(item.get("kind") or "") == "structured_list":
            action_state = _plugin_structured_list_action_state(item, actions=actions)
            if action_state:
                item["action_state"] = action_state
        result.append(item)
    return result


def _plugin_structured_list_action_state(view, *, actions=None):
    supported_operations = {
        str(item)
        for item in (view.get("patch_operations") or view.get("supported_patch_operations") or [])
        if str(item or "").strip()
    }
    if not supported_operations:
        return {}
    items = [item for item in (view.get("items") or []) if isinstance(item, dict)]
    try:
        item_count = int(view.get("item_count"))
    except Exception:
        item_count = len(items)
    if item_count < 0:
        item_count = len(items)
    selection = view.get("selection") if isinstance(view.get("selection"), dict) else {}
    try:
        selected_index = int(selection.get("default_index", 0 if item_count else -1))
    except Exception:
        selected_index = 0 if item_count else -1
    if item_count <= 0:
        selected_index = -1
    elif selected_index < 0 or selected_index >= item_count:
        selected_index = 0
    action_id = _plugin_config_action_id_for_view(view, actions=actions)
    can_update_item = bool({"update_item", "replace_item"} & supported_operations)

    def button_state(key, label, operation, *, target_offset=None, effective_operation=None):
        effective = effective_operation or operation
        visible = operation in supported_operations
        if operation == "update_item":
            visible = can_update_item
            if "update_item" not in supported_operations and "replace_item" in supported_operations:
                effective = "replace_item"
        requires_selection = operation in {"update_item", "replace_item", "delete_item", "remove_item", "set_enabled", "move_item"}
        enabled = bool(visible)
        disabled_reason = ""
        if requires_selection and selected_index < 0:
            enabled = False
            disabled_reason = "需要先选择配置项。"
        if operation == "move_item" and enabled:
            to_index = selected_index + int(target_offset or 0)
            if to_index < 0 or to_index >= item_count:
                enabled = False
                disabled_reason = "配置项已经在边界位置。"
        return {
            "key": key,
            "label": label,
            "operation": operation,
            "effective_operation": effective,
            "target_offset": target_offset,
            "visible": bool(visible),
            "enabled": bool(enabled),
            "requires_selection": bool(requires_selection),
            "disabled_reason": disabled_reason,
            "action_id": action_id,
        }

    buttons = {
        "append_item": button_state("append_item", "新增", "append_item"),
        "update_item": button_state("update_item", "应用修改", "update_item"),
        "delete_item": button_state("delete_item", "删除", "delete_item"),
        "set_enabled": button_state("set_enabled", "启停", "set_enabled"),
        "move_item_-1": button_state("move_item_-1", "上移", "move_item", target_offset=-1),
        "move_item_1": button_state("move_item_1", "下移", "move_item", target_offset=1),
    }
    return {
        "schema_version": "plugin_config_action_state.v1",
        "view_id": str(view.get("view_id") or ""),
        "editor_kind": str(view.get("editor_kind") or ""),
        "section": str(view.get("section") or ""),
        "action_id": action_id,
        "item_count": item_count,
        "selected_index": selected_index,
        "supported_operations": sorted(supported_operations),
        "buttons": buttons,
    }


def _plugin_config_action_id_for_view(view, *, actions=None):
    if not isinstance(view, dict):
        return ""
    explicit_action_id = str(view.get("action_id") or "").strip()
    if explicit_action_id:
        return explicit_action_id
    view_id = str(view.get("view_id") or "").strip()
    editor_kind = str(view.get("editor_kind") or "").strip()
    for action in actions or []:
        if not isinstance(action, dict):
            continue
        action_id = str(action.get("action_id") or "").strip()
        if not action_id:
            continue
        if view_id and str(action.get("view_id") or "").strip() == view_id:
            return action_id
        if editor_kind and str(action.get("editor_kind") or "").strip() == editor_kind:
            return action_id
    return ""


def _plugin_parameter_metadata_lines(metadata, *, capabilities=None):
    if not isinstance(metadata, dict):
        return []
    lines = []
    field_count = int(metadata.get("field_count") or len(metadata.get("fields") or []))
    group_titles = [
        str(group.get("title") or "").strip()
        for group in (metadata.get("groups") or [])
        if isinstance(group, dict) and str(group.get("title") or "").strip()
    ]
    options_sources = []
    requirements = metadata.get("context_requirements") if isinstance(metadata.get("context_requirements"), dict) else {}
    for item in requirements.get("options_sources") or []:
        text = str(item or "").strip()
        if text:
            options_sources.append(text)
    metadata_capabilities = metadata.get("capabilities") if isinstance(metadata.get("capabilities"), dict) else {}
    merged_capabilities = dict(capabilities or {})
    merged_capabilities.update(metadata_capabilities)
    capability_labels = []
    for key, label in [
        ("dynamic_options", "动态候选"),
        ("conditional_fields", "条件字段"),
        ("field_dependencies", "字段依赖"),
        ("field_actions", "字段动作"),
        ("advanced_fields", "高级字段"),
    ]:
        if merged_capabilities.get(key):
            capability_labels.append(label)
    lines.append(f"参数字段：{field_count} 个")
    if group_titles:
        lines.append("参数分组：" + "、".join(group_titles[:6]))
    if options_sources:
        lines.append("候选来源：" + "、".join(options_sources[:6]))
    if capability_labels:
        lines.append("参数能力：" + "、".join(capability_labels))
    return lines


def _plugin_config_compatibility_lines(compatibility):
    if not isinstance(compatibility, dict):
        return []
    lines = []
    legacy_state = _plugin_legacy_config_state(
        compatibility,
        has_custom_config=bool(compatibility.get("legacy_custom_config")),
    )
    primary_path = str(compatibility.get("primary_config_path") or "").strip()
    recommendation = str(compatibility.get("ui_recommendation") or "").strip()
    compatibility_tier = str(compatibility.get("compatibility_tier") or "").strip()
    if primary_path:
        line = f"主配置路径：{primary_path}"
        if recommendation:
            line += f"；UI建议 {recommendation}"
        if compatibility_tier:
            line += f"；兼容等级 {compatibility_tier}"
        lines.append(line)
    ui_support = compatibility.get("ui_support") if isinstance(compatibility.get("ui_support"), dict) else {}
    direct_ui = ui_support.get("direct_ui") if isinstance(ui_support.get("direct_ui"), dict) else {}
    supported_ui = [
        label
        for key, label in [
            ("tk", "Tk"),
            ("qt", "Qt"),
            ("dotnet", ".NET"),
            ("web", "Web"),
            ("electron", "Electron"),
        ]
        if direct_ui.get(key)
    ]
    if supported_ui:
        entry = str(ui_support.get("recommended_entry") or "").strip()
        line = "可直接支持UI：" + "、".join(supported_ui)
        if entry:
            line += f"；推荐入口 {entry}"
        lines.append(line)
    if legacy_state.get("available"):
        lines.append(
            f"旧窗口状态：{legacy_state.get('mode')}；状态 {legacy_state.get('status')}；UI建议 {legacy_state.get('ui_recommendation')}"
        )
    capability_labels = []
    for key, label in [
        ("schema_config", "schema配置"),
        ("config_description", "配置描述"),
        ("config_patch", "结构化patch"),
        ("config_effect_preview", "配置效果预览"),
        ("legacy_custom_config", "旧版窗口"),
        ("legacy_fallback_available", "旧版fallback"),
        ("external_only", "独立环境"),
    ]:
        if compatibility.get(key):
            capability_labels.append(label)
    if capability_labels:
        lines.append("兼容能力：" + "、".join(capability_labels))
    lifecycle = str(compatibility.get("legacy_lifecycle") or "").strip()
    migration_target = str(compatibility.get("migration_target") or "").strip()
    remove_when = str(compatibility.get("remove_when") or "").strip()
    lifecycle_parts = []
    if lifecycle:
        lifecycle_parts.append(f"生命周期 {lifecycle}")
    if migration_target:
        lifecycle_parts.append(f"迁移目标 {migration_target}")
    if remove_when:
        lifecycle_parts.append(f"退场条件 {remove_when}")
    if lifecycle_parts:
        lines.append("兼容状态：" + "；".join(lifecycle_parts))
    return lines


def _plugin_compatibility_lifecycle_summary(item):
    if not isinstance(item, dict):
        return ""
    parts = []
    lifecycle = str(item.get("lifecycle") or "").strip()
    migration_target = str(item.get("migration_target") or "").strip()
    remove_when = str(item.get("remove_when") or "").strip()
    if lifecycle:
        parts.append(f"生命周期 {lifecycle}")
    if migration_target:
        parts.append(f"迁移目标 {migration_target}")
    if remove_when:
        parts.append(f"退场条件 {remove_when}")
    return "，".join(parts)


def _plugin_protocol_schema_summary(schema, title):
    if not isinstance(schema, dict):
        return ""
    kind = str(schema.get("kind") or schema.get("protocol_family") or "").strip()
    parts = [title + (f"：{kind}" if kind else "")]
    operations = []
    for item in schema.get("operations") or []:
        if isinstance(item, dict):
            operation = str(item.get("operation") or "").strip()
        else:
            operation = str(item or "").strip()
        if operation:
            operations.append(operation)
    if operations:
        parts.append("操作 " + "、".join(operations[:6]))
    fields = []
    for item in schema.get("fields") or []:
        if isinstance(item, dict):
            key = str(item.get("key") or "").strip()
        else:
            key = str(item or "").strip()
        if key:
            fields.append(key)
    if fields:
        parts.append("字段 " + "、".join(fields[:8]))
    sections = schema.get("sections")
    if isinstance(sections, dict) and sections:
        parts.append("区域 " + "、".join(str(key) for key in list(sections.keys())[:6]))
    return "；".join(part for part in parts if part)


def _plugin_protocol_manifest_summary(manifest):
    if not isinstance(manifest, dict):
        return ""
    parts = []
    schema_version = str(manifest.get("schema_version") or "").strip()
    if schema_version:
        parts.append(f"协议清单：{schema_version}")
    interfaces = manifest.get("interfaces") if isinstance(manifest.get("interfaces"), dict) else {}
    enabled_interfaces = [
        key
        for key, enabled in interfaces.items()
        if enabled and str(key or "").strip()
    ]
    if enabled_interfaces:
        parts.append("接口 " + "、".join(enabled_interfaces[:6]))
    views = [item for item in (manifest.get("views") or []) if isinstance(item, dict)]
    if views:
        parts.append(f"视图 {len(views)} 个")
    models = [str(item) for item in (manifest.get("models") or []) if str(item).strip()]
    if models:
        parts.append("模型 " + "、".join(models[:6]))
    patch = manifest.get("patch") if isinstance(manifest.get("patch"), dict) else {}
    patch_sections = [str(item) for item in (patch.get("sections") or []) if str(item).strip()]
    if patch_sections:
        parts.append("Patch区域 " + "、".join(patch_sections[:6]))
    config_effect = manifest.get("config_effect") if isinstance(manifest.get("config_effect"), dict) else {}
    provider = str(config_effect.get("provider") or "").strip()
    if provider:
        parts.append("效果预览 " + provider)
    return "；".join(parts)


def _format_plugin_warning_item(item):
    if not isinstance(item, dict):
        return ""
    message = str(item.get("message") or "").strip()
    if not message:
        return ""
    details = []
    target = item.get("target") if isinstance(item.get("target"), dict) else {}
    view_id = str(item.get("view_id") or target.get("view_id") or "").strip()
    field = str(item.get("field") or target.get("field") or "").strip()
    path = str(item.get("path") or target.get("path") or target.get("focus_path") or "").strip()
    config_path = item.get("config_path")
    if config_path in (None, "", []):
        config_path = target.get("config_path")
    code = str(item.get("code") or "").strip()
    if view_id:
        details.append(f"视图 {view_id}")
    if field:
        details.append(f"字段 {field}")
    if path:
        details.append(f"路径 {path}")
    config_path_text = _format_plugin_config_path(config_path)
    if config_path_text:
        details.append(f"配置 {config_path_text}")
    if code:
        details.append(f"代码 {code}")
    return f"{message}（{'；'.join(details)}）" if details else message


def _format_plugin_config_path(value):
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (list, tuple)):
        parts = [str(part).strip() for part in value if str(part).strip()]
        return ".".join(parts)
    return ""


def _plugin_config_effect_summary(effect):
    effect = effect or {}
    summary = copy.deepcopy(effect.get("summary") or {})
    result = {}
    if isinstance(summary, dict):
        result.update(summary)
    for key, label in [
        ("required_input_tables", "需要输入表"),
        ("expected_output_fields", "预期输出字段"),
        ("side_effects", "运行影响"),
        ("warnings", "提示"),
        ("issues", "问题"),
    ]:
        value = effect.get(key)
        if value not in (None, "", [], {}):
            result[label] = copy.deepcopy(value)
    return result


def _plugin_config_effect_state(effect):
    effect = effect if isinstance(effect, dict) else {}
    summary = _plugin_config_effect_summary(effect)
    required_tables = [
        copy.deepcopy(item)
        for item in (effect.get("required_input_tables") or [])
        if isinstance(item, dict)
    ]
    output_fields = [
        str(item)
        for item in (effect.get("expected_output_fields") or [])
        if str(item).strip()
    ]
    side_effects = [
        copy.deepcopy(item)
        for item in (effect.get("side_effects") or [])
        if isinstance(item, dict)
    ]
    warnings = list(effect.get("warnings") or [])
    issues = list(effect.get("issues") or [])
    if issues:
        status = "error"
    elif warnings:
        status = "warning"
    else:
        status = "ok"
    summary_rows = [
        {"key": str(key), "label": str(key), "value": copy.deepcopy(value)}
        for key, value in summary.items()
    ]
    table_rows = []
    for item in required_tables:
        alias = str(item.get("alias") or "").strip()
        role = str(item.get("role") or "").strip()
        try:
            row_count = int(item.get("row_count") or 0)
        except Exception:
            row_count = 0
        available = bool(item.get("available", bool(row_count or item.get("headers"))))
        table_rows.append({
            "alias": alias,
            "role": role,
            "required": bool(item.get("required", True)),
            "available": available,
            "row_count": row_count,
            "headers": [str(header) for header in (item.get("headers") or [])],
        })
    return {
        "schema_version": "plugin_config_effect_state.v1",
        "plugin_id": str(effect.get("plugin_id") or "").strip(),
        "effect_schema_version": str(effect.get("schema_version") or "").strip(),
        "protocol_family": str(effect.get("protocol_family") or "").strip(),
        "config_key": str(effect.get("config_key") or "").strip(),
        "status": status,
        "status_message": _plugin_config_effect_status_message(status, table_rows, output_fields, side_effects, warnings, issues),
        "summary": summary,
        "summary_rows": summary_rows,
        "required_input_tables": table_rows,
        "expected_output_fields": output_fields,
        "side_effects": side_effects,
        "warning_count": len(warnings),
        "issue_count": len(issues),
    }


def _plugin_config_effect_status_message(status, table_rows, output_fields, side_effects, warnings, issues):
    if status == "error":
        return f"配置效果预览存在问题：{len(issues)} 项。"
    parts = [
        f"输入表 {len(table_rows)} 个",
        f"输出字段 {len(output_fields)} 个",
        f"运行影响 {len(side_effects)} 项",
    ]
    if status == "warning":
        parts.append(f"提示 {len(warnings)} 项")
    return "配置效果预览：" + "，".join(parts) + "。"


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
        item.setdefault("target", _plugin_config_warning_target(item))
        result.append(item)
    return result


def _plugin_config_warning_target(item):
    if not isinstance(item, dict):
        return {}
    view_id = str(item.get("view_id") or "").strip()
    field = str(item.get("field") or "").strip()
    path = str(item.get("path") or "").strip()
    config_path = item.get("config_path")
    config_path_text = _format_plugin_config_path(config_path)
    target = {
        "schema_version": "plugin_config_warning_target.v1",
        "kind": "plugin_config_warning_target",
        "view_id": view_id,
        "field": field,
        "path": path,
        "config_path": copy.deepcopy(config_path if isinstance(config_path, (list, tuple)) else []),
        "config_path_text": config_path_text,
        "can_focus_view": bool(view_id),
        "can_focus_field": bool(view_id and (field or config_path_text or path)),
    }
    focus_path = path
    if not focus_path and view_id and field:
        focus_path = f"/views/{view_id}/fields/{field}"
    elif not focus_path and view_id:
        focus_path = f"/views/{view_id}"
    target["focus_path"] = focus_path
    return target


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
    plugin_id = str((default_config or {}).get("plugin_id") or "")
    parameter_fields = _plugin_parameter_fields(parameter_schema, plugin_id=plugin_id)
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


def _plugin_parameter_fields(parameter_schema, *, plugin_id=""):
    parameter_fields = []
    for field in parameter_schema or []:
        if not isinstance(field, dict):
            continue
        field_schema = _parameter_field_schema(field, plugin_id=plugin_id)
        if field_schema:
            parameter_fields.append(field_schema)
    parameter_fields.sort(key=_plugin_parameter_field_sort_key)
    return parameter_fields


def _plugin_parameter_metadata(default_config, parameter_schema):
    plugin_id = str((default_config or {}).get("plugin_id") or "")
    parameter_fields = _plugin_parameter_fields(parameter_schema, plugin_id=plugin_id)
    group_map = _plugin_parameter_group_map(parameter_fields)
    groups = []
    for title, fields in sorted(group_map.items(), key=lambda item: _plugin_parameter_group_sort_key(item[0], item[1])):
        group_key = "plugin.parameters" if title == "插件参数" else "plugin.parameters." + _sanitize_path_segment(title, "group")
        groups.append({
            "title": title,
            "group_key": group_key,
            "advanced": str(title or "").startswith("高级参数"),
            "field_keys": [str(field.get("key") or "") for field in fields if str(field.get("key") or "")],
            "param_keys": [str(field.get("param_key") or "") for field in fields if str(field.get("param_key") or "")],
        })
    options_sources = sorted({
        str((field.get("options_source") or {}).get("type") or "")
        for field in parameter_fields
        if isinstance(field.get("options_source"), dict) and str((field.get("options_source") or {}).get("type") or "")
    })
    options_source_index = _plugin_parameter_options_source_index(parameter_fields)
    options_source_details = _plugin_parameter_options_source_details(options_source_index)
    field_index = _plugin_parameter_field_index(parameter_fields)
    group_index = {
        group["group_key"]: {
            "title": group["title"],
            "advanced": group["advanced"],
            "field_keys": list(group["field_keys"]),
            "param_keys": list(group["param_keys"]),
        }
        for group in groups
    }
    return {
        "schema_version": "plugin_parameters.v1",
        "plugin_id": plugin_id,
        "field_count": len(parameter_fields),
        "fields": copy.deepcopy(parameter_fields),
        "groups": groups,
        "field_index": field_index,
        "group_index": group_index,
        "layout_index": _plugin_parameter_layout_index(groups, parameter_fields),
        "ui_hints": _plugin_parameter_ui_hints(parameter_fields),
        "dependency_index": _plugin_parameter_dependency_index(parameter_fields),
        "options_source_index": options_source_index,
        "options_source_details": options_source_details,
        "default_params": copy.deepcopy((default_config or {}).get("params") or {}),
        "context_requirements": {
            "options_sources": options_sources,
            "needs_preview_headers": "preview_headers" in options_sources,
            "needs_table_names": "table_names" in options_sources,
            "needs_plugin_input_tables": "plugin_input_tables" in options_sources,
            "needs_dynamic_options": "plugin_dynamic_choices" in options_sources,
        },
        "capabilities": {
            "dynamic_options": "plugin_dynamic_choices" in options_sources,
            "conditional_fields": any(field.get("visible_when") or field.get("enabled_when") for field in parameter_fields),
            "field_dependencies": any(field.get("depends_on") or field.get("refresh_on_change") for field in parameter_fields),
            "field_actions": any(field.get("action") for field in parameter_fields),
            "advanced_fields": any(bool(field.get("advanced")) for field in parameter_fields),
        },
    }


def _plugin_parameter_layout_index(groups, parameter_fields):
    field_order = [str(field.get("key") or "") for field in parameter_fields or [] if str(field.get("key") or "")]
    return {
        "schema_version": "plugin_parameter_layout.v1",
        "field_order": field_order,
        "group_order": [str(group.get("group_key") or "") for group in groups or [] if str(group.get("group_key") or "")],
        "groups": [
            {
                "group_key": group.get("group_key"),
                "title": group.get("title"),
                "advanced": bool(group.get("advanced")),
                "field_keys": list(group.get("field_keys") or []),
                "field_count": len(group.get("field_keys") or []),
            }
            for group in groups or []
        ],
    }


def _plugin_parameter_ui_hints(parameter_fields):
    hinted_fields = []
    advanced_fields = []
    warning_fields = []
    placeholder_fields = []
    numeric_fields = []
    width_hint_fields = []
    for field in parameter_fields or []:
        if not isinstance(field, dict):
            continue
        key = str(field.get("key") or "").strip()
        if not key:
            continue
        hint = {
            "field_key": key,
            "param_key": field.get("param_key"),
            "label": field.get("label"),
            "type": field.get("type"),
        }
        copied_any = False
        for meta_key in ("placeholder", "warning", "empty_text", "invalid_value_text", "width_hint", "unit", "min", "max", "step"):
            if meta_key in field:
                hint[meta_key] = copy.deepcopy(field.get(meta_key))
                copied_any = True
        if field.get("advanced"):
            hint["advanced"] = True
            advanced_fields.append(key)
            copied_any = True
        if "warning" in field:
            warning_fields.append(key)
        if "placeholder" in field:
            placeholder_fields.append(key)
        if any(meta_key in field for meta_key in ("min", "max", "step", "unit")):
            numeric_fields.append(key)
        if "width_hint" in field:
            width_hint_fields.append(key)
        if copied_any:
            hinted_fields.append(hint)
    return {
        "schema_version": "plugin_parameter_ui_hints.v1",
        "field_count": len(hinted_fields),
        "fields": hinted_fields,
        "advanced_fields": advanced_fields,
        "warning_fields": warning_fields,
        "placeholder_fields": placeholder_fields,
        "numeric_fields": numeric_fields,
        "width_hint_fields": width_hint_fields,
    }


def _plugin_parameter_options_source_index(parameter_fields):
    result = {}
    for field in parameter_fields or []:
        if not isinstance(field, dict):
            continue
        key = str(field.get("key") or "").strip()
        source = field.get("options_source")
        source_type = str((source or {}).get("type") or "").strip() if isinstance(source, dict) else ""
        if not key or not source_type:
            continue
        entry = {
            "field_key": key,
            "param_key": field.get("param_key"),
            "label": field.get("label"),
            "type": field.get("type"),
            "options_source": copy.deepcopy(source),
            "allow_custom": bool(field.get("allow_custom", True)),
        }
        for meta_key in ("empty_text", "invalid_value_text", "depends_on", "refresh_on_change", "visible_when", "enabled_when"):
            if meta_key in field:
                entry[meta_key] = copy.deepcopy(field.get(meta_key))
        result.setdefault(source_type, []).append(entry)
    for entries in result.values():
        entries.sort(key=lambda item: str(item.get("field_key") or ""))
    return result


def _plugin_parameter_options_source_details(options_source_index):
    labels = {
        "preview_headers": "当前输入表字段",
        "table_names": "SQLite 数据库表",
        "table_columns": "SQLite 表字段",
        "plugin_input_tables": "插件输入表",
        "plugin_dynamic_choices": "插件动态候选",
    }
    empty_texts = {
        "preview_headers": "当前输入表没有可选字段",
        "table_names": "当前没有可选数据库表",
        "table_columns": "当前表没有可选字段",
        "plugin_input_tables": "当前插件没有可选输入表",
        "plugin_dynamic_choices": "当前没有可选项",
    }
    result = {}
    for source_type, entries in sorted((options_source_index or {}).items()):
        fields = [str(item.get("field_key") or "") for item in entries if str(item.get("field_key") or "")]
        depends_on = sorted({
            str(dep)
            for item in entries
            for dep in (item.get("depends_on") or [])
            if str(dep).strip()
        })
        refresh_on_change = sorted({
            str(dep)
            for item in entries
            for dep in (item.get("refresh_on_change") or [])
            if str(dep).strip()
        })
        result[source_type] = {
            "type": source_type,
            "label": labels.get(source_type, source_type),
            "field_keys": fields,
            "field_count": len(fields),
            "empty_text": empty_texts.get(source_type, "当前没有可选项"),
            "depends_on": depends_on,
            "refresh_on_change": refresh_on_change,
            "dynamic": source_type == "plugin_dynamic_choices",
        }
    return result


def _plugin_parameter_field_index(parameter_fields):
    result = {}
    for field in parameter_fields or []:
        if not isinstance(field, dict):
            continue
        key = str(field.get("key") or "").strip()
        if not key:
            continue
        entry = {
            "param_key": field.get("param_key"),
            "config_path": copy.deepcopy(field.get("config_path") or []),
            "label": field.get("label"),
            "type": field.get("type"),
            "group": _plugin_parameter_group_title(field),
            "advanced": bool(field.get("advanced")),
            "required": bool(field.get("required")),
        }
        options_source = field.get("options_source")
        if isinstance(options_source, dict):
            entry["options_source"] = copy.deepcopy(options_source)
        for meta_key in ("depends_on", "refresh_on_change", "visible_when", "enabled_when"):
            if meta_key in field:
                entry[meta_key] = copy.deepcopy(field.get(meta_key))
        result[key] = entry
    return result


def _plugin_parameter_dependency_index(parameter_fields):
    result = {}
    for field in parameter_fields or []:
        if not isinstance(field, dict):
            continue
        key = str(field.get("key") or "").strip()
        if not key:
            continue
        dependencies = []
        for meta_key in ("depends_on", "refresh_on_change"):
            values = field.get(meta_key) or []
            if isinstance(values, str):
                values = [values]
            dependencies.extend(str(value).strip() for value in values if str(value).strip())
        for meta_key in ("visible_when", "enabled_when"):
            dependencies.extend(_parameter_condition_field_refs(field.get(meta_key)))
        for dependency in sorted(set(dependencies)):
            result.setdefault(dependency, []).append(key)
    for dependents in result.values():
        dependents.sort()
    return result


def _parameter_condition_field_refs(condition):
    if not isinstance(condition, dict):
        return []
    refs = []
    for key, value in condition.items():
        if key == "field":
            text = str(value or "").strip()
            if text:
                refs.append(text)
        elif key in ("all", "any") and isinstance(value, list):
            for item in value:
                refs.extend(_parameter_condition_field_refs(item))
        elif key == "not":
            refs.extend(_parameter_condition_field_refs(value))
    return refs


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
