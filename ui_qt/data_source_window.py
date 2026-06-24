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
        self.page_source = None
        self.page_offset = 0
        self.page_limit = 500
        self.page_has_more = False
        self.current_table_is_partial = False

        self.window = qt.QtWidgets.QDialog(parent)
        self.window.setWindowTitle("输入数据源管理")
        self.window.resize(1120, 720)
        self._build_ui(db_path=db_path)
        self.set_table(initial_headers or [], initial_rows or [], source=self.current_source, dirty=False)

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
        db_row.addWidget(qt.QtWidgets.QLabel("数据库："))
        db_row.addWidget(self.db_path_edit, 1)
        db_row.addWidget(self.choose_db_button)
        layout.addLayout(db_row)

        load_table_row = qt.QtWidgets.QHBoxLayout()
        self.refresh_tables_button = qt.QtWidgets.QPushButton("刷新表")
        self.table_combo = qt.QtWidgets.QComboBox()
        self.load_table_button = qt.QtWidgets.QPushButton("载入表")
        load_table_row.addWidget(qt.QtWidgets.QLabel("选择表："))
        load_table_row.addWidget(self.table_combo, 1)
        load_table_row.addWidget(self.refresh_tables_button)
        load_table_row.addWidget(self.load_table_button)
        layout.addLayout(load_table_row)

        page_row = qt.QtWidgets.QHBoxLayout()
        self.page_size_spin = qt.QtWidgets.QSpinBox()
        self.page_size_spin.setRange(1, 100000)
        self.page_size_spin.setValue(self.page_limit)
        self.page_size_spin.setSingleStep(100)
        self.prev_page_button = qt.QtWidgets.QPushButton("上一页")
        self.next_page_button = qt.QtWidgets.QPushButton("下一页")
        self.load_full_table_button = qt.QtWidgets.QPushButton("载入完整表")
        self.page_status_label = qt.QtWidgets.QLabel("分页预览：未载入")
        page_row.addWidget(qt.QtWidgets.QLabel("每页："))
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
        save_row.addWidget(qt.QtWidgets.QLabel("保存表名："))
        save_row.addWidget(self.save_table_name_edit, 1)
        save_row.addWidget(qt.QtWidgets.QLabel("模式："))
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
        search_row.addWidget(qt.QtWidgets.QLabel("搜索："))
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
        self.apply_edit_mode()
        self.refresh_table_combo(show_status=False)

    def current_table(self):
        headers, rows = self.table_model.table_data()
        return {"type": "table", "headers": headers, "rows": rows}

    def describe_state(self):
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

    def set_table(self, headers, rows, *, source=None, title="", dirty=False, page_info=None, partial=False):
        self.current_source = copy.deepcopy(source or {"type": "memory"})
        self.dirty = bool(dirty)
        self._set_page_state(page_info=page_info, source=source, partial=partial)
        self.search_matches = []
        self.search_index = -1
        self.search_navigation = {}
        self.table_model.set_table(headers or [], rows or [])
        self.table_model.clear_search_highlight()
        table_name = self.current_source.get("table_name") or ""
        if table_name:
            self.table_combo.setCurrentText(str(table_name))
            self.save_table_name_edit.setText(str(table_name))
        self._refresh_page_controls()
        self._refresh_table_shape_status(title=title)

    def mark_dirty(self):
        if self.current_table_is_partial:
            return
        self.dirty = True
        self._refresh_table_shape_status()

    def _refresh_table_shape_status(self, *, title=""):
        table = self.current_table()
        headers = table.get("headers") or []
        rows = table.get("rows") or []
        dirty_note = "，未保存" if self.dirty else ""
        page_note = "，分页预览" if self.current_table_is_partial else ""
        prefix = str(title or "当前表格")
        self.status_label.setText(f"{prefix}：{len(rows)} 行 x {len(headers)} 列{page_note}{dirty_note}")

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
        can_page = bool(source)
        self.page_size_spin.setEnabled(can_page)
        self.prev_page_button.setEnabled(self.current_table_is_partial and self.page_offset > 0)
        self.next_page_button.setEnabled(self.current_table_is_partial and self.page_has_more)
        self.load_full_table_button.setEnabled(can_page)
        self.promote_header_button.setEnabled(not self.current_table_is_partial)
        self.save_button.setEnabled(not self.current_table_is_partial)
        self.edit_mode_checkbox.setEnabled(not self.current_table_is_partial)
        if self.current_table_is_partial and self.edit_mode_checkbox.isChecked():
            self.edit_mode_checkbox.blockSignals(True)
            self.edit_mode_checkbox.setChecked(False)
            self.edit_mode_checkbox.blockSignals(False)
        self.apply_edit_mode()

        if self.current_table_is_partial:
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
        loaded = self.engine_client.load_table(source, limit=limit + 1, offset=offset)
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
            source=loaded.get("source") or source,
            title=f"SQLite：{table_name}",
            dirty=False,
            page_info=page_info,
            partial=is_partial,
        )

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
