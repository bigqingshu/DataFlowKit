# -*- coding: utf-8 -*-
"""Helpers for plugin dynamic parameter choices and custom config windows."""

import copy

from workflow.plugin_config_helpers import (
    apply_plugin_custom_config_result,
    build_plugin_dynamic_control_state,
    get_plugin_static_parameter_choices,
    normalize_plugin_dynamic_parameter_choices,
)


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
