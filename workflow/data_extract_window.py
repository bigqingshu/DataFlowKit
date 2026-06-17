# -*- coding: utf-8 -*-
"""Data extraction / field generation window."""

import re
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
from datetime import datetime

from shared.atomic_json_utils import atomic_write_json, load_json_with_backup


def load_json_file_with_recovery(path, parent=None):
    data, info = load_json_with_backup(path)
    warning = info.get("warning", "")
    if warning:
        messagebox.showwarning("配置已从备份恢复", warning, parent=parent)
    return data


class DataExtractWindow:
    # 数据提取 / 字段生成窗口

    METHODS = [
        "正则提取",
        "固定位置提取",
        "从左取N位",
        "从右取N位",
        "按分隔符提取",
        "前后关键字之间提取",
        "指定字符前提取",
        "指定字符后提取",
        "删除前缀",
        "删除后缀",
    ]
    OUTPUT_MODES = ["生成新字段", "覆盖源字段"]
    UNMATCHED_MODES = ["留空", "保留原值", "填写固定值", "跳过该行"]
    POSITION_BASES = ["从1开始", "从0开始"]
    FIND_MODES = ["第一次出现", "最后一次出现"]

    def __init__(self, app):
        self.app = app
        self.window = tk.Toplevel(app.root)
        self.window.title("数据提取 / 字段生成")
        self.window.geometry("1320x780")
        self.window.transient(app.root)

        self.preview_results = []
        self.last_backup = None

        self.source_field_var = tk.StringVar(value=app.headers[0] if app.headers else "")
        self.method_var = tk.StringVar(value="正则提取")
        self.output_mode_var = tk.StringVar(value="生成新字段")
        self.new_field_var = tk.StringVar(value="提取结果")
        self.unmatched_mode_var = tk.StringVar(value="留空")
        self.unmatched_fixed_var = tk.StringVar(value="未匹配")
        self.result_limit_var = tk.StringVar(value="1000")
        self.case_sensitive_var = tk.BooleanVar(value=True)
        self.strip_result_var = tk.BooleanVar(value=True)

        # 正则提取
        self.regex_pattern_var = tk.StringVar()
        self.regex_group_var = tk.StringVar(value="0")
        self.regex_find_all_var = tk.BooleanVar(value=False)
        self.regex_joiner_var = tk.StringVar(value=";")

        # 固定位置提取
        self.start_pos_var = tk.StringVar(value="1")
        self.extract_len_var = tk.StringVar(value="1")
        self.position_base_var = tk.StringVar(value="从1开始")

        # 左/右取N位
        self.n_chars_var = tk.StringVar(value="1")

        # 分隔符提取
        self.delimiter_var = tk.StringVar(value="-")
        self.part_index_var = tk.StringVar(value="1")
        self.ignore_empty_part_var = tk.BooleanVar(value=False)

        # 前后关键字之间提取
        self.before_key_var = tk.StringVar()
        self.after_key_var = tk.StringVar()
        self.between_occurrence_var = tk.StringVar(value="1")

        # 指定字符前/后提取
        self.marker_var = tk.StringVar(value="-")
        self.find_mode_var = tk.StringVar(value="第一次出现")

        # 删除前缀/后缀
        self.prefix_var = tk.StringVar()
        self.suffix_var = tk.StringVar()

        self.build_ui()
        self.update_param_ui()

    def build_ui(self):
        main = ttk.Frame(self.window, padding=8)
        main.pack(fill=tk.BOTH, expand=True)

        top = ttk.LabelFrame(main, text="1. 数据源与提取方式", padding=8)
        top.pack(fill=tk.X)

        ttk.Label(top, text="源字段：").grid(row=0, column=0, sticky=tk.W, padx=4, pady=4)
        self.source_combo = ttk.Combobox(top, textvariable=self.source_field_var, values=self.app.headers, width=28, state="readonly")
        self.source_combo.grid(row=0, column=1, sticky=tk.W, padx=4, pady=4)

        ttk.Label(top, text="提取方式：").grid(row=0, column=2, sticky=tk.W, padx=4, pady=4)
        method_combo = ttk.Combobox(top, textvariable=self.method_var, values=self.METHODS, width=22, state="readonly")
        method_combo.grid(row=0, column=3, sticky=tk.W, padx=4, pady=4)
        method_combo.bind("<<ComboboxSelected>>", lambda event: self.update_param_ui())

        ttk.Checkbutton(top, text="区分大小写", variable=self.case_sensitive_var).grid(row=0, column=4, sticky=tk.W, padx=4, pady=4)
        ttk.Checkbutton(top, text="提取结果去除首尾空格", variable=self.strip_result_var).grid(row=0, column=5, sticky=tk.W, padx=4, pady=4)

        self.param_frame = ttk.LabelFrame(main, text="2. 提取参数", padding=8)
        self.param_frame.pack(fill=tk.X, pady=8)

        output = ttk.LabelFrame(main, text="3. 输出设置", padding=8)
        output.pack(fill=tk.X)

        ttk.Label(output, text="输出方式：").grid(row=0, column=0, sticky=tk.W, padx=4, pady=4)
        output_combo = ttk.Combobox(output, textvariable=self.output_mode_var, values=self.OUTPUT_MODES, width=16, state="readonly")
        output_combo.grid(row=0, column=1, sticky=tk.W, padx=4, pady=4)
        output_combo.bind("<<ComboboxSelected>>", lambda event: self.update_output_state())

        ttk.Label(output, text="新字段名：").grid(row=0, column=2, sticky=tk.W, padx=4, pady=4)
        self.new_field_entry = ttk.Entry(output, textvariable=self.new_field_var, width=28)
        self.new_field_entry.grid(row=0, column=3, sticky=tk.W, padx=4, pady=4)

        ttk.Label(output, text="未匹配时：").grid(row=0, column=4, sticky=tk.W, padx=4, pady=4)
        ttk.Combobox(output, textvariable=self.unmatched_mode_var, values=self.UNMATCHED_MODES, width=14, state="readonly").grid(row=0, column=5, sticky=tk.W, padx=4, pady=4)

        ttk.Label(output, text="固定值：").grid(row=0, column=6, sticky=tk.W, padx=4, pady=4)
        ttk.Entry(output, textvariable=self.unmatched_fixed_var, width=18).grid(row=0, column=7, sticky=tk.W, padx=4, pady=4)

        center = ttk.LabelFrame(main, text="4. 提取结果预览", padding=6)
        center.pack(fill=tk.BOTH, expand=True, pady=8)

        self.preview_tree = ttk.Treeview(
            center,
            columns=("行号", "原内容", "提取结果", "状态"),
            show="headings",
            height=16
        )
        for col, width in [("行号", 70), ("原内容", 420), ("提取结果", 420), ("状态", 140)]:
            self.preview_tree.heading(col, text=col)
            self.preview_tree.column(col, width=width, anchor=tk.W, stretch=False)

        y_scroll = ttk.Scrollbar(center, orient=tk.VERTICAL, command=self.preview_tree.yview)
        x_scroll = ttk.Scrollbar(center, orient=tk.HORIZONTAL, command=self.preview_tree.xview)
        self.preview_tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)
        self.preview_tree.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")
        center.rowconfigure(0, weight=1)
        center.columnconfigure(0, weight=1)

        bottom = ttk.Frame(main)
        bottom.pack(fill=tk.X)

        ttk.Label(bottom, text="预览最大显示行数：").pack(side=tk.LEFT, padx=4)
        ttk.Entry(bottom, textvariable=self.result_limit_var, width=8).pack(side=tk.LEFT, padx=4)
        ttk.Button(bottom, text="预览提取结果", command=self.preview_extract).pack(side=tk.LEFT, padx=4)
        ttk.Button(bottom, text="执行提取", command=self.execute_extract).pack(side=tk.LEFT, padx=4)
        ttk.Button(bottom, text="撤销上一次提取", command=self.undo_last_extract).pack(side=tk.LEFT, padx=4)
        ttk.Button(bottom, text="保存当前结果为新表", command=self.save_current_result_to_new_table).pack(side=tk.LEFT, padx=4)
        ttk.Button(bottom, text="保存规则模板", command=self.save_template).pack(side=tk.LEFT, padx=4)
        ttk.Button(bottom, text="载入规则模板", command=self.load_template).pack(side=tk.LEFT, padx=4)
        ttk.Button(bottom, text="关闭", command=self.window.destroy).pack(side=tk.RIGHT, padx=4)

        self.status_var = tk.StringVar(value="提示：正则提取直接使用 Python re 规则。分组 0 表示完整匹配，分组 1 表示第一个括号内容。")
        ttk.Label(main, textvariable=self.status_var, padding=(0, 6)).pack(fill=tk.X)
        self.update_output_state()

    def clear_param_frame(self):
        for child in self.param_frame.winfo_children():
            child.destroy()

    def update_param_ui(self):
        self.clear_param_frame()
        method = self.method_var.get()

        if method == "正则提取":
            ttk.Label(self.param_frame, text="Python正则：").grid(row=0, column=0, sticky=tk.W, padx=4, pady=4)
            ttk.Entry(self.param_frame, textvariable=self.regex_pattern_var, width=60).grid(row=0, column=1, columnspan=4, sticky=tk.W, padx=4, pady=4)
            ttk.Label(self.param_frame, text="提取分组：").grid(row=0, column=5, sticky=tk.W, padx=4, pady=4)
            ttk.Entry(self.param_frame, textvariable=self.regex_group_var, width=8).grid(row=0, column=6, sticky=tk.W, padx=4, pady=4)
            ttk.Checkbutton(self.param_frame, text="提取全部匹配", variable=self.regex_find_all_var).grid(row=1, column=1, sticky=tk.W, padx=4, pady=4)
            ttk.Label(self.param_frame, text="全部匹配连接符：").grid(row=1, column=2, sticky=tk.W, padx=4, pady=4)
            ttk.Entry(self.param_frame, textvariable=self.regex_joiner_var, width=12).grid(row=1, column=3, sticky=tk.W, padx=4, pady=4)
            ttk.Label(self.param_frame, text="示例：BP\\d+GK 或 客码[:：]([A-Za-z0-9_-]+)").grid(row=1, column=4, columnspan=4, sticky=tk.W, padx=4, pady=4)

        elif method == "固定位置提取":
            ttk.Label(self.param_frame, text="起始位置：").grid(row=0, column=0, sticky=tk.W, padx=4, pady=4)
            ttk.Entry(self.param_frame, textvariable=self.start_pos_var, width=10).grid(row=0, column=1, sticky=tk.W, padx=4, pady=4)
            ttk.Label(self.param_frame, text="提取长度：").grid(row=0, column=2, sticky=tk.W, padx=4, pady=4)
            ttk.Entry(self.param_frame, textvariable=self.extract_len_var, width=10).grid(row=0, column=3, sticky=tk.W, padx=4, pady=4)
            ttk.Label(self.param_frame, text="位置规则：").grid(row=0, column=4, sticky=tk.W, padx=4, pady=4)
            ttk.Combobox(self.param_frame, textvariable=self.position_base_var, values=self.POSITION_BASES, width=12, state="readonly").grid(row=0, column=5, sticky=tk.W, padx=4, pady=4)
            ttk.Label(self.param_frame, text="示例：123456789，起始3、长度4 → 3456（从1开始）").grid(row=1, column=0, columnspan=6, sticky=tk.W, padx=4, pady=4)

        elif method in ["从左取N位", "从右取N位"]:
            ttk.Label(self.param_frame, text="N：").grid(row=0, column=0, sticky=tk.W, padx=4, pady=4)
            ttk.Entry(self.param_frame, textvariable=self.n_chars_var, width=10).grid(row=0, column=1, sticky=tk.W, padx=4, pady=4)
            ttk.Label(self.param_frame, text="示例：ABC123456，取3位 → 左取ABC / 右取456").grid(row=0, column=2, columnspan=5, sticky=tk.W, padx=4, pady=4)

        elif method == "按分隔符提取":
            ttk.Label(self.param_frame, text="分隔符：").grid(row=0, column=0, sticky=tk.W, padx=4, pady=4)
            ttk.Entry(self.param_frame, textvariable=self.delimiter_var, width=16).grid(row=0, column=1, sticky=tk.W, padx=4, pady=4)
            ttk.Label(self.param_frame, text="取第几段：").grid(row=0, column=2, sticky=tk.W, padx=4, pady=4)
            ttk.Entry(self.param_frame, textvariable=self.part_index_var, width=10).grid(row=0, column=3, sticky=tk.W, padx=4, pady=4)
            ttk.Checkbutton(self.param_frame, text="忽略空段", variable=self.ignore_empty_part_var).grid(row=0, column=4, sticky=tk.W, padx=4, pady=4)
            ttk.Label(self.param_frame, text="段序号从1开始；可填 -1 表示最后一段，-2 表示倒数第2段。").grid(row=1, column=0, columnspan=6, sticky=tk.W, padx=4, pady=4)

        elif method == "前后关键字之间提取":
            ttk.Label(self.param_frame, text="开始关键字：").grid(row=0, column=0, sticky=tk.W, padx=4, pady=4)
            ttk.Entry(self.param_frame, textvariable=self.before_key_var, width=24).grid(row=0, column=1, sticky=tk.W, padx=4, pady=4)
            ttk.Label(self.param_frame, text="结束关键字：").grid(row=0, column=2, sticky=tk.W, padx=4, pady=4)
            ttk.Entry(self.param_frame, textvariable=self.after_key_var, width=24).grid(row=0, column=3, sticky=tk.W, padx=4, pady=4)
            ttk.Label(self.param_frame, text="第几个匹配：").grid(row=0, column=4, sticky=tk.W, padx=4, pady=4)
            ttk.Entry(self.param_frame, textvariable=self.between_occurrence_var, width=8).grid(row=0, column=5, sticky=tk.W, padx=4, pady=4)
            ttk.Label(self.param_frame, text="示例：型号[BP2526GK]，开始 型号[，结束 ] → BP2526GK").grid(row=1, column=0, columnspan=6, sticky=tk.W, padx=4, pady=4)

        elif method in ["指定字符前提取", "指定字符后提取"]:
            ttk.Label(self.param_frame, text="指定字符/字符串：").grid(row=0, column=0, sticky=tk.W, padx=4, pady=4)
            ttk.Entry(self.param_frame, textvariable=self.marker_var, width=20).grid(row=0, column=1, sticky=tk.W, padx=4, pady=4)
            ttk.Label(self.param_frame, text="查找位置：").grid(row=0, column=2, sticky=tk.W, padx=4, pady=4)
            ttk.Combobox(self.param_frame, textvariable=self.find_mode_var, values=self.FIND_MODES, width=12, state="readonly").grid(row=0, column=3, sticky=tk.W, padx=4, pady=4)
            ttk.Label(self.param_frame, text="示例：BP2526GK-35RD-01，指定 -，前提取 → BP2526GK").grid(row=1, column=0, columnspan=6, sticky=tk.W, padx=4, pady=4)

        elif method == "删除前缀":
            ttk.Label(self.param_frame, text="要删除的前缀：").grid(row=0, column=0, sticky=tk.W, padx=4, pady=4)
            ttk.Entry(self.param_frame, textvariable=self.prefix_var, width=30).grid(row=0, column=1, sticky=tk.W, padx=4, pady=4)
            ttk.Label(self.param_frame, text="示例：HYBP2526GK 删除 HY → BP2526GK").grid(row=0, column=2, columnspan=5, sticky=tk.W, padx=4, pady=4)

        elif method == "删除后缀":
            ttk.Label(self.param_frame, text="要删除的后缀：").grid(row=0, column=0, sticky=tk.W, padx=4, pady=4)
            ttk.Entry(self.param_frame, textvariable=self.suffix_var, width=30).grid(row=0, column=1, sticky=tk.W, padx=4, pady=4)
            ttk.Label(self.param_frame, text="示例：BP2526GK_TEMP 删除 _TEMP → BP2526GK").grid(row=0, column=2, columnspan=5, sticky=tk.W, padx=4, pady=4)

    def update_output_state(self):
        if self.output_mode_var.get() == "生成新字段":
            self.new_field_entry.configure(state="normal")
        else:
            self.new_field_entry.configure(state="disabled")

    def get_source_index(self):
        field = self.source_field_var.get().strip()
        if field not in self.app.headers:
            raise ValueError("请选择有效的源字段。")
        return self.app.headers.index(field)

    def parse_int(self, value, name):
        try:
            return int(str(value).strip())
        except Exception:
            raise ValueError(f"{name} 必须是整数。")

    def normalize_case(self, text):
        return text if self.case_sensitive_var.get() else text.lower()

    def find_marker_index(self, text, marker):
        if marker == "":
            raise ValueError("指定字符/字符串不能为空。")
        search_text = self.normalize_case(text)
        search_marker = self.normalize_case(marker)
        if self.find_mode_var.get() == "最后一次出现":
            return search_text.rfind(search_marker)
        return search_text.find(search_marker)

    def apply_unmatched(self, original, status):
        mode = self.unmatched_mode_var.get()
        if mode == "留空":
            return "", status
        if mode == "保留原值":
            return original, status
        if mode == "填写固定值":
            return self.unmatched_fixed_var.get(), status
        if mode == "跳过该行":
            return "", "跳过"
        return "", status

    def post_process_result(self, result):
        if result is None:
            result = ""
        result = str(result)
        if self.strip_result_var.get():
            result = result.strip()
        return result

    def extract_one(self, original):
        text = "" if original is None else str(original)
        method = self.method_var.get()

        try:
            if method == "正则提取":
                pattern = self.regex_pattern_var.get()
                if not pattern:
                    raise ValueError("正则表达式不能为空。")
                flags = 0 if self.case_sensitive_var.get() else re.IGNORECASE
                group_index = self.parse_int(self.regex_group_var.get(), "提取分组")

                if self.regex_find_all_var.get():
                    results = []
                    for m in re.finditer(pattern, text, flags):
                        try:
                            results.append(m.group(group_index))
                        except IndexError:
                            return self.apply_unmatched(text, "分组不存在")
                    if not results:
                        return self.apply_unmatched(text, "未匹配")
                    return self.post_process_result(self.regex_joiner_var.get().join(results)), "成功"

                m = re.search(pattern, text, flags)
                if not m:
                    return self.apply_unmatched(text, "未匹配")
                try:
                    return self.post_process_result(m.group(group_index)), "成功"
                except IndexError:
                    return self.apply_unmatched(text, "分组不存在")

            if method == "固定位置提取":
                start = self.parse_int(self.start_pos_var.get(), "起始位置")
                length = self.parse_int(self.extract_len_var.get(), "提取长度")
                if length < 0:
                    raise ValueError("提取长度不能小于0。")
                start_idx = start - 1 if self.position_base_var.get() == "从1开始" else start
                if start_idx < 0 or start_idx >= len(text):
                    return self.apply_unmatched(text, "越界")
                return self.post_process_result(text[start_idx:start_idx + length]), "成功"

            if method == "从左取N位":
                n = self.parse_int(self.n_chars_var.get(), "N")
                if n < 0:
                    raise ValueError("N不能小于0。")
                return self.post_process_result(text[:n]), "成功"

            if method == "从右取N位":
                n = self.parse_int(self.n_chars_var.get(), "N")
                if n < 0:
                    raise ValueError("N不能小于0。")
                return self.post_process_result(text[-n:] if n else ""), "成功"

            if method == "按分隔符提取":
                delimiter = self.delimiter_var.get()
                if delimiter == "":
                    raise ValueError("分隔符不能为空。")
                parts = text.split(delimiter)
                if self.ignore_empty_part_var.get():
                    parts = [p for p in parts if p != ""]
                part_index = self.parse_int(self.part_index_var.get(), "取第几段")
                if part_index == 0:
                    raise ValueError("段序号不能为0。正数从1开始，负数表示倒数。")
                idx = part_index - 1 if part_index > 0 else part_index
                if idx < -len(parts) or idx >= len(parts):
                    return self.apply_unmatched(text, "越界")
                return self.post_process_result(parts[idx]), "成功"

            if method == "前后关键字之间提取":
                start_key = self.before_key_var.get()
                end_key = self.after_key_var.get()
                if start_key == "" or end_key == "":
                    raise ValueError("开始关键字和结束关键字不能为空。")
                occurrence = self.parse_int(self.between_occurrence_var.get(), "第几个匹配")
                if occurrence <= 0:
                    raise ValueError("第几个匹配必须大于0。")

                search_text = self.normalize_case(text)
                search_start = self.normalize_case(start_key)
                search_end = self.normalize_case(end_key)
                pos = 0
                found = None
                for _ in range(occurrence):
                    s = search_text.find(search_start, pos)
                    if s < 0:
                        return self.apply_unmatched(text, "未匹配")
                    content_start = s + len(start_key)
                    e = search_text.find(search_end, content_start)
                    if e < 0:
                        return self.apply_unmatched(text, "未匹配")
                    found = text[content_start:e]
                    pos = e + len(end_key)
                return self.post_process_result(found), "成功"

            if method == "指定字符前提取":
                marker = self.marker_var.get()
                idx = self.find_marker_index(text, marker)
                if idx < 0:
                    return self.apply_unmatched(text, "未匹配")
                return self.post_process_result(text[:idx]), "成功"

            if method == "指定字符后提取":
                marker = self.marker_var.get()
                idx = self.find_marker_index(text, marker)
                if idx < 0:
                    return self.apply_unmatched(text, "未匹配")
                return self.post_process_result(text[idx + len(marker):]), "成功"

            if method == "删除前缀":
                prefix = self.prefix_var.get()
                if prefix == "":
                    raise ValueError("前缀不能为空。")
                if self.normalize_case(text).startswith(self.normalize_case(prefix)):
                    return self.post_process_result(text[len(prefix):]), "成功"
                return self.apply_unmatched(text, "未匹配")

            if method == "删除后缀":
                suffix = self.suffix_var.get()
                if suffix == "":
                    raise ValueError("后缀不能为空。")
                if self.normalize_case(text).endswith(self.normalize_case(suffix)):
                    return self.post_process_result(text[:-len(suffix)]), "成功"
                return self.apply_unmatched(text, "未匹配")

            raise ValueError(f"未知提取方式：{method}")

        except re.error as e:
            raise ValueError(f"正则错误：{e}")

    def build_preview_results(self):
        source_idx = self.get_source_index()
        results = []
        for row_index, row in enumerate(self.app.rows):
            original = ""
            if source_idx < len(row):
                original = row[source_idx]
            extracted, status = self.extract_one(original)
            results.append({
                "row_index": row_index,
                "original": "" if original is None else str(original),
                "extracted": "" if extracted is None else str(extracted),
                "status": status
            })
        return results

    def get_preview_limit(self):
        try:
            limit = int(self.result_limit_var.get().strip())
            return max(limit, 1)
        except Exception:
            return 1000

    def refresh_preview_tree(self, results):
        self.preview_tree.delete(*self.preview_tree.get_children())
        limit = self.get_preview_limit()
        for item in results[:limit]:
            self.preview_tree.insert("", tk.END, values=(
                item["row_index"] + 1,
                item["original"],
                item["extracted"],
                item["status"]
            ))

    def preview_extract(self):
        try:
            results = self.build_preview_results()
        except Exception as e:
            messagebox.showwarning("预览失败", str(e))
            return

        self.preview_results = results
        self.refresh_preview_tree(results)
        success_count = sum(1 for r in results if r.get("status") == "成功")
        skip_count = sum(1 for r in results if r.get("status") == "跳过")
        self.status_var.set(
            f"预览完成：共 {len(results)} 行，成功 {success_count} 行，跳过 {skip_count} 行，"
            f"当前显示前 {min(self.get_preview_limit(), len(results))} 行。"
        )

    def get_unique_header(self, base_name, headers):
        name = str(base_name or "提取结果").strip() or "提取结果"
        if name not in headers:
            return name
        counter = 2
        while f"{name}_{counter}" in headers:
            counter += 1
        return f"{name}_{counter}"

    def execute_extract(self):
        try:
            results = self.build_preview_results()
            source_idx = self.get_source_index()
        except Exception as e:
            messagebox.showwarning("执行失败", str(e))
            return

        if self.output_mode_var.get() == "覆盖源字段":
            ok = messagebox.askyesno("确认覆盖", "覆盖源字段会直接修改当前预览数据，是否继续？")
            if not ok:
                return

        self.last_backup = {
            "headers": list(self.app.headers),
            "rows": [list(row) for row in self.app.rows]
        }

        changed = 0
        skipped = 0
        if self.output_mode_var.get() == "生成新字段":
            new_field = self.get_unique_header(self.new_field_var.get(), self.app.headers)
            self.app.headers.append(new_field)
            for item, row in zip(results, self.app.rows):
                if item["status"] == "跳过":
                    skipped += 1
                    row.append("")
                    continue
                row.append(item["extracted"])
                changed += 1
        else:
            for item, row in zip(results, self.app.rows):
                if item["status"] == "跳过":
                    skipped += 1
                    continue
                while len(row) < len(self.app.headers):
                    row.append("")
                if source_idx < len(row):
                    row[source_idx] = item["extracted"]
                    changed += 1

        self.preview_results = results
        self.refresh_preview_tree(results)
        self.app.refresh_tree()
        self.app.info_var.set(f"数据提取完成：修改/写入 {changed} 行，跳过 {skipped} 行。")
        self.status_var.set(f"执行完成：修改/写入 {changed} 行，跳过 {skipped} 行。可点击“撤销上一次提取”恢复。")

    def undo_last_extract(self):
        if not self.last_backup:
            messagebox.showwarning("提示", "没有可撤销的提取操作。")
            return

        self.app.headers = list(self.last_backup["headers"])
        self.app.rows = [list(row) for row in self.last_backup["rows"]]
        self.last_backup = None
        self.source_combo.configure(values=self.app.headers)
        if self.app.headers:
            self.source_field_var.set(self.app.headers[0])
        self.app.refresh_tree()
        self.app.info_var.set("已撤销上一次数据提取。")
        self.status_var.set("已撤销上一次数据提取。")

    def save_current_result_to_new_table(self):
        if not self.app.headers:
            messagebox.showwarning("提示", "当前没有可保存的数据。")
            return
        default_name = f"提取结果_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        name = simpledialog.askstring("保存为新表", "请输入新表名：", initialvalue=default_name, parent=self.window)
        if not name:
            return
        try:
            table_name, row_count = self.app.save_rows_to_sqlite_table(
                table_name_raw=name,
                headers=self.app.headers,
                rows=self.app.rows,
                recreate=False
            )
            self.app.table_name_var.set(table_name)
            self.app.info_var.set(f"数据提取结果已保存为新表：{table_name}，共 {row_count} 行。")
            messagebox.showinfo("保存成功", f"已保存为新表：{table_name}\n行数：{row_count}")
        except Exception as e:
            messagebox.showerror("保存失败", str(e))

    def collect_template(self):
        return {
            "source_field": self.source_field_var.get(),
            "method": self.method_var.get(),
            "output_mode": self.output_mode_var.get(),
            "new_field": self.new_field_var.get(),
            "unmatched_mode": self.unmatched_mode_var.get(),
            "unmatched_fixed": self.unmatched_fixed_var.get(),
            "case_sensitive": bool(self.case_sensitive_var.get()),
            "strip_result": bool(self.strip_result_var.get()),
            "regex_pattern": self.regex_pattern_var.get(),
            "regex_group": self.regex_group_var.get(),
            "regex_find_all": bool(self.regex_find_all_var.get()),
            "regex_joiner": self.regex_joiner_var.get(),
            "start_pos": self.start_pos_var.get(),
            "extract_len": self.extract_len_var.get(),
            "position_base": self.position_base_var.get(),
            "n_chars": self.n_chars_var.get(),
            "delimiter": self.delimiter_var.get(),
            "part_index": self.part_index_var.get(),
            "ignore_empty_part": bool(self.ignore_empty_part_var.get()),
            "before_key": self.before_key_var.get(),
            "after_key": self.after_key_var.get(),
            "between_occurrence": self.between_occurrence_var.get(),
            "marker": self.marker_var.get(),
            "find_mode": self.find_mode_var.get(),
            "prefix": self.prefix_var.get(),
            "suffix": self.suffix_var.get(),
        }

    def apply_template(self, data):
        def set_if(name, var):
            if name in data:
                var.set(data[name])

        set_if("source_field", self.source_field_var)
        set_if("method", self.method_var)
        set_if("output_mode", self.output_mode_var)
        set_if("new_field", self.new_field_var)
        set_if("unmatched_mode", self.unmatched_mode_var)
        set_if("unmatched_fixed", self.unmatched_fixed_var)
        if "case_sensitive" in data:
            self.case_sensitive_var.set(bool(data["case_sensitive"]))
        if "strip_result" in data:
            self.strip_result_var.set(bool(data["strip_result"]))
        set_if("regex_pattern", self.regex_pattern_var)
        set_if("regex_group", self.regex_group_var)
        if "regex_find_all" in data:
            self.regex_find_all_var.set(bool(data["regex_find_all"]))
        set_if("regex_joiner", self.regex_joiner_var)
        set_if("start_pos", self.start_pos_var)
        set_if("extract_len", self.extract_len_var)
        set_if("position_base", self.position_base_var)
        set_if("n_chars", self.n_chars_var)
        set_if("delimiter", self.delimiter_var)
        set_if("part_index", self.part_index_var)
        if "ignore_empty_part" in data:
            self.ignore_empty_part_var.set(bool(data["ignore_empty_part"]))
        set_if("before_key", self.before_key_var)
        set_if("after_key", self.after_key_var)
        set_if("between_occurrence", self.between_occurrence_var)
        set_if("marker", self.marker_var)
        set_if("find_mode", self.find_mode_var)
        set_if("prefix", self.prefix_var)
        set_if("suffix", self.suffix_var)
        self.update_param_ui()
        self.update_output_state()

    def save_template(self):
        path = filedialog.asksaveasfilename(
            title="保存数据提取规则模板",
            defaultextension=".json",
            filetypes=[("JSON 模板", "*.json"), ("所有文件", "*.*")]
        )
        if not path:
            return
        try:
            atomic_write_json(path, self.collect_template())
            self.status_var.set(f"已保存模板：{path}")
        except Exception as e:
            messagebox.showerror("保存模板失败", str(e))

    def load_template(self):
        path = filedialog.askopenfilename(
            title="载入数据提取规则模板",
            filetypes=[("JSON 模板", "*.json"), ("所有文件", "*.*")]
        )
        if not path:
            return
        try:
            data = load_json_file_with_recovery(path, parent=self.window)
            self.apply_template(data)
            self.status_var.set(f"已载入模板：{path}")
        except Exception as e:
            messagebox.showerror("载入模板失败", str(e))
