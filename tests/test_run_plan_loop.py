# -*- coding: utf-8 -*-
import unittest

from workflow.run_plan_loop import (
    CANCELLED_RUN_LOG,
    MAX_STEPS_ERROR,
    build_run_plan_result,
    advance_run_plan_step,
    disabled_node_next_pc,
    execute_run_plan_loop,
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

    def test_build_run_plan_result_respects_return_context(self):
        base = build_run_plan_result(["A"], [["a"]], ["log"], {"ctx": 1}, return_context=False)
        with_ctx = build_run_plan_result(["A"], [["a"]], ["log"], {"ctx": 1}, return_context=True)

        self.assertEqual(base, (["A"], [["a"]], ["log"]))
        self.assertEqual(with_ctx, (["A"], [["a"]], ["log"], {"ctx": 1}))

    def test_execute_run_plan_loop_skips_disabled_and_stops_when_step_requests(self):
        calls = []

        class Window:
            def ensure_node_identity(self, node):
                calls.append(("identity", node["type"]))

            def refresh_node_table_access(self, node):
                calls.append(("access", node["type"]))

        nodes = [
            {"type": "禁用节点", "enabled": False},
            {"type": "执行节点", "config": {}},
            {"type": "停止节点", "config": {}},
        ]
        initial_state = {
            "node_list": nodes,
            "headers": ["A"],
            "rows": [["a"]],
            "logs": [],
            "context": {},
            "end": 2,
            "pc": 0,
            "steps": 0,
            "max_steps": 10,
            "anchors_info": {"all": []},
        }

        def step_executor(window, headers, rows, logs, context, node, idx, end, node_total, steps, **kwargs):
            calls.append(("step", idx, steps, kwargs["anchors_info"], kwargs["node_list"]))
            logs.append(f"ran {idx}")
            return list(headers) + [node["type"]], [list(rows[0]) + [str(idx)]], idx + 1, idx == 1

        result = execute_run_plan_loop(
            Window(),
            initial_state,
            execute_actions=True,
            progress_callback=object(),
            cancel_event=None,
            suppress_jump_at_stop=True,
            raise_error=True,
            step_executor=step_executor,
        )

        self.assertEqual(result["headers"], ["A", "执行节点"])
        self.assertEqual(result["rows"], [["a", "1"]])
        self.assertEqual(result["logs"], ["跳过 1.禁用节点", "ran 1"])
        self.assertEqual(result["pc"], 2)
        self.assertEqual(result["steps"], 2)
        self.assertIn(("identity", "禁用节点"), calls)
        self.assertIn(("step", 1, 2, {"all": []}, nodes), calls)


if __name__ == "__main__":
    unittest.main()
