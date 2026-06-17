# -*- coding: utf-8 -*-
"""Main ClipboardTableApp preview parsing and search helpers."""

import csv
import io
import tkinter as tk
from tkinter import messagebox


class ClipboardTablePreviewMixin:
    """Compatibility methods for the main preview table."""

    def load_clipboard(self):
        try:
            data = self.root.clipboard_get()
        except tk.TclError:
            messagebox.showwarning("提示", "剪贴板中没有可读取的文本数据。")
            return

        if not data.strip():
            messagebox.showwarning("提示", "剪贴板内容为空。")
            return

        self.raw_data = data
        self.parse_data(data)

    def reparse_current_raw(self):
        if self.raw_data:
            self.parse_data(self.raw_data)

    def parse_data(self, data):
        data = data.replace("\r\n", "\n").replace("\r", "\n")

        delimiter = "\t"
        if "\t" not in data and "," in data:
            delimiter = ","

        reader = csv.reader(io.StringIO(data), delimiter=delimiter)
        parsed_rows = []

        for row in reader:
            if not row:
                continue

            cleaned_row = [cell.strip() for cell in row]

            if all(cell == "" for cell in cleaned_row):
                continue

            parsed_rows.append(cleaned_row)

        if not parsed_rows:
            messagebox.showwarning("提示", "没有解析到有效表格数据。")
            return

        max_cols = max(len(row) for row in parsed_rows)

        normalized_rows = []
        for row in parsed_rows:
            row = row + [""] * (max_cols - len(row))
            normalized_rows.append(row)

        if self.first_row_header_var.get() and len(normalized_rows) >= 2:
            raw_headers = normalized_rows[0]
            data_rows = normalized_rows[1:]
        else:
            raw_headers = [f"列{i + 1}" for i in range(max_cols)]
            data_rows = normalized_rows

        self.headers = self.make_display_headers(raw_headers)
        self.rows = data_rows

        self.refresh_tree()

        self.info_var.set(
            f"解析完成：{len(self.rows)} 行 × {len(self.headers)} 列。"
            f" 分隔符：{'TAB制表符' if delimiter == chr(9) else '逗号'}"
        )

    def make_display_headers(self, headers):
        result = []
        used = {}

        for index, header in enumerate(headers, start=1):
            name = str(header).strip()
            if not name:
                name = f"列{index}"

            if name in used:
                used[name] += 1
                name = f"{name}_{used[name]}"
            else:
                used[name] = 1

            result.append(name)

        return result

    def refresh_tree(self):
        self.search_matches = []
        self.search_index = -1
        self.tree.delete(*self.tree.get_children())

        self.tree["columns"] = self.headers

        for col in self.headers:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=140, minwidth=80, anchor=tk.W, stretch=False)

        self.tree.tag_configure("search_match", background="#fff7cc")
        self.tree.tag_configure("search_current", background="#ffd580")

        for row in self.rows:
            fixed = list(row)
            if len(fixed) < len(self.headers):
                fixed += [""] * (len(self.headers) - len(fixed))
            if len(fixed) > len(self.headers):
                fixed = fixed[:len(self.headers)]
            self.tree.insert("", tk.END, values=fixed)

    def clear_main_search_marks(self):
        for iid in self.tree.get_children():
            self.tree.item(iid, tags=())
        self.search_matches = []
        self.search_index = -1

    def search_main_preview(self, reset=True):
        keyword = self.search_var.get().strip()
        if not keyword:
            messagebox.showwarning("提示", "请输入搜索关键词。")
            return

        keyword_lower = keyword.lower()
        self.clear_main_search_marks()

        for iid in self.tree.get_children():
            values = self.tree.item(iid, "values")
            row_text = "\t".join(str(v) for v in values)
            if keyword_lower in row_text.lower():
                self.search_matches.append(iid)
                self.tree.item(iid, tags=("search_match",))

        if not self.search_matches:
            self.info_var.set(f"搜索完成：未找到包含『{keyword}』的行。")
            return

        self.search_index = 0 if reset else max(self.search_index, 0)
        self.goto_main_search_result()
        self.info_var.set(f"搜索完成：找到 {len(self.search_matches)} 行匹配『{keyword}』。")

    def goto_main_search_result(self):
        if not self.search_matches:
            return
        self.search_index %= len(self.search_matches)
        current_iid = self.search_matches[self.search_index]
        for iid in self.search_matches:
            self.tree.item(iid, tags=("search_match",))
        self.tree.item(current_iid, tags=("search_current",))
        self.tree.selection_set(current_iid)
        self.tree.focus(current_iid)
        self.tree.see(current_iid)
        self.info_var.set(f"当前搜索结果：{self.search_index + 1}/{len(self.search_matches)}")

    def search_main_next(self):
        if not self.search_matches:
            self.search_main_preview(reset=True)
            return
        self.search_index += 1
        self.goto_main_search_result()

    def search_main_prev(self):
        if not self.search_matches:
            self.search_main_preview(reset=True)
            return
        self.search_index -= 1
        self.goto_main_search_result()

    def clear_preview(self):
        self.raw_data = ""
        self.headers = []
        self.rows = []

        if self.edit_entry is not None:
            self.edit_entry.destroy()
            self.edit_entry = None

        self.tree.delete(*self.tree.get_children())
        self.tree["columns"] = []
        self.info_var.set("已清空预览。")

    def delete_header_and_promote_next_row(self):
        if not self.headers:
            messagebox.showwarning("提示", "当前没有字段名，请先读取剪贴板数据。")
            return

        if not self.rows:
            messagebox.showwarning("提示", "当前没有下一行数据，无法提升为字段名。")
            return

        new_headers_raw = self.rows[0]
        new_rows = self.rows[1:]

        self.headers = self.make_display_headers(new_headers_raw)
        self.rows = new_rows

        self.refresh_tree()

        self.info_var.set(
            f"已删除原字段名，并使用下一行作为新字段名："
            f"{len(self.rows)} 行 × {len(self.headers)} 列。"
        )
