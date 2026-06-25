# -*- coding: utf-8 -*-
"""Qt input data source manager window."""

from __future__ import annotations

import copy

from ui_qt.table_model import make_table_model
from ui_qt.table_view_utils import configure_fast_table_view, item_view_enum


class DataSourceManagerWindow:
    """Small reusable manager for preparing a workflow input table."""

    def __init__(
        self,
        qt,
        *,
        engine_client,
        parent=None,
        initial_headers=None,
        initial_rows=None,
        initial_source=None,
        db_path="",
        on_apply=None,
        on_db_path_changed=None,
    ):
        self.qt = qt
        self.engine_client = engine_client
        self.on_apply = on_apply
        self.on_db_path_changed = on_db_path_changed
        self.current_source = copy.deepcopy(initial_source or {"type": "memory"})
        self.dirty = False
        self.search_matches = []
        self.search_index = -1
        self.search_navigation = {}
        self.save_mode_entries = []
        self.save_modes_description = {}
        self.service_description = self._describe_data_source_service()
        self.client_profiles = self._service_client_profiles()
        self.transport_hints = self._service_transport_hints()
        self.page_source = None
        self.page_offset = 0
        self.page_limit = self._transport_page_size_default(default=500)
        self.page_has_more = False
        self.current_table_is_partial = False
        self.current_table_handle = ""
        self.current_display_name = ""
        self.manager_layout = {}
        self.manager_ui_hints = {}
        self.manager_sections_by_id = {}
        self.manager_action_sections = {}
        self.action_widgets = {}
        self.section_widgets = {}

        self.window = qt.QtWidgets.QDialog(parent)
        self.window.setWindowTitle("输入数据源管理")
        self.window.resize(1120, 720)
        self._build_ui(db_path=db_path)
        self.set_table(initial_headers or [], initial_rows or [], source=self.current_source, dirty=False)
        self._refresh_manager_protocol_metadata()

    def show(self):
        self.window.show()
        self.window.raise_()
        self.window.activateWindow()

    def _build_ui(self, *, db_path=""):
        qt = self.qt
        layout = qt.QtWidgets.QVBoxLayout(self.window)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        toolbar = qt.QtWidgets.QHBoxLayout()
        self.clipboard_button = qt.QtWidgets.QPushButton("读取剪贴板")
        self.import_button = qt.QtWidgets.QPushButton("导入文件")
        self.clear_button = qt.QtWidgets.QPushButton("清空")
        self.promote_header_button = qt.QtWidgets.QPushButton("首行作字段名")
        self.edit_mode_checkbox = qt.QtWidgets.QCheckBox("修改模式")
        self.apply_input_button = qt.QtWidgets.QPushButton("设置为工作流输入")
        for button in [self.clipboard_button, self.import_button, self.clear_button, self.promote_header_button]:
            toolbar.addWidget(button)
        toolbar.addWidget(self.edit_mode_checkbox)
        toolbar.addStretch(1)
        toolbar.addWidget(self.apply_input_button)
        layout.addLayout(toolbar)

        db_row = qt.QtWidgets.QHBoxLayout()
        self.db_path_edit = qt.QtWidgets.QLineEdit(str(db_path or ""))
        self.db_path_edit.setPlaceholderText("SQLite 数据库路径")
        self.choose_db_button = qt.QtWidgets.QPushButton("选择")
        self.database_label = qt.QtWidgets.QLabel("数据库：")
        db_row.addWidget(self.database_label)
        db_row.addWidget(self.db_path_edit, 1)
        db_row.addWidget(self.choose_db_button)
        layout.addLayout(db_row)

        load_table_row = qt.QtWidgets.QHBoxLayout()
        self.refresh_tables_button = qt.QtWidgets.QPushButton("刷新表")
        self.table_combo = qt.QtWidgets.QComboBox()
        self.load_table_button = qt.QtWidgets.QPushButton("载入表")
        self.table_loader_label = qt.QtWidgets.QLabel("选择表：")
        load_table_row.addWidget(self.table_loader_label)
        load_table_row.addWidget(self.table_combo, 1)
        load_table_row.addWidget(self.refresh_tables_button)
        load_table_row.addWidget(self.load_table_button)
        layout.addLayout(load_table_row)

        page_row = qt.QtWidgets.QHBoxLayout()
        self.page_size_spin = qt.QtWidgets.QSpinBox()
        self.page_size_spin.setRange(1, self._transport_page_size_max(default=100000))
        self.page_size_spin.setValue(self.page_limit)
        self.page_size_spin.setSingleStep(100)
        self.prev_page_button = qt.QtWidgets.QPushButton("上一页")
        self.next_page_button = qt.QtWidgets.QPushButton("下一页")
        self.load_full_table_button = qt.QtWidgets.QPushButton("载入完整表")
        self.page_status_label = qt.QtWidgets.QLabel("分页预览：未载入")
        self.page_size_label = qt.QtWidgets.QLabel("每页：")
        page_row.addWidget(self.page_size_label)
        page_row.addWidget(self.page_size_spin)
        page_row.addWidget(self.prev_page_button)
        page_row.addWidget(self.next_page_button)
        page_row.addWidget(self.load_full_table_button)
        page_row.addWidget(self.page_status_label, 1)
        layout.addLayout(page_row)

        save_row = qt.QtWidgets.QHBoxLayout()
        self.save_table_name_edit = qt.QtWidgets.QLineEdit()
        self.save_mode_combo = qt.QtWidgets.QComboBox()
        self._populate_save_modes()
        self.save_button = qt.QtWidgets.QPushButton("保存到 SQLite")
        self.delete_table_button = qt.QtWidgets.QPushButton("删除当前表")
        self.save_table_name_label = qt.QtWidgets.QLabel("保存表名：")
        self.save_mode_label = qt.QtWidgets.QLabel("模式：")
        save_row.addWidget(self.save_table_name_label)
        save_row.addWidget(self.save_table_name_edit, 1)
        save_row.addWidget(self.save_mode_label)
        save_row.addWidget(self.save_mode_combo)
        save_row.addWidget(self.save_button)
        save_row.addWidget(self.delete_table_button)
        layout.addLayout(save_row)

        search_row = qt.QtWidgets.QHBoxLayout()
        self.search_edit = qt.QtWidgets.QLineEdit()
        self.search_edit.setPlaceholderText("搜索当前表格")
        self.search_button = qt.QtWidgets.QPushButton("搜索")
        self.prev_button = qt.QtWidgets.QPushButton("上一个")
        self.next_button = qt.QtWidgets.QPushButton("下一个")
        self.search_status_label = qt.QtWidgets.QLabel("")
        self.search_label = qt.QtWidgets.QLabel("搜索：")
        search_row.addWidget(self.search_label)
        search_row.addWidget(self.search_edit, 1)
        search_row.addWidget(self.search_button)
        search_row.addWidget(self.prev_button)
        search_row.addWidget(self.next_button)
        search_row.addWidget(self.search_status_label)
        layout.addLayout(search_row)

        self.table_view = qt.QtWidgets.QTableView()
        self.table_model = make_table_model([], [], qt=qt, parent=self.table_view)
        self.table_view.setModel(self.table_model)
        configure_fast_table_view(qt, self.table_view)
        layout.addWidget(self.table_view, 1)

        self.status_label = qt.QtWidgets.QLabel("等待载入数据。")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.clipboard_button.clicked.connect(lambda checked=False: self.load_clipboard())
        self.import_button.clicked.connect(lambda checked=False: self.import_file())
        self.clear_button.clicked.connect(lambda checked=False: self.clear_table())
        self.promote_header_button.clicked.connect(lambda checked=False: self.promote_first_row_to_headers())
        self.edit_mode_checkbox.stateChanged.connect(lambda *_args: self.apply_edit_mode())
        self.apply_input_button.clicked.connect(lambda checked=False: self.apply_to_workflow())
        self.choose_db_button.clicked.connect(lambda checked=False: self.choose_db_path())
        self.refresh_tables_button.clicked.connect(lambda checked=False: self.refresh_table_combo())
        self.load_table_button.clicked.connect(lambda checked=False: self.load_selected_table())
        self.prev_page_button.clicked.connect(lambda checked=False: self.goto_prev_page())
        self.next_page_button.clicked.connect(lambda checked=False: self.goto_next_page())
        self.load_full_table_button.clicked.connect(lambda checked=False: self.load_full_selected_table())
        self.page_size_spin.valueChanged.connect(lambda *_args: self.reload_current_page_size())
        self.db_path_edit.editingFinished.connect(lambda: self.refresh_table_combo(show_status=False))
        self.save_button.clicked.connect(lambda checked=False: self.save_current_table())
        self.delete_table_button.clicked.connect(lambda checked=False: self.delete_selected_table())
        self.search_button.clicked.connect(lambda checked=False: self.search_current_table(reset=True))
        self.search_edit.returnPressed.connect(lambda: self.search_current_table(reset=True))
        self.prev_button.clicked.connect(lambda checked=False: self.goto_search_match(-1))
        self.next_button.clicked.connect(lambda checked=False: self.goto_search_match(1))
        self.table_model.dataChanged.connect(lambda *_args: self.mark_dirty())
        self.window.finished.connect(lambda *_args: self._release_current_table_handle())
        self._register_protocol_widgets()
        self.apply_edit_mode()
        self.refresh_table_combo(show_status=False)

    def _register_protocol_widgets(self):
        self.action_widgets = {
            "load_clipboard": [self.clipboard_button],
            "import_file": [self.import_button],
            "clear_table": [self.clear_button],
            "promote_first_row": [self.promote_header_button],
            "apply_to_workflow": [self.apply_input_button],
            "list_tables": [self.refresh_tables_button],
            "load_table": [self.load_table_button],
            "create_table_handle": [self.load_table_button],
            "get_table_handle_page": [self.prev_page_button, self.next_page_button],
            "get_table_page": [self.load_full_table_button],
            "save_sqlite": [self.save_button],
            "delete_sqlite": [self.delete_table_button],
            "search_table": [self.search_edit, self.search_button],
            "build_table_search_navigation": [self.prev_button, self.next_button],
            "patch_cell": [self.edit_mode_checkbox, self.table_view],
        }
        self.section_widgets = {
            "toolbar": [
                self.clipboard_button,
                self.import_button,
                self.clear_button,
                self.promote_header_button,
                self.edit_mode_checkbox,
                self.apply_input_button,
            ],
            "database": [self.database_label, self.db_path_edit, self.choose_db_button, self.refresh_tables_button],
            "table_loader": [self.table_loader_label, self.table_combo, self.load_table_button],
            "paging": [
                self.page_size_label,
                self.page_size_spin,
                self.prev_page_button,
                self.next_page_button,
                self.load_full_table_button,
                self.page_status_label,
            ],
            "save": [
                self.save_table_name_label,
                self.save_table_name_edit,
                self.save_mode_label,
                self.save_mode_combo,
                self.save_button,
                self.delete_table_button,
            ],
            "search": [self.search_label, self.search_edit, self.search_button, self.prev_button, self.next_button, self.search_status_label],
            "table": [self.table_view],
            "status": [self.status_label],
        }

    def _refresh_manager_protocol_metadata(self, manager_state=None):
        state = manager_state if isinstance(manager_state, dict) else self._describe_data_source_manager_state()
        layout = state.get("layout") if isinstance(state.get("layout"), dict) else {}
        ui_hints = state.get("ui_hints") if isinstance(state.get("ui_hints"), dict) else {}
        service = state.get("service") if isinstance(state.get("service"), dict) else {}
        client_profiles = service.get("client_profiles") if isinstance(service.get("client_profiles"), dict) else self.client_profiles
        transport_hints = service.get("transport_hints") if isinstance(service.get("transport_hints"), dict) else self.transport_hints
        if not layout and not ui_hints:
            return
        self.manager_layout = copy.deepcopy(layout)
        self.manager_ui_hints = copy.deepcopy(ui_hints)
        self.client_profiles = copy.deepcopy(client_profiles if isinstance(client_profiles, dict) else {})
        self.transport_hints = copy.deepcopy(transport_hints if isinstance(transport_hints, dict) else {})
        self.manager_sections_by_id = {
            str(section.get("section_id") or ""): copy.deepcopy(section)
            for section in layout.get("sections") or []
            if isinstance(section, dict) and str(section.get("section_id") or "")
        }
        self.manager_action_sections = {}
        for section_id, section in self.manager_sections_by_id.items():
            for action_id in section.get("action_ids") or []:
                action_key = str(action_id or "")
                if action_key and action_key not in self.manager_action_sections:
                    self.manager_action_sections[action_key] = section_id
        self.window.setProperty("data_source_manager_layout_schema", str(layout.get("schema_version") or ""))
        self.window.setProperty("data_source_manager_ui_hints_schema", str(ui_hints.get("schema_version") or ""))
        self.window.setProperty("data_source_manager_default_section", str(layout.get("default_section_id") or ui_hints.get("default_focus") or ""))
        self.window.setProperty("data_source_manager_display_mode", str(ui_hints.get("display_mode") or ""))
        table_transfer = self._transport_table_transfer()
        self.window.setProperty("data_source_client_profiles_schema", str(self.client_profiles.get("schema_version") or ""))
        self.window.setProperty("data_source_transport_hints_schema", str(self.transport_hints.get("schema_version") or ""))
        self.window.setProperty("data_source_default_client_profile", str(self.client_profiles.get("default_profile") or ""))
        self.window.setProperty("data_source_table_transfer_action", str(table_transfer.get("preferred_action") or ""))
        self.window.setProperty("data_source_table_page_action", str(table_transfer.get("page_action") or ""))
        self.window.setProperty("data_source_table_release_action", str(table_transfer.get("release_action") or ""))
        self.window.setProperty("data_source_page_size_default", self._transport_page_size_default(default=self.page_limit))
        self.window.setProperty("data_source_page_size_max_hint", self._transport_page_size_max(default=self.page_size_spin.maximum() if hasattr(self, "page_size_spin") else 100000))
        if hasattr(self, "page_size_spin"):
            self.page_size_spin.setMaximum(self._transport_page_size_max(default=self.page_size_spin.maximum()))
        self._apply_manager_section_hints()
        self._apply_manager_action_hints()

    def _apply_manager_section_hints(self):
        section_hints = self.manager_ui_hints.get("section_hints") if isinstance(self.manager_ui_hints, dict) else {}
        if not isinstance(section_hints, dict):
            section_hints = {}
        for section_id, widgets in (self.section_widgets or {}).items():
            section = self.manager_sections_by_id.get(section_id) or {}
            hint = section_hints.get(section_id) if isinstance(section_hints.get(section_id), dict) else {}
            tooltip = self._section_tooltip(section_id, section, hint)
            for widget in widgets:
                if widget is None:
                    continue
                if hasattr(widget, "setProperty"):
                    widget.setProperty("data_source_section_id", section_id)
                    widget.setProperty("data_source_section_role", str(section.get("role") or ""))
                if tooltip and hasattr(widget, "setToolTip") and not self._widget_action_id(widget):
                    widget.setToolTip(tooltip)

    def _apply_manager_action_hints(self):
        for action_id, widgets in (self.action_widgets or {}).items():
            section_id = self.manager_action_sections.get(action_id, "")
            tooltip = self._action_tooltip(action_id, section_id)
            prominence = self._action_prominence(action_id)
            for widget in widgets:
                if widget is None:
                    continue
                if hasattr(widget, "setProperty"):
                    widget.setProperty("data_source_action_id", action_id)
                    widget.setProperty("data_source_section_id", section_id)
                    widget.setProperty("data_source_prominence", prominence)
                if tooltip and hasattr(widget, "setToolTip"):
                    widget.setToolTip(tooltip)

    def _widget_action_id(self, widget):
        if widget is None or not hasattr(widget, "property"):
            return ""
        return str(widget.property("data_source_action_id") or "")

    def _section_tooltip(self, section_id, section, hint):
        title = str(section.get("title") or section_id or "").strip()
        role = str(section.get("role") or "").strip()
        description = str(hint.get("description") or "").strip()
        warning = str(hint.get("warning") or "").strip()
        lines = []
        if title:
            lines.append(f"区域：{title}")
        if role:
            lines.append(f"角色：{role}")
        if description:
            lines.append(description)
        if warning:
            lines.append(f"警告：{warning}")
        return "\n".join(lines)

    def _action_tooltip(self, action_id, section_id):
        service = self.service_description if isinstance(self.service_description, dict) else {}
        action_schema = service.get("action_schema") if isinstance(service.get("action_schema"), dict) else {}
        actions = action_schema.get("actions") if isinstance(action_schema.get("actions"), dict) else {}
        action = actions.get(action_id) if isinstance(actions, dict) else {}
        if not isinstance(action, dict):
            table_actions = service.get("table_actions") if isinstance(service.get("table_actions"), dict) else {}
            data_actions = service.get("data_actions") if isinstance(service.get("data_actions"), dict) else {}
            action = table_actions.get(action_id) or data_actions.get(action_id) or {}
        section = self.manager_sections_by_id.get(section_id) or {}
        section_hints = self.manager_ui_hints.get("section_hints") if isinstance(self.manager_ui_hints, dict) else {}
        hint = section_hints.get(section_id) if isinstance(section_hints, dict) and isinstance(section_hints.get(section_id), dict) else {}
        lines = [f"协议动作：{action_id}"]
        section_title = str(section.get("title") or section_id or "").strip()
        if section_title:
            lines.append(f"区域：{section_title}")
        engine_action = str(action.get("engine_action") or "").strip()
        if engine_action:
            lines.append(f"服务动作：{engine_action}")
        prominence = self._action_prominence(action_id)
        if prominence:
            lines.append(f"显示优先级：{prominence}")
        result = str(action.get("result") or "").strip()
        if result:
            lines.append(f"结果：{result}")
        if action.get("requires_confirmation"):
            lines.append("需要确认")
        description = str(hint.get("description") or "").strip()
        warning = str(hint.get("warning") or "").strip()
        if description:
            lines.append(description)
        if warning:
            lines.append(f"警告：{warning}")
        return "\n".join(lines)

    def _action_prominence(self, action_id):
        hints = self.manager_ui_hints if isinstance(self.manager_ui_hints, dict) else {}
        prominence = hints.get("action_prominence") if isinstance(hints.get("action_prominence"), dict) else {}
        return str(prominence.get(action_id) or "normal")

    def current_table(self):
        headers, rows = self.table_model.table_data()
        return {"type": "table", "headers": headers, "rows": rows}

    def describe_state(self):
        manager_state = self._describe_data_source_manager_state()
        if manager_state:
            result = copy.deepcopy(manager_state)
            result["ok"] = True
            return result
        panel_state = self._describe_data_source_panel_state()
        if panel_state:
            result = copy.deepcopy(panel_state)
            result["ok"] = True
            return result
        table = self.current_table()
        try:
            actions = self.engine_client.describe_data_source_actions(
                table,
                source=self.current_source,
                dirty=self.dirty,
            )
        except Exception:
            actions = {"ok": False, "action_state": {}, "action_schema": {}}
        action_schema = actions.get("action_schema") if isinstance(actions.get("action_schema"), dict) else {}
        save_modes = self.save_modes_description if isinstance(self.save_modes_description, dict) else {}
        service = self.service_description if isinstance(self.service_description, dict) else {}
        return {
            "ok": True,
            "source": copy.deepcopy(self.current_source or {}),
            "dirty": bool(self.dirty),
            "partial": bool(self.current_table_is_partial),
            "shape": {
                "rows": len(table.get("rows") or []),
                "columns": len(table.get("headers") or []),
            },
            "action_state": copy.deepcopy(actions.get("action_state") or {}),
            "service": {
                "schema_version": str(service.get("schema_version") or ""),
                "protocol_family": str(service.get("protocol_family") or ""),
                "service_id": str(service.get("service_id") or ""),
                "capabilities": copy.deepcopy(service.get("capabilities") or {}),
                "action_ids": sorted(str(key) for key in (service.get("actions") or {}).keys()),
                "data_action_ids": sorted(str(key) for key in (service.get("data_actions") or {}).keys()),
                "table_action_ids": sorted(str(key) for key in (service.get("table_actions") or {}).keys()),
                "client_profiles": copy.deepcopy(service.get("client_profiles") or {}),
                "transport_hints": copy.deepcopy(service.get("transport_hints") or {}),
                "result_schemas": copy.deepcopy(service.get("result_schemas") or {}),
            },
            "action_schema": {
                "schema_version": str(action_schema.get("schema_version") or ""),
                "action_ids": sorted(str(key) for key in (action_schema.get("actions") or {}).keys()),
                "result_schemas": copy.deepcopy(action_schema.get("result_schemas") or {}),
            },
            "save_modes": {
                "schema_version": str(save_modes.get("schema_version") or ""),
                "mode_ids": [
                    str(item.get("id") or "")
                    for item in (save_modes.get("modes") or self.save_mode_entries)
                    if str(item.get("id") or "")
                ],
                "mode_field": copy.deepcopy(save_modes.get("mode_field") or {}),
            },
        }

    def _describe_data_source_manager_state(self, *, display_name=""):
        table_names = [
            str(self.table_combo.itemData(index) or self.table_combo.itemText(index) or "").strip()
            for index in range(self.table_combo.count())
            if str(self.table_combo.itemData(index) or self.table_combo.itemText(index) or "").strip()
        ]
        try:
            described = self.engine_client.build_data_source_manager_state(
                self.current_table(),
                source=self.current_source,
                dirty=self.dirty,
                display_name=str(display_name or self._current_status_title()),
                partial=self.current_table_is_partial,
                page_info={
                    "offset": self.page_offset,
                    "limit": self.page_limit,
                    "has_more": self.page_has_more,
                },
                search_navigation=self.search_navigation,
                db_path=self.db_path_edit.text().strip(),
                table_names=table_names,
                selected_table=self.table_combo.currentText().strip(),
            )
        except Exception:
            return {}
        if not described.get("ok") or not isinstance(described.get("manager_state"), dict):
            return {}
        return copy.deepcopy(described["manager_state"])

    def _describe_data_source_panel_state(self, *, display_name=""):
        try:
            panel = self.engine_client.build_data_source_panel_state(
                self.current_table(),
                source=self.current_source,
                dirty=self.dirty,
                display_name=str(display_name or self._current_status_title()),
                partial=self.current_table_is_partial,
                page_info={
                    "offset": self.page_offset,
                    "limit": self.page_limit,
                    "has_more": self.page_has_more,
                },
                search_navigation=self.search_navigation,
            )
        except Exception:
            return {}
        if not panel.get("ok") or not isinstance(panel.get("panel_state"), dict):
            return {}
        return copy.deepcopy(panel["panel_state"])

    def _describe_data_source_service(self):
        try:
            described = self.engine_client.describe_data_source_service()
        except Exception:
            return {}
        return copy.deepcopy(described if isinstance(described, dict) else {})

    def _service_client_profiles(self):
        service = self.service_description if isinstance(self.service_description, dict) else {}
        profiles = service.get("client_profiles") if isinstance(service.get("client_profiles"), dict) else {}
        return copy.deepcopy(profiles)

    def _service_transport_hints(self):
        service = self.service_description if isinstance(self.service_description, dict) else {}
        hints = service.get("transport_hints") if isinstance(service.get("transport_hints"), dict) else {}
        return copy.deepcopy(hints)

    def _transport_table_transfer(self):
        hints = self.transport_hints if isinstance(self.transport_hints, dict) else {}
        transfer = hints.get("table_transfer") if isinstance(hints.get("table_transfer"), dict) else {}
        return transfer

    def _transport_page_size_default(self, *, default=500):
        transfer = self._transport_table_transfer()
        return max(1, self._int_value(transfer.get("page_size_default"), default=default))

    def _transport_page_size_max(self, *, default=100000):
        transfer = self._transport_table_transfer()
        return max(1, self._int_value(transfer.get("page_size_max_hint"), default=default))

    def _has_table_action(self, action_id):
        service = self.service_description if isinstance(self.service_description, dict) else {}
        table_actions = service.get("table_actions") if isinstance(service.get("table_actions"), dict) else {}
        action = table_actions.get(action_id) if isinstance(table_actions, dict) else {}
        if not isinstance(action, dict):
            return False
        engine_action = str(action.get("engine_action") or action_id)
        return engine_action == action_id and callable(getattr(self.engine_client, action_id, None))

    def _release_current_table_handle(self):
        handle = str(getattr(self, "current_table_handle", "") or "").strip()
        if not handle:
            return
        self.current_table_handle = ""
        self._release_table_handle(handle)

    def _release_table_handle(self, handle):
        handle = str(handle or "").strip()
        if not handle:
            return
        try:
            self.engine_client.release_table_handle(handle)
        except Exception:
            pass

    def set_table(
        self,
        headers,
        rows,
        *,
        source=None,
        title="",
        dirty=False,
        page_info=None,
        partial=False,
        table_handle="",
        release_handle=True,
    ):
        table_handle = str(table_handle or "").strip()
        if release_handle and getattr(self, "current_table_handle", "") and self.current_table_handle != table_handle:
            self._release_current_table_handle()
        if table_handle:
            self.current_table_handle = table_handle
        self.current_source = copy.deepcopy(source or {"type": "memory"})
        self.dirty = bool(dirty)
        self._set_page_state(page_info=page_info, source=source, partial=partial)
        self.search_matches = []
        self.search_index = -1
        self.search_navigation = {}
        self.table_model.set_table(headers or [], rows or [])
        self.table_model.clear_search_highlight()
        table_name = self.current_source.get("table_name") or ""
        self.current_display_name = str(title or table_name or "当前表格")
        if table_name:
            self.table_combo.setCurrentText(str(table_name))
            self.save_table_name_edit.setText(str(table_name))
        self._refresh_page_controls()
        self._refresh_table_shape_status(title=title)

    def mark_dirty(self):
        if self.current_table_is_partial:
            return
        self.dirty = True
        self._refresh_data_action_controls()
        self._refresh_table_shape_status()

    def _refresh_table_shape_status(self, *, title=""):
        panel_state = self._describe_data_source_panel_state(display_name=title or self._current_status_title())
        view_state = panel_state.get("view_state") if isinstance(panel_state, dict) else {}
        status_text = str((view_state or {}).get("status_text") or "").strip()
        if status_text:
            self.current_display_name = str((view_state or {}).get("title") or title or self._current_status_title())
            self.status_label.setText(status_text)
            return
        table = self.current_table()
        headers = table.get("headers") or []
        rows = table.get("rows") or []
        dirty_note = "，未保存" if self.dirty else ""
        page_note = "，分页预览" if self.current_table_is_partial else ""
        prefix = str(title or "当前表格")
        self.status_label.setText(f"{prefix}：{len(rows)} 行 x {len(headers)} 列{page_note}{dirty_note}")

    def _current_status_title(self):
        if getattr(self, "current_display_name", ""):
            return str(self.current_display_name)
        if not hasattr(self, "status_label"):
            return ""
        return self.status_label.text().split("：", 1)[0]

    def _set_page_state(self, *, page_info=None, source=None, partial=False):
        self.current_table_is_partial = bool(partial)
        if self.current_table_is_partial:
            info = dict(page_info or {})
            self.page_source = copy.deepcopy(source or self.current_source or {})
            self.page_offset = self._int_value(info.get("offset"), default=0)
            self.page_limit = self._int_value(info.get("limit"), default=self._page_size_value())
            self.page_has_more = bool(info.get("has_more"))
        else:
            self.page_source = None
            self.page_offset = 0
            self.page_limit = self._page_size_value()
            self.page_has_more = False

    def _int_value(self, value, *, default=0):
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _page_size_value(self):
        if hasattr(self, "page_size_spin"):
            return max(1, self._int_value(self.page_size_spin.value(), default=self.page_limit))
        return max(1, self._int_value(self.page_limit, default=500))

    def _selected_sqlite_source(self):
        if self.current_table_is_partial and self.page_source:
            source = copy.deepcopy(self.page_source)
            if source.get("type") == "sqlite" and source.get("db_path") and source.get("table_name"):
                return source
        db_path = self.db_path_edit.text().strip()
        table_name = self.table_combo.currentText().strip()
        if db_path and table_name:
            return {"type": "sqlite", "db_path": db_path, "table_name": table_name}
        source = copy.deepcopy(self.current_source or {})
        if source.get("type") == "sqlite" and source.get("db_path") and source.get("table_name"):
            return source
        return None

    def _refresh_page_controls(self):
        if not hasattr(self, "page_status_label"):
            return
        source = self._selected_sqlite_source()
        panel_state = self._describe_data_source_panel_state()
        view_state = panel_state.get("view_state") if isinstance(panel_state, dict) else {}
        controls_state = self._describe_data_source_panel_state_for_source(source or self.current_source)
        controls_view = controls_state.get("view_state") if isinstance(controls_state, dict) else {}
        page_controls = (controls_view or {}).get("page_controls") if isinstance(controls_view, dict) else {}
        if isinstance(page_controls, dict) and page_controls:
            self.page_size_spin.setEnabled(bool(page_controls.get("page_size_enabled")))
            self.prev_page_button.setEnabled(bool(page_controls.get("prev_enabled")))
            self.next_page_button.setEnabled(bool(page_controls.get("next_enabled")))
            self.load_full_table_button.setEnabled(bool(page_controls.get("load_full_enabled")))
        else:
            can_page = bool(source)
            self.page_size_spin.setEnabled(can_page)
            self.prev_page_button.setEnabled(self.current_table_is_partial and self.page_offset > 0)
            self.next_page_button.setEnabled(self.current_table_is_partial and self.page_has_more)
            self.load_full_table_button.setEnabled(can_page)
        self._refresh_data_action_controls()
        if self.current_table_is_partial and self.edit_mode_checkbox.isChecked():
            self.edit_mode_checkbox.blockSignals(True)
            self.edit_mode_checkbox.setChecked(False)
            self.edit_mode_checkbox.blockSignals(False)
        self.apply_edit_mode()

        page_status_text = str((view_state or {}).get("page_status_text") or "").strip()
        if page_status_text:
            self.page_status_label.setText(page_status_text)
        elif self.current_table_is_partial:
            row_count = len(self.current_table().get("rows") or [])
            if row_count:
                start = self.page_offset + 1
                end = self.page_offset + row_count
                text = f"分页预览：第 {start}-{end} 行，每页 {self.page_limit}"
            else:
                text = f"分页预览：偏移 {self.page_offset} 无数据，每页 {self.page_limit}"
            text += "，还有下一页" if self.page_has_more else "，已到末页"
            self.page_status_label.setText(text)
        elif (self.current_source or {}).get("type") == "sqlite":
            self.page_status_label.setText("分页预览：当前为完整表")
        else:
            self.page_status_label.setText("分页预览：未载入")

    def _data_source_action_state(self, *, source=None):
        try:
            actions = self.engine_client.describe_data_source_actions(
                self.current_table(),
                source=source if source is not None else self.current_source,
                dirty=self.dirty,
            )
        except Exception:
            return {}
        return copy.deepcopy((actions.get("action_state") or {}).get("actions") or {})

    @staticmethod
    def _action_enabled(actions, action_id, default=False):
        action = actions.get(action_id) if isinstance(actions, dict) else {}
        if not isinstance(action, dict):
            return bool(default)
        return bool(action.get("enabled", default))

    def _refresh_data_action_controls(self):
        if not hasattr(self, "save_button"):
            return
        panel_state = self._describe_data_source_panel_state()
        if panel_state:
            action_enabled = (panel_state.get("view_state") or {}).get("action_enabled") or {}
            selected_state = self._describe_data_source_panel_state_for_source(self._selected_sqlite_source() or self.current_source)
            selected_enabled = (selected_state.get("view_state") or {}).get("action_enabled") if selected_state else {}
            self.clear_button.setEnabled(bool(action_enabled.get("clear_table")))
            self.promote_header_button.setEnabled(not self.current_table_is_partial and bool(action_enabled.get("promote_first_row")))
            self.search_button.setEnabled(bool(action_enabled.get("search_table")))
            self.save_button.setEnabled(not self.current_table_is_partial and bool(action_enabled.get("save_sqlite")))
            self.apply_input_button.setEnabled(bool(action_enabled.get("apply_to_workflow")))
            self.edit_mode_checkbox.setEnabled(not self.current_table_is_partial and bool(action_enabled.get("patch_cell")))
            self.delete_table_button.setEnabled(bool((selected_enabled or {}).get("delete_sqlite")))
            return
        actions = self._data_source_action_state()
        selected_actions = self._data_source_action_state(source=self._selected_sqlite_source() or self.current_source)
        editable_table = not self.current_table_is_partial
        self.clear_button.setEnabled(self._action_enabled(actions, "clear_table"))
        self.promote_header_button.setEnabled(editable_table and self._action_enabled(actions, "promote_first_row"))
        self.search_button.setEnabled(self._action_enabled(actions, "search_table"))
        self.save_button.setEnabled(editable_table and self._action_enabled(actions, "save_sqlite"))
        self.apply_input_button.setEnabled(self._action_enabled(actions, "apply_to_workflow"))
        self.edit_mode_checkbox.setEnabled(editable_table and self._action_enabled(actions, "patch_cell"))
        self.delete_table_button.setEnabled(self._action_enabled(selected_actions, "delete_sqlite"))

    def _describe_data_source_panel_state_for_source(self, source, *, display_name=""):
        try:
            panel = self.engine_client.build_data_source_panel_state(
                self.current_table(),
                source=source,
                dirty=self.dirty,
                display_name=str(display_name or self._current_status_title()),
                partial=self.current_table_is_partial,
                page_info={
                    "offset": self.page_offset,
                    "limit": self.page_limit,
                    "has_more": self.page_has_more,
                },
                search_navigation=self.search_navigation,
            )
        except Exception:
            return {}
        if not panel.get("ok") or not isinstance(panel.get("panel_state"), dict):
            return {}
        return copy.deepcopy(panel["panel_state"])

    def _populate_save_modes(self):
        try:
            described = self.engine_client.describe_table_save_modes()
        except Exception:
            described = {"ok": False, "modes": []}
        self.save_modes_description = copy.deepcopy(described if isinstance(described, dict) else {})
        self.save_mode_entries = list(described.get("modes") or [])
        if not self.save_mode_entries:
            self.save_mode_entries = [
                {"id": "replace", "label": "覆盖同名表"},
                {"id": "timestamp", "label": "自动加时间戳"},
                {"id": "fail", "label": "存在则报错"},
                {"id": "append", "label": "追加"},
            ]
        for item in self.save_mode_entries:
            mode_id = str(item.get("id") or "replace")
            label = str(item.get("label") or mode_id)
            self.save_mode_combo.addItem(label, mode_id)

    def _edit_trigger(self, name):
        group = getattr(self.qt.QtWidgets.QAbstractItemView, "EditTrigger", None)
        if group is not None and hasattr(group, name):
            return getattr(group, name)
        return getattr(self.qt.QtWidgets.QAbstractItemView, name)

    def apply_edit_mode(self):
        if self.current_table_is_partial:
            trigger = "NoEditTriggers"
        else:
            trigger = "AllEditTriggers" if self.edit_mode_checkbox.isChecked() else "NoEditTriggers"
        self.table_view.setEditTriggers(self._edit_trigger(trigger))

    def load_clipboard(self):
        text = self.qt.QtWidgets.QApplication.clipboard().text()
        result = self.engine_client.parse_clipboard_table(text, first_row_header=True)
        if not result.get("ok"):
            self._show_result_issues("读取剪贴板失败", result)
            return
        table = result.get("table") or {}
        self.set_table(
            table.get("headers") or [],
            table.get("rows") or [],
            source={"type": "clipboard"},
            title="剪贴板数据",
            dirty=True,
        )

    def import_file(self):
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
        except Exception as exc:
            self.status_label.setText(f"导入失败：{exc}")
            return
        table = imported.get("table") or {}
        self.set_table(
            table.get("headers") or [],
            table.get("rows") or [],
            source={"type": "file", "path": str(path)},
            title="导入文件",
            dirty=True,
        )

    def clear_table(self):
        self.set_table([], [], source={"type": "memory"}, title="已清空", dirty=False)

    def promote_first_row_to_headers(self):
        result = self.engine_client.promote_first_row_to_headers(self.current_table())
        if not result.get("ok"):
            self._show_result_issues("首行作字段名失败", result)
            return
        table = result.get("table") or {}
        self.set_table(
            table.get("headers") or [],
            table.get("rows") or [],
            source=self.current_source,
            title="已提升字段名",
            dirty=True,
        )

    def choose_db_path(self):
        path, _ = self.qt.QtWidgets.QFileDialog.getOpenFileName(
            self.window,
            "选择 SQLite 数据库",
            self.db_path_edit.text().strip(),
            "SQLite 数据库 (*.db *.sqlite);;所有文件 (*.*)",
        )
        if path:
            self.db_path_edit.setText(path)
            self.refresh_table_combo()

    def refresh_table_combo(self, *, show_status=True):
        db_path = self.db_path_edit.text().strip()
        if db_path and callable(self.on_db_path_changed):
            self.on_db_path_changed(db_path)
        try:
            listed = self.engine_client.list_tables(db_path=db_path or None)
        except Exception as exc:
            listed = {"ok": False, "tables": [], "issues": [{"message": str(exc)}]}
        table_names = []
        for item in listed.get("tables") or []:
            if isinstance(item, dict):
                name = str(item.get("name") or item.get("table_name") or item.get("table") or "").strip()
            else:
                name = str(item or "").strip()
            if name:
                table_names.append(name)
        current = self.table_combo.currentText()
        self.table_combo.blockSignals(True)
        self.table_combo.clear()
        self.table_combo.addItems(table_names)
        if current and current in table_names:
            self.table_combo.setCurrentText(current)
        self.table_combo.blockSignals(False)
        enabled = bool(db_path and table_names)
        self.load_table_button.setEnabled(enabled)
        self.delete_table_button.setEnabled(enabled)
        self._refresh_page_controls()
        if show_status:
            self.status_label.setText(f"已刷新数据表：{len(table_names)} 个" if db_path else "请先选择 SQLite 数据库。")

    def load_selected_table(self):
        self.load_table_page(0)

    def load_table_page(self, offset):
        db_path = self.db_path_edit.text().strip()
        table_name = self.table_combo.currentText().strip()
        if not db_path or not table_name:
            self.status_label.setText("请先选择数据库和表。")
            return
        limit = self._page_size_value()
        offset = max(0, self._int_value(offset, default=0))
        source = {
            "type": "sqlite",
            "db_path": db_path,
            "table_name": table_name,
        }
        loaded, table_handle = self._load_table_page_payload(source, limit=limit, offset=offset)
        if not loaded.get("ok"):
            self._show_result_issues("载入表失败", loaded)
            return
        table = loaded.get("table") or {}
        rows = [list(row) for row in (table.get("rows") or [])]
        visible_rows = rows[:limit]
        page_info = {
            "offset": offset,
            "limit": limit,
            "row_count": len(visible_rows),
            "has_more": len(rows) > limit,
        }
        is_partial = bool(offset > 0 or page_info["has_more"])
        self.set_table(
            table.get("headers") or [],
            visible_rows,
            source=source,
            title=f"SQLite：{table_name}",
            dirty=False,
            page_info=page_info,
            partial=is_partial,
            table_handle=table_handle if is_partial else "",
            release_handle=False if table_handle else True,
        )
        if table_handle and not is_partial:
            self.current_table_handle = ""
            self._release_table_handle(table_handle)

    def _load_table_page_payload(self, source, *, limit, offset):
        table_handle = str(getattr(self, "current_table_handle", "") or "").strip()
        if table_handle and self._has_table_action("get_table_handle_page"):
            loaded = self.engine_client.get_table_handle_page(table_handle, limit=limit + 1, offset=offset)
            if loaded.get("ok"):
                return loaded, table_handle
            self._release_current_table_handle()
        if self._has_table_action("create_table_handle"):
            self._release_current_table_handle()
            loaded = self.engine_client.create_table_handle(source=source, limit=limit + 1, offset=offset)
            if loaded.get("ok"):
                return loaded, str(loaded.get("handle") or "").strip()
        return self.engine_client.load_table(source, limit=limit + 1, offset=offset), ""

    def reload_current_page_size(self):
        if self.current_table_is_partial and self._selected_sqlite_source():
            self.load_table_page(0)
        else:
            self.page_limit = self._page_size_value()
            self._refresh_page_controls()

    def goto_prev_page(self):
        if not self.current_table_is_partial:
            return
        self.load_table_page(max(0, self.page_offset - self.page_limit))

    def goto_next_page(self):
        if not self.current_table_is_partial or not self.page_has_more:
            return
        self.load_table_page(self.page_offset + self.page_limit)

    def load_full_selected_table(self):
        source = self._selected_sqlite_source()
        if not source:
            self.status_label.setText("请先选择数据库和表。")
            return None
        loaded = self.engine_client.load_table(source)
        if not loaded.get("ok"):
            self._show_result_issues("载入完整表失败", loaded)
            return None
        table = loaded.get("table") or {}
        self.set_table(
            table.get("headers") or [],
            table.get("rows") or [],
            source=loaded.get("source") or source,
            title=f"SQLite完整表：{source.get('table_name') or ''}",
            dirty=False,
        )
        return loaded

    def save_current_table(self):
        if self.current_table_is_partial:
            self.status_label.setText("分页预览不支持直接保存，请先载入完整表。")
            return
        db_path = self.db_path_edit.text().strip()
        table_name = self.save_table_name_edit.text().strip() or self.table_combo.currentText().strip()
        if not db_path or not table_name:
            self.status_label.setText("保存前需要数据库路径和表名。")
            return
        result = self.engine_client.save_table(
            self.current_table(),
            db_path=db_path,
            table_name=table_name,
            mode=self._save_mode(),
        )
        if not result.get("ok"):
            self._show_result_issues("保存失败", result)
            return
        self.current_source = copy.deepcopy(result.get("source") or {"type": "sqlite", "db_path": db_path, "table_name": table_name})
        self.dirty = False
        self.refresh_table_combo(show_status=False)
        actual_name = result.get("table_name") or table_name
        self.table_combo.setCurrentText(str(actual_name))
        self.save_table_name_edit.setText(str(actual_name))
        self._refresh_table_shape_status(title=f"已保存：{actual_name}")

    def _save_mode(self):
        mode = ""
        if hasattr(self.save_mode_combo, "currentData"):
            mode = self.save_mode_combo.currentData()
        if not mode:
            mode = self.save_mode_combo.currentText()
        normalized = self.engine_client.normalize_table_save_mode(mode)
        if normalized.get("ok"):
            return normalized.get("mode") or "replace"
        return "replace"

    def delete_selected_table(self):
        db_path = self.db_path_edit.text().strip()
        table_name = self.table_combo.currentText().strip()
        if not db_path or not table_name:
            self.status_label.setText("删除前需要数据库路径和表名。")
            return
        buttons = self.qt.QtWidgets.QMessageBox.StandardButton.Yes | self.qt.QtWidgets.QMessageBox.StandardButton.No
        answer = self.qt.QtWidgets.QMessageBox.question(
            self.window,
            "删除当前表",
            f"即将删除 SQLite 表：{table_name}\n删除前会创建备份表，是否继续？",
            buttons,
            self.qt.QtWidgets.QMessageBox.StandardButton.No,
        )
        if answer != self.qt.QtWidgets.QMessageBox.StandardButton.Yes:
            self.status_label.setText("已取消删除。")
            return
        result = self.engine_client.delete_table(
            db_path=db_path,
            table_name=table_name,
            backup=True,
            confirmed=True,
        )
        if not result.get("ok"):
            self._show_result_issues("删除失败", result)
            return
        self.refresh_table_combo(show_status=False)
        if self.current_source.get("type") == "sqlite" and self.current_source.get("table_name") == table_name:
            self.clear_table()
        backup = result.get("backup_table") or ""
        self.status_label.setText(f"已删除表：{table_name}" + (f"，备份表：{backup}" if backup else ""))

    def search_current_table(self, *, reset=False):
        result = self.engine_client.search_table(
            self.current_table(),
            self.search_edit.text(),
            current_index=self.search_index,
            reset=reset,
        )
        self._apply_search_navigation(result.get("navigation") or {})

    def goto_search_match(self, offset):
        if not self.search_matches:
            self.search_current_table(reset=True)
            return
        result = self.engine_client.build_table_search_navigation(
            self.search_matches,
            current_index=self.search_index,
            offset=offset,
        )
        self._apply_search_navigation(result.get("navigation") or {})

    def _apply_search_navigation(self, navigation):
        self.search_navigation = dict(navigation or {})
        self.search_matches = list(self.search_navigation.get("matches") or [])
        try:
            self.search_index = int(self.search_navigation.get("current_index", -1))
        except (TypeError, ValueError):
            self.search_index = -1
        if not self.search_matches or not self.search_navigation.get("found"):
            self.search_index = -1
            self.table_model.clear_search_highlight()
            self.search_status_label.setText(self.search_navigation.get("status_text") or "未找到")
            return
        self._select_search_match(self.search_navigation)

    def _select_search_match(self, navigation=None):
        if not self.search_matches:
            return
        navigation = navigation or self.search_navigation or {}
        match = navigation.get("current_match") or self.search_matches[self.search_index]
        row = int(match.get("row", 0) or 0)
        column = int(match.get("column", 0) or 0)
        index = self.table_model.index(row, column)
        highlighted_rows = set(navigation.get("highlighted_rows") or [item.get("row") for item in self.search_matches])
        self.table_model.set_search_highlight(highlighted_rows, current_cell=(row, column))
        self.table_view.clearSelection()
        self.table_view.selectRow(row)
        self.table_view.setCurrentIndex(index)
        self.table_view.scrollTo(index, item_view_enum(self.qt, "ScrollHint", "PositionAtCenter"))
        self.search_status_label.setText(navigation.get("status_text") or f"{self.search_index + 1}/{len(self.search_matches)}")

    def apply_to_workflow(self):
        if not callable(self.on_apply):
            self.status_label.setText("当前窗口未绑定工作流输入回调。")
            return
        loaded_full = False
        if self.current_table_is_partial:
            loaded = self.load_full_selected_table()
            if not loaded:
                return
            loaded_full = True
        table = self.current_table()
        source = copy.deepcopy(self.current_source or {"type": "memory"})
        title = source.get("table_name") or source.get("path") or "输入表格"
        self.on_apply({
            "headers": list(table.get("headers") or []),
            "rows": [list(row) for row in (table.get("rows") or [])],
            "source": source,
            "table_title": f"输入表格：{title}",
            "status_message": "已从数据源管理窗口设置工作流输入。",
            "message_panel": self.engine_client.build_message_panel_state(
                mode="success",
                title="输入数据源",
                body="已将当前表格设置为工作流输入。",
            ).get("panel") or {},
        })
        if loaded_full:
            self.status_label.setText("已载入完整表并设置为工作流输入。")
        else:
            self.status_label.setText("已设置为工作流输入。")

    def _show_result_issues(self, title, result):
        issues = result.get("issues") or []
        message = "\n".join(str(item.get("message") or item) for item in issues) if issues else str(result.get("message") or title)
        self.status_label.setText(f"{title}：{message}")
