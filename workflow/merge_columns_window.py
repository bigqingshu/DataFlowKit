# -*- coding: utf-8 -*-
"""Merge columns / generated column window."""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from shared.atomic_json_utils import atomic_write_json, load_json_with_backup


def load_json_file_with_recovery(path, parent=None):
    data, info = load_json_with_backup(path)
    warning = info.get("warning", "")
    if warning:
        messagebox.showwarning("配置已从备份恢复", warning, parent=parent)
    return data


class MergeColumnsWindow:
    """
    合并列 / 生成新列窗口。

    作用：
    - 从当前主界面预览数据中选择多个字段；
    - 通过“合并顺序列表”明确字段拼接顺序；
    - 支持每两列之间设置不同连接符，也支持自定义连接符；
    - 生成一个新的字段列；
    - 支持预览、执行、撤销、保存/载入模板。
    """

    SEPARATOR_OPTIONS = [
        "空字符", "空格", "换行", "Windows换行", "制表符",
        "-", "_", "/", "\\", "|", ",", ";", ":", ".", "+", "自定义"
    ]

    SEPARATOR_MAP = {
        "空字符": "",
        "空格": " ",
        "换行": "\n",
        "Windows换行": "\r\n",
        "制表符": "\t",
        "-": "-",
        "_": "_",
        "/": "/",
        "\\": "\\",
        "|": "|",
        ",": ",",
        ";": ";",
        ":": ":",
        ".": ".",
        "+": "+",
    }

    def __init__(self, app):
        self.app = app
        self.last_snapshot = None
        self.separator_rows = []

        self.window = tk.Toplevel(app.root)
        self.window.title("合并列 / 生成新列")
        self.window.geometry("1120x760")
        self.window.transient(app.root)

        self.new_field_var = tk.StringVar(value="合并结果")
        self.default_separator_var = tk.StringVar(value="空字符")
        self.default_separator_custom_var = tk.StringVar(value="")
        self.skip_empty_var = tk.BooleanVar(value=False)
        self.trim_value_var = tk.BooleanVar(value=False)
        self.empty_placeholder_var = tk.StringVar(value="")
        self.preview_limit_var = tk.IntVar(value=500)
        self.status_var = tk.StringVar(value="请从左侧字段池添加字段到右侧合并顺序列表。")

        self.build_ui()

    def build_ui(self):
        main = ttk.Frame(self.window, padding=10)
        main.pack(fill=tk.BOTH, expand=True)

        source_frame = ttk.LabelFrame(main, text="1. 字段选择与合并顺序", padding=8)
        source_frame.pack(fill=tk.X)

        # 左侧：全部字段池
        left = ttk.Frame(source_frame)
        left.grid(row=0, column=0, sticky="nsw", padx=(0, 8))

        ttk.Label(left, text="可选字段：").pack(anchor=tk.W)

        available_frame = ttk.Frame(left)
        available_frame.pack(fill=tk.Y, pady=4)

        self.available_listbox = tk.Listbox(
            available_frame,
            selectmode=tk.EXTENDED,
            height=12,
            width=32,
            exportselection=False
        )
        available_scroll = ttk.Scrollbar(available_frame, orient=tk.VERTICAL, command=self.available_listbox.yview)
        self.available_listbox.configure(yscrollcommand=available_scroll.set)
        self.available_listbox.pack(side=tk.LEFT, fill=tk.Y)
        available_scroll.pack(side=tk.LEFT, fill=tk.Y)

        self.refresh_available_fields()
        self.available_listbox.bind("<Double-1>", lambda event: self.add_selected_fields())

        left_btns = ttk.Frame(left)
        left_btns.pack(fill=tk.X, pady=4)
        ttk.Button(left_btns, text="全选", command=lambda: self.available_listbox.select_set(0, tk.END)).pack(side=tk.LEFT, padx=2)
        ttk.Button(left_btns, text="清空选择", command=lambda: self.available_listbox.selection_clear(0, tk.END)).pack(side=tk.LEFT, padx=2)

        # 中间：添加/删除按钮
        middle = ttk.Frame(source_frame)
        middle.grid(row=0, column=1, sticky="n", padx=8, pady=28)

        ttk.Button(middle, text="添加 →", command=self.add_selected_fields).pack(fill=tk.X, pady=3)
        ttk.Button(middle, text="← 删除", command=self.remove_order_fields).pack(fill=tk.X, pady=3)
        ttk.Separator(middle, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=6)
        ttk.Button(middle, text="上移", command=self.move_order_up).pack(fill=tk.X, pady=3)
        ttk.Button(middle, text="下移", command=self.move_order_down).pack(fill=tk.X, pady=3)
        ttk.Button(middle, text="清空", command=self.clear_order_fields).pack(fill=tk.X, pady=3)

        # 右侧：合并顺序列表
        right = ttk.Frame(source_frame)
        right.grid(row=0, column=2, sticky="nsw", padx=(8, 16))

        ttk.Label(right, text="合并顺序：").pack(anchor=tk.W)

        order_frame = ttk.Frame(right)
        order_frame.pack(fill=tk.Y, pady=4)

        self.order_listbox = tk.Listbox(
            order_frame,
            selectmode=tk.EXTENDED,
            height=12,
            width=34,
            exportselection=False
        )
        order_scroll = ttk.Scrollbar(order_frame, orient=tk.VERTICAL, command=self.order_listbox.yview)
        self.order_listbox.configure(yscrollcommand=order_scroll.set)
        self.order_listbox.pack(side=tk.LEFT, fill=tk.Y)
        order_scroll.pack(side=tk.LEFT, fill=tk.Y)
        self.order_listbox.bind("<Delete>", lambda event: self.remove_order_fields())

        # 右侧设置区
        setting = ttk.Frame(source_frame)
        setting.grid(row=0, column=3, sticky="nsew", padx=(8, 0))
        source_frame.columnconfigure(3, weight=1)

        row = 0
        ttk.Label(setting, text="新字段名：").grid(row=row, column=0, sticky=tk.W, padx=4, pady=4)
        ttk.Entry(setting, textvariable=self.new_field_var, width=32).grid(row=row, column=1, sticky=tk.W, padx=4, pady=4)

        row += 1
        ttk.Checkbutton(
            setting,
            text="合并前去除每个字段首尾空格",
            variable=self.trim_value_var
        ).grid(row=row, column=0, columnspan=3, sticky=tk.W, padx=4, pady=4)

        row += 1
        ttk.Checkbutton(
            setting,
            text="跳过空值字段，不参与拼接",
            variable=self.skip_empty_var
        ).grid(row=row, column=0, columnspan=3, sticky=tk.W, padx=4, pady=4)

        row += 1
        ttk.Label(setting, text="空值占位符：").grid(row=row, column=0, sticky=tk.W, padx=4, pady=4)
        ttk.Entry(setting, textvariable=self.empty_placeholder_var, width=32).grid(row=row, column=1, sticky=tk.W, padx=4, pady=4)
        ttk.Label(setting, text="不跳过空值时可用，例如填 NA").grid(row=row, column=2, sticky=tk.W, padx=4, pady=4)

        row += 1
        ttk.Label(setting, text="预览最大行数：").grid(row=row, column=0, sticky=tk.W, padx=4, pady=4)
        ttk.Spinbox(setting, from_=10, to=100000, textvariable=self.preview_limit_var, width=12).grid(row=row, column=1, sticky=tk.W, padx=4, pady=4)

        # 列间隔符设置区
        sep_frame = ttk.LabelFrame(main, text="2. 列间隔符设置：每两列之间可使用不同连接符", padding=8)
        sep_frame.pack(fill=tk.X, pady=8)

        sep_top = ttk.Frame(sep_frame)
        sep_top.pack(fill=tk.X)

        ttk.Label(sep_top, text="批量设为：").pack(side=tk.LEFT, padx=4)
        self.default_separator_combo = ttk.Combobox(
            sep_top,
            textvariable=self.default_separator_var,
            values=self.SEPARATOR_OPTIONS,
            width=12,
            state="readonly"
        )
        self.default_separator_combo.pack(side=tk.LEFT, padx=4)
        self.default_separator_combo.bind("<<ComboboxSelected>>", lambda event: self.update_default_custom_state())

        self.default_separator_custom_entry = ttk.Entry(sep_top, textvariable=self.default_separator_custom_var, width=16)
        self.default_separator_custom_entry.pack(side=tk.LEFT, padx=4)
        ttk.Button(sep_top, text="应用到全部间隔符", command=self.apply_default_separator_to_all).pack(side=tk.LEFT, padx=4)
        ttk.Label(sep_top, text="常用：空字符、空格、换行、制表符、-、_，也可选择“自定义”。").pack(side=tk.LEFT, padx=8)
        ttk.Label(
            sep_frame,
            text="提示：自定义连接符支持 {换行符}、{制表符}、{空格}、{空字符}，也兼容 \\n、\\t，可组合普通文字，如 {换行符}客码:",
            foreground="gray",
            wraplength=1060
        ).pack(anchor=tk.W, padx=4, pady=(6, 0))
        self.update_default_custom_state()

        sep_body = ttk.Frame(sep_frame)
        sep_body.pack(fill=tk.X, pady=6)

        self.sep_canvas = tk.Canvas(sep_body, height=150, highlightthickness=0)
        sep_scroll = ttk.Scrollbar(sep_body, orient=tk.VERTICAL, command=self.sep_canvas.yview)
        self.sep_canvas.configure(yscrollcommand=sep_scroll.set)
        self.sep_canvas.pack(side=tk.LEFT, fill=tk.X, expand=True)
        sep_scroll.pack(side=tk.LEFT, fill=tk.Y)

        self.sep_inner = ttk.Frame(self.sep_canvas)
        self.sep_window_id = self.sep_canvas.create_window((0, 0), window=self.sep_inner, anchor="nw")
        self.sep_inner.bind("<Configure>", self.on_separator_inner_configure)
        self.sep_canvas.bind("<Configure>", self.on_separator_canvas_configure)

        # 操作区
        action = ttk.LabelFrame(main, text="3. 操作", padding=8)
        action.pack(fill=tk.X, pady=8)

        ttk.Button(action, text="预览合并结果", command=self.preview_merge).pack(side=tk.LEFT, padx=4)
        ttk.Button(action, text="执行合并到新列", command=self.apply_merge).pack(side=tk.LEFT, padx=4)
        ttk.Button(action, text="撤销上一次合并", command=self.undo_merge).pack(side=tk.LEFT, padx=4)
        ttk.Separator(action, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8)
        ttk.Button(action, text="保存合并模板", command=self.save_template).pack(side=tk.LEFT, padx=4)
        ttk.Button(action, text="载入合并模板", command=self.load_template).pack(side=tk.LEFT, padx=4)
        ttk.Button(action, text="关闭", command=self.window.destroy).pack(side=tk.RIGHT, padx=4)

        ttk.Label(main, textvariable=self.status_var).pack(fill=tk.X, pady=4)

        preview_frame = ttk.LabelFrame(main, text="4. 合并结果预览", padding=8)
        preview_frame.pack(fill=tk.BOTH, expand=True)

        self.preview_tree = ttk.Treeview(preview_frame, show="headings")
        y_scroll = ttk.Scrollbar(preview_frame, orient=tk.VERTICAL, command=self.preview_tree.yview)
        x_scroll = ttk.Scrollbar(preview_frame, orient=tk.HORIZONTAL, command=self.preview_tree.xview)
        self.preview_tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)
        self.preview_tree.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")
        preview_frame.rowconfigure(0, weight=1)
        preview_frame.columnconfigure(0, weight=1)

        self.rebuild_separator_ui()

    def on_separator_inner_configure(self, event=None):
        self.sep_canvas.configure(scrollregion=self.sep_canvas.bbox("all"))

    def on_separator_canvas_configure(self, event=None):
        if event:
            self.sep_canvas.itemconfigure(self.sep_window_id, width=event.width)

    def refresh_available_fields(self):
        if not hasattr(self, "available_listbox"):
            return
        self.available_listbox.delete(0, tk.END)
        for header in self.app.headers:
            self.available_listbox.insert(tk.END, header)

    def add_selected_fields(self):
        selections = list(self.available_listbox.curselection())
        if not selections:
            messagebox.showinfo("提示", "请先在左侧可选字段中选择字段。")
            return

        existing = set(self.get_order_headers())
        added = 0
        for index in selections:
            header = self.app.headers[index]
            if header in existing:
                continue
            self.order_listbox.insert(tk.END, header)
            existing.add(header)
            added += 1

        if added == 0:
            self.status_var.set("所选字段已经在合并顺序列表中。")
        else:
            self.status_var.set(f"已添加 {added} 个字段到合并顺序列表。")

        self.rebuild_separator_ui()

    def remove_order_fields(self):
        selections = list(self.order_listbox.curselection())
        if not selections:
            return
        for index in reversed(selections):
            self.order_listbox.delete(index)
        self.rebuild_separator_ui()
        self.status_var.set("已从合并顺序中删除选中字段。")

    def clear_order_fields(self):
        self.order_listbox.delete(0, tk.END)
        self.rebuild_separator_ui()
        self.status_var.set("已清空合并顺序。")

    def move_order_up(self):
        selections = list(self.order_listbox.curselection())
        if not selections:
            return

        for index in selections:
            if index <= 0:
                continue
            value = self.order_listbox.get(index)
            self.order_listbox.delete(index)
            self.order_listbox.insert(index - 1, value)

        self.order_listbox.selection_clear(0, tk.END)
        for index in selections:
            self.order_listbox.selection_set(max(0, index - 1))

        self.rebuild_separator_ui()

    def move_order_down(self):
        selections = list(self.order_listbox.curselection())
        if not selections:
            return

        size = self.order_listbox.size()
        for index in reversed(selections):
            if index >= size - 1:
                continue
            value = self.order_listbox.get(index)
            self.order_listbox.delete(index)
            self.order_listbox.insert(index + 1, value)

        self.order_listbox.selection_clear(0, tk.END)
        for index in selections:
            self.order_listbox.selection_set(min(size - 1, index + 1))

        self.rebuild_separator_ui()

    def get_order_headers(self):
        return [self.order_listbox.get(i) for i in range(self.order_listbox.size())]

    def get_order_indices(self):
        indices = []
        missing = []
        for header in self.get_order_headers():
            try:
                indices.append(self.app.headers.index(header))
            except ValueError:
                missing.append(header)
        if missing:
            raise ValueError("以下字段在当前表格中不存在：" + ", ".join(missing))
        return indices

    def parse_separator_text(self, text):
        """把用户可读的特殊分隔符写法转换成真实字符。"""
        value = "" if text is None else str(text)
        replacements = [
            ("{Windows换行}", "\r\n"),
            ("{windows换行}", "\r\n"),
            ("{换行符}", "\n"),
            ("{换行}", "\n"),
            ("{newline}", "\n"),
            ("{NEWLINE}", "\n"),
            ("{制表符}", "\t"),
            ("{tab}", "\t"),
            ("{TAB}", "\t"),
            ("{空格}", " "),
            ("{space}", " "),
            ("{SPACE}", " "),
            ("{空字符}", ""),
            ("{empty}", ""),
            ("{EMPTY}", ""),
        ]
        for key, real in replacements:
            value = value.replace(key, real)
        # 兼容高级用户直接输入的转义写法。
        value = value.replace("\\r\\n", "\r\n")
        value = value.replace("\\n", "\n")
        value = value.replace("\\t", "\t")
        return value

    def separator_to_input_text(self, text):
        """把真实换行/制表符转换成输入框里更容易识别的占位符。"""
        value = "" if text is None else str(text)
        value = value.replace("\r\n", "{Windows换行}")
        value = value.replace("\n", "{换行符}")
        value = value.replace("\t", "{制表符}")
        return value

    def display_to_separator(self, option, custom_value=""):
        if option == "自定义":
            return self.parse_separator_text(custom_value)
        return self.SEPARATOR_MAP.get(option, "")

    def separator_to_display(self, sep):
        for display, value in self.SEPARATOR_MAP.items():
            if value == sep:
                return display, ""
        return "自定义", self.separator_to_input_text(sep)

    def get_separator_raw_text(self, index):
        if index < 0 or index >= len(self.separator_rows):
            return ""
        item = self.separator_rows[index]
        option = item["option_var"].get()
        if option == "自定义":
            return item["custom_var"].get()
        return option

    def preview_separator_pair(self, index, left_name, right_name):
        raw_text = self.get_separator_raw_text(index)
        sep = self.get_current_separators()[index] if index < len(self.get_current_separators()) else ""

        win = tk.Toplevel(self.window)
        win.title("连接符效果预览")
        win.geometry("520x360")
        win.transient(self.window)

        frame = ttk.Frame(win, padding=10)
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
        effect_box.insert("1.0", "A" + sep + "B")
        effect_box.configure(state="disabled")

        ttk.Label(frame, text="支持：{换行符}、{制表符}、{空格}、{空字符}，也兼容 \\n、\\t。", foreground="gray").pack(anchor=tk.W, pady=(4, 0))
        ttk.Button(frame, text="关闭", command=win.destroy).pack(anchor=tk.E, pady=(8, 0))

    def get_current_separators(self):
        result = []
        for item in self.separator_rows:
            option = item["option_var"].get()
            custom = item["custom_var"].get()
            result.append(self.display_to_separator(option, custom))
        return result

    def update_default_custom_state(self):
        if not hasattr(self, "default_separator_custom_entry"):
            return
        if self.default_separator_var.get() == "自定义":
            self.default_separator_custom_entry.configure(state="normal")
        else:
            self.default_separator_custom_entry.configure(state="disabled")

    def update_custom_entry_state(self, index):
        if index < 0 or index >= len(self.separator_rows):
            return
        item = self.separator_rows[index]
        if item["option_var"].get() == "自定义":
            item["custom_entry"].configure(state="normal")
        else:
            item["custom_entry"].configure(state="disabled")

    def apply_default_separator_to_all(self):
        option = self.default_separator_var.get()
        custom = self.default_separator_custom_var.get()
        for i, item in enumerate(self.separator_rows):
            item["option_var"].set(option)
            item["custom_var"].set(custom)
            self.update_custom_entry_state(i)
        self.status_var.set("已将批量连接符应用到全部列间隔符。")

    def rebuild_separator_ui(self):
        old_separators = self.get_current_separators() if self.separator_rows else []
        headers = self.get_order_headers() if hasattr(self, "order_listbox") else []

        for child in self.sep_inner.winfo_children():
            child.destroy()
        self.separator_rows = []

        if len(headers) < 2:
            ttk.Label(
                self.sep_inner,
                text="合并顺序少于 2 个字段时，不需要设置列间隔符。"
            ).grid(row=0, column=0, sticky=tk.W, padx=4, pady=6)
            self.sep_canvas.configure(scrollregion=self.sep_canvas.bbox("all"))
            return

        for i in range(len(headers) - 1):
            sep_value = old_separators[i] if i < len(old_separators) else self.display_to_separator(
                self.default_separator_var.get(),
                self.default_separator_custom_var.get()
            )
            option, custom = self.separator_to_display(sep_value)

            option_var = tk.StringVar(value=option)
            custom_var = tk.StringVar(value=custom)

            ttk.Label(
                self.sep_inner,
                text=f"{i + 1}. {headers[i]} 和 {headers[i + 1]} 之间："
            ).grid(row=i, column=0, sticky=tk.W, padx=4, pady=3)

            combo = ttk.Combobox(
                self.sep_inner,
                textvariable=option_var,
                values=self.SEPARATOR_OPTIONS,
                width=12,
                state="readonly"
            )
            combo.grid(row=i, column=1, sticky=tk.W, padx=4, pady=3)

            entry = ttk.Entry(self.sep_inner, textvariable=custom_var, width=24)
            entry.grid(row=i, column=2, sticky=tk.W, padx=4, pady=3)

            preview_btn = ttk.Button(
                self.sep_inner,
                text="预览",
                command=lambda idx=i, left=headers[i], right=headers[i + 1]: self.preview_separator_pair(idx, left, right)
            )
            preview_btn.grid(row=i, column=3, sticky=tk.W, padx=4, pady=3)

            self.separator_rows.append({
                "option_var": option_var,
                "custom_var": custom_var,
                "custom_entry": entry,
            })

            combo.bind("<<ComboboxSelected>>", lambda event, idx=i: self.update_custom_entry_state(idx))
            self.update_custom_entry_state(i)

        self.sep_canvas.configure(scrollregion=self.sep_canvas.bbox("all"))

    def make_unique_header(self, base_name):
        base_name = str(base_name or "合并结果").strip() or "合并结果"
        existing = set(self.app.headers)
        if base_name not in existing:
            return base_name

        i = 2
        while f"{base_name}_{i}" in existing:
            i += 1
        return f"{base_name}_{i}"

    def get_cell_value(self, row, index):
        if index < len(row):
            value = row[index]
        else:
            value = ""

        value = "" if value is None else str(value)

        if self.trim_value_var.get():
            value = value.strip()

        return value

    def build_merged_value_and_status(self, row, selected_indices, separators):
        placeholder = self.empty_placeholder_var.get()
        skip_empty = self.skip_empty_var.get()
        values = [self.get_cell_value(row, index) for index in selected_indices]
        empty_count = sum(1 for value in values if value == "")

        if not values:
            return "", "无字段"

        if skip_empty:
            result = ""
            has_value = False
            for i, value in enumerate(values):
                if value == "":
                    continue
                if not has_value:
                    result = value
                    has_value = True
                else:
                    sep = separators[i - 1] if i - 1 < len(separators) else ""
                    result += sep + value
        else:
            parts = []
            for value in values:
                if value == "":
                    value = placeholder
                parts.append(value)

            result = ""
            for i, part in enumerate(parts):
                if i == 0:
                    result = part
                else:
                    sep = separators[i - 1] if i - 1 < len(separators) else ""
                    result += sep + part

        if empty_count == len(values):
            status = "全部为空"
        elif empty_count > 0:
            status = "部分字段为空"
        else:
            status = "成功"

        return result, status

    def build_merged_value(self, row, selected_indices, separators):
        merged, _status = self.build_merged_value_and_status(row, selected_indices, separators)
        return merged

    def collect_preview_rows(self):
        selected_indices = self.get_order_indices()
        if not selected_indices:
            raise ValueError("请先添加需要合并的字段到右侧合并顺序列表。")

        if not self.app.rows:
            raise ValueError("当前没有可合并的数据行。")

        try:
            limit = int(self.preview_limit_var.get())
        except Exception:
            limit = 500
        if limit <= 0:
            limit = 500

        selected_headers = self.get_order_headers()
        separators = self.get_current_separators()
        if len(separators) < max(0, len(selected_indices) - 1):
            separators += [""] * (len(selected_indices) - 1 - len(separators))

        preview_rows = []
        for row_no, row in enumerate(self.app.rows[:limit], start=1):
            source_values = [self.get_cell_value(row, idx) for idx in selected_indices]
            merged, status = self.build_merged_value_and_status(row, selected_indices, separators)
            preview_rows.append([row_no] + source_values + [merged, status])

        return selected_headers, preview_rows

    def preview_merge(self):
        try:
            selected_headers, preview_rows = self.collect_preview_rows()
        except Exception as e:
            messagebox.showwarning("提示", str(e))
            return

        columns = ["行号"] + selected_headers + ["合并结果", "状态"]
        self.preview_tree.delete(*self.preview_tree.get_children())
        self.preview_tree["columns"] = columns

        for col in columns:
            self.preview_tree.heading(col, text=col)
            self.preview_tree.column(col, width=150, minwidth=80, anchor=tk.W, stretch=False)

        for row in preview_rows:
            self.preview_tree.insert("", tk.END, values=row)

        self.status_var.set(f"已预览 {len(preview_rows)} 行。合并顺序：{' → '.join(selected_headers)}")

    def apply_merge(self):
        try:
            selected_indices = self.get_order_indices()
        except Exception as e:
            messagebox.showwarning("提示", str(e))
            return

        if not selected_indices:
            messagebox.showwarning("提示", "请先添加需要合并的字段到右侧合并顺序列表。")
            return

        if not self.app.rows:
            messagebox.showwarning("提示", "当前没有可合并的数据行。")
            return

        selected_headers = self.get_order_headers()
        separators = self.get_current_separators()
        if len(separators) < max(0, len(selected_indices) - 1):
            separators += [""] * (len(selected_indices) - 1 - len(separators))

        new_header = self.make_unique_header(self.new_field_var.get())

        confirm = messagebox.askyesno(
            "确认合并",
            "将按以下顺序合并字段：\n\n"
            + " → ".join(selected_headers)
            + f"\n\n生成新字段：{new_header}\n\n是否继续？"
        )
        if not confirm:
            return

        self.last_snapshot = (
            list(self.app.headers),
            [list(row) for row in self.app.rows]
        )

        self.app.headers.append(new_header)

        for row in self.app.rows:
            while len(row) < len(self.app.headers) - 1:
                row.append("")
            row.append(self.build_merged_value(row, selected_indices, separators))

        self.app.refresh_tree()
        self.app.info_var.set(f"合并列完成：已生成新字段 {new_header}，共处理 {len(self.app.rows)} 行。")
        self.status_var.set(f"合并完成：已生成新字段 {new_header}。")

        # 主界面字段变化后，刷新左侧字段池；合并顺序保持原字段不变。
        self.refresh_available_fields()
        self.preview_merge()

    def undo_merge(self):
        if not self.last_snapshot:
            messagebox.showinfo("提示", "没有可撤销的合并操作。")
            return

        headers, rows = self.last_snapshot
        self.app.headers = headers
        self.app.rows = rows
        self.app.refresh_tree()
        self.app.info_var.set("已撤销上一次列合并。")
        self.status_var.set("已撤销上一次列合并。")
        self.last_snapshot = None

        self.refresh_available_fields()
        # 移除顺序列表中已不存在的字段。
        existing = set(self.app.headers)
        current = [h for h in self.get_order_headers() if h in existing]
        self.order_listbox.delete(0, tk.END)
        for header in current:
            self.order_listbox.insert(tk.END, header)
        self.rebuild_separator_ui()

        self.preview_tree.delete(*self.preview_tree.get_children())
        self.preview_tree["columns"] = []

    def collect_template(self):
        return {
            "output_field": self.new_field_var.get(),
            "fields": self.get_order_headers(),
            "separators": self.get_current_separators(),
            "skip_empty": self.skip_empty_var.get(),
            "trim_value": self.trim_value_var.get(),
            "empty_placeholder": self.empty_placeholder_var.get(),
            "preview_limit": self.preview_limit_var.get(),
        }

    def apply_template(self, data):
        self.new_field_var.set(data.get("output_field", "合并结果"))
        self.skip_empty_var.set(bool(data.get("skip_empty", False)))
        self.trim_value_var.set(bool(data.get("trim_value", False)))
        self.empty_placeholder_var.set(data.get("empty_placeholder", ""))
        try:
            self.preview_limit_var.set(int(data.get("preview_limit", 500)))
        except Exception:
            self.preview_limit_var.set(500)

        fields = data.get("fields", [])
        existing = set(self.app.headers)
        missing = [field for field in fields if field not in existing]
        valid_fields = [field for field in fields if field in existing]

        self.order_listbox.delete(0, tk.END)
        for field in valid_fields:
            self.order_listbox.insert(tk.END, field)

        # 先重建，再写入模板中的连接符。
        self.rebuild_separator_ui()
        separators = data.get("separators", [])
        for i, sep in enumerate(separators[:len(self.separator_rows)]):
            option, custom = self.separator_to_display(sep)
            self.separator_rows[i]["option_var"].set(option)
            self.separator_rows[i]["custom_var"].set(custom)
            self.update_custom_entry_state(i)

        if missing:
            self.status_var.set("模板已载入，但以下字段不存在，已跳过：" + ", ".join(missing))
        else:
            self.status_var.set("合并模板已载入。")

    def save_template(self):
        path = filedialog.asksaveasfilename(
            title="保存合并规则模板",
            defaultextension=".json",
            filetypes=[("JSON 模板", "*.json"), ("所有文件", "*.*")]
        )
        if not path:
            return
        try:
            atomic_write_json(path, self.collect_template())
            self.status_var.set(f"已保存合并模板：{path}")
        except Exception as e:
            messagebox.showerror("保存模板失败", str(e))

    def load_template(self):
        path = filedialog.askopenfilename(
            title="载入合并规则模板",
            filetypes=[("JSON 模板", "*.json"), ("所有文件", "*.*")]
        )
        if not path:
            return
        try:
            data = load_json_file_with_recovery(path, parent=self.window)
            self.apply_template(data)
            self.status_var.set(f"已载入合并模板：{path}")
        except Exception as e:
            messagebox.showerror("载入模板失败", str(e))
