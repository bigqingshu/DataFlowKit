# -*- coding: utf-8 -*-
"""Shared QTableView setup helpers."""

from __future__ import annotations

from ui_qt.qt_compat import qt_enum


def item_view_enum(qt, group_name, member_name):
    group = getattr(qt.QtWidgets.QAbstractItemView, group_name, None)
    if group is not None and hasattr(group, member_name):
        return getattr(group, member_name)
    return getattr(qt.QtWidgets.QAbstractItemView, member_name)


def header_resize_enum(qt, member_name):
    group = getattr(qt.QtWidgets.QHeaderView, "ResizeMode", None)
    if group is not None and hasattr(group, member_name):
        return getattr(group, member_name)
    return getattr(qt.QtWidgets.QHeaderView, member_name)


def configure_fast_table_view(qt, table_view, *, stretch_last_section=False):
    """Apply DataFlowKit's default table-view behavior for large data grids."""

    table_view.setAlternatingRowColors(True)
    table_view.setWordWrap(False)
    table_view.setShowGrid(False)
    table_view.setSortingEnabled(False)
    table_view.setAutoScroll(False)
    table_view.setSelectionBehavior(item_view_enum(qt, "SelectionBehavior", "SelectRows"))
    table_view.setSelectionMode(item_view_enum(qt, "SelectionMode", "SingleSelection"))
    table_view.setTextElideMode(qt_enum(qt, "TextElideMode", "ElideRight"))
    table_view.setVerticalScrollMode(item_view_enum(qt, "ScrollMode", "ScrollPerPixel"))
    table_view.setHorizontalScrollMode(item_view_enum(qt, "ScrollMode", "ScrollPerPixel"))
    table_view.setStyleSheet(
        "QTableView::item:selected { background: #2f6fed; color: white; }"
        "QTableView::item:selected:!active { background: #8ab4ff; color: #101828; }"
    )

    try:
        horizontal = table_view.horizontalHeader()
        horizontal.setStretchLastSection(bool(stretch_last_section))
        horizontal.setDefaultSectionSize(120)
        horizontal.setMinimumSectionSize(48)
        horizontal.setSectionResizeMode(header_resize_enum(qt, "Interactive"))
    except Exception:
        pass

    try:
        vertical = table_view.verticalHeader()
        vertical.setDefaultSectionSize(24)
        vertical.setMinimumSectionSize(18)
        vertical.setSectionResizeMode(header_resize_enum(qt, "Fixed"))
    except Exception:
        pass
