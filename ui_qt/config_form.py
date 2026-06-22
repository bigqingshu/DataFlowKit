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


class NodeConfigForm:
    """Build editable Qt widgets for a workflow node dict."""

    def __init__(self, qt, parent=None, headers=None):
        self.qt = qt
        self.headers = list(headers or [])
        self.widget = qt.QtWidgets.QWidget(parent)
        self.root_layout = qt.QtWidgets.QVBoxLayout(self.widget)
        self.root_layout.setContentsMargins(0, 0, 0, 0)
        self.root_layout.setSpacing(8)
        self.scroll_area = qt.QtWidgets.QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.root_layout.addWidget(self.scroll_area)
        self.node = None
        self.node_fields = {}
        self.config_fields = {}
        self.set_node(None)

    def set_headers(self, headers):
        self.headers = list(headers or [])

    def set_node(self, node, headers=None):
        if headers is not None:
            self.set_headers(headers)
        self.node = copy.deepcopy(node) if isinstance(node, dict) else None
        self.node_fields = {}
        self.config_fields = {}

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
            elif kind == "choice":
                config[key] = str(editor.currentText())
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

    def _build_config_group(self, title, config, keys):
        group = self.qt.QtWidgets.QGroupBox(title or "参数")
        form = self._form_layout(group)
        for key in keys:
            value = config[key]
            editor = self._build_config_editor(key, value)
            form.addRow(config_field_label(key), editor)
        return group

    def _build_config_editor(self, key, value):
        choices = choices_for_field(key, headers=self.headers)
        if choices:
            kind = "choice"
        elif is_long_text_field(key):
            kind = "long_text"
        else:
            kind = value_kind(value)
        editor = self._editor_for_field(key, kind, value, choices)
        help_text = field_help_text(key)
        if help_text:
            editor.setToolTip(help_text)
        self.config_fields[key] = {
            "kind": kind,
            "editor": editor,
        }
        return editor

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
        if kind == "long_text":
            widget = self.qt.QtWidgets.QPlainTextEdit()
            widget.setPlainText(format_form_value(value))
            widget.setMinimumHeight(76)
            return widget
        return self._line(format_form_value(value))

    def _line(self, value="", read_only=False):
        widget = self.qt.QtWidgets.QLineEdit()
        widget.setText(format_form_value(value))
        widget.setReadOnly(bool(read_only))
        return widget
