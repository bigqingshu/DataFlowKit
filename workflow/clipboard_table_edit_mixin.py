# -*- coding: utf-8 -*-
"""Main ClipboardTableApp cell editing helpers."""

import tkinter as tk
from tkinter import messagebox, ttk


class ClipboardTableEditMixin:
    """Compatibility methods for the main preview cell editor."""

    def toggle_edit_mode(self):
        self.edit_mode = not self.edit_mode

        if self.edit_mode:
            self.edit_btn_text.set("修改模式:开")
            self.info_var.set("修改模式已开启：双击预览表格中的单元格即可修改。")
        else:
            self.edit_btn_text.set("修改模式:关")
            self.info_var.set("修改模式已关闭。")

            if self.edit_entry is not None:
                self.edit_entry.destroy()
                self.edit_entry = None

    def _destroy_edit_entry(self):
        if self.edit_entry is not None:
            self.edit_entry.destroy()
            self.edit_entry = None

    def _get_edit_target(self, event):
        region = self.tree.identify("region", event.x, event.y)
        if region != "cell":
            return None

        row_id = self.tree.identify_row(event.y)
        col_id = self.tree.identify_column(event.x)
        if not row_id or not col_id:
            return None

        try:
            col_index = int(col_id.replace("#", "")) - 1
            row_index = self.tree.index(row_id)
        except Exception:
            return None

        if row_index < 0 or row_index >= len(self.rows):
            return None
        if col_index < 0 or col_index >= len(self.headers):
            return None

        bbox = self.tree.bbox(row_id, col_id)
        if not bbox:
            return None

        x, y, width, height = bbox
        old_value = ""
        if col_index < len(self.rows[row_index]):
            old_value = self.rows[row_index][col_index]

        return {
            "row_id": row_id,
            "col_id": col_id,
            "row_index": row_index,
            "col_index": col_index,
            "bbox": bbox,
            "old_value": old_value,
            "x": x,
            "y": y,
            "width": width,
            "height": height,
        }

    def _save_edit_value(self, row_index, col_index, row_id, new_value):
        while len(self.rows[row_index]) < len(self.headers):
            self.rows[row_index].append("")

        self.rows[row_index][col_index] = new_value

        values = list(self.tree.item(row_id, "values"))
        while len(values) < len(self.headers):
            values.append("")
        values[col_index] = new_value
        self.tree.item(row_id, values=values)
        self.info_var.set(f"已修改：第 {row_index + 1} 行，第 {col_index + 1} 列。")

    def on_tree_double_click(self, event):
        if not self.edit_mode:
            return

        target = self._get_edit_target(event)
        if not target:
            return

        self._destroy_edit_entry()

        entry = ttk.Entry(self.tree)
        entry.place(
            x=target["x"],
            y=target["y"],
            width=target["width"],
            height=target["height"],
        )
        entry.insert(0, target["old_value"])
        entry.select_range(0, tk.END)
        entry.focus()

        closed = {"done": False}

        def close_editor(save=True):
            if closed["done"]:
                return
            closed["done"] = True

            if save:
                self._save_edit_value(
                    target["row_index"],
                    target["col_index"],
                    target["row_id"],
                    entry.get(),
                )

            entry.destroy()
            self.edit_entry = None

        entry.bind("<Return>", lambda e: close_editor(save=True))
        entry.bind("<FocusOut>", lambda e: close_editor(save=True))
        entry.bind("<Escape>", lambda e: close_editor(save=False))

        self.edit_entry = entry
