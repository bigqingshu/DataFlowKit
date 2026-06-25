# -*- coding: utf-8 -*-
"""Qt6 workflow shell shaped like the original workflow panel."""

from __future__ import annotations

import copy
import html
import json
import time
from datetime import datetime
from pathlib import Path

from ui_qt.config_form import NodeConfigForm
from ui_qt.data_source_window import DataSourceManagerWindow
from ui_qt.engine_client import QtHeadlessEngineClient, SAMPLE_HEADERS, SAMPLE_PLAN, SAMPLE_ROWS
from ui_qt.node_ui_metadata import CATEGORY_ORDER, category_label, format_node_detail
from ui_qt.qt_compat import qt_enum
from ui_qt.table_model import make_table_model
from ui_qt.table_view_utils import configure_fast_table_view
from workflow.node_config_context_cache import (
    build_preview_context_cache,
    resolve_node_config_headers,
)


class QtWorkflowMainWindow:
    """Controller for a Qt workflow panel that mirrors the classic window."""

    def __init__(self, qt, parent=None, engine_client=None):
        self.qt = qt
        self.user_role = qt_enum(qt, "ItemDataRole", "UserRole")
        self.engine_client = engine_client or QtHeadlessEngineClient()
        self.window = qt.QtWidgets.QMainWindow(parent)
        self.window.setWindowTitle(f"DataFlowKit Qt6 工作流面板 ({qt.binding})")
        self.window.resize(1380, 860)

        self.current_plan_path = None
        self.current_plan = copy.deepcopy(SAMPLE_PLAN)
        self.current_headers = list(SAMPLE_HEADERS)
        self.current_rows = [list(row) for row in SAMPLE_ROWS]
        self.current_input_source = {"type": "sample"}
        self.current_input_db_path = ""
        self.preview_headers = list(SAMPLE_HEADERS)
        self.preview_rows = [list(row) for row in SAMPLE_ROWS]
        self.last_preview_headers = []
        self.last_preview_rows = []
        self.current_table_kind = "input"
        self.plan_dir = Path.cwd() / "plan"
        self.node_schema_by_id = {}
        self.current_job_id = ""
        self.current_job_action = ""
        self.current_job_title = ""
        self.current_job_event_sequence = 0
        self.current_job_messages = []
        self.current_job_started_at = 0.0
        self.current_job_has_workflow_elapsed = False
        self.current_job_stop_index = None
        self.node_config_preview_cache = {}
        self.workflow_action_buttons = []
        self.node_action_buttons = {}
        self.run_action_buttons = {}
        self.output_mode_records = []
        self.output_mode_meta = {}
        self.preview_source_records = []
        self.current_message_panel = {}
        self.data_source_manager_controller = None
        self.data_source_service_description = {}
        self.node_enabled_icon_cache = {}
        self.plugin_config_view_widgets_by_id = {}
        self.plugin_warning_targets_by_link = {}
        self.current_plugin_config_description = {}
        self.current_legacy_plugin_config_action = {}

        self._build_ui()
        self.refresh_data_source_service_description()
        self.refresh_all()

    def refresh_data_source_service_description(self):
        try:
            described = self.engine_client.describe_data_source_service()
        except Exception:
            described = {}
        self.data_source_service_description = copy.deepcopy(described if isinstance(described, dict) else {})
        return self.data_source_service_description

    def _data_source_table_action(self, action_id):
        service = self.data_source_service_description if isinstance(self.data_source_service_description, dict) else {}
        actions = service.get("table_actions") if isinstance(service.get("table_actions"), dict) else {}
        action = actions.get(action_id) if isinstance(actions.get(action_id), dict) else {}
        return action

    def _has_data_source_table_action(self, action_id):
        return bool(self._data_source_table_action(action_id).get("engine_action"))

    def _table_context(self):
        table_names = []
        table_columns = {}
        try:
            listed = self.engine_client.list_tables(db_path=self.current_data_source_db_path() or None)
        except Exception:
            listed = {}
        for item in listed.get("tables") or []:
            name = self._table_record_name(item)
            if not name:
                continue
            table_names.append(name)
            headers = self._table_record_headers(item)
            if headers:
                table_columns[name] = [str(header) for header in headers]
        return {
            "table_names": table_names,
            "table_columns": table_columns,
        }

    def _table_record_name(self, item):
        if isinstance(item, dict):
            return str(item.get("name") or item.get("table_name") or item.get("table") or "").strip()
        return str(item or "").strip()

    def _table_record_headers(self, item):
        if isinstance(item, dict):
            return [str(header) for header in (item.get("headers") or item.get("columns") or [])]
        return []

    def _build_ui(self):
        qt = self.qt
        self.status_bar = self.window.statusBar()
        self.job_timer = qt.QtCore.QTimer(self.window)
        self.job_timer.setInterval(100)
        self.job_timer.timeout.connect(lambda: self.poll_current_job())
        self.toolbar = self.window.addToolBar("Workflow")
        try:
            self.toolbar.setMovable(False)
        except Exception:
            pass

        self.action_new_sample = self._add_action("示例", self.load_sample_plan, "SP_FileDialogNewFolder")
        self.action_import_table = self._add_action("导入表格", self.import_table, "SP_DriveHDIcon")
        self.action_open = self._add_action("打开计划", self.open_plan, "SP_DialogOpenButton")
        self.action_save = self._add_action("保存计划", self.save_plan, "SP_DialogSaveButton")
        self.action_validate = self._add_action("校验", self.validate_plan, "SP_DialogApplyButton")
        self.action_preview = self._add_action("预览完整计划", self.preview_full_plan, "SP_MediaPlay")
        self.action_show_input = self._add_action("输入表", self.show_input_table, "SP_ArrowBack")
        self.action_show_preview = self._add_action("结果表", self.show_preview_table, "SP_ArrowForward")
        self._build_menu_bar()

        root = qt.QtWidgets.QWidget()
        root_layout = qt.QtWidgets.QHBoxLayout(root)
        root_layout.setContentsMargins(8, 8, 8, 8)
        root_layout.setSpacing(8)

        left = self._build_left_panel()
        right = self._build_right_panel()
        root_layout.addWidget(left, 0)
        root_layout.addWidget(right, 1)
        self.window.setCentralWidget(root)

    def _build_menu_bar(self):
        menu_bar = self.window.menuBar()
        file_menu = menu_bar.addMenu("文件")
        file_menu.addAction(self.action_new_sample)
        file_menu.addAction(self.action_import_table)
        file_menu.addAction(self.action_open)
        file_menu.addAction(self.action_save)

        workflow_menu = menu_bar.addMenu("工作流")
        workflow_menu.addAction(self.action_validate)
        workflow_menu.addAction(self.action_preview)

        view_menu = menu_bar.addMenu("视图")
        view_menu.addAction(self.action_show_input)
        view_menu.addAction(self.action_show_preview)

    def _add_action(self, text, callback, icon_name=""):
        action = self.qt.QtGui.QAction(self._standard_icon(icon_name), text, self.window)
        action.triggered.connect(lambda checked=False: callback())
        self.toolbar.addAction(action)
        return action

    def _standard_icon(self, icon_name):
        if not icon_name:
            return self.qt.QtGui.QIcon()
        style_enum = getattr(self.qt.QtWidgets.QStyle, "StandardPixmap", None)
        value = None
        if style_enum is not None:
            value = getattr(style_enum, icon_name, None)
        if value is None:
            value = getattr(self.qt.QtWidgets.QStyle, icon_name, None)
        if value is None:
            return self.qt.QtGui.QIcon()
        return self.window.style().standardIcon(value)

    def _make_node_tool_button(self, tooltip, callback, icon_name):
        button = self.qt.QtWidgets.QToolButton()
        button.setIcon(self._standard_icon(icon_name))
        button.setToolTip(str(tooltip or ""))
        button.setAccessibleName(str(tooltip or ""))
        button.setAutoRaise(True)
        button.setFixedSize(28, 28)
        button.setIconSize(self.qt.QtCore.QSize(18, 18))
        try:
            button.setToolButtonStyle(qt_enum(self.qt, "ToolButtonStyle", "ToolButtonIconOnly"))
        except Exception:
            pass
        button.clicked.connect(lambda checked=False: callback())
        return button

    def _node_enabled_icon(self, enabled):
        enabled = bool(enabled)
        cache_key = "enabled" if enabled else "disabled"
        if cache_key in self.node_enabled_icon_cache:
            return self.node_enabled_icon_cache[cache_key]
        size = 20
        pixmap = self.qt.QtGui.QPixmap(size, size)
        pixmap.fill(qt_enum(self.qt, "GlobalColor", "transparent"))
        painter = self.qt.QtGui.QPainter(pixmap)
        render_hint_group = getattr(self.qt.QtGui.QPainter, "RenderHint", None)
        antialiasing = getattr(render_hint_group, "Antialiasing", None) if render_hint_group is not None else None
        if antialiasing is None:
            antialiasing = getattr(self.qt.QtGui.QPainter, "Antialiasing")
        painter.setRenderHint(antialiasing, True)
        fill_color = "#f6ffed" if enabled else "#fff1f0"
        border_color = "#52c41a" if enabled else "#d92d20"
        text_color = "#237804" if enabled else "#b42318"
        painter.setBrush(self.qt.QtGui.QBrush(self.qt.QtGui.QColor(fill_color)))
        painter.setPen(self.qt.QtGui.QPen(self.qt.QtGui.QColor(border_color), 1.6))
        painter.drawEllipse(2, 2, size - 4, size - 4)
        font = painter.font()
        font.setBold(True)
        font.setPointSize(12 if enabled else 13)
        painter.setFont(font)
        painter.setPen(self.qt.QtGui.QColor(text_color))
        painter.drawText(pixmap.rect(), qt_enum(self.qt, "AlignmentFlag", "AlignCenter"), "√" if enabled else "×")
        painter.end()
        icon = self.qt.QtGui.QIcon(pixmap)
        self.node_enabled_icon_cache[cache_key] = icon
        return icon

    def _refresh_node_enabled_tool_button(self):
        button = self.node_action_buttons.get("启用/禁用")
        if button is None:
            return
        index = self.selected_node_index()
        nodes = self.current_plan.get("nodes", []) or []
        has_node = index is not None and 0 <= index < len(nodes)
        enabled = True
        if has_node:
            enabled = bool(nodes[index].get("enabled", True))
        button.setIcon(self._node_enabled_icon(enabled))
        label = "√ 已启用，点击后禁用当前节点" if enabled else "× 已禁用，点击后启用当前节点"
        if not has_node:
            label = "启用/禁用"
        button.setToolTip(label)
        button.setAccessibleName(label)

    def _polish_node_views(self):
        self.catalog_tree.setAlternatingRowColors(True)
        self.node_list.setAlternatingRowColors(True)
        self.node_list.setStyleSheet(
            "QListWidget#workflowNodeList { border: 1px solid #d0d5dd; background: #ffffff; }"
            "QListWidget#workflowNodeList::item { padding: 6px 8px; margin: 1px 2px; border-radius: 4px; }"
            "QListWidget#workflowNodeList::item:selected { background: #2f6fed; color: white; }"
            "QListWidget#workflowNodeList::item:selected:!active { background: #8ab4ff; color: #101828; }"
            "QTreeWidget#nodeCatalogTree { border: 1px solid #d0d5dd; background: #ffffff; }"
            "QTreeWidget#nodeCatalogTree::item { padding: 4px 6px; }"
            "QTreeWidget#nodeCatalogTree::item:selected { background: #e7f0ff; color: #101828; }"
        )

    def _build_left_panel(self):
        qt = self.qt
        panel = qt.QtWidgets.QWidget()
        panel.setMinimumWidth(360)
        panel.setMaximumWidth(430)
        layout = qt.QtWidgets.QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        source_group = qt.QtWidgets.QGroupBox("1. 输入数据源")
        source_layout = qt.QtWidgets.QVBoxLayout(source_group)
        self.input_summary_label = qt.QtWidgets.QLabel("")
        self.input_summary_label.setWordWrap(True)
        input_db_row = qt.QtWidgets.QHBoxLayout()
        self.input_db_path_edit = qt.QtWidgets.QLineEdit()
        self.input_db_path_edit.setPlaceholderText("输入 SQLite 数据库路径")
        self.input_db_path_edit.setToolTip("输入数据源使用的 SQLite 数据库，不再复用输出数据库路径")
        self.choose_input_db_button = qt.QtWidgets.QPushButton("...")
        self.choose_input_db_button.setMaximumWidth(36)
        self.refresh_input_tables_button = qt.QtWidgets.QPushButton("刷新")
        self.input_db_path_edit.editingFinished.connect(lambda: self.apply_input_db_path_from_edit(show_status=False))
        self.choose_input_db_button.clicked.connect(lambda checked=False: self.choose_input_db_path())
        self.refresh_input_tables_button.clicked.connect(lambda checked=False: self.apply_input_db_path_from_edit(show_status=True))
        input_db_row.addWidget(qt.QtWidgets.QLabel("输入库："))
        input_db_row.addWidget(self.input_db_path_edit, 1)
        input_db_row.addWidget(self.choose_input_db_button)
        input_db_row.addWidget(self.refresh_input_tables_button)
        source_table_row = qt.QtWidgets.QHBoxLayout()
        self.input_table_combo = qt.QtWidgets.QComboBox()
        self.input_table_combo.setMinimumWidth(180)
        self.input_table_combo.setToolTip("从输入 SQLite 数据库选择表作为工作流输入")
        self.load_input_table_button = qt.QtWidgets.QPushButton("载入")
        self.load_input_table_button.clicked.connect(lambda checked=False: self.load_selected_input_table())
        source_table_row.addWidget(qt.QtWidgets.QLabel("选择表："))
        source_table_row.addWidget(self.input_table_combo, 1)
        source_table_row.addWidget(self.load_input_table_button)
        source_button_row = qt.QtWidgets.QHBoxLayout()
        self.data_source_manager_button = qt.QtWidgets.QPushButton("输入数据源管理")
        self.data_source_manager_button.clicked.connect(lambda checked=False: self.open_data_source_manager())
        reload_button = qt.QtWidgets.QPushButton("重新载入示例输入")
        reload_button.clicked.connect(lambda checked=False: self.reload_sample_input())
        source_button_row.addWidget(self.data_source_manager_button)
        source_button_row.addWidget(reload_button)
        source_layout.addWidget(self.input_summary_label)
        source_layout.addLayout(input_db_row)
        source_layout.addLayout(source_table_row)
        source_layout.addLayout(source_button_row)

        node_group = qt.QtWidgets.QGroupBox("2. 工作流节点")
        node_layout = qt.QtWidgets.QVBoxLayout(node_group)
        self.node_type_combo = qt.QtWidgets.QComboBox(node_group)
        self.node_type_combo.setMinimumWidth(220)
        self.node_type_combo.currentIndexChanged.connect(lambda index: self.show_selected_node_type_detail())
        self.node_type_combo.hide()
        self.add_node_button = qt.QtWidgets.QPushButton("添加节点", node_group)
        self.add_node_button.clicked.connect(lambda checked=False: self.add_selected_node_type())
        self.add_node_button.hide()
        refresh_row = qt.QtWidgets.QHBoxLayout()
        self.refresh_schema_button = qt.QtWidgets.QPushButton("刷新节点")
        self.refresh_schema_button.clicked.connect(lambda checked=False: self.refresh_catalog())
        self.refresh_plugin_button = qt.QtWidgets.QPushButton("刷新插件")
        self.refresh_plugin_button.clicked.connect(lambda checked=False: self.refresh_plugins())
        refresh_row.addStretch(1)
        refresh_row.addWidget(self.refresh_schema_button)
        refresh_row.addWidget(self.refresh_plugin_button)

        self.catalog_tree = qt.QtWidgets.QTreeWidget()
        self.catalog_tree.setHeaderHidden(True)
        self.catalog_tree.setMaximumHeight(190)
        self.catalog_tree.setObjectName("nodeCatalogTree")
        self.catalog_tree.itemDoubleClicked.connect(lambda item, column: self.add_catalog_node(item))
        self.catalog_tree.itemSelectionChanged.connect(self.show_catalog_node_detail)

        self.node_list = qt.QtWidgets.QListWidget()
        self.node_list.setObjectName("workflowNodeList")
        self.node_list.setSelectionMode(qt.QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
        self.node_list.setUniformItemSizes(True)
        self.node_list.setSpacing(2)
        self.node_list.currentRowChanged.connect(self.show_node_config)
        self._polish_node_views()

        node_list_tools = qt.QtWidgets.QHBoxLayout()
        node_list_tools.addStretch(1)
        for text, callback, icon_name in [
            ("删除", self.delete_selected_node, "SP_TrashIcon"),
            ("上移", self.move_selected_node_up, "SP_ArrowUp"),
            ("下移", self.move_selected_node_down, "SP_ArrowDown"),
            ("启用/禁用", self.toggle_selected_node_enabled, ""),
        ]:
            button = self._make_node_tool_button(text, callback, icon_name)
            node_list_tools.addWidget(button)
            self.node_action_buttons[text] = button

        node_buttons_b = qt.QtWidgets.QHBoxLayout()
        for text, callback in [
            ("复制节点", self.copy_selected_node),
            ("清空节点", self.clear_nodes),
            ("预览到当前节点", self.preview_to_selected_node),
        ]:
            button = qt.QtWidgets.QPushButton(text)
            button.clicked.connect(lambda checked=False, cb=callback: cb())
            node_buttons_b.addWidget(button)
            self.node_action_buttons[text] = button

        node_layout.addWidget(self.catalog_tree, 0)
        node_layout.addLayout(node_list_tools)
        node_layout.addWidget(self.node_list, 1)
        node_layout.addLayout(refresh_row)
        node_layout.addLayout(node_buttons_b)

        template_group = qt.QtWidgets.QGroupBox("3. 计划模板")
        template_layout = qt.QtWidgets.QVBoxLayout(template_group)
        template_buttons = qt.QtWidgets.QHBoxLayout()
        save_template = qt.QtWidgets.QPushButton("保存计划模板")
        load_template = qt.QtWidgets.QPushButton("载入计划模板")
        refresh_templates = qt.QtWidgets.QPushButton("刷新模板")
        save_template.clicked.connect(lambda checked=False: self.save_plan())
        load_template.clicked.connect(lambda checked=False: self.open_plan())
        refresh_templates.clicked.connect(lambda checked=False: self.refresh_template_list())
        template_buttons.addWidget(save_template)
        template_buttons.addWidget(load_template)
        template_buttons.addWidget(refresh_templates)
        self.plan_template_combo = qt.QtWidgets.QComboBox()
        self.load_selected_template_button = qt.QtWidgets.QPushButton("载入选中模板")
        self.load_selected_template_button.clicked.connect(lambda checked=False: self.load_selected_plan_template())
        template_layout.addLayout(template_buttons)
        template_layout.addWidget(self.plan_template_combo)
        template_layout.addWidget(self.load_selected_template_button)

        layout.addWidget(source_group)
        layout.addWidget(node_group, 1)
        layout.addWidget(template_group)
        return panel

    def _build_right_panel(self):
        qt = self.qt
        panel = qt.QtWidgets.QWidget()
        layout = qt.QtWidgets.QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.node_tabs = qt.QtWidgets.QTabWidget()

        config_page = qt.QtWidgets.QWidget()
        config_layout = qt.QtWidgets.QVBoxLayout(config_page)
        config_layout.setContentsMargins(8, 8, 8, 8)
        config_layout.setSpacing(6)
        self.config_header_label = qt.QtWidgets.QLabel("未选择节点")
        self.config_header_label.setWordWrap(True)
        self.config_form = NodeConfigForm(
            qt,
            headers=self.current_headers,
            plan=self.current_plan,
            action_handler=self._handle_config_field_action,
            engine_client=self.engine_client,
        )
        self.apply_config_button = qt.QtWidgets.QPushButton("应用节点配置")
        self.apply_config_button.clicked.connect(lambda checked=False: self.apply_node_config())
        self.legacy_plugin_config_button = qt.QtWidgets.QPushButton("兼容旧版设置")
        self.legacy_plugin_config_button.clicked.connect(lambda checked=False: self.open_legacy_plugin_config())
        self.legacy_plugin_config_button.setVisible(False)
        config_button_row = qt.QtWidgets.QHBoxLayout()
        config_button_row.addWidget(self.legacy_plugin_config_button)
        config_button_row.addWidget(self.apply_config_button, 1)
        config_layout.addWidget(self.config_header_label)
        config_layout.addWidget(self.config_form.widget, 1)
        config_layout.addLayout(config_button_row)

        detail_page = qt.QtWidgets.QWidget()
        detail_layout = qt.QtWidgets.QVBoxLayout(detail_page)
        detail_layout.setContentsMargins(8, 8, 8, 8)
        detail_layout.setSpacing(6)
        self.node_detail_title_label = qt.QtWidgets.QLabel("未选择节点")
        self.node_detail_title_label.setWordWrap(True)
        self.node_detail_title_label.setStyleSheet("font-weight: 600;")
        self.node_detail_meta_label = qt.QtWidgets.QLabel("")
        self.node_detail_meta_label.setWordWrap(True)
        self.node_detail_badges_label = qt.QtWidgets.QLabel("")
        self.node_detail_badges_label.setWordWrap(True)
        self.node_detail_sections = qt.QtWidgets.QTextBrowser()
        self.node_detail_sections.setOpenExternalLinks(False)
        self.node_detail_sections.setReadOnly(True)
        self.node_detail_sections.setMaximumHeight(190)
        self.node_detail_sections.anchorClicked.connect(self._handle_node_detail_link)
        self.plugin_config_view_tabs = qt.QtWidgets.QTabWidget()
        self.plugin_config_view_tabs.setVisible(False)
        self.plugin_config_view_tabs.setSizePolicy(
            qt.QtWidgets.QSizePolicy.Policy.Expanding,
            qt.QtWidgets.QSizePolicy.Policy.Ignored,
        )
        detail_layout.addWidget(self.node_detail_title_label)
        detail_layout.addWidget(self.node_detail_meta_label)
        detail_layout.addWidget(self.node_detail_badges_label)
        detail_layout.addWidget(self.node_detail_sections)
        detail_layout.addWidget(self.plugin_config_view_tabs, 1)

        self.node_tabs.addTab(config_page, "节点配置")
        self.node_tabs.addTab(detail_page, "节点说明")

        action_row = qt.QtWidgets.QHBoxLayout()
        for text, callback in [
            ("预览到当前节点", self.preview_to_selected_node),
            ("预览完整计划", self.preview_full_plan),
            ("执行计划", self.execute_plan),
            ("校验", self.validate_plan),
        ]:
            button = qt.QtWidgets.QPushButton(text)
            button.clicked.connect(lambda checked=False, cb=callback: cb())
            self.workflow_action_buttons.append(button)
            action_row.addWidget(button)
            self.run_action_buttons[text] = button
        self.cancel_job_button = qt.QtWidgets.QPushButton("取消任务")
        self.cancel_job_button.setEnabled(False)
        self.cancel_job_button.clicked.connect(lambda checked=False: self.cancel_current_job())
        action_row.addWidget(self.cancel_job_button)
        action_row.addStretch(1)

        progress_group = qt.QtWidgets.QGroupBox("执行进度")
        progress_layout = qt.QtWidgets.QVBoxLayout(progress_group)
        progress_layout.setContentsMargins(8, 6, 8, 6)
        progress_layout.setSpacing(4)
        self.workflow_progress_label = qt.QtWidgets.QLabel("等待执行")
        self.workflow_progress = qt.QtWidgets.QProgressBar()
        self.workflow_progress.setRange(0, 100)
        self.workflow_progress.setFixedHeight(10)
        self.workflow_progress.setTextVisible(False)
        self.node_progress_label = qt.QtWidgets.QLabel("节点进度")
        self.node_progress = qt.QtWidgets.QProgressBar()
        self.node_progress.setRange(0, 100)
        self.node_progress.setFixedHeight(10)
        self.node_progress.setTextVisible(False)
        progress_layout.addWidget(self.workflow_progress_label)
        progress_layout.addWidget(self.workflow_progress)
        progress_layout.addWidget(self.node_progress_label)
        progress_layout.addWidget(self.node_progress)

        output_page = qt.QtWidgets.QWidget()
        output_layout = qt.QtWidgets.QFormLayout(output_page)
        output_layout.setContentsMargins(8, 8, 8, 8)
        output_layout.setSpacing(6)
        output_panel = self.engine_client.build_output_panel_state()
        self.output_mode_meta = dict(output_panel.get("mode_meta") or {})
        self.output_mode_records = list(self.output_mode_meta.values())
        output_fields = {item.get("key"): item for item in (output_panel.get("fields") or [])}

        self.output_mode_combo = qt.QtWidgets.QComboBox()
        self.output_mode_combo.setEditable(False)
        self.output_mode_combo.addItems(output_fields.get("mode", {}).get("choices") or ["输出到主界面预览区", "保存为SQLite新表", "覆盖当前表", "导出为xlsx"])
        self.output_table_edit = qt.QtWidgets.QLineEdit("结果表")
        self.output_db_path_edit = qt.QtWidgets.QLineEdit()
        self.output_db_path_edit.setPlaceholderText("SQLite 数据库路径")
        self.output_path_edit = qt.QtWidgets.QLineEdit()
        self.output_path_edit.setPlaceholderText("xlsx 输出路径")
        self.backup_checkbox = qt.QtWidgets.QCheckBox()
        self.backup_checkbox.setChecked(True)

        self.output_db_path_button = qt.QtWidgets.QPushButton("...")
        self.output_db_path_button.setMaximumWidth(36)
        self.output_db_path_button.clicked.connect(lambda checked=False: self._trigger_output_field_action("db_path"))
        self.output_path_button = qt.QtWidgets.QPushButton("...")
        self.output_path_button.setMaximumWidth(36)
        self.output_path_button.clicked.connect(lambda checked=False: self._trigger_output_field_action("path"))

        db_path_row = qt.QtWidgets.QWidget()
        db_path_row_layout = qt.QtWidgets.QHBoxLayout(db_path_row)
        db_path_row_layout.setContentsMargins(0, 0, 0, 0)
        db_path_row_layout.setSpacing(4)
        db_path_row_layout.addWidget(self.output_db_path_edit, 1)
        db_path_row_layout.addWidget(self.output_db_path_button)

        path_row = qt.QtWidgets.QWidget()
        path_row_layout = qt.QtWidgets.QHBoxLayout(path_row)
        path_row_layout.setContentsMargins(0, 0, 0, 0)
        path_row_layout.setSpacing(4)
        path_row_layout.addWidget(self.output_path_edit, 1)
        path_row_layout.addWidget(self.output_path_button)

        self.output_form_fields = {
            "mode": {"label": qt.QtWidgets.QLabel(output_fields.get("mode", {}).get("label", "输出方式")), "editor": self.output_mode_combo, "schema": output_fields.get("mode", {}), "widget": self.output_mode_combo},
            "target": {"label": qt.QtWidgets.QLabel(output_fields.get("target", {}).get("label", "输出表名")), "editor": self.output_table_edit, "schema": output_fields.get("target", {}), "widget": self.output_table_edit},
            "db_path": {"label": qt.QtWidgets.QLabel(output_fields.get("db_path", {}).get("label", "数据库路径")), "editor": self.output_db_path_edit, "schema": output_fields.get("db_path", {}), "widget": db_path_row, "action_button": self.output_db_path_button},
            "path": {"label": qt.QtWidgets.QLabel(output_fields.get("path", {}).get("label", "输出文件")), "editor": self.output_path_edit, "schema": output_fields.get("path", {}), "widget": path_row, "action_button": self.output_path_button},
            "backup_before_overwrite": {"label": qt.QtWidgets.QLabel(output_fields.get("backup_before_overwrite", {}).get("label", "覆盖前自动备份旧表")), "editor": self.backup_checkbox, "schema": output_fields.get("backup_before_overwrite", {}), "widget": self.backup_checkbox},
        }
        for key in ["mode", "target", "db_path", "path", "backup_before_overwrite"]:
            field = self.output_form_fields[key]
            output_layout.addRow(field["label"], field.get("widget") or field["editor"])

        self.output_mode_combo.currentTextChanged.connect(lambda *_args: self._apply_output_form_state())
        self.output_db_path_edit.editingFinished.connect(lambda: self.refresh_preview_table_combo())
        self._apply_output_panel_state(output_panel)

        preview_page = qt.QtWidgets.QWidget()
        preview_layout = qt.QtWidgets.QVBoxLayout(preview_page)
        preview_layout.setContentsMargins(8, 8, 8, 8)
        preview_layout.setSpacing(6)
        preview_toolbar = qt.QtWidgets.QHBoxLayout()
        self.show_input_button = qt.QtWidgets.QPushButton("输入表")
        self.show_preview_button = qt.QtWidgets.QPushButton("结果表")
        self.show_input_button.clicked.connect(lambda checked=False: self.show_input_table())
        self.show_preview_button.clicked.connect(lambda checked=False: self.show_preview_table())
        self.preview_table_combo = qt.QtWidgets.QComboBox()
        self.preview_table_combo.currentIndexChanged.connect(lambda index: self.show_selected_preview_table())
        self.log_button = qt.QtWidgets.QPushButton("显示日志")
        self.log_button.clicked.connect(lambda checked=False: self.show_log_text())
        preview_toolbar.addWidget(self.show_input_button)
        preview_toolbar.addWidget(self.show_preview_button)
        preview_toolbar.addWidget(qt.QtWidgets.QLabel("查看表："))
        preview_toolbar.addWidget(self.preview_table_combo, 1)
        preview_toolbar.addWidget(self.log_button)

        self.table_title = qt.QtWidgets.QLabel("表格预览")
        self.table_view = qt.QtWidgets.QTableView()
        self.table_model = make_table_model(self.preview_headers, self.preview_rows, qt=self.qt, parent=self.table_view)
        self.table_view.setModel(self.table_model)
        configure_fast_table_view(self.qt, self.table_view)

        self.message_tabs = qt.QtWidgets.QTabWidget()
        self.message_tabs.setSizePolicy(
            qt.QtWidgets.QSizePolicy.Policy.Expanding,
            qt.QtWidgets.QSizePolicy.Policy.Expanding,
        )
        self.issue_text = qt.QtWidgets.QPlainTextEdit()
        self.issue_text.setReadOnly(True)
        self.log_text = qt.QtWidgets.QPlainTextEdit()
        self.log_text.setReadOnly(True)
        self.info_text = qt.QtWidgets.QPlainTextEdit()
        self.info_text.setReadOnly(True)
        for editor in [self.info_text, self.issue_text, self.log_text]:
            editor.setSizePolicy(
                qt.QtWidgets.QSizePolicy.Policy.Expanding,
                qt.QtWidgets.QSizePolicy.Policy.Expanding,
            )
        self.message_tabs.addTab(self.info_text, "说明")
        self.message_tabs.addTab(self.issue_text, "问题")
        self.message_tabs.addTab(self.log_text, "日志")
        preview_layout.addLayout(preview_toolbar)
        preview_layout.addWidget(self.table_title)
        preview_layout.addWidget(self.table_view, 1)

        message_page = qt.QtWidgets.QWidget()
        message_layout = qt.QtWidgets.QVBoxLayout(message_page)
        message_layout.setContentsMargins(8, 8, 8, 8)
        message_layout.setSpacing(6)
        message_layout.addWidget(self.message_tabs, 1)

        self.result_tabs = qt.QtWidgets.QTabWidget()
        self.result_tabs.addTab(preview_page, "预览")
        self.result_tabs.addTab(output_page, "输出")
        self.result_tabs.addTab(message_page, "消息")

        layout.addWidget(self.node_tabs, 2)
        layout.addLayout(action_row)
        layout.addWidget(progress_group)
        layout.addWidget(self.result_tabs, 3)
        return panel

    def refresh_all(self, *, selected_index=None):
        self.refresh_catalog()
        self.refresh_template_list(show_status=False)
        self.refresh_input_table_combo(show_status=False)
        self.refresh_node_list()
        if selected_index is not None and 0 <= int(selected_index) < self.node_list.count():
            self.node_list.setCurrentRow(int(selected_index))
        self.update_input_summary()
        self.refresh_preview_table_combo()
        self.update_table(self.current_headers, self.current_rows, title="输入表格")
        self.show_node_config(self.node_list.currentRow())
        self.status_bar.showMessage(self._plan_status_text())
        self.refresh_action_states()

    def _panel_state(self, *, selected_index=None):
        if selected_index is None:
            selected_index = self.selected_node_index()
        return self.engine_client.build_workflow_panel_state(
            plan=self.current_plan,
            current_headers=self.current_headers,
            current_rows=self.current_rows,
            selected_index=selected_index,
            preview_headers=self.last_preview_headers,
            preview_rows=self.last_preview_rows,
            current_plan_path=self.current_plan_path,
            include_unsupported=True,
            **self._table_context(),
        )

    def refresh_catalog(self):
        panel_state = self._panel_state()
        catalog = panel_state.get("catalog") or {}
        schemas = catalog.get("items") or []
        self.node_schema_by_id = {item.get("node_type_id"): item for item in schemas}
        self.node_type_combo.blockSignals(True)
        self.node_type_combo.clear()
        for item in schemas:
            self.node_type_combo.addItem(item.get("display_name") or item.get("node_type_id", ""), item.get("node_type_id", ""))
        self.node_type_combo.blockSignals(False)

        self.catalog_tree.clear()
        for group in catalog.get("groups") or []:
            group_name = group.get("group") or "其他"
            category_item = self.qt.QtWidgets.QTreeWidgetItem([group_name])
            category_item.setData(0, self.user_role, "")
            self.catalog_tree.addTopLevelItem(category_item)
            for item in group.get("items") or []:
                summary = item.get("summary", "")
                badges = " / ".join((item.get("badges") or [])[:2])
                detail = summary
                if badges:
                    detail = f"{summary} · {badges}" if summary else badges
                child = self.qt.QtWidgets.QTreeWidgetItem([f"{item.get('display_name')}\n{detail}"])
                child.setData(0, self.user_role, item.get("node_type_id", ""))
                child.setToolTip(0, format_node_detail(
                    item.get("node_type_id", ""),
                    display_name=item.get("display_name", ""),
                    category=group_name,
                    supported_headless=item.get("supported_headless"),
                ))
                category_item.addChild(child)
            category_item.setExpanded(True)
        self.show_selected_node_type_detail()

    def refresh_plugins(self):
        try:
            listed = self.engine_client.list_plugins(refresh=True)
            state = self.engine_client.build_plugin_list_state(listed).get("state") or {}
        except Exception as exc:
            state = {
                "status_message": "插件刷新失败",
                "message_panel": self.engine_client.build_message_panel_state(
                    mode="error",
                    title="插件刷新失败",
                    body=str(exc),
                    preferred_tab="issues",
                ).get("panel") or {},
            }
        self.refresh_catalog()
        panel = state.get("message_panel") or {}
        if panel:
            self._apply_message_panel(panel)
        status_message = str(state.get("status_message") or "")
        if status_message:
            self.status_bar.showMessage(status_message)

    def refresh_template_list(self, show_status=True):
        self.plan_template_combo.clear()
        listed = self.engine_client.list_plan_templates(self.plan_dir)
        state = self.engine_client.build_template_list_state(listed, show_status=show_status).get("state") or {}
        templates = state.get("templates") or []
        for item in templates:
            self.plan_template_combo.addItem(item["name"], item["path"])
        panel = state.get("message_panel") or {}
        if panel:
            self._apply_message_panel(panel)
        status_message = str(state.get("status_message") or "")
        if status_message:
            self.status_bar.showMessage(status_message)

    def update_input_summary(self):
        panel_state = self._panel_state()
        self.input_summary_label.setText(panel_state.get("input_summary", ""))

    def refresh_node_list(self):
        selected = self.node_list.currentRow()
        panel_state = self._panel_state(selected_index=selected if selected >= 0 else None)
        self.node_list.clear()
        for node_item in panel_state.get("node_items") or []:
            item = self.qt.QtWidgets.QListWidgetItem(node_item.get("summary_text", ""))
            item.setData(self.user_role, node_item.get("index"))
            if not bool(node_item.get("enabled", True)):
                item.setForeground(self.qt.QtGui.QBrush(self.qt.QtGui.QColor("#667085")))
                item.setBackground(self.qt.QtGui.QBrush(self.qt.QtGui.QColor("#f2f4f7")))
            self.node_list.addItem(item)
        if self.node_list.count():
            if selected < 0:
                selected = 0
            self.node_list.setCurrentRow(min(selected, self.node_list.count() - 1))
        else:
            self.config_form.set_node(None)
            self.config_header_label.setText("未选择节点")
            self._update_legacy_plugin_config_button({})
        self.refresh_action_states()

    def selected_node_index(self):
        row = self.node_list.currentRow()
        nodes = self.current_plan.get("nodes", []) or []
        if row < 0 or row >= len(nodes):
            return None
        return row

    def selected_node_indexes(self):
        rows = sorted({item.row() for item in self.node_list.selectedIndexes()})
        nodes = self.current_plan.get("nodes", []) or []
        return [row for row in rows if 0 <= row < len(nodes)]

    def current_node_type_id_from_combo(self):
        return str(self.node_type_combo.currentData() or "")

    def add_selected_node_type(self):
        self.add_node_by_type(self.current_node_type_id_from_combo())

    def add_catalog_node(self, item):
        self.add_node_by_type(str(item.data(0, self.user_role) or ""))

    def apply_plan_command(self, command, *, status_message=""):
        result = self.engine_client.apply_plan_command(
            self.current_plan,
            command,
            preview_headers=self.current_headers,
            **self._table_context(),
        )
        if not result.get("ok"):
            self._apply_feedback(self.engine_client.describe_plan_command_feedback(
                result,
                success_status=status_message,
                success_title="计划编辑",
                failure_status="计划编辑失败",
            ))
            return None
        self.current_plan = result.get("plan") or self.current_plan
        self._clear_node_config_preview_cache()
        self.refresh_node_list()
        selected = result.get("selected_index")
        if selected is not None and self.node_list.count():
            self.node_list.setCurrentRow(max(0, min(int(selected), self.node_list.count() - 1)))
        if status_message:
            self._apply_feedback(self.engine_client.describe_plan_command_feedback(
                result,
                success_status=status_message,
                success_title="计划编辑",
            ))
        self.refresh_action_states()
        return result

    def add_node_by_type(self, node_type_id):
        if not node_type_id:
            return
        nodes = self.current_plan.get("nodes", []) or []
        indexes = self.selected_node_indexes()
        insert_at = indexes[-1] + 1 if len(indexes) == 1 else len(nodes)
        result = self.apply_plan_command({
            "type": "insert_node",
            "node_type_id": node_type_id,
            "index": insert_at,
            "include_legacy_type": False,
        })
        if result:
            selected = result.get("selected_index")
            node = (self.current_plan.get("nodes", []) or [])[selected] if selected is not None else {}
            self.status_bar.showMessage(f"已添加节点：{node.get('name') or node_type_id}")

    def delete_selected_node(self):
        indexes = self.selected_node_indexes()
        if not indexes:
            return
        self.apply_plan_command({"type": "delete_nodes", "indexes": indexes}, status_message="节点已删除。")

    def move_selected_node_up(self):
        index = self.selected_node_index()
        if index is None or index <= 0:
            return
        self.apply_plan_command({"type": "move_node", "index": index, "direction": "up"}, status_message="节点已上移。")

    def move_selected_node_down(self):
        index = self.selected_node_index()
        nodes = self.current_plan.get("nodes", []) or []
        if index is None or index >= len(nodes) - 1:
            return
        self.apply_plan_command({"type": "move_node", "index": index, "direction": "down"}, status_message="节点已下移。")

    def toggle_selected_node_enabled(self):
        index = self.selected_node_index()
        if index is None:
            return
        self.apply_plan_command({"type": "toggle_node_enabled", "index": index}, status_message="节点启用状态已切换。")

    def copy_selected_node(self):
        index = self.selected_node_index()
        if index is None:
            return
        self.apply_plan_command({"type": "duplicate_node", "index": index}, status_message="节点已复制。")

    def clear_nodes(self):
        prompt = self.engine_client.describe_confirmation_prompt(
            action="clear_nodes",
            plan=self.current_plan,
        )
        if not self._confirm_prompt(prompt):
            return
        self.apply_plan_command({"type": "clear_nodes"}, status_message="节点已清空。")

    def _clear_node_config_preview_cache(self):
        self.node_config_preview_cache = {}

    def _node_config_headers_for_index(self, index):
        resolved = resolve_node_config_headers(
            selected_index=index,
            current_headers=self.current_headers,
            preview_cache=self.node_config_preview_cache,
            plan=self.current_plan,
        )
        return list(resolved.get("headers") or [])

    def show_node_config(self, row):
        panel_state = self._panel_state(selected_index=row)
        node = panel_state.get("selected_node")
        if row is None or row < 0 or node is None:
            self.config_form.set_node(None)
            self.config_header_label.setText("未选择节点")
            self.current_plugin_config_description = {}
            self._update_legacy_plugin_config_button({})
            self._clear_plugin_config_views()
            self.refresh_action_states(selected_indexes=[])
            return
        node_type_id = self._node_type_id_for_node(node)
        table_context = self._table_context()
        config_headers = self._node_config_headers_for_index(row)
        schema = panel_state.get("selected_schema") or self.node_schema_by_id.get(node_type_id, {})
        if not str(node_type_id or "").startswith("plugin."):
            try:
                schema = self.engine_client.get_node_ui_schema(
                    node_type_id,
                    preview_headers=config_headers,
                    table_names=table_context.get("table_names"),
                    table_columns=table_context.get("table_columns"),
                ) or schema
            except Exception:
                pass
        plugin_config_description = self._describe_plugin_config_for_node(node_type_id, node)
        self.current_plugin_config_description = copy.deepcopy(plugin_config_description if isinstance(plugin_config_description, dict) else {})
        if plugin_config_description.get("ok") and isinstance(plugin_config_description.get("node_ui_schema"), dict):
            schema = plugin_config_description["node_ui_schema"]
            schema = self._schema_with_plugin_config_hints(schema, plugin_config_description)
            self.node_schema_by_id[node_type_id] = schema
        display = schema.get("display_name") or node.get("type") or node_type_id
        self.config_header_label.setText(f"节点类型：{display}    节点名称：{node.get('name', '')}")
        self.config_form.set_node(
            node,
            headers=config_headers,
            table_names=table_context.get("table_names"),
            table_columns=table_context.get("table_columns"),
            plan=self.current_plan,
            schema=schema,
        )
        self._update_legacy_plugin_config_button(schema, plugin_config_description)
        self.show_node_detail(node_type_id, preview_headers=config_headers)
        self._append_plugin_config_detail(plugin_config_description)
        self._render_plugin_config_views(plugin_config_description)
        self.refresh_action_states(selected_indexes=[row])

    def _describe_plugin_config_for_node(self, node_type_id, node):
        if not str(node_type_id or "").startswith("plugin."):
            return {}
        try:
            return self.engine_client.describe_plugin_config(
                node_type_id,
                config=copy.deepcopy((node or {}).get("config") or {}),
                input_table=self._input_table_payload(),
                context=self._plugin_config_context_payload(),
            )
        except Exception:
            return {}

    def _schema_with_plugin_config_hints(self, schema, described):
        schema_copy = copy.deepcopy(schema if isinstance(schema, dict) else {})
        if not schema_copy or not isinstance(described, dict) or not described.get("ok"):
            return schema_copy
        hints_by_key = self._plugin_parameter_field_hints(described)
        if not hints_by_key:
            return schema_copy
        form = schema_copy.get("form") if isinstance(schema_copy.get("form"), dict) else {}
        for group in form.get("groups") or []:
            if not isinstance(group, dict):
                continue
            for field in group.get("fields") or []:
                if not isinstance(field, dict):
                    continue
                field_key = str(field.get("key") or "").strip()
                hint = hints_by_key.get(field_key)
                if not hint:
                    continue
                field.setdefault("protocol_hints", {})
                field["protocol_hints"]["plugin_config_ui_hints"] = copy.deepcopy(hint)
                self._merge_plugin_parameter_hint_into_field(field, hint)
        return schema_copy

    def _plugin_parameter_field_hints(self, described):
        ui_hints = self._plugin_config_ui_hints(described)
        parameter_hints = ui_hints.get("parameter_field_hints") if isinstance(ui_hints.get("parameter_field_hints"), dict) else {}
        fields = parameter_hints.get("fields") if isinstance(parameter_hints.get("fields"), list) else []
        if not fields:
            metadata = described.get("parameter_metadata") if isinstance(described.get("parameter_metadata"), dict) else {}
            metadata_hints = metadata.get("ui_hints") if isinstance(metadata.get("ui_hints"), dict) else {}
            fields = metadata_hints.get("fields") if isinstance(metadata_hints.get("fields"), list) else []
        result = {}
        for item in fields:
            if not isinstance(item, dict):
                continue
            field_key = str(item.get("field_key") or item.get("key") or "").strip()
            if field_key:
                result[field_key] = copy.deepcopy(item)
        return result

    def _merge_plugin_parameter_hint_into_field(self, field, hint):
        for meta_key in ("placeholder", "empty_text", "invalid_value_text", "width_hint", "unit", "min", "max", "step"):
            if meta_key in hint and meta_key not in field:
                field[meta_key] = copy.deepcopy(hint.get(meta_key))
        if hint.get("advanced"):
            field["advanced"] = True
        warning = str(hint.get("warning") or "").strip()
        if warning:
            existing = str(field.get("warning") or "").strip()
            if not existing:
                field["warning"] = warning
            elif warning not in existing:
                field["warning"] = existing + "\n" + warning

    def _append_plugin_config_detail(self, described):
        if not described.get("ok"):
            return
        rendered_sections = self._append_plugin_config_sections(described.get("config_sections"))
        self._append_plugin_warning_target_links(described.get("warning_items") or [])
        if rendered_sections:
            return
        lines = []
        plugin_extension = described.get("plugin_extension") if isinstance(described.get("plugin_extension"), dict) else {}
        views = [item for item in (described.get("views") or []) if isinstance(item, dict)]
        resources = [item for item in (described.get("resources") or []) if isinstance(item, dict)]
        actions = [item for item in (described.get("actions") or []) if isinstance(item, dict)]
        if views:
            lines.append("配置视图：" + "、".join(str(item.get("title") or item.get("view_id") or "") for item in views[:6]))
        if resources:
            lines.append("配置资源：" + "、".join(str(item.get("label") or item.get("resource_id") or "") for item in resources[:6]))
        manifest_line = self._plugin_protocol_manifest_summary(
            described.get("protocol_manifest") or plugin_extension.get("protocol_manifest")
        )
        if manifest_line:
            lines.append(manifest_line)
        patch_schema_line = self._plugin_protocol_schema_summary(plugin_extension.get("patch_schema"), "Patch协议")
        if patch_schema_line:
            lines.append(patch_schema_line)
        warning_schema_line = self._plugin_protocol_schema_summary(plugin_extension.get("warning_schema"), "警告协议")
        if warning_schema_line:
            lines.append(warning_schema_line)
        warning_items = [item for item in (described.get("warning_items") or []) if isinstance(item, dict)]
        if warning_items:
            warning_lines = []
            for item in warning_items[:4]:
                line = self._format_plugin_warning_item(item)
                if line:
                    warning_lines.append(line)
            if warning_lines:
                lines.append("配置警告：" + "；".join(warning_lines))
        compatibility_actions = [item for item in actions if str(item.get("kind") or "") == "compatibility"]
        config_actions = [item for item in actions if str(item.get("kind") or "") != "compatibility"]
        if compatibility_actions:
            lines.append("兼容动作：" + "、".join(str(item.get("label") or item.get("action_id") or "") for item in compatibility_actions[:6]))
            lifecycle_lines = []
            for item in compatibility_actions[:3]:
                line = self._plugin_compatibility_lifecycle_summary(item)
                if line:
                    lifecycle_lines.append(line)
            if lifecycle_lines:
                lines.append("兼容状态：" + "；".join(lifecycle_lines))
            compatibility_warnings = [
                str(item.get("warning") or "").strip()
                for item in compatibility_actions
                if str(item.get("warning") or "").strip()
            ]
            if compatibility_warnings:
                lines.append("兼容提示：" + "；".join(compatibility_warnings[:3]))
        if config_actions:
            lines.append("配置动作：" + "、".join(str(item.get("label") or item.get("action_id") or "") for item in config_actions[:6]))
        plugin_layout = self._plugin_config_layout(described)
        plugin_ui_hints = self._plugin_config_ui_hints(described)
        if plugin_layout:
            layout_parts = []
            default_view_id = str(plugin_layout.get("default_view_id") or "").strip()
            if default_view_id:
                layout_parts.append(f"默认视图 {default_view_id}")
            primary_views = [str(item) for item in (plugin_layout.get("primary_views") or []) if str(item).strip()]
            advanced_views = [str(item) for item in (plugin_layout.get("advanced_views") or []) if str(item).strip()]
            if primary_views:
                layout_parts.append("主要视图 " + "、".join(primary_views[:4]))
            if advanced_views:
                layout_parts.append("高级视图 " + "、".join(advanced_views[:4]))
            if layout_parts:
                lines.append("插件配置布局：" + "；".join(layout_parts))
        if plugin_ui_hints:
            hint_parts = []
            for key, label in [
                ("navigation", "导航"),
                ("density", "密度"),
                ("display_mode", "显示模式"),
            ]:
                value = str(plugin_ui_hints.get(key) or "").strip()
                if value:
                    hint_parts.append(f"{label} {value}")
            view_hints = plugin_ui_hints.get("view_hints") if isinstance(plugin_ui_hints.get("view_hints"), dict) else {}
            if view_hints:
                hint_parts.append(f"视图提示 {len(view_hints)} 个")
            if hint_parts:
                lines.append("插件UI提示：" + "；".join(hint_parts[:6]))
        parameter_metadata = described.get("parameter_metadata") if isinstance(described.get("parameter_metadata"), dict) else {}
        layout_index = parameter_metadata.get("layout_index") if isinstance(parameter_metadata.get("layout_index"), dict) else {}
        ui_hints = parameter_metadata.get("ui_hints") if isinstance(parameter_metadata.get("ui_hints"), dict) else {}
        if layout_index:
            group_order = [
                str(group.get("title") or "").strip()
                for group in (layout_index.get("groups") or [])
                if isinstance(group, dict) and str(group.get("title") or "").strip()
            ]
            if group_order:
                lines.append("参数布局：" + "、".join(group_order[:6]))
            advanced_groups = [
                str(group.get("title") or "").strip()
                for group in (layout_index.get("groups") or [])
                if isinstance(group, dict) and bool(group.get("advanced")) and str(group.get("title") or "").strip()
            ]
            if advanced_groups:
                lines.append("高级分组：" + "、".join(advanced_groups[:6]))
        if ui_hints:
            hint_fields = [
                str(item.get("label") or item.get("field_key") or "").strip()
                for item in (ui_hints.get("fields") or [])
                if isinstance(item, dict) and str(item.get("label") or item.get("field_key") or "").strip()
            ]
            if hint_fields:
                lines.append("参数提示：" + "、".join(hint_fields[:6]))
            hint_parts = []
            for key, label in [
                ("advanced_fields", "高级字段"),
                ("warning_fields", "警告字段"),
                ("placeholder_fields", "占位提示"),
                ("numeric_fields", "数值约束"),
                ("width_hint_fields", "宽度提示"),
            ]:
                values = [str(item) for item in (ui_hints.get(key) or []) if str(item).strip()]
                if values:
                    hint_parts.append(f"{label} {len(values)} 个")
            if hint_parts:
                lines.append("参数UI提示：" + "；".join(hint_parts[:6]))
        if not lines:
            return
        body = "<br>".join(html.escape(line) for line in lines if line)
        if body:
            self.node_detail_sections.append(f"<p><b>配置协议</b><br>{body}</p>")

    def _append_plugin_warning_target_links(self, warning_items):
        lines = []
        for item in warning_items:
            if not isinstance(item, dict):
                continue
            link = self._plugin_warning_target_link(item)
            if not link:
                continue
            text = html.escape(self._format_plugin_warning_item(item))
            if text:
                lines.append(f"{text} {link}")
        if lines:
            body = "<br>".join(lines[:6])
            self.node_detail_sections.append(f"<p><b>配置警告定位</b><br>{body}</p>")

    def _append_plugin_config_sections(self, sections):
        rendered = 0
        for section in sections or []:
            if not isinstance(section, dict):
                continue
            title = str(section.get("title") or "").strip()
            lines = [
                str(line).strip()
                for line in (section.get("lines") or [])
                if str(line).strip()
            ]
            if not title or not lines:
                continue
            body = "<br>".join(html.escape(line) for line in lines)
            self.node_detail_sections.append(f"<p><b>{html.escape(title)}</b><br>{body}</p>")
            rendered += 1
        return rendered > 0

    def _plugin_compatibility_lifecycle_summary(self, item):
        if not isinstance(item, dict):
            return ""
        parts = []
        lifecycle = str(item.get("lifecycle") or "").strip()
        migration_target = str(item.get("migration_target") or "").strip()
        remove_when = str(item.get("remove_when") or "").strip()
        if lifecycle:
            parts.append(f"生命周期 {lifecycle}")
        if migration_target:
            parts.append(f"迁移目标 {migration_target}")
        if remove_when:
            parts.append(f"退场条件 {remove_when}")
        return "，".join(parts)

    def _plugin_protocol_schema_summary(self, schema, title):
        if not isinstance(schema, dict):
            return ""
        kind = str(schema.get("kind") or schema.get("protocol_family") or "").strip()
        parts = [title + (f"：{kind}" if kind else "")]
        operations = []
        for item in schema.get("operations") or []:
            if isinstance(item, dict):
                operation = str(item.get("operation") or "").strip()
            else:
                operation = str(item or "").strip()
            if operation:
                operations.append(operation)
        if operations:
            parts.append("操作 " + "、".join(operations[:6]))
        fields = []
        for item in schema.get("fields") or []:
            if isinstance(item, dict):
                key = str(item.get("key") or "").strip()
            else:
                key = str(item or "").strip()
            if key:
                fields.append(key)
        if fields:
            parts.append("字段 " + "、".join(fields[:8]))
        sections = schema.get("sections")
        if isinstance(sections, dict) and sections:
            parts.append("区域 " + "、".join(str(key) for key in list(sections.keys())[:6]))
        return "；".join(part for part in parts if part)

    def _plugin_protocol_manifest_summary(self, manifest):
        if not isinstance(manifest, dict):
            return ""
        parts = []
        schema_version = str(manifest.get("schema_version") or "").strip()
        if schema_version:
            parts.append(f"协议清单：{schema_version}")
        interfaces = manifest.get("interfaces") if isinstance(manifest.get("interfaces"), dict) else {}
        enabled_interfaces = [
            key
            for key, enabled in interfaces.items()
            if enabled and str(key or "").strip()
        ]
        if enabled_interfaces:
            parts.append("接口 " + "、".join(enabled_interfaces[:6]))
        views = [item for item in (manifest.get("views") or []) if isinstance(item, dict)]
        if views:
            parts.append(f"视图 {len(views)} 个")
        models = [str(item) for item in (manifest.get("models") or []) if str(item).strip()]
        if models:
            parts.append("模型 " + "、".join(models[:6]))
        patch = manifest.get("patch") if isinstance(manifest.get("patch"), dict) else {}
        patch_sections = [str(item) for item in (patch.get("sections") or []) if str(item).strip()]
        if patch_sections:
            parts.append("Patch区域 " + "、".join(patch_sections[:6]))
        config_effect = manifest.get("config_effect") if isinstance(manifest.get("config_effect"), dict) else {}
        provider = str(config_effect.get("provider") or "").strip()
        if provider:
            parts.append("效果预览 " + provider)
        return "；".join(parts)

    def _format_plugin_warning_item(self, item):
        if not isinstance(item, dict):
            return ""
        message = str(item.get("message") or "").strip()
        if not message:
            return ""
        details = []
        target = item.get("target") if isinstance(item.get("target"), dict) else {}
        view_id = str(item.get("view_id") or target.get("view_id") or "").strip()
        field = str(item.get("field") or target.get("field") or "").strip()
        path = str(item.get("path") or target.get("path") or target.get("focus_path") or "").strip()
        config_path = item.get("config_path")
        if config_path in (None, "", []):
            config_path = target.get("config_path")
        code = str(item.get("code") or "").strip()
        if view_id:
            details.append(f"视图 {view_id}")
        if field:
            details.append(f"字段 {field}")
        if path:
            details.append(f"路径 {path}")
        config_path_text = self._format_plugin_config_path(config_path)
        if config_path_text:
            details.append(f"配置 {config_path_text}")
        if code:
            details.append(f"代码 {code}")
        return f"{message}（{'；'.join(details)}）" if details else message

    def _plugin_warning_target_link(self, item):
        target = item.get("target") if isinstance(item, dict) and isinstance(item.get("target"), dict) else {}
        if not target.get("can_focus_view"):
            return ""
        view_id = str(target.get("view_id") or "").strip()
        if not view_id:
            return ""
        key = f"plugin_warning_{len(self.plugin_warning_targets_by_link)}"
        self.plugin_warning_targets_by_link[key] = copy.deepcopy(target)
        return f'<a href="dfk-plugin-warning:{html.escape(key, quote=True)}">定位</a>'

    def _handle_node_detail_link(self, url):
        text = url.toString() if hasattr(url, "toString") else str(url or "")
        prefix = "dfk-plugin-warning:"
        if not text.startswith(prefix):
            return
        key = text[len(prefix):]
        target = self.plugin_warning_targets_by_link.get(key)
        if self._focus_plugin_config_target(target):
            self.status_bar.showMessage("已定位到插件配置警告。")

    def _format_plugin_config_path(self, value):
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, (list, tuple)):
            parts = [str(part).strip() for part in value if str(part).strip()]
            return ".".join(parts)
        return ""

    def _clear_plugin_config_views(self):
        if not hasattr(self, "plugin_config_view_tabs"):
            return
        self.plugin_config_view_widgets_by_id = {}
        self.plugin_config_view_tabs.clear()
        self.plugin_config_view_tabs.setVisible(False)

    def _render_plugin_config_views(self, described):
        self._clear_plugin_config_views()
        if not described.get("ok"):
            return
        warnings_by_view = self._plugin_warning_items_by_view(described)
        view_hints = self._plugin_config_view_hints(described)
        default_view_id = self._plugin_config_default_view_id(described)
        added = 0
        default_tab_index = -1
        for view in self._ordered_plugin_config_views(described):
            if not isinstance(view, dict):
                continue
            kind = str(view.get("kind") or "")
            view_id = str(view.get("view_id") or "")
            if view_id == "plugin.params":
                continue
            widget = self._make_plugin_config_view_widget(view, described)
            if widget is None:
                continue
            widget.plugin_config_view_id = view_id
            widget.plugin_config_view_kind = kind
            widget.plugin_config_editor_kind = str(view.get("editor_kind") or "")
            title = str(view.get("title") or view_id or kind or "配置")
            tab_index = self.plugin_config_view_tabs.addTab(widget, title[:24])
            if view_id:
                self.plugin_config_view_widgets_by_id[view_id] = widget
            self._apply_plugin_config_tab_warning(tab_index, warnings_by_view.get(view_id) or [])
            self._apply_plugin_config_tab_hint(tab_index, view, view_hints.get(view_id) or {})
            if view_id and view_id == default_view_id:
                default_tab_index = tab_index
            added += 1
        if default_tab_index >= 0:
            self.plugin_config_view_tabs.setCurrentIndex(default_tab_index)
        self.plugin_config_view_tabs.setVisible(added > 0)

    def _ordered_plugin_config_views(self, described):
        views = [view for view in (described or {}).get("views") or [] if isinstance(view, dict)]
        layout = self._plugin_config_layout(described)
        view_order = [str(item).strip() for item in (layout.get("view_order") or []) if str(item).strip()]
        if not view_order:
            return views
        order_index = {view_id: index for index, view_id in enumerate(view_order)}
        return sorted(
            views,
            key=lambda view: (
                order_index.get(str(view.get("view_id") or ""), len(order_index)),
                views.index(view),
            ),
        )

    def _plugin_config_layout(self, described):
        if not isinstance(described, dict):
            return {}
        layout = described.get("layout") if isinstance(described.get("layout"), dict) else {}
        if layout:
            return layout
        extension = described.get("plugin_extension") if isinstance(described.get("plugin_extension"), dict) else {}
        return extension.get("layout") if isinstance(extension.get("layout"), dict) else {}

    def _plugin_config_ui_hints(self, described):
        if not isinstance(described, dict):
            return {}
        ui_hints = described.get("ui_hints") if isinstance(described.get("ui_hints"), dict) else {}
        if ui_hints:
            return ui_hints
        extension = described.get("plugin_extension") if isinstance(described.get("plugin_extension"), dict) else {}
        return extension.get("ui_hints") if isinstance(extension.get("ui_hints"), dict) else {}

    def _plugin_config_view_hints(self, described):
        ui_hints = self._plugin_config_ui_hints(described)
        view_hints = ui_hints.get("view_hints") if isinstance(ui_hints.get("view_hints"), dict) else {}
        return view_hints

    def _plugin_config_default_view_id(self, described):
        layout = self._plugin_config_layout(described)
        ui_hints = self._plugin_config_ui_hints(described)
        return str(layout.get("default_view_id") or ui_hints.get("default_view_id") or "").strip()

    def _focus_plugin_config_target(self, target):
        if not isinstance(target, dict) or not target.get("can_focus_view"):
            return False
        view_id = str(target.get("view_id") or "").strip()
        if not view_id or not hasattr(self, "plugin_config_view_tabs"):
            return False
        widget = self.plugin_config_view_widgets_by_id.get(view_id)
        tab_index = -1
        for index in range(self.plugin_config_view_tabs.count()):
            tab_widget = self.plugin_config_view_tabs.widget(index)
            if tab_widget is widget or str(getattr(tab_widget, "plugin_config_view_id", "") or "") == view_id:
                tab_index = index
                widget = tab_widget
                break
        if tab_index < 0 or widget is None:
            return False
        if hasattr(self, "node_tabs") and self.node_tabs.count() > 1:
            self.node_tabs.setCurrentIndex(1)
        self.plugin_config_view_tabs.setCurrentIndex(tab_index)
        self._focus_plugin_config_view_item(widget, target)
        return True

    def _focus_plugin_config_view_item(self, widget, target):
        table = getattr(widget, "plugin_config_table", None)
        if table is None:
            return False
        row = self._plugin_config_target_row(widget, target)
        if row < 0 or row >= table.rowCount():
            return False
        table.selectRow(row)
        table.setFocus()
        item = table.item(row, 0)
        if item is not None:
            table.scrollToItem(item)
        detail_tabs = getattr(widget, "plugin_config_detail_tabs", None)
        if detail_tabs is not None:
            self._refresh_plugin_structured_detail_sections(widget)
        return True

    def _plugin_config_target_row(self, widget, target):
        if not isinstance(target, dict):
            return -1
        for key in ("to_index", "target_index"):
            value = target.get(key)
            if value in (None, ""):
                continue
            try:
                return int(value)
            except (TypeError, ValueError):
                pass
        target_id = str(target.get("target_id") or "").strip()
        if not target_id:
            return -1
        items = getattr(widget, "plugin_config_items", []) or []
        for row, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            if self._plugin_structured_target_id(widget, row) == target_id:
                return row
            for field in ("id", "name", "key"):
                if str(item.get(field) or "").strip() == target_id:
                    return row
        return -1

    def _plugin_warning_items_by_view(self, described):
        result = {}
        for item in described.get("warning_items") or []:
            if not isinstance(item, dict):
                continue
            target = item.get("target") if isinstance(item.get("target"), dict) else {}
            view_id = str(item.get("view_id") or target.get("view_id") or "").strip()
            line = self._format_plugin_warning_item(item)
            if view_id and line:
                result.setdefault(view_id, []).append(line)
        return result

    def _apply_plugin_config_tab_warning(self, tab_index, warning_lines):
        if tab_index < 0 or not warning_lines:
            return
        tooltip = "\n".join(str(line) for line in warning_lines[:6] if str(line).strip())
        if tooltip:
            self.plugin_config_view_tabs.setTabToolTip(tab_index, tooltip)
        try:
            standard_pixmap = getattr(
                self.qt.QtWidgets.QStyle.StandardPixmap,
                "SP_MessageBoxWarning",
            )
        except Exception:
            standard_pixmap = getattr(self.qt.QtWidgets.QStyle, "SP_MessageBoxWarning", None)
        if standard_pixmap is None:
            return
        try:
            icon = self.window.style().standardIcon(standard_pixmap)
        except Exception:
            return
        if not icon.isNull():
            self.plugin_config_view_tabs.setTabIcon(tab_index, icon)

    def _apply_plugin_config_tab_hint(self, tab_index, view, hint):
        if tab_index < 0 or not isinstance(hint, dict):
            return
        lines = []
        for key, label in [
            ("description", ""),
            ("empty_text", "空状态"),
            ("role", "角色"),
            ("primary_action", "主动作"),
        ]:
            value = str(hint.get(key) or "").strip()
            if not value:
                continue
            lines.append(f"{label}：{value}" if label else value)
        if not lines:
            return
        existing = str(self.plugin_config_view_tabs.tabToolTip(tab_index) or "").strip()
        tooltip = "\n".join([part for part in [existing, "\n".join(lines)] if part])
        self.plugin_config_view_tabs.setTabToolTip(tab_index, tooltip)
        title = str(hint.get("title") or view.get("title") or "").strip()
        if title:
            self.plugin_config_view_tabs.setTabText(tab_index, title[:24])

    def _make_plugin_config_view_widget(self, view, described):
        kind = str(view.get("kind") or "")
        if kind == "summary":
            summary = copy.deepcopy(
                view.get("summary")
                or described.get("summary")
                or (described.get("plugin_extension") or {}).get("summary")
                or {}
            )
            state = view.get("state") if isinstance(view.get("state"), dict) else {}
            if state.get("schema_version") == "plugin_config_effect_state.v1" and state.get("status_message"):
                summary.setdefault("状态", state.get("status_message"))
            return self._make_plugin_summary_widget(summary)
        if kind == "form":
            return self._make_plugin_form_view_widget(view)
        if kind == "structured_list":
            return self._make_plugin_structured_list_widget(view, described)
        if kind == "text_preview":
            return self._make_plugin_text_preview_widget(view)
        if kind == "resource_list":
            return self._make_plugin_resource_list_widget(view, described)
        return self._make_plugin_protocol_text_widget(view)

    def _plugin_config_action_id_for_view(self, view, described=None):
        if not isinstance(view, dict):
            return ""
        explicit_action_id = str(view.get("action_id") or "").strip()
        if explicit_action_id:
            return explicit_action_id
        view_id = str(view.get("view_id") or "").strip()
        editor_kind = str(view.get("editor_kind") or "").strip()
        for action in (described or {}).get("actions") or []:
            if not isinstance(action, dict):
                continue
            action_id = str(action.get("action_id") or "").strip()
            if not action_id:
                continue
            if view_id and str(action.get("view_id") or "").strip() == view_id:
                return action_id
            if editor_kind and str(action.get("editor_kind") or "").strip() == editor_kind:
                return action_id
        return ""

    def _make_plugin_summary_widget(self, summary):
        qt = self.qt
        table = qt.QtWidgets.QTableWidget()
        rows = [(str(key), self._format_plugin_protocol_value(value)) for key, value in (summary or {}).items()]
        table.setColumnCount(2)
        table.setHorizontalHeaderLabels(["项目", "值"])
        table.setRowCount(len(rows))
        for row, (key, value) in enumerate(rows):
            table.setItem(row, 0, qt.QtWidgets.QTableWidgetItem(key))
            table.setItem(row, 1, qt.QtWidgets.QTableWidgetItem(value))
        self._polish_plugin_protocol_table(table)
        return table

    def _make_plugin_form_view_widget(self, view):
        qt = self.qt
        form_payload = view.get("form") if isinstance(view.get("form"), dict) else {}
        values = view.get("values") if isinstance(view.get("values"), dict) else {}
        rows = []
        for group in form_payload.get("groups") or []:
            if not isinstance(group, dict):
                continue
            group_label = str(group.get("title") or group.get("label") or group.get("group") or "").strip()
            for field in group.get("fields") or []:
                if isinstance(field, dict):
                    rows.append((group_label, field))
        if not rows:
            for field in view.get("fields") or []:
                if isinstance(field, dict):
                    rows.append(("", field))
        if not rows and values:
            rows = [("", {"key": key, "label": key, "value": value}) for key, value in values.items()]
        if not rows:
            return self._make_plugin_protocol_text_widget(view)

        table = qt.QtWidgets.QTableWidget()
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels(["分组", "字段", "值", "说明"])
        table.setRowCount(len(rows))
        for row, (group_label, field) in enumerate(rows):
            key = str(field.get("key") or field.get("name") or field.get("param_key") or "").strip()
            label = str(field.get("label") or key).strip()
            if "value" in field:
                value = field.get("value")
            elif key and key in values:
                value = values.get(key)
            else:
                value = field.get("default", "")
            help_text = field.get("help") or field.get("description") or field.get("warning") or field.get("placeholder") or ""
            for col, value_text in enumerate([
                group_label,
                label,
                self._format_plugin_protocol_value(value),
                self._format_plugin_protocol_value(help_text),
            ]):
                table.setItem(row, col, qt.QtWidgets.QTableWidgetItem(value_text))
        self._polish_plugin_protocol_table(table)
        return table

    def _make_plugin_structured_list_widget(self, view, described=None):
        qt = self.qt
        item_schema = view.get("item_schema") if isinstance(view.get("item_schema"), dict) else {}
        supported_operations = {
            str(item)
            for item in (view.get("patch_operations") or view.get("supported_patch_operations") or [])
            if str(item or "")
        }
        action_state = view.get("action_state") if isinstance(view.get("action_state"), dict) else {}
        action_buttons = action_state.get("buttons") if isinstance(action_state.get("buttons"), dict) else {}
        schema_columns = [item for item in (item_schema.get("columns") or []) if isinstance(item, dict)]
        can_update_item = bool({"update_item", "replace_item"} & supported_operations)
        if can_update_item and schema_columns:
            columns = list(schema_columns)
        else:
            columns = [item for item in (view.get("columns") or []) if isinstance(item, dict)]
            if not columns:
                columns = [item for item in (item_schema.get("display_columns") or []) if isinstance(item, dict)]
            if not columns:
                columns = list(schema_columns)
        items = [item for item in (view.get("items") or []) if isinstance(item, dict)]
        if not columns and items:
            columns = [{"key": key, "label": key} for key in items[0].keys()]
        editable = bool(can_update_item and columns)
        frame = qt.QtWidgets.QWidget()
        layout = qt.QtWidgets.QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        summary_parts = []
        if view.get("item_count") is not None:
            summary_parts.append(f"共 {view.get('item_count')} 项")
        if view.get("editor_kind"):
            summary_parts.append(f"编辑器：{view.get('editor_kind')}")
        if summary_parts:
            label = qt.QtWidgets.QLabel("；".join(summary_parts))
            label.setWordWrap(True)
            layout.addWidget(label)
        table = qt.QtWidgets.QTableWidget()
        frame.plugin_config_view = copy.deepcopy(view)
        frame.plugin_config_item_schema = copy.deepcopy(item_schema)
        frame.plugin_config_columns = copy.deepcopy(columns)
        frame.plugin_config_items = copy.deepcopy(items)
        frame.plugin_config_table = table
        frame.plugin_config_editable = editable
        frame.plugin_config_described = copy.deepcopy(described or {})
        frame.plugin_config_schema_version = str(
            (described or {}).get("config_schema_version")
            or (described or {}).get("schema_version")
            or ""
        )
        frame.plugin_config_protocol_family = str((described or {}).get("protocol_family") or "")
        frame.plugin_config_plugin_id = str((described or {}).get("plugin_id") or "")
        frame.plugin_config_config_key = str((described or {}).get("config_key") or "")
        frame.plugin_config_view_id = str(view.get("view_id") or "")
        frame.plugin_config_editor_kind = str(view.get("editor_kind") or "")
        frame.plugin_config_action_id = self._plugin_config_action_id_for_view(view, described)
        frame.plugin_config_section = str(view.get("section") or "")
        frame.plugin_config_action_state = copy.deepcopy(action_state)
        if "append_value" in view:
            append_value = view.get("append_value")
        else:
            append_value = view.get("item_default")
            model_key = str(view.get("item_model_key") or (view.get("item_schema") or {}).get("model_key") or "")
            models = (described or {}).get("models") if isinstance((described or {}).get("models"), dict) else {}
            if append_value is None and model_key:
                append_value = models.get(model_key)
        frame.plugin_config_append_value = copy.deepcopy(append_value if append_value is not None else {})
        table.setColumnCount(len(columns))
        table.setHorizontalHeaderLabels([str(column.get("label") or column.get("key") or "") for column in columns])
        table.setRowCount(len(items))
        for row, item in enumerate(items):
            for col, column in enumerate(columns):
                value = self._plugin_structured_item_value(item, column)
                if editable and not bool(column.get("read_only")):
                    table.setCellWidget(
                        row,
                        col,
                        self._plugin_structured_cell_editor(
                            column,
                            value,
                            view=view,
                            described=described,
                            current_values=item,
                        ),
                    )
                else:
                    table.setItem(row, col, qt.QtWidgets.QTableWidgetItem(
                        self._format_plugin_protocol_value(value)
                    ))
        self._polish_plugin_protocol_table(table)
        if table.rowCount():
            table.selectRow(0)
        layout.addWidget(table, 1)
        detail_sections = [
            section for section in (item_schema.get("detail_sections") or [])
            if isinstance(section, dict)
        ]
        if detail_sections:
            detail_tabs = qt.QtWidgets.QTabWidget()
            detail_tabs.setObjectName("pluginConfigDetailTabs")
            frame.plugin_config_detail_sections = copy.deepcopy(detail_sections)
            frame.plugin_config_detail_tabs = detail_tabs
            frame.plugin_config_detail_widgets = []
            detail_tabs.setMinimumHeight(170)
            detail_tabs.setSizePolicy(
                qt.QtWidgets.QSizePolicy.Policy.Expanding,
                qt.QtWidgets.QSizePolicy.Policy.Ignored,
            )
            layout.addWidget(detail_tabs, 1)
            table.itemSelectionChanged.connect(
                lambda fr=frame: self._refresh_plugin_structured_detail_sections(fr)
            )
            self._refresh_plugin_structured_detail_sections(frame)
        button_row = qt.QtWidgets.QHBoxLayout()
        buttons = {}
        button_specs = {}
        for spec in self._plugin_structured_button_specs(
            action_buttons,
            supported_operations=supported_operations,
            can_update_item=can_update_item,
            button_order=action_state.get("button_order") if isinstance(action_state.get("button_order"), list) else [],
        ):
            button_key = str(spec.get("key") or "").strip()
            if not button_key:
                continue
            button = qt.QtWidgets.QPushButton(str(spec.get("label") or button_key))
            visible = bool(spec.get("visible", True))
            if not visible:
                button.setVisible(False)
            button.clicked.connect(
                lambda checked=False, op=str(spec.get("effective_operation") or spec.get("operation") or ""), offset=spec.get("target_offset"), fr=frame: self._apply_plugin_structured_list_patch(fr, op, offset)
            )
            button_row.addWidget(button)
            buttons[button_key] = button
            button_specs[button_key] = copy.deepcopy(spec)
        button_row.addStretch(1)
        frame.plugin_config_buttons = buttons
        frame.plugin_config_button_specs = button_specs
        table.itemSelectionChanged.connect(
            lambda fr=frame: self._update_plugin_structured_list_buttons(fr)
        )
        layout.addLayout(button_row)
        self._update_plugin_structured_list_buttons(frame)
        return frame

    def _plugin_structured_button_specs(
        self,
        action_buttons,
        *,
        supported_operations,
        can_update_item,
        button_order=None,
    ):
        action_buttons = action_buttons if isinstance(action_buttons, dict) else {}
        if action_buttons:
            result = []
            ordered_keys = []
            seen = set()
            for key in button_order or []:
                button_key = str(key or "").strip()
                if button_key and button_key in action_buttons and button_key not in seen:
                    ordered_keys.append(button_key)
                    seen.add(button_key)
            for key in action_buttons:
                if key not in seen:
                    ordered_keys.append(key)
                    seen.add(key)
            for key in ordered_keys:
                state = action_buttons.get(key)
                if not isinstance(state, dict):
                    continue
                operation = str(state.get("operation") or "").strip()
                if not operation:
                    continue
                target_offset = state.get("target_offset")
                button_key = str(state.get("key") or key or "").strip()
                if not button_key:
                    button_key = operation if target_offset is None else f"{operation}_{target_offset}"
                spec = copy.deepcopy(state)
                spec["key"] = button_key
                spec.setdefault("effective_operation", str(state.get("effective_operation") or operation))
                spec.setdefault("target_offset", target_offset)
                spec.setdefault("visible", bool(state.get("visible", True)))
                spec.setdefault("enabled", bool(state.get("enabled", spec.get("visible", True))))
                result.append(spec)
            if result:
                return result

        fallback = []
        for text, operation, target_offset in [
            ("新增", "append_item", None),
            ("应用修改", "update_item", None),
            ("删除", "delete_item", None),
            ("启停", "set_enabled", None),
            ("上移", "move_item", -1),
            ("下移", "move_item", 1),
        ]:
            button_key = operation if target_offset is None else f"{operation}_{target_offset}"
            effective_operation = operation
            visible = True
            if operation == "update_item":
                visible = bool(can_update_item)
                if "update_item" not in supported_operations and "replace_item" in supported_operations:
                    effective_operation = "replace_item"
            elif supported_operations and operation not in supported_operations:
                visible = False
            fallback.append({
                "key": button_key,
                "label": text,
                "operation": operation,
                "effective_operation": effective_operation,
                "target_offset": target_offset,
                "visible": visible,
                "enabled": visible,
            })
        return fallback

    def _update_plugin_structured_list_buttons(self, frame):
        table = getattr(frame, "plugin_config_table", None)
        buttons = getattr(frame, "plugin_config_buttons", {}) or {}
        specs = getattr(frame, "plugin_config_button_specs", {}) or {}
        items = getattr(frame, "plugin_config_items", []) or []
        row = table.currentRow() if table is not None else -1
        item_count = len(items)
        for key, button in buttons.items():
            if button is None:
                continue
            spec = specs.get(key) if isinstance(specs.get(key), dict) else {}
            visible = bool(spec.get("visible", button.isVisible()))
            enabled = bool(spec.get("enabled", visible))
            operation = str(spec.get("operation") or "")
            requires_selection = bool(spec.get("requires_selection"))
            disabled_reason = str(spec.get("disabled_reason") or "").strip()
            if requires_selection and row < 0:
                enabled = False
                disabled_reason = "需要先选择配置项。"
            if operation == "move_item" and row >= 0:
                try:
                    to_index = row + int(spec.get("target_offset") or 0)
                except Exception:
                    to_index = row
                if to_index < 0 or to_index >= item_count:
                    enabled = False
                    disabled_reason = "配置项已经在边界位置。"
                elif visible:
                    enabled = True
                    disabled_reason = ""
            if operation in {"update_item", "replace_item", "delete_item", "remove_item", "set_enabled"} and row >= 0 and visible:
                enabled = True
                disabled_reason = ""
            button.setVisible(visible)
            button.setEnabled(enabled)
            if disabled_reason:
                button.setToolTip(disabled_reason)
            elif button.toolTip():
                button.setToolTip("")

    def _refresh_plugin_structured_detail_sections(self, frame):
        tabs = getattr(frame, "plugin_config_detail_tabs", None)
        table = getattr(frame, "plugin_config_table", None)
        if tabs is None or table is None:
            return
        sections = [
            section for section in (getattr(frame, "plugin_config_detail_sections", []) or [])
            if isinstance(section, dict)
        ]
        items = copy.deepcopy(getattr(frame, "plugin_config_items", []) or [])
        row = table.currentRow()
        if row < 0 and items:
            row = 0
        item = copy.deepcopy(items[row]) if 0 <= row < len(items) and isinstance(items[row], dict) else {}
        tabs.clear()
        detail_widgets = []
        view = getattr(frame, "plugin_config_view", {}) or {}
        described = getattr(frame, "plugin_config_described", {}) or {}
        for section in sections:
            widget = self._make_plugin_detail_section_widget(section, item, view=view, described=described)
            if widget is None:
                continue
            title = str(section.get("title") or section.get("label") or section.get("key") or "详情")
            tabs.addTab(widget, title[:24])
            detail_widgets.append(widget)
        frame.plugin_config_detail_widgets = detail_widgets

    def _make_plugin_detail_section_widget(self, section, item, *, view=None, described=None):
        kind = str((section or {}).get("kind") or "")
        if kind == "form":
            return self._make_plugin_detail_form_widget(section, item, view=view, described=described)
        if kind == "structured_list":
            return self._make_plugin_detail_structured_list_widget(section, item, view=view, described=described)
        return self._make_plugin_protocol_text_widget(section)

    def _make_plugin_detail_form_widget(self, section, item, *, view=None, described=None):
        qt = self.qt
        widget = qt.QtWidgets.QWidget()
        widget.setObjectName("pluginConfigDetailForm")
        form = qt.QtWidgets.QFormLayout(widget)
        form.setContentsMargins(6, 6, 6, 6)
        form.setSpacing(6)
        fields = [field for field in ((section or {}).get("fields") or []) if isinstance(field, dict)]
        editors = []
        for field in fields:
            column = self._plugin_detail_field_column(section, field)
            value = self._plugin_structured_item_value(item, column)
            editor = self._plugin_structured_cell_editor(
                column,
                value,
                view=view,
                described=described,
                current_values=item,
            )
            help_text = str(field.get("help") or field.get("description") or field.get("warning") or "").strip()
            if help_text:
                editor.setToolTip(help_text)
            form.addRow(str(column.get("label") or column.get("key") or ""), editor)
            editors.append((copy.deepcopy(column), editor))
        if not editors:
            form.addRow("", qt.QtWidgets.QLabel("暂无详情字段"))
        widget.plugin_detail_kind = "form"
        widget.plugin_detail_form_fields = editors
        return widget

    def _make_plugin_detail_structured_list_widget(self, section, item, *, view=None, described=None):
        qt = self.qt
        widget = qt.QtWidgets.QWidget()
        widget.setObjectName("pluginConfigDetailStructuredList")
        layout = qt.QtWidgets.QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        item_schema = section.get("item_schema") if isinstance(section.get("item_schema"), dict) else {}
        columns = [column for column in (item_schema.get("columns") or []) if isinstance(column, dict)]
        path = self._plugin_protocol_path(section.get("config_path"), [section.get("key") or ""])
        rows = self._plugin_protocol_path_value(item, path, [])
        rows = [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []
        if not columns and rows:
            columns = [{"key": key, "label": key} for key in rows[0].keys()]
        table = qt.QtWidgets.QTableWidget()
        table.setColumnCount(len(columns))
        table.setHorizontalHeaderLabels([str(column.get("label") or column.get("key") or "") for column in columns])
        table.setRowCount(0)
        widget.plugin_detail_kind = "structured_list"
        widget.plugin_detail_path = copy.deepcopy(path)
        widget.plugin_detail_columns = copy.deepcopy(columns)
        widget.plugin_detail_source_items = copy.deepcopy(rows)
        widget.plugin_detail_row_sources = []
        widget.plugin_detail_item_default = copy.deepcopy(
            section.get("item_default") if isinstance(section.get("item_default"), dict) else {}
        )
        widget.plugin_detail_table = table
        widget.plugin_config_view = copy.deepcopy(view or {})
        widget.plugin_config_described = copy.deepcopy(described or {})
        for row_value in rows:
            self._plugin_detail_table_append_row(widget, row_value)
        self._polish_plugin_protocol_table(table)
        if table.rowCount():
            table.selectRow(0)
        layout.addWidget(table, 1)
        button_row = qt.QtWidgets.QHBoxLayout()
        add_button = qt.QtWidgets.QPushButton("新增明细")
        delete_button = qt.QtWidgets.QPushButton("删除明细")
        add_button.clicked.connect(lambda checked=False, w=widget: self._plugin_detail_table_append_row(w))
        delete_button.clicked.connect(lambda checked=False, w=widget: self._plugin_detail_table_delete_current_row(w))
        button_row.addWidget(add_button)
        button_row.addWidget(delete_button)
        button_row.addStretch(1)
        layout.addLayout(button_row)
        widget.plugin_detail_buttons = {
            "append_item": add_button,
            "delete_item": delete_button,
        }
        return widget

    def _plugin_detail_table_append_row(self, widget, value=None):
        table = getattr(widget, "plugin_detail_table", None)
        if table is None:
            return
        columns = copy.deepcopy(getattr(widget, "plugin_detail_columns", []) or [])
        default = copy.deepcopy(getattr(widget, "plugin_detail_item_default", {}) or {})
        row_value = copy.deepcopy(value if isinstance(value, dict) else default)
        row = table.rowCount()
        table.insertRow(row)
        row_sources = getattr(widget, "plugin_detail_row_sources", None)
        if isinstance(row_sources, list):
            row_sources.append(copy.deepcopy(row_value))
        for col, column in enumerate(columns):
            cell_value = self._plugin_structured_item_value(row_value, column)
            if bool((column or {}).get("read_only")):
                table.setItem(row, col, self.qt.QtWidgets.QTableWidgetItem(
                    self._format_plugin_protocol_value(cell_value)
                ))
            else:
                table.setCellWidget(
                    row,
                    col,
                    self._plugin_structured_cell_editor(
                        column,
                        cell_value,
                        view=getattr(widget, "plugin_config_view", {}) or {},
                        described=getattr(widget, "plugin_config_described", {}) or {},
                        current_values=row_value,
                    ),
                )
        table.selectRow(row)

    def _plugin_detail_table_delete_current_row(self, widget):
        table = getattr(widget, "plugin_detail_table", None)
        if table is None:
            return
        row = table.currentRow()
        if row < 0:
            return
        table.removeRow(row)
        row_sources = getattr(widget, "plugin_detail_row_sources", None)
        if isinstance(row_sources, list) and row < len(row_sources):
            row_sources.pop(row)
        if table.rowCount():
            table.selectRow(min(row, table.rowCount() - 1))

    def _plugin_structured_item_value(self, item, column):
        if not isinstance(item, dict):
            return None
        column = column or {}
        key = str(column.get("key") or "")
        path = column.get("config_path")
        if isinstance(path, str):
            path = [part for part in path.split(".") if part]
        elif not isinstance(path, (list, tuple)):
            path = []
        if path:
            current = item
            found = True
            for part in path:
                if not isinstance(current, dict) or part not in current:
                    found = False
                    break
                current = current.get(part)
            if found:
                return current
        if key in item:
            return item.get(key)
        if "." in key:
            current = item
            found = True
            for part in [part for part in key.split(".") if part]:
                if not isinstance(current, dict) or part not in current:
                    found = False
                    break
                current = current.get(part)
            if found:
                return current
        if path and path[-1] in item:
            return item.get(path[-1])
        return None

    def _plugin_protocol_path(self, value, fallback=None):
        if isinstance(value, str):
            return [part for part in value.split(".") if part]
        if isinstance(value, (list, tuple)):
            return [str(part) for part in value if str(part)]
        if fallback is None:
            return []
        return self._plugin_protocol_path(fallback, [])

    def _plugin_protocol_path_value(self, item, path, default=None):
        current = item
        for part in self._plugin_protocol_path(path):
            if not isinstance(current, dict) or part not in current:
                return default
            current = current.get(part)
        return current

    def _plugin_protocol_set_path_value(self, item, path, value):
        if not isinstance(item, dict):
            return
        parts = self._plugin_protocol_path(path)
        if not parts:
            return
        current = item
        for part in parts[:-1]:
            if not isinstance(current.get(part), dict):
                current[part] = {}
            current = current[part]
        current[parts[-1]] = value

    def _plugin_detail_field_column(self, section, field):
        column = copy.deepcopy(field or {})
        section_path = self._plugin_protocol_path(
            (section or {}).get("config_path"),
            [(section or {}).get("key") or ""],
        )
        field_path = self._plugin_protocol_path(column.get("config_path"))
        if not field_path:
            key = str(column.get("key") or "")
            field_path = [part for part in key.split(".") if part] if key else []
        column["config_path"] = section_path + field_path
        return column

    def _plugin_structured_column_kind(self, column):
        column_type = str((column or {}).get("type") or "text")
        if column_type == "bool":
            return "bool"
        if column_type in {"select", "field_select", "table_select"}:
            return "choice"
        if column_type in {"textarea", "long_text"}:
            return "long_text"
        if column_type in {"number", "int", "float"}:
            return "number"
        return "text"

    def _plugin_structured_cell_editor(self, column, value, *, view=None, described=None, current_values=None):
        qt = self.qt
        kind = self._plugin_structured_column_kind(column)
        if kind == "bool":
            widget = qt.QtWidgets.QCheckBox()
            widget.setChecked(bool(value))
            return widget
        if kind == "choice":
            widget = qt.QtWidgets.QComboBox()
            allow_custom = bool((column or {}).get("allow_custom", True))
            widget.setEditable(allow_custom)
            choices = self._plugin_structured_cell_choices(
                column,
                view=view,
                described=described,
                current_values=current_values,
            )
            current = "" if value is None else str(value)
            if current and current not in choices:
                choices.insert(0, current)
            widget.addItems(choices or ([current] if current else []))
            widget.setCurrentText(current)
            return widget
        if kind == "long_text":
            widget = qt.QtWidgets.QPlainTextEdit()
            widget.setPlainText("" if value is None else str(value))
            widget.setMinimumHeight(52)
            return widget
        widget = qt.QtWidgets.QLineEdit()
        widget.setText("" if value is None else str(value))
        return widget

    def _plugin_structured_cell_choices(self, column, *, view=None, described=None, current_values=None):
        static_choices = [str(item) for item in ((column or {}).get("choices") or []) if str(item).strip()]
        options_source = column.get("options_source") if isinstance((column or {}).get("options_source"), dict) else {}
        source_type = str(options_source.get("type") or "").strip()
        if source_type not in {"plugin_config_context", "visual_mapping_context"}:
            return static_choices
        resolved = self._resolve_plugin_structured_cell_options(
            column,
            view=view,
            described=described,
            current_values=current_values,
        )
        if not resolved:
            return static_choices
        return [str(item) for item in (resolved.get("choices") or []) if str(item).strip()]

    def _resolve_plugin_structured_cell_options(self, column, *, view=None, described=None, current_values=None):
        described = described if isinstance(described, dict) else {}
        plugin_id = str(described.get("plugin_id") or "").strip()
        if not plugin_id:
            return {}
        field_key = str((column or {}).get("key") or "").strip()
        if not field_key:
            return {}
        view = view if isinstance(view, dict) else {}
        try:
            result = self.engine_client.resolve_plugin_config_options(
                plugin_id,
                field_key=field_key,
                current_values=copy.deepcopy(current_values or {}),
                view_id=str(view.get("view_id") or "").strip(),
                section=str(view.get("section") or "").strip(),
                config=copy.deepcopy(described.get("config") or self._current_plugin_config()),
                input_table=self._input_table_payload(),
                context=self._plugin_config_context_payload(),
            )
        except Exception:
            return {}
        if not result.get("ok") or result.get("schema_version") != "DataFlowKit.plugin_config_options.v1":
            return {}
        if str(result.get("source") or "") == "unknown":
            return {}
        return result

    def _current_plugin_config(self):
        try:
            node = self.config_form.to_node()
        except Exception:
            node = None
        if isinstance(node, dict) and isinstance(node.get("config"), dict):
            return copy.deepcopy(node.get("config") or {})
        index = self.selected_node_index()
        nodes = self.current_plan.get("nodes") if isinstance(self.current_plan, dict) else []
        if index is not None and isinstance(nodes, list) and 0 <= index < len(nodes):
            node = nodes[index]
            if isinstance(node, dict) and isinstance(node.get("config"), dict):
                return copy.deepcopy(node.get("config") or {})
        return {}

    def _plugin_config_context_payload(self):
        input_db_path = self.current_data_source_db_path()
        output_db_path = self.output_db_path_edit.text().strip()
        db_path = input_db_path or output_db_path
        return {
            "db_path": db_path,
            "input_db_path": input_db_path,
            "output_db_path": output_db_path,
            "workflow_name": self.current_plan.get("plan_name", "") if isinstance(self.current_plan, dict) else "",
        }

    def _plugin_structured_editor_value(self, widget, column):
        kind = self._plugin_structured_column_kind(column)
        if kind == "bool":
            return bool(widget.isChecked())
        if kind == "choice":
            return str(widget.currentText())
        if kind == "long_text":
            return str(widget.toPlainText())
        raw = str(widget.text()).strip() if widget is not None else ""
        if kind == "number":
            if not raw:
                return None
            try:
                return float(raw) if "." in raw else int(raw)
            except ValueError as exc:
                label = str((column or {}).get("label") or (column or {}).get("key") or "数值")
                raise ValueError(f"{label} 不是有效数字：{raw}") from exc
        return str(widget.text()) if widget is not None else ""

    def _plugin_structured_set_item_value(self, item, column, value):
        if not isinstance(item, dict):
            return
        column = column or {}
        path = column.get("config_path")
        if isinstance(path, str):
            path = [part for part in path.split(".") if part]
        elif not isinstance(path, (list, tuple)):
            path = []
        if not path:
            key = str(column.get("key") or "")
            path = [part for part in key.split(".") if part] if "." in key else ([key] if key else [])
        if not path:
            return
        current = item
        for part in path[:-1]:
            if not isinstance(current.get(part), dict):
                current[part] = {}
            current = current[part]
        current[path[-1]] = value

    def _plugin_structured_row_payload(self, frame, row):
        table = getattr(frame, "plugin_config_table", None)
        columns = copy.deepcopy(getattr(frame, "plugin_config_columns", []) or [])
        items = copy.deepcopy(getattr(frame, "plugin_config_items", []) or [])
        if table is None or row < 0:
            return {}
        payload = copy.deepcopy(items[row]) if 0 <= row < len(items) and isinstance(items[row], dict) else {}
        for col, column in enumerate(columns):
            if bool((column or {}).get("read_only")):
                continue
            widget = table.cellWidget(row, col)
            if widget is not None:
                value = self._plugin_structured_editor_value(widget, column)
            else:
                item = table.item(row, col)
                if item is None:
                    continue
                value = item.text()
            self._plugin_structured_set_item_value(payload, column, value)
        self._plugin_structured_apply_detail_payload(frame, payload, row)
        return payload

    def _plugin_structured_apply_detail_payload(self, frame, payload, row):
        if not isinstance(payload, dict):
            return
        table = getattr(frame, "plugin_config_table", None)
        if table is None or table.currentRow() != row:
            return
        for widget in getattr(frame, "plugin_config_detail_widgets", []) or []:
            kind = str(getattr(widget, "plugin_detail_kind", "") or "")
            if kind == "form":
                for column, editor in getattr(widget, "plugin_detail_form_fields", []) or []:
                    value = self._plugin_structured_editor_value(editor, column)
                    self._plugin_structured_set_item_value(payload, column, value)
            elif kind == "structured_list":
                path = copy.deepcopy(getattr(widget, "plugin_detail_path", []) or [])
                rows = self._plugin_detail_structured_list_payload(widget)
                self._plugin_protocol_set_path_value(payload, path, rows)

    def _plugin_detail_structured_list_payload(self, widget):
        table = getattr(widget, "plugin_detail_table", None)
        columns = copy.deepcopy(getattr(widget, "plugin_detail_columns", []) or [])
        source_items = copy.deepcopy(
            getattr(widget, "plugin_detail_row_sources", None)
            if isinstance(getattr(widget, "plugin_detail_row_sources", None), list)
            else (getattr(widget, "plugin_detail_source_items", []) or [])
        )
        if table is None:
            return []
        rows = []
        for row in range(table.rowCount()):
            payload = copy.deepcopy(source_items[row]) if 0 <= row < len(source_items) and isinstance(source_items[row], dict) else {}
            for col, column in enumerate(columns):
                if bool((column or {}).get("read_only")):
                    continue
                editor = table.cellWidget(row, col)
                if editor is not None:
                    value = self._plugin_structured_editor_value(editor, column)
                else:
                    item = table.item(row, col)
                    if item is None:
                        continue
                    value = item.text()
                self._plugin_structured_set_item_value(payload, column, value)
            rows.append(payload)
        return rows

    def _apply_plugin_structured_list_patch(self, frame, operation, target_offset=None):
        view = copy.deepcopy(getattr(frame, "plugin_config_view", {}) or {})
        table = getattr(frame, "plugin_config_table", None)
        items = copy.deepcopy(getattr(frame, "plugin_config_items", []) or [])
        target_path = copy.deepcopy(view.get("config_path") or [view.get("view_id") or ""])
        section = str(getattr(frame, "plugin_config_section", "") or "")
        if not section:
            path_parts = self._plugin_protocol_path(target_path)
            if len(path_parts) >= 4 and path_parts[0] == "plugin_settings" and path_parts[1] == "configs":
                section = path_parts[3]
            elif len(path_parts) == 1:
                section = path_parts[0]
        config_key = str(getattr(frame, "plugin_config_config_key", "") or "")
        path_parts = self._plugin_protocol_path(target_path)
        if not config_key and len(path_parts) >= 4 and path_parts[0] == "plugin_settings" and path_parts[1] == "configs":
            config_key = path_parts[2]
        patch = {
            "schema_version": str(getattr(frame, "plugin_config_schema_version", "") or ""),
            "protocol_family": str(getattr(frame, "plugin_config_protocol_family", "") or ""),
            "plugin_id": str(getattr(frame, "plugin_config_plugin_id", "") or ""),
            "config_key": config_key,
            "config_name": config_key,
            "section": section,
            "operation": operation,
            "path": copy.deepcopy(target_path),
            "target": copy.deepcopy(target_path),
        }
        view_id = str(getattr(frame, "plugin_config_view_id", "") or view.get("view_id") or "").strip()
        editor_kind = str(getattr(frame, "plugin_config_editor_kind", "") or view.get("editor_kind") or "").strip()
        action_id = str(getattr(frame, "plugin_config_action_id", "") or view.get("action_id") or "").strip()
        if view_id:
            patch["view_id"] = view_id
        if editor_kind:
            patch["editor_kind"] = editor_kind
        if action_id:
            patch["action_id"] = action_id
        selected_row = table.currentRow() if table is not None else -1
        if operation in ("delete_item", "set_enabled", "move_item", "update_item", "replace_item"):
            if selected_row < 0:
                self.status_bar.showMessage("请先选择一条配置项。")
                return
            patch["target_index"] = int(selected_row)
            patch["index"] = int(selected_row)
            target_id = self._plugin_structured_target_id(frame, selected_row)
            if target_id:
                patch["target_id"] = target_id
        if operation == "append_item":
            value = copy.deepcopy(getattr(frame, "plugin_config_append_value", {}) or {})
            patch["payload"] = value
            patch["value"] = copy.deepcopy(value)
        elif operation == "set_enabled":
            item = items[selected_row] if 0 <= selected_row < len(items) else {}
            enabled = not bool(item.get("enabled", True))
            patch["enabled"] = enabled
            patch["payload"] = {"enabled": enabled}
        elif operation in {"update_item", "replace_item"}:
            try:
                value = self._plugin_structured_row_payload(frame, selected_row)
            except ValueError as exc:
                self.show_error("插件配置写回失败", str(exc))
                return
            patch["payload"] = value
            patch["value"] = copy.deepcopy(value)
        elif operation == "move_item":
            to_index = selected_row + int(target_offset or 0)
            if to_index < 0 or to_index >= len(items):
                self.status_bar.showMessage("配置项已经在边界位置。")
                return
            patch["to_index"] = to_index
        self._apply_plugin_config_patch(patch)

    def _plugin_structured_target_id(self, frame, row):
        items = getattr(frame, "plugin_config_items", []) or []
        if row < 0 or row >= len(items) or not isinstance(items[row], dict):
            return ""
        view = getattr(frame, "plugin_config_view", {}) or {}
        patch_target = view.get("patch_target") if isinstance(view.get("patch_target"), dict) else {}
        item_identity = view.get("item_identity") if isinstance(view.get("item_identity"), dict) else {}
        target_fields = (
            patch_target.get("target_id_fields")
            or item_identity.get("target_id_fields")
            or []
        )
        for field in target_fields:
            value = self._plugin_protocol_path_value(items[row], field, "")
            text = str(value).strip() if value is not None else ""
            if text:
                return text
        return ""

    def _apply_plugin_config_patch(self, patch):
        index = self.selected_node_index()
        if index is None:
            self.status_bar.showMessage("请先选择插件节点。")
            return
        try:
            node = self.config_form.to_node()
            node_type_id = self._node_type_id_for_node(node)
            config = copy.deepcopy(node.get("config", {}) or {})
            plugin_id = config.get("plugin_id") or node_type_id
            result = self.engine_client.apply_plugin_config_patch(
                plugin_id,
                patch=copy.deepcopy(patch),
                config=config,
                input_table=self._input_table_payload(),
                context=self._plugin_config_context_payload(),
            )
        except Exception as exc:
            self.show_error("插件配置写回失败", str(exc))
            return
        if not result.get("ok"):
            self._apply_feedback(self.engine_client.build_user_feedback(
                code="plugin_config_patch_failed",
                title="插件配置写回失败",
                level="error",
                status_message="插件配置写回失败",
                issue_message="插件配置修改未通过校验或写回失败。",
                issues=result.get("issues", []),
            ))
            return
        if isinstance(result.get("config"), dict):
            self.current_plan.setdefault("nodes", [])[index]["config"] = copy.deepcopy(result["config"])
        self.refresh_node_list()
        self.node_list.setCurrentRow(index)
        self.show_node_config(index)
        patch_result = result.get("patch_result") if isinstance(result.get("patch_result"), dict) else {}
        self._focus_plugin_config_target(patch_result.get("target"))
        self.status_bar.showMessage(str(
            patch_result.get("status_message")
            or patch_result.get("message")
            or result.get("message")
            or "插件配置已更新。"
        ))

    def _make_plugin_resource_list_widget(self, view, described):
        qt = self.qt
        resource_ids = {str(item) for item in (view.get("resource_ids") or [])}
        resources = [
            item for item in (described.get("resources") or [])
            if isinstance(item, dict) and (not resource_ids or str(item.get("resource_id") or "") in resource_ids)
        ]
        table = qt.QtWidgets.QTableWidget()
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels(["资源", "类型", "存储", "文件"])
        table.setRowCount(len(resources))
        for row, resource in enumerate(resources):
            values = [
                resource.get("label") or resource.get("resource_id"),
                resource.get("kind"),
                resource.get("storage"),
                resource.get("file"),
            ]
            for col, value in enumerate(values):
                table.setItem(row, col, qt.QtWidgets.QTableWidgetItem(self._format_plugin_protocol_value(value)))
        self._polish_plugin_protocol_table(table)
        return table

    def _make_plugin_text_preview_widget(self, view):
        text = view.get("text")
        if text is None:
            text = view.get("content")
        if text is None:
            text = view.get("preview")
        if text is None:
            text = view.get("value")
        editor = self.qt.QtWidgets.QPlainTextEdit()
        editor.setReadOnly(True)
        if isinstance(text, (dict, list)):
            editor.setPlainText(json.dumps(text, ensure_ascii=False, indent=2))
        else:
            editor.setPlainText("" if text is None else str(text))
        return editor

    def _make_plugin_protocol_text_widget(self, payload):
        editor = self.qt.QtWidgets.QPlainTextEdit()
        editor.setReadOnly(True)
        editor.setPlainText(json.dumps(payload or {}, ensure_ascii=False, indent=2))
        return editor

    def _polish_plugin_protocol_table(self, table):
        qt = self.qt
        table.setAlternatingRowColors(True)
        table.setWordWrap(False)
        table.setEditTriggers(qt.QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(qt.QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(qt.QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        try:
            table.horizontalHeader().setStretchLastSection(True)
            table.resizeColumnsToContents()
            table.resizeRowsToContents()
        except Exception:
            pass

    def _format_plugin_protocol_value(self, value):
        if isinstance(value, bool):
            return "是" if value else "否"
        if value is None:
            return ""
        if isinstance(value, (list, tuple)):
            text = "、".join(self._format_plugin_protocol_value(item) for item in value)
        elif isinstance(value, dict):
            text = json.dumps(value, ensure_ascii=False, sort_keys=True)
        else:
            text = str(value)
        return text if len(text) <= 500 else text[:497] + "..."

    def _legacy_plugin_config_action(self, schema=None, described=None):
        schema = schema if isinstance(schema, dict) else {}
        described = described if isinstance(described, dict) else {}
        plugin = schema.get("plugin") if isinstance(schema.get("plugin"), dict) else {}
        actions = described.get("actions") if isinstance(described.get("actions"), list) else []
        for item in actions:
            if not isinstance(item, dict):
                continue
            action_id = str(item.get("action_id") or "").strip()
            kind = str(item.get("kind") or "").strip()
            if action_id == "open_legacy_config" or kind == "compatibility":
                action = copy.deepcopy(item)
                action.setdefault("source", "plugin_config_description.actions")
                return action

        custom_window = plugin.get("custom_config_window") if isinstance(plugin.get("custom_config_window"), dict) else {}
        legacy_state = plugin.get("legacy_config_state") if isinstance(plugin.get("legacy_config_state"), dict) else {}
        if not (legacy_state.get("ui_visible") or legacy_state.get("available") or custom_window.get("available")):
            return {}
        action = {
            "action_id": str(legacy_state.get("action_id") or "open_legacy_config"),
            "label": str(legacy_state.get("label") or custom_window.get("label") or "兼容旧版设置"),
            "kind": "compatibility",
            "compatibility": str(legacy_state.get("compatibility") or custom_window.get("compatibility") or "legacy"),
            "mode": str(legacy_state.get("mode") or ""),
            "fallback": bool(legacy_state.get("fallback", custom_window.get("fallback", True))),
            "deprecated": bool(legacy_state.get("deprecated", custom_window.get("deprecated", True))),
            "lifecycle": str(legacy_state.get("lifecycle") or custom_window.get("lifecycle") or "legacy_fallback"),
            "preferred": bool(legacy_state.get("preferred", custom_window.get("preferred", False))),
            "ui_role": str(legacy_state.get("ui_role") or custom_window.get("ui_role") or "fallback_action"),
            "ui_prominence": str(legacy_state.get("ui_prominence") or custom_window.get("ui_prominence") or "low"),
            "ui_placement": str(legacy_state.get("ui_placement") or custom_window.get("ui_placement") or "compatibility_menu"),
            "requires_confirmation": bool(legacy_state.get("requires_confirmation", custom_window.get("requires_confirmation", True))),
            "migration_target": str(legacy_state.get("migration_target") or custom_window.get("migration_target") or "describe_config + parameter_metadata + config_patch"),
            "remove_when": str(legacy_state.get("remove_when") or custom_window.get("remove_when") or "插件已提供等价 schema/patch 配置能力且目标 UI 已完成承接。"),
            "warning": str(
                legacy_state.get("warning")
                or custom_window.get("warning")
                or "兼容旧 Tk 插件设置窗口；标准配置仍以当前表单为主。"
            ),
            "legacy_config_state": copy.deepcopy(legacy_state),
            "source": "node_ui_schema.plugin.legacy_config_state",
        }
        return action

    def _update_legacy_plugin_config_button(self, schema, described=None):
        schema = schema if isinstance(schema, dict) else {}
        described = described if isinstance(described, dict) else {}
        plugin = schema.get("plugin") if isinstance(schema.get("plugin"), dict) else {}
        legacy_state = plugin.get("legacy_config_state") if isinstance(plugin.get("legacy_config_state"), dict) else {}
        compatibility = plugin.get("config_compatibility") if isinstance(plugin.get("config_compatibility"), dict) else {}
        if not compatibility and isinstance(schema.get("config_compatibility"), dict):
            compatibility = schema.get("config_compatibility") or {}
        if not compatibility and isinstance(described.get("config_compatibility"), dict):
            compatibility = described.get("config_compatibility") or {}
        action = self._legacy_plugin_config_action(schema, described)
        self.current_legacy_plugin_config_action = copy.deepcopy(action)
        visible = bool(action)
        tooltip = str(
            action.get("warning")
            or "兼容旧 Tk 插件设置窗口；标准配置仍以当前表单为主。"
        )
        lifecycle_parts = []
        mode = str(action.get("mode") or "").strip()
        lifecycle = str(action.get("lifecycle") or "").strip()
        ui_placement = str(action.get("ui_placement") or "").strip()
        ui_prominence = str(action.get("ui_prominence") or "").strip()
        preferred = bool(action.get("preferred", False))
        requires_confirmation = bool(action.get("requires_confirmation", False))
        migration_target = str(action.get("migration_target") or "").strip()
        remove_when = str(action.get("remove_when") or "").strip()
        compatibility_tier = str(compatibility.get("compatibility_tier") or "").strip()
        ui_support = compatibility.get("ui_support") if isinstance(compatibility.get("ui_support"), dict) else {}
        direct_ui = ui_support.get("direct_ui") if isinstance(ui_support.get("direct_ui"), dict) else {}
        action_source = str(action.get("source") or "").strip()
        if mode:
            lifecycle_parts.append(f"模式：{mode}")
        if lifecycle:
            lifecycle_parts.append(f"生命周期：{lifecycle}")
        if compatibility_tier:
            lifecycle_parts.append(f"兼容等级：{compatibility_tier}")
        supported_ui = [
            label
            for key, label in [
                ("tk", "Tk"),
                ("qt", "Qt"),
                ("dotnet", ".NET"),
                ("web", "Web"),
                ("electron", "Electron"),
            ]
            if direct_ui.get(key)
        ]
        if supported_ui:
            lifecycle_parts.append("标准协议支持UI：" + "、".join(supported_ui))
        if ui_placement:
            lifecycle_parts.append(f"建议位置：{ui_placement}")
        if ui_prominence:
            lifecycle_parts.append(f"显示优先级：{ui_prominence}")
        lifecycle_parts.append(f"推荐主入口：{'是' if preferred else '否'}")
        if requires_confirmation:
            lifecycle_parts.append("打开前建议提示兼容风险")
        if migration_target:
            lifecycle_parts.append(f"迁移目标：{migration_target}")
        if remove_when:
            lifecycle_parts.append(f"退场条件：{remove_when}")
        if action_source:
            lifecycle_parts.append(f"来源：{action_source}")
        if lifecycle_parts:
            tooltip = tooltip + "\n" + "\n".join(lifecycle_parts)
        self.legacy_plugin_config_button.setVisible(visible)
        enabled_default = bool(action.get("ui_enabled_default", legacy_state.get("ui_enabled_default", visible)))
        self.legacy_plugin_config_button.setEnabled(visible and enabled_default and not bool(self.current_job_id))
        self.legacy_plugin_config_button.setText(str(action.get("label") or "兼容旧版设置"))
        self.legacy_plugin_config_button.setToolTip(tooltip)

    def open_legacy_plugin_config(self):
        index = self.selected_node_index()
        if index is None:
            self._apply_feedback(self.engine_client.describe_selection_feedback(
                selected_index=index,
                purpose="打开旧版插件设置",
            ))
            return
        try:
            node = self.config_form.to_node()
            node_type_id = self._node_type_id_for_node(node)
            config = node.get("config", {}) or {}
            plugin_id = config.get("plugin_id") or node_type_id
            action = self.current_legacy_plugin_config_action or self._legacy_plugin_config_action(
                getattr(self.config_form, "schema", {}) or {},
                self.current_plugin_config_description,
            )
            prompt = self.engine_client.describe_confirmation_prompt(
                action="legacy_plugin_config",
                compatibility_action=action,
            )
            if not self._confirm_prompt(prompt):
                return
            result = self.engine_client.run_plugin_custom_config_window(
                plugin_id,
                config=config,
                input_table=self._input_table_payload(),
                context=self._plugin_config_context_payload(),
                parent=None,
            )
        except Exception as exc:
            self.show_error("旧版插件设置错误", str(exc))
            return
        if not result.get("ok"):
            self._apply_feedback(self.engine_client.build_user_feedback(
                level="warning",
                code="legacy_plugin_config_failed",
                title="旧版插件设置",
                status_message="旧版插件设置未应用",
                issue_message=self.engine_client.format_issues_text(result.get("issues") or []),
                issues=result.get("issues") or [],
            ))
            return
        if not result.get("changed"):
            self._apply_feedback(self.engine_client.build_user_feedback(
                level="info",
                code="legacy_plugin_config_unchanged",
                title="旧版插件设置",
                status_message="旧版插件设置未更改。",
                issue_message="旧版插件设置未更改。",
            ))
            return

        updated_node = copy.deepcopy(node)
        updated_node["config"] = copy.deepcopy(result.get("config") or config)
        table_context = self._table_context()
        config_headers = self._node_config_headers_for_index(index)
        applied = self.engine_client.apply_node_config_state(
            self.current_plan,
            index=index,
            node=updated_node,
            preview_headers=config_headers,
            table_names=table_context.get("table_names"),
            table_columns=table_context.get("table_columns"),
        )
        validation = applied.get("validation") or {}
        self.config_form.set_validation_issues(validation.get("issues", []))
        if not applied.get("ok"):
            self._apply_feedback({"feedback": applied.get("feedback") or {}})
            return
        apply_result = applied.get("apply_result") or {}
        if apply_result.get("ok"):
            self.current_plan = apply_result.get("plan") or self.current_plan
            self._clear_node_config_preview_cache()
            self.refresh_all(selected_index=apply_result.get("selected_index", index))
        self._apply_feedback(self.engine_client.build_user_feedback(
            level="success",
            code="legacy_plugin_config_applied",
            title="旧版插件设置",
            status_message="旧版插件设置已应用。",
            issue_message="旧版插件设置已写回当前节点配置。",
        ))

    def apply_node_config(self):
        index = self.selected_node_index()
        if index is None:
            return
        try:
            node = self.config_form.to_node()
            table_context = self._table_context()
            config_headers = self._node_config_headers_for_index(index)
            result = self.engine_client.apply_node_config_state(
                self.current_plan,
                index=index,
                node=node,
                preview_headers=config_headers,
                table_names=table_context.get("table_names"),
                table_columns=table_context.get("table_columns"),
            )
            validation = result.get("validation") or {}
            self.config_form.set_validation_issues(validation.get("issues", []))
            feedback = {"feedback": result.get("feedback") or {}}
            self._apply_feedback(feedback)
            if not result.get("ok"):
                return
            apply_result = result.get("apply_result") or {}
            if apply_result.get("ok"):
                self.current_plan = apply_result.get("plan") or self.current_plan
                self._clear_node_config_preview_cache()
                self.refresh_all(selected_index=apply_result.get("selected_index", index))
        except Exception as exc:
            self.show_error("配置无效", str(exc))

    def _apply_feedback(self, feedback, *, fallback_status="", fallback_issue=""):
        payload = (feedback or {}).get("feedback") or {}
        status_message = str(payload.get("status_message") or fallback_status or "")
        panel = payload.get("message_panel") or self.engine_client.build_message_panel_state(
            mode=str(payload.get("level") or "info"),
            title=str(payload.get("title") or ""),
            body=str(payload.get("issue_message") or fallback_issue or ""),
            issues=payload.get("issues") or [],
            logs=payload.get("logs") or [],
        ).get("panel") or {}

        self._apply_message_panel(panel)

        if status_message:
            self.status_bar.showMessage(status_message)

    def _apply_message_panel(self, panel):
        panel = panel or {}
        self.current_message_panel = dict(panel)
        mode = str(panel.get("mode") or "info")
        title = str(panel.get("title") or "")
        info_body = str(panel.get("info_body") or "")
        issue_body = str(panel.get("issue_body") or "")
        logs = [str(item) for item in (panel.get("logs") or []) if str(item).strip()]
        issues = panel.get("issues") or []
        issue_text = issue_body or (self._format_issues(issues) if issues else "")
        info_lines = [item for item in [title, info_body] if str(item).strip()]
        self.info_text.setPlainText("\n\n".join(info_lines))
        self.issue_text.setPlainText(issue_text)
        self.log_text.setPlainText("\n".join(logs))
        preferred_tab = str(panel.get("preferred_tab") or "").strip().lower()
        switch_outer_tab = bool(panel.get("switch_result_tab", preferred_tab in {"issues", "logs"}))
        if preferred_tab == "issues":
            if switch_outer_tab and hasattr(self, "result_tabs"):
                self.result_tabs.setCurrentWidget(self.message_tabs.parentWidget())
            self.message_tabs.setCurrentWidget(self.issue_text)
        elif preferred_tab == "logs":
            if switch_outer_tab and hasattr(self, "result_tabs"):
                self.result_tabs.setCurrentWidget(self.message_tabs.parentWidget())
            self.message_tabs.setCurrentWidget(self.log_text)
        else:
            self.message_tabs.setCurrentWidget(self.info_text)

    def _confirm_prompt(self, prompt_result):
        prompt = (prompt_result or {}).get("prompt") or {}
        if not prompt.get("required"):
            return True
        title = str(prompt.get("title") or "请确认")
        message = str(prompt.get("message") or "")
        details = [str(item) for item in (prompt.get("details") or []) if str(item).strip()]
        body = message
        if details:
            body = (body + "\n\n" if body else "") + "\n".join(details)
        buttons = self.qt.QtWidgets.QMessageBox.StandardButton.Yes | self.qt.QtWidgets.QMessageBox.StandardButton.No
        answer = self.qt.QtWidgets.QMessageBox.question(
            self.window,
            title,
            body,
            buttons,
            self.qt.QtWidgets.QMessageBox.StandardButton.No,
        )
        return answer == self.qt.QtWidgets.QMessageBox.StandardButton.Yes

    def _file_dialog_filter_text(self, filters):
        filters = filters or []
        if not filters:
            return "所有文件 (*.*)"
        parts = []
        for item in filters:
            label = str((item or {}).get("label") or "所有文件")
            pattern = str((item or {}).get("pattern") or "*.*")
            parts.append(f"{label} ({pattern})")
        return ";;".join(parts)

    def _choose_file_path(self, action):
        described = self.engine_client.describe_file_action(
            action,
            current_plan_path=self.current_plan_path,
            plan_dir=self.plan_dir,
        )
        dialog = described.get("file_dialog") or {}
        title = str(dialog.get("title") or "选择文件")
        initial_path = str(dialog.get("initial_path") or "")
        filters = self._file_dialog_filter_text(dialog.get("filters") or [])
        if dialog.get("dialog") == "save_file":
            path, _ = self.qt.QtWidgets.QFileDialog.getSaveFileName(
                self.window,
                title,
                initial_path,
                filters,
            )
        else:
            path, _ = self.qt.QtWidgets.QFileDialog.getOpenFileName(
                self.window,
                title,
                initial_path,
                filters,
            )
        return path

    def _apply_imported_table_state(self, state):
        state = state or {}
        self.current_headers = list(state.get("headers") or [])
        self.current_rows = [list(row) for row in (state.get("rows") or [])]
        self.current_input_source = copy.deepcopy(state.get("source") or {"type": "file"})
        self.current_plan["headers"] = list(self.current_headers)
        self.current_plan["rows"] = [list(row) for row in self.current_rows]
        had_preview = self._clear_preview_for_input_change()
        table_context = self._table_context()
        self.config_form.set_headers(self.current_headers)
        self.config_form.set_table_names(table_context.get("table_names"))
        self.config_form.set_table_columns(table_context.get("table_columns"))
        self.config_form.set_plan(self.current_plan)
        self.refresh_catalog()
        self.update_input_summary()
        self.update_table(self.current_headers, self.current_rows, title=state.get("table_title") or "输入表格")
        self.show_node_config(self.node_list.currentRow())
        panel = state.get("message_panel") or self.engine_client.build_message_panel_state(
            mode="success",
            title="导入输入表格",
            body=str(state.get("issue_message") or ""),
        ).get("panel") or {}
        if had_preview:
            panel = self.engine_client.build_message_panel_state(
                mode="warning",
                title="输入数据源",
                body="输入已变更，旧预览结果已清空。",
                preferred_tab="issues",
            ).get("panel") or panel
        self._apply_message_panel(panel)
        status_message = str(state.get("status_message") or "已导入输入表格。")
        if had_preview:
            status_message += " 旧预览结果已清空。"
        self.status_bar.showMessage(status_message)

    def _apply_input_table_state(self, state):
        state = state or {}
        self.current_headers = list(state.get("headers") or [])
        self.current_rows = [list(row) for row in (state.get("rows") or [])]
        self.current_input_source = copy.deepcopy(state.get("source") or self.current_input_source or {})
        source_db_path = str((self.current_input_source or {}).get("db_path") or "").strip()
        if source_db_path:
            self.set_current_input_db_path(source_db_path, refresh=False)
        self.current_plan["headers"] = list(self.current_headers)
        self.current_plan["rows"] = [list(row) for row in self.current_rows]
        had_preview = self._clear_preview_for_input_change()
        table_context = self._table_context()
        self.config_form.set_headers(self.current_headers)
        self.config_form.set_table_names(table_context.get("table_names"))
        self.config_form.set_table_columns(table_context.get("table_columns"))
        self.config_form.set_plan(self.current_plan)
        self.refresh_catalog()
        self.update_input_summary()
        self.refresh_preview_table_combo()
        self.update_table(self.current_headers, self.current_rows, title=state.get("table_title") or "输入表格")
        self.show_node_config(self.node_list.currentRow())
        panel = state.get("message_panel")
        if had_preview:
            panel = self.engine_client.build_message_panel_state(
                mode="warning",
                title="输入数据源",
                body="输入已变更，旧预览结果已清空。",
                preferred_tab="issues",
            ).get("panel") or panel
        if panel:
            self._apply_message_panel(panel)
        status_message = str(state.get("status_message") or "已载入输入表格。")
        if had_preview:
            status_message += " 旧预览结果已清空。"
        self.status_bar.showMessage(status_message)

    def _apply_loaded_plan_state(self, state):
        state = state or {}
        self.current_plan_path = Path(state["plan_path"]) if state.get("plan_path") else None
        self.current_plan = copy.deepcopy(state.get("plan") or self.current_plan)
        self.current_headers = list(state.get("headers") or [])
        self.current_rows = [list(row) for row in (state.get("rows") or [])]
        self.current_input_source = copy.deepcopy(state.get("input_source") or self.current_input_source or {})
        self.set_current_input_db_path(state.get("input_db_path") or "", refresh=False)
        self.apply_output_settings_from_plan(state.get("plan") or {})
        self.last_preview_headers = []
        self.last_preview_rows = []
        self._clear_node_config_preview_cache()
        self.refresh_all()
        panel = state.get("message_panel") or self.engine_client.build_message_panel_state(
            mode="info",
            title="打开计划",
            body=str(state.get("issue_message") or ""),
        ).get("panel") or {}
        self._apply_message_panel(panel)
        self.status_bar.showMessage(str(state.get("status_message") or "已打开计划。"))

    def _apply_saved_plan_state(self, state):
        state = state or {}
        self.current_plan = copy.deepcopy(state.get("plan") or self.current_plan)
        self.current_plan_path = Path(state["plan_path"]) if state.get("plan_path") else self.current_plan_path
        self.refresh_template_list(show_status=False)
        panel = state.get("message_panel") or {}
        if panel:
            self._apply_message_panel(panel)
        self.status_bar.showMessage(str(state.get("status_message") or "已保存计划。"))

    def show_selected_node_type_detail(self):
        node_type_id = self.current_node_type_id_from_combo()
        if node_type_id:
            self.show_node_detail(node_type_id)

    def show_catalog_node_detail(self):
        items = self.catalog_tree.selectedItems()
        if not items:
            return
        node_type_id = str(items[0].data(0, self.user_role) or "")
        if node_type_id:
            self.show_node_detail(node_type_id)

    def show_node_detail(self, node_type_id, preview_headers=None):
        headers = self.current_headers if preview_headers is None else list(preview_headers or [])
        try:
            described = self.engine_client.describe_node_detail(node_type_id, preview_headers=headers, **self._table_context())
        except Exception:
            described = {}
        try:
            context = self.engine_client.describe_node_config_context(
                node_type_id,
                preview_headers=headers,
                **self._table_context(),
            )
        except Exception:
            context = {}
        schema = described.get("schema") or self.node_schema_by_id.get(node_type_id) or {}
        detail = described.get("detail") or {}
        if not schema and not detail:
            return
        self._apply_node_detail_panel(detail, schema, context)

    def _apply_node_detail_panel(self, detail, schema=None, context=None):
        self._clear_plugin_config_views()
        self.plugin_warning_targets_by_link = {}
        detail = detail or {}
        schema = schema or {}
        context = context or {}
        title = str(detail.get("title") or schema.get("display_name") or "节点说明")
        category = str(detail.get("category") or schema.get("category_label") or schema.get("category") or "")
        node_type_id = str(detail.get("node_type_id") or schema.get("node_type_id") or "")
        risk = str(detail.get("risk") or schema.get("risk") or "")
        supported = detail.get("supported_headless")
        badges = [str(item) for item in (detail.get("badges") or []) if str(item).strip()]
        sections = list(detail.get("sections") or [])
        meta_items = [item for item in (detail.get("meta_items") or []) if isinstance(item, dict)]
        warning_items = [item for item in (context.get("warning_items") or []) if isinstance(item, dict)]
        help_sections = [item for item in (context.get("help_sections") or []) if isinstance(item, dict)]
        shared_config_sections = [item for item in (context.get("shared_config_sections") or []) if isinstance(item, dict)]

        if warning_items:
            warning_lines = []
            for item in warning_items:
                line = self._format_plugin_warning_item(item)
                if line:
                    warning_lines.append(line)
            if warning_lines:
                sections.append({"title": "结构化警告", "lines": warning_lines})
        if help_sections:
            preview_lines = []
            for item in help_sections[:4]:
                label = str(item.get("label") or item.get("key") or "").strip()
                first_section = next((section for section in (item.get("sections") or []) if isinstance(section, dict)), {})
                first_lines = [str(line).strip() for line in (first_section.get("lines") or []) if str(line).strip()]
                if label and first_lines:
                    preview_lines.append(f"{label}：{first_lines[0]}")
            if preview_lines:
                sections.append({"title": "配置提示", "lines": preview_lines})
        for section in shared_config_sections:
            title = str(section.get("title") or "").strip()
            lines = [str(line).strip() for line in (section.get("lines") or []) if str(line).strip()]
            if title or lines:
                sections.append({"title": title or "共享配置状态", "lines": lines})

        self.node_detail_title_label.setText(title)
        if meta_items:
            meta_text = str(detail.get("meta_text") or "").strip()
            if not meta_text:
                meta_text = " | ".join(
                    f"{str(item.get('label') or '').strip()}：{str(item.get('value') or '').strip()}"
                    for item in meta_items
                    if str(item.get("label") or "").strip() and str(item.get("value") or "").strip()
                )
            self.node_detail_meta_label.setText(meta_text)
        else:
            meta_parts = []
            if category:
                meta_parts.append(f"分类：{category}")
            if node_type_id:
                meta_parts.append(f"类型：{node_type_id}")
            if risk:
                meta_parts.append(f"风险：{risk}")
            if supported is not None:
                meta_parts.append("执行层：支持 headless" if supported else "执行层：仅旧执行链")
            self.node_detail_meta_label.setText(" | ".join(meta_parts))
        self.node_detail_badges_label.setText(("标签：" + " / ".join(badges)) if badges else "")

        blocks = []
        summary = str(detail.get("summary") or "").strip()
        if summary:
            blocks.append(f"<p><b>摘要</b><br>{summary}</p>")
        for section in sections:
            section_title = str((section or {}).get("title") or "").strip()
            lines = [str(item) for item in ((section or {}).get("lines") or []) if str(item).strip()]
            if not section_title and not lines:
                continue
            body = "<br>".join(lines)
            if section_title:
                blocks.append(f"<p><b>{section_title}</b><br>{body}</p>")
            elif body:
                blocks.append(f"<p>{body}</p>")
        self.node_detail_sections.setHtml("".join(blocks) or "<p>暂无说明</p>")

    def _handle_config_field_action(self, payload):
        payload = payload or {}
        field_key = str(payload.get("field_key") or "")
        action = payload.get("action") or {}
        action_key = str(action.get("key") or "")
        if action_key == "pick_table_name":
            return self._pick_single_table_for_field(field_key, payload)
        if action_key == "pick_table_names":
            return self._pick_multi_tables_for_field(field_key, payload)
        if action_key == "pick_table_field":
            return self._pick_single_table_field_for_field(field_key, payload)
        if action_key == "pick_table_fields":
            return self._pick_multi_table_fields_for_field(field_key, payload)
        if action_key == "pick_preview_header":
            return self._pick_single_value_for_field(field_key, payload)
        if action_key == "pick_preview_headers":
            return self._pick_multi_values_for_field(field_key, payload)
        if action_key == "pick_plan_ref":
            return self._pick_plan_reference_for_field(field_key, payload)
        if action_key == "pick_runtime_ref":
            return self._pick_runtime_reference_for_field(field_key, payload)
        if action_key == "pick_plugin_input_table":
            return self._pick_plugin_input_table_for_field(field_key, payload)
        if action_key == "browse_directory":
            return self._browse_directory_for_field(field_key, payload)
        if action_key == "browse_file":
            return self._browse_file_for_field(field_key, payload)
        return {}

    def _browse_directory_for_field(self, field_key, payload):
        current = str(payload.get("value") or "")
        path = self.qt.QtWidgets.QFileDialog.getExistingDirectory(
            self.window,
            f"选择{field_key}",
            current,
        )
        return {"value": path} if path else {}

    def _browse_file_for_field(self, field_key, payload):
        current = str(payload.get("value") or "")
        path, _ = self.qt.QtWidgets.QFileDialog.getOpenFileName(
            self.window,
            f"选择{field_key}",
            current,
            "所有文件 (*.*)",
        )
        return {"value": path} if path else {}

    def _pick_plugin_input_table_for_field(self, field_key, payload):
        picker_context = self.engine_client.describe_picker_context(
            plan=self._picker_plan(),
            field_key=field_key,
            action_key="pick_plugin_input_table",
            options_source=payload.get("options_source") or (payload.get("schema") or {}).get("options_source") or {},
            current_values=payload.get("current_values") or {},
        ).get("picker_context") or {}
        candidates = [str(item) for item in (picker_context.get("candidates") or []) if str(item).strip()]
        if not candidates:
            self._apply_feedback(self.engine_client.describe_picker_feedback(
                action_key="pick_plugin_input_table",
                field_key=field_key,
                candidates=candidates,
            ))
            return {}
        current = str(payload.get("value") or "")
        value, accepted = self.qt.QtWidgets.QInputDialog.getItem(
            self.window,
            f"选择{field_key}",
            "可用输入表：",
            candidates,
            max(0, candidates.index(current)) if current in candidates else 0,
            False,
        )
        if not accepted:
            return {}
        return {"value": value}

    def _picker_plan(self):
        plan = getattr(self, "plan", None)
        return plan if isinstance(plan, dict) else self.current_plan

    def _pick_plan_reference_for_field(self, field_key, payload):
        action = payload.get("action") or {}
        ref_kind = str(action.get("ref_kind") or "").strip()
        picker_context = self.engine_client.describe_picker_context(
            plan=self._picker_plan(),
            field_key=field_key,
            action_key="pick_plan_ref",
            ref_kind=ref_kind,
            options_source=payload.get("options_source") or {},
        ).get("picker_context") or {}
        candidates = [str(item) for item in (picker_context.get("candidates") or payload.get("plan_refs") or []) if str(item).strip()]
        if not candidates:
            self._apply_feedback(self.engine_client.describe_picker_feedback(
                action_key="pick_plan_ref",
                field_key=field_key,
                candidates=candidates,
                ref_kind=ref_kind,
            ))
            return {}
        current = str(payload.get("value") or "")
        if len(candidates) == 1:
            return {"value": candidates[0]}
        value, accepted = self.qt.QtWidgets.QInputDialog.getItem(
            self.window,
            f"选择{field_key}",
            "可用循环：" if ref_kind == "loop_id" else "可用锚点：",
            candidates,
            max(0, candidates.index(current)) if current in candidates else 0,
            False,
        )
        if not accepted:
            return {}
        return {"value": value}

    def _pick_runtime_reference_for_field(self, field_key, payload):
        action = payload.get("action") or {}
        ref_kind = str(action.get("ref_kind") or "").strip()
        picker_context = self.engine_client.describe_picker_context(
            plan=self._picker_plan(),
            field_key=field_key,
            action_key="pick_runtime_ref",
            ref_kind=ref_kind,
            options_source=payload.get("options_source") or {},
        ).get("picker_context") or {}
        candidates = [str(item) for item in (picker_context.get("candidates") or payload.get("runtime_refs") or []) if str(item).strip()]
        if not candidates:
            self._apply_feedback(self.engine_client.describe_picker_feedback(
                action_key="pick_runtime_ref",
                field_key=field_key,
                candidates=candidates,
                ref_kind=ref_kind,
            ))
            return {}
        current = str(payload.get("value") or "")
        if len(candidates) == 1:
            return {"value": candidates[0]}
        value, accepted = self.qt.QtWidgets.QInputDialog.getItem(
            self.window,
            f"选择{field_key}",
            "可用中转表：" if ref_kind == "transit_table" else "可用中转名称：",
            candidates,
            max(0, candidates.index(current)) if current in candidates else 0,
            False,
        )
        if not accepted:
            return {}
        return {"value": value}

    def _pick_single_table_for_field(self, field_key, payload):
        picker_context = self.engine_client.describe_picker_context(
            field_key=field_key,
            action_key="pick_table_name",
            options_source=payload.get("options_source") or (payload.get("schema") or {}).get("options_source") or {},
            table_names=payload.get("table_names") or [],
        ).get("picker_context") or {}
        candidates = [str(item) for item in (picker_context.get("candidates") or payload.get("table_names") or []) if str(item).strip()]
        if not candidates:
            self._apply_feedback(self.engine_client.describe_picker_feedback(
                action_key="pick_table_name",
                field_key=field_key,
                candidates=candidates,
            ))
            return {}
        current = str(payload.get("value") or "")
        value, accepted = self.qt.QtWidgets.QInputDialog.getItem(
            self.window,
            f"选择{field_key}",
            "可用数据表：",
            candidates,
            max(0, candidates.index(current)) if current in candidates else 0,
            False,
        )
        if not accepted:
            return {}
        return {"value": value}

    def _pick_multi_tables_for_field(self, field_key, payload):
        picker_context = self.engine_client.describe_picker_context(
            field_key=field_key,
            action_key="pick_table_names",
            options_source=payload.get("options_source") or (payload.get("schema") or {}).get("options_source") or {},
            table_names=payload.get("table_names") or [],
            current_values=self._current_picker_values(payload),
        ).get("picker_context") or {}
        candidates = [str(item) for item in (picker_context.get("candidates") or payload.get("table_names") or []) if str(item).strip()]
        if not candidates:
            self._apply_feedback(self.engine_client.describe_picker_feedback(
                action_key="pick_table_names",
                field_key=field_key,
                candidates=candidates,
            ))
            return {}
        selected = set(str(item) for item in (payload.get("value") or []) if str(item).strip())

        dialog = self.qt.QtWidgets.QDialog(self.window)
        dialog.setWindowTitle(f"选择{field_key}")
        dialog.resize(360, 420)
        layout = self.qt.QtWidgets.QVBoxLayout(dialog)
        hint = self.qt.QtWidgets.QLabel("勾选需要关联的数据表，可多选。")
        layout.addWidget(hint)
        list_widget = self.qt.QtWidgets.QListWidget(dialog)
        list_widget.setSelectionMode(self.qt.QtWidgets.QAbstractItemView.SelectionMode.NoSelection)
        for item in candidates:
            row = self.qt.QtWidgets.QListWidgetItem(item, list_widget)
            row.setFlags(row.flags() | self.qt.QtCore.Qt.ItemFlag.ItemIsUserCheckable)
            row.setCheckState(
                self.qt.QtCore.Qt.CheckState.Checked if item in selected else self.qt.QtCore.Qt.CheckState.Unchecked
            )
        layout.addWidget(list_widget, 1)
        button_box = self.qt.QtWidgets.QDialogButtonBox(
            self.qt.QtWidgets.QDialogButtonBox.StandardButton.Ok | self.qt.QtWidgets.QDialogButtonBox.StandardButton.Cancel,
            parent=dialog,
        )
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)
        if dialog.exec() != int(self.qt.QtWidgets.QDialog.DialogCode.Accepted):
            return {}

        values = []
        for index in range(list_widget.count()):
            item = list_widget.item(index)
            if item.checkState() == self.qt.QtCore.Qt.CheckState.Checked:
                values.append(item.text())
        return {"value": values}

    def _pick_single_value_for_field(self, field_key, payload):
        candidates = [str(item) for item in (payload.get("headers") or []) if str(item).strip()]
        if not candidates:
            self._apply_feedback(self.engine_client.describe_picker_feedback(
                action_key="pick_preview_header",
                field_key=field_key,
                candidates=candidates,
            ))
            return {}
        current = str(payload.get("value") or "")
        value, accepted = self.qt.QtWidgets.QInputDialog.getItem(
            self.window,
            f"选择{field_key}",
            "可用字段：",
            candidates,
            max(0, candidates.index(current)) if current in candidates else 0,
            False,
        )
        if not accepted:
            return {}
        return {"value": value}

    def _pick_multi_values_for_field(self, field_key, payload):
        candidates = [str(item) for item in (payload.get("headers") or []) if str(item).strip()]
        if not candidates:
            self._apply_feedback(self.engine_client.describe_picker_feedback(
                action_key="pick_preview_headers",
                field_key=field_key,
                candidates=candidates,
            ))
            return {}
        selected = set(str(item) for item in (payload.get("value") or []) if str(item).strip())

        dialog = self.qt.QtWidgets.QDialog(self.window)
        dialog.setWindowTitle(f"选择{field_key}")
        dialog.resize(360, 420)
        layout = self.qt.QtWidgets.QVBoxLayout(dialog)
        hint = self.qt.QtWidgets.QLabel("勾选需要的字段，可多选。")
        layout.addWidget(hint)
        list_widget = self.qt.QtWidgets.QListWidget(dialog)
        list_widget.setSelectionMode(self.qt.QtWidgets.QAbstractItemView.SelectionMode.NoSelection)
        for item in candidates:
            row = self.qt.QtWidgets.QListWidgetItem(item, list_widget)
            row.setFlags(row.flags() | self.qt.QtCore.Qt.ItemFlag.ItemIsUserCheckable)
            row.setCheckState(
                self.qt.QtCore.Qt.CheckState.Checked if item in selected else self.qt.QtCore.Qt.CheckState.Unchecked
            )
        layout.addWidget(list_widget, 1)
        button_box = self.qt.QtWidgets.QDialogButtonBox(
            self.qt.QtWidgets.QDialogButtonBox.StandardButton.Ok | self.qt.QtWidgets.QDialogButtonBox.StandardButton.Cancel,
            parent=dialog,
        )
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)
        if dialog.exec() != int(self.qt.QtWidgets.QDialog.DialogCode.Accepted):
            return {}

        values = []
        for index in range(list_widget.count()):
            item = list_widget.item(index)
            if item.checkState() == self.qt.QtCore.Qt.CheckState.Checked:
                values.append(item.text())
        return {"value": values}

    def _pick_multi_table_fields_for_field(self, field_key, payload):
        action = payload.get("action") or {}
        schema = payload.get("schema") or {}
        picker_context = self.engine_client.describe_picker_context(
            field_key=field_key,
            action_key="pick_table_fields",
            options_source=(schema.get("options_source") or {}),
            table_columns=payload.get("table_columns") or {},
            current_values=self._current_picker_values(payload),
        ).get("picker_context") or {}
        table_field = str(picker_context.get("table_field") or action.get("table_field") or (schema.get("options_source") or {}).get("table_field") or "").strip()
        table_name = str(picker_context.get("table_name") or "")
        candidates = [str(item) for item in (picker_context.get("candidates") or []) if str(item).strip()]
        if not table_name:
            self._apply_feedback(self.engine_client.describe_picker_feedback(
                action_key="pick_table_fields",
                field_key=field_key,
                table_name=table_name,
                table_field=table_field,
                candidates=candidates,
            ))
            return {}
        if not candidates:
            self._apply_feedback(self.engine_client.describe_picker_feedback(
                action_key="pick_table_fields",
                field_key=field_key,
                table_name=table_name,
                table_field=table_field,
                candidates=candidates,
            ))
            return {}
        selected = set(str(item) for item in (payload.get("value") or []) if str(item).strip())

        dialog = self.qt.QtWidgets.QDialog(self.window)
        dialog.setWindowTitle(f"选择{field_key}")
        dialog.resize(360, 420)
        layout = self.qt.QtWidgets.QVBoxLayout(dialog)
        hint = self.qt.QtWidgets.QLabel(f"当前数据表：{table_name}")
        layout.addWidget(hint)
        list_widget = self.qt.QtWidgets.QListWidget(dialog)
        list_widget.setSelectionMode(self.qt.QtWidgets.QAbstractItemView.SelectionMode.NoSelection)
        for item in candidates:
            row = self.qt.QtWidgets.QListWidgetItem(item, list_widget)
            row.setFlags(row.flags() | self.qt.QtCore.Qt.ItemFlag.ItemIsUserCheckable)
            row.setCheckState(
                self.qt.QtCore.Qt.CheckState.Checked if item in selected else self.qt.QtCore.Qt.CheckState.Unchecked
            )
        layout.addWidget(list_widget, 1)
        button_box = self.qt.QtWidgets.QDialogButtonBox(
            self.qt.QtWidgets.QDialogButtonBox.StandardButton.Ok | self.qt.QtWidgets.QDialogButtonBox.StandardButton.Cancel,
            parent=dialog,
        )
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)
        if dialog.exec() != int(self.qt.QtWidgets.QDialog.DialogCode.Accepted):
            return {}

        values = []
        for index in range(list_widget.count()):
            item = list_widget.item(index)
            if item.checkState() == self.qt.QtCore.Qt.CheckState.Checked:
                values.append(item.text())
        return {"value": values}

    def _pick_single_table_field_for_field(self, field_key, payload):
        action = payload.get("action") or {}
        schema = payload.get("schema") or {}
        picker_context = self.engine_client.describe_picker_context(
            field_key=field_key,
            action_key="pick_table_field",
            options_source=(schema.get("options_source") or {}),
            table_columns=payload.get("table_columns") or {},
            current_values=self._current_picker_values(payload),
        ).get("picker_context") or {}
        table_field = str(picker_context.get("table_field") or action.get("table_field") or (schema.get("options_source") or {}).get("table_field") or "").strip()
        table_name = str(picker_context.get("table_name") or "")
        candidates = [str(item) for item in (picker_context.get("candidates") or []) if str(item).strip()]
        if not table_name:
            self._apply_feedback(self.engine_client.describe_picker_feedback(
                action_key="pick_table_field",
                field_key=field_key,
                table_name=table_name,
                table_field=table_field,
                candidates=candidates,
            ))
            return {}
        if not candidates:
            self._apply_feedback(self.engine_client.describe_picker_feedback(
                action_key="pick_table_field",
                field_key=field_key,
                table_name=table_name,
                table_field=table_field,
                candidates=candidates,
            ))
            return {}
        current = str(payload.get("value") or "")
        value, accepted = self.qt.QtWidgets.QInputDialog.getItem(
            self.window,
            f"选择{field_key}",
            f"{table_name} 可用字段：",
            candidates,
            max(0, candidates.index(current)) if current in candidates else 0,
            False,
        )
        if not accepted:
            return {}
        return {"value": value}

    def _current_config_field_value(self, field_key):
        field = self.config_form.config_fields.get(field_key) or {}
        if not field:
            return ""
        return self.config_form._field_value_for_action(field)

    def _current_picker_values(self, payload):
        values = {}
        try:
            values.update(self.config_form._current_field_values())
        except Exception:
            pass
        if isinstance(payload, dict):
            extra = payload.get("current_values") or {}
            if isinstance(extra, dict):
                values.update(extra)
        return values

    def _apply_output_form_settings(self, settings):
        mode = str((settings or {}).get("mode") or "").strip()
        if mode:
            index = self.output_mode_combo.findText(mode)
            if index >= 0:
                self.output_mode_combo.setCurrentIndex(index)
        self.output_table_edit.setText(str((settings or {}).get("target") or "结果表"))
        self.output_db_path_edit.setText(str((settings or {}).get("db_path") or ""))
        self.output_path_edit.setText(str((settings or {}).get("path") or ""))
        self.backup_checkbox.setChecked(bool((settings or {}).get("backup_before_overwrite", True)))

    def _apply_output_panel_state(self, panel_state=None):
        if panel_state is None:
            panel_state = self.engine_client.build_output_panel_state(self.current_output_settings())
        self.output_mode_meta = dict(panel_state.get("mode_meta") or self.output_mode_meta)
        self._apply_output_form_settings(panel_state.get("settings") or {})
        fields = {field.get("key"): field for field in (panel_state.get("fields") or [])}
        for key, ui_field in self.output_form_fields.items():
            payload = fields.get(key) or {}
            ui_field["schema"] = payload
            visible = bool(payload.get("visible", key == "mode"))
            ui_field.get("label").setVisible(visible)
            (ui_field.get("widget") or ui_field.get("editor")).setVisible(visible)
            action_button = ui_field.get("action_button")
            action = payload.get("action") or {}
            if action_button is not None:
                action_button.setToolTip(str(action.get("label") or ""))
                action_button.setVisible(bool(action) and visible)
        view_state = panel_state.get("view_state") or {}
        if view_state.get("refresh_preview_sources"):
            self.refresh_preview_table_combo()

    def _apply_output_form_state(self):
        self._apply_output_panel_state()

    def _trigger_output_field_action(self, field_key):
        field = self.output_form_fields.get(field_key) or {}
        action = (field.get("schema") or {}).get("action") or {}
        if not action:
            return
        path = self._choose_custom_file_path(action)
        if not path:
            return
        editor = field.get("editor")
        if editor is not None:
            editor.setText(str(path))
        if field_key == "db_path":
            self._apply_output_form_state()

    def _choose_custom_file_path(self, dialog):
        dialog = dialog or {}
        title = str(dialog.get("title") or "选择文件")
        filters = self._file_dialog_filter_text(dialog.get("filters") or [])
        if dialog.get("dialog") == "save_file":
            path, _ = self.qt.QtWidgets.QFileDialog.getSaveFileName(self.window, title, "", filters)
        else:
            path, _ = self.qt.QtWidgets.QFileDialog.getOpenFileName(self.window, title, "", filters)
        return path

    def update_table(self, headers, rows, title="表格预览"):
        self.preview_headers = list(headers or [])
        self.preview_rows = [list(row) for row in (rows or [])]
        self.table_model.set_table(self.preview_headers, self.preview_rows)
        self.table_title.setText(f"{title} · {len(self.preview_rows)} 行 x {len(self.preview_headers)} 列")

    def _clear_preview_for_input_change(self):
        had_preview = bool(self.last_preview_headers or self.last_preview_rows or self.node_config_preview_cache)
        self.last_preview_headers = []
        self.last_preview_rows = []
        self._clear_node_config_preview_cache()
        return had_preview

    def load_sample_plan(self):
        self.current_plan_path = None
        self.current_plan = copy.deepcopy(SAMPLE_PLAN)
        self.current_headers = list(SAMPLE_HEADERS)
        self.current_rows = [list(row) for row in SAMPLE_ROWS]
        self.current_input_source = {"type": "sample"}
        self.set_current_input_db_path("", refresh=False)
        self.last_preview_headers = []
        self.last_preview_rows = []
        self._clear_node_config_preview_cache()
        self.refresh_all()
        self._apply_message_panel(self.engine_client.build_message_panel_state(
            mode="success",
            title="示例计划",
            body="已载入 Qt6 示例计划。",
        ).get("panel") or {})

    def reload_sample_input(self):
        self.current_headers = list(SAMPLE_HEADERS)
        self.current_rows = [list(row) for row in SAMPLE_ROWS]
        self.current_input_source = {"type": "sample"}
        self.set_current_input_db_path("", refresh=False)
        self.last_preview_headers = []
        self.last_preview_rows = []
        self._clear_node_config_preview_cache()
        self.current_plan["headers"] = list(self.current_headers)
        self.current_plan["rows"] = [list(row) for row in self.current_rows]
        self.update_input_summary()
        self.refresh_preview_table_combo()
        self.update_table(self.current_headers, self.current_rows, title="输入表格")
        self.status_bar.showMessage("已重新载入示例输入。")

    def current_data_source_db_path(self):
        return self.current_input_db_path

    def current_workflow_context(self):
        source = copy.deepcopy(self.current_input_source if isinstance(self.current_input_source, dict) else {})
        db_path = self.current_data_source_db_path()
        snapshot = {
            "db_path": db_path,
            "input_db_path": db_path,
            "input_source": copy.deepcopy(source),
        }
        if source:
            snapshot["input_table_name"] = str(source.get("table_name") or source.get("table") or "").strip()
        context = {
            "workflow_snapshot": snapshot,
            "input_source": source,
        }
        if db_path:
            context["db_path"] = db_path
            context["input_db_path"] = db_path
        return context

    def _merge_workflow_context(self, context=None):
        merged = self.current_workflow_context()
        if not isinstance(context, dict):
            return merged
        incoming = copy.deepcopy(context)
        incoming_snapshot = incoming.pop("workflow_snapshot", None)
        if isinstance(incoming_snapshot, dict):
            merged_snapshot = merged.setdefault("workflow_snapshot", {})
            merged_snapshot.update(incoming_snapshot)
        merged.update(incoming)
        return merged

    def set_current_input_db_path(self, db_path, *, refresh=True, show_status=False):
        db_path = str(db_path or "").strip()
        changed = db_path != self.current_input_db_path
        self.current_input_db_path = db_path
        if hasattr(self, "input_db_path_edit") and self.input_db_path_edit.text().strip() != db_path:
            self.input_db_path_edit.setText(db_path)
        if not changed and not refresh:
            return
        if refresh:
            self.refresh_input_table_combo(show_status=show_status)

    def apply_input_db_path_from_edit(self, *, show_status=True):
        self.set_current_input_db_path(
            self.input_db_path_edit.text().strip() if hasattr(self, "input_db_path_edit") else "",
            refresh=True,
            show_status=show_status,
        )

    def choose_input_db_path(self):
        path, _ = self.qt.QtWidgets.QFileDialog.getOpenFileName(
            self.window,
            "选择输入 SQLite 数据库",
            self.current_data_source_db_path(),
            "SQLite 数据库 (*.db *.sqlite);;所有文件 (*.*)",
        )
        if path:
            self.set_current_input_db_path(path, refresh=True, show_status=True)

    def refresh_input_table_combo(self, *, show_status=True):
        if not hasattr(self, "input_table_combo"):
            return
        db_path = self.current_data_source_db_path()
        current_table = self.input_table_combo.currentData()
        list_action = self._data_source_table_action("list_tables")
        load_action = self._data_source_table_action("load_table")
        list_available = bool(list_action.get("engine_action"))
        load_available = bool(load_action.get("engine_action"))
        if not list_available:
            self.input_table_combo.clear()
            self.load_input_table_button.setEnabled(False)
            self.input_table_combo.setToolTip("当前数据源服务未声明 list_tables 表动作。")
            self.load_input_table_button.setToolTip("当前数据源服务未声明 load_table 表动作。")
            if show_status:
                self.status_bar.showMessage("当前数据源服务不支持列出输入表。")
            return
        try:
            listed = self.engine_client.list_tables(db_path=db_path or None)
        except Exception as exc:
            listed = {
                "ok": False,
                "tables": [],
                "issues": [{
                    "severity": "warning",
                    "code": "input_table_list_failed",
                    "message": str(exc),
                }],
            }
        tables = []
        for item in listed.get("tables") or []:
            name = self._table_record_name(item)
            if name:
                tables.append(name)
        self.input_table_combo.blockSignals(True)
        self.input_table_combo.clear()
        restore_index = 0
        for index, table_name in enumerate(tables):
            self.input_table_combo.addItem(table_name, table_name)
            if table_name == current_table:
                restore_index = index
        self.input_table_combo.setCurrentIndex(restore_index if tables else -1)
        self.input_table_combo.blockSignals(False)
        self.input_table_combo.setToolTip(str(list_action.get("label") or "从输入 SQLite 数据库选择表作为工作流输入"))
        load_tooltip = str(load_action.get("label") or "载入选中的 SQLite 表作为工作流输入")
        engine_action = str(load_action.get("engine_action") or "").strip()
        if engine_action:
            load_tooltip += f"\n服务动作：{engine_action}"
        self.load_input_table_button.setToolTip(load_tooltip)
        self.load_input_table_button.setEnabled(bool(db_path and tables and load_available))
        if show_status:
            if db_path:
                self.status_bar.showMessage(f"输入表列表已刷新：{len(tables)} 个")
            else:
                self.status_bar.showMessage("请选择输入 SQLite 数据库后再刷新输入表。")

    def load_selected_input_table(self):
        if not self._has_data_source_table_action("load_table"):
            self._apply_message_panel(self.engine_client.build_message_panel_state(
                mode="warning",
                title="输入数据源",
                body="当前数据源服务未声明 load_table 表动作。",
                preferred_tab="issues",
            ).get("panel") or {})
            self.status_bar.showMessage("当前数据源服务不支持载入输入表。")
            return
        db_path = self.current_data_source_db_path()
        table_name = str(self.input_table_combo.currentData() or self.input_table_combo.currentText() or "").strip()
        if not db_path:
            self._apply_message_panel(self.engine_client.build_message_panel_state(
                mode="warning",
                title="输入数据源",
                body="请先选择输入 SQLite 数据库。",
                preferred_tab="issues",
            ).get("panel") or {})
            self.status_bar.showMessage("载入输入表需要数据库路径。")
            return
        if not table_name:
            self._apply_message_panel(self.engine_client.build_message_panel_state(
                mode="warning",
                title="输入数据源",
                body="请先选择要载入的 SQLite 表。",
                preferred_tab="issues",
            ).get("panel") or {})
            self.status_bar.showMessage("请先选择输入表。")
            return
        loaded = self.engine_client.load_table({
            "type": "sqlite",
            "db_path": db_path,
            "table_name": table_name,
        })
        if not loaded.get("ok"):
            self._apply_message_panel(self.engine_client.build_message_panel_state(
                mode="error",
                title="载入输入表失败",
                issues=loaded.get("issues") or [],
                preferred_tab="issues",
            ).get("panel") or {})
            self.status_bar.showMessage("载入输入表失败")
            return
        table = loaded.get("table") or {}
        self.set_current_input_db_path(db_path, refresh=False)
        self._apply_input_table_state({
            "headers": list(table.get("headers") or []),
            "rows": [list(row) for row in (table.get("rows") or [])],
            "source": loaded.get("source") or {"type": "sqlite", "db_path": db_path, "table_name": table_name},
            "table_title": f"输入表格：{table_name}",
            "status_message": f"已载入输入表：{table_name}",
            "message_panel": self.engine_client.build_message_panel_state(
                mode="success",
                title="输入数据源",
                body=f"已载入 SQLite 表：{table_name}",
            ).get("panel") or {},
        })

    def open_data_source_manager(self):
        self.data_source_manager_controller = DataSourceManagerWindow(
            self.qt,
            engine_client=self.engine_client,
            parent=self.window,
            initial_headers=self.current_headers,
            initial_rows=self.current_rows,
            initial_source=self.current_input_source,
            db_path=self.current_data_source_db_path(),
            on_apply=self._apply_data_source_manager_input,
            on_db_path_changed=self._handle_data_source_manager_db_path,
        )
        self.data_source_manager_controller.show()
        self.status_bar.showMessage("已打开输入数据源管理。")

    def _handle_data_source_manager_db_path(self, db_path):
        self.set_current_input_db_path(db_path, refresh=True, show_status=False)

    def _apply_data_source_manager_input(self, state):
        source = (state or {}).get("source") or {}
        if isinstance(source, dict) and source.get("db_path"):
            self.set_current_input_db_path(source.get("db_path"), refresh=False)
        self._apply_input_table_state(state)
        self.refresh_input_table_combo(show_status=False)

    def import_table(self):
        path = self._choose_file_path("import_table")
        if not path:
            return
        try:
            imported = self.engine_client.import_table_file(path)
            state = self.engine_client.build_import_table_state(imported).get("state") or {}
            self._apply_imported_table_state(state)
        except Exception as exc:
            self.show_error("导入失败", str(exc))

    def open_plan(self):
        path = self._choose_file_path("open_plan")
        if path:
            self.load_plan_path(Path(path))

    def load_selected_plan_template(self):
        path = self.plan_template_combo.currentData()
        if path:
            self.load_plan_path(Path(path))

    def load_plan_path(self, path):
        try:
            loaded = self.engine_client.load_plan_template(path)
            if not loaded.get("ok"):
                self._apply_feedback(self.engine_client.describe_plan_file_failure(
                    action="打开计划",
                    issues=loaded.get("issues") or [],
                ))
                return
            state = self.engine_client.build_loaded_plan_state(loaded).get("state") or {}
            self._apply_loaded_plan_state(state)
        except Exception as exc:
            self.show_error("打开失败", str(exc))

    def save_plan(self):
        path = self.current_plan_path
        if path is None:
            selected = self._choose_file_path("save_plan")
            if not selected:
                return
            path = Path(selected)
        try:
            saved = self.engine_client.save_plan_template(
                path,
                self.current_plan,
                headers=self.current_headers,
                rows=self.current_rows,
                output_mode=self.output_mode_combo.currentText(),
                output_table=self.output_table_edit.text(),
                backup_before_overwrite=self.backup_checkbox.isChecked(),
                db_path=self.output_db_path_edit.text(),
                output_path=self.output_path_edit.text(),
                input_source=self.current_input_source,
                input_db_path=self.current_data_source_db_path(),
            )
            if not saved.get("ok"):
                self._apply_feedback(self.engine_client.describe_plan_file_failure(
                    action="保存计划",
                    issues=saved.get("issues") or [],
                ))
                return
            state = self.engine_client.build_saved_plan_state(saved, self.current_plan).get("state") or {}
            self._apply_saved_plan_state(state)
        except Exception as exc:
            self.show_error("保存失败", str(exc))

    def validate_plan(self):
        combined = self.engine_client.validate_workflow_request(
            self.current_plan,
            execute_actions=True,
            output_settings=self.current_output_settings(),
            workflow_db_path=self.current_data_source_db_path(),
        )
        self._apply_feedback(self.engine_client.describe_validation_feedback(combined))
        return combined

    def build_access_precheck(self, plan=None, *, execute_actions=True, stop_index=None, confirmed=False):
        result = self.engine_client.validate_workflow_request(
            plan or self.current_plan,
            execute_actions=execute_actions,
            stop_index=stop_index,
            output_settings=self.current_output_settings(),
            workflow_db_path=self.current_data_source_db_path(),
            confirmed=confirmed,
        )
        return result.get("access_precheck") or {}

    def preview_to_selected_node(self):
        index = self.selected_node_index()
        if index is None:
            self._apply_feedback(self.engine_client.describe_selection_feedback(
                selected_index=index,
                purpose="预览",
            ))
            return
        self.preview_plan(stop_index=index, title=f"预览到节点 {index + 1}")

    def preview_full_plan(self):
        self.preview_plan(stop_index=None, title="Headless 预览结果")

    def preview_plan(self, stop_index=None, title="Headless 预览结果"):
        input_table = self._input_table_payload()
        plan = copy.deepcopy(self.current_plan)
        validation = self.engine_client.validate_workflow_request(
            plan,
            execute_actions=False,
            stop_index=stop_index,
            output_settings=self.current_output_settings(),
            workflow_db_path=self.current_data_source_db_path(),
        )
        if not (validation.get("validation") or {}).get("ok"):
            self._apply_feedback(
                self.engine_client.describe_validation_feedback(validation),
                fallback_status="预览前校验失败",
            )
            return
        self.start_workflow_job(
            "preview_plan",
            plan,
            input_table=input_table,
            title=title,
            stop_index=stop_index,
            status_prefix="预览",
        )

    def execute_plan(self):
        input_table = self._input_table_payload()
        validation = self.validate_plan()
        if not validation.get("ok"):
            return
        access_precheck = validation.get("access_precheck") or {}
        prompt = self.engine_client.describe_confirmation_prompt(
            action="run_plan",
            plan=self.current_plan,
            output_settings=self.current_output_settings(),
            access_precheck=access_precheck,
        )
        if not self._confirm_prompt(prompt):
            self.status_bar.showMessage("已取消执行")
            return
        self.start_workflow_job(
            "run_plan",
            copy.deepcopy(self.current_plan),
            input_table=input_table,
            title="执行结果",
            execute_actions=True,
            output_settings=self.current_output_settings(),
            confirmed=True,
            status_prefix="执行",
        )

    def start_workflow_job(self, job_action, plan, *, input_table=None, title="", status_prefix="", **options):
        if self.current_job_id:
            self._apply_feedback(self.engine_client.describe_job_run_conflict(current_job_id=self.current_job_id))
            return
        supplied_context = options.pop("context", None)
        supplied_initial_context = options.pop("initial_context", None)
        options["context"] = self._merge_workflow_context(
            supplied_context if supplied_context is not None else supplied_initial_context
        )
        try:
            started = self.engine_client.start_job(
                job_action,
                plan,
                input_table=input_table,
                **options,
            )
        except Exception as exc:
            self._apply_feedback(self.engine_client.describe_job_start_failure(
                status_prefix=status_prefix or "任务",
                error=exc,
            ))
            return

        self.current_job_id = str(started.get("job_id") or "")
        self.current_job_action = job_action
        self.current_job_title = title or "Headless 预览结果"
        self.current_job_event_sequence = 0
        self.current_job_messages = []
        self.current_job_started_at = time.perf_counter()
        self.current_job_has_workflow_elapsed = False
        self.current_job_stop_index = options.get("stop_index", options.get("stop_at"))
        self._clear_node_config_preview_cache()
        self._apply_job_progress_state(self.engine_client.build_job_progress_state(
            current_job_id=self.current_job_id,
            title=self.current_job_title,
            running=True,
        ).get("progress") or {})
        started_state = self.engine_client.describe_job_started(status_prefix=status_prefix or "任务")
        self._apply_message_panel(started_state.get("message_panel") or {})
        self.set_workflow_running(True)
        self.job_timer.start()
        self.poll_current_job()

    def cancel_current_job(self):
        if not self.current_job_id:
            return
        try:
            result = self.engine_client.cancel_job(self.current_job_id)
            self.append_job_message(result.get("message", "已请求取消任务。"))
            self.status_bar.showMessage("已请求取消后台任务")
        except Exception as exc:
            failure = self.engine_client.describe_job_cancel_failure(error=exc)
            self._apply_message_panel(failure.get("message_panel") or {})
            self.status_bar.showMessage(failure.get("status_message") or "取消任务失败")

    def poll_current_job(self):
        if not self.current_job_id:
            self.job_timer.stop()
            return
        try:
            events = self.engine_client.get_job_events(
                self.current_job_id,
                since=self.current_job_event_sequence,
            )
            self.current_job_event_sequence = int(events.get("next_sequence", self.current_job_event_sequence) or 0)
            for event in events.get("events", []):
                self.handle_job_event(event)
            status = self.engine_client.get_job_status(self.current_job_id, include_result=True)
        except Exception as exc:
            self.job_timer.stop()
            self.set_workflow_running(False)
            failure = self.engine_client.describe_job_poll_failure(error=exc)
            self._apply_message_panel(failure.get("message_panel") or {})
            self.status_bar.showMessage(failure.get("status_message") or "后台任务状态读取失败")
            self.current_job_id = ""
            return

        if status.get("done"):
            self.finish_workflow_job(status)

    def handle_job_event(self, event):
        event_type = event.get("type", "")
        message = event.get("message", "")
        level = self._job_event_level(event_type)
        if event_type in {"node_done", "node_error"}:
            message = self._message_with_elapsed(message, event.get("elapsed_seconds"), label="耗时")
        elif event_type in {"workflow_done", "workflow_cancelled"}:
            rows = event.get("rows")
            cols = event.get("cols")
            if event_type == "workflow_cancelled":
                message = "工作流已取消"
            else:
                message = "工作流完成"
            if rows is not None and cols is not None:
                message = f"{message}：{rows} 行 × {cols} 列"
            message = self._message_with_elapsed(message, event.get("elapsed_seconds"), label="总耗时")
            self.current_job_has_workflow_elapsed = True
        if message:
            self.append_job_message(message, level=level, timestamp=event.get("timestamp"))
        if event_type == "node_start":
            pass
        elif event_type == "node_progress":
            pass
        elif event_type == "node_done":
            pass
        elif event_type == "job_cancel_requested":
            pass
        self._apply_job_progress_state(self.engine_client.build_job_progress_state(
            current_job_id=self.current_job_id,
            title=self.current_job_title,
            event=event,
            running=bool(self.current_job_id),
        ).get("progress") or {})

    def append_job_message(self, message, *, level="INFO", timestamp=None):
        if not message:
            return
        self.current_job_messages.append(self._format_job_log_line(message, level=level, timestamp=timestamp))
        self._apply_message_panel(self.engine_client.build_message_panel_state(
            mode="info",
            title="执行日志",
            logs=self.current_job_messages[-80:],
        ).get("panel") or {})
        if self.current_job_id and hasattr(self, "result_tabs"):
            self.result_tabs.setCurrentIndex(0)

    def _job_event_level(self, event_type):
        if event_type in {"node_error", "job_failed", "workflow_error"}:
            return "ERROR"
        if event_type in {"job_cancel_requested", "workflow_cancelled"}:
            return "WARN"
        return "INFO"

    def _message_with_elapsed(self, message, elapsed, *, label="耗时"):
        message = str(message or "").strip()
        if elapsed is None or "耗时" in message:
            return message
        try:
            seconds = float(elapsed)
        except (TypeError, ValueError):
            return message
        suffix = f"{label} {seconds:.2f} 秒"
        if not message:
            return suffix
        separator = "；" if message.endswith(("。", "！", "？")) else "，"
        return f"{message}{separator}{suffix}"

    def _format_job_log_line(self, message, *, level="INFO", timestamp=None):
        text = str(message or "")
        if text.startswith("[") and "] [" in text:
            return text
        level_text = str(level or "INFO").upper()
        return f"[{self._format_job_timestamp(timestamp)}] [{level_text}] {text}"

    def _format_job_timestamp(self, timestamp=None):
        try:
            if timestamp is None:
                dt = datetime.now()
            else:
                dt = datetime.fromtimestamp(float(timestamp))
        except Exception:
            dt = datetime.now()
        return dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

    def finish_workflow_job(self, status):
        self.job_timer.stop()
        self.set_workflow_running(False)
        if self.current_job_started_at and not self.current_job_has_workflow_elapsed:
            level = "ERROR" if status.get("status") == "failed" else "INFO"
            self.append_job_message(
                self._message_with_elapsed("工作流结束", time.perf_counter() - self.current_job_started_at, label="总耗时"),
                level=level,
            )
        final = self.engine_client.finalize_job_result(
            status,
            job_action=self.current_job_action,
            logs=self.current_job_messages,
            output_settings=self.current_output_settings(),
        )
        table = final.get("table") or {}
        headers = list(table.get("headers") or [])
        rows = [list(row) for row in (table.get("rows") or [])]
        view_state = final.get("view_state") or {}
        if status.get("status") == "failed":
            self._apply_message_panel(final.get("message_panel") or {})
            self.status_bar.showMessage(str(view_state.get("status_message") or "后台任务失败"))
        elif headers or rows:
            self.last_preview_headers = headers
            self.last_preview_rows = rows
            if self.current_job_action == "preview_plan":
                self.node_config_preview_cache = build_preview_context_cache(
                    plan=self.current_plan,
                    stop_index=self.current_job_stop_index,
                    headers=headers,
                    rows=rows,
                )
            self.update_table(headers, rows, title=str(view_state.get("table_title") or self.current_job_title or "执行结果"))
            self.current_table_kind = str(view_state.get("table_kind") or "preview")
            if hasattr(self, "result_tabs"):
                self.result_tabs.setCurrentIndex(0)
            if view_state.get("should_refresh_preview_sources"):
                self.refresh_preview_table_combo()
            success_panel = final.get("message_panel") or self.engine_client.build_message_panel_state(
                mode="success",
                title=self.current_job_title,
                body=f"{self.current_job_title}完成，无日志。",
                logs=final.get("logs") or [],
            ).get("panel") or {}
            success_panel = dict(success_panel)
            success_panel["switch_result_tab"] = False
            self._apply_message_panel(success_panel)
            self._apply_job_progress_state(self.engine_client.build_job_progress_state(
                current_job_id=self.current_job_id,
                title=self.current_job_title,
                final=final,
            ).get("progress") or {})
            self.status_bar.showMessage(str(view_state.get("status_message") or final.get("display_message") or f"{self.current_job_title}完成。"))
        else:
            self._apply_message_panel(self.engine_client.build_message_panel_state(
                mode="info",
                title="后台任务",
                body=status.get("message", "后台任务已结束。"),
                logs=self.current_job_messages,
            ).get("panel") or {})
            self.status_bar.showMessage(str(view_state.get("status_message") or status.get("message", "后台任务已结束。")))
        self.current_job_id = ""
        self.current_job_action = ""
        self.current_job_title = ""
        self.current_job_event_sequence = 0
        self.current_job_messages = []
        self.current_job_started_at = 0.0
        self.current_job_has_workflow_elapsed = False
        self.current_job_stop_index = None

    def set_workflow_running(self, running):
        self.refresh_action_states(is_running=bool(running))

    def refresh_action_states(self, is_running=None, selected_indexes=None):
        if is_running is None:
            is_running = bool(self.current_job_id)
        if selected_indexes is None:
            selected_indexes = self.selected_node_indexes()
        result = self.engine_client.describe_workflow_actions(
            plan=self.current_plan,
            selected_indexes=selected_indexes,
            is_running=bool(is_running),
        )
        actions = result.get("actions") or {}
        button_map = {
            "delete_nodes": self.node_action_buttons.get("删除"),
            "move_node_up": self.node_action_buttons.get("上移"),
            "move_node_down": self.node_action_buttons.get("下移"),
            "toggle_node_enabled": self.node_action_buttons.get("启用/禁用"),
            "duplicate_node": self.node_action_buttons.get("复制节点"),
            "clear_nodes": self.node_action_buttons.get("清空节点"),
            "preview_selected": self.node_action_buttons.get("预览到当前节点"),
            "preview_full": self.run_action_buttons.get("预览完整计划"),
            "execute_plan": self.run_action_buttons.get("执行计划"),
            "validate_plan": self.run_action_buttons.get("校验"),
            "cancel_job": self.cancel_job_button,
            "apply_node_config": self.apply_config_button,
            "add_node": self.add_node_button,
            "refresh_catalog": self.refresh_schema_button,
            "refresh_plugins": self.refresh_plugin_button,
        }
        for action_key, button in button_map.items():
            if button is None:
                continue
            button.setEnabled(bool((actions.get(action_key) or {}).get("enabled", False)))
        legacy_enabled = bool((actions.get("legacy_plugin_config") or {}).get("enabled", False))
        legacy_action_enabled = bool(
            (self.current_legacy_plugin_config_action or {}).get(
                "ui_enabled_default",
                bool(self.current_legacy_plugin_config_action),
            )
        )
        self.legacy_plugin_config_button.setEnabled(
            self.legacy_plugin_config_button.isVisible()
            and legacy_enabled
            and legacy_action_enabled
        )
        self._refresh_node_enabled_tool_button()

    def _apply_job_progress_state(self, progress):
        progress = progress or {}
        self.workflow_progress_label.setText(str(progress.get("workflow_label") or "等待执行"))
        self.workflow_progress.setValue(int(progress.get("workflow_value", 0) or 0))
        self.node_progress_label.setText(str(progress.get("node_label") or "节点进度"))
        self.node_progress.setValue(int(progress.get("node_value", 0) or 0))

    def show_input_table(self):
        self._show_preview_source({"type": "memory", "table_role": "input"})

    def show_preview_table(self):
        self._show_preview_source({"type": "memory", "table_role": "preview"})

    def show_log_text(self):
        if hasattr(self, "result_tabs"):
            self.result_tabs.setCurrentWidget(self.message_tabs.parentWidget())
        self.message_tabs.setCurrentWidget(self.log_text)
        self.log_text.setFocus()

    def refresh_preview_table_combo(self):
        panel_state = self.engine_client.build_preview_panel_state(
            current_source=self.preview_table_combo.currentData(),
            current_headers=self.current_headers,
            current_rows=self.current_rows,
            preview_headers=self.last_preview_headers,
            preview_rows=self.last_preview_rows,
            db_path=self.output_db_path_edit.text().strip(),
        )
        self.preview_source_records = list(panel_state.get("sources") or [])
        issues = panel_state.get("issues") or []
        if issues:
            self._apply_message_panel(self.engine_client.build_message_panel_state(mode="warning", title="预览来源", issues=issues).get("panel") or {})

        self.preview_table_combo.blockSignals(True)
        self.preview_table_combo.clear()
        restore_index = 0
        selected_key = str(panel_state.get("selected_key") or "")
        for index, item in enumerate(self.preview_source_records):
            label = item.get("label", "")
            source = item.get("source") or {}
            self.preview_table_combo.addItem(label, source)
            if self._table_source_key(source) == selected_key:
                restore_index = index
        self.preview_table_combo.setCurrentIndex(restore_index)
        self.preview_table_combo.blockSignals(False)

    def show_selected_preview_table(self):
        source = self.preview_table_combo.currentData() or {}
        self._show_preview_source(source)

    def _table_source_key(self, source):
        if not isinstance(source, dict):
            return ""
        return f"{source.get('type', '')}:{source.get('table_role', '')}:{source.get('table_name', '')}"

    def _show_preview_source(self, source, *, kind=None):
        try:
            loaded = self.engine_client.load_preview_source(
                source,
                current_headers=self.current_headers,
                current_rows=self.current_rows,
                preview_headers=self.last_preview_headers,
                preview_rows=self.last_preview_rows,
            )
        except Exception as exc:
            self._apply_message_panel(self.engine_client.build_message_panel_state(mode="error", title="读取预览来源失败", body=str(exc)).get("panel") or {})
            self.status_bar.showMessage("读取预览来源失败")
            return
        if not loaded.get("ok"):
            self._apply_message_panel(loaded.get("message_panel") or self.engine_client.build_message_panel_state(mode="warning", title="读取预览来源失败", issues=loaded.get("issues", [])).get("panel") or {})
            view_state = loaded.get("view_state") or {}
            self.status_bar.showMessage(str(view_state.get("status_message") or loaded.get("message", "读取预览来源失败")))
            return
        table = loaded.get("table") or {}
        headers = list(table.get("headers") or [])
        rows = [list(row) for row in (table.get("rows") or [])]
        view_state = loaded.get("view_state") or {}
        self.current_table_kind = str(kind or view_state.get("table_kind") or "preview")
        self.update_table(headers, rows, title=str(view_state.get("table_title") or loaded.get("title") or "表格预览"))
        self._apply_message_panel(loaded.get("message_panel") or self.engine_client.build_message_panel_state(mode="info", title="预览来源", body=loaded.get("message", "")).get("panel") or {})
        self.status_bar.showMessage(str(view_state.get("status_message") or loaded.get("message", "已切换表格。")))

    def _input_table_payload(self):
        return {
            "type": "table",
            "headers": list(self.current_headers),
            "rows": [list(row) for row in self.current_rows],
        }

    def _node_type_id_for_node(self, node):
        return str(node.get("node_type_id") or node.get("type") or "")

    def apply_output_settings_from_plan(self, plan):
        plan = plan or {}
        described = self.engine_client.describe_output_form(plan)
        self.output_mode_meta = dict(described.get("mode_meta") or self.output_mode_meta)
        self._apply_output_form_settings(described.get("settings") or {})
        self._apply_output_form_state()

    def current_output_settings(self):
        result = self.engine_client.build_output_settings(
            output_mode=self.output_mode_combo.currentText(),
            output_table=self.output_table_edit.text(),
            backup_before_overwrite=self.backup_checkbox.isChecked(),
            db_path=self.output_db_path_edit.text(),
            output_path=self.output_path_edit.text(),
        )
        return result.get("settings") or {}

    def _condition_matches(self, condition, values):
        if not condition:
            return True
        if not isinstance(condition, dict):
            return True
        field = condition.get("field")
        actual = values.get(field)
        if "equals" in condition:
            return str(actual) == str(condition.get("equals"))
        if "in" in condition:
            return any(str(actual) == str(item) for item in (condition.get("in") or []))
        return True

    def _format_issues(self, issues):
        issues = issues or []
        if not issues:
            return "无问题。"
        lines = []
        for issue in issues:
            severity = issue.get("severity", "")
            code = issue.get("code", "")
            path = issue.get("path", "")
            message = issue.get("message", "")
            lines.append(f"[{severity}] {code} {path}".strip())
            if message:
                lines.append(message)
        return "\n".join(lines)

    def _format_validation(self, validation):
        lines = [
            "OK: " + ("true" if validation.get("ok") else "false"),
            f"节点数: {validation.get('node_count', 0)}",
        ]
        issues = validation.get("issues", []) or []
        if not issues:
            lines.append("无校验问题。")
            return "\n".join(lines)
        lines.append("")
        for issue in issues:
            node_index = issue.get("node_index")
            code = issue.get("code", "")
            severity = issue.get("severity", "")
            node_type_id = issue.get("node_type_id", "")
            message = issue.get("message", "")
            lines.append(f"[{severity}] #{node_index} {code} {node_type_id}")
            lines.append(message)
        return "\n".join(lines)

    def _plan_status_text(self):
        return self.engine_client.plan_status_text(self.current_plan, current_plan_path=self.current_plan_path)

    def show_error(self, title, message):
        self.qt.QtWidgets.QMessageBox.critical(self.window, title, message)


def build_main_window(qt, parent=None, engine_client=None):
    controller = QtWorkflowMainWindow(qt, parent=parent, engine_client=engine_client)
    controller.window.qt_workflow_controller = controller
    return controller.window
