# -*- coding: utf-8 -*-
"""Qt6 workflow shell shaped like the original workflow panel."""

from __future__ import annotations

import copy
from pathlib import Path

from ui_qt.config_form import NodeConfigForm
from ui_qt.engine_client import QtHeadlessEngineClient, SAMPLE_HEADERS, SAMPLE_PLAN, SAMPLE_ROWS
from ui_qt.node_ui_metadata import CATEGORY_ORDER, category_label, format_node_detail
from ui_qt.qt_compat import qt_enum
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
        self.node_action_buttons = {}
        self.run_action_buttons = {}
        self.output_mode_records = []
        self.output_mode_meta = {}
        self.preview_source_records = []

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
            self.run_action_buttons[text] = button
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
        output_layout = qt.QtWidgets.QFormLayout(output_group)
        output_layout.setContentsMargins(8, 8, 8, 8)
        output_layout.setSpacing(6)
        output_form = self.engine_client.describe_output_form()
        self.output_mode_meta = dict(output_form.get("mode_meta") or {})
        self.output_mode_records = list(self.output_mode_meta.values())
        output_fields = {item.get("key"): item for item in (output_form.get("form") or {}).get("fields", [])}

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

        self.output_form_fields = {
            "mode": {"label": qt.QtWidgets.QLabel(output_fields.get("mode", {}).get("label", "输出方式")), "editor": self.output_mode_combo, "schema": output_fields.get("mode", {})},
            "target": {"label": qt.QtWidgets.QLabel(output_fields.get("target", {}).get("label", "输出表名")), "editor": self.output_table_edit, "schema": output_fields.get("target", {})},
            "db_path": {"label": qt.QtWidgets.QLabel(output_fields.get("db_path", {}).get("label", "数据库路径")), "editor": self.output_db_path_edit, "schema": output_fields.get("db_path", {})},
            "path": {"label": qt.QtWidgets.QLabel(output_fields.get("path", {}).get("label", "输出文件")), "editor": self.output_path_edit, "schema": output_fields.get("path", {})},
            "backup_before_overwrite": {"label": qt.QtWidgets.QLabel(output_fields.get("backup_before_overwrite", {}).get("label", "覆盖前自动备份旧表")), "editor": self.backup_checkbox, "schema": output_fields.get("backup_before_overwrite", {})},
        }
        for key in ["mode", "target", "db_path", "path", "backup_before_overwrite"]:
            field = self.output_form_fields[key]
            output_layout.addRow(field["label"], field["editor"])

        self.output_mode_combo.currentTextChanged.connect(lambda *_args: self._apply_output_form_state())
        self.output_db_path_edit.editingFinished.connect(lambda: self.refresh_preview_table_combo())
        self._apply_output_form_settings(output_form.get("settings") or {})
        self._apply_output_form_state()

        preview_group = qt.QtWidgets.QGroupBox("6. 结果预览")
        preview_layout = qt.QtWidgets.QVBoxLayout(preview_group)
        preview_toolbar = qt.QtWidgets.QHBoxLayout()
        self.show_input_button = qt.QtWidgets.QPushButton("输入表")
        self.show_preview_button = qt.QtWidgets.QPushButton("结果表")
        self.show_input_button.clicked.connect(lambda checked=False: self.show_input_table())
        self.show_preview_button.clicked.connect(lambda checked=False: self.show_preview_table())
        self.preview_table_combo = qt.QtWidgets.QComboBox()
        self.preview_table_combo.addItems(["输入表格", "Headless 预览结果"])
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
        panel_state = self._panel_state()
        self.input_summary_label.setText(panel_state.get("input_summary", ""))

    def refresh_node_list(self):
        selected = self.node_list.currentRow()
        panel_state = self._panel_state(selected_index=selected if selected >= 0 else None)
        self.node_list.clear()
        for node_item in panel_state.get("node_items") or []:
            item = self.qt.QtWidgets.QListWidgetItem(node_item.get("summary_text", ""))
            item.setData(self.user_role, node_item.get("index"))
            self.node_list.addItem(item)
        if self.node_list.count():
            if selected < 0:
                selected = 0
            self.node_list.setCurrentRow(min(selected, self.node_list.count() - 1))
        else:
            self.config_form.set_node(None)
            self.config_header_label.setText("未选择节点")
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
        self.apply_plan_command({"type": "clear_nodes"}, status_message="节点已清空。")

    def show_node_config(self, row):
        panel_state = self._panel_state(selected_index=row)
        node = panel_state.get("selected_node")
        if row is None or row < 0 or node is None:
            self.config_form.set_node(None)
            self.config_header_label.setText("未选择节点")
            return
        node_type_id = self._node_type_id_for_node(node)
        schema = panel_state.get("selected_schema") or self.node_schema_by_id.get(node_type_id, {})
        display = schema.get("display_name") or node.get("type") or node_type_id
        self.config_header_label.setText(f"节点类型：{display}    节点名称：{node.get('name', '')}")
        self.config_form.set_node(node, headers=self.current_headers, schema=schema)
        self.show_node_detail(node_type_id)
        self.refresh_action_states()

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
                described = self.engine_client.describe_node_detail(node_type_id, preview_headers=self.current_headers)
                schema = described.get("schema") or {}
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

    def _apply_output_form_state(self):
        values = self.current_output_settings()
        for field in self.output_form_fields.values():
            schema = field.get("schema") or {}
            visible = self._condition_matches(schema.get("visible_when"), values)
            field.get("label").setVisible(visible)
            field.get("editor").setVisible(visible)

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
            imported = self.engine_client.import_table_file(path)
            table = imported.get("table") or {}
            self.current_headers = list(table.get("headers") or [])
            self.current_rows = [list(row) for row in (table.get("rows") or [])]
            self.current_plan["headers"] = list(self.current_headers)
            self.current_plan["rows"] = [list(row) for row in self.current_rows]
            self.config_form.set_headers(self.current_headers)
            self.refresh_catalog()
            self.update_input_summary()
            self.update_table(self.current_headers, self.current_rows, title="输入表格")
            self.show_node_config(self.node_list.currentRow())
            self.status_bar.showMessage(f"已导入输入表格：{imported.get('path') or path}")
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
            self.apply_output_settings_from_plan(data)
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
                db_path=self.output_db_path_edit.text(),
                output_path=self.output_path_edit.text(),
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
        combined = self.engine_client.validate_workflow_request(
            self.current_plan,
            execute_actions=True,
            output_settings=self.current_output_settings(),
        )
        validation = combined.get("validation") or {}
        jump_validation = combined.get("jump_validation") or {}
        access_precheck = combined.get("access_precheck") or {}
        text = self._format_validation(validation)
        jump_issues = jump_validation.get("issues", []) or []
        if jump_issues:
            text = text + "\n\n跳转校验：\n" + self._format_issues(jump_issues)
        access_issues = access_precheck.get("issues", []) or []
        if access_issues:
            text = (
                text
                + "\n\n权限预检：\n"
                + access_precheck.get("summary", "")
                + "\n"
                + self._format_issues(access_issues)
            )
        self.issue_text.setPlainText(text)
        if not combined.get("ok"):
            self.status_bar.showMessage("校验发现问题")
        elif jump_issues or access_issues:
            self.status_bar.showMessage("校验发现提示")
        else:
            self.status_bar.showMessage("校验通过")
        return combined

    def build_access_precheck(self, plan=None, *, execute_actions=True, stop_index=None, confirmed=False):
        result = self.engine_client.validate_workflow_request(
            plan or self.current_plan,
            execute_actions=execute_actions,
            stop_index=stop_index,
            output_settings=self.current_output_settings(),
            confirmed=confirmed,
        )
        return result.get("access_precheck") or {}

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
        validation = self.engine_client.validate_workflow_request(
            plan,
            execute_actions=False,
            stop_index=stop_index,
            output_settings=self.current_output_settings(),
        )
        if not (validation.get("validation") or {}).get("ok"):
            self.issue_text.setPlainText(self._format_validation(validation.get("validation") or {}))
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
            execute_actions=True,
            output_settings=self.current_output_settings(),
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
        self._apply_job_progress_state(self.engine_client.build_job_progress_state(
            current_job_id=self.current_job_id,
            title=self.current_job_title,
            running=True,
        ).get("progress") or {})
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

    def append_job_message(self, message):
        if not message:
            return
        self.current_job_messages.append(str(message))
        self.issue_text.setPlainText("\n".join(self.current_job_messages[-80:]))

    def finish_workflow_job(self, status):
        self.job_timer.stop()
        self.set_workflow_running(False)
        final = self.engine_client.finalize_job_result(
            status,
            job_action=self.current_job_action,
            logs=self.current_job_messages,
            output_settings=self.current_output_settings(),
        )
        table = final.get("table") or {}
        headers = list(table.get("headers") or [])
        rows = [list(row) for row in (table.get("rows") or [])]
        if status.get("status") == "failed":
            self.issue_text.setPlainText(final.get("display_message") or "后台任务失败。")
            self.status_bar.showMessage("后台任务失败")
        elif headers or rows:
            logs = final.get("logs") or []
            final_status_message = final.get("display_message") or f"{self.current_job_title}完成。"
            self.last_preview_headers = headers
            self.last_preview_rows = rows
            title = self.current_job_title
            if self.current_job_action == "run_plan" and not (final.get("output") or {}).get("ok", True):
                title = "执行结果（输出未落地）"
            self.update_table(headers, rows, title=title)
            self.current_table_kind = "preview"
            self.refresh_preview_table_combo()
            output = final.get("output") or {}
            if output:
                if output.get("ok"):
                    self.issue_text.setPlainText("\n".join(output.get("logs") or logs) or output.get("message", "输出完成。"))
                else:
                    issue_text = self._format_issues(output.get("issues", []))
                    if logs:
                        issue_text = issue_text + "\n\n执行日志：\n" + "\n".join(logs)
                    self.issue_text.setPlainText(issue_text)
            else:
                self.issue_text.setPlainText("\n".join(logs) or f"{self.current_job_title}完成，无日志。")
            self._apply_job_progress_state(self.engine_client.build_job_progress_state(
                current_job_id=self.current_job_id,
                title=self.current_job_title,
                final=final,
            ).get("progress") or {})
            self.status_bar.showMessage(final_status_message)
        else:
            self.issue_text.setPlainText("\n".join(self.current_job_messages) or status.get("message", "后台任务已结束。"))
            self.status_bar.showMessage(status.get("message", "后台任务已结束。"))
        self.current_job_id = ""
        self.current_job_action = ""
        self.current_job_title = ""
        self.current_job_event_sequence = 0
        self.current_job_messages = []

    def set_workflow_running(self, running):
        self.refresh_action_states(is_running=bool(running))

    def refresh_action_states(self, is_running=None):
        if is_running is None:
            is_running = bool(self.current_job_id)
        result = self.engine_client.describe_workflow_actions(
            plan=self.current_plan,
            selected_indexes=self.selected_node_indexes(),
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
        }
        for action_key, button in button_map.items():
            if button is None:
                continue
            button.setEnabled(bool((actions.get(action_key) or {}).get("enabled", False)))

    def _apply_job_progress_state(self, progress):
        progress = progress or {}
        self.workflow_progress_label.setText(str(progress.get("workflow_label") or "等待执行"))
        self.workflow_progress.setValue(int(progress.get("workflow_value", 0) or 0))
        self.node_progress_label.setText(str(progress.get("node_label") or "节点进度"))
        self.node_progress.setValue(int(progress.get("node_value", 0) or 0))

    def show_input_table(self):
        self._show_preview_source({"type": "memory", "table_role": "input"}, kind="input")

    def show_preview_table(self):
        self._show_preview_source({"type": "memory", "table_role": "preview"}, kind="preview")

    def show_log_text(self):
        self.issue_text.setFocus()

    def refresh_preview_table_combo(self):
        current_key = self._table_source_key(self.preview_table_combo.currentData())
        result = self.engine_client.list_preview_sources(
            current_headers=self.current_headers,
            current_rows=self.current_rows,
            preview_headers=self.last_preview_headers,
            preview_rows=self.last_preview_rows,
            db_path=self.output_db_path_edit.text().strip(),
        )
        self.preview_source_records = list(result.get("sources") or [])
        issues = result.get("issues") or []
        if issues:
            self.issue_text.setPlainText(self._format_issues(issues))

        self.preview_table_combo.blockSignals(True)
        self.preview_table_combo.clear()
        restore_index = 0
        for index, item in enumerate(self.preview_source_records):
            label = item.get("label", "")
            source = item.get("source") or {}
            self.preview_table_combo.addItem(label, source)
            if self._table_source_key(source) == current_key:
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
            self.issue_text.setPlainText(str(exc))
            self.status_bar.showMessage("读取预览来源失败")
            return
        if not loaded.get("ok"):
            self.issue_text.setPlainText(self._format_issues(loaded.get("issues", [])))
            self.status_bar.showMessage(loaded.get("message", "读取预览来源失败"))
            return
        table = loaded.get("table") or {}
        headers = list(table.get("headers") or [])
        rows = [list(row) for row in (table.get("rows") or [])]
        resolved_source = loaded.get("source") or source or {}
        source_type = resolved_source.get("type")
        source_role = resolved_source.get("table_role")
        if kind:
            self.current_table_kind = kind
        elif source_type == "memory" and source_role == "input":
            self.current_table_kind = "input"
        elif source_type == "memory" and source_role == "preview":
            self.current_table_kind = "preview"
        elif source_type == "sqlite":
            self.current_table_kind = "sqlite"
        else:
            self.current_table_kind = "preview"
        self.update_table(headers, rows, title=loaded.get("title") or "表格预览")
        self.issue_text.setPlainText(loaded.get("message", ""))
        self.status_bar.showMessage(loaded.get("message", "已切换表格。"))

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
