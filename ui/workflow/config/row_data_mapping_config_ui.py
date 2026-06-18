# -*- coding: utf-8 -*-
"""Tkinter UI helpers for the row-data mapping workflow node configuration."""

import tkinter as tk
from tkinter import ttk


ROW_DATA_MAPPING_MODE_VALUES = ["按行取值展开"]
ROW_DATA_MAPPING_END_MODE_VALUES = ["填充到数据边界", "固定行数", "填充到指定行", "遇到空行停止"]
ROW_DATA_MAPPING_EMPTY_MODE_VALUES = ["跳过空值", "保留空值", "填写固定值"]


def build_row_data_mapping_header(frame):
    ttk.Label(
        frame,
        text="按行向下处理：处理第 N 行时，就取第 N 行指定字段的值，并展开成多行输出。适合“一行对应一个文件，多列是多个修改项”的数据结构。",
        foreground="gray",
        wraplength=1050,
    ).grid(row=0, column=0, columnspan=8, sticky=tk.W, padx=4, pady=(0, 6))


def build_row_data_mapping_basic_section(window, frame, config):
    mode_var = window.add_labeled_combo(
        frame,
        "处理模式：",
        config.get("mode", "按行取值展开"),
        ROW_DATA_MAPPING_MODE_VALUES,
        1,
        0,
        18,
    )
    start_row_var = window.add_labeled_entry(frame, "起始行号：", config.get("start_row", "1"), 1, 2, 10)
    end_mode_var = window.add_labeled_combo(
        frame,
        "结束条件：",
        config.get("end_mode", "填充到数据边界"),
        ROW_DATA_MAPPING_END_MODE_VALUES,
        2,
        0,
        18,
    )
    count_var = window.add_labeled_entry(frame, "固定行数：", config.get("count", "1"), 2, 2, 10)
    end_row_var = window.add_labeled_entry(frame, "结束行号：", config.get("end_row", "1"), 2, 4, 10)

    for var, key in [
        (mode_var, "mode"),
        (start_row_var, "start_row"),
        (end_mode_var, "end_mode"),
        (count_var, "count"),
        (end_row_var, "end_row"),
    ]:
        window.sync_var_to_config(var, config, key)
    return {
        "mode_var": mode_var,
        "start_row_var": start_row_var,
        "end_mode_var": end_mode_var,
        "count_var": count_var,
        "end_row_var": end_row_var,
    }


def build_row_data_mapping_listbox(parent, headers, selected_fields):
    wrap = ttk.Frame(parent)
    listbox = tk.Listbox(wrap, selectmode=tk.MULTIPLE, height=8, exportselection=False)
    yscroll = ttk.Scrollbar(wrap, orient=tk.VERTICAL, command=listbox.yview)
    listbox.configure(yscrollcommand=yscroll.set)
    listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    yscroll.pack(side=tk.RIGHT, fill=tk.Y)

    selected = set(selected_fields or [])
    for index, header in enumerate(headers):
        listbox.insert(tk.END, header)
        if header in selected:
            listbox.selection_set(index)
    return wrap, listbox


def sync_row_data_mapping_selected_fields(listbox, config, key):
    config[key] = [listbox.get(index) for index in listbox.curselection()]


def build_row_data_mapping_field_sections(frame, config, headers):
    ttk.Label(frame, text="取值字段：").grid(row=3, column=0, sticky=tk.NW, padx=4, pady=4)
    value_wrap, value_list = build_row_data_mapping_listbox(frame, headers, config.get("value_fields", []))
    value_wrap.grid(row=3, column=1, columnspan=2, sticky="nsew", padx=4, pady=4)

    ttk.Label(frame, text="保留字段：").grid(row=3, column=3, sticky=tk.NW, padx=4, pady=4)
    keep_wrap, keep_list = build_row_data_mapping_listbox(frame, headers, config.get("keep_fields", []))
    keep_wrap.grid(row=3, column=4, columnspan=2, sticky="nsew", padx=4, pady=4)

    section = {
        "value_wrap": value_wrap,
        "value_list": value_list,
        "keep_wrap": keep_wrap,
        "keep_list": keep_list,
    }
    value_list.bind(
        "<<ListboxSelect>>",
        lambda event=None: sync_row_data_mapping_selected_fields(value_list, config, "value_fields"),
    )
    keep_list.bind(
        "<<ListboxSelect>>",
        lambda event=None: sync_row_data_mapping_selected_fields(keep_list, config, "keep_fields"),
    )
    return section


def select_all_row_data_mapping_fields(listbox, config, key):
    listbox.selection_set(0, tk.END)
    sync_row_data_mapping_selected_fields(listbox, config, key)


def clear_row_data_mapping_fields(listbox, config, key):
    listbox.selection_clear(0, tk.END)
    sync_row_data_mapping_selected_fields(listbox, config, key)


def build_row_data_mapping_field_action_buttons(frame, field_section, config):
    value_list = field_section["value_list"]
    keep_list = field_section["keep_list"]

    btn_row = ttk.Frame(frame)
    btn_row.grid(row=4, column=1, columnspan=5, sticky=tk.W, padx=4, pady=2)
    ttk.Button(
        btn_row,
        text="取值字段全选",
        command=lambda: select_all_row_data_mapping_fields(value_list, config, "value_fields"),
    ).pack(side=tk.LEFT, padx=2)
    ttk.Button(
        btn_row,
        text="清空取值字段",
        command=lambda: clear_row_data_mapping_fields(value_list, config, "value_fields"),
    ).pack(side=tk.LEFT, padx=2)
    ttk.Button(
        btn_row,
        text="保留字段全选",
        command=lambda: select_all_row_data_mapping_fields(keep_list, config, "keep_fields"),
    ).pack(side=tk.LEFT, padx=12)
    ttk.Button(
        btn_row,
        text="清空保留字段",
        command=lambda: clear_row_data_mapping_fields(keep_list, config, "keep_fields"),
    ).pack(side=tk.LEFT, padx=2)
    return btn_row


def build_row_data_mapping_output_section(window, frame, config):
    output_frame = ttk.LabelFrame(frame, text="输出字段设置", padding=6)
    output_frame.grid(row=5, column=0, columnspan=8, sticky="ew", padx=4, pady=8)
    value_name_var = window.add_labeled_entry(output_frame, "目标值字段名：", config.get("output_value_field", "输出内容"), 0, 0, 18)
    source_name_var = window.add_labeled_entry(output_frame, "来源字段名列：", config.get("source_field_name", "来源字段"), 0, 2, 18)
    row_name_var = window.add_labeled_entry(output_frame, "原始行号列：", config.get("original_row_field", "原始行号"), 1, 0, 18)
    status_name_var = window.add_labeled_entry(output_frame, "状态列：", config.get("status_field", "状态"), 1, 2, 18)

    output_source_var = tk.BooleanVar(value=bool(config.get("output_source_field", True)))
    output_row_var = tk.BooleanVar(value=bool(config.get("output_original_row", True)))
    output_status_var = tk.BooleanVar(value=bool(config.get("output_status", True)))
    ttk.Checkbutton(output_frame, text="输出来源字段名", variable=output_source_var).grid(row=2, column=0, sticky=tk.W, padx=4, pady=4)
    ttk.Checkbutton(output_frame, text="输出原始行号", variable=output_row_var).grid(row=2, column=1, sticky=tk.W, padx=4, pady=4)
    ttk.Checkbutton(output_frame, text="输出状态", variable=output_status_var).grid(row=2, column=2, sticky=tk.W, padx=4, pady=4)

    for var, key in [
        (value_name_var, "output_value_field"),
        (source_name_var, "source_field_name"),
        (row_name_var, "original_row_field"),
        (status_name_var, "status_field"),
    ]:
        window.sync_var_to_config(var, config, key)
    window.sync_bool_to_config(output_source_var, config, "output_source_field")
    window.sync_bool_to_config(output_row_var, config, "output_original_row")
    window.sync_bool_to_config(output_status_var, config, "output_status")
    return {
        "frame": output_frame,
        "value_name_var": value_name_var,
        "source_name_var": source_name_var,
        "row_name_var": row_name_var,
        "status_name_var": status_name_var,
        "output_source_var": output_source_var,
        "output_row_var": output_row_var,
        "output_status_var": output_status_var,
    }


def build_row_data_mapping_empty_section(window, frame, config):
    empty_frame = ttk.LabelFrame(frame, text="空值处理", padding=6)
    empty_frame.grid(row=6, column=0, columnspan=8, sticky="ew", padx=4, pady=4)
    empty_mode_var = window.add_labeled_combo(
        empty_frame,
        "空值处理：",
        config.get("empty_mode", "跳过空值"),
        ROW_DATA_MAPPING_EMPTY_MODE_VALUES,
        0,
        0,
        16,
    )
    empty_fixed_var = window.add_labeled_entry(empty_frame, "固定值：", config.get("empty_fixed", "未填写"), 0, 2, 18)
    trim_var = tk.BooleanVar(value=bool(config.get("trim_value", True)))
    ttk.Checkbutton(empty_frame, text="取值前去除首尾空格", variable=trim_var).grid(
        row=1,
        column=0,
        columnspan=2,
        sticky=tk.W,
        padx=4,
        pady=4,
    )

    window.sync_var_to_config(empty_mode_var, config, "empty_mode")
    window.sync_var_to_config(empty_fixed_var, config, "empty_fixed")
    window.sync_bool_to_config(trim_var, config, "trim_value")
    return {
        "frame": empty_frame,
        "empty_mode_var": empty_mode_var,
        "empty_fixed_var": empty_fixed_var,
        "trim_var": trim_var,
    }


def build_row_data_mapping_footer(frame):
    ttk.Label(
        frame,
        text="输出逻辑：外层按行处理，内层按取值字段处理。例如第1行输出本行的编码/客码/PCB，第2行再输出第2行对应字段。",
        foreground="gray",
        wraplength=1050,
    ).grid(row=7, column=0, columnspan=8, sticky=tk.W, padx=4, pady=(8, 4))


def build_row_data_mapping_config(window, config, headers):
    """Build the row-data mapping node configuration UI."""
    frame = ttk.LabelFrame(window.config_frame, text="行数据映射填充节点", padding=8)
    frame.pack(fill=tk.BOTH, expand=True, pady=8)
    headers = list(headers)

    build_row_data_mapping_header(frame)
    build_row_data_mapping_basic_section(window, frame, config)
    field_section = build_row_data_mapping_field_sections(frame, config, headers)
    build_row_data_mapping_field_action_buttons(frame, field_section, config)
    build_row_data_mapping_output_section(window, frame, config)
    build_row_data_mapping_empty_section(window, frame, config)
    build_row_data_mapping_footer(frame)
