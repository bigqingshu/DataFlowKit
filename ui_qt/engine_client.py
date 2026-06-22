# -*- coding: utf-8 -*-
"""Qt-side client wrapper for the headless workflow engine."""

from __future__ import annotations

import copy

from engine import HeadlessWorkflowEngine, PlanValidationError


SAMPLE_HEADERS = ["source_file", "sheet_name", "row_index", "text"]
SAMPLE_ROWS = [
    ["demo.xlsx", "Sheet1", 1, "alpha"],
    ["demo.xlsx", "Sheet1", 2, "beta"],
    ["report.docx", "Paragraph", 1, "gamma"],
]

SAMPLE_PLAN = {
    "template_type": "workflow_plan",
    "version": "1.0",
    "plan_name": "Qt6 示例计划",
    "nodes": [
        {
            "node_id": "node_qt_sample_1",
            "node_type_id": "core.new_columns",
            "node_version": "1.0.0",
            "name": "添加状态列",
            "enabled": True,
            "config": {
                "columns_text": "status=ready",
                "value_mode": "按列配置值",
                "conflict_mode": "自动改名",
                "strip_column_name": True,
                "allow_empty_name": False,
            },
            "ui": {},
            "extensions": {},
        }
    ],
    "headers": SAMPLE_HEADERS,
    "rows": SAMPLE_ROWS,
    "metadata": {},
    "ui": {},
    "extensions": {},
}


class QtHeadlessEngineClient:
    """Small protocol-oriented facade used by the Qt shell."""

    def __init__(self, engine=None):
        self.engine = engine or HeadlessWorkflowEngine()

    def list_node_catalog(self, include_unsupported=True):
        return self.engine.list_node_catalog(include_unsupported=include_unsupported)

    def list_node_ui_schemas(self, include_unsupported=True, preview_headers=None):
        return self.engine.list_node_ui_schemas(
            include_unsupported=include_unsupported,
            preview_headers=preview_headers,
        )

    def get_node_ui_schema(self, node_type_id, preview_headers=None):
        return self.engine.get_node_ui_schema(
            node_type_id,
            preview_headers=preview_headers,
        )

    def make_default_node(self, node_type_id, preview_headers=None, *, include_legacy_type=False):
        return self.engine.make_default_node(
            node_type_id,
            preview_headers=preview_headers,
            include_legacy_type=include_legacy_type,
        )

    def validate_plan(self, plan):
        return self.engine.validate_plan(copy.deepcopy(plan))

    def preview_plan(self, plan, input_table=None):
        return self.engine.preview_plan(copy.deepcopy(plan), input_table=input_table)

    def run_plan(self, plan, input_table=None):
        return self.engine.run_plan(copy.deepcopy(plan), input_table=input_table, execute_actions=False)

    def validate_and_preview(self, plan, input_table=None):
        validation = self.validate_plan(plan)
        if not validation.get("ok"):
            return validation, None
        try:
            return validation, self.preview_plan(plan, input_table=input_table)
        except PlanValidationError as exc:
            return {
                "ok": False,
                "issues": list(exc.issues),
                "node_count": len((plan or {}).get("nodes", [])) if isinstance(plan, dict) else 0,
            }, None
