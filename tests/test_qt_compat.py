# -*- coding: utf-8 -*-
import sys
import types
import unittest

from ui_qt import qt_compat
from ui_qt.table_model import create_table_model_class, normalize_table


class FakeIndex:
    def __init__(self, row=0, column=0, valid=True):
        self._row = row
        self._column = column
        self._valid = valid

    def isValid(self):
        return self._valid

    def row(self):
        return self._row

    def column(self):
        return self._column


class FakeSignalEmitter:
    def __init__(self):
        self.calls = []

    def emit(self, *args):
        self.calls.append(args)


class FakeAbstractTableModel:
    def __init__(self, parent=None):
        self.parent = parent
        self.dataChanged = FakeSignalEmitter()
        self.reset_calls = []

    def flags(self, index):
        return 1

    def beginResetModel(self):
        self.reset_calls.append("begin")

    def endResetModel(self):
        self.reset_calls.append("end")


class FakeQt6Namespace:
    class ItemDataRole:
        DisplayRole = "display"
        EditRole = "edit"

    class Orientation:
        Horizontal = "horizontal"
        Vertical = "vertical"

    class ItemFlag:
        ItemIsEditable = 2


class FakeQt5Namespace:
    DisplayRole = "display"
    EditRole = "edit"
    Horizontal = "horizontal"
    Vertical = "vertical"
    ItemIsEditable = 2


def install_fake_binding(name, qt_namespace, pyside=True):
    package = types.ModuleType(name)
    package.__path__ = []
    core = types.ModuleType(f"{name}.QtCore")
    core.Qt = qt_namespace
    core.QAbstractTableModel = FakeAbstractTableModel
    if pyside:
        core.Signal = object
        core.Slot = object
        core.Property = object
    else:
        core.pyqtSignal = object
        core.pyqtSlot = object
        core.pyqtProperty = object
    gui = types.ModuleType(f"{name}.QtGui")
    widgets = types.ModuleType(f"{name}.QtWidgets")
    sys.modules[name] = package
    sys.modules[f"{name}.QtCore"] = core
    sys.modules[f"{name}.QtGui"] = gui
    sys.modules[f"{name}.QtWidgets"] = widgets
    return [name, f"{name}.QtCore", f"{name}.QtGui", f"{name}.QtWidgets"]


class QtCompatTests(unittest.TestCase):
    def tearDown(self):
        qt_compat._cached_qt = None

    def test_normalize_binding_accepts_supported_aliases(self):
        self.assertEqual(qt_compat.normalize_binding("pyqt5"), "PyQt5")
        self.assertEqual(qt_compat.normalize_binding("PySide6"), "PySide6")
        with self.assertRaises(ValueError):
            qt_compat.normalize_binding("Qt7")

    def test_binding_candidates_respects_preferred_and_env(self):
        self.assertEqual(qt_compat.binding_candidates("PyQt6"), ("PyQt6",))
        self.assertEqual(
            qt_compat.binding_candidates(env={qt_compat.QT_API_ENV: "pyside2"}),
            ("PySide2",),
        )
        self.assertEqual(qt_compat.binding_candidates(env={}), qt_compat.SUPPORTED_BINDINGS)

    def test_loads_fake_pyside6_binding(self):
        keys = install_fake_binding("PySide6", FakeQt6Namespace, pyside=True)
        try:
            api = qt_compat.load_qt("PySide6")
            self.assertEqual(api.binding, "PySide6")
            self.assertTrue(api.is_qt6)
            self.assertTrue(api.is_pyside)
            self.assertEqual(qt_compat.qt_enum(api, "ItemDataRole", "DisplayRole"), "display")
        finally:
            for key in keys:
                sys.modules.pop(key, None)

    def test_loads_fake_pyqt5_binding(self):
        keys = install_fake_binding("PyQt5", FakeQt5Namespace, pyside=False)
        try:
            api = qt_compat.load_qt("PyQt5")
            self.assertEqual(api.binding, "PyQt5")
            self.assertFalse(api.is_qt6)
            self.assertTrue(api.is_pyqt)
            self.assertEqual(qt_compat.qt_enum(api, "ItemDataRole", "DisplayRole"), "display")
        finally:
            for key in keys:
                sys.modules.pop(key, None)

    def test_exec_qt_supports_qt6_and_qt5_names(self):
        class Qt6Object:
            def exec(self):
                return "qt6"

        class Qt5Object:
            def exec_(self):
                return "qt5"

        self.assertEqual(qt_compat.exec_qt(Qt6Object()), "qt6")
        self.assertEqual(qt_compat.exec_qt(Qt5Object()), "qt5")

    def test_normalize_table_rectangularizes_rows(self):
        headers, rows = normalize_table(["A", "B"], [[1], [2, 3, 4]])
        self.assertEqual(headers, ["A", "B"])
        self.assertEqual(rows, [[1, ""], [2, 3]])

    def test_table_model_uses_compat_enums(self):
        keys = install_fake_binding("PySide6", FakeQt6Namespace, pyside=True)
        try:
            api = qt_compat.load_qt("PySide6")
            model_class = create_table_model_class(api)
            model = model_class(headers=["A", "B"], rows=[[1, None]])

            self.assertEqual(model.rowCount(), 1)
            self.assertEqual(model.columnCount(), 2)
            self.assertEqual(model.data(FakeIndex(0, 0)), "1")
            self.assertEqual(model.data(FakeIndex(0, 1)), "")
            self.assertEqual(model.headerData(0, FakeQt6Namespace.Orientation.Horizontal), "A")
            self.assertEqual(model.headerData(0, FakeQt6Namespace.Orientation.Vertical), "1")
            self.assertTrue(model.setData(FakeIndex(0, 1), "x"))
            self.assertEqual(model.rows, [[1, "x"]])
            self.assertEqual(len(model.dataChanged.calls), 1)

            model.set_table(["C"], [[3, 4]])
            self.assertEqual(model.table_data(), (["C"], [[3]]))
            self.assertEqual(model.reset_calls, ["begin", "end"])
        finally:
            for key in keys:
                sys.modules.pop(key, None)


if __name__ == "__main__":
    unittest.main()

