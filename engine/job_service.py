# -*- coding: utf-8 -*-
"""In-process background job service for headless workflow runs."""

from __future__ import annotations

import copy
import threading
import time
import traceback
import uuid


SUPPORTED_JOB_ACTIONS = {"preview_plan", "run_plan"}


class JobService:
    """Run headless workflow actions in background threads and keep events."""

    def __init__(self, engine, *, job_id_factory=None, time_factory=None):
        self.engine = engine
        self.job_id_factory = job_id_factory or (lambda: "job_" + uuid.uuid4().hex)
        self.time_factory = time_factory or time.time
        self._lock = threading.RLock()
        self._jobs = {}

    def start_job(self, action, payload=None):
        action = str(action or "").strip()
        if action not in SUPPORTED_JOB_ACTIONS:
            raise ValueError("job_action 仅支持 preview_plan 或 run_plan。")
        job_id = str(self.job_id_factory())
        cancel_event = threading.Event()
        record = {
            "job_id": job_id,
            "action": action,
            "status": "queued",
            "message": "任务已排队。",
            "created_at": self.time_factory(),
            "updated_at": self.time_factory(),
            "done": False,
            "cancel_requested": False,
            "events": [],
            "result": None,
            "error": None,
            "_cancel_event": cancel_event,
            "_thread": None,
        }
        with self._lock:
            self._jobs[job_id] = record
        thread = threading.Thread(
            target=self._run_job,
            args=(job_id, action, copy.deepcopy(payload or {}), cancel_event),
            daemon=True,
        )
        record["_thread"] = thread
        thread.start()
        return self.get_job_status(job_id, include_result=False)

    def get_job_status(self, job_id, *, include_result=True):
        with self._lock:
            record = self._require_job(job_id)
            return self._snapshot(record, include_result=include_result)

    def get_job_events(self, job_id, *, since=0):
        since = int(since or 0)
        with self._lock:
            record = self._require_job(job_id)
            events = [copy.deepcopy(item) for item in record["events"] if int(item.get("sequence", 0)) > since]
            return {
                "ok": True,
                "job_id": record["job_id"],
                "status": record["status"],
                "events": events,
                "next_sequence": len(record["events"]),
                "done": bool(record["done"]),
            }

    def cancel_job(self, job_id):
        with self._lock:
            record = self._require_job(job_id)
            if record["done"]:
                return {
                    "ok": True,
                    "job_id": record["job_id"],
                    "cancel_requested": bool(record["cancel_requested"]),
                    "status": record["status"],
                    "message": "任务已结束。",
                }
            record["cancel_requested"] = True
            record["updated_at"] = self.time_factory()
            record["_cancel_event"].set()
            self._append_event_locked(record, {
                "type": "job_cancel_requested",
                "message": "已请求取消任务。",
            })
            return {
                "ok": True,
                "job_id": record["job_id"],
                "cancel_requested": True,
                "status": record["status"],
                "message": "已请求取消任务。",
            }

    def _run_job(self, job_id, action, payload, cancel_event):
        with self._lock:
            record = self._require_job(job_id)
            record["status"] = "running"
            record["message"] = "任务运行中。"
            record["updated_at"] = self.time_factory()
            self._append_event_locked(record, {
                "type": "job_started",
                "action": action,
                "message": "任务运行中。",
            })

        try:
            result = self._execute(action, payload, cancel_event, job_id)
            result_payload = _json_safe(result.to_dict(include_context=bool(payload.get("return_context", False))))
            status = "cancelled" if result_payload.get("cancelled") else "succeeded"
            message = "任务已取消。" if status == "cancelled" else "任务完成。"
            with self._lock:
                record = self._require_job(job_id)
                record["status"] = status
                record["message"] = message
                record["done"] = True
                record["result"] = result_payload
                record["updated_at"] = self.time_factory()
                self._append_event_locked(record, {
                    "type": "job_done",
                    "status": status,
                    "message": message,
                })
        except Exception as exc:
            with self._lock:
                record = self._require_job(job_id)
                record["status"] = "failed"
                record["message"] = str(exc)
                record["done"] = True
                record["error"] = {
                    "code": "job_failed",
                    "message": str(exc),
                    "traceback": traceback.format_exc(),
                }
                record["updated_at"] = self.time_factory()
                self._append_event_locked(record, {
                    "type": "job_failed",
                    "message": str(exc),
                })

    def _execute(self, action, payload, cancel_event, job_id):
        progress_callback = lambda event: self._append_event(job_id, event)
        common = {
            "input_table": payload.get("input_data", payload.get("input_table")),
            "stop_index": _optional_int(payload.get("stop_at", payload.get("stop_index"))),
            "start_index": int(payload.get("start_index", 0) or 0),
            "initial_context": payload.get("context"),
            "progress_callback": progress_callback,
            "cancel_event": cancel_event,
            "return_context": bool(payload.get("return_context", False)),
        }
        if action == "preview_plan":
            return self.engine.preview_plan(
                payload.get("plan", {}),
                dry_run=bool(payload.get("dry_run", True)),
                safety_mode=payload.get("safety_mode"),
                **common,
            )
        return self.engine.run_plan(
            payload.get("plan", {}),
            execute_actions=bool(payload.get("execute_actions", True)),
            dry_run=bool(payload.get("dry_run", False)),
            safety_mode=payload.get("safety_mode"),
            **common,
        )

    def _append_event(self, job_id, event):
        with self._lock:
            record = self._require_job(job_id)
            self._append_event_locked(record, event)

    def _append_event_locked(self, record, event):
        payload = _json_safe(event or {})
        payload["job_id"] = record["job_id"]
        payload["sequence"] = len(record["events"]) + 1
        payload.setdefault("timestamp", self.time_factory())
        record["events"].append(payload)
        record["updated_at"] = self.time_factory()

    def _snapshot(self, record, *, include_result=True):
        payload = {
            "ok": True,
            "job_id": record["job_id"],
            "action": record["action"],
            "status": record["status"],
            "message": record["message"],
            "done": bool(record["done"]),
            "cancel_requested": bool(record["cancel_requested"]),
            "event_count": len(record["events"]),
            "created_at": record["created_at"],
            "updated_at": record["updated_at"],
        }
        if include_result and record.get("result") is not None:
            payload["result"] = copy.deepcopy(record["result"])
        if record.get("error") is not None:
            payload["error"] = copy.deepcopy(record["error"])
        return payload

    def _require_job(self, job_id):
        job_id = str(job_id or "")
        if job_id not in self._jobs:
            raise ValueError(f"未知 job_id：{job_id}")
        return self._jobs[job_id]


def _optional_int(value):
    if value is None or value == "":
        return None
    return int(value)


def _json_safe(value):
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)
