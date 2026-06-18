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
import os
import sys
import traceback
import queue
import time
import uuid
from datetime import datetime

from db import PluginDatabaseAPI, TableAccessManager
from shared.atomic_json_utils import atomic_write_json, load_json_with_backup
from workflow.default_configs import (
    default_config_for_type as workflow_default_config_for_type,
    default_name_for_node as workflow_default_name_for_node,
)
from workflow.advanced_filter_window import AdvancedFilterWindow
from workflow.batch_replace_window import BatchReplaceWindow
from workflow.clipboard_table_edit_mixin import ClipboardTableEditMixin
from workflow.clipboard_table_io_mixin import ClipboardTableIoMixin
from workflow.clipboard_table_preview_mixin import ClipboardTablePreviewMixin
from workflow.clipboard_table_ui_mixin import ClipboardTableUiMixin
from workflow.data_extract_window import DataExtractWindow
from workflow.merge_columns_window import MergeColumnsWindow
from workflow.filter_config_window_mixin import FilterConfigWindowMixin
from workflow.group_config_window_mixin import GroupConfigWindowMixin
from workflow.plan_template_io_mixin import PlanTemplateIoMixin
from workflow.plan_preview_mixin import PlanPreviewMixin
from workflow.plan_workflow_window_mixin import PlanWorkflowUiMixin
from workflow.plugin_config_window_mixin import PluginConfigWindowMixin
from workflow.plugin_dirs_mixin import PluginDirsMixin
from workflow.plugin_registry_mixin import PluginRegistryMixin
from workflow.window_geometry_mixin import WindowGeometryMixin
from workflow.workflow_config_preview_mixin import WorkflowConfigPreviewMixin
from workflow.workflow_config_ui_helpers_mixin import WorkflowConfigUiHelpersMixin
from workflow.workflow_app_support_mixin import WorkflowAppSupportMixin
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





class ClipboardTableApp(ClipboardTableUiMixin, ClipboardTableEditMixin, ClipboardTablePreviewMixin, ClipboardTableIoMixin):
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

    def on_table_selected(self, event=None):
        table_name = self.table_name_var.get().strip()

        if not table_name:
            return

        self.load_table_from_sqlite(table_name)

class PlanWorkflowWindow(
    PlanTemplateIoMixin,
    PluginDirsMixin,
    PluginRegistryMixin,
    WindowGeometryMixin,
    WorkflowConfigPreviewMixin,
    WorkflowConfigUiHelpersMixin,
    WorkflowAppSupportMixin,
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
        return workflow_default_name_for_node(node_type)

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

    # ==================== 后台执行 / 进度条管理 ====================
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
