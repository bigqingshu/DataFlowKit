# -*- coding: utf-8 -*-
import time
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


def wait_for_job(engine, job_id, timeout=2.0):
    deadline = time.time() + timeout
    status = engine.get_job_status(job_id)
    while not status.get("done") and time.time() < deadline:
        time.sleep(0.01)
        status = engine.get_job_status(job_id)
    return status


class JobServiceTests(unittest.TestCase):
    def test_headless_job_service_runs_preview_and_collects_events(self):
        engine = HeadlessWorkflowEngine()
        started = engine.start_job("preview_plan", {
            "plan": {
                "nodes": [
                    {
                        "node_type_id": "core.new_columns",
                        "enabled": True,
                        "config": {"columns_text": "B=b", "value_mode": "按列配置值"},
                    }
                ],
            },
            "input_data": {"type": "table", "headers": ["A"], "rows": [["a"]]},
        })

        status = wait_for_job(engine, started["job_id"])
        events = engine.get_job_events(started["job_id"])
        tail = engine.get_job_events(started["job_id"], since=events["next_sequence"] - 1)

        self.assertEqual(status["status"], "succeeded")
        self.assertTrue(status["done"])
        self.assertEqual(status["result"]["table"]["headers"], ["A", "B"])
        self.assertIn("workflow_start", [item["type"] for item in events["events"]])
        self.assertEqual(events["events"][-1]["type"], "job_done")
        self.assertEqual(tail["events"][0]["type"], "job_done")

    def test_stdio_worker_exposes_job_actions(self):
        worker = StdioWorker()
        started = worker.handle_request(request("start_job", {
            "job_action": "preview_plan",
            "plan": {
                "nodes": [
                    {
                        "node_type_id": "core.new_columns",
                        "enabled": True,
                        "config": {"columns_text": "B=b", "value_mode": "按列配置值"},
                    }
                ],
            },
            "input_data": {"type": "table", "headers": ["A"], "rows": [["a"]]},
        }))
        job_id = started["result"]["job_id"]

        deadline = time.time() + 2.0
        status = worker.handle_request(request("get_job_status", {"job_id": job_id}))
        while not status["result"].get("done") and time.time() < deadline:
            time.sleep(0.01)
            status = worker.handle_request(request("get_job_status", {"job_id": job_id}))
        events = worker.handle_request(request("get_job_events", {"job_id": job_id}))
        cancelled = worker.handle_request(request("cancel_job", {"job_id": job_id}))

        self.assertTrue(started["ok"])
        self.assertEqual(status["result"]["status"], "succeeded")
        self.assertEqual(status["result"]["result"]["table"]["headers"], ["A", "B"])
        self.assertTrue(events["ok"])
        self.assertEqual(events["result"]["events"][-1]["type"], "job_done")
        self.assertTrue(cancelled["ok"])
        self.assertEqual(cancelled["result"]["message"], "任务已结束。")

    def test_stdio_worker_reports_unknown_job_id(self):
        worker = StdioWorker()

        response = worker.handle_request(request("get_job_status", {"job_id": "missing"}))

        self.assertFalse(response["ok"])
        self.assertIn("未知 job_id", response["message"])


if __name__ == "__main__":
    unittest.main()
