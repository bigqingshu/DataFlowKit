# -*- coding: utf-8 -*-
"""Config area scrolling and reset helpers for workflow windows."""

import tkinter as tk
from tkinter import ttk


class WorkflowConfigAreaMixin:
    """Compatibility methods for the node configuration area."""

    def _on_config_frame_configure(self, event=None):
        """更新节点配置区滚动范围。"""
        if hasattr(self, "config_canvas"):
            self.config_canvas.configure(scrollregion=self.config_canvas.bbox("all"))

    def _on_config_canvas_configure(self, event=None):
        """让内部配置区域宽度跟随 Canvas，减少横向截断。"""
        if hasattr(self, "config_canvas") and hasattr(self, "config_canvas_window"):
            try:
                self.config_canvas.itemconfigure(self.config_canvas_window, width=event.width)
            except Exception:
                pass

    def _bind_config_mousewheel(self, event=None):
        if hasattr(self, "config_canvas"):
            self.config_canvas.bind_all("<MouseWheel>", self._on_config_mousewheel)
            self.config_canvas.bind_all("<Shift-MouseWheel>", self._on_config_shift_mousewheel)

    def _unbind_config_mousewheel(self, event=None):
        if hasattr(self, "config_canvas"):
            self.config_canvas.unbind_all("<MouseWheel>")
            self.config_canvas.unbind_all("<Shift-MouseWheel>")

    def _on_config_mousewheel(self, event):
        if hasattr(self, "config_canvas"):
            self.config_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _on_config_shift_mousewheel(self, event):
        if hasattr(self, "config_canvas"):
            self.config_canvas.xview_scroll(int(-1 * (event.delta / 120)), "units")

    def show_empty_config(self):
        self.clear_config_frame()
        ttk.Label(
            self.config_frame,
            text="请先添加并选择一个节点。每个节点会接收上一步结果，并输出给下一步。",
            foreground="gray",
        ).pack(anchor=tk.W)

    def clear_config_frame(self):
        for child in self.config_frame.winfo_children():
            child.destroy()
        self.current_config_widgets = {}
        self.separator_widgets = []
        self.field_listbox = None
        if hasattr(self, "config_canvas"):
            self.config_canvas.yview_moveto(0)
            self.config_canvas.xview_moveto(0)
            self.config_canvas.after_idle(
                lambda: self.config_canvas.configure(scrollregion=self.config_canvas.bbox("all"))
            )
