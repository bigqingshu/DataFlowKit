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

    def apply_plan_command(self, plan, command, preview_headers=None, table_names=None, table_columns=None):
        return self.engine.apply_plan_command(
            copy.deepcopy(plan),
            command,
            preview_headers=preview_headers,
            table_names=table_names,
            table_columns=table_columns,
        )

    def validate_plan(self, plan):
        return self.engine.validate_plan(copy.deepcopy(plan))

    def list_plan_templates(self, plan_dir):
        return self.engine.list_plan_templates(plan_dir)

    def load_plan_template(self, path, *, migrate=True):
        return self.engine.load_plan_template(path, migrate=migrate)

    def save_plan_template(
        self,
        path,
        plan,
        *,
        headers=None,
        rows=None,
        output_mode=None,
        output_table=None,
        backup_before_overwrite=None,
        db_path=None,
        output_path=None,
        migrate=True,
    ):
        return self.engine.save_plan_template(
            path,
            copy.deepcopy(plan),
            headers=headers,
            rows=rows,
            output_mode=output_mode,
            output_table=output_table,
            backup_before_overwrite=backup_before_overwrite,
            db_path=db_path,
            output_path=output_path,
            migrate=migrate,
        )

    def validate_plan_template(self, plan):
        return self.engine.validate_plan_template(copy.deepcopy(plan))

    def start_job(self, job_action, plan, input_table=None, **options):
        payload = {
            "job_action": job_action,
            "plan": copy.deepcopy(plan),
            "input_data": input_table,
        }
        payload.update(options)
        return self.engine.start_job(job_action, payload)

    def get_job_status(self, job_id, *, include_result=True):
        return self.engine.get_job_status(job_id, include_result=include_result)

    def get_job_events(self, job_id, *, since=0):
        return self.engine.get_job_events(job_id, since=since)

    def cancel_job(self, job_id):
        return self.engine.cancel_job(job_id)

    def list_output_modes(self):
        return self.engine.list_output_modes()

    def apply_output(
        self,
        *,
        headers=None,
        rows=None,
        logs=None,
        output_mode=None,
        output_table=None,
        backup_before_overwrite=None,
        db_path=None,
        output_path=None,
    ):
        return self.engine.apply_output(
            headers=headers,
            rows=rows,
            logs=logs,
            output_mode=output_mode,
            output_table=output_table,
            backup_before_overwrite=backup_before_overwrite,
            db_path=db_path,
            output_path=output_path,
        )

    def list_tables(self, *, db_path=None):
        return self.engine.list_tables(db_path=db_path)

    def load_table(self, source=None, *, db_path=None, table_name=None, path=None, limit=None, offset=0):
        return self.engine.load_table(
            source,
            db_path=db_path,
            table_name=table_name,
            path=path,
            limit=limit,
            offset=offset,
        )

    def get_table_page(self, table, *, limit=None, offset=0, source=None):
        return self.engine.get_table_page(table, limit=limit, offset=offset, source=source)

    def validate_config(self, node, preview_headers=None, table_names=None, table_columns=None):
        return self.engine.validate_config(
            copy.deepcopy(node),
            preview_headers=preview_headers,
            table_names=table_names,
            table_columns=table_columns,
        )

    def validate_plan_configs(self, plan, preview_headers=None, table_names=None, table_columns=None):
        return self.engine.validate_plan_configs(
            copy.deepcopy(plan),
            preview_headers=preview_headers,
            table_names=table_names,
            table_columns=table_columns,
        )

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
