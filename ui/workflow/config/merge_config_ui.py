# -*- coding: utf-8 -*-
"""Tkinter UI helpers for the merge-columns workflow node configuration."""

import tkinter as tk
from tkinter import ttk

from workflow.nodes.data_nodes import parse_separator_text as parse_merge_separator_text


def ensure_separator_count(config):
    fields = config.get("fields", [])
    need = max(len(fields) - 1, 0)
    separators = list(config.get("separators", []))
    if len(separators) < need:
        separators += ["-"] * (need - len(separators))
    if len(separators) > need:
        separators = separators[:need]
    config["separators"] = separators


def separator_to_input_text(text):
    value = "" if text is None else str(text)
    value = value.replace("\r\n", "{Windows换行}")
    value = value.replace("\n", "{换行符}")
    value = value.replace("\t", "{制表符}")
    return value


def sep_value_to_display(separator, separator_options):
    mapping = {"": "空字符", " ": "空格", "\n": "换行", "\r\n": "Windows换行", "\t": "制表符"}
    return mapping.get(separator, separator if separator in separator_options else "自定义")


def display_to_sep_value(display, custom):
    if display == "空字符":
        return ""
    if display == "空格":
        return " "
    if display == "换行":
        return "\n"
    if display == "Windows换行":
        return "\r\n"
    if display == "制表符":
        return "\t"
    if display == "自定义":
        return parse_merge_separator_text(custom)
    return display


def preview_plan_separator(window, left_name, right_name, combo_var, custom_var):
    display = combo_var.get()
    raw_text = custom_var.get() if display == "自定义" else display
    separator = display_to_sep_value(display, custom_var.get())

    preview_win = tk.Toplevel(window.window)
    preview_win.title("连接符效果预览")
    preview_win.geometry("520x360")
    preview_win.transient(window.window)

    frame = ttk.Frame(preview_win, padding=10)
    frame.pack(fill=tk.BOTH, expand=True)
    ttk.Label(frame, text=f"模拟列数据：{left_name}=A，{right_name}=B").pack(anchor=tk.W, pady=(0, 6))
    ttk.Label(frame, text="用户输入：").pack(anchor=tk.W)
    raw_box = tk.Text(frame, height=4, wrap=tk.WORD)
    raw_box.pack(fill=tk.X, pady=4)
    raw_box.insert("1.0", raw_text)
    raw_box.configure(state="disabled")
    ttk.Label(frame, text="实际合并效果：").pack(anchor=tk.W, pady=(8, 0))
    effect_box = tk.Text(frame, height=7, wrap=tk.WORD)
    effect_box.pack(fill=tk.BOTH, expand=True, pady=4)
    effect_box.insert("1.0", "A" + separator + "B")
    effect_box.configure(state="disabled")
    ttk.Label(frame, text="支持：{换行符}、{制表符}、{空格}、{空字符}，也兼容 \\n、\\t。", foreground="gray").pack(
        anchor=tk.W,
        pady=(4, 0),
    )
    ttk.Button(frame, text="关闭", command=preview_win.destroy).pack(anchor=tk.E, pady=(8, 0))


def refresh_merge_separator_ui(window, parent, config):
    for child in parent.winfo_children():
        child.destroy()
    fields = config.get("fields", [])
    separators = config.get("separators", [])
    ttk.Label(
        parent,
        text="提示：自定义连接符支持 {换行符}、{制表符}、{空格}、{空字符}，也兼容 \\n、\\t，可组合普通文字，如 {换行符}客码:",
        foreground="gray",
        wraplength=1050,
    ).pack(anchor=tk.W, pady=(0, 4))
    if len(fields) < 2:
        ttk.Label(parent, text="至少选择两列后才需要设置连接符。", foreground="gray").pack(anchor=tk.W)
        return
    for index in range(len(fields) - 1):
        row = ttk.Frame(parent)
        row.pack(fill=tk.X, pady=2)
        ttk.Label(row, text=f"{fields[index]} 和 {fields[index + 1]} 之间：", width=34).pack(side=tk.LEFT)
        current = separators[index] if index < len(separators) else "-"
        display_value = sep_value_to_display(current, window.SEPARATOR_OPTIONS)
        combo_var = tk.StringVar(value=display_value)
        custom_var = tk.StringVar(value=separator_to_input_text(current) if display_value == "自定义" else "")
        combo = ttk.Combobox(row, textvariable=combo_var, values=window.SEPARATOR_OPTIONS, width=12, state="readonly")
        combo.pack(side=tk.LEFT, padx=4)
        ttk.Label(row, text="自定义：").pack(side=tk.LEFT)
        entry = ttk.Entry(row, textvariable=custom_var, width=24)
        entry.pack(side=tk.LEFT, padx=4)
        ttk.Button(
            row,
            text="预览",
            command=lambda l=fields[index], r=fields[index + 1], cv=combo_var, uv=custom_var: preview_plan_separator(
                window,
                l,
                r,
                cv,
                uv,
            ),
        ).pack(side=tk.LEFT, padx=4)

        def update_sep(*_, idx=index, cv=combo_var, uv=custom_var):
            config["separators"][idx] = display_to_sep_value(cv.get(), uv.get())

        combo_var.trace_add("write", update_sep)
        custom_var.trace_add("write", update_sep)


def build_merge_config(window, config, headers):
    frame = ttk.LabelFrame(window.config_frame, text="合并列节点", padding=8)
    frame.pack(fill=tk.BOTH, expand=True, pady=8)

    top = ttk.Frame(frame)
    top.pack(fill=tk.X)
    out_var = window.add_labeled_entry(top, "新字段名：", config.get("output_field", "合并结果"), 0, 0, 24)
    skip_var = tk.BooleanVar(value=config.get("skip_empty", True))
    trim_var = tk.BooleanVar(value=config.get("trim_value", True))
    ttk.Checkbutton(top, text="跳过空值", variable=skip_var).grid(row=0, column=2, sticky=tk.W, padx=4, pady=4)
    ttk.Checkbutton(top, text="去除首尾空格", variable=trim_var).grid(row=0, column=3, sticky=tk.W, padx=4, pady=4)
    placeholder_var = window.add_labeled_entry(top, "空值占位符：", config.get("empty_placeholder", ""), 0, 4, 12)
    for var, key in [(out_var, "output_field"), (placeholder_var, "empty_placeholder")]:
        window.sync_var_to_config(var, config, key)
    window.sync_bool_to_config(skip_var, config, "skip_empty")
    window.sync_bool_to_config(trim_var, config, "trim_value")

    body = ttk.Frame(frame)
    body.pack(fill=tk.BOTH, expand=True, pady=6)
    left = ttk.LabelFrame(body, text="可选字段", padding=6)
    left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 6))
    right = ttk.LabelFrame(body, text="合并顺序", padding=6)
    right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    available_wrap = ttk.Frame(left)
    available_wrap.pack(fill=tk.BOTH, expand=True)
    available_list = tk.Listbox(available_wrap, height=10, exportselection=False)
    available_scroll = ttk.Scrollbar(available_wrap, orient=tk.VERTICAL, command=available_list.yview)
    available_list.configure(yscrollcommand=available_scroll.set)
    available_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    available_scroll.pack(side=tk.RIGHT, fill=tk.Y)
    for header in headers:
        available_list.insert(tk.END, header)

    order_wrap = ttk.Frame(right)
    order_wrap.pack(fill=tk.BOTH, expand=True)
    order_list = tk.Listbox(order_wrap, height=10, exportselection=False)
    order_scroll = ttk.Scrollbar(order_wrap, orient=tk.VERTICAL, command=order_list.yview)
    order_list.configure(yscrollcommand=order_scroll.set)
    order_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    order_scroll.pack(side=tk.RIGHT, fill=tk.Y)
    for field in config.get("fields", []):
        order_list.insert(tk.END, field)
    window.field_listbox = order_list

    btns = ttk.Frame(body)
    btns.pack(side=tk.LEFT, fill=tk.Y, padx=6)
    sep_frame = ttk.LabelFrame(frame, text="每两列之间的连接符", padding=6)
    sep_frame.pack(fill=tk.X)

    def sync_fields():
        config["fields"] = list(order_list.get(0, tk.END))
        ensure_separator_count(config)
        refresh_merge_separator_ui(window, sep_frame, config)

    def add_field():
        selected = available_list.curselection()
        if not selected:
            return
        order_list.insert(tk.END, available_list.get(selected[0]))
        sync_fields()

    def remove_field():
        selected = order_list.curselection()
        if not selected:
            return
        order_list.delete(selected[0])
        sync_fields()

    def move_up():
        selected = order_list.curselection()
        if not selected or selected[0] <= 0:
            return
        index = selected[0]
        value = order_list.get(index)
        order_list.delete(index)
        order_list.insert(index - 1, value)
        order_list.selection_set(index - 1)
        sync_fields()

    def move_down():
        selected = order_list.curselection()
        if not selected or selected[0] >= order_list.size() - 1:
            return
        index = selected[0]
        value = order_list.get(index)
        order_list.delete(index)
        order_list.insert(index + 1, value)
        order_list.selection_set(index + 1)
        sync_fields()

    def clear_fields():
        order_list.delete(0, tk.END)
        sync_fields()

    for text, command in [("添加 →", add_field), ("删除", remove_field), ("上移", move_up), ("下移", move_down), ("清空", clear_fields)]:
        ttk.Button(btns, text=text, command=command).pack(fill=tk.X, pady=2)

    ensure_separator_count(config)
    refresh_merge_separator_ui(window, sep_frame, config)
