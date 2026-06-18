# -*- coding: utf-8 -*-
"""Initialization for the main clipboard table app window."""

import os
import sys
import tkinter as tk


def default_app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class ClipboardTableInitMixin:
    """Initializes ClipboardTableApp state before the UI is built."""

    def __init__(self, root):
        self.root = root
        self.root.title("剪贴板表格解析器 - SQLite保存版")
        self.root.geometry("1420x760")

        self.raw_data = ""
        self.headers = []
        self.rows = []

        self.edit_mode = False
        self.edit_entry = None

        self.search_var = tk.StringVar(value="")
        self.search_matches = []
        self.search_index = -1

        self.app_dir = default_app_dir()

        self.db_path_var = tk.StringVar(value=os.path.join(self.app_dir, "clipboard_tables.db"))
        self.table_name_var = tk.StringVar(value="paste_table")
        self.first_row_header_var = tk.BooleanVar(value=True)
        self.recreate_table_var = tk.BooleanVar(value=True)
        self.edit_btn_text = tk.StringVar(value="修改模式:关")

        self.build_ui()
