# -*- coding: utf-8 -*-
import unittest
import types

from workflow.run_plan_context import build_run_plan_initial_state


class RunPlanContextTests(unittest.TestCase):
    def make_window(self):
        window = types.SimpleNamespace()
        window.nodes = [{"type": "app_node"}]
        window.app = types.SimpleNamespace(headers=["app_h"], rows=[["app_r"]])
        window.normalize_table_access_policy = lambda: {"source": "window"}
        window.collect_jump_anchors = lambda nodes=None: {"nodes": nodes, "by_id": {}}
        return window

    def test_snapshot_supplies_nodes_headers_rows_and_policy(self):
        window = self.make_window()
        snapshot = {
            "nodes": [{"type": "snap_node"}],
            "headers": ["snap_h"],
            "rows": [["snap_r"]],
            "table_access_policy": {"raw": True},
        }
        state = build_run_plan_initial_state(
            window,
            workflow_snapshot=snapshot,
            normalize_policy=lambda value: {"normalized": value},
        )

        self.assertIs(state["node_list"], snapshot["nodes"])
        self.assertEqual(state["headers"], ["snap_h"])
        self.assertEqual(state["rows"], [["snap_r"]])
        self.assertEqual(state["context"]["table_access_policy"], {"normalized": {"raw": True}})
        self.assertIs(state["context"]["workflow_snapshot"], snapshot)
        self.assertEqual(state["end"], 0)
        self.assertEqual(state["max_steps"], 2000)
        self.assertEqual(state["anchors_info"]["nodes"], snapshot["nodes"])

    def test_initial_inputs_override_snapshot_and_context_is_reused(self):
        window = self.make_window()
        context = {"transit_tables": {"old": {}}, "table_access_policy": {"keep": True}}
        progress = object()
        cancel = object()
        snapshot = {"headers": ["snap_h"], "rows": [["snap_r"]]}

        state = build_run_plan_initial_state(
            window,
            stop_index=7,
            start_index=3,
            initial_headers=["init_h"],
            initial_rows=[["init_r"]],
            initial_context=context,
            progress_callback=progress,
            cancel_event=cancel,
            workflow_snapshot=snapshot,
            normalize_policy=lambda value: value,
        )

        self.assertIs(state["context"], context)
        self.assertEqual(state["headers"], ["init_h"])
        self.assertEqual(state["rows"], [["init_r"]])
        self.assertIn("loop_states", context)
        self.assertIn("condition_flags", context)
        self.assertEqual(context["table_access_policy"], {"keep": True})
        self.assertIs(context["progress_callback"], progress)
        self.assertIs(context["cancel_event"], cancel)
        self.assertEqual(state["end"], 7)
        self.assertEqual(state["pc"], 3)


if __name__ == "__main__":
    unittest.main()
