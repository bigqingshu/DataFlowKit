# -*- coding: utf-8 -*-
import unittest

from engine.headless import HeadlessWorkflowEngine
from engine.stdio_worker import StdioWorker


def request(action, payload=None, request_id="req1"):
    return {
        "request_id": request_id,
        "api_version": "1.0",
        "action": action,
        "payload": payload or {},
    }


class OutputServiceTests(unittest.TestCase):
    def test_output_service_lists_modes_and_prepares_preview_output(self):
        engine = HeadlessWorkflowEngine()

        modes = engine.list_output_modes()
        output = engine.apply_output(
            headers=["A"],
            rows=[["a"]],
            logs=["done"],
            output_mode="输出到主界面预览区",
        )

        self.assertTrue(modes["ok"])
        self.assertEqual(modes["modes"][0]["mode"], "输出到主界面预览区")
        self.assertTrue(output["ok"])
        self.assertEqual(output["action"]["type"], "update_frontend_table")
        self.assertEqual(output["table"]["headers"], ["A"])
        self.assertEqual(output["logs"], ["done"])

    def test_output_service_blocks_side_effect_modes_without_writer(self):
        engine = HeadlessWorkflowEngine()

        output = engine.apply_output(
            headers=["A"],
            rows=[["a"]],
            output_mode="保存为SQLite新表",
            output_table="结果表",
        )
        missing_target = engine.apply_output(
            headers=["A"],
            rows=[["a"]],
            output_mode="覆盖当前表",
            output_table="",
        )

        self.assertFalse(output["ok"])
        self.assertEqual(output["issues"][0]["code"], "output_writer_not_connected")
        self.assertFalse(missing_target["ok"])
        self.assertEqual(missing_target["issues"][0]["code"], "missing_output_table")

    def test_stdio_worker_exposes_output_actions(self):
        worker = StdioWorker()

        modes = worker.handle_request(request("list_output_modes"))
        output = worker.handle_request(request("apply_output", {
            "headers": ["A"],
            "rows": [["a"]],
            "logs": ["done"],
            "output_mode": "输出到主界面预览区",
        }))

        self.assertTrue(modes["ok"])
        self.assertEqual(modes["result"]["modes"][0]["mode"], "输出到主界面预览区")
        self.assertTrue(output["ok"])
        self.assertTrue(output["result"]["ok"])
        self.assertEqual(output["result"]["table"]["rows"], [["a"]])


if __name__ == "__main__":
    unittest.main()

