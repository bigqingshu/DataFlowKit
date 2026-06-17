# -*- coding: utf-8 -*-
"""
剪贴板表格解析器 - SQLite保存版 + 高级筛选/数据匹配窗口

功能概览：
1. 从 Windows 剪贴板读取 Excel/WPS/网页表格数据。
2. 在 Tkinter GUI 中预览、编辑、保存到 SQLite。
3. 下拉选择 SQLite 表后，可自动加载数据库表数据。
4. 新增“高级筛选 / 数据匹配”窗口：
   - 支持选择一个或多个 SQLite 表作为数据源。
   - 支持多条件筛选：等于、不等于、包含、大于、小于、为空等。
   - 支持多表匹配规则：字段相等、字段包含等。
   - 支持选择输出字段。
   - 支持预览筛选结果。
   - 支持保存筛选结果为新表。
   - 支持保存/载入筛选模板 JSON。
5. 新增“批量替换 / 数据处理”窗口：
   - 支持按字段进行局部字符串替换或整格替换。
   - 支持替换前预览、执行替换、撤销上一次替换。
   - 支持保存/载入替换规则模板 JSON。
6. 新增主界面“导出为 xlsx”按钮，可导出当前预览数据。
7. 新增“数据提取 / 字段生成”窗口：
   - 支持 Python 正则提取、固定位置提取、按分隔符提取、关键字之间提取等。
   - 支持预览、执行、撤销、生成新字段、覆盖源字段、保存/载入规则模板。
8. 新增“合并列 / 生成新列”窗口：
   - 支持从字段池添加字段到合并顺序列表。
   - 支持上移、下移、删除、清空字段顺序。
   - 支持每两列之间设置不同连接符，也支持自定义连接符和 {换行符}/{制表符} 等特殊占位符。
   - 支持预览、执行、撤销、保存/载入合并模板。
9. 新增“计划 / 工作流处理”窗口：
   - 支持把批量替换、数据提取、合并列、高级筛选、删除列、移动列组成顺序节点。
   - 上一步输出可直接作为下一步输入。
   - 支持预览到当前节点、预览完整计划、输出到主界面、保存/覆盖SQLite表、导出xlsx。
10. 新增文件工作流节点：获取文件列表、批量重命名，可与数据提取/替换/合并列组合生成新文件名。
11. 新增表格编辑类工作流节点：复制列、复制行、删除行、填充值、序列填充、区域填充。
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
import sqlite3
import csv
import io
import re
import os
import sys
import json
import traceback
import queue
import time
import uuid
from datetime import datetime

from core.text_utils import (
    make_sql_columns as core_make_sql_columns,
    quote_ident as core_quote_ident,
    sanitize_sql_name as core_sanitize_sql_name,
)
from db import PluginDatabaseAPI, TableAccessManager
from plugin_runtime.scanner import scan_plugins
from shared.atomic_json_utils import atomic_write_json, load_json_with_backup
from workflow.default_configs import default_config_for_type as workflow_default_config_for_type
from workflow.advanced_filter_window import AdvancedFilterWindow
from workflow.batch_replace_window import BatchReplaceWindow
from workflow.data_extract_window import DataExtractWindow
from workflow.merge_columns_window import MergeColumnsWindow
from workflow.filter_config_window_mixin import FilterConfigWindowMixin
from workflow.group_config_window_mixin import GroupConfigWindowMixin
from workflow.plan_preview_mixin import PlanPreviewMixin
from workflow.plan_workflow_window_mixin import PlanWorkflowUiMixin
from workflow.plugin_config_window_mixin import PluginConfigWindowMixin
from workflow.table_access_window_mixin import TableAccessWindowMixin
from workflow.workflow_execution_mixin import WorkflowExecutionMixin
from workflow.workflow_node_execution_mixin import WorkflowNodeExecutionMixin
from workflow import group_template_ui as workflow_group_template_ui
from workflow.workflow_config_builder_mixin import WorkflowConfigBuilderMixin
from workflow.workflow_control_runtime_mixin import WorkflowControlRuntimeMixin
from workflow.workflow_data_runtime_mixin import WorkflowDataRuntimeMixin
from workflow.workflow_jump_mixin import WorkflowJumpMixin
from workflow.workflow_output_runtime_mixin import WorkflowOutputRuntimeMixin
from workflow.workflow_plugin_runtime_mixin import WorkflowPluginRuntimeMixin
from workflow.workflow_table_runtime_mixin import WorkflowTableRuntimeMixin


def get_app_dir():
    """
    返回程序真实工作目录。

    - 直接运行 .py：使用 .py 文件所在目录。
    - PyInstaller 打包为 exe 后：使用 exe 所在目录。

    这样 plan / logs / export / 默认数据库等目录不会被创建到
    PyInstaller 单文件模式的 C 盘临时解压目录 _MEIxxxxx 中。
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def load_json_file_with_recovery(path, parent=None):
    data, info = load_json_with_backup(path)
    warning = info.get("warning", "")
    if warning:
        messagebox.showwarning("配置已从备份恢复", warning, parent=parent)
    return data





class ClipboardTableApp:
    def __init__(self, root):
        self.root = root
        self.root.title("剪贴板表格解析器 - SQLite保存版")
        self.root.geometry("1420x760")

        self.raw_data = ""
        self.headers = []
        self.rows = []

        self.edit_mode = False
        self.edit_entry = None

        # 主界面搜索状态
        self.search_var = tk.StringVar(value="")
        self.search_matches = []
        self.search_index = -1

        # 程序真实目录：兼容直接运行 .py 和 PyInstaller 单文件 exe。
        # 所有需要长期保留的文件都应基于此目录，避免写到 _MEI 临时目录。
        self.app_dir = get_app_dir()

        self.db_path_var = tk.StringVar(value=os.path.join(self.app_dir, "clipboard_tables.db"))
        self.table_name_var = tk.StringVar(value="paste_table")
        self.first_row_header_var = tk.BooleanVar(value=True)
        self.recreate_table_var = tk.BooleanVar(value=True)
        self.edit_btn_text = tk.StringVar(value="修改模式:关")

        self.build_ui()

    def build_ui(self):
        top_frame = ttk.Frame(self.root, padding=8)
        top_frame.pack(fill=tk.X)

        ttk.Button(
            top_frame,
            text="读取剪贴板并解析",
            command=self.load_clipboard
        ).pack(side=tk.LEFT, padx=4)

        ttk.Button(
            top_frame,
            text="清空预览",
            command=self.clear_preview
        ).pack(side=tk.LEFT, padx=4)

        ttk.Button(
            top_frame,
            text="删除字段名，并用下一行作为字段名",
            command=self.delete_header_and_promote_next_row
        ).pack(side=tk.LEFT, padx=4)

        ttk.Button(
            top_frame,
            textvariable=self.edit_btn_text,
            command=self.toggle_edit_mode
        ).pack(side=tk.LEFT, padx=4)

        ttk.Button(
            top_frame,
            text="计划 / 工作流处理",
            command=self.open_plan_workflow
        ).pack(side=tk.LEFT, padx=4)

        ttk.Button(
            top_frame,
            text="批量替换 / 数据处理",
            command=self.open_batch_replace
        ).pack(side=tk.LEFT, padx=4)

        ttk.Button(
            top_frame,
            text="数据提取 / 字段生成",
            command=self.open_data_extract
        ).pack(side=tk.LEFT, padx=4)

        ttk.Button(
            top_frame,
            text="合并列 / 生成新列",
            command=self.open_merge_columns
        ).pack(side=tk.LEFT, padx=4)

        ttk.Button(
            top_frame,
            text="高级筛选 / 数据匹配",
            command=self.open_advanced_filter
        ).pack(side=tk.LEFT, padx=4)

        ttk.Button(
            top_frame,
            text="导出为 xlsx",
            command=self.export_current_preview_to_xlsx
        ).pack(side=tk.LEFT, padx=4)

        ttk.Button(
            top_frame,
            text="保存到 SQLite",
            command=self.save_to_sqlite
        ).pack(side=tk.LEFT, padx=4)

        ttk.Button(
            top_frame,
            text="删除当前表",
            command=self.delete_current_sqlite_table
        ).pack(side=tk.LEFT, padx=4)

        ttk.Separator(self.root, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=4)

        # 主界面选项区拆成独立行，避免不同 row 共用同一个 grid 列宽互相影响。
        # 之前搜索按钮通过较大的 padx 放在 option_frame 的 column=1，
        # 会把数据库路径输入框所在列撑宽，导致“选择 / 刷新表名”整体右移。
        option_frame = ttk.Frame(self.root, padding=8)
        option_frame.pack(fill=tk.X)

        # 第1行：数据库路径设置
        db_frame = ttk.Frame(option_frame)
        db_frame.pack(fill=tk.X, anchor=tk.W)

        ttk.Label(db_frame, text="数据库：").pack(side=tk.LEFT, padx=(4, 4))

        ttk.Entry(
            db_frame,
            textvariable=self.db_path_var,
            width=80
        ).pack(side=tk.LEFT, padx=(4, 4))

        ttk.Button(
            db_frame,
            text="选择",
            command=self.choose_db
        ).pack(side=tk.LEFT, padx=(4, 4))

        ttk.Button(
            db_frame,
            text="刷新表名",
            command=self.refresh_table_list
        ).pack(side=tk.LEFT, padx=(4, 4))

        # 第2行：表名与保存选项
        table_option_frame = ttk.Frame(option_frame)
        table_option_frame.pack(fill=tk.X, anchor=tk.W, pady=(6, 0))

        ttk.Label(table_option_frame, text="表名：").pack(side=tk.LEFT, padx=(4, 4))

        self.table_combo = ttk.Combobox(
            table_option_frame,
            textvariable=self.table_name_var,
            width=32,
            state="normal"
        )
        self.table_combo.pack(side=tk.LEFT, padx=(4, 18))

        self.table_combo.configure(postcommand=self.refresh_table_list)
        self.table_combo.bind("<<ComboboxSelected>>", self.on_table_selected)

        ttk.Checkbutton(
            table_option_frame,
            text="第一行作为字段名",
            variable=self.first_row_header_var,
            command=self.reparse_current_raw
        ).pack(side=tk.LEFT, padx=(12, 12))

        ttk.Checkbutton(
            table_option_frame,
            text="保存时重建同名表",
            variable=self.recreate_table_var
        ).pack(side=tk.LEFT, padx=(12, 12))

        # 第3行：搜索区。搜索按钮保留你指定的 padx=330，但只影响 search_frame 自身，
        # 不再影响上方数据库行和表名行的布局。
        search_frame = ttk.Frame(option_frame)
        search_frame.pack(fill=tk.X, anchor=tk.W, pady=(6, 0))

        ttk.Label(search_frame, text="搜索：").grid(row=0, column=0, sticky=tk.W, padx=(4, 4), pady=4)
        search_entry = ttk.Entry(search_frame, textvariable=self.search_var, width=38)
        search_entry.grid(row=0, column=1, sticky=tk.W, padx=(4, 4), pady=4)
        search_entry.bind("<Return>", lambda e: self.search_main_preview(reset=True))
        ttk.Button(search_frame, text="搜索", command=lambda: self.search_main_preview(reset=True)).grid(row=0, column=2, sticky=tk.W, padx=(12, 8), pady=4)
        ttk.Button(search_frame, text="上一个", command=self.search_main_prev).grid(row=0, column=3, sticky=tk.W, padx=(12, 8), pady=4)
        ttk.Button(search_frame, text="下一个", command=self.search_main_next).grid(row=0, column=4, sticky=tk.W, padx=(12, 8), pady=4)

        self.info_var = tk.StringVar(value="等待读取剪贴板数据。")
        ttk.Label(self.root, textvariable=self.info_var, padding=8).pack(fill=tk.X)

        table_frame = ttk.Frame(self.root)
        table_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        self.tree = ttk.Treeview(table_frame, show="headings")

        y_scroll = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.tree.yview)
        x_scroll = ttk.Scrollbar(table_frame, orient=tk.HORIZONTAL, command=self.tree.xview)

        self.tree.configure(
            yscrollcommand=y_scroll.set,
            xscrollcommand=x_scroll.set
        )

        self.tree.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")

        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)

        self.tree.bind("<Double-1>", self.on_tree_double_click)

        # 程序启动时尝试刷新表名
        self.refresh_table_list()

    def open_plan_workflow(self):
        if not self.headers:
            messagebox.showwarning("提示", "当前没有可处理的数据，请先读取剪贴板或加载数据库表。")
            return

        PlanWorkflowWindow(self)

    def open_advanced_filter(self):
        db_path = self.db_path_var.get().strip()
        if not db_path:
            messagebox.showwarning("提示", "请先设置 SQLite 数据库路径。")
            return

        if not os.path.exists(db_path):
            messagebox.showwarning("提示", "当前 SQLite 数据库不存在，请先保存数据或选择已有数据库。")
            return

        AdvancedFilterWindow(self)


    def open_batch_replace(self):
        if not self.headers:
            messagebox.showwarning("提示", "当前没有可处理的数据，请先读取剪贴板或加载数据库表。")
            return

        BatchReplaceWindow(self)

    def open_data_extract(self):
        if not self.headers:
            messagebox.showwarning("提示", "当前没有可处理的数据，请先读取剪贴板或加载数据库表。")
            return

        DataExtractWindow(self)

    def open_merge_columns(self):
        if not self.headers:
            messagebox.showwarning("提示", "当前没有可处理的数据，请先读取剪贴板或加载数据库表。")
            return

        MergeColumnsWindow(self)

    def normalize_sheet_title(self, name):
        name = str(name or "导出数据").strip() or "导出数据"
        name = re.sub(r"[\\/*?:\[\]]", "_", name)
        return name[:31] or "导出数据"

    def column_letter(self, index):
        result = ""
        while index > 0:
            index, rem = divmod(index - 1, 26)
            result = chr(65 + rem) + result
        return result or "A"

    def calc_display_width(self, value):
        text = str(value or "")
        width = 0
        for ch in text:
            width += 2 if ord(ch) > 127 else 1
        return width

    def export_current_preview_to_xlsx(self, headers=None, rows=None, table_name=None, title="导出为 xlsx"):
        headers = list(self.headers if headers is None else headers)
        rows = [list(row) for row in (self.rows if rows is None else rows)]
        table_name = self.table_name_var.get() if table_name is None else table_name

        if not headers:
            messagebox.showwarning("提示", "当前没有可导出的表格字段。")
            return

        default_base = self.sanitize_sql_name(table_name, "导出数据")
        default_name = f"{default_base}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        path = filedialog.asksaveasfilename(
            title=title,
            defaultextension=".xlsx",
            initialfile=default_name,
            filetypes=[("Excel 工作簿", "*.xlsx"), ("所有文件", "*.*")]
        )

        if not path:
            return

        if not path.lower().endswith(".xlsx"):
            path += ".xlsx"

        try:
            try:
                self.export_xlsx_with_openpyxl(path, headers=headers, rows=rows, table_name=table_name)
                engine = "openpyxl"
            except ModuleNotFoundError:
                self.export_xlsx_minimal(path, headers=headers, rows=rows, table_name=table_name)
                engine = "内置简易导出器"

            self.info_var.set(f"导出成功：{path}")
            messagebox.showinfo(
                "导出成功",
                f"已导出当前预览数据。\n\n文件：{path}\n行数：{len(rows)}\n列数：{len(headers)}\n导出方式：{engine}"
            )
        except Exception as e:
            messagebox.showerror("导出失败", str(e))

    def export_xlsx_with_openpyxl(self, path, headers=None, rows=None, table_name=None):
        from openpyxl import Workbook
        from openpyxl.styles import Font, Alignment, PatternFill, Border, Side

        headers = [str(h) for h in (self.headers if headers is None else headers)]
        rows = [list(row) for row in (self.rows if rows is None else rows)]
        table_name = self.table_name_var.get() if table_name is None else table_name

        wb = Workbook()
        ws = wb.active
        ws.title = self.normalize_sheet_title(table_name)

        ws.append(headers)

        for row in rows:
            fixed = list(row)
            if len(fixed) < len(headers):
                fixed += [""] * (len(headers) - len(fixed))
            if len(fixed) > len(headers):
                fixed = fixed[:len(headers)]
            ws.append(["" if value is None else str(value) for value in fixed])

        header_fill = PatternFill("solid", fgColor="D9EAF7")
        thin = Side(style="thin", color="CCCCCC")
        border = Border(left=thin, right=thin, top=thin, bottom=thin)

        for cell in ws[1]:
            cell.font = Font(bold=True)
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.border = border

        for row_cells in ws.iter_rows(min_row=2):
            for cell in row_cells:
                cell.alignment = Alignment(vertical="center")
                cell.border = border

        ws.freeze_panes = "A2"
        if headers:
            last_col = self.column_letter(len(headers))
            ws.auto_filter.ref = f"A1:{last_col}{max(len(rows) + 1, 1)}"

        for col_idx, header in enumerate(headers, start=1):
            max_width = self.calc_display_width(header)
            for row in rows[:3000]:
                if col_idx - 1 < len(row):
                    max_width = max(max_width, self.calc_display_width(row[col_idx - 1]))
            ws.column_dimensions[self.column_letter(col_idx)].width = min(max(max_width + 2, 10), 40)

        wb.save(path)

    def export_xlsx_minimal(self, path, headers=None, rows=None, table_name=None):
        import zipfile
        from xml.sax.saxutils import escape

        headers = [str(h) for h in (self.headers if headers is None else headers)]
        rows = [list(row) for row in (self.rows if rows is None else rows)]
        sheet_rows = [headers]
        for row in rows:
            fixed = list(row)
            if len(fixed) < len(headers):
                fixed += [""] * (len(headers) - len(fixed))
            if len(fixed) > len(headers):
                fixed = fixed[:len(headers)]
            sheet_rows.append(["" if value is None else str(value) for value in fixed])

        def cell_xml(row_idx, col_idx, value, style_id="0"):
            ref = f"{self.column_letter(col_idx)}{row_idx}"
            value = escape(str(value))
            return f'<c r="{ref}" t="inlineStr" s="{style_id}"><is><t>{value}</t></is></c>'

        col_xml = []
        for col_idx, header in enumerate(headers, start=1):
            max_width = self.calc_display_width(header)
            for row in rows[:3000]:
                if col_idx - 1 < len(row):
                    max_width = max(max_width, self.calc_display_width(row[col_idx - 1]))
            width = min(max(max_width + 2, 10), 40)
            col_xml.append(f'<col min="{col_idx}" max="{col_idx}" width="{width}" customWidth="1"/>')

        row_xml_list = []
        for r_idx, row in enumerate(sheet_rows, start=1):
            style_id = "1" if r_idx == 1 else "0"
            cells = "".join(cell_xml(r_idx, c_idx, value, style_id) for c_idx, value in enumerate(row, start=1))
            row_xml_list.append(f'<row r="{r_idx}">{cells}</row>')

        last_col = self.column_letter(len(headers) if headers else 1)
        last_row = max(len(sheet_rows), 1)
        auto_filter = f'<autoFilter ref="A1:{last_col}{last_row}"/>' if headers else ""

        sheet_xml = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheetViews>
    <sheetView workbookViewId="0">
      <pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>
      <selection pane="bottomLeft"/>
    </sheetView>
  </sheetViews>
  <cols>{''.join(col_xml)}</cols>
  <sheetData>{''.join(row_xml_list)}</sheetData>
  {auto_filter}
</worksheet>'''

        styles_xml = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/></font></fonts>
  <fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FFD9EAF7"/></patternFill></fill></fills>
  <borders count="2"><border/><border><left style="thin"><color rgb="FFCCCCCC"/></left><right style="thin"><color rgb="FFCCCCCC"/></right><top style="thin"><color rgb="FFCCCCCC"/></top><bottom style="thin"><color rgb="FFCCCCCC"/></bottom></border></borders>
  <cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
  <cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1"/><xf numFmtId="0" fontId="1" fillId="2" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1"/></cellXfs>
</styleSheet>'''

        content_types = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>'''

        rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>'''

        workbook_xml = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets><sheet name="{escape(self.normalize_sheet_title(self.table_name_var.get()))}" sheetId="1" r:id="rId1"/></sheets>
</workbook>'''

        workbook_rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>'''

        now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        core_xml = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:creator>ClipboardTableTool</dc:creator><cp:lastModifiedBy>ClipboardTableTool</cp:lastModifiedBy><dcterms:created xsi:type="dcterms:W3CDTF">{now}</dcterms:created><dcterms:modified xsi:type="dcterms:W3CDTF">{now}</dcterms:modified>
</cp:coreProperties>'''

        app_xml = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"><Application>ClipboardTableTool</Application></Properties>'''

        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("[Content_Types].xml", content_types)
            zf.writestr("_rels/.rels", rels)
            zf.writestr("xl/workbook.xml", workbook_xml)
            zf.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
            zf.writestr("xl/worksheets/sheet1.xml", sheet_xml)
            zf.writestr("xl/styles.xml", styles_xml)
            zf.writestr("docProps/core.xml", core_xml)
            zf.writestr("docProps/app.xml", app_xml)

    def choose_db(self):
        path = filedialog.asksaveasfilename(
            title="选择 SQLite 数据库",
            defaultextension=".db",
            filetypes=[
                ("SQLite 数据库", "*.db"),
                ("SQLite 数据库", "*.sqlite"),
                ("所有文件", "*.*")
            ]
        )
        if path:
            self.db_path_var.set(path)
            self.refresh_table_list()

    def get_db_path(self):
        return self.db_path_var.get().strip()

    def get_table_names(self):
        db_path = self.get_db_path()

        if not db_path or not os.path.exists(db_path):
            return []
        return TableAccessManager(db_path, node_type="主界面").list_tables()

    def get_table_columns(self, table_name):
        db_path = self.get_db_path()

        return TableAccessManager(db_path, node_type="主界面").get_columns(table_name)

    def refresh_table_list(self):
        try:
            tables = self.get_table_names()
            self.table_combo["values"] = tables

            if tables:
                self.info_var.set(f"已读取当前数据库表：{len(tables)} 个。")
            else:
                self.info_var.set("当前数据库中没有普通数据表。")
        except Exception as e:
            self.table_combo["values"] = []
            self.info_var.set(f"读取数据库表失败：{e}")

    def on_table_selected(self, event=None):
        table_name = self.table_name_var.get().strip()

        if not table_name:
            return

        self.load_table_from_sqlite(table_name)

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

    def on_tree_double_click(self, event):
        if not self.edit_mode:
            return

        region = self.tree.identify("region", event.x, event.y)
        if region != "cell":
            return

        row_id = self.tree.identify_row(event.y)
        col_id = self.tree.identify_column(event.x)

        if not row_id or not col_id:
            return

        try:
            col_index = int(col_id.replace("#", "")) - 1
            row_index = self.tree.index(row_id)
        except Exception:
            return

        if row_index < 0 or row_index >= len(self.rows):
            return

        if col_index < 0 or col_index >= len(self.headers):
            return

        bbox = self.tree.bbox(row_id, col_id)
        if not bbox:
            return

        x, y, width, height = bbox

        old_value = ""
        if col_index < len(self.rows[row_index]):
            old_value = self.rows[row_index][col_index]

        if self.edit_entry is not None:
            self.edit_entry.destroy()
            self.edit_entry = None

        entry = ttk.Entry(self.tree)
        entry.place(x=x, y=y, width=width, height=height)
        entry.insert(0, old_value)
        entry.select_range(0, tk.END)
        entry.focus()

        closed = {"done": False}

        def close_editor(save=True):
            if closed["done"]:
                return

            closed["done"] = True

            if save:
                new_value = entry.get()

                while len(self.rows[row_index]) < len(self.headers):
                    self.rows[row_index].append("")

                self.rows[row_index][col_index] = new_value

                values = list(self.tree.item(row_id, "values"))

                while len(values) < len(self.headers):
                    values.append("")

                values[col_index] = new_value
                self.tree.item(row_id, values=values)

                self.info_var.set(f"已修改：第 {row_index + 1} 行，第 {col_index + 1} 列。")

            entry.destroy()
            self.edit_entry = None

        entry.bind("<Return>", lambda e: close_editor(save=True))
        entry.bind("<FocusOut>", lambda e: close_editor(save=True))
        entry.bind("<Escape>", lambda e: close_editor(save=False))

        self.edit_entry = entry

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

    def sanitize_sql_name(self, name, default_name):
        return core_sanitize_sql_name(name, default_name)

    def make_sql_columns(self, headers):
        return core_make_sql_columns(headers)

    def quote_ident(self, name):
        return core_quote_ident(name)

    def table_exists(self, conn, table_name):
        cur = conn.cursor()
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,)
        )
        return cur.fetchone() is not None

    def get_available_table_name(self, conn, base_name):
        if not self.table_exists(conn, base_name):
            return base_name

        suffix = datetime.now().strftime("%Y%m%d_%H%M%S")
        new_name = f"{base_name}_{suffix}"

        counter = 2
        while self.table_exists(conn, new_name):
            new_name = f"{base_name}_{suffix}_{counter}"
            counter += 1

        return new_name

    def format_db_value(self, value):
        if value is None:
            return ""

        if isinstance(value, bytes):
            return f"<BLOB {len(value)} bytes>"

        return str(value)

    def load_table_from_sqlite(self, table_name):
        db_path = self.db_path_var.get().strip()

        if not db_path:
            messagebox.showwarning("提示", "请先选择 SQLite 数据库。")
            return

        if not os.path.exists(db_path):
            messagebox.showwarning("提示", "当前数据库文件不存在。")
            return

        try:
            manager = TableAccessManager(db_path, node_type="主界面读取")
            if not manager.table_exists(table_name):
                messagebox.showwarning("提示", f"表不存在：{table_name}")
                return

            data = manager.read_table(table_name)
            headers = list(data.get("headers", []))

            if not headers:
                messagebox.showwarning("提示", f"表没有字段：{table_name}")
                return

            if self.edit_entry is not None:
                self.edit_entry.destroy()
                self.edit_entry = None

            self.raw_data = ""

            self.headers = self.make_display_headers(headers)
            self.rows = [list(row) for row in data.get("rows", [])]

            self.refresh_tree()

            self.info_var.set(
                f"已加载数据库表：{table_name}，"
                f"{len(self.rows)} 行 × {len(self.headers)} 列。"
            )

        except Exception as e:
            messagebox.showerror("读取表失败", str(e))

    def save_rows_to_sqlite_table(self, table_name_raw, headers, rows, recreate=True):
        db_path = self.get_db_path()
        if not db_path:
            raise ValueError("数据库路径为空。")

        table_name = self.sanitize_sql_name(table_name_raw, "result_table")
        sql_columns = self.make_sql_columns(headers)

        normalized_rows = []
        for row in rows:
            fixed_row = list(row)
            if len(fixed_row) < len(sql_columns):
                fixed_row += [""] * (len(sql_columns) - len(fixed_row))
            if len(fixed_row) > len(sql_columns):
                fixed_row = fixed_row[:len(sql_columns)]
            normalized_rows.append(fixed_row)

        mode = "replace" if recreate else "timestamp"
        info = TableAccessManager(db_path, node_type="主界面保存").write_table(
            table_name,
            sql_columns,
            normalized_rows,
            mode=mode,
        )
        self.refresh_table_list()

        return info.get("table_name", table_name), len(normalized_rows)

    def save_to_sqlite(self):
        if not self.headers or not self.rows:
            messagebox.showwarning("提示", "当前没有可保存的数据，请先读取剪贴板。")
            return

        db_path = self.db_path_var.get().strip()
        if not db_path:
            messagebox.showwarning("提示", "请填写 SQLite 数据库路径。")
            return

        table_name_raw = self.table_name_var.get().strip()

        try:
            table_name, row_count = self.save_rows_to_sqlite_table(
                table_name_raw=table_name_raw,
                headers=self.headers,
                rows=self.rows,
                recreate=self.recreate_table_var.get()
            )

            self.info_var.set(
                f"保存成功：数据库 {db_path}，表 {table_name}，共 {row_count} 行。"
            )

            messagebox.showinfo(
                "保存成功",
                f"已保存到 SQLite。\n\n数据库：{db_path}\n表名：{table_name}\n行数：{row_count}"
            )

        except Exception as e:
            messagebox.showerror("保存失败", str(e))

    def make_table_backup_name(self, conn, table_name):
        """生成当前 SQLite 表的备份表名，避免覆盖已有备份。"""
        base_name = f"{table_name}_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        backup_name = base_name
        counter = 2
        while self.table_exists(conn, backup_name):
            backup_name = f"{base_name}_{counter}"
            counter += 1
        return backup_name

    def backup_sqlite_table_before_delete(self, conn, table_name):
        """删除前复制当前表到同库备份表，返回备份表名。"""
        backup_name = self.make_table_backup_name(conn, table_name)
        conn.execute(
            f"CREATE TABLE {self.quote_ident(backup_name)} AS "
            f"SELECT * FROM {self.quote_ident(table_name)}"
        )
        return backup_name

    def delete_current_sqlite_table(self):
        """主页删除当前下拉框选中的 SQLite 表。

        安全规则：
        1. 必须先开启修改模式。
        2. 只允许删除当前数据库中已存在、且当前下拉框选中的普通表。
        3. 删除前询问是否备份，备份失败则不删除。
        4. 删除前进行二次确认。
        """
        if not self.edit_mode:
            messagebox.showwarning(
                "禁止删除",
                "删除 SQLite 表属于高风险操作。\n\n请先开启“修改模式:开”，再点击“删除当前表”。"
            )
            return

        db_path = self.get_db_path()
        if not db_path:
            messagebox.showwarning("提示", "请先选择 SQLite 数据库。")
            return

        if not os.path.exists(db_path):
            messagebox.showwarning("提示", "当前 SQLite 数据库文件不存在。")
            return

        table_name = self.table_name_var.get().strip()
        if not table_name:
            messagebox.showwarning("提示", "请先在“表名”下拉框选择要删除的 SQLite 表。")
            return

        try:
            tables = self.get_table_names()
        except Exception as e:
            messagebox.showerror("读取表失败", str(e))
            return

        if table_name not in tables:
            messagebox.showwarning(
                "禁止删除",
                "只能删除当前 SQLite 数据库中已存在、并且从表名下拉框选中的普通表。\n\n"
                f"当前表名：{table_name}"
            )
            return

        if table_name.lower().startswith("sqlite_"):
            messagebox.showwarning("禁止删除", "不能删除 SQLite 系统内部表。")
            return

        backup_choice = messagebox.askyesnocancel(
            "删除当前表",
            "即将删除当前 SQLite 表：\n\n"
            f"数据库：{db_path}\n"
            f"表名：{table_name}\n\n"
            "是否先备份后删除？\n\n"
            "是：先复制为备份表，再删除当前表。\n"
            "否：不备份，直接删除当前表。\n"
            "取消：放弃删除。"
        )

        if backup_choice is None:
            self.info_var.set("已取消删除当前表。")
            return

        confirm_text = (
            "请再次确认删除操作。\n\n"
            f"将删除 SQLite 表：{table_name}\n"
        )
        if backup_choice:
            confirm_text += "删除前会先在当前数据库中创建备份表。\n\n"
        else:
            confirm_text += "本次选择不备份，删除后只能依靠你自己的数据库备份恢复。\n\n"
        confirm_text += "确认继续删除吗？"

        if not messagebox.askyesno("二次确认删除", confirm_text):
            self.info_var.set("已取消删除当前表。")
            return

        try:
            backup_name = TableAccessManager(db_path, node_type="主界面删除").drop_table(
                table_name,
                backup=bool(backup_choice),
            )

            self.refresh_table_list()

            if backup_name:
                self.table_name_var.set(backup_name)
                try:
                    self.load_table_from_sqlite(backup_name)
                except Exception:
                    self.clear_preview()
                msg = f"已备份并删除当前表。备份表：{backup_name}"
            else:
                self.table_name_var.set("")
                self.clear_preview()
                msg = f"已删除当前表：{table_name}"

            self.info_var.set(msg)
            messagebox.showinfo(
                "删除完成",
                f"已删除 SQLite 表：{table_name}"
                + (f"\n\n备份表：{backup_name}" if backup_name else "\n\n本次未创建备份表。")
            )

        except Exception as e:
            messagebox.showerror("删除失败", str(e))
            self.info_var.set(f"删除失败：{e}")



class PlanWorkflowWindow(
    PlanWorkflowUiMixin,
    PlanPreviewMixin,
    WorkflowConfigBuilderMixin,
    WorkflowJumpMixin,
    WorkflowDataRuntimeMixin,
    WorkflowControlRuntimeMixin,
    WorkflowPluginRuntimeMixin,
    WorkflowTableRuntimeMixin,
    WorkflowOutputRuntimeMixin,
    PluginConfigWindowMixin,
    FilterConfigWindowMixin,
    GroupConfigWindowMixin,
    TableAccessWindowMixin,
    WorkflowExecutionMixin,
    WorkflowNodeExecutionMixin,
):
    """
    计划 / 工作流处理窗口。

    设计目标：
    1. 把批量替换、数据提取、合并列、高级筛选、删除列、移动列作为节点串联。
    2. 每个节点都接收 headers / rows，输出新的 headers / rows。
    3. 支持预览到当前节点、预览完整计划、输出到主界面或保存到 SQLite。

    说明：
    - 计划内的“高级筛选”支持以上一步结果作为“当前表”，再选择数据库中的其他表进行多表匹配。
    """

    NODE_TYPES = ["获取文件列表", "节点组 / 子工作流", "循环执行起点", "跳转锚点节点", "无条件跳转节点", "条件判断节点", "条件跳转节点", "批量替换", "数据提取", "格式规范化 / 日期时间解析", "新建日期时间列", "新建列", "合并列", "批量更改列名", "去重 / 重复数据处理", "列数字运算", "匹配值输出列名", "复制列", "复制行", "删除行", "填充值", "序列填充", "区域填充", "行数据映射填充", "保存中转数据", "选定列写入指定表", "字段映射写入表", "高级筛选", "删除列", "移动列", "批量重命名", "循环判断回跳"]
    TABLE_ACCESS_POLICY_CHOICES = ["只审计", "预检确认", "强制拦截"]
    MAX_EXPANDED_ROWS = 200000
    MAX_TARGET_CELLS = 1000000
    TABLE_ACCESS_POLICY_DISPLAY = {
        "audit": "只审计",
        "prompt": "预检确认",
        "strict": "强制拦截",
        "off": "关闭",
    }
    STANDARD_WRITE_MODE_CHOICES = [
        "",
        "current_table_default",
        "create_new",
        "append",
        "overlay_by_order",
        "update_by_key",
        "upsert_by_key",
        "clear_keep_schema",
        "keep_schema_insert",
        "replace_table",
        "timestamp_new",
        "fail_if_exists",
        "write_fields_only",
        "fill_blank_fields",
    ]
    LOGIC_TYPES = ["AND", "OR"]
    FILTER_OPS = ["等于", "不等于", "包含", "不包含", "开头是", "结尾是", "大于", "小于", "大于等于", "小于等于", "为空", "不为空", "正则匹配"]
    FILTER_VALUE_SOURCES = ["固定值", "字段值"]
    REPLACE_MATCH_MODES = ["包含", "完全相等", "开头是", "结尾是", "正则匹配", "为空", "不为空"]
    REPLACE_MODES = ["局部替换匹配字符串", "整格替换为新值"]
    REPLACE_VALUE_SOURCES = ["手动输入", "列字段"]
    REPLACE_ROW_POLICIES = ["当前行", "第一行", "固定行号", "按匹配行号", "按命中序号"]
    EXTRACT_METHODS = [
        "正则提取", "固定位置提取", "从左取N位", "从右取N位", "按分隔符提取",
        "前后关键字之间提取", "指定字符前提取", "指定字符后提取", "删除前缀", "删除后缀"
    ]
    OUTPUT_MODES = ["生成新字段", "覆盖源字段"]
    UNMATCHED_MODES = ["留空", "保留原值", "填写固定值", "跳过该行"]
    FORMAT_PARSE_TYPES = ["日期", "时间", "日期时间"]
    FORMAT_INPUT_STRUCTURES = ["固定位置", "分隔符", "自动识别常见格式"]
    FORMAT_YEAR_RULES = ["20xx", "19xx", "自动窗口", "不补全"]
    FORMAT_DATE_ORDERS = ["年-月-日", "月-日-年", "日-月-年"]
    FORMAT_OUTPUT_MODES = ["生成新字段", "覆盖源字段", "生成多个字段"]
    CURRENT_DATETIME_OUTPUT_MODES = ["生成新字段", "覆盖已有字段"]
    CURRENT_DATETIME_TIME_MODES = ["整次运行固定同一时间", "逐行实时获取"]
    CURRENT_DATETIME_FORMAT_MODES = ["占位符模板", "Python strftime"]
    NEW_COLUMNS_CONFLICT_MODES = ["自动改名", "跳过已有字段", "覆盖已有字段", "存在则报错"]
    NEW_COLUMNS_VALUE_MODES = ["统一默认值", "按列配置值", "空值"]
    SEPARATOR_OPTIONS = ["空字符", "空格", "换行", "Windows换行", "制表符", "-", "_", "/", "\\", "|", ",", ";", ":", ".", "+", "自定义"]

    def __init__(self, app):
        self.app = app
        self.window = tk.Toplevel(app.root)
        self.window.title("计划 / 工作流处理")
        self.window.geometry("1680x950")
        self.window.minsize(1050, 650)
        self.window.transient(app.root)

        self.nodes = []
        self.preview_headers = list(app.headers)
        self.preview_rows = [list(row) for row in app.rows]
        self.current_config_widgets = {}
        self.separator_widgets = []
        self.field_listbox = None
        self.status_var = tk.StringVar(value="计划窗口已打开。先添加节点，再预览或执行完整计划。")
        self.output_mode_var = tk.StringVar(value="输出到主界面预览区")
        self.output_table_var = tk.StringVar(value=self.make_default_output_table_name())
        self.backup_before_overwrite_var = tk.BooleanVar(value=True)
        self.table_access_policy_var = tk.StringVar(value="只审计")
        self.node_type_var = tk.StringVar(value=self.NODE_TYPES[0])
        self.selected_node_index = None
        self.preview_edit_mode = False
        self.preview_edit_entry = None
        self.preview_edit_btn_text = tk.StringVar(value="修改模式:关")
        self.preview_dirty = False
        self.current_transit_tables = {}
        self.last_workflow_context = {}
        self.last_table_access_logs = []
        self.last_table_access_precheck = []
        # “当前预览结果”独立缓存：结果预览区临时载入 SQLite/中转/主界面表时，
        # 不应覆盖最后一次计划预览/执行得到的结果，否则下拉切换后会丢失原预览结果。
        self.plan_preview_headers = list(self.preview_headers)
        self.plan_preview_rows = [list(row) for row in self.preview_rows]
        self.preview_view_kind = "preview"
        # 结果预览区表格选择：用于快速查看当前预览、主界面表、SQLite表和中转副表。
        self.preview_table_var = tk.StringVar(value="当前预览结果")
        self.preview_table_map = {}
        self.preview_search_var = tk.StringVar(value="")
        self.preview_search_matches = []
        self.preview_search_index = -1

        # 循环单步调试缓存：在“循环判断回跳”节点点击“执行循环一次”时复用。
        # 用于逐次运行循环体，后续预览节点可接着这个 N 次循环后的上下文继续执行。
        self.manual_loop_context = None
        self.manual_loop_headers = None
        self.manual_loop_rows = None
        self.manual_loop_start_idx = None
        self.manual_loop_judge_idx = None
        self.manual_loop_after_index = None
        self.manual_loop_logs = []

        # 后台执行/进度条状态：主界面不直接跑耗时流程，后台线程负责执行，Queue 回传进度。
        # 第一版采用线程 worker，接口按“可迁移到子进程 worker”的消息协议设计。
        self.workflow_worker_thread = None
        self.workflow_worker_queue = queue.Queue()
        self.workflow_worker_cancel = None
        self.workflow_worker_running = False
        self.workflow_progress_var = tk.DoubleVar(value=0)
        self.node_progress_var = tk.DoubleVar(value=0)
        self.workflow_progress_text = tk.StringVar(value="总进度：空闲")
        self.node_progress_text = tk.StringVar(value="当前节点：空闲")
        self.worker_status_text = tk.StringVar(value="执行状态：空闲")
        self.workflow_current_task = None
        self.workflow_widget_state_backup = {}
        self.workflow_cancel_button = None

        # 外部插件节点：启动/打开计划窗口时扫描 plugins 目录并注册。
        self.plugin_registry = {}
        self.plugin_display_map = {}
        self.plugin_load_errors = []
        self.load_plugins(show_status=False)

        # 计划模板库：程序真实目录下的 plan 文件夹。
        # 只识别 template_type == "workflow_plan" 的新版模板。
        self.plan_dir = self.get_plan_dir()
        # 节点组模板库：程序真实目录下的 groups 文件夹。
        self.group_dir = self.get_group_dir()
        self.plan_template_var = tk.StringVar(value="")
        self.plan_template_map = {}

        self.build_ui()
        self.refresh_node_list()
        self.refresh_preview_tree(self.preview_headers, self.preview_rows)
        self.refresh_plan_template_list(show_status=False)

    def make_default_output_table_name(self):
        base = self.app.sanitize_sql_name(self.app.table_name_var.get(), "计划结果")
        return f"{base}_计划结果_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

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
        ttk.Label(self.config_frame, text="请先添加并选择一个节点。每个节点会接收上一步结果，并输出给下一步。", foreground="gray").pack(anchor=tk.W)

    def clear_config_frame(self):
        for child in self.config_frame.winfo_children():
            child.destroy()
        self.current_config_widgets = {}
        self.separator_widgets = []
        self.field_listbox = None
        if hasattr(self, "config_canvas"):
            self.config_canvas.yview_moveto(0)
            self.config_canvas.xview_moveto(0)
            self.config_canvas.after_idle(lambda: self.config_canvas.configure(scrollregion=self.config_canvas.bbox("all")))

    def get_selected_node_index(self):
        sel = self.node_listbox.curselection()
        if not sel:
            return None
        return sel[0]

    def on_node_select(self, event=None):
        idx = self.get_selected_node_index()
        self.selected_node_index = idx
        self.rebuild_current_config()

    def rebuild_current_config(self):
        idx = self.get_selected_node_index()
        if idx is None or idx < 0 or idx >= len(self.nodes):
            self.show_empty_config()
            return
        self.build_node_config(idx)

    def refresh_node_list(self, select_index=None, reveal=True):
        self.ensure_node_tree_identity(self.nodes)
        selected = self.get_selected_node_index() if select_index is None else select_index
        self.node_listbox.delete(0, tk.END)
        for idx, node in enumerate(self.nodes, start=1):
            mark = "√" if node.get("enabled", True) else "×"
            self.node_listbox.insert(tk.END, f"[{mark}] {idx}. {node.get('type')}：{node.get('name', '')}")
        if selected is not None and self.nodes:
            selected = min(selected, len(self.nodes) - 1)
            self.selected_node_index = selected
            self.node_listbox.selection_clear(0, tk.END)
            self.node_listbox.selection_set(selected)
            self.node_listbox.activate(selected)
            if reveal:
                self.node_listbox.see(selected)
        elif not self.nodes:
            self.selected_node_index = None


    # ------------------------------------------------------------------
    # 外部 Python 插件节点
    # ------------------------------------------------------------------
    def get_plugins_dir(self):
        path = os.path.join(getattr(self.app, "app_dir", get_app_dir()), "plugins")
        os.makedirs(path, exist_ok=True)
        return path

    def get_plugin_data_dir(self, plugin_id=None):
        base = os.path.join(getattr(self.app, "app_dir", get_app_dir()), "plugin_data")
        if plugin_id:
            base = os.path.join(base, self.app.sanitize_sql_name(plugin_id, "plugin"))
        os.makedirs(base, exist_ok=True)
        return base

    def get_plugin_log_dir(self):
        path = os.path.join(getattr(self.app, "app_dir", get_app_dir()), "logs", "plugins")
        os.makedirs(path, exist_ok=True)
        return path

    def get_plugin_env_dir(self, plugin_id=None):
        base = os.path.join(getattr(self.app, "app_dir", get_app_dir()), "plugin_envs")
        if plugin_id:
            base = os.path.join(base, self.app.sanitize_sql_name(plugin_id, "plugin"))
        os.makedirs(base, exist_ok=True)
        return base

    def get_node_type_values(self):
        values = list(self.NODE_TYPES)
        values.extend(sorted(getattr(self, "plugin_display_map", {}).keys()))
        return values

    def refresh_plugins(self):
        self.load_plugins(show_status=True)
        if hasattr(self, "node_type_combo"):
            self.node_type_combo["values"] = self.get_node_type_values()
        if self.node_type_var.get() not in self.get_node_type_values():
            self.node_type_var.set(self.NODE_TYPES[0])
        self.rebuild_current_config()

    def load_plugins(self, show_status=False):
        """扫描 plugins 目录并注册插件。"""
        self.plugin_registry = {}
        self.plugin_display_map = {}
        self.plugin_load_errors = []
        plugins_dir = self.get_plugins_dir()
        registry, errors = scan_plugins(plugins_dir)
        self.plugin_registry = registry
        self.plugin_load_errors = errors

        used_names = {}
        external_only_count = 0
        for plugin_id, item in sorted(self.plugin_registry.items(), key=lambda kv: kv[1]["info"].get("name", kv[0])):
            name = str(item["info"].get("name", plugin_id)).strip() or plugin_id
            suffix = ""
            if item.get("load_status") == "仅独立环境运行":
                external_only_count += 1
                suffix = " [仅独立]"
            display = f"插件 / {name}{suffix}"
            if display in used_names:
                used_names[display] += 1
                display = f"插件 / {name} ({plugin_id}){suffix}"
            else:
                used_names[display] = 1
            self.plugin_display_map[display] = plugin_id

        if show_status:
            msg = f"插件刷新完成：已注册 {len(self.plugin_registry)} 个插件"
            if external_only_count:
                msg += f"，其中仅独立环境 {external_only_count} 个"
            if self.plugin_load_errors:
                msg += f"，加载失败 {len(self.plugin_load_errors)} 个"
                first = self.plugin_load_errors[0]
                msg += f"；示例：{first.get('file')} - {first.get('error')}"
            self.status_var.set(msg)


    def default_config_for_plugin(self, plugin_id):
        item = self.plugin_registry.get(plugin_id, {})
        schema = item.get("schema", [])
        params = {}
        for field in schema:
            if not isinstance(field, dict):
                continue
            name = field.get("name")
            if not name:
                continue
            default = field.get("default", "")
            if field.get("type") == "multi_field_select" and default == "":
                default = []
            params[name] = default
        info = item.get("info", {})
        default_run_mode = info.get("run_mode") or item.get("run_mode_default") or "主程序内置环境"
        if default_run_mode in ("external_python", "独立环境", "插件独立环境"):
            default_run_mode = "插件独立环境"
        else:
            default_run_mode = "主程序内置环境"
        return {
            "plugin_id": plugin_id,
            "params": params,
            "input_tables": [],
            "run_mode": default_run_mode,
            "external_python": "",
            "external_env_dir": self.get_plugin_env_dir(plugin_id),
            "external_entry": item.get("external_entry", item.get("path", "")),
            "external_timeout": "0",
            "output_mode": "使用插件返回结果",
            "save_output_as_transit": False,
            "transit_name": item.get("info", {}).get("name", plugin_id),
            "transit_conflict_mode": "覆盖",
            "save_plugin_log_file": True,
            "save_plugin_log_sqlite": False,
            "save_plugin_log_transit": False,
            "plugin_log_transit_name": f"{item.get('info', {}).get('name', plugin_id)}_日志",
            "plugin_log_in_preview": False,
            "plugin_failure_policy": "停止工作流",
        }

    def get_sqlite_table_names(self):
        db_path = self.app.db_path_var.get().strip()
        if not db_path or not os.path.exists(db_path):
            return []
        try:
            return TableAccessManager(db_path).list_tables()
        except Exception:
            return []

    def get_workflow_snapshot(self, context=None):
        """返回后台任务快照。后台线程优先使用快照，避免直接读取 Tkinter 变量。"""
        if isinstance(context, dict):
            snapshot = context.get("workflow_snapshot") or {}
            if isinstance(snapshot, dict):
                return snapshot
        return {}

    def get_workflow_db_path(self, context=None):
        """执行期统一获取 SQLite 路径：优先读 workflow_snapshot，兜底读主线程 UI 变量。"""
        snapshot = self.get_workflow_snapshot(context)
        db_path = str(snapshot.get("db_path") or "").strip()
        if db_path:
            return db_path
        try:
            return self.app.db_path_var.get().strip()
        except Exception:
            return ""

    def make_node_id(self):
        return "node_" + uuid.uuid4().hex[:12]

    def center_toplevel(self, win, parent=None, width=None, height=None):
        """把 Toplevel 放到父窗口中心；没有父窗口时放到屏幕中心。"""
        try:
            parent = parent or self.window
            win.update_idletasks()
            w = int(width or win.winfo_width() or win.winfo_reqwidth() or 600)
            h = int(height or win.winfo_height() or win.winfo_reqheight() or 400)
            if parent is not None and parent.winfo_exists():
                parent.update_idletasks()
                px = parent.winfo_rootx()
                py = parent.winfo_rooty()
                pw = parent.winfo_width()
                ph = parent.winfo_height()
                if pw <= 1 or ph <= 1:
                    px = py = 0
                    pw = win.winfo_screenwidth()
                    ph = win.winfo_screenheight()
            else:
                px = py = 0
                pw = win.winfo_screenwidth()
                ph = win.winfo_screenheight()
            x = max(0, px + (pw - w) // 2)
            y = max(0, py + (ph - h) // 2)
            win.geometry(f"{w}x{h}+{x}+{y}" if width or height else f"+{x}+{y}")
        except Exception:
            pass

    def show_centered_toplevel(self, win, parent=None, width=None, height=None):
        self.center_toplevel(win, parent, width, height)
        try:
            win.deiconify()
        except Exception:
            pass
        try:
            win.lift()
        except Exception:
            pass
        try:
            win.focus_set()
        except Exception:
            pass

    def default_config_for_type(self, node_type):
        table_names = []
        needs_sqlite_defaults = {"匹配值输出列名", "选定列写入指定表", "字段映射写入表"}
        if node_type in needs_sqlite_defaults:
            try:
                table_names = self.app.get_table_names()
            except Exception:
                pass
        table_columns = {}
        for table in table_names[:1]:
            try:
                table_columns[table] = self.app.get_table_columns(table)
            except Exception:
                table_columns[table] = []
        return workflow_default_config_for_type(
            node_type,
            preview_headers=self.preview_headers,
            table_names=table_names,
            table_columns=table_columns,
            app_dir=getattr(self.app, "app_dir", get_app_dir()),
        )

    def default_name_for_node(self, node_type):
        return {
            "节点组 / 子工作流": "节点组 / 子工作流",
            "循环执行起点": "循环执行起点",
            "循环判断回跳": "循环判断回跳",
            "批量替换": "批量替换",
            "数据提取": "数据提取",
            "格式规范化 / 日期时间解析": "格式规范化 / 日期时间解析",
            "新建日期时间列": "新建日期时间列",
            "新建列": "新建列",
            "合并列": "合并列",
            "批量更改列名": "批量更改列名",
            "去重 / 重复数据处理": "去重 / 重复数据处理",
            "列数字运算": "列数字运算",
            "匹配值输出列名": "匹配值输出列名",
            "复制列": "复制列",
            "复制行": "复制行",
            "删除行": "删除行",
            "填充值": "填充值",
            "序列填充": "序列填充",
            "区域填充": "区域填充",
            "行数据映射填充": "行数据映射填充",
            "保存中转数据": "保存中转数据",
            "字段映射写入表": "字段映射写入表",
            "高级筛选": "筛选数据",
            "删除列": "删除列",
            "移动列": "整理列顺序",
        }.get(node_type, node_type)

    def add_node(self):
        node_type = self.node_type_var.get()
        if node_type in getattr(self, "plugin_display_map", {}):
            plugin_id = self.plugin_display_map[node_type]
            plugin_info = self.plugin_registry.get(plugin_id, {}).get("info", {})
            node = {
                "enabled": True,
                "type": "插件节点",
                "name": plugin_info.get("name", plugin_id),
                "config": self.default_config_for_plugin(plugin_id),
            }
        else:
            node = {
                "enabled": True,
                "type": node_type,
                "name": self.default_name_for_node(node_type),
                "config": self.default_config_for_type(node_type),
            }
        self.ensure_node_identity(node)
        selected = self.node_listbox.curselection()
        insert_at = int(selected[0]) + 1 if len(selected) == 1 else len(self.nodes)
        self.nodes.insert(insert_at, node)
        self.refresh_node_list(select_index=insert_at, reveal=True)
        self.build_node_config(insert_at)
        if len(selected) == 1:
            self.status_var.set(f"已在当前节点下方插入：{node.get('name', node.get('type', '节点'))}")
        else:
            self.status_var.set(f"已追加节点：{node.get('name', node.get('type', '节点'))}")

    def delete_node(self):
        idx = self.get_selected_node_index()
        if idx is None:
            return
        del self.nodes[idx]
        self.refresh_node_list()
        self.rebuild_current_config()

    def move_node_up(self):
        idx = self.get_selected_node_index()
        if idx is None or idx <= 0:
            return
        self.nodes[idx - 1], self.nodes[idx] = self.nodes[idx], self.nodes[idx - 1]
        self.refresh_node_list(select_index=idx - 1, reveal=True)
        self.rebuild_current_config()

    def move_node_down(self):
        idx = self.get_selected_node_index()
        if idx is None or idx >= len(self.nodes) - 1:
            return
        self.nodes[idx + 1], self.nodes[idx] = self.nodes[idx], self.nodes[idx + 1]
        self.refresh_node_list(select_index=idx + 1, reveal=True)
        self.rebuild_current_config()

    def toggle_node_enabled(self):
        idx = self.get_selected_node_index()
        if idx is None:
            return
        self.nodes[idx]["enabled"] = not self.nodes[idx].get("enabled", True)
        self.refresh_node_list(select_index=idx, reveal=True)

    def copy_node(self):
        idx = self.get_selected_node_index()
        if idx is None:
            return
        import copy
        new_node = copy.deepcopy(self.nodes[idx])
        new_node["name"] = f"{new_node.get('name', new_node.get('type'))}_复制"
        self.ensure_node_tree_identity([new_node], force_new=True)
        self.nodes.insert(idx + 1, new_node)
        self.refresh_node_list(select_index=idx + 1, reveal=True)
        self.rebuild_current_config()

    def clear_nodes(self):
        if self.nodes and not messagebox.askyesno("确认", "是否清空所有计划节点？"):
            return
        self.nodes.clear()
        self.refresh_node_list()
        self.show_empty_config()

    def update_node_name(self, idx, name_var):
        if 0 <= idx < len(self.nodes):
            self.nodes[idx]["name"] = name_var.get().strip() or self.nodes[idx]["type"]
            self.refresh_node_list(select_index=idx, reveal=True)

    def make_config_preview_context(self):
        """
        配置界面专用的预运行上下文。

        用途：刷新某个节点配置时，会临时运行它前面的节点，以便拿到“到当前节点为止”的字段列表和中转副表。
        这里允许“选定列写入指定表”在配置预运行时写入【当前工作表】和【中转副表】，
        这样后续高级筛选、匹配值输出列名、插件节点等配置界面才能看到这些临时字段。

        注意：selected_columns_config_preview_only 会在该节点内部拦截 SQLite 写入，
        防止只是切换/刷新配置界面时误改真实数据库。
        """
        return {
            "transit_tables": {},
            "loop_states": {},
            "loop_results": {},
            "is_config_probe": True,
            "allow_selected_columns_write_in_preview": True,
            "selected_columns_config_preview_only": True,
        }

    def get_headers_rows_before(self, idx):
        return self.run_plan(
            stop_index=idx - 1,
            raise_error=True,
            initial_context=self.make_config_preview_context(),
        )[:2]

    def get_transit_context_before(self, idx):
        """运行到指定节点之前，取得已经保存的内存中转副表。配置界面用于列出可引用的中转表。"""
        if idx is None or idx <= 0:
            return self.make_config_preview_context()
        try:
            _, _, _, context = self.run_plan(
                stop_index=idx - 1,
                raise_error=False,
                return_context=True,
                initial_context=self.make_config_preview_context(),
            )
            return context
        except Exception:
            return self.make_config_preview_context()

    def make_node_enabled_var(self, idx):
        var = tk.BooleanVar(value=self.nodes[idx].get("enabled", True))
        def on_change(*_):
            if 0 <= idx < len(self.nodes):
                self.nodes[idx]["enabled"] = bool(var.get())
                self.refresh_node_list(select_index=idx, reveal=True)
        var.trace_add("write", on_change)
        return var

    def add_labeled_entry(self, parent, label, value, row, col, width=20):
        ttk.Label(parent, text=label).grid(row=row, column=col, sticky=tk.W, padx=4, pady=4)
        var = tk.StringVar(value=value)
        ttk.Entry(parent, textvariable=var, width=width).grid(row=row, column=col + 1, sticky=tk.W, padx=4, pady=4)
        return var

    def add_labeled_combo(self, parent, label, value, values, row, col, width=20, readonly=True):
        ttk.Label(parent, text=label).grid(row=row, column=col, sticky=tk.W, padx=4, pady=4)
        var = tk.StringVar(value=value if value in values or not readonly else (values[0] if values else value))
        state = "readonly" if readonly else "normal"
        ttk.Combobox(parent, textvariable=var, values=values, width=width, state=state).grid(row=row, column=col + 1, sticky=tk.W, padx=4, pady=4)
        return var

    def add_labeled_combo_control(self, parent, label, value, values, row, col, width=20, readonly=True):
        ttk.Label(parent, text=label).grid(row=row, column=col, sticky=tk.W, padx=4, pady=4)
        var = tk.StringVar(value=value if value in values or not readonly else (values[0] if values else value))
        state = "readonly" if readonly else "normal"
        combo = ttk.Combobox(parent, textvariable=var, values=values, width=width, state=state)
        combo.grid(row=row, column=col + 1, sticky=tk.W, padx=4, pady=4)
        return var, combo

    def refresh_combo_values(self, combo, var, values, keep_custom=True, fallback=""):
        values = [str(v) for v in (values or [])]
        current = str(var.get() or "")
        display_values = list(values)
        if current and current not in display_values and keep_custom:
            display_values = [current] + display_values
        combo.configure(values=display_values)
        if not current:
            var.set(fallback if fallback in values else (values[0] if values else fallback))
        elif current not in values and not keep_custom:
            var.set(fallback if fallback in values else (values[0] if values else fallback))

    def refresh_listbox_values(self, listbox, values, selected_values=None):
        selected_values = set(selected_values or [])
        listbox.delete(0, tk.END)
        selected_indices = []
        for i, value in enumerate(values or []):
            listbox.insert(tk.END, value)
            if value in selected_values:
                selected_indices.append(i)
        for i in selected_indices:
            listbox.selection_set(i)
        return selected_indices

    def sync_var_to_config(self, var, config, key, cast=str):
        def on_change(*_):
            try:
                config[key] = cast(var.get())
            except Exception:
                config[key] = var.get()
        var.trace_add("write", on_change)
        return var

    def sync_bool_to_config(self, var, config, key):
        def on_change(*_):
            config[key] = bool(var.get())
        var.trace_add("write", on_change)
        return var


    # ------------------------------
    # 节点组 / 子工作流
    # ------------------------------
    def merge_selected_nodes_to_group(self):
        return workflow_group_template_ui.merge_selected_nodes_to_group(
            self,
            messagebox_module=messagebox,
            simpledialog_module=simpledialog,
        )

    def expand_selected_group(self):
        return workflow_group_template_ui.expand_selected_group(self, messagebox_module=messagebox)

    def get_group_dir(self):
        return workflow_group_template_ui.get_group_dir(self, get_app_dir)

    def validate_group_template_data(self, data):
        return workflow_group_template_ui.validate_group_template_data(data)

    def build_group_template_data(self, config, group_name=None):
        return workflow_group_template_ui.build_group_template_data(config, group_name=group_name)

    def group_config_from_template_data(self, data):
        return workflow_group_template_ui.group_config_from_template_data(data)

    def save_group_template_from_config(self, config):
        return workflow_group_template_ui.save_group_template_from_config(
            self,
            config,
            atomic_write_json,
            messagebox_module=messagebox,
            filedialog_module=filedialog,
        )

    def load_group_template_dialog(self):
        return workflow_group_template_ui.load_group_template_dialog(
            self,
            load_json_file_with_recovery,
            messagebox_module=messagebox,
            filedialog_module=filedialog,
        )

    def open_group_dir(self):
        return workflow_group_template_ui.open_group_dir(self, messagebox_module=messagebox)

    def get_plan_dir(self):
        """返回程序真实目录下的 plan 模板目录，并确保目录存在。"""
        base_dir = getattr(self.app, "app_dir", get_app_dir())
        plan_dir = os.path.join(base_dir, "plan")
        os.makedirs(plan_dir, exist_ok=True)
        return plan_dir

    def sanitize_plan_file_name(self, name):
        """生成适合作为文件名的计划模板名称。"""
        name = str(name or "工作流计划").strip()
        name = re.sub(r'[\\/:*?"<>|]+', "_", name)
        name = re.sub(r"\s+", "_", name)
        return name or "工作流计划"

    def build_plan_template_data(self, plan_name=None):
        """
        收集当前计划模板数据。新版模板必须带 template_type。

        plan_name 优先由保存时选择的 JSON 文件名传入，
        这样模板下拉菜单中的计划名会和实际保存文件名保持一致。
        """
        plan_name = str(plan_name or "").strip()
        if not plan_name:
            plan_name = self.output_table_var.get().strip() or "工作流计划"

        self.refresh_node_tree_table_access(self.nodes)
        return {
            "template_type": "workflow_plan",
            "version": "1.0",
            "plan_name": plan_name,
            "nodes": self.nodes,
            "output_mode": self.output_mode_var.get(),
            "output_table": self.output_table_var.get(),
            "backup_before_overwrite": self.backup_before_overwrite_var.get(),
            "table_access_policy": self.normalize_table_access_policy(),
        }

    def validate_plan_template_data(self, data):
        """
        只识别新版计划模板：
        - 必须是 dict
        - template_type 必须等于 workflow_plan
        - nodes 必须是 list
        """
        if not isinstance(data, dict):
            return False, "模板内容不是 JSON 对象。"
        if data.get("template_type") != "workflow_plan":
            return False, "template_type 不是 workflow_plan。"
        if not isinstance(data.get("nodes"), list):
            return False, "nodes 字段不存在或不是列表。"
        return True, ""

    def apply_plan_template_data(self, data, source_path=""):
        """把已验证的计划模板应用到当前计划窗口。"""
        ok, reason = self.validate_plan_template_data(data)
        if not ok:
            raise ValueError(reason)

        self.nodes = data.get("nodes", [])
        self.ensure_node_tree_identity(self.nodes)
        self.output_mode_var.set(data.get("output_mode", "输出到主界面预览区"))
        self.output_table_var.set(data.get("output_table", self.make_default_output_table_name()))
        self.backup_before_overwrite_var.set(bool(data.get("backup_before_overwrite", True)))
        self.set_table_access_policy(data.get("table_access_policy", "audit"))
        self.refresh_node_list()
        self.rebuild_current_config()

        if source_path:
            self.status_var.set(f"计划模板已载入：{source_path}")
        else:
            self.status_var.set("计划模板已载入。")

    def open_plan_dir(self):
        """打开程序真实目录下的 plan 模板目录。"""
        os.makedirs(self.plan_dir, exist_ok=True)
        try:
            if hasattr(os, "startfile"):
                os.startfile(self.plan_dir)
            else:
                messagebox.showinfo("plan目录", self.plan_dir)
        except Exception as e:
            messagebox.showerror("打开失败", f"无法打开 plan 目录：\n{self.plan_dir}\n\n{e}")

    def save_plan_template(self):
        os.makedirs(self.plan_dir, exist_ok=True)
        default_name = self.sanitize_plan_file_name(self.output_table_var.get() or "工作流计划") + ".json"
        path = filedialog.asksaveasfilename(
            title="保存计划模板",
            initialdir=self.plan_dir,
            initialfile=default_name,
            defaultextension=".json",
            filetypes=[("JSON模板", "*.json"), ("所有文件", "*.*")]
        )
        if not path:
            return

        # 使用用户实际保存的 JSON 文件名作为 plan_name。
        # 例如保存为“PDF批量重命名.json”，则 JSON 内部写入：
        # "plan_name": "PDF批量重命名"。
        saved_file_name = os.path.basename(path)
        saved_plan_name = os.path.splitext(saved_file_name)[0].strip() or "工作流计划"

        data = self.build_plan_template_data(plan_name=saved_plan_name)
        try:
            atomic_write_json(path, data)
            self.status_var.set(f"计划模板已保存：{path}；plan_name 已同步为：{saved_plan_name}")
            self.refresh_plan_template_list(show_status=False)

            # 保存后尽量自动选中刚保存的模板，便于确认和后续快速载入。
            if hasattr(self, "plan_template_combo") and hasattr(self, "plan_template_map"):
                abs_saved_path = os.path.abspath(path)
                for display_name, template_path in self.plan_template_map.items():
                    if os.path.abspath(template_path) == abs_saved_path:
                        self.plan_template_var.set(display_name)
                        break
        except Exception as e:
            messagebox.showerror("保存失败", str(e))

    def load_plan_template_from_path(self, path):
        if not path:
            return
        if self.nodes:
            ok = messagebox.askyesno(
                "确认载入模板",
                "当前计划已有节点，载入模板会覆盖当前计划。\n是否继续？"
            )
            if not ok:
                return
        try:
            data = load_json_file_with_recovery(path, parent=self.window)
            self.apply_plan_template_data(data, source_path=path)
        except Exception as e:
            messagebox.showerror("载入失败", str(e))

    def load_plan_template(self):
        path = filedialog.askopenfilename(
            title="载入计划模板",
            initialdir=self.plan_dir,
            filetypes=[("JSON模板", "*.json"), ("所有文件", "*.*")]
        )
        if not path:
            return
        self.load_plan_template_from_path(path)

    def load_selected_plan_template(self):
        display = self.plan_template_var.get()
        if not display:
            messagebox.showwarning("提示", "请先从下拉菜单选择一个计划模板。")
            return

        path = self.plan_template_map.get(display)
        if not path:
            self.refresh_plan_template_list(show_status=False)
            path = self.plan_template_map.get(display)

        if not path:
            messagebox.showwarning("提示", "选中的计划模板不存在或已失效，请刷新模板列表。")
            return

        self.load_plan_template_from_path(path)


    # ==================== 后台执行 / 进度条管理 ====================
    def get_workflow_log_dir(self):
        log_dir = os.path.join(getattr(self.app, "app_dir", get_app_dir()), "logs", "workflow")
        os.makedirs(log_dir, exist_ok=True)
        return log_dir

    def write_workflow_error_log(self, mode, message, traceback_text="", logs=None, snapshot=None):
        """后台线程错误日志。只写文件，不直接操作 Tkinter。"""
        try:
            log_dir = self.get_workflow_log_dir()
            path = os.path.join(log_dir, f"workflow_error_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.log")
            snapshot = snapshot or {}
            node_count = len(snapshot.get("nodes", self.nodes) or [])
            with open(path, "w", encoding="utf-8") as f:
                f.write(f"任务模式：{mode}\n")
                f.write(f"时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"节点数量：{node_count}\n")
                if snapshot.get("db_path"):
                    f.write(f"数据库：{snapshot.get('db_path')}\n")
                if snapshot.get("workflow_name"):
                    f.write(f"工作流/输出名：{snapshot.get('workflow_name')}\n")
                f.write(f"错误信息：{message}\n\n")
                if logs:
                    f.write("执行日志：\n")
                    for item in logs:
                        f.write(f"- {item}\n")
                    f.write("\n")
                if traceback_text:
                    f.write("Traceback：\n")
                    f.write(traceback_text)
            return path
        except Exception:
            return ""



if __name__ == "__main__":
    # 预留给后续子进程 Worker / PyInstaller 打包使用。当前版本后台执行采用线程 Worker。
    try:
        import multiprocessing
        multiprocessing.freeze_support()
    except Exception:
        pass
    root = tk.Tk()
    app = ClipboardTableApp(root)
    root.mainloop()
