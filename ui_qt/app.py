# -*- coding: utf-8 -*-
"""Qt6 shell entry point.

Run with:

    python -m ui_qt.app
"""

from __future__ import annotations

import argparse
import os
import sys

from ui_qt.main_window import build_main_window
from ui_qt.qt_compat import QtBindingUnavailable, exec_qt, get_qt


QT6_BINDINGS = ("PySide6", "PyQt6")


def load_qt6(preferred_binding=None):
    candidates = (preferred_binding,) if preferred_binding else QT6_BINDINGS
    failures = []
    for binding in candidates:
        if binding not in QT6_BINDINGS:
            failures.append(f"{binding}: Qt6 shell only supports PySide6/PyQt6")
            continue
        try:
            return get_qt(binding)
        except QtBindingUnavailable as exc:
            failures.append(f"{binding}: {exc}")
    raise QtBindingUnavailable("; ".join(failures) or "No Qt6 binding candidates")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="DataFlowKit Qt6 shell")
    parser.add_argument("--binding", choices=QT6_BINDINGS, default="", help="Force a Qt6 binding")
    parser.add_argument("--offscreen", action="store_true", help="Use the Qt offscreen platform plugin")
    parser.add_argument("--smoke", action="store_true", help="Create the window and exit immediately")
    return parser.parse_args(list(argv or []))


def main(argv=None, preferred_binding=None):
    cli_args = list(sys.argv[1:] if argv is None else argv)
    args = parse_args(cli_args)
    if args.offscreen:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    qt = load_qt6(preferred_binding or args.binding or None)
    app_argv = [sys.argv[0]] + cli_args
    app = qt.QtWidgets.QApplication.instance() or qt.QtWidgets.QApplication(app_argv)
    window = build_main_window(qt)
    window.show()
    if args.smoke:
        qt.QtCore.QTimer.singleShot(0, app.quit)
    return exec_qt(app)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except QtBindingUnavailable as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(2)
