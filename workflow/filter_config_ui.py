# -*- coding: utf-8 -*-
"""Tkinter UI orchestration for the advanced filter workflow node configuration."""

import tkinter as tk
from tkinter import ttk

from workflow.filter_config_helpers import (
    build_filter_field_refresh_state,
    ensure_filter_config_defaults,
    invert_filter_output_fields_by_indexes,
    select_all_filter_output_fields,
    select_current_table_filter_output_fields,
)


def build_filter_config(window, config, headers, transit_context=None):
    """
    计划节点内的高级筛选配置。
    主输入固定为“上一步结果”，在字段列表中显示为“当前表.字段”。
    可额外勾选 SQLite 数据库中的表，并通过匹配规则把当前表和副表关联起来。
    """
    ensure_filter_config_defaults(config)
    window.normalize_plan_filter_config_field_references(
        config,
        headers,
        config.get("extra_tables", []),
    )

    frame = ttk.LabelFrame(window.config_frame, text="高级筛选节点（支持：上一步结果 + 多表匹配）", padding=8)
    frame.pack(fill=tk.BOTH, expand=True, pady=8)

    risk_section = window.build_filter_header_risk_section(frame, start_row=0)
    risk_var = risk_section["risk_var"]
    risk_label = risk_section["risk_label"]

    def refresh_filter_risk_text():
        window.refresh_filter_risk_text(headers, config, risk_var, risk_label)

    selected_tables = list(config.get("extra_tables", []))
    transit_context = transit_context or {"transit_tables": {}}
    all_fields = window.get_plan_filter_available_fields(headers, selected_tables, transit_context)
    field_state = build_filter_field_refresh_state(
        headers,
        all_fields,
        selected_output_fields=config.get("output_fields", []),
    )
    current_fields = field_state["current_values"]

    def sync_extra_tables(rebuild=False):
        config["extra_tables"] = [table_list.get(index) for index in table_list.curselection()]
        if rebuild:
            refresh_filter_field_sources()

    source_section = window.build_filter_source_table_section(
        frame,
        config,
        headers,
        selected_tables,
        transit_context,
        sync_extra_tables,
        start_row=risk_section["next_row"],
    )
    table_list = source_section["table_list"]

    condition_section = window.build_filter_condition_section(frame, config, all_fields, start_row=3)
    value_source_var = condition_section["value_source_var"]
    value_var = condition_section["value_var"]
    value_combo = condition_section["value_combo"]

    def refresh_condition_value_input(*_):
        window.refresh_filter_condition_value_input(field_state, value_source_var, value_var, value_combo)

    value_source_var.trace_add("write", refresh_condition_value_input)
    refresh_condition_value_input()

    window.build_filter_condition_action_buttons(condition_section, config, refresh_filter_risk_text)

    join_section = window.build_filter_join_section(frame, config, all_fields, current_fields, start_row=4)
    join_logic_var = join_section["join_logic_var"]
    join_logic_var.trace_add("write", lambda *_: refresh_filter_risk_text())
    window.build_filter_join_action_buttons(join_section, config, refresh_filter_risk_text)

    output_section = window.build_filter_output_section(frame, config, all_fields, start_row=5)
    output_actions = window.build_filter_output_action_buttons(output_section, config, headers, field_state)
    refresh_actual_output_text = output_actions["refresh_actual_output_text"]
    sync_output_fields = output_actions["sync_output_fields"]

    def refresh_filter_field_sources():
        window.refresh_filter_field_sources(
            headers,
            config,
            transit_context,
            field_state,
            source_section,
            condition_section,
            join_section,
            output_section,
            sync_output_fields,
            refresh_condition_value_input,
            refresh_filter_risk_text,
        )

    refresh_actual_output_text()
    refresh_filter_risk_text()


def select_all_output_fields(listbox, config):
    fields = select_all_filter_output_fields(listbox.get(0, tk.END))
    listbox.selection_set(0, tk.END)
    config["output_fields"] = fields


def invert_output_fields(listbox, config):
    selected = set(listbox.curselection())
    fields = list(listbox.get(0, tk.END))
    result = invert_filter_output_fields_by_indexes(fields, selected)
    listbox.selection_clear(0, tk.END)
    for index, field in enumerate(fields):
        if index not in selected:
            listbox.selection_set(index)
    config["output_fields"] = result


def select_current_table_output_fields(listbox, config):
    listbox.selection_clear(0, tk.END)
    fields = list(listbox.get(0, tk.END))
    selected = select_current_table_filter_output_fields(fields)
    selected_set = set(selected)
    for index, field in enumerate(fields):
        if field in selected_set:
            listbox.selection_set(index)
    config["output_fields"] = selected
