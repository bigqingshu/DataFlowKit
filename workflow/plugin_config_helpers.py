# -*- coding: utf-8 -*-
"""Pure helpers for plugin node configuration UI."""


def normalize_plugin_run_mode(value, available_run_modes=None, default_value="主程序内置环境"):
    available = list(available_run_modes or [])
    mode = str(value or default_value or "").strip()
    if mode in ("external_python", "独立环境", "插件独立环境"):
        mode = "插件独立环境"
    else:
        mode = "主程序内置环境"
    if available and mode not in available:
        return available[0]
    return mode or (available[0] if available else "插件独立环境")


def build_plugin_load_status_state(load_status, metadata_source="", import_error=""):
    status = str(load_status or "可内置运行")
    text = f"加载状态：{status}"
    if metadata_source:
        text += f"    元信息来源：{metadata_source}"
    if status == "仅独立环境运行":
        text += "    该插件不会在扫描阶段强制导入业务依赖。"
    return {
        "text": text,
        "foreground": "#b26a00" if status == "仅独立环境运行" else "gray",
        "import_error_text": f"主程序环境导入提示：{str(import_error).strip()}" if str(import_error or "").strip() else "",
    }


def ensure_plugin_input_specs(config):
    specs = config.get("input_tables")
    if not isinstance(specs, list):
        specs = []
        config["input_tables"] = specs
    return specs


def default_plugin_input_spec(index, sqlite_tables=None, transit_names=None):
    sqlite_values = list(sqlite_tables or [])
    transit_values = list(transit_names or [])
    return {
        "alias": f"输入表{int(index) + 1}",
        "source_type": "SQLite表",
        "sqlite_table": sqlite_values[0] if sqlite_values else "",
        "transit_table": transit_values[0] if transit_values else "",
        "enabled": True,
    }


def format_plugin_input_spec(spec):
    spec = spec or {}
    alias = str(spec.get("alias") or "").strip() or "输入表"
    source_type = str(spec.get("source_type") or "当前工作流表").strip() or "当前工作流表"
    if source_type == "SQLite表":
        detail = spec.get("sqlite_table") or spec.get("table") or ""
    elif source_type == "中转副表":
        detail = spec.get("transit_table") or spec.get("table") or ""
    else:
        detail = "当前工作流表"
    enabled = "" if spec.get("enabled", True) else " [停用]"
    return f"{alias} <- {source_type}:{detail}{enabled}"


def plugin_input_spec_to_rows(input_specs):
    return [format_plugin_input_spec(spec) for spec in (input_specs or []) if isinstance(spec, dict)]


def build_plugin_input_spec(alias, source_type, sqlite_table="", transit_table="", enabled=True, fallback_index=0):
    normalized_source = str(source_type or "SQLite表").strip() or "SQLite表"
    return {
        "alias": str(alias or "").strip() or f"输入表{int(fallback_index) + 1}",
        "source_type": normalized_source,
        "sqlite_table": str(sqlite_table or "").strip(),
        "transit_table": str(transit_table or "").strip(),
        "enabled": bool(enabled),
    }


def build_plugin_input_table_choices(sqlite_tables=None, transit_context=None):
    return {
        "sqlite_tables": list(sqlite_tables or []),
        "transit_names": sorted((transit_context or {}).get("transit_tables", {}) or {}),
    }


def plugin_config_transit_reuse_note(transit_context=None):
    reused = list((transit_context or {}).get("_reused_preview_transit_tables", []) or [])
    if not reused:
        return ""
    names = "、".join(str(name) for name in reused[:5])
    if len(reused) > 5:
        names += f" 等 {len(reused)} 个"
    return f"插件设置窗口将复用上次真实预览/执行生成的中转副表数据：{names}"


def get_plugin_input_table_alias_choices(table_headers, input_specs):
    table_headers = table_headers or {}
    choices = []
    for key in ("当前表",):
        if key in table_headers and key not in choices:
            choices.append(key)
    for spec in input_specs or []:
        if not isinstance(spec, dict) or spec.get("enabled", True) is False:
            continue
        alias = str(spec.get("alias") or "").strip()
        if alias and alias in table_headers and alias not in choices:
            choices.append(alias)
    for key in table_headers:
        if key not in choices:
            choices.append(key)
    return choices


def resolve_plugin_field_table_alias(spec, params):
    spec = spec or {}
    params = params or {}
    table_param = (
        spec.get("table_param")
        or spec.get("source_table_param")
        or spec.get("depends_on")
        or spec.get("table_alias_param")
    )
    alias = str(params.get(table_param, "") or spec.get("table_alias", "") or spec.get("default_table_alias", "")).strip()
    return alias or "当前表"


def get_plugin_field_choices_for_table_param(spec, params, table_headers):
    alias = resolve_plugin_field_table_alias(spec, params)
    return list((table_headers or {}).get(alias, []) or [])


def get_plugin_static_parameter_choices(spec):
    spec = spec or {}
    return list(spec.get("choices", spec.get("options", [])) or [])


def normalize_plugin_dynamic_parameter_choices(fallback_choices, dynamic_result):
    if isinstance(dynamic_result, dict):
        dynamic_result = dynamic_result.get("choices", dynamic_result.get("options", []))
    if isinstance(dynamic_result, (list, tuple)):
        return [str(value) for value in dynamic_result]
    return list(fallback_choices or [])


def with_current_value_in_choices(value, choices):
    result = [str(v) for v in (choices or [])]
    if value not in (None, ""):
        current = str(value)
        if current not in result:
            result = [current] + result
    return result


def build_plugin_select_initial_value(value, choices, fallback=""):
    values = [str(v) for v in (choices or [])]
    if value not in (None, ""):
        return str(value)
    return values[0] if values else str(fallback or "")


def build_plugin_field_select_initial_value(value, choices, default_value=""):
    values = [str(v) for v in (choices or [])]
    if value not in (None, ""):
        return str(value)
    default_text = str(default_value or "")
    return default_text if default_text in values else (values[0] if values else default_text)


def build_plugin_dynamic_control_state(control_type, spec, current_value, choices):
    spec = spec or {}
    values = [str(v) for v in (choices or [])]
    current = str(current_value or "")
    display_choices = list(values)
    allow_custom = bool(spec.get("allow_custom", True))
    default_value = str(spec.get("default", "") or "")
    desired = current
    if control_type == "input_table_select":
        if current not in values:
            desired = values[0] if values else "当前表"
    elif control_type in ("input_table_field_select", "dynamic_select"):
        if not current:
            desired = default_value if default_value in values else (values[0] if values else default_value)
        elif current not in values:
            if allow_custom:
                display_choices = [current] + [choice for choice in values if choice != current]
            else:
                desired = values[0] if values else default_value
    return {
        "choices": display_choices,
        "value": desired,
    }


def build_plugin_dynamic_select_choices(spec, value, dynamic_choices):
    choices = [str(v) for v in (dynamic_choices or [])]
    return with_current_value_in_choices(value, choices)


def apply_plugin_custom_config_result(config, params, result):
    if not isinstance(result, dict):
        return False
    params.clear()
    params.update(result)
    config["params"] = params
    return True
