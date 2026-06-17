# -*- coding: utf-8 -*-
"""PlanWorkflowWindow mixin for result preview table helpers."""

import os
import sys
import tkinter as tk
from tkinter import messagebox as tk_messagebox

from db import TableAccessManager


def _window_messagebox(window):
    module = sys.modules.get(window.__class__.__module__)
    return getattr(module, "messagebox", tk_messagebox)


class PlanPreviewMixin:
    """Compatibility methods used by the result preview area."""

    def set_plan_preview_result(self, headers, rows, display=True, source_label="当前预览结果"):
        """Save the latest workflow preview/execution result."""
        self.plan_preview_headers = list(headers or [])
        self.plan_preview_rows = [list(row) for row in (rows or [])]
        if display:
            self.preview_view_kind = "preview"
            self.preview_table_var.set("当前预览结果")
            self.preview_headers = list(self.plan_preview_headers)
            self.preview_rows = [list(row) for row in self.plan_preview_rows]
            self.refresh_preview_tree(self.preview_headers, self.preview_rows)

    def get_plan_preview_result(self):
        headers = list(getattr(self, "plan_preview_headers", []))
        rows = [list(row) for row in getattr(self, "plan_preview_rows", [])]
        return headers, rows

    def reload_from_app_preview(self):
        headers = list(self.app.headers)
        rows = [list(row) for row in self.app.rows]
        self.set_plan_preview_result(headers, rows, display=True, source_label="主界面当前预览")
        self.status_var.set(f"已重新读取主界面当前预览，并保存为当前预览结果：{len(rows)} 行 × {len(headers)} 列。")
        self.rebuild_current_config()

    def toggle_preview_edit_mode(self):
        self.preview_edit_mode = not self.preview_edit_mode
        if self.preview_edit_mode:
            self.preview_edit_btn_text.set("修改模式:开")
            self.status_var.set("计划预览修改模式已开启：双击结果预览表格中的单元格即可修改当前预览数据。")
        else:
            self.preview_edit_btn_text.set("修改模式:关")
            self.status_var.set("计划预览修改模式已关闭。")
            if self.preview_edit_entry is not None:
                self.preview_edit_entry.destroy()
                self.preview_edit_entry = None

    def refresh_preview_tree(self, headers, rows, limit=1000):
        if self.preview_edit_entry is not None:
            self.preview_edit_entry.destroy()
            self.preview_edit_entry = None
        self.preview_search_matches = []
        self.preview_search_index = -1
        self.preview_dirty = False
        self.preview_tree.delete(*self.preview_tree.get_children())
        self.preview_tree["columns"] = headers
        for h in headers:
            self.preview_tree.heading(h, text=h)
            self.preview_tree.column(h, width=140, minwidth=80, anchor=tk.W, stretch=False)
        self.preview_tree.tag_configure("search_match", background="#fff7cc")
        self.preview_tree.tag_configure("search_current", background="#ffd580")
        for row in rows[:limit]:
            fixed = list(row)
            if len(fixed) < len(headers):
                fixed += [""] * (len(headers) - len(fixed))
            if len(fixed) > len(headers):
                fixed = fixed[:len(headers)]
            self.preview_tree.insert("", tk.END, values=fixed)
        try:
            self.refresh_preview_table_choices(show_status=False)
        except Exception:
            pass

    def clear_preview_search_marks(self):
        for iid in self.preview_tree.get_children():
            self.preview_tree.item(iid, tags=())
        self.preview_search_matches = []
        self.preview_search_index = -1

    def search_preview_table(self, reset=True):
        msg = _window_messagebox(self)
        keyword = self.preview_search_var.get().strip()
        if not keyword:
            msg.showwarning("提示", "请输入搜索关键词。")
            return

        keyword_lower = keyword.lower()
        self.clear_preview_search_marks()

        for iid in self.preview_tree.get_children():
            values = self.preview_tree.item(iid, "values")
            row_text = "\t".join(str(v) for v in values)
            if keyword_lower in row_text.lower():
                self.preview_search_matches.append(iid)
                self.preview_tree.item(iid, tags=("search_match",))

        if not self.preview_search_matches:
            self.status_var.set(f"搜索完成：未找到包含『{keyword}』的结果预览行。")
            return

        self.preview_search_index = 0 if reset else max(self.preview_search_index, 0)
        self.goto_preview_search_result()
        self.status_var.set(f"搜索完成：找到 {len(self.preview_search_matches)} 行匹配『{keyword}』。")

    def goto_preview_search_result(self):
        if not self.preview_search_matches:
            return
        self.preview_search_index %= len(self.preview_search_matches)
        current_iid = self.preview_search_matches[self.preview_search_index]
        for iid in self.preview_search_matches:
            self.preview_tree.item(iid, tags=("search_match",))
        self.preview_tree.item(current_iid, tags=("search_current",))
        self.preview_tree.selection_set(current_iid)
        self.preview_tree.focus(current_iid)
        self.preview_tree.see(current_iid)
        self.status_var.set(f"当前搜索结果：{self.preview_search_index + 1}/{len(self.preview_search_matches)}")

    def search_preview_next(self):
        if not self.preview_search_matches:
            self.search_preview_table(reset=True)
            return
        self.preview_search_index += 1
        self.goto_preview_search_result()

    def search_preview_prev(self):
        if not self.preview_search_matches:
            self.search_preview_table(reset=True)
            return
        self.preview_search_index -= 1
        self.goto_preview_search_result()

    def refresh_preview_table_choices(self, show_status=False):
        """Refresh the table picker for the result preview area."""
        choices = []
        mapping = {}

        def add_choice(label, key):
            display = label
            if display in mapping:
                n = 2
                while f"{display} ({n})" in mapping:
                    n += 1
                display = f"{display} ({n})"
            choices.append(display)
            mapping[display] = key

        add_choice("当前预览结果", ("preview", None))
        add_choice("主界面当前预览", ("main_preview", None))

        for name in sorted((self.current_transit_tables or {}).keys()):
            add_choice(f"中转:{name}", ("transit", name))

        try:
            for table in self.get_sqlite_table_names():
                add_choice(f"SQLite:{table}", ("sqlite", table))
        except Exception:
            pass

        self.preview_table_map = mapping
        if hasattr(self, "preview_table_combo"):
            self.preview_table_combo["values"] = choices
        current = self.preview_table_var.get()
        if not current or current not in mapping:
            self.preview_table_var.set("当前预览结果" if "当前预览结果" in mapping else (choices[0] if choices else ""))
        if show_status:
            self.status_var.set(f"已刷新结果预览可查看表：{len(choices)} 个。")
        return choices

    def read_sqlite_table_for_preview(self, table_name):
        """Read a SQLite table for quick display in the result preview area."""
        db_path = self.get_workflow_db_path(None)
        if not db_path or not os.path.exists(db_path):
            raise ValueError("当前 SQLite 数据库路径不存在。")
        data = TableAccessManager(db_path, node_type="结果预览").read_table(table_name)
        return list(data.get("headers", [])), [list(row) for row in data.get("rows", [])]

    def load_selected_preview_table(self):
        """Load the selected table into the workflow preview area."""
        msg = _window_messagebox(self)
        self.refresh_preview_table_choices(show_status=False)
        selected = self.preview_table_var.get()
        if not selected:
            msg.showwarning("提示", "请先选择要查看的表。")
            return
        key = self.preview_table_map.get(selected)
        if not key:
            msg.showwarning("提示", "选中的表不存在或已失效，请刷新后重试。")
            return
        kind, name = key
        try:
            if kind == "preview":
                headers, rows = self.get_plan_preview_result()
                label = "当前预览结果"
            elif kind == "main_preview":
                headers = list(self.app.headers)
                rows = [list(r) for r in self.app.rows]
                label = "主界面当前预览"
            elif kind == "transit":
                item = (self.current_transit_tables or {}).get(name)
                if item is None:
                    raise ValueError(f"中转副表不存在或尚未生成：{name}")
                headers = list(item.get("headers", []))
                rows = [list(r) for r in item.get("rows", [])]
                label = f"中转:{name}"
            elif kind == "sqlite":
                headers, rows = self.read_sqlite_table_for_preview(name)
                label = f"SQLite:{name}"
            else:
                raise ValueError(f"未知表类型：{kind}")

            self.preview_view_kind = kind
            self.preview_headers, self.preview_rows = headers, rows
            self.refresh_preview_tree(headers, rows)
            self.preview_table_var.set(selected)
            self.status_var.set(f"已载入表到结果预览：{label}，{len(rows)} 行 × {len(headers)} 列。当前预览结果已独立缓存，不会被临时查看表覆盖。")
        except Exception as e:
            msg.showerror("载入表失败", str(e))

    def export_preview_to_xlsx(self):
        """Export the currently displayed result preview table."""
        msg = _window_messagebox(self)
        headers = list(self.preview_headers or [])
        rows = [list(row) for row in (self.preview_rows or [])]
        if not headers:
            msg.showwarning("提示", "当前结果预览没有可导出的表格字段。")
            return
        table_name = self.preview_table_var.get().strip() or "计划预览结果"
        self.app.export_current_preview_to_xlsx(
            headers=headers,
            rows=rows,
            table_name=table_name,
            title="导出为 xlsx",
        )
