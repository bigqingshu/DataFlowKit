# -*- coding: utf-8 -*-
import queue
import unittest
from unittest.mock import patch

from workflow.plan_workflow_window_init_mixin import PlanWorkflowWindowInitMixin


class FakeVar:
    def __init__(self, value=None):
        self.value = value

    def get(self):
        return self.value


class FakeToplevel:
    def __init__(self, root):
        self.root = root
        self.calls = []

    def title(self, value):
        self.calls.append(("title", value))

    def geometry(self, value):
        self.calls.append(("geometry", value))

    def minsize(self, width, height):
        self.calls.append(("minsize", width, height))

    def transient(self, root):
        self.calls.append(("transient", root))


class FakeTableNameVar:
    def get(self):
        return "source_table"


class FakeApp:
    def __init__(self):
        self.root = object()
        self.headers = ["A", "B"]
        self.rows = [["a", "b"], ["c"]]
        self.table_name_var = FakeTableNameVar()

    def sanitize_sql_name(self, value, fallback):
        return value or fallback


class FakeWindow(PlanWorkflowWindowInitMixin):
    NODE_TYPES = ["批量替换", "高级筛选"]

    def make_default_output_table_name(self):
        return "默认输出表"

    def load_plugins(self, show_status=False):
        self.calls.append(("load_plugins", show_status))

    def get_plan_dir(self):
        self.calls.append(("get_plan_dir",))
        return "plan-dir"

    def get_group_dir(self):
        self.calls.append(("get_group_dir",))
        return "group-dir"

    def build_ui(self):
        self.calls.append(("build_ui",))

    def refresh_node_list(self):
        self.calls.append(("refresh_node_list",))

    def refresh_preview_tree(self, headers, rows):
        self.calls.append(("refresh_preview_tree", list(headers), [list(row) for row in rows]))

    def refresh_plan_template_list(self, show_status=False):
        self.calls.append(("refresh_plan_template_list", show_status))


class PlanWorkflowWindowInitMixinTests(unittest.TestCase):
    def test_initializes_workflow_window_state_and_startup_refreshes(self):
        app = FakeApp()
        FakeWindow.calls = []

        def init_calls(self):
            self.calls = []
            PlanWorkflowWindowInitMixin.__init__(self, app)

        FakeWindow.__init__ = init_calls

        with patch("workflow.plan_workflow_window_init_mixin.tk.Toplevel", new=FakeToplevel):
            with patch("workflow.plan_workflow_window_init_mixin.tk.StringVar", new=FakeVar):
                with patch("workflow.plan_workflow_window_init_mixin.tk.BooleanVar", new=FakeVar):
                    with patch("workflow.plan_workflow_window_init_mixin.tk.DoubleVar", new=FakeVar):
                        window = FakeWindow()

        self.assertEqual(window.window.calls, [
            ("title", "计划 / 工作流处理"),
            ("geometry", "1680x950"),
            ("minsize", 1050, 650),
            ("transient", app.root),
        ])
        self.assertEqual(window.nodes, [])
        self.assertEqual(window.preview_headers, ["A", "B"])
        self.assertEqual(window.preview_rows, [["a", "b"], ["c"]])
        self.assertEqual(window.output_mode_var.get(), "输出到主界面预览区")
        self.assertEqual(window.output_table_var.get(), "默认输出表")
        self.assertTrue(window.backup_before_overwrite_var.get())
        self.assertEqual(window.table_access_policy_var.get(), "只审计")
        self.assertEqual(window.node_type_var.get(), "批量替换")
        self.assertEqual(window.plan_preview_headers, ["A", "B"])
        self.assertEqual(window.plan_preview_rows, [["a", "b"], ["c"]])
        self.assertEqual(window.preview_view_kind, "preview")
        self.assertEqual(window.preview_table_var.get(), "当前预览结果")
        self.assertIsNone(window.manual_loop_context)
        self.assertIsInstance(window.workflow_worker_queue, queue.Queue)
        self.assertEqual(window.workflow_progress_var.get(), 0)
        self.assertEqual(window.node_progress_var.get(), 0)
        self.assertEqual(window.plugin_registry, {})
        self.assertEqual(window.plugin_display_map, {})
        self.assertEqual(window.plugin_load_errors, [])
        self.assertEqual(window.plan_dir, "plan-dir")
        self.assertEqual(window.group_dir, "group-dir")
        self.assertEqual(window.plan_template_var.get(), "")
        self.assertEqual(window.plan_template_map, {})
        self.assertEqual(window.calls, [
            ("load_plugins", False),
            ("get_plan_dir",),
            ("get_group_dir",),
            ("build_ui",),
            ("refresh_node_list",),
            ("refresh_preview_tree", ["A", "B"], [["a", "b"], ["c"]]),
            ("refresh_plan_template_list", False),
        ])


if __name__ == "__main__":
    unittest.main()
