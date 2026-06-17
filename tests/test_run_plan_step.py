# -*- coding: utf-8 -*-
import unittest

from workflow.run_plan_step import (
    begin_node_execution,
    build_node_run_log,
    emit_node_done,
    emit_node_error,
    emit_node_start,
    finish_node_execution,
    get_current_table_manager,
    handle_node_execution_error,
    prepare_node_execution,
    resolve_next_pc,
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

    def test_prepare_and_begin_node_execution(self):
        events = []
        calls = []

        class Window:
            def check_current_table_permission(self, context, headers, write=False, operation=""):
                calls.append((tuple(headers), write, operation))
                return {"write": write, "operation": operation}

        context = {}
        node = {"type": "新建列", "config": {"name": "B"}, "node_id": "n1"}

        node_type, config = prepare_node_execution(context, node, 0, 2, 1, events.append)
        before_shape, manager = begin_node_execution(Window(), context, ["A"], [["a"], ["b"]], node_type)

        self.assertEqual(node_type, "新建列")
        self.assertEqual(config, {"name": "B"})
        self.assertEqual(context["current_node_info"]["node_id"], "n1")
        self.assertEqual(events[0]["type"], "node_start")
        self.assertEqual(before_shape, (2, 1))
        self.assertTrue(manager["write"])
        self.assertEqual(calls[-1], (("A",), True, "write_current_table"))

    def test_resolve_next_pc_allows_jump_to_end_and_rejects_out_of_bounds(self):
        self.assertEqual(resolve_next_pc(2, None, 5), 3)
        self.assertEqual(resolve_next_pc(2, 5, 5), 5)
        with self.assertRaisesRegex(RuntimeError, "循环跳转目标越界：-1"):
            resolve_next_pc(2, -1, 5)
        with self.assertRaisesRegex(RuntimeError, "循环跳转目标越界：6"):
            resolve_next_pc(2, 6, 5)

    def test_finish_node_execution_logs_progress_and_resolves_jump(self):
        calls = []
        events = []

        class Window:
            def log_current_table_transform(self, manager, before_shape, headers, rows, node_type=""):
                calls.append((manager, before_shape, list(headers), [list(row) for row in rows], node_type))

        logs = []
        next_pc, should_stop = finish_node_execution(
            Window(),
            logs,
            {"manager": "current"},
            (2, 1),
            1,
            "新建列",
            {},
            ["A", "B"],
            [["a", "b"]],
            "OK",
            4,
            end=5,
            node_total=6,
            steps=3,
            progress_callback=events.append,
        )

        self.assertEqual(next_pc, 4)
        self.assertFalse(should_stop)
        self.assertEqual(calls[0][1], (2, 1))
        self.assertEqual(logs, ["2.新建列 2×1→1×2 OK"])
        self.assertEqual(events[0]["type"], "node_done")

    def test_finish_node_execution_can_suppress_jump_at_stop(self):
        class Window:
            def log_current_table_transform(self, manager, before_shape, headers, rows, node_type=""):
                pass

        next_pc, should_stop = finish_node_execution(
            Window(),
            [],
            {},
            (1, 1),
            3,
            "循环判断回跳",
            {},
            ["A"],
            [["a"]],
            "OK",
            1,
            end=3,
            node_total=5,
            steps=4,
            progress_callback=None,
            suppress_jump_at_stop=True,
        )

        self.assertEqual(next_pc, 4)
        self.assertFalse(should_stop)

    def test_finish_node_execution_stops_after_save(self):
        class Window:
            def log_current_table_transform(self, manager, before_shape, headers, rows, node_type=""):
                pass

        logs = []
        next_pc, should_stop = finish_node_execution(
            Window(),
            logs,
            {},
            (1, 1),
            0,
            "保存中转数据",
            {"stop_after_save": True},
            ["A"],
            [["a"]],
            "保存完成",
            None,
            end=3,
            node_total=4,
            steps=1,
            progress_callback=None,
        )

        self.assertIsNone(next_pc)
        self.assertTrue(should_stop)
        self.assertIn("保存后停止", logs[-1])

    def test_handle_node_execution_error_returns_next_pc_or_raises(self):
        events = []
        logs = []

        next_pc = handle_node_execution_error(
            events.append,
            logs,
            2,
            5,
            "新建列",
            ValueError("bad"),
            raise_error=False,
        )

        self.assertEqual(next_pc, 3)
        self.assertEqual(events[0]["type"], "node_error")
        self.assertEqual(logs, ["失败 3.新建列：bad"])
        with self.assertRaisesRegex(RuntimeError, "第 3 个节点【新建列】执行失败：bad"):
            handle_node_execution_error(None, [], 2, 5, "新建列", ValueError("bad"), raise_error=True)


if __name__ == "__main__":
    unittest.main()
