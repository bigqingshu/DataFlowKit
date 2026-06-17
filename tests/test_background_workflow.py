# -*- coding: utf-8 -*-
import queue
import unittest
from unittest import mock

from workflow.background_workflow import (
    background_workflow_worker,
    finish_execute_plan_output,
    handle_background_workflow_message,
    poll_background_workflow_queue,
    start_background_workflow,
)


class FakeVar:
    def __init__(self, value=None):
        self.value = value

    def set(self, value):
        self.value = value

    def get(self):
        return self.value


class FakeCancel:
    def __init__(self, cancelled=False):
        self.cancelled = cancelled

    def is_set(self):
        return self.cancelled


class FakeApp:
    def __init__(self):
        self.headers = []
        self.rows = []
        self.raw_data = "raw"
        self.refresh_count = 0
        self.info_var = FakeVar()

    def refresh_tree(self):
        self.refresh_count += 1

    def refresh_table_list(self):
        self.refresh_count += 1


class FakeTkRoot:
    def __init__(self):
        self.after_calls = []

    def after(self, delay_ms, callback):
        self.after_calls.append((delay_ms, callback))


class FakeThread:
    instances = []

    def __init__(self, target=None, args=(), daemon=False):
        self.target = target
        self.args = args
        self.daemon = daemon
        self.started = False
        self.alive = True
        FakeThread.instances.append(self)

    def start(self):
        self.started = True

    def is_alive(self):
        return self.alive


class BackgroundWorkflowTests(unittest.TestCase):
    def make_window(self):
        class Window:
            pass

        window = Window()
        window.window = FakeTkRoot()
        window.nodes = [{"type": "节点"}]
        window.workflow_worker_queue = queue.Queue()
        window.workflow_worker_thread = None
        window.workflow_worker_cancel = FakeCancel(False)
        window.workflow_worker_running = False
        window.workflow_progress_var = FakeVar()
        window.node_progress_var = FakeVar()
        window.workflow_progress_text = FakeVar()
        window.node_progress_text = FakeVar()
        window.worker_status_text = FakeVar()
        window.status_var = FakeVar()
        window.app = FakeApp()
        window.current_transit_tables = {}
        window.last_workflow_context = None
        window.last_table_access_logs = []
        window.state_calls = []
        window.preview_result = None
        window.output_mode = "输出到主界面预览区"
        window.output_table = "result"
        window.logs_text = ""
        window.workflow_worker_cancel = FakeCancel(False)
        window.is_background_workflow_running = lambda: bool(
            window.workflow_worker_running
            and window.workflow_worker_thread
            and window.workflow_worker_thread.is_alive()
        )
        window.confirm_jump_precheck = mock.Mock(return_value=True)
        window.confirm_table_access_precheck = mock.Mock(return_value=True)
        window.build_workflow_task_snapshot = mock.Mock(return_value={"snapshot": True})
        window._set_background_workflow_state = lambda running, title="": (
            setattr(window, "workflow_worker_running", bool(running)),
            window.state_calls.append((running, title)),
        )
        window.format_logs = lambda logs: " | " + ",".join(logs) if logs else ""
        window.set_plan_preview_result = lambda headers, rows, display=True: setattr(window, "preview_result", (headers, rows, display))
        window.get_workflow_output_mode = lambda context=None: window.output_mode
        window.get_workflow_output_table = lambda context=None: window.output_table
        window.get_workflow_backup_before_overwrite = lambda context=None: True
        window.save_result_to_sqlite = lambda headers, rows, table, overwrite=False, backup=True, context=None: f"{table}_saved"
        window.export_result_to_xlsx = lambda headers, rows, path: setattr(window, "exported", (headers, rows, path))
        window._finish_execute_plan_output = lambda headers, rows, logs, context=None, snapshot=None: finish_execute_plan_output(
            window, headers, rows, logs, context=context, snapshot=snapshot
        )
        window._background_progress_callback = lambda message: window.workflow_worker_queue.put(message)
        window._background_workflow_worker = mock.Mock()
        window._poll_background_workflow_queue = mock.Mock()
        window._handle_background_workflow_message = mock.Mock()
        window.write_workflow_error_log = lambda mode, message, traceback_text="", logs=None, snapshot=None: "error.log"
        return window

    def setUp(self):
        FakeThread.instances = []

    def test_start_background_workflow_creates_worker_and_schedules_poll(self):
        window = self.make_window()

        with mock.patch("workflow.background_workflow.threading.Thread", FakeThread):
            start_background_workflow(window, "preview_full", "预览完整计划")

        self.assertEqual(window.state_calls, [(True, "预览完整计划")])
        self.assertIsInstance(window.workflow_worker_queue, queue.Queue)
        self.assertFalse(window.workflow_worker_cancel.is_set())
        self.assertEqual(len(FakeThread.instances), 1)
        thread = FakeThread.instances[0]
        self.assertIs(thread.target, window._background_workflow_worker)
        self.assertEqual(thread.args, ("preview_full", None, False, {"snapshot": True}))
        self.assertTrue(thread.daemon)
        self.assertTrue(thread.started)
        self.assertEqual(window.window.after_calls, [(80, window._poll_background_workflow_queue)])

    def test_start_background_workflow_aborts_when_jump_precheck_declines(self):
        window = self.make_window()
        window.confirm_jump_precheck.return_value = False

        with mock.patch("workflow.background_workflow.threading.Thread", FakeThread):
            start_background_workflow(window, "execute_plan", "执行计划", execute_actions=True)

        self.assertEqual(window.status_var.get(), "工作流已取消：跳转校验未继续。")
        self.assertEqual(window.state_calls, [])
        self.assertEqual(FakeThread.instances, [])
        window.confirm_table_access_precheck.assert_not_called()

    def test_poll_background_workflow_queue_drains_messages_and_reschedules_when_running(self):
        window = self.make_window()
        window.workflow_worker_running = True
        window.workflow_worker_thread = FakeThread(target=window._background_workflow_worker)
        window.workflow_worker_queue.put({"type": "workflow_start"})
        window.workflow_worker_queue.put({"type": "node_done"})

        poll_background_workflow_queue(window)

        self.assertEqual(
            [call.args[0] for call in window._handle_background_workflow_message.call_args_list],
            [{"type": "workflow_start"}, {"type": "node_done"}],
        )
        self.assertEqual(window.window.after_calls, [(80, window._poll_background_workflow_queue)])

    def test_poll_background_workflow_queue_schedules_final_drain_when_thread_finished(self):
        window = self.make_window()
        window.workflow_worker_running = True
        thread = FakeThread(target=window._background_workflow_worker)
        thread.alive = False
        window.workflow_worker_thread = thread

        poll_background_workflow_queue(window)

        self.assertFalse(window.workflow_worker_running)
        self.assertEqual(window.window.after_calls, [(120, window._poll_background_workflow_queue)])

    def test_worker_preview_to_emits_done_message(self):
        window = self.make_window()
        calls = []

        def run_plan(**kwargs):
            calls.append(kwargs)
            return ["A"], [["a"]], ["log"], {"transit_tables": {"t": {}}}

        window.run_plan = run_plan

        background_workflow_worker(window, "preview_to", stop_index=2, snapshot={"nodes": []})

        messages = []
        while not window.workflow_worker_queue.empty():
            messages.append(window.workflow_worker_queue.get())

        self.assertEqual(messages[0]["type"], "workflow_start")
        self.assertEqual(messages[-1]["type"], "workflow_done")
        self.assertEqual(messages[-1]["prefix"], "已预览到节点 3")
        self.assertEqual(calls[0]["stop_index"], 2)
        self.assertTrue(calls[0]["initial_context"]["allow_selected_columns_write_in_preview"])

    def test_handle_progress_and_done_messages_updates_window_state(self):
        window = self.make_window()
        context = {
            "transit_tables": {"temp": {}},
            "table_access_logs": ["audit"],
            "ui_refresh_requests": ["table_list"],
        }

        handle_background_workflow_message(window, {
            "type": "node_progress",
            "current": 1,
            "total": 4,
            "node_name": "节点A",
            "message": "处理中",
        })
        self.assertEqual(window.node_progress_var.get(), 25)
        self.assertEqual(window.worker_status_text.get(), "处理中")

        handle_background_workflow_message(window, {
            "type": "workflow_done",
            "mode": "preview_full",
            "prefix": "完成",
            "headers": ["A"],
            "rows": [["a"]],
            "logs": ["log"],
            "context": context,
        })

        self.assertEqual(window.current_transit_tables, {"temp": {}})
        self.assertEqual(window.last_table_access_logs, ["audit"])
        self.assertEqual(window.preview_result, (["A"], [["a"]], True))
        self.assertEqual(window.workflow_progress_var.get(), 100)
        self.assertIn("完成：1 行 × 1 列", window.status_var.get())

    def test_finish_execute_plan_output_to_main_preview(self):
        window = self.make_window()

        finish_execute_plan_output(window, ["A"], [["a"]], ["log"], context={}, snapshot={})

        self.assertEqual(window.app.headers, ["A"])
        self.assertEqual(window.app.rows, [["a"]])
        self.assertEqual(window.app.raw_data, "")
        self.assertEqual(window.preview_result, (["A"], [["a"]], True))
        self.assertIn("已输出到主界面", window.status_var.get())


if __name__ == "__main__":
    unittest.main()
