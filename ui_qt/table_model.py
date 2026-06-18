# -*- coding: utf-8 -*-
"""Qt table model prototype for DataFlowKit tables."""

from __future__ import annotations

from typing import Iterable, List, Optional, Sequence

from ui_qt.qt_compat import QtApi, get_qt, qt_enum


def normalize_table(headers: Optional[Iterable[object]], rows: Optional[Iterable[Iterable[object]]]):
    """Return normalized ``headers`` and rectangular ``rows`` lists."""

    fixed_headers = [str(item) for item in (headers or [])]
    width = len(fixed_headers)
    fixed_rows: List[List[object]] = []
    for raw_row in rows or []:
        row = list(raw_row)
        if width and len(row) < width:
            row.extend([""] * (width - len(row)))
        if width and len(row) > width:
            row = row[:width]
        fixed_rows.append(row)
    return fixed_headers, fixed_rows


_model_class_cache = {}


def create_table_model_class(qt: Optional[QtApi] = None):
    """Create a ``QAbstractTableModel`` subclass for the selected Qt binding."""

    qt = qt or get_qt()
    if qt.binding in _model_class_cache:
        return _model_class_cache[qt.binding]

    display_role = qt_enum(qt, "ItemDataRole", "DisplayRole")
    edit_role = qt_enum(qt, "ItemDataRole", "EditRole")
    horizontal = qt_enum(qt, "Orientation", "Horizontal")
    item_is_editable = qt_enum(qt, "ItemFlag", "ItemIsEditable")

    class TableDataModel(qt.QtCore.QAbstractTableModel):
        """Editable table model backed by ``headers`` and ``rows`` lists."""

        def __init__(self, headers=None, rows=None, parent=None):
            super().__init__(parent)
            self.headers, self.rows = normalize_table(headers, rows)

        def rowCount(self, parent=None):  # noqa: N802 - Qt API name
            return len(self.rows)

        def columnCount(self, parent=None):  # noqa: N802 - Qt API name
            return len(self.headers)

        def data(self, index, role=display_role):
            if not index or not index.isValid():
                return None
            if role not in (display_role, edit_role):
                return None
            row = index.row()
            column = index.column()
            if row < 0 or row >= len(self.rows):
                return None
            if column < 0 or column >= len(self.headers):
                return None
            value = self.rows[row][column] if column < len(self.rows[row]) else ""
            return "" if value is None else str(value)

        def setData(self, index, value, role=edit_role):  # noqa: N802 - Qt API name
            if role != edit_role or not index or not index.isValid():
                return False
            row = index.row()
            column = index.column()
            if row < 0 or row >= len(self.rows):
                return False
            if column < 0 or column >= len(self.headers):
                return False
            while len(self.rows[row]) < len(self.headers):
                self.rows[row].append("")
            self.rows[row][column] = "" if value is None else str(value)
            self.dataChanged.emit(index, index, [role])
            return True

        def flags(self, index):
            base_flags = super().flags(index)
            if not index or not index.isValid():
                return base_flags
            return base_flags | item_is_editable

        def headerData(self, section, orientation, role=display_role):  # noqa: N802 - Qt API name
            if role != display_role:
                return None
            if orientation == horizontal:
                if 0 <= section < len(self.headers):
                    return self.headers[section]
                return ""
            return str(section + 1)

        def set_table(self, headers: Sequence[object], rows: Sequence[Sequence[object]]):
            self.beginResetModel()
            self.headers, self.rows = normalize_table(headers, rows)
            self.endResetModel()

        def table_data(self):
            return list(self.headers), [list(row) for row in self.rows]

    TableDataModel.__name__ = f"TableDataModel_{qt.binding}"
    _model_class_cache[qt.binding] = TableDataModel
    return TableDataModel


def make_table_model(headers=None, rows=None, qt: Optional[QtApi] = None, parent=None):
    """Create a table model instance for the selected Qt binding."""

    model_class = create_table_model_class(qt)
    return model_class(headers=headers, rows=rows, parent=parent)

