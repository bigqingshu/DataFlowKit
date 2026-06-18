# -*- coding: utf-8 -*-
import os
import tempfile
import unittest

from workflow.workflow_app_support_mixin import WorkflowAppSupportMixin
from workflow.workflow_task_snapshot_mixin import WorkflowTaskSnapshotMixin
from workflow.window_geometry_mixin import WindowGeometryMixin


class FakeVar:
    def __init__(self, value=None):
        self.value = value

    def get(self):
        return self.value


class FakeApp:
    def __init__(self, app_dir):
        self.app_dir = app_dir
        self.db_path_var = FakeVar(os.path.join(app_dir, "demo.db"))


class FakeWindow(WorkflowAppSupportMixin, WorkflowTaskSnapshotMixin, WindowGeometryMixin):
    def __init__(self, app_dir):
        self.app = FakeApp(app_dir)
        self.app.headers = ["A"]
        self.app.rows = [["1"]]
        self.nodes = [{"type": "批量替换"}]
        self.output_table_var = FakeVar("结果")
        self.output_mode_var = FakeVar("输出到主界面预览区")
        self.backup_before_overwrite_var = FakeVar(True)
        self.manual_loop_context = None
        self.manual_loop_after_index = None
        self.manual_loop_headers = None
        self.manual_loop_rows = None
        self.window = self

    def normalize_table_access_policy(self):
        return "audit"

    def ensure_node_identity(self, node):
        node.setdefault("node_id", "node_1")

    def winfo_exists(self):
        return False

    def update_idletasks(self):
        pass

    def winfo_width(self):
        return 800

    def winfo_height(self):
        return 600

    def winfo_reqwidth(self):
        return 800

    def winfo_reqheight(self):
        return 600

    def winfo_screenwidth(self):
        return 1200

    def winfo_screenheight(self):
        return 900

    def geometry(self, value):
        self.last_geometry = value

    def deiconify(self):
        self.deiconified = True

    def lift(self):
        self.lifted = True

    def focus_set(self):
        self.focused = True


class WorkflowAppSupportMixinTests(unittest.TestCase):
    def test_snapshot_and_db_path_helpers(self):
        with tempfile.TemporaryDirectory(dir=os.getcwd()) as tmp:
            window = FakeWindow(tmp)
            snapshot = window.build_workflow_task_snapshot("preview_to", stop_index=3, execute_actions=False)

        self.assertEqual(snapshot["app_dir"], tmp)
        self.assertEqual(snapshot["db_path"], os.path.join(tmp, "demo.db"))
        self.assertEqual(snapshot["workflow_name"], "结果")
        self.assertEqual(snapshot["workflow_plan"]["template_type"], "workflow_plan")
        self.assertEqual(snapshot["workflow_plan"]["nodes"][0]["node_type_id"], "core.replace")
        self.assertEqual(snapshot["workflow_plan"]["headers"], ["A"])
        self.assertEqual(window.get_workflow_db_path({"workflow_snapshot": {"db_path": "x"}}), "x")
        self.assertEqual(window.get_sqlite_table_names(), [])

    def test_log_dir_and_error_log(self):
        with tempfile.TemporaryDirectory(dir=os.getcwd()) as tmp:
            window = FakeWindow(tmp)
            path = window.write_workflow_error_log("mode", "boom", "trace", logs=["a"], snapshot={"nodes": [1]})
            self.assertTrue(path.endswith(".log"))
            self.assertTrue(os.path.exists(path))

    def test_center_geometry(self):
        with tempfile.TemporaryDirectory(dir=os.getcwd()) as tmp:
            window = FakeWindow(tmp)
            child = FakeWindow(tmp)
            window.center_toplevel(child, window, 400, 300)
            self.assertEqual(child.last_geometry, "400x300+400+300")


if __name__ == "__main__":
    unittest.main()
