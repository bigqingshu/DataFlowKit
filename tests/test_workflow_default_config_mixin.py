# -*- coding: utf-8 -*-
import unittest
from unittest.mock import patch

from workflow.workflow_default_config_mixin import WorkflowDefaultConfigMixin


class FakeApp:
    def __init__(self, app_dir="C:\\app", table_names=None, table_columns=None, fail_names=False, fail_columns=False):
        self.app_dir = app_dir
        self.table_names = list(table_names or [])
        self.table_columns = dict(table_columns or {})
        self.fail_names = fail_names
        self.fail_columns = fail_columns
        self.calls = []

    def get_table_names(self):
        self.calls.append(("get_table_names",))
        if self.fail_names:
            raise RuntimeError("names failed")
        return list(self.table_names)

    def get_table_columns(self, table):
        self.calls.append(("get_table_columns", table))
        if self.fail_columns:
            raise RuntimeError("columns failed")
        return list(self.table_columns.get(table, []))


class FakeWindow(WorkflowDefaultConfigMixin):
    def __init__(self, app):
        self.app = app
        self.preview_headers = ["A", "B"]


class WorkflowDefaultConfigMixinTests(unittest.TestCase):
    def test_non_sqlite_node_uses_preview_headers_without_table_lookup(self):
        app = FakeApp(app_dir="C:\\demo", table_names=["target"])
        window = FakeWindow(app)

        with patch("workflow.workflow_default_config_mixin.build_default_config_for_type", return_value={"ok": True}) as build:
            result = window.default_config_for_type("批量替换")

        self.assertEqual(result, {"ok": True})
        self.assertEqual(app.calls, [])
        build.assert_called_once_with(
            "批量替换",
            preview_headers=["A", "B"],
            table_names=[],
            table_columns={},
            app_dir="C:\\demo",
        )

    def test_sqlite_node_collects_table_names_and_first_table_columns(self):
        app = FakeApp(
            table_names=["target", "other"],
            table_columns={"target": ["K1", "K2"], "other": ["O1"]},
        )
        window = FakeWindow(app)

        with patch("workflow.workflow_default_config_mixin.build_default_config_for_type", return_value={}) as build:
            window.default_config_for_type("字段映射写入表")

        self.assertEqual(app.calls, [("get_table_names",), ("get_table_columns", "target")])
        build.assert_called_once_with(
            "字段映射写入表",
            preview_headers=["A", "B"],
            table_names=["target", "other"],
            table_columns={"target": ["K1", "K2"]},
            app_dir="C:\\app",
        )

    def test_sqlite_lookup_failures_fall_back_to_empty_defaults(self):
        app = FakeApp(fail_names=True)
        window = FakeWindow(app)

        with patch("workflow.workflow_default_config_mixin.build_default_config_for_type", return_value={}) as build:
            window.default_config_for_type("匹配值输出列名")

        build.assert_called_once_with(
            "匹配值输出列名",
            preview_headers=["A", "B"],
            table_names=[],
            table_columns={},
            app_dir="C:\\app",
        )

        app = FakeApp(table_names=["broken"], fail_columns=True)
        window = FakeWindow(app)
        with patch("workflow.workflow_default_config_mixin.build_default_config_for_type", return_value={}) as build:
            window.default_config_for_type("选定列写入指定表")

        build.assert_called_once_with(
            "选定列写入指定表",
            preview_headers=["A", "B"],
            table_names=["broken"],
            table_columns={"broken": []},
            app_dir="C:\\app",
        )


if __name__ == "__main__":
    unittest.main()
