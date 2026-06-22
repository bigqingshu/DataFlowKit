# -*- coding: utf-8 -*-
"""Standalone Qt table prototype.

Run after installing one supported binding, for example:

    python -m pip install PySide6
    python -m ui_qt.demo_table
"""

from __future__ import annotations

import sys

from ui_qt.qt_compat import QtBindingUnavailable, exec_qt, get_qt
from ui_qt.table_model import make_table_model


SAMPLE_HEADERS = ["source_file", "sheet_name", "row_index", "text"]
SAMPLE_ROWS = [
    ["demo.xlsx", "Sheet1", 1, "alpha"],
    ["demo.xlsx", "Sheet1", 2, "beta"],
    ["report.docx", "Paragraph", 1, "gamma"],
]


def build_window(qt=None, headers=None, rows=None):
    qt = qt or get_qt()
    window = qt.QtWidgets.QMainWindow()
    window.setWindowTitle(f"DataFlowKit Qt table prototype ({qt.binding})")

    table = qt.QtWidgets.QTableView()
    model = make_table_model(headers or SAMPLE_HEADERS, rows or SAMPLE_ROWS, qt=qt, parent=table)
    table.setModel(model)
    table.setAlternatingRowColors(True)
    table.setWordWrap(False)
    try:
        table.horizontalHeader().setStretchLastSection(True)
    except Exception:
        pass

    window.setCentralWidget(table)
    window.resize(960, 540)
    window.table_view = table
    window.table_model = model
    return window


def main(argv=None, preferred_binding=None):
    argv = list(sys.argv if argv is None else argv)
    qt = get_qt(preferred_binding)
    app = qt.QtWidgets.QApplication.instance() or qt.QtWidgets.QApplication(argv)
    window = build_window(qt=qt)
    window.show()
    return exec_qt(app)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except QtBindingUnavailable as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(2)

