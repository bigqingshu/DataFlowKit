# -*- coding: utf-8 -*-
"""Tkinter UI helpers for the dedupe workflow node configuration."""

import tkinter as tk
from tkinter import ttk


DEDUPE_MODE_VALUES = ["整行去重", "指定字段/组合字段去重"]
KEEP_POLICY_VALUES = ["保留第一条", "保留最后一条", "保留非空字段最多", "不删除，仅标记"]
OUTPUT_MODE_VALUES = ["输出去重后的数据", "输出重复项数据", "输出唯一项数据", "输出重复统计表", "原表增加重复标记列"]
EMPTY_KEY_POLICY_VALUES = ["空键参与去重", "空键跳过去重"]


def build_dedupe_general_section(window, frame, config):
    ttk.Label(
        frame,
        text="按整行、指定字段或组合字段识别重复数据；可输出去重结果、重复项、唯一项、统计表，或给原表增加重复标记列。",
        foreground="gray",
        wraplength=1100,
    ).grid(row=0, column=0, columnspan=8, sticky=tk.W, padx=4, pady=(0, 6))

    mode_var = window.add_labeled_combo(
        frame,
        "去重方式：",
        config.get("dedupe_mode", "指定字段/组合字段去重"),
        DEDUPE_MODE_VALUES,
        1,
        0,
        22,
    )
    keep_var = window.add_labeled_combo(
        frame,
        "保留策略：",
        config.get("keep_policy", "保留第一条"),
        KEEP_POLICY_VALUES,
        1,
        2,
        18,
    )
    output_var = window.add_labeled_combo(
        frame,
        "输出模式：",
        config.get("output_mode", "输出去重后的数据"),
        OUTPUT_MODE_VALUES,
        1,
        4,
        22,
    )
    empty_key_var = window.add_labeled_combo(
        frame,
        "空键处理：",
        config.get("empty_key_policy", "空键参与去重"),
        EMPTY_KEY_POLICY_VALUES,
        2,
        0,
        18,
    )
    trim_var = tk.BooleanVar(value=bool(config.get("trim", True)))
    ignore_case_var = tk.BooleanVar(value=bool(config.get("ignore_case", False)))
    marker_var = tk.BooleanVar(value=bool(config.get("add_marker_columns", True)))
    ttk.Checkbutton(frame, text="去除首尾空格", variable=trim_var).grid(row=2, column=2, sticky=tk.W, padx=4, pady=4)
    ttk.Checkbutton(frame, text="忽略大小写", variable=ignore_case_var).grid(row=2, column=3, sticky=tk.W, padx=4, pady=4)
    ttk.Checkbutton(frame, text="输出时增加重复标记列", variable=marker_var).grid(row=2, column=4, columnspan=2, sticky=tk.W, padx=4, pady=4)
    for var, key in [
        (mode_var, "dedupe_mode"),
        (keep_var, "keep_policy"),
        (output_var, "output_mode"),
        (empty_key_var, "empty_key_policy"),
    ]:
        window.sync_var_to_config(var, config, key)
    window.sync_bool_to_config(trim_var, config, "trim")
    window.sync_bool_to_config(ignore_case_var, config, "ignore_case")
    window.sync_bool_to_config(marker_var, config, "add_marker_columns")
    return {
        "mode_var": mode_var,
        "keep_var": keep_var,
        "output_var": output_var,
        "empty_key_var": empty_key_var,
        "trim_var": trim_var,
        "ignore_case_var": ignore_case_var,
        "marker_var": marker_var,
    }


def build_dedupe_key_fields_section(frame, config, headers):
    field_frame = ttk.LabelFrame(frame, text="去重字段（选择“指定字段/组合字段去重”时使用，可多选）", padding=6)
    field_frame.grid(row=3, column=0, columnspan=8, sticky="nsew", padx=4, pady=6)
    field_frame.rowconfigure(0, weight=1)
    field_frame.columnconfigure(0, weight=1)
    listbox = tk.Listbox(field_frame, selectmode=tk.MULTIPLE, height=10, exportselection=False)
    yscroll = ttk.Scrollbar(field_frame, orient=tk.VERTICAL, command=listbox.yview)
    xscroll = ttk.Scrollbar(field_frame, orient=tk.HORIZONTAL, command=listbox.xview)
    listbox.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
    listbox.grid(row=0, column=0, sticky="nsew")
    yscroll.grid(row=0, column=1, sticky="ns")
    xscroll.grid(row=1, column=0, sticky="ew")
    selected = set(config.get("key_fields", []))
    for index, header in enumerate(headers):
        listbox.insert(tk.END, header)
        if header in selected:
            listbox.selection_set(index)
    return {
        "frame": field_frame,
        "listbox": listbox,
    }


def sync_dedupe_key_fields(field_section, config, headers):
    listbox = field_section["listbox"]
    config["key_fields"] = [headers[index] for index in listbox.curselection() if 0 <= index < len(headers)]


def build_dedupe_key_field_action_buttons(field_section, config, headers):
    listbox = field_section["listbox"]

    def sync_key_fields(event=None):
        sync_dedupe_key_fields(field_section, config, headers)

    def select_all():
        listbox.selection_set(0, tk.END)
        sync_key_fields()

    def select_none():
        listbox.selection_clear(0, tk.END)
        sync_key_fields()

    def invert_selection():
        current = set(listbox.curselection())
        listbox.selection_clear(0, tk.END)
        for index in range(len(headers)):
            if index not in current:
                listbox.selection_set(index)
        sync_key_fields()

    listbox.bind("<<ListboxSelect>>", sync_key_fields)
    btns = ttk.Frame(field_section["frame"])
    btns.grid(row=0, column=2, sticky="ns", padx=6)
    ttk.Button(btns, text="全选", command=select_all).pack(fill=tk.X, pady=2)
    ttk.Button(btns, text="全不选", command=select_none).pack(fill=tk.X, pady=2)
    ttk.Button(btns, text="反选", command=invert_selection).pack(fill=tk.X, pady=2)


def build_dedupe_marker_section(window, frame, config):
    marker_frame = ttk.LabelFrame(frame, text="重复标记字段名", padding=6)
    marker_frame.grid(row=4, column=0, columnspan=8, sticky="ew", padx=4, pady=6)
    group_var = window.add_labeled_entry(marker_frame, "重复组编号：", config.get("duplicate_group_field", "重复组编号"), 0, 0, 18)
    status_var = window.add_labeled_entry(marker_frame, "重复状态：", config.get("duplicate_status_field", "重复状态"), 0, 2, 18)
    index_var = window.add_labeled_entry(marker_frame, "组内序号：", config.get("duplicate_index_field", "组内序号"), 0, 4, 18)
    count_var = window.add_labeled_entry(marker_frame, "重复次数：", config.get("duplicate_count_field", "重复次数"), 1, 0, 18)
    keep_flag_var = window.add_labeled_entry(marker_frame, "是否保留：", config.get("keep_flag_field", "是否保留"), 1, 2, 18)
    for var, key in [
        (group_var, "duplicate_group_field"),
        (status_var, "duplicate_status_field"),
        (index_var, "duplicate_index_field"),
        (count_var, "duplicate_count_field"),
        (keep_flag_var, "keep_flag_field"),
    ]:
        window.sync_var_to_config(var, config, key)
    return {
        "frame": marker_frame,
        "group_var": group_var,
        "status_var": status_var,
        "index_var": index_var,
        "count_var": count_var,
        "keep_flag_var": keep_flag_var,
    }


def build_dedupe_footer(frame):
    ttk.Label(
        frame,
        text="说明：第一版支持整行、单字段或多字段组合去重；可选择保留首条、末条、非空字段最多，或不删除仅标记。预览完整计划时可先检查重复组和保留结果。",
        foreground="gray",
        wraplength=1100,
    ).grid(row=5, column=0, columnspan=8, sticky=tk.W, padx=4, pady=(6, 0))


def build_dedupe_config(window, config, headers):
    frame = ttk.LabelFrame(window.config_frame, text="去重 / 重复数据处理节点", padding=8)
    frame.pack(fill=tk.BOTH, expand=True, pady=8)
    headers = list(headers)
    build_dedupe_general_section(window, frame, config)
    field_section = build_dedupe_key_fields_section(frame, config, headers)
    build_dedupe_key_field_action_buttons(field_section, config, headers)
    build_dedupe_marker_section(window, frame, config)
    build_dedupe_footer(frame)
