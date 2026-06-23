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
    cache_key = (qt.binding, id(qt.QtCore.QAbstractTableModel))
    if cache_key in _model_class_cache:
        return _model_class_cache[cache_key]

    display_role = qt_enum(qt, "ItemDataRole", "DisplayRole")
    edit_role = qt_enum(qt, "ItemDataRole", "EditRole")
    background_role = qt_enum(qt, "ItemDataRole", "BackgroundRole")
    horizontal = qt_enum(qt, "Orientation", "Horizontal")
    item_is_editable = qt_enum(qt, "ItemFlag", "ItemIsEditable")
    search_match_brush = qt.QtGui.QBrush(qt.QtGui.QColor("#fff5c2"))
    search_current_brush = qt.QtGui.QBrush(qt.QtGui.QColor("#ffd36e"))

    class TableDataModel(qt.QtCore.QAbstractTableModel):
        """Editable table model backed by ``headers`` and ``rows`` lists."""

        def __init__(self, headers=None, rows=None, parent=None):
            super().__init__(parent)
            self.headers, self.rows = normalize_table(headers, rows)
            self.search_highlight_rows = set()
            self.search_current_cell = None

        def rowCount(self, parent=None):  # noqa: N802 - Qt API name
            return len(self.rows)

        def columnCount(self, parent=None):  # noqa: N802 - Qt API name
            return len(self.headers)

        def data(self, index, role=display_role):
            if not index or not index.isValid():
                return None
            if role not in (display_role, edit_role, background_role):
                return None
            row = index.row()
            column = index.column()
            if row < 0 or row >= len(self.rows):
                return None
            if column < 0 or column >= len(self.headers):
                return None
            if role == background_role:
                current = self.search_current_cell
                if current and row == current[0]:
                    return search_current_brush
                if row in self.search_highlight_rows:
                    return search_match_brush
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
            self.search_highlight_rows = set()
            self.search_current_cell = None
            self.endResetModel()

        def table_data(self):
            return list(self.headers), [list(row) for row in self.rows]

        def set_search_highlight(self, rows=None, current_cell=None):
            previous_rows = set(self.search_highlight_rows)
            previous_current = self.search_current_cell
            next_rows = {int(row) for row in (rows or []) if self._valid_row(row)}
            next_current = self._normalized_cell(current_cell)
            changed_rows = previous_rows | next_rows
            if previous_current is not None:
                changed_rows.add(previous_current[0])
            if next_current is not None:
                changed_rows.add(next_current[0])
            self.search_highlight_rows = next_rows
            self.search_current_cell = next_current
            self._emit_background_changed(changed_rows)

        def clear_search_highlight(self):
            self.set_search_highlight([])

        def _normalized_cell(self, cell):
            if not cell:
                return None
            try:
                row, column = int(cell[0]), int(cell[1])
            except (TypeError, ValueError, IndexError):
                return None
            if row < 0 or row >= len(self.rows):
                return None
            if column < 0 or column >= len(self.headers):
                return None
            return row, column

        def _valid_row(self, row):
            try:
                value = int(row)
            except (TypeError, ValueError):
                return False
            return 0 <= value < len(self.rows)

        def _emit_background_changed(self, rows):
            if not rows or not self.headers:
                return
            roles = [background_role]
            last_column = len(self.headers) - 1
            for row in sorted(rows):
                if 0 <= row < len(self.rows):
                    self.dataChanged.emit(self.index(row, 0), self.index(row, last_column), roles)

    TableDataModel.__name__ = f"TableDataModel_{qt.binding}"
    _model_class_cache[cache_key] = TableDataModel
    return TableDataModel


def make_table_model(headers=None, rows=None, qt: Optional[QtApi] = None, parent=None):
    """Create a table model instance for the selected Qt binding."""

    model_class = create_table_model_class(qt)
    return model_class(headers=headers, rows=rows, parent=parent)
