# -*- coding: utf-8 -*-
"""Tkinter UI helpers for filesystem workflow node configurations."""

import os
import sys
import tkinter as tk
from tkinter import ttk, filedialog


BATCH_RENAME_NAME_VALUE_TYPE_VALUES = ["仅文件名", "完整路径"]
BATCH_RENAME_CONFLICT_MODE_VALUES = ["跳过目标已存在", "自动加编号", "覆盖目标（危险）"]


def get_default_app_dir(window):
    if hasattr(window, "app"):
        app_dir = getattr(window.app, "app_dir", None)
        if app_dir:
            return app_dir
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def choose_file_list_directory(window, config, dir_var):
    path = filedialog.askdirectory(
        title="选择要扫描的目录",
        initialdir=dir_var.get() or get_default_app_dir(window),
    )
    if path:
        dir_var.set(path)
        config["directory"] = path


def build_file_list_config(window, config):
    frame = ttk.LabelFrame(window.config_frame, text="获取文件列表节点", padding=8)
    frame.pack(fill=tk.BOTH, expand=True, pady=8)
    ttk.Label(
        frame,
        text="把指定目录中的文件/文件夹读取成表格。后续可用数据提取、批量替换、合并列生成新文件名，再用批量重命名节点执行。",
        foreground="gray",
        wraplength=1050,
    ).grid(row=0, column=0, columnspan=6, sticky=tk.W, padx=4, pady=(0, 6))

    dir_var = tk.StringVar(value=config.get("directory", get_default_app_dir(window)))
    ttk.Label(frame, text="目录：").grid(row=1, column=0, sticky=tk.W, padx=4, pady=4)
    ttk.Entry(frame, textvariable=dir_var, width=78).grid(row=1, column=1, columnspan=3, sticky=tk.W, padx=4, pady=4)
    ttk.Button(
        frame,
        text="选择目录",
        command=lambda: choose_file_list_directory(window, config, dir_var),
    ).grid(row=1, column=4, sticky=tk.W, padx=4, pady=4)
    window.sync_var_to_config(dir_var, config, "directory")

    recursive_var = tk.BooleanVar(value=bool(config.get("recursive", True)))
    include_files_var = tk.BooleanVar(value=bool(config.get("include_files", True)))
    include_dirs_var = tk.BooleanVar(value=bool(config.get("include_dirs", False)))
    include_hidden_var = tk.BooleanVar(value=bool(config.get("include_hidden", False)))
    for index, (text, var, key) in enumerate(
        [
            ("递归包含子目录", recursive_var, "recursive"),
            ("包含文件", include_files_var, "include_files"),
            ("包含文件夹", include_dirs_var, "include_dirs"),
            ("包含隐藏项", include_hidden_var, "include_hidden"),
        ]
    ):
        ttk.Checkbutton(frame, text=text, variable=var).grid(row=2, column=index, sticky=tk.W, padx=4, pady=4)
        window.sync_bool_to_config(var, config, key)

    ext_var = window.add_labeled_entry(frame, "扩展名过滤：", config.get("extensions", ""), 3, 0, 28)
    ttk.Label(frame, text="示例：.pdf;.xlsx;.docx，留空表示不过滤", foreground="gray").grid(
        row=3,
        column=2,
        columnspan=3,
        sticky=tk.W,
        padx=4,
    )
    window.sync_var_to_config(ext_var, config, "extensions")

    contains_var = window.add_labeled_entry(frame, "文件名包含：", config.get("name_contains", ""), 4, 0, 28)
    glob_var = window.add_labeled_entry(frame, "通配符：", config.get("glob_pattern", "*"), 4, 2, 18)
    ttk.Label(frame, text="示例：*.pdf、*报告*，默认 *", foreground="gray").grid(row=4, column=4, sticky=tk.W, padx=4)
    window.sync_var_to_config(contains_var, config, "name_contains")
    window.sync_var_to_config(glob_var, config, "glob_pattern")

    max_var = window.add_labeled_entry(frame, "最大读取数量：", config.get("max_files", "20000"), 5, 0, 12)
    window.sync_var_to_config(max_var, config, "max_files")

    ttk.Label(
        frame,
        text="输出字段包括：文件名、完整路径、所在目录、扩展名、文件大小、修改时间、创建时间、是否文件夹、新文件名、新完整路径、重命名状态。",
        foreground="gray",
        wraplength=1050,
    ).grid(row=6, column=0, columnspan=6, sticky=tk.W, padx=4, pady=6)


def get_batch_rename_default_fields(config, headers):
    headers = list(headers or [])
    path_default = config.get("path_field") if config.get("path_field") in headers else ("完整路径" if "完整路径" in headers else (headers[0] if headers else ""))
    new_default = config.get("new_name_field") if config.get("new_name_field") in headers else ("新文件名" if "新文件名" in headers else (headers[0] if headers else ""))
    return path_default, new_default


def choose_batch_rename_log_path(config, log_path_var):
    path = filedialog.asksaveasfilename(
        title="选择重命名日志",
        defaultextension=".csv",
        filetypes=[("CSV文件", "*.csv"), ("所有文件", "*.*")],
    )
    if path:
        log_path_var.set(path)
        config["log_path"] = path


def build_batch_rename_config(window, config, headers):
    headers = list(headers or [])
    frame = ttk.LabelFrame(window.config_frame, text="批量重命名节点", padding=8)
    frame.pack(fill=tk.BOTH, expand=True, pady=8)
    ttk.Label(
        frame,
        text="根据当前表格中的【完整路径】和【新文件名/新路径】字段生成重命名结果。默认仅预览，不会实际改文件；需要执行时请勾选实际执行。",
        foreground="gray",
        wraplength=1050,
    ).grid(row=0, column=0, columnspan=6, sticky=tk.W, padx=4, pady=(0, 6))

    path_default, new_default = get_batch_rename_default_fields(config, headers)
    path_var = window.add_labeled_combo(frame, "原路径字段：", path_default, headers, 1, 0, 24, readonly=False)
    new_name_var = window.add_labeled_combo(frame, "新名称字段：", new_default, headers, 1, 2, 24, readonly=False)
    window.sync_var_to_config(path_var, config, "path_field")
    window.sync_var_to_config(new_name_var, config, "new_name_field")

    type_var = window.add_labeled_combo(
        frame,
        "新名称类型：",
        config.get("name_value_type", "仅文件名"),
        BATCH_RENAME_NAME_VALUE_TYPE_VALUES,
        2,
        0,
        14,
    )
    conflict_var = window.add_labeled_combo(
        frame,
        "冲突处理：",
        config.get("conflict_mode", "跳过目标已存在"),
        BATCH_RENAME_CONFLICT_MODE_VALUES,
        2,
        2,
        18,
    )
    window.sync_var_to_config(type_var, config, "name_value_type")
    window.sync_var_to_config(conflict_var, config, "conflict_mode")

    new_path_var = window.add_labeled_entry(frame, "输出新路径字段：", config.get("new_path_field", "新完整路径"), 3, 0, 18)
    status_var = window.add_labeled_entry(frame, "输出状态字段：", config.get("status_field", "重命名状态"), 3, 2, 18)
    window.sync_var_to_config(new_path_var, config, "new_path_field")
    window.sync_var_to_config(status_var, config, "status_field")

    auto_ext_var = tk.BooleanVar(value=bool(config.get("auto_append_ext", False)))
    allow_dirs_var = tk.BooleanVar(value=bool(config.get("allow_dirs", False)))
    create_target_dirs_var = tk.BooleanVar(value=bool(config.get("create_target_dirs", False)))
    actual_var = tk.BooleanVar(value=bool(config.get("actual_rename", False)))
    log_var = tk.BooleanVar(value=bool(config.get("write_log", True)))
    for index, (text, var, key) in enumerate(
        [
            ("新名称无扩展名时自动补原扩展名", auto_ext_var, "auto_append_ext"),
            ("允许重命名文件夹", allow_dirs_var, "allow_dirs"),
            ("目标目录不存在时自动创建", create_target_dirs_var, "create_target_dirs"),
            ("实际执行重命名", actual_var, "actual_rename"),
            ("写入CSV日志", log_var, "write_log"),
        ]
    ):
        ttk.Checkbutton(frame, text=text, variable=var).grid(
            row=4 + index // 2,
            column=(index % 2) * 2,
            columnspan=2,
            sticky=tk.W,
            padx=4,
            pady=4,
        )
        window.sync_bool_to_config(var, config, key)

    log_path_var = tk.StringVar(value=config.get("log_path", os.path.abspath("rename_log.csv")))
    ttk.Label(frame, text="日志路径：").grid(row=7, column=0, sticky=tk.W, padx=4, pady=4)
    ttk.Entry(frame, textvariable=log_path_var, width=70).grid(row=7, column=1, columnspan=3, sticky=tk.W, padx=4, pady=4)
    ttk.Button(
        frame,
        text="选择",
        command=lambda: choose_batch_rename_log_path(config, log_path_var),
    ).grid(row=7, column=4, sticky=tk.W, padx=4, pady=4)
    window.sync_var_to_config(log_path_var, config, "log_path")

    ttk.Label(
        frame,
        text="推荐流程：获取文件列表 → 数据提取/替换/合并列生成【新文件名】 → 批量重命名预览 → 确认无误后勾选实际执行。完整路径目标目录不存在时，可勾选自动创建目录。",
        foreground="gray",
        wraplength=1050,
    ).grid(row=8, column=0, columnspan=6, sticky=tk.W, padx=4, pady=6)
