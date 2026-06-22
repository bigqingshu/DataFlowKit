# -*- coding: utf-8 -*-
"""Dynamic node configuration form for the Qt workflow shell."""

from __future__ import annotations

import copy
import json

from ui_qt.node_ui_metadata import (
    choices_for_field,
    config_layout_for_node,
    config_field_label,
    field_help_text,
    is_long_text_field,
    node_field_label,
)


def value_kind(value):
    """Return the editor kind for a config value."""

    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int) and not isinstance(value, bool):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, (list, dict)):
        return "json"
    return "text"


def format_form_value(value):
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False, indent=2)
    if value is None:
        return ""
    return str(value)


def coerce_form_value(kind, text, field_name=""):
    if kind == "int":
        return int(str(text).strip() or "0")
    if kind == "float":
        return float(str(text).strip() or "0")
    if kind == "json":
        raw = str(text).strip()
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            name = field_name or "JSON 字段"
            raise ValueError(f"{name} 不是有效 JSON：{exc}") from exc
    return "" if text is None else str(text)


def coerce_multi_select_value(value):
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if value in (None, ""):
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return [str(value)]


def format_multi_select_summary(value):
    items = coerce_multi_select_value(value)
    if not items:
        return "未选择"
    return "、".join(items)


def structured_item_default(columns):
    item = {}
    for column in columns or []:
        if not isinstance(column, dict):
            continue
        key = str(column.get("key") or "").strip()
        if not key:
            continue
        item[key] = copy.deepcopy(column.get("default", ""))
    return item


class NodeConfigForm:
    """Build editable Qt widgets for a workflow node dict."""

    def __init__(self, qt, parent=None, headers=None, action_handler=None):
        self.qt = qt
        self.headers = list(headers or [])
        self.action_handler = action_handler
        self.widget = qt.QtWidgets.QWidget(parent)
        self.root_layout = qt.QtWidgets.QVBoxLayout(self.widget)
        self.root_layout.setContentsMargins(0, 0, 0, 0)
        self.root_layout.setSpacing(8)
        self.scroll_area = qt.QtWidgets.QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.root_layout.addWidget(self.scroll_area)
        self.node = None
        self.schema = {}
        self.node_fields = {}
        self.config_fields = {}
        self.validation_issues = []
        self.set_node(None)

    def set_headers(self, headers):
        self.headers = list(headers or [])
        self._refresh_dynamic_options()

    def set_validation_issues(self, issues=None):
        self.validation_issues = list(issues or [])
        self._apply_validation_state()

    def describe_state(self):
        return {
            "ok": True,
            "fields": {
                key: {
                    "kind": field.get("kind"),
                    "visible": bool(field.get("editor").isVisible()) if field.get("editor") is not None else False,
                    "enabled": bool(field.get("editor").isEnabled()) if field.get("editor") is not None else False,
                    "issues": list(field.get("issues") or []),
                    "action": copy.deepcopy((field.get("schema") or {}).get("action") or {}),
                    "action_visible": bool(field.get("action_button").isVisible()) if field.get("action_button") is not None else False,
                    "action_enabled": bool(field.get("action_button").isEnabled()) if field.get("action_button") is not None else False,
                }
                for key, field in self.config_fields.items()
            },
            "issues": list(self.validation_issues or []),
        }

    def set_node(self, node, headers=None, schema=None):
        if headers is not None:
            self.set_headers(headers)
        self.node = copy.deepcopy(node) if isinstance(node, dict) else None
        self.schema = copy.deepcopy(schema) if isinstance(schema, dict) else {}
        self.node_fields = {}
        self.config_fields = {}
        self.validation_issues = []

        content = self.qt.QtWidgets.QWidget()
        outer = self.qt.QtWidgets.QVBoxLayout(content)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        if self.node is None:
            label = self.qt.QtWidgets.QLabel("")
            outer.addWidget(label)
            outer.addStretch(1)
            self.scroll_area.setWidget(content)
            return

        outer.addWidget(self._build_node_group())
        for group in self._build_config_groups():
            outer.addWidget(group)
        self._apply_dynamic_state()
        self._apply_validation_state()
        outer.addStretch(1)
        self.scroll_area.setWidget(content)

    def to_node(self):
        if self.node is None:
            return None

        node = copy.deepcopy(self.node)
        node["name"] = self.node_fields["name"].text()
        node["enabled"] = bool(self.node_fields["enabled"].isChecked())
        node["node_version"] = self.node_fields["node_version"].text().strip() or "1.0.0"

        config = {}
        for key, field in self.config_fields.items():
            kind = field["kind"]
            editor = field["editor"]
            if kind == "bool":
                config[key] = bool(editor.isChecked())
            elif kind == "field_multi_select":
                config[key] = list(getattr(editor, "multi_select_value", []))
            elif kind == "choice":
                config[key] = str(editor.currentText())
            elif kind == "structured_list":
                config[key] = self._structured_list_value(field)
            elif kind == "long_text":
                config[key] = str(editor.toPlainText())
            elif kind == "json":
                config[key] = coerce_form_value(kind, editor.toPlainText(), key)
            else:
                config[key] = coerce_form_value(kind, editor.text(), key)
        node["config"] = config
        return node

    def _build_node_group(self):
        group = self.qt.QtWidgets.QGroupBox("节点")
        form = self.qt.QtWidgets.QFormLayout(group)
        form.setContentsMargins(8, 8, 8, 8)
        form.setSpacing(6)

        node_type_id = self._line(self.node.get("node_type_id") or self.node.get("type", ""), read_only=True)
        node_id = self._line(self.node.get("node_id", ""), read_only=True)
        name = self._line(self.node.get("name", "") or self.node.get("type", "") or self.node.get("node_type_id", ""))
        enabled = self.qt.QtWidgets.QCheckBox()
        enabled.setChecked(bool(self.node.get("enabled", True)))
        node_version = self._line(self.node.get("node_version", "1.0.0"))

        self.node_fields = {
            "node_type_id": node_type_id,
            "node_id": node_id,
            "name": name,
            "enabled": enabled,
            "node_version": node_version,
        }

        form.addRow(node_field_label("node_type_id"), node_type_id)
        form.addRow(node_field_label("node_id"), node_id)
        form.addRow(node_field_label("name"), name)
        form.addRow(node_field_label("enabled"), enabled)
        form.addRow(node_field_label("node_version"), node_version)
        return group

    def _build_config_groups(self):
        config = self.node.get("config", {}) or {}
        if not isinstance(config, dict):
            config = {}
        if not config:
            group = self.qt.QtWidgets.QGroupBox("参数")
            form = self._form_layout(group)
            form.addRow("", self.qt.QtWidgets.QLabel(""))
            return [group]

        schema_groups = self._build_schema_config_groups(config)
        if schema_groups is not None:
            return schema_groups

        groups = []
        used = set()
        for spec in config_layout_for_node(self.node.get("node_type_id", "")):
            fields = [key for key in spec.get("fields", []) if key in config]
            if not fields:
                continue
            groups.append(self._build_config_group(spec.get("title", "参数"), config, fields))
            used.update(fields)

        remaining = [key for key in config.keys() if key not in used]
        if remaining:
            groups.append(self._build_config_group("其他参数", config, remaining))
        return groups

    def _build_schema_config_groups(self, config):
        form_schema = self.schema.get("form", {}) if isinstance(self.schema, dict) else {}
        schema_groups = form_schema.get("groups", []) if isinstance(form_schema, dict) else []
        if not isinstance(schema_groups, list) or not schema_groups:
            return None

        groups = []
        used = set()
        for group_spec in schema_groups:
            if not isinstance(group_spec, dict):
                continue
            field_specs = []
            for field_spec in group_spec.get("fields", []):
                if not isinstance(field_spec, dict):
                    continue
                key = field_spec.get("key")
                if key in config:
                    field_specs.append(field_spec)
                    used.add(key)
            if field_specs:
                groups.append(self._build_config_group(group_spec.get("title", "参数"), config, field_specs))

        remaining = [key for key in config.keys() if key not in used]
        if remaining:
            groups.append(self._build_config_group("其他参数", config, remaining))
        return groups

    def _build_config_group(self, title, config, fields):
        group = self.qt.QtWidgets.QGroupBox(title or "参数")
        form = self._form_layout(group)
        for item in fields:
            field_schema = item if isinstance(item, dict) else {}
            key = field_schema.get("key") if field_schema else item
            if key not in config:
                continue
            value = config[key]
            editor = self._build_config_editor(key, value, field_schema=field_schema)
            label = self.qt.QtWidgets.QLabel(field_schema.get("label") or config_field_label(key))
            form.addRow(label, editor)
            self.config_fields[key]["label"] = label
        return group

    def _build_config_editor(self, key, value, field_schema=None):
        field_schema = dict(field_schema or {})
        field_type = field_schema.get("type", "")
        choices = list(field_schema.get("choices") or choices_for_field(key, headers=self.headers))
        if field_type == "field_multi_select":
            kind = "field_multi_select"
        elif field_type in {"select", "field_select", "table_select"} or choices:
            kind = "choice"
        elif field_type == "structured_list":
            kind = "structured_list"
        elif field_type == "textarea" or is_long_text_field(key):
            kind = "long_text"
        elif field_type == "bool":
            kind = "bool"
        elif field_type == "json":
            kind = "json"
        elif field_type == "number":
            kind = value_kind(value) if value_kind(value) in {"int", "float"} else "text"
        else:
            kind = value_kind(value)
        self.config_fields[key] = {
            "kind": kind,
            "editor": None,
            "editor_container": None,
            "schema": field_schema,
            "visible_when": field_schema.get("visible_when"),
            "enabled_when": field_schema.get("enabled_when"),
            "depends_on": list(field_schema.get("depends_on") or []),
            "issues": [],
            "action_button": None,
        }
        editor = self._editor_for_field(key, kind, value, choices)
        container = self._wrap_editor_with_action(key, editor)
        self.config_fields[key]["editor"] = editor
        self.config_fields[key]["editor_container"] = container
        help_text = self._field_tooltip(key, field_schema)
        if help_text:
            editor.setToolTip(help_text)
        self._connect_dynamic_refresh(editor, kind)
        return container

    def _wrap_editor_with_action(self, key, editor):
        field = self.config_fields.get(key) or {}
        action = (field.get("schema") or {}).get("action") or {}
        if not action:
            return editor

        container = self.qt.QtWidgets.QWidget()
        layout = self.qt.QtWidgets.QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(editor, 1)

        button = self.qt.QtWidgets.QPushButton(str(action.get("label") or "操作"))
        button.setMaximumWidth(76)
        button.setToolTip(self._field_action_tooltip(key, action))
        button.clicked.connect(lambda checked=False, field_key=key: self._trigger_field_action(field_key))
        layout.addWidget(button)
        field["action_button"] = button
        self.config_fields[key] = field
        return container

    def _field_action_tooltip(self, key, action):
        label = str(action.get("label") or "")
        if label:
            return label
        return f"操作：{config_field_label(key)}"

    def _trigger_field_action(self, key):
        if not callable(self.action_handler):
            return
        field = self.config_fields.get(key) or {}
        schema = copy.deepcopy(field.get("schema") or {})
        action = copy.deepcopy(schema.get("action") or {})
        if not action:
            return
        payload = {
            "field_key": key,
            "schema": schema,
            "action": action,
            "value": self._field_value_for_action(field),
            "headers": list(self.headers or []),
        }
        result = self.action_handler(payload) or {}
        if "value" in result:
            self._set_field_value(field, result.get("value"))
            self._apply_dynamic_state()

    def _field_value_for_action(self, field):
        editor = field.get("editor")
        kind = field.get("kind")
        if editor is None:
            return None
        if kind == "bool":
            return bool(editor.isChecked())
        if kind == "field_multi_select":
            return list(getattr(editor, "multi_select_value", []))
        if kind == "choice":
            return str(editor.currentText())
        if kind == "structured_list":
            return self._structured_list_value(field)
        if kind in {"long_text", "json"}:
            return str(editor.toPlainText())
        return str(editor.text())

    def _set_field_value(self, field, value):
        editor = field.get("editor")
        kind = field.get("kind")
        if editor is None:
            return
        if kind == "bool":
            editor.setChecked(bool(value))
        elif kind == "field_multi_select":
            values = coerce_multi_select_value(value)
            editor.multi_select_value = values
            editor.setText(format_multi_select_summary(values))
        elif kind == "choice":
            editor.setCurrentText(format_form_value(value))
        elif kind in {"long_text", "json"}:
            editor.setPlainText(format_form_value(value))
        elif kind != "structured_list":
            editor.setText(format_form_value(value))

    def _refresh_dynamic_options(self):
        for key, field in self.config_fields.items():
            editor = field.get("editor")
            schema = field.get("schema") or {}
            if editor is None or field.get("kind") != "choice":
                continue
            options_source = schema.get("options_source") or {}
            if options_source.get("type") != "preview_headers":
                continue
            current = str(editor.currentText())
            editor.blockSignals(True)
            editor.clear()
            values = [str(item) for item in self.headers]
            if current and current not in values:
                values.insert(0, current)
            editor.addItems(values)
            editor.setCurrentText(current)
            editor.blockSignals(False)

    def _form_layout(self, parent):
        form = self.qt.QtWidgets.QFormLayout(parent)
        form.setContentsMargins(8, 8, 8, 8)
        form.setSpacing(6)
        return form

    def _editor_for_field(self, key, kind, value, choices=None):
        if kind == "bool":
            widget = self.qt.QtWidgets.QCheckBox()
            widget.setChecked(bool(value))
            return widget
        if kind == "field_multi_select":
            widget = self._line(format_multi_select_summary(value), read_only=True)
            widget.multi_select_value = coerce_multi_select_value(value)
            return widget
        if kind == "choice":
            widget = self.qt.QtWidgets.QComboBox()
            widget.setEditable(True)
            current = format_form_value(value)
            values = [str(item) for item in (choices or [])]
            if current and current not in values:
                values.insert(0, current)
            if not values:
                values = [current]
            widget.addItems(values)
            widget.setCurrentText(current)
            return widget
        if kind == "json":
            widget = self.qt.QtWidgets.QPlainTextEdit()
            widget.setPlainText(format_form_value(value))
            widget.setMinimumHeight(88)
            return widget
        if kind == "structured_list":
            return self._structured_list_editor(key, value)
        if kind == "long_text":
            widget = self.qt.QtWidgets.QPlainTextEdit()
            widget.setPlainText(format_form_value(value))
            widget.setMinimumHeight(76)
            return widget
        return self._line(format_form_value(value))

    def _structured_list_editor(self, key, value):
        field_schema = self.config_fields.get(key, {}).get("schema", {})
        item_schema = field_schema.get("item_schema") or {}
        columns = list(item_schema.get("columns") or [])

        frame = self.qt.QtWidgets.QWidget()
        layout = self.qt.QtWidgets.QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        table = self.qt.QtWidgets.QTableWidget(frame)
        table.setColumnCount(len(columns))
        table.setHorizontalHeaderLabels([str(col.get("label") or col.get("key") or "") for col in columns])
        table.setMinimumHeight(140)
        table.setSelectionBehavior(self.qt.QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(self.qt.QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        try:
            table.horizontalHeader().setStretchLastSection(True)
        except Exception:
            pass

        button_row = self.qt.QtWidgets.QHBoxLayout()
        add_button = self.qt.QtWidgets.QPushButton("添加")
        remove_button = self.qt.QtWidgets.QPushButton("删除")
        up_button = self.qt.QtWidgets.QPushButton("上移")
        down_button = self.qt.QtWidgets.QPushButton("下移")
        for button in [add_button, remove_button, up_button, down_button]:
            button_row.addWidget(button)
        button_row.addStretch(1)

        layout.addWidget(table)
        layout.addLayout(button_row)

        state = {
            "table": table,
            "columns": columns,
            "buttons": {
                "add": add_button,
                "remove": remove_button,
                "up": up_button,
                "down": down_button,
            },
        }
        frame.structured_state = state

        add_button.clicked.connect(lambda checked=False: self._structured_list_add_row(frame))
        remove_button.clicked.connect(lambda checked=False: self._structured_list_remove_row(frame))
        up_button.clicked.connect(lambda checked=False: self._structured_list_move_row(frame, -1))
        down_button.clicked.connect(lambda checked=False: self._structured_list_move_row(frame, 1))
        table.itemSelectionChanged.connect(lambda: self._update_structured_list_buttons(frame))

        for item in value or []:
            self._structured_list_append_row(frame, item if isinstance(item, dict) else {})
        if table.rowCount() == 0:
            self._structured_list_append_row(frame, structured_item_default(columns))
        self._update_structured_list_buttons(frame)
        return frame

    def _structured_list_append_row(self, frame, item):
        state = getattr(frame, "structured_state", {})
        table = state.get("table")
        columns = state.get("columns") or []
        if table is None:
            return
        row = table.rowCount()
        table.insertRow(row)
        for column_index, column in enumerate(columns):
            key = str(column.get("key") or "")
            cell_value = item.get(key, column.get("default", "")) if isinstance(item, dict) else column.get("default", "")
            editor = self._structured_cell_editor(column, cell_value)
            table.setCellWidget(row, column_index, editor)
            self._connect_dynamic_refresh(editor, self._structured_column_kind(column))
        table.setCurrentCell(row, 0)

    def _structured_cell_editor(self, column, value):
        choices = list(column.get("choices") or [])
        if not choices and (column.get("options_source") or {}).get("type") == "preview_headers":
            choices = list(self.headers)
        kind = self._structured_column_kind(column)
        key = str(column.get("key") or "")
        editor = self._editor_for_field(key, kind, value, choices)
        action = column.get("action") or {}
        if not action and (column.get("options_source") or {}).get("type") == "preview_headers" and kind in {"choice", "field_multi_select"}:
            action = {
                "key": "pick_preview_headers" if kind == "field_multi_select" else "pick_preview_header",
                "label": "选择字段",
                "style": "picker",
                "source": "preview_headers",
                "multiple": kind == "field_multi_select",
            }
        if not action:
            return editor

        container = self.qt.QtWidgets.QWidget()
        layout = self.qt.QtWidgets.QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(editor, 1)
        button = self.qt.QtWidgets.QPushButton(str(action.get("label") or "操作"))
        button.setMaximumWidth(76)
        button.setToolTip(self._field_action_tooltip(key, action))
        button.clicked.connect(
            lambda checked=False, editor_widget=editor, column_schema=copy.deepcopy(column), column_key=key, action_payload=copy.deepcopy(action): self._trigger_structured_cell_action(
                editor_widget,
                kind,
                column_key,
                column_schema,
                action_payload,
            )
        )
        layout.addWidget(button)
        return container

    def _trigger_structured_cell_action(self, editor, kind, column_key, column_schema, action):
        if not callable(self.action_handler):
            return
        payload = {
            "field_key": column_key,
            "schema": copy.deepcopy(column_schema or {}),
            "action": copy.deepcopy(action or {}),
            "value": self._structured_editor_value(editor, kind),
            "headers": list(self.headers or []),
            "context": {"kind": "structured_cell"},
        }
        result = self.action_handler(payload) or {}
        if "value" in result:
            self._set_structured_editor_value(editor, kind, result.get("value"))
            self._apply_dynamic_state()

    def _structured_editor_value(self, editor, kind):
        if kind == "bool":
            return bool(editor.isChecked())
        if kind == "field_multi_select":
            return list(getattr(editor, "multi_select_value", []))
        if kind == "choice":
            return str(editor.currentText())
        if kind == "long_text":
            return str(editor.toPlainText())
        return str(editor.text())

    def _set_structured_editor_value(self, editor, kind, value):
        if kind == "bool":
            editor.setChecked(bool(value))
        elif kind == "field_multi_select":
            values = coerce_multi_select_value(value)
            editor.multi_select_value = values
            editor.setText(format_multi_select_summary(values))
        elif kind == "choice":
            editor.setCurrentText(format_form_value(value))
        elif kind == "long_text":
            editor.setPlainText(format_form_value(value))
        else:
            editor.setText(format_form_value(value))

    def _structured_column_kind(self, column):
        column_type = str((column or {}).get("type") or "text")
        if column_type in {"select", "field_select", "table_select"}:
            return "choice"
        if column_type == "bool":
            return "bool"
        if column_type == "textarea":
            return "long_text"
        if column_type == "number":
            return "text"
        return "text"

    def _structured_list_value(self, field):
        editor = field.get("editor")
        state = getattr(editor, "structured_state", {})
        table = state.get("table")
        columns = state.get("columns") or []
        rows = []
        if table is None:
            return rows
        for row in range(table.rowCount()):
            item = {}
            has_value = False
            for column_index, column in enumerate(columns):
                key = str(column.get("key") or "")
                widget = self._structured_cell_widget(table.cellWidget(row, column_index), column)
                if not key or widget is None:
                    continue
                kind = self._structured_column_kind(column)
                if kind == "bool":
                    value = bool(widget.isChecked())
                elif kind == "choice":
                    value = str(widget.currentText())
                elif kind == "long_text":
                    value = str(widget.toPlainText())
                else:
                    raw = widget.text()
                    if str(column.get("type") or "") == "number":
                        value = coerce_form_value("float", raw, key) if "." in str(raw) else coerce_form_value("int", raw, key)
                    else:
                        value = str(raw)
                item[key] = value
                if value not in ("", None, False):
                    has_value = True
            if has_value:
                rows.append(item)
        return rows

    def _structured_list_current_row(self, frame):
        table = getattr(frame, "structured_state", {}).get("table")
        if table is None:
            return -1
        return table.currentRow()

    def _structured_list_add_row(self, frame):
        columns = getattr(frame, "structured_state", {}).get("columns") or []
        self._structured_list_append_row(frame, structured_item_default(columns))
        self._apply_dynamic_state()

    def _structured_list_remove_row(self, frame):
        state = getattr(frame, "structured_state", {})
        table = state.get("table")
        if table is None:
            return
        row = table.currentRow()
        if row < 0:
            return
        table.removeRow(row)
        if table.rowCount() == 0:
            self._structured_list_append_row(frame, structured_item_default(state.get("columns") or []))
        self._update_structured_list_buttons(frame)
        self._apply_dynamic_state()

    def _structured_list_move_row(self, frame, offset):
        state = getattr(frame, "structured_state", {})
        table = state.get("table")
        columns = state.get("columns") or []
        if table is None:
            return
        row = table.currentRow()
        target = row + int(offset)
        if row < 0 or target < 0 or target >= table.rowCount():
            return
        current = {}
        other = {}
        for column_index, column in enumerate(columns):
            key = str(column.get("key") or column_index)
            current[key] = self._structured_widget_value(self._structured_cell_widget(table.cellWidget(row, column_index), column), column)
            other[key] = self._structured_widget_value(self._structured_cell_widget(table.cellWidget(target, column_index), column), column)
        for column_index, column in enumerate(columns):
            key = str(column.get("key") or column_index)
            self._set_structured_widget_value(self._structured_cell_widget(table.cellWidget(row, column_index), column), column, other.get(key))
            self._set_structured_widget_value(self._structured_cell_widget(table.cellWidget(target, column_index), column), column, current.get(key))
        table.setCurrentCell(target, 0)
        self._update_structured_list_buttons(frame)
        self._apply_dynamic_state()

    def _structured_cell_widget(self, widget, column):
        if widget is None:
            return None
        if hasattr(widget, "currentText") or hasattr(widget, "text") or hasattr(widget, "toPlainText") or hasattr(widget, "isChecked"):
            return widget
        kind = self._structured_column_kind(column)
        if kind == "choice":
            return widget.findChild(self.qt.QtWidgets.QComboBox)
        if kind == "bool":
            return widget.findChild(self.qt.QtWidgets.QCheckBox)
        if kind == "long_text":
            return widget.findChild(self.qt.QtWidgets.QPlainTextEdit)
        return widget.findChild(self.qt.QtWidgets.QLineEdit)

    def _structured_widget_value(self, widget, column):
        if widget is None:
            return ""
        kind = self._structured_column_kind(column)
        if kind == "bool":
            return bool(widget.isChecked())
        if kind == "choice":
            return str(widget.currentText())
        if kind == "long_text":
            return str(widget.toPlainText())
        return str(widget.text())

    def _set_structured_widget_value(self, widget, column, value):
        if widget is None:
            return
        kind = self._structured_column_kind(column)
        if kind == "bool":
            widget.setChecked(bool(value))
        elif kind == "choice":
            widget.setCurrentText(format_form_value(value))
        elif kind == "long_text":
            widget.setPlainText(format_form_value(value))
        else:
            widget.setText(format_form_value(value))

    def _update_structured_list_buttons(self, frame):
        state = getattr(frame, "structured_state", {})
        table = state.get("table")
        buttons = state.get("buttons") or {}
        row = table.currentRow() if table is not None else -1
        count = table.rowCount() if table is not None else 0
        if buttons.get("remove") is not None:
            buttons["remove"].setEnabled(row >= 0 and count > 0)
        if buttons.get("up") is not None:
            buttons["up"].setEnabled(row > 0)
        if buttons.get("down") is not None:
            buttons["down"].setEnabled(0 <= row < count - 1)

    def _line(self, value="", read_only=False):
        widget = self.qt.QtWidgets.QLineEdit()
        widget.setText(format_form_value(value))
        widget.setReadOnly(bool(read_only))
        return widget

    def _field_tooltip(self, key, field_schema):
        parts = []
        help_text = field_schema.get("help") or field_help_text(key)
        if help_text:
            parts.append(str(help_text))
        validation = field_schema.get("validation") or {}
        if validation.get("required"):
            parts.append("必填")
        if validation.get("integer"):
            parts.append("必须为整数")
        if "min" in validation:
            parts.append(f"最小值：{validation['min']}")
        return "\n".join(parts)

    def _connect_dynamic_refresh(self, editor, kind):
        try:
            if kind == "bool":
                editor.stateChanged.connect(lambda *_args: self._apply_dynamic_state())
            elif kind == "choice":
                editor.currentTextChanged.connect(lambda *_args: self._apply_dynamic_state())
            elif kind in {"long_text", "json"}:
                editor.textChanged.connect(lambda *_args: self._apply_dynamic_state())
            else:
                editor.textChanged.connect(lambda *_args: self._apply_dynamic_state())
        except AttributeError:
            return

    def _apply_dynamic_state(self):
        values = self._current_field_values()
        for field in self.config_fields.values():
            label = field.get("label")
            editor = field.get("editor")
            container = field.get("editor_container") or editor
            action_button = field.get("action_button")
            if editor is None:
                continue
            visible = self._condition_matches(field.get("visible_when"), values)
            enabled = visible and self._condition_matches(field.get("enabled_when"), values)
            if label is not None:
                label.setVisible(visible)
            container.setVisible(visible)
            editor.setEnabled(enabled)
            if action_button is not None:
                action_button.setEnabled(enabled)
        self._apply_validation_state()

    def _apply_validation_state(self):
        issue_map = {}
        for issue in self.validation_issues or []:
            path = str((issue or {}).get("path") or "")
            field_key = path.split(".")[-1] if path else ""
            if field_key:
                issue_map.setdefault(field_key, []).append(copy.deepcopy(issue))
        for key, field in self.config_fields.items():
            editor = field.get("editor")
            label = field.get("label")
            field_issues = list(issue_map.get(key) or [])
            field["issues"] = field_issues
            tooltip = self._field_tooltip(key, field.get("schema") or {})
            if field_issues:
                issue_text = "\n".join(str(item.get("message") or "") for item in field_issues if str(item.get("message") or "").strip())
                tooltip = (tooltip + "\n\n" if tooltip else "") + issue_text
            if editor is not None:
                editor.setToolTip(tooltip)
            if label is not None:
                label.setToolTip(tooltip)

    def _current_field_values(self):
        values = {}
        for key, field in self.config_fields.items():
            editor = field.get("editor")
            kind = field.get("kind")
            if editor is None:
                continue
            if kind == "bool":
                values[key] = bool(editor.isChecked())
            elif kind == "field_multi_select":
                values[key] = list(getattr(editor, "multi_select_value", []))
            elif kind == "choice":
                values[key] = str(editor.currentText())
            elif kind == "structured_list":
                values[key] = self._structured_list_value(field)
            elif kind in {"long_text", "json"}:
                values[key] = str(editor.toPlainText())
            else:
                values[key] = str(editor.text())
        return values

    def _condition_matches(self, condition, values):
        if not condition:
            return True
        if not isinstance(condition, dict):
            return True
        if "all" in condition:
            return all(self._condition_matches(item, values) for item in condition.get("all") or [])
        if "any" in condition:
            return any(self._condition_matches(item, values) for item in condition.get("any") or [])
        if "not" in condition:
            return not self._condition_matches(condition.get("not"), values)

        field = condition.get("field")
        actual = values.get(field)
        if "equals" in condition and not self._values_equal(actual, condition.get("equals")):
            return False
        if "not_equals" in condition and self._values_equal(actual, condition.get("not_equals")):
            return False
        if "in" in condition:
            expected_values = condition.get("in") or []
            if not any(self._values_equal(actual, expected) for expected in expected_values):
                return False
        if "not_in" in condition:
            expected_values = condition.get("not_in") or []
            if any(self._values_equal(actual, expected) for expected in expected_values):
                return False
        if "truthy" in condition and bool(actual) is not bool(condition.get("truthy")):
            return False
        return True

    def _values_equal(self, actual, expected):
        if isinstance(expected, bool):
            if isinstance(actual, bool):
                return actual is expected
            return str(actual).strip().lower() in {"1", "true", "yes", "on"} if expected else str(actual).strip().lower() in {"", "0", "false", "no", "off"}
        return str(actual) == str(expected)
