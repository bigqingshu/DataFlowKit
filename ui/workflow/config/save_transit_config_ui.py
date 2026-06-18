# -*- coding: utf-8 -*-
"""Tkinter UI helpers for the save-transit workflow node configuration."""

import os
import sys
import tkinter as tk
from tkinter import ttk, filedialog


SQLITE_MODE_VALUES = ["覆盖同名表", "自动加时间戳", "追加写入", "报错停止"]


def get_default_export_dir(window):
    if hasattr(window, "app"):
        app_dir = getattr(window.app, "app_dir", None)
        if app_dir:
            return os.path.join(app_dir, "export")
    if getattr(sys, "frozen", False):
        return os.path.join(os.path.dirname(os.path.abspath(sys.executable)), "export")
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "export")


def get_default_xlsx_path(window):
    return os.path.join(get_default_export_dir(window), "中转数据.xlsx")


def build_save_transit_header(frame):
    ttk.Label(
        frame,
        text="把当前工作流执行到这里的数据保存一份。默认保存为内存副表，后续高级筛选节点可把它作为副表引用；也可以在正式执行时保存到 SQLite 或导出 xlsx。",
        foreground="gray",
        wraplength=1050,
    ).grid(row=0, column=0, columnspan=6, sticky=tk.W, padx=4, pady=(0, 6))


def build_save_transit_basic_section(window, frame, config):
    name_var = window.add_labeled_entry(frame, "中转名称：", config.get("transit_name", "中转数据"), 1, 0, 28)
    window.sync_var_to_config(name_var, config, "transit_name")

    save_memory_var = tk.BooleanVar(value=bool(config.get("save_memory", True)))
    append_memory_var = tk.BooleanVar(value=bool(config.get("append_memory", False)))
    save_sqlite_var = tk.BooleanVar(value=bool(config.get("save_sqlite", False)))
    save_xlsx_var = tk.BooleanVar(value=bool(config.get("save_xlsx", False)))
    stop_var = tk.BooleanVar(value=bool(config.get("stop_after_save", False)))

    ttk.Checkbutton(frame, text="保存为内存副表（供后续高级筛选引用）", variable=save_memory_var).grid(
        row=2,
        column=0,
        columnspan=3,
        sticky=tk.W,
        padx=4,
        pady=4,
    )
    ttk.Checkbutton(frame, text="同名内存副表已有数据时追加写入（循环汇总用）", variable=append_memory_var).grid(
        row=2,
        column=3,
        columnspan=3,
        sticky=tk.W,
        padx=4,
        pady=4,
    )
    ttk.Checkbutton(frame, text="正式执行时保存到 SQLite 表", variable=save_sqlite_var).grid(
        row=3,
        column=0,
        columnspan=3,
        sticky=tk.W,
        padx=4,
        pady=4,
    )
    ttk.Checkbutton(frame, text="正式执行时导出为 xlsx", variable=save_xlsx_var).grid(
        row=3,
        column=3,
        columnspan=3,
        sticky=tk.W,
        padx=4,
        pady=4,
    )
    ttk.Checkbutton(frame, text="保存后停止工作流", variable=stop_var).grid(
        row=4,
        column=0,
        columnspan=3,
        sticky=tk.W,
        padx=4,
        pady=4,
    )

    window.sync_bool_to_config(save_memory_var, config, "save_memory")
    window.sync_bool_to_config(append_memory_var, config, "append_memory")
    window.sync_bool_to_config(save_sqlite_var, config, "save_sqlite")
    window.sync_bool_to_config(save_xlsx_var, config, "save_xlsx")
    window.sync_bool_to_config(stop_var, config, "stop_after_save")
    return {
        "name_var": name_var,
        "save_memory_var": save_memory_var,
        "append_memory_var": append_memory_var,
        "save_sqlite_var": save_sqlite_var,
        "save_xlsx_var": save_xlsx_var,
        "stop_var": stop_var,
    }


def build_save_transit_sqlite_section(window, frame, config):
    sqlite_frame = ttk.LabelFrame(frame, text="SQLite 保存设置", padding=6)
    sqlite_frame.grid(row=5, column=0, columnspan=6, sticky="ew", padx=4, pady=6)
    table_var = window.add_labeled_entry(
        sqlite_frame,
        "SQLite表名：",
        config.get("sqlite_table", config.get("transit_name", "中转数据")),
        0,
        0,
        28,
    )
    mode_var = window.add_labeled_combo(
        sqlite_frame,
        "同名处理：",
        config.get("sqlite_mode", "自动加时间戳"),
        SQLITE_MODE_VALUES,
        0,
        2,
        16,
    )
    window.sync_var_to_config(table_var, config, "sqlite_table")
    window.sync_var_to_config(mode_var, config, "sqlite_mode")
    return {
        "frame": sqlite_frame,
        "table_var": table_var,
        "mode_var": mode_var,
    }


def choose_save_transit_xlsx_path(window, config, path_var):
    initial_dir = os.path.dirname(path_var.get()) if path_var.get() else get_default_export_dir(window)
    os.makedirs(initial_dir, exist_ok=True)
    path = filedialog.asksaveasfilename(
        title="选择中转数据 xlsx 导出路径",
        initialdir=initial_dir,
        initialfile=os.path.basename(path_var.get()) or "中转数据.xlsx",
        defaultextension=".xlsx",
        filetypes=[("Excel 工作簿", "*.xlsx"), ("所有文件", "*.*")],
    )
    if path:
        path_var.set(path)
        config["xlsx_path"] = path


def build_save_transit_xlsx_section(window, frame, config):
    xlsx_frame = ttk.LabelFrame(frame, text="xlsx 导出设置", padding=6)
    xlsx_frame.grid(row=6, column=0, columnspan=6, sticky="ew", padx=4, pady=6)
    path_var = tk.StringVar(value=config.get("xlsx_path", get_default_xlsx_path(window)))
    ttk.Label(xlsx_frame, text="xlsx路径：").grid(row=0, column=0, sticky=tk.W, padx=4, pady=4)
    ttk.Entry(xlsx_frame, textvariable=path_var, width=72).grid(row=0, column=1, columnspan=3, sticky=tk.W, padx=4, pady=4)
    ttk.Button(
        xlsx_frame,
        text="选择",
        command=lambda: choose_save_transit_xlsx_path(window, config, path_var),
    ).grid(row=0, column=4, sticky=tk.W, padx=4, pady=4)
    window.sync_var_to_config(path_var, config, "xlsx_path")
    return {
        "frame": xlsx_frame,
        "path_var": path_var,
    }


def build_save_transit_footer(frame):
    ttk.Label(
        frame,
        text="说明：预览计划时只会保存内存副表，不会写 SQLite/xlsx；点击【执行计划】时才会执行外部保存。该节点默认不改变当前数据，继续向后传递。",
        foreground="gray",
        wraplength=1050,
    ).grid(row=7, column=0, columnspan=6, sticky=tk.W, padx=4, pady=(8, 4))


def build_save_transit_config(window, config, headers):
    """Build the save-transit node configuration UI."""
    frame = ttk.LabelFrame(window.config_frame, text="保存中转数据节点", padding=8)
    frame.pack(fill=tk.BOTH, expand=True, pady=8)
    build_save_transit_header(frame)
    build_save_transit_basic_section(window, frame, config)
    build_save_transit_sqlite_section(window, frame, config)
    build_save_transit_xlsx_section(window, frame, config)
    build_save_transit_footer(frame)
