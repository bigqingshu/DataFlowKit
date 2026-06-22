# -*- coding: utf-8 -*-
"""Qt6 workflow shell shaped like the original workflow panel."""

from __future__ import annotations

import copy
from pathlib import Path

from ui_qt.config_form import NodeConfigForm
from ui_qt.engine_client import QtHeadlessEngineClient, SAMPLE_HEADERS, SAMPLE_PLAN, SAMPLE_ROWS
from ui_qt.node_ui_metadata import CATEGORY_ORDER, category_label, format_node_detail
from ui_qt.qt_compat import qt_enum
from engine.table_io import load_table_file
from ui_qt.table_model import make_table_model


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
        self.workflow_action_buttons = []

        self._build_ui()
        self.refresh_all()

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
        reload_button = qt.QtWidgets.QPushButton("重新载入示例输入")
        reload_button.clicked.connect(lambda checked=False: self.reload_sample_input())
        source_layout.addWidget(self.input_summary_label)
        source_layout.addWidget(reload_button)

        node_group = qt.QtWidgets.QGroupBox("2. 工作流节点")
        node_layout = qt.QtWidgets.QVBoxLayout(node_group)
        add_row = qt.QtWidgets.QHBoxLayout()
        self.node_type_combo = qt.QtWidgets.QComboBox()
        self.node_type_combo.setMinimumWidth(220)
        self.node_type_combo.currentIndexChanged.connect(lambda index: self.show_selected_node_type_detail())
        self.add_node_button = qt.QtWidgets.QPushButton("添加节点")
        self.add_node_button.clicked.connect(lambda checked=False: self.add_selected_node_type())
        self.refresh_schema_button = qt.QtWidgets.QPushButton("刷新节点")
        self.refresh_schema_button.clicked.connect(lambda checked=False: self.refresh_catalog())
        add_row.addWidget(self.node_type_combo, 1)
        add_row.addWidget(self.add_node_button)
        add_row.addWidget(self.refresh_schema_button)

        self.catalog_tree = qt.QtWidgets.QTreeWidget()
        self.catalog_tree.setHeaderHidden(True)
        self.catalog_tree.setMaximumHeight(190)
        self.catalog_tree.itemDoubleClicked.connect(lambda item, column: self.add_catalog_node(item))
        self.catalog_tree.itemSelectionChanged.connect(self.show_catalog_node_detail)

        self.node_list = qt.QtWidgets.QListWidget()
        self.node_list.setSelectionMode(qt.QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
        self.node_list.currentRowChanged.connect(self.show_node_config)

        node_buttons_a = qt.QtWidgets.QHBoxLayout()
        for text, callback in [
            ("删除", self.delete_selected_node),
            ("上移", self.move_selected_node_up),
            ("下移", self.move_selected_node_down),
            ("启用/禁用", self.toggle_selected_node_enabled),
        ]:
            button = qt.QtWidgets.QPushButton(text)
            button.clicked.connect(lambda checked=False, cb=callback: cb())
            node_buttons_a.addWidget(button)

        node_buttons_b = qt.QtWidgets.QHBoxLayout()
        for text, callback in [
            ("复制节点", self.copy_selected_node),
            ("清空节点", self.clear_nodes),
            ("预览到当前节点", self.preview_to_selected_node),
        ]:
            button = qt.QtWidgets.QPushButton(text)
            button.clicked.connect(lambda checked=False, cb=callback: cb())
            node_buttons_b.addWidget(button)

        node_layout.addLayout(add_row)
        node_layout.addWidget(self.catalog_tree, 0)
        node_layout.addWidget(self.node_list, 1)
        node_layout.addLayout(node_buttons_a)
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

        config_group = qt.QtWidgets.QGroupBox("4. 节点配置")
        config_layout = qt.QtWidgets.QVBoxLayout(config_group)
        self.config_header_label = qt.QtWidgets.QLabel("未选择节点")
        self.config_header_label.setWordWrap(True)
        self.config_form = NodeConfigForm(qt, headers=self.current_headers)
        self.apply_config_button = qt.QtWidgets.QPushButton("应用节点配置")
        self.apply_config_button.clicked.connect(lambda checked=False: self.apply_node_config())
        config_layout.addWidget(self.config_header_label)
        config_layout.addWidget(self.config_form.widget, 1)
        config_layout.addWidget(self.apply_config_button)

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
        self.cancel_job_button = qt.QtWidgets.QPushButton("取消任务")
        self.cancel_job_button.setEnabled(False)
        self.cancel_job_button.clicked.connect(lambda checked=False: self.cancel_current_job())
        action_row.addWidget(self.cancel_job_button)
        action_row.addStretch(1)

        progress_group = qt.QtWidgets.QGroupBox("执行进度")
        progress_layout = qt.QtWidgets.QVBoxLayout(progress_group)
        self.workflow_progress_label = qt.QtWidgets.QLabel("等待执行")
        self.workflow_progress = qt.QtWidgets.QProgressBar()
        self.workflow_progress.setRange(0, 100)
        self.node_progress_label = qt.QtWidgets.QLabel("节点进度")
        self.node_progress = qt.QtWidgets.QProgressBar()
        self.node_progress.setRange(0, 100)
        progress_layout.addWidget(self.workflow_progress_label)
        progress_layout.addWidget(self.workflow_progress)
        progress_layout.addWidget(self.node_progress_label)
        progress_layout.addWidget(self.node_progress)

        output_group = qt.QtWidgets.QGroupBox("5. 输出设置")
        output_layout = qt.QtWidgets.QHBoxLayout(output_group)
        self.output_mode_combo = qt.QtWidgets.QComboBox()
        self.output_mode_combo.addItems(["输出到主界面预览区", "保存为SQLite新表", "覆盖当前表", "导出为xlsx"])
        self.output_table_edit = qt.QtWidgets.QLineEdit("结果表")
        self.backup_checkbox = qt.QtWidgets.QCheckBox("覆盖前自动备份旧表")
        self.backup_checkbox.setChecked(True)
        output_layout.addWidget(qt.QtWidgets.QLabel("输出方式："))
        output_layout.addWidget(self.output_mode_combo)
        output_layout.addWidget(qt.QtWidgets.QLabel("输出表名："))
        output_layout.addWidget(self.output_table_edit, 1)
        output_layout.addWidget(self.backup_checkbox)

        preview_group = qt.QtWidgets.QGroupBox("6. 结果预览")
        preview_layout = qt.QtWidgets.QVBoxLayout(preview_group)
        preview_toolbar = qt.QtWidgets.QHBoxLayout()
        self.show_input_button = qt.QtWidgets.QPushButton("输入表")
        self.show_preview_button = qt.QtWidgets.QPushButton("结果表")
        self.show_input_button.clicked.connect(lambda checked=False: self.show_input_table())
        self.show_preview_button.clicked.connect(lambda checked=False: self.show_preview_table())
        self.preview_table_combo = qt.QtWidgets.QComboBox()
        self.preview_table_combo.addItems(["输入表格", "Headless 预览结果"])
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
        self.table_view.setAlternatingRowColors(True)
        self.table_view.setWordWrap(False)
        try:
            self.table_view.horizontalHeader().setStretchLastSection(True)
            self.table_view.setSortingEnabled(False)
        except Exception:
            pass

        self.issue_text = qt.QtWidgets.QPlainTextEdit()
        self.issue_text.setReadOnly(True)
        self.issue_text.setMaximumHeight(140)
        preview_layout.addLayout(preview_toolbar)
        preview_layout.addWidget(self.table_title)
        preview_layout.addWidget(self.table_view, 1)
        preview_layout.addWidget(self.issue_text)

        layout.addWidget(config_group, 2)
        layout.addLayout(action_row)
        layout.addWidget(progress_group)
        layout.addWidget(output_group)
        layout.addWidget(preview_group, 3)
        return panel

    def refresh_all(self):
        self.refresh_catalog()
        self.refresh_template_list(show_status=False)
        self.refresh_node_list()
        self.update_input_summary()
        self.update_table(self.current_headers, self.current_rows, title="输入表格")
        self.show_node_config(self.node_list.currentRow())
        self.status_bar.showMessage(self._plan_status_text())

    def refresh_catalog(self):
        schemas = self.engine_client.list_node_ui_schemas(include_unsupported=True, preview_headers=self.current_headers)
        self.node_schema_by_id = {item.get("node_type_id"): item for item in schemas}
        self.node_type_combo.blockSignals(True)
        self.node_type_combo.clear()
        for item in schemas:
            self.node_type_combo.addItem(item.get("display_name") or item.get("node_type_id", ""), item.get("node_type_id", ""))
        self.node_type_combo.blockSignals(False)

        self.catalog_tree.clear()
        grouped = {}
        for item in schemas:
            grouped.setdefault(item.get("category", "未知"), []).append(item)
        ordered_categories = [item for item in CATEGORY_ORDER if item in grouped]
        ordered_categories.extend(sorted(key for key in grouped.keys() if key not in ordered_categories))
        for category in ordered_categories:
            category_item = self.qt.QtWidgets.QTreeWidgetItem([category_label(category)])
            category_item.setData(0, self.user_role, "")
            self.catalog_tree.addTopLevelItem(category_item)
            for item in grouped.get(category, []):
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
                    category=item.get("category", ""),
                    supported_headless=item.get("capabilities", {}).get("headless_preview"),
                ))
                category_item.addChild(child)
            category_item.setExpanded(True)
        self.show_selected_node_type_detail()

    def refresh_template_list(self, show_status=True):
        self.plan_template_combo.clear()
        result = self.engine_client.list_plan_templates(self.plan_dir)
        templates = result.get("templates", [])
        if not templates:
            if show_status:
                self.status_bar.showMessage(f"模板刷新完成：0 个。")
            return
        for item in templates:
            self.plan_template_combo.addItem(item["name"], item["path"])
        if show_status:
            self.status_bar.showMessage(f"模板刷新完成：{self.plan_template_combo.count()} 个。")

    def update_input_summary(self):
        self.input_summary_label.setText(f"当前输入：{len(self.current_rows)} 行 x {len(self.current_headers)} 列")

    def refresh_node_list(self):
        selected = self.node_list.currentRow()
        self.node_list.clear()
        for index, node in enumerate(self.current_plan.get("nodes", []) or []):
            node_type_id = self._node_type_id_for_node(node)
            schema = self.node_schema_by_id.get(node_type_id, {})
            display = schema.get("display_name") or node.get("type") or node_type_id
            name = node.get("name") or display or "未命名节点"
            mark = "√" if node.get("enabled", True) else "×"
            item = self.qt.QtWidgets.QListWidgetItem(f"[{mark}] {index + 1}. {display}：{name}\n{node_type_id}")
            item.setData(self.user_role, index)
            self.node_list.addItem(item)
        if self.node_list.count():
            if selected < 0:
                selected = 0
            self.node_list.setCurrentRow(min(selected, self.node_list.count() - 1))
        else:
            self.config_form.set_node(None)
            self.config_header_label.setText("未选择节点")

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
        )
        if not result.get("ok"):
            self.issue_text.setPlainText(self._format_issues(result.get("issues", [])))
            self.status_bar.showMessage("计划编辑失败")
            return None
        self.current_plan = result.get("plan") or self.current_plan
        self.refresh_node_list()
        selected = result.get("selected_index")
        if selected is not None and self.node_list.count():
            self.node_list.setCurrentRow(max(0, min(int(selected), self.node_list.count() - 1)))
        if status_message:
            self.status_bar.showMessage(status_message)
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
        self.apply_plan_command({"type": "clear_nodes"}, status_message="节点已清空。")

    def show_node_config(self, row):
        nodes = self.current_plan.get("nodes", []) or []
        if row is None or row < 0 or row >= len(nodes):
            self.config_form.set_node(None)
            self.config_header_label.setText("未选择节点")
            return
        node = nodes[row]
        node_type_id = self._node_type_id_for_node(node)
        schema = self.node_schema_by_id.get(node_type_id, {})
        display = schema.get("display_name") or node.get("type") or node_type_id
        self.config_header_label.setText(f"节点类型：{display}    节点名称：{node.get('name', '')}")
        self.config_form.set_node(node, headers=self.current_headers, schema=schema)
        self.show_node_detail(node_type_id)

    def apply_node_config(self):
        index = self.selected_node_index()
        if index is None:
            return
        try:
            node = self.config_form.to_node()
            if not isinstance(node, dict):
                raise ValueError("节点配置必须是 JSON object。")
            if not node.get("node_type_id") and not node.get("type"):
                raise ValueError("节点必须包含 node_type_id 或 legacy type。")
            validation = self.engine_client.validate_config(node, preview_headers=self.current_headers)
            if not validation.get("ok"):
                self.issue_text.setPlainText(self._format_issues(validation.get("issues", [])))
                self.status_bar.showMessage("节点配置校验失败")
                return
            issues = validation.get("issues", []) or []
            if issues:
                self.issue_text.setPlainText(self._format_issues(issues))
            self.apply_plan_command({"type": "replace_node", "index": index, "node": node}, status_message="节点配置已应用。")
        except Exception as exc:
            self.show_error("配置无效", str(exc))

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

    def show_node_detail(self, node_type_id):
        schema = self.node_schema_by_id.get(node_type_id)
        if schema is None:
            try:
                schema = self.engine_client.get_node_ui_schema(node_type_id, preview_headers=self.current_headers)
            except Exception:
                schema = {}
        if not schema:
            return
        self.issue_text.setPlainText(format_node_detail(
            node_type_id,
            display_name=schema.get("display_name", ""),
            category=schema.get("category", ""),
            supported_headless=schema.get("capabilities", {}).get("headless_preview"),
        ))

    def update_table(self, headers, rows, title="表格预览"):
        self.preview_headers = list(headers or [])
        self.preview_rows = [list(row) for row in (rows or [])]
        self.table_model.set_table(self.preview_headers, self.preview_rows)
        self.table_title.setText(f"{title} · {len(self.preview_rows)} 行 x {len(self.preview_headers)} 列")

    def load_sample_plan(self):
        self.current_plan_path = None
        self.current_plan = copy.deepcopy(SAMPLE_PLAN)
        self.current_headers = list(SAMPLE_HEADERS)
        self.current_rows = [list(row) for row in SAMPLE_ROWS]
        self.last_preview_headers = []
        self.last_preview_rows = []
        self.refresh_all()
        self.issue_text.setPlainText("已载入 Qt6 示例计划。")

    def reload_sample_input(self):
        self.current_headers = list(SAMPLE_HEADERS)
        self.current_rows = [list(row) for row in SAMPLE_ROWS]
        self.current_plan["headers"] = list(self.current_headers)
        self.current_plan["rows"] = [list(row) for row in self.current_rows]
        self.update_input_summary()
        self.update_table(self.current_headers, self.current_rows, title="输入表格")
        self.status_bar.showMessage("已重新载入示例输入。")

    def import_table(self):
        path, _ = self.qt.QtWidgets.QFileDialog.getOpenFileName(
            self.window,
            "导入输入表格",
            "",
            "表格文件 (*.json *.csv *.tsv *.tab);;JSON 文件 (*.json);;CSV 文件 (*.csv);;TSV 文件 (*.tsv *.tab);;所有文件 (*.*)",
        )
        if not path:
            return
        try:
            headers, rows = load_table_file(path)
            self.current_headers = list(headers)
            self.current_rows = [list(row) for row in rows]
            self.current_plan["headers"] = list(self.current_headers)
            self.current_plan["rows"] = [list(row) for row in self.current_rows]
            self.config_form.set_headers(self.current_headers)
            self.refresh_catalog()
            self.update_input_summary()
            self.update_table(self.current_headers, self.current_rows, title="输入表格")
            self.show_node_config(self.node_list.currentRow())
            self.status_bar.showMessage(f"已导入输入表格：{path}")
        except Exception as exc:
            self.show_error("导入失败", str(exc))

    def open_plan(self):
        path, _ = self.qt.QtWidgets.QFileDialog.getOpenFileName(
            self.window,
            "打开 workflow_plan",
            "",
            "JSON 文件 (*.json);;所有文件 (*.*)",
        )
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
                self.issue_text.setPlainText(self._format_issues(loaded.get("issues", [])))
                self.status_bar.showMessage("打开失败：计划模板校验未通过")
                return
            data = loaded["plan"]
            self.current_plan_path = Path(loaded["path"])
            self.current_plan = data
            self.current_headers = list(data.get("headers", []))
            self.current_rows = [list(row) for row in data.get("rows", [])]
            self.last_preview_headers = []
            self.last_preview_rows = []
            self.refresh_all()
            warning = loaded.get("warning") or ""
            self.issue_text.setPlainText(warning or f"已打开计划：{path}")
        except Exception as exc:
            self.show_error("打开失败", str(exc))

    def save_plan(self):
        path = self.current_plan_path
        if path is None:
            selected, _ = self.qt.QtWidgets.QFileDialog.getSaveFileName(
                self.window,
                "保存 workflow_plan",
                str(self.plan_dir / "工作流计划.json"),
                "JSON 文件 (*.json);;所有文件 (*.*)",
            )
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
            )
            if not saved.get("ok"):
                self.issue_text.setPlainText(self._format_issues(saved.get("issues", [])))
                self.status_bar.showMessage("保存失败：计划模板校验未通过")
                return
            self.current_plan = saved.get("plan") or self.current_plan
            self.current_plan_path = Path(saved["path"])
            self.refresh_template_list(show_status=False)
            self.status_bar.showMessage(f"已保存：{path}")
        except Exception as exc:
            self.show_error("保存失败", str(exc))

    def validate_plan(self):
        validation = self.engine_client.validate_plan(self.current_plan)
        self.issue_text.setPlainText(self._format_validation(validation))
        self.status_bar.showMessage("校验通过" if validation.get("ok") else "校验发现问题")
        return validation

    def preview_to_selected_node(self):
        index = self.selected_node_index()
        if index is None:
            self.issue_text.setPlainText("请先选择一个节点。")
            return
        self.preview_plan(stop_index=index, title=f"预览到节点 {index + 1}")

    def preview_full_plan(self):
        self.preview_plan(stop_index=None, title="Headless 预览结果")

    def preview_plan(self, stop_index=None, title="Headless 预览结果"):
        input_table = self._input_table_payload()
        plan = copy.deepcopy(self.current_plan)
        validation = self.engine_client.validate_plan(plan)
        if not validation.get("ok"):
            self.issue_text.setPlainText(self._format_validation(validation))
            self.status_bar.showMessage("预览前校验失败")
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
        self.start_workflow_job(
            "run_plan",
            copy.deepcopy(self.current_plan),
            input_table=input_table,
            title="执行结果",
            execute_actions=False,
            status_prefix="执行",
        )

    def start_workflow_job(self, job_action, plan, *, input_table=None, title="", status_prefix="", **options):
        if self.current_job_id:
            self.issue_text.setPlainText("当前已有后台任务运行，请等待完成或先取消。")
            self.status_bar.showMessage("后台任务运行中")
            return
        try:
            started = self.engine_client.start_job(
                job_action,
                plan,
                input_table=input_table,
                **options,
            )
        except Exception as exc:
            self.issue_text.setPlainText(str(exc))
            self.status_bar.showMessage(f"{status_prefix or '任务'}启动失败")
            return

        self.current_job_id = str(started.get("job_id") or "")
        self.current_job_action = job_action
        self.current_job_title = title or "Headless 预览结果"
        self.current_job_event_sequence = 0
        self.current_job_messages = []
        self.workflow_progress.setValue(0)
        self.node_progress.setValue(0)
        self.workflow_progress_label.setText(f"{status_prefix or '任务'}已启动：{self.current_job_id}")
        self.node_progress_label.setText("节点进度：等待事件")
        self.issue_text.setPlainText(f"{status_prefix or '任务'}已启动。")
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
            self.issue_text.setPlainText(str(exc))
            self.status_bar.showMessage("取消任务失败")

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
            self.issue_text.setPlainText(str(exc))
            self.status_bar.showMessage("后台任务状态读取失败")
            self.current_job_id = ""
            return

        if status.get("done"):
            self.finish_workflow_job(status)

    def handle_job_event(self, event):
        event_type = event.get("type", "")
        message = event.get("message", "")
        if message:
            self.append_job_message(message)
        if event_type == "node_start":
            node_index = int(event.get("node_index", 0) or 0)
            node_total = max(1, int(event.get("node_total", 1) or 1))
            self.workflow_progress.setValue(int(node_index * 100 / node_total))
            self.node_progress.setValue(0)
            self.workflow_progress_label.setText(f"总进度：节点 {node_index + 1} / {node_total}")
            self.node_progress_label.setText(f"当前节点：{event.get('node_name', '')} - 开始")
        elif event_type == "node_progress":
            current = event.get("current")
            total = event.get("total")
            if total:
                self.node_progress.setValue(int(float(current or 0) * 100 / max(1.0, float(total))))
            self.node_progress_label.setText(message or "当前节点：处理中")
        elif event_type == "node_done":
            node_index = int(event.get("node_index", 0) or 0)
            node_total = max(1, int(event.get("node_total", 1) or 1))
            self.workflow_progress.setValue(int((node_index + 1) * 100 / node_total))
            self.node_progress.setValue(100)
            self.node_progress_label.setText(f"当前节点：{event.get('node_name', '')} - 完成")
        elif event_type == "job_cancel_requested":
            self.node_progress_label.setText("当前节点：正在取消")

    def append_job_message(self, message):
        if not message:
            return
        self.current_job_messages.append(str(message))
        self.issue_text.setPlainText("\n".join(self.current_job_messages[-80:]))

    def finish_workflow_job(self, status):
        self.job_timer.stop()
        self.set_workflow_running(False)
        result = status.get("result") or {}
        table = result.get("table") or {}
        headers = list(table.get("headers") or [])
        rows = [list(row) for row in (table.get("rows") or [])]
        if status.get("status") == "failed":
            error = status.get("error") or {}
            self.issue_text.setPlainText(error.get("message") or status.get("message") or "后台任务失败。")
            self.status_bar.showMessage("后台任务失败")
        elif headers or rows:
            self.last_preview_headers = headers
            self.last_preview_rows = rows
            self.update_table(headers, rows, title=self.current_job_title)
            self.current_table_kind = "preview"
            logs = result.get("logs") or self.current_job_messages
            self.issue_text.setPlainText("\n".join(logs) or f"{self.current_job_title}完成，无日志。")
            self.workflow_progress.setValue(100)
            self.node_progress.setValue(100)
            self.workflow_progress_label.setText(f"{self.current_job_title}完成：{len(rows)} 行 x {len(headers)} 列")
            self.node_progress_label.setText(f"执行步数：{result.get('steps', 0)}")
            self.status_bar.showMessage(f"{self.current_job_title}完成。")
        else:
            self.issue_text.setPlainText("\n".join(self.current_job_messages) or status.get("message", "后台任务已结束。"))
            self.status_bar.showMessage(status.get("message", "后台任务已结束。"))
        self.current_job_id = ""
        self.current_job_action = ""
        self.current_job_title = ""
        self.current_job_event_sequence = 0
        self.current_job_messages = []

    def set_workflow_running(self, running):
        for button in self.workflow_action_buttons:
            button.setEnabled(not running)
        self.cancel_job_button.setEnabled(bool(running))

    def show_input_table(self):
        self.current_table_kind = "input"
        self.update_table(self.current_headers, self.current_rows, title="输入表格")
        self.status_bar.showMessage("已切换到输入表格。")

    def show_preview_table(self):
        if not self.last_preview_headers and not self.last_preview_rows:
            self.issue_text.setPlainText("还没有预览结果。")
            self.status_bar.showMessage("暂无预览结果")
            return
        self.current_table_kind = "preview"
        self.update_table(self.last_preview_headers, self.last_preview_rows, title="Headless 预览结果")
        self.status_bar.showMessage("已切换到预览结果。")

    def show_log_text(self):
        self.issue_text.setFocus()

    def _input_table_payload(self):
        return {
            "type": "table",
            "headers": list(self.current_headers),
            "rows": [list(row) for row in self.current_rows],
        }

    def _node_type_id_for_node(self, node):
        return str(node.get("node_type_id") or node.get("type") or "")

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
        name = self.current_plan.get("plan_name", "未命名计划")
        path = str(self.current_plan_path) if self.current_plan_path else "未保存"
        return f"{name} · {path}"

    def show_error(self, title, message):
        self.qt.QtWidgets.QMessageBox.critical(self.window, title, message)


def build_main_window(qt, parent=None, engine_client=None):
    controller = QtWorkflowMainWindow(qt, parent=parent, engine_client=engine_client)
    controller.window.qt_workflow_controller = controller
    return controller.window
