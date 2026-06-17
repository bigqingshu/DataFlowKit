# -*- coding: utf-8 -*-
import csv
import os
import tempfile
import types
import unittest

from workflow.file_node_runtime import (
    apply_batch_rename_node_for_window,
    apply_file_list_node_for_window,
)
from workflow.nodes.file_nodes import BATCH_RENAME_LOG_HEADERS


class FileNodeRuntimeTests(unittest.TestCase):
    def test_file_list_runtime_uses_window_app_dir_and_progress(self):
        progress = []

        class Window:
            def __init__(self, app_dir):
                self.app = types.SimpleNamespace(app_dir=app_dir)

            def check_workflow_cancelled(self, context=None):
                return None

            def report_workflow_node_progress(self, context=None, current=None, total=None, message="", node_name=""):
                progress.append((context, current, total, message, node_name))

        with tempfile.TemporaryDirectory() as tmp:
            for index in range(200):
                with open(os.path.join(tmp, f"{index:03d}.txt"), "w", encoding="utf-8") as f:
                    f.write(str(index))

            context = {"progress_callback": lambda item: None}
            headers, rows, message = apply_file_list_node_for_window(
                Window(tmp),
                [],
                [],
                {"recursive": False, "max_files": "200"},
                context=context,
            )

        self.assertEqual(headers[0], "文件名")
        self.assertEqual(len(rows), 200)
        self.assertIn("读取文件列表 200 项", message)
        self.assertTrue(progress)
        self.assertIs(progress[-1][0], context)
        self.assertEqual(progress[-1][1], 200)

    def test_batch_rename_runtime_writes_log_after_execute(self):
        class Window:
            def check_workflow_cancelled(self, context=None):
                return None

            def report_workflow_node_progress(self, context=None, current=None, total=None, message="", node_name=""):
                return None

        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "old.txt")
            log_path = os.path.join(tmp, "rename_log.csv")
            with open(src, "w", encoding="utf-8") as f:
                f.write("old")

            headers, rows, message = apply_batch_rename_node_for_window(
                Window(),
                ["完整路径", "新文件名"],
                [[src, "new.txt"]],
                {"actual_rename": True, "log_path": log_path},
                execute_actions=True,
                context={},
            )

            with open(log_path, "r", encoding="utf-8-sig", newline="") as f:
                log_rows = list(csv.reader(f))

            self.assertEqual(headers, ["完整路径", "新文件名", "新完整路径", "重命名状态"])
            self.assertEqual(rows[0][3], "已重命名")
            self.assertEqual(message, "实际重命名 1 项，跳过/失败 0 项")
            self.assertFalse(os.path.exists(src))
            self.assertTrue(os.path.exists(os.path.join(tmp, "new.txt")))
            self.assertEqual(log_rows[0], BATCH_RENAME_LOG_HEADERS)
            self.assertEqual(log_rows[1][0], "1")
            self.assertEqual(log_rows[1][1], src)


if __name__ == "__main__":
    unittest.main()
