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
from tkinter import messagebox
import os
import sys
import traceback
import queue
import time
import uuid

from db import PluginDatabaseAPI, TableAccessManager
from workflow.clipboard_table_actions_mixin import ClipboardTableActionsMixin
from workflow.clipboard_table_edit_mixin import ClipboardTableEditMixin
from workflow.clipboard_table_io_mixin import ClipboardTableIoMixin
from workflow.clipboard_table_preview_mixin import ClipboardTablePreviewMixin
from workflow.clipboard_table_ui_mixin import ClipboardTableUiMixin
from workflow.filter_config_window_mixin import FilterConfigWindowMixin
from workflow.group_config_window_mixin import GroupConfigWindowMixin
from workflow.plan_template_io_mixin import PlanTemplateIoMixin
from workflow.plan_preview_mixin import PlanPreviewMixin
from workflow.plan_workflow_window_mixin import PlanWorkflowUiMixin
from workflow.plugin_config_window_mixin import PluginConfigWindowMixin
from workflow.plugin_dirs_mixin import PluginDirsMixin
from workflow.plugin_registry_mixin import PluginRegistryMixin
from workflow.window_geometry_mixin import WindowGeometryMixin
from workflow.workflow_constants import WorkflowConstantsMixin
from workflow.workflow_config_preview_mixin import WorkflowConfigPreviewMixin
from workflow.workflow_config_area_mixin import WorkflowConfigAreaMixin
from workflow.workflow_config_ui_helpers_mixin import WorkflowConfigUiHelpersMixin
from workflow.workflow_app_support_mixin import WorkflowAppSupportMixin
from workflow.workflow_default_config_mixin import WorkflowDefaultConfigMixin
from workflow.workflow_group_template_mixin import WorkflowGroupTemplateMixin
from workflow.workflow_naming_mixin import WorkflowNamingMixin
from workflow.workflow_node_list_mixin import WorkflowNodeListMixin
from workflow.table_access_window_mixin import TableAccessWindowMixin
from workflow.workflow_execution_mixin import WorkflowExecutionMixin
from workflow.workflow_node_execution_mixin import WorkflowNodeExecutionMixin
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


class ClipboardTableApp(
    ClipboardTableActionsMixin,
    ClipboardTableUiMixin,
    ClipboardTableEditMixin,
    ClipboardTablePreviewMixin,
    ClipboardTableIoMixin,
):
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

class PlanWorkflowWindow(
    WorkflowConstantsMixin,
    PlanTemplateIoMixin,
    PluginDirsMixin,
    PluginRegistryMixin,
    WindowGeometryMixin,
    WorkflowConfigPreviewMixin,
    WorkflowConfigAreaMixin,
    WorkflowConfigUiHelpersMixin,
    WorkflowAppSupportMixin,
    WorkflowDefaultConfigMixin,
    WorkflowGroupTemplateMixin,
    WorkflowNamingMixin,
    WorkflowNodeListMixin,
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

    # ==================== 后台执行 / 进度条管理 ====================


ClipboardTableApp.workflow_window_class = PlanWorkflowWindow


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
