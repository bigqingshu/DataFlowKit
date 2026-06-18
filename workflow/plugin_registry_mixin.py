# -*- coding: utf-8 -*-
"""Plugin registry and default node configuration helpers."""

from plugin_runtime.scanner import scan_plugins


class PluginRegistryMixin:
    """Compatibility methods for plugin discovery and default config."""

    def get_node_type_values(self):
        values = list(self.NODE_TYPES)
        values.extend(sorted(getattr(self, "plugin_display_map", {}).keys()))
        return values

    def refresh_plugins(self):
        self.load_plugins(show_status=True)
        if hasattr(self, "node_type_combo"):
            self.node_type_combo["values"] = self.get_node_type_values()
        if self.node_type_var.get() not in self.get_node_type_values():
            self.node_type_var.set(self.NODE_TYPES[0])
        self.rebuild_current_config()

    def load_plugins(self, show_status=False):
        """扫描 plugins 目录并注册插件。"""
        self.plugin_registry = {}
        self.plugin_display_map = {}
        self.plugin_load_errors = []
        plugins_dir = self.get_plugins_dir()
        registry, errors = scan_plugins(plugins_dir)
        self.plugin_registry = registry
        self.plugin_load_errors = errors

        used_names = {}
        external_only_count = 0
        for plugin_id, item in sorted(self.plugin_registry.items(), key=lambda kv: kv[1]["info"].get("name", kv[0])):
            name = str(item["info"].get("name", plugin_id)).strip() or plugin_id
            suffix = ""
            if item.get("load_status") == "仅独立环境运行":
                external_only_count += 1
                suffix = " [仅独立]"
            display = f"插件 / {name}{suffix}"
            if display in used_names:
                used_names[display] += 1
                display = f"插件 / {name} ({plugin_id}){suffix}"
            else:
                used_names[display] = 1
            self.plugin_display_map[display] = plugin_id

        if show_status:
            msg = f"插件刷新完成：已注册 {len(self.plugin_registry)} 个插件"
            if external_only_count:
                msg += f"，其中仅独立环境 {external_only_count} 个"
            if self.plugin_load_errors:
                msg += f"，加载失败 {len(self.plugin_load_errors)} 个"
                first = self.plugin_load_errors[0]
                msg += f"；示例：{first.get('file')} - {first.get('error')}"
            self.status_var.set(msg)

    def default_config_for_plugin(self, plugin_id):
        item = self.plugin_registry.get(plugin_id, {})
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
            params[name] = default
        info = item.get("info", {})
        default_run_mode = info.get("run_mode") or item.get("run_mode_default") or "主程序内置环境"
        if default_run_mode in ("external_python", "独立环境", "插件独立环境"):
            default_run_mode = "插件独立环境"
        else:
            default_run_mode = "主程序内置环境"
        return {
            "plugin_id": plugin_id,
            "params": params,
            "input_tables": [],
            "run_mode": default_run_mode,
            "external_python": "",
            "external_env_dir": self.get_plugin_env_dir(plugin_id),
            "external_entry": item.get("external_entry", item.get("path", "")),
            "external_timeout": "0",
            "output_mode": "使用插件返回结果",
            "save_output_as_transit": False,
            "transit_name": item.get("info", {}).get("name", plugin_id),
            "transit_conflict_mode": "覆盖",
            "save_plugin_log_file": True,
            "save_plugin_log_sqlite": False,
            "save_plugin_log_transit": False,
            "plugin_log_transit_name": f"{item.get('info', {}).get('name', plugin_id)}_日志",
            "plugin_log_in_preview": False,
            "plugin_failure_policy": "停止工作流",
        }
