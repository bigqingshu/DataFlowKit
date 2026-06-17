# -*- coding: utf-8 -*-
import unittest

from workflow.run_plan_step import (
    build_node_run_log,
    emit_node_done,
    emit_node_error,
    emit_node_start,
    get_current_table_manager,
    set_current_node_info,
)


class RunPlanStepTests(unittest.TestCase):
    def test_set_current_node_info_copies_table_access(self):
        context = {}
        node = {
            "node_id": "n1",
            "name": "节点",
            "table_access": {"current_table": {"fields": ["A"]}},
        }

        info = set_current_node_info(context, node, "新建列", 2)
        node["table_access"]["current_table"]["fields"].append("B")

        self.assertEqual(info["node_id"], "n1")
        self.assertEqual(info["node_index"], 2)
        self.assertEqual(info["table_access"]["current_table"]["fields"], ["A"])
        self.assertIs(context["current_node_info"], info)

    def test_progress_payload_helpers(self):
        events = []

        start = emit_node_start(events.append, 0, 3, 1, "新建列")
        done = emit_node_done(events.append, 0, 3, 1, "新建列", ["A", "B"], [["a", "b"]])
        error = emit_node_error(events.append, 1, 3, "删除行", RuntimeError("bad"))

        self.assertEqual([event["type"] for event in events], ["node_start", "node_done", "node_error"])
        self.assertEqual(start["message"], "开始执行节点 1.新建列")
        self.assertEqual(done["rows"], 1)
        self.assertEqual(done["cols"], 2)
        self.assertIn("执行失败：bad", error["message"])
        self.assertIsNone(emit_node_start(None, 0, 1, 1, "x"))

    def test_get_current_table_manager_uses_jump_or_current_permissions(self):
        calls = []

        class Window:
            def get_table_manager(self, context, node_type=""):
                calls.append(("manager", node_type))
                return {"kind": "manager", "node_type": node_type}

            def check_current_table_permission(self, context, headers, write=False, operation=""):
                calls.append(("check", tuple(headers), write, operation))
                return {"kind": "check", "write": write, "operation": operation}

        window = Window()

        jump_manager = get_current_table_manager(window, {}, ["A"], "无条件跳转节点")
        condition_manager = get_current_table_manager(window, {}, ["A"], "条件判断节点")
        write_manager = get_current_table_manager(window, {}, ["A"], "新建列")

        self.assertEqual(jump_manager, {"kind": "manager", "node_type": "无条件跳转节点"})
        self.assertEqual(condition_manager["operation"], "read_current_table")
        self.assertFalse(condition_manager["write"])
        self.assertEqual(write_manager["operation"], "write_current_table")
        self.assertTrue(write_manager["write"])
        self.assertEqual(calls[0], ("manager", "无条件跳转节点"))

    def test_build_node_run_log(self):
        self.assertEqual(
            build_node_run_log(1, "新建列", (2, 1), ["A", "B"], [["a", "b"]], "OK"),
            "2.新建列 2×1→1×2 OK",
        )


if __name__ == "__main__":
    unittest.main()
