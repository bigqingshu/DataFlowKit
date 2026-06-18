# -*- coding: utf-8 -*-
"""Helpers for plugin dynamic parameter choices and custom config windows."""

import copy

from workflow.plugin_config_helpers import (
    apply_plugin_custom_config_result,
    build_plugin_dynamic_control_state,
    get_plugin_field_choices_for_table_param,
    get_plugin_input_table_alias_choices,
    get_plugin_static_parameter_choices,
    normalize_plugin_dynamic_parameter_choices,
)


def plugin_config_context_with_live_transit(window, transit_context=None, include_rows=False):
    """插件配置期复用上次真实预览生成的中转副表。"""
    config_context = copy.deepcopy(transit_context or {"transit_tables": {}})
    transit_tables = config_context.setdefault("transit_tables", {})
    reused = []

    live_tables = {}
    if isinstance(getattr(window, "last_workflow_context", None), dict):
        live_tables.update(window.last_workflow_context.get("transit_tables", {}) or {})
    live_tables.update(getattr(window, "current_transit_tables", {}) or {})

    for name, live_item in live_tables.items():
        if not isinstance(live_item, dict):
            continue
        live_rows = list(live_item.get("rows", []) or [])
        if not live_rows:
            continue
        existing = transit_tables.get(name)
        existing_rows = []
        if isinstance(existing, dict):
            existing_rows = list(existing.get("rows", []) or [])
        if existing_rows:
            continue
        if include_rows:
            transit_tables[name] = copy.deepcopy(live_item)
        else:
            headers = list(live_item.get("headers", []) or [])
            source = live_item.get("source", "上次真实预览")
            if isinstance(existing, dict):
                merged = copy.deepcopy(existing)
                if not merged.get("headers") and headers:
                    merged["headers"] = headers
                merged.setdefault("rows", [])
                merged.setdefault("source", source)
                transit_tables[name] = merged
            else:
                transit_tables[name] = {"headers": headers, "rows": [], "source": source}
        if name not in reused:
            reused.append(name)

    if reused:
        config_context["_reused_preview_transit_tables"] = reused
    return config_context


def get_plugin_dynamic_parameter_choices_for_config(
    window,
    item,
    config,
    params,
    spec,
    key,
    headers,
    current_rows=None,
    transit_context=None,
    input_table_headers=None,
):
    choices = get_plugin_static_parameter_choices(spec)
    provider = getattr(item.get("module"), "get_dynamic_parameter_options", None)
    if not callable(provider):
        return choices
    try:
        context = transit_context or {}
        plugin_context = window.make_plugin_context(config, context, execute_actions=False)
        plugin_context["input_table_headers"] = input_table_headers or window.build_plugin_input_table_headers(
            config,
            headers,
            context,
        )
        plugin_context["plugin_input_table_specs"] = copy.deepcopy(config.get("input_tables", []))
        try:
            plugin_context["input_tables"] = window.build_plugin_input_tables(config, headers, current_rows or [], context)
        except Exception as table_exc:
            plugin_context["input_tables_error"] = str(table_exc)
        dynamic = provider(key, dict(params), plugin_context)
        return normalize_plugin_dynamic_parameter_choices(choices, dynamic)
    except Exception:
        return choices


def create_plugin_dynamic_config_context(window, item, config, params, headers, transit_context, current_rows, dynamic_param_controls):
    state = {"refreshing_dynamic_controls": False}

    def set_param(key, value):
        params[key] = value
        config["params"] = params

    def get_input_table_header_map():
        return window.build_plugin_input_table_headers(config, headers, transit_context or {})

    def get_input_table_alias_choices():
        return get_plugin_input_table_alias_choices(
            get_input_table_header_map(),
            config.get("input_tables", []) or [],
        )

    def get_field_choices_for_table_param(spec):
        return get_plugin_field_choices_for_table_param(
            spec,
            params,
            get_input_table_header_map(),
        )

    def get_dynamic_parameter_choices(spec, key):
        return window.get_plugin_dynamic_parameter_choices_for_config(
            item,
            config,
            params,
            spec,
            key,
            headers,
            current_rows=current_rows,
            transit_context=transit_context or {},
            input_table_headers=get_input_table_header_map(),
        )

    def dynamic_choices_for_control(control):
        typ = control.get("type", "")
        spec = control.get("spec", {})
        key = control.get("key", "")
        if typ == "dynamic_select":
            return get_dynamic_parameter_choices(spec, key)
        if typ == "input_table_select":
            return get_input_table_alias_choices()
        if typ == "input_table_field_select":
            return get_field_choices_for_table_param(spec)
        return []

    def refresh_plugin_dynamic_controls():
        state["refreshing_dynamic_controls"] = True
        try:
            window.refresh_plugin_dynamic_config_controls(
                dynamic_param_controls,
                set_param,
                dynamic_choices_for_control,
            )
        finally:
            state["refreshing_dynamic_controls"] = False

    return {
        "set_param": set_param,
        "get_input_table_alias_choices": get_input_table_alias_choices,
        "get_field_choices_for_table_param": get_field_choices_for_table_param,
        "get_dynamic_parameter_choices": get_dynamic_parameter_choices,
        "refresh_plugin_dynamic_controls": refresh_plugin_dynamic_controls,
        "is_refreshing_dynamic_controls": lambda: state["refreshing_dynamic_controls"],
    }


def run_plugin_custom_config_window(
    window,
    item,
    config,
    params,
    headers,
    current_rows=None,
    transit_context=None,
    dynamic_param_controls=None,
    refresh_dynamic_controls=None,
):
    window_transit_context = window.plugin_config_context_with_live_transit(transit_context, include_rows=True)
    plugin_context = window.make_plugin_context(config, window_transit_context or {}, execute_actions=False)
    try:
        input_tables = window.build_plugin_input_tables(config, headers, current_rows or [], window_transit_context or {})
        plugin_context["input_tables"] = input_tables
        plugin_context["plugin_input_table_specs"] = copy.deepcopy(config.get("input_tables", []))
        reuse_note_for_window = window.plugin_config_transit_reuse_note(window_transit_context)
        if reuse_note_for_window:
            plugin_context["plugin_config_data_note"] = reuse_note_for_window
            window.status_var.set(reuse_note_for_window)
    except Exception as table_exc:
        plugin_context["input_tables_error"] = str(table_exc)
        plugin_context["plugin_input_table_specs"] = copy.deepcopy(config.get("input_tables", []))
    result = item["module"].open_config_window(window.window, dict(params), plugin_context)
    if not apply_plugin_custom_config_result(config, params, result):
        return False
    for control in dynamic_param_controls or []:
        key = control.get("key", "")
        var = control.get("var")
        if var is not None and key in params:
            var.set(params.get(key, ""))
    if callable(refresh_dynamic_controls):
        refresh_dynamic_controls()
    return True


def refresh_plugin_dynamic_config_controls(controls, set_param, get_choices):
    for control in controls or []:
        combo = control.get("combo")
        var = control.get("var")
        spec = control.get("spec", {})
        key = control.get("key", "")
        typ = control.get("type", "")
        if combo is None or var is None:
            continue
        current = str(var.get() or "")
        state = build_plugin_dynamic_control_state(
            typ,
            spec,
            current,
            get_choices(control) if callable(get_choices) else [],
        )
        try:
            combo.configure(values=state["choices"])
        except Exception:
            pass
        desired = state["value"]
        if desired != current:
            var.set(desired)
        set_param(key, var.get())
