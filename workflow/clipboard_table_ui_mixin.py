# -*- coding: utf-8 -*-
"""Main ClipboardTableApp UI construction helpers."""

import tkinter as tk
from tkinter import ttk


class ClipboardTableUiMixin:
    """Builds the main ClipboardTableApp window."""

    def build_ui(self):
        top_frame = self.build_top_button_bar()
        ttk.Separator(self.root, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=4)
        option_frame = self.build_option_frame()
        self.build_database_options(option_frame)
        self.build_table_options(option_frame)
        self.build_search_options(option_frame)
        self.build_info_label()
        self.build_preview_table()
        self.refresh_table_list()
        return top_frame

    def build_top_button_bar(self):
        top_frame = ttk.Frame(self.root, padding=8)
        top_frame.pack(fill=tk.X)

        buttons = [
            ("读取剪贴板并解析", self.load_clipboard),
            ("清空预览", self.clear_preview),
            ("删除字段名，并用下一行作为字段名", self.delete_header_and_promote_next_row),
            (None, self.toggle_edit_mode),
            ("计划 / 工作流处理", self.open_plan_workflow),
            ("批量替换 / 数据处理", self.open_batch_replace),
            ("数据提取 / 字段生成", self.open_data_extract),
            ("合并列 / 生成新列", self.open_merge_columns),
            ("高级筛选 / 数据匹配", self.open_advanced_filter),
            ("导出为 xlsx", self.export_current_preview_to_xlsx),
            ("保存到 SQLite", self.save_to_sqlite),
            ("删除当前表", self.delete_current_sqlite_table),
        ]
        for text, command in buttons:
            options = {"command": command}
            if text is None:
                options["textvariable"] = self.edit_btn_text
            else:
                options["text"] = text
            ttk.Button(top_frame, **options).pack(side=tk.LEFT, padx=4)

        return top_frame

    def build_option_frame(self):
        # 主界面选项区拆成独立行，避免不同 row 共用同一个 grid 列宽互相影响。
        # 之前搜索按钮通过较大的 padx 放在 option_frame 的 column=1，
        # 会把数据库路径输入框所在列撑宽，导致“选择 / 刷新表名”整体右移。
        option_frame = ttk.Frame(self.root, padding=8)
        option_frame.pack(fill=tk.X)
        return option_frame

    def build_database_options(self, option_frame):
        db_frame = ttk.Frame(option_frame)
        db_frame.pack(fill=tk.X, anchor=tk.W)

        ttk.Label(db_frame, text="数据库：").pack(side=tk.LEFT, padx=(4, 4))
        ttk.Entry(db_frame, textvariable=self.db_path_var, width=80).pack(side=tk.LEFT, padx=(4, 4))
        ttk.Button(db_frame, text="选择", command=self.choose_db).pack(side=tk.LEFT, padx=(4, 4))
        ttk.Button(db_frame, text="刷新表名", command=self.refresh_table_list).pack(side=tk.LEFT, padx=(4, 4))
        return db_frame

    def build_table_options(self, option_frame):
        table_option_frame = ttk.Frame(option_frame)
        table_option_frame.pack(fill=tk.X, anchor=tk.W, pady=(6, 0))

        ttk.Label(table_option_frame, text="表名：").pack(side=tk.LEFT, padx=(4, 4))
        self.table_combo = ttk.Combobox(
            table_option_frame,
            textvariable=self.table_name_var,
            width=32,
            state="normal",
        )
        self.table_combo.pack(side=tk.LEFT, padx=(4, 18))
        self.table_combo.configure(postcommand=self.refresh_table_list)
        self.table_combo.bind("<<ComboboxSelected>>", self.on_table_selected)

        ttk.Checkbutton(
            table_option_frame,
            text="第一行作为字段名",
            variable=self.first_row_header_var,
            command=self.reparse_current_raw,
        ).pack(side=tk.LEFT, padx=(12, 12))

        ttk.Checkbutton(
            table_option_frame,
            text="保存时重建同名表",
            variable=self.recreate_table_var,
        ).pack(side=tk.LEFT, padx=(12, 12))
        return table_option_frame

    def build_search_options(self, option_frame):
        # 搜索按钮保留你指定的 padx=330，但只影响 search_frame 自身，
        # 不再影响上方数据库行和表名行的布局。
        search_frame = ttk.Frame(option_frame)
        search_frame.pack(fill=tk.X, anchor=tk.W, pady=(6, 0))

        ttk.Label(search_frame, text="搜索：").grid(row=0, column=0, sticky=tk.W, padx=(4, 4), pady=4)
        search_entry = ttk.Entry(search_frame, textvariable=self.search_var, width=38)
        search_entry.grid(row=0, column=1, sticky=tk.W, padx=(4, 4), pady=4)
        search_entry.bind("<Return>", lambda e: self.search_main_preview(reset=True))
        ttk.Button(search_frame, text="搜索", command=lambda: self.search_main_preview(reset=True)).grid(
            row=0,
            column=2,
            sticky=tk.W,
            padx=(12, 8),
            pady=4,
        )
        ttk.Button(search_frame, text="上一个", command=self.search_main_prev).grid(
            row=0,
            column=3,
            sticky=tk.W,
            padx=(12, 8),
            pady=4,
        )
        ttk.Button(search_frame, text="下一个", command=self.search_main_next).grid(
            row=0,
            column=4,
            sticky=tk.W,
            padx=(12, 8),
            pady=4,
        )
        return search_frame

    def build_info_label(self):
        self.info_var = tk.StringVar(value="等待读取剪贴板数据。")
        return ttk.Label(self.root, textvariable=self.info_var, padding=8).pack(fill=tk.X)

    def build_preview_table(self):
        table_frame = ttk.Frame(self.root)
        table_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        self.tree = ttk.Treeview(table_frame, show="headings")
        y_scroll = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.tree.yview)
        x_scroll = ttk.Scrollbar(table_frame, orient=tk.HORIZONTAL, command=self.tree.xview)

        self.tree.configure(
            yscrollcommand=y_scroll.set,
            xscrollcommand=x_scroll.set,
        )

        self.tree.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")

        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)
        self.tree.bind("<Double-1>", self.on_tree_double_click)
        return table_frame
