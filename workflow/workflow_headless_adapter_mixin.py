# -*- coding: utf-8 -*-
"""Optional Tkinter adapter methods for the headless workflow engine."""

from engine import HeadlessWorkflowEngine, PlanValidationError


class WorkflowHeadlessAdapterMixin:
    """Bridge current Tkinter workflow state to the UI-free engine API.

    The current Tkinter runtime still owns full execution for service-heavy
    nodes.  These helpers expose protocol/headless capabilities without
    replacing the existing buttons or background worker behavior.
    """

    def make_headless_engine(self):
        return HeadlessWorkflowEngine()

    def build_headless_runtime_request(self, action, request_id="", stop_index=None, include_input=True):
        plan = self.build_workflow_protocol_plan(include_input=include_input)
        payload = {"plan": plan}
        if include_input:
            payload["input_data"] = {
                "type": "table",
                "headers": list(self.app.headers),
                "rows": [list(row) for row in self.app.rows],
            }
        if stop_index is not None:
            payload["stop_at"] = int(stop_index)
        return {
            "request_id": str(request_id or ""),
            "api_version": "1.0",
            "action": action,
            "payload": payload,
        }

    def validate_current_plan_for_headless(self, stop_index=None):
        engine = self.make_headless_engine()
        plan = self.build_workflow_protocol_plan(include_input=True)
        return engine.validate_plan(plan, stop_index=stop_index)

    def preview_current_plan_headless(self, stop_index=None, raise_error=False):
        engine = self.make_headless_engine()
        plan = self.build_workflow_protocol_plan(include_input=True)
        try:
            return engine.preview_plan(
                plan,
                stop_index=stop_index,
                input_table={
                    "type": "table",
                    "headers": list(self.app.headers),
                    "rows": [list(row) for row in self.app.rows],
                },
            )
        except PlanValidationError:
            if raise_error:
                raise
            return None
