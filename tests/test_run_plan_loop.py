# -*- coding: utf-8 -*-
import unittest

from workflow.run_plan_loop import (
    CANCELLED_RUN_LOG,
    MAX_STEPS_ERROR,
    advance_run_plan_step,
    disabled_node_next_pc,
    is_run_cancelled,
    prepare_run_plan_node,
    should_continue_run_plan,
    stop_if_cancelled,
)


class RunPlanLoopTests(unittest.TestCase):
    def test_should_continue_run_plan_checks_pc_and_stop_bound(self):
        self.assertTrue(should_continue_run_plan(0, 3, 2))
        self.assertTrue(should_continue_run_plan(2, 3, 2))
        self.assertFalse(should_continue_run_plan(3, 3, 3))
        self.assertFalse(should_continue_run_plan(2, 5, 1))

    def test_stop_if_cancelled_appends_log_once_per_call(self):
        class Event:
            def is_set(self):
                return True

        logs = []

        self.assertFalse(is_run_cancelled(None))
        self.assertTrue(stop_if_cancelled(Event(), logs))
        self.assertEqual(logs, [CANCELLED_RUN_LOG])
        self.assertFalse(stop_if_cancelled(None, logs))
        self.assertEqual(logs, [CANCELLED_RUN_LOG])

    def test_advance_run_plan_step_returns_next_step_or_raises(self):
        self.assertEqual(advance_run_plan_step(0, 2), 1)
        self.assertEqual(advance_run_plan_step(1, 2), 2)
        with self.assertRaisesRegex(RuntimeError, MAX_STEPS_ERROR):
            advance_run_plan_step(2, 2)

    def test_prepare_run_plan_node_refreshes_identity_and_table_access(self):
        calls = []

        class Window:
            def ensure_node_identity(self, node):
                calls.append(("identity", node["type"]))
                node["node_id"] = "n1"

            def refresh_node_table_access(self, node):
                calls.append(("access", node["type"]))
                node["table_access"] = {"current_table": {}}

        node_list = [{"type": "新建列"}]
        idx, node = prepare_run_plan_node(Window(), node_list, 0)

        self.assertEqual(idx, 0)
        self.assertIs(node, node_list[0])
        self.assertEqual(node["node_id"], "n1")
        self.assertEqual(calls, [("identity", "新建列"), ("access", "新建列")])

    def test_disabled_node_next_pc_appends_skip_log(self):
        logs = []

        self.assertIsNone(disabled_node_next_pc({"type": "新建列", "enabled": True}, 1, logs))
        self.assertEqual(logs, [])
        self.assertEqual(disabled_node_next_pc({"type": "删除行", "enabled": False}, 2, logs), 3)
        self.assertEqual(logs, ["跳过 3.删除行"])


if __name__ == "__main__":
    unittest.main()
