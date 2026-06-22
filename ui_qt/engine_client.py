# -*- coding: utf-8 -*-
"""Qt-side client wrapper for the headless workflow engine."""

from __future__ import annotations

import copy

from engine import HeadlessWorkflowEngine, PlanValidationError, WorkflowFacade


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
        self.facade = WorkflowFacade(self.engine)

    def list_node_catalog(self, include_unsupported=True):
        return self.engine.list_node_catalog(include_unsupported=include_unsupported)

    def list_node_ui_schemas(self, include_unsupported=True, preview_headers=None):
        return self.engine.list_node_ui_schemas(
            include_unsupported=include_unsupported,
            preview_headers=preview_headers,
        )

    def list_node_ui_catalog(self, *, include_unsupported=True, preview_headers=None, table_names=None, table_columns=None):
        return self.facade.list_node_ui_catalog(
            include_unsupported=include_unsupported,
            preview_headers=preview_headers,
            table_names=table_names,
            table_columns=table_columns,
        )

    def build_workflow_panel_state(self, **kwargs):
        return self.facade.build_workflow_panel_state(**kwargs)

    def describe_workflow_actions(self, **kwargs):
        return self.facade.describe_workflow_actions(**kwargs)

    def build_job_progress_state(self, **kwargs):
        return self.facade.build_job_progress_state(**kwargs)

    def build_user_feedback(self, **kwargs):
        return self.facade.build_user_feedback(**kwargs)

    def describe_selection_feedback(self, **kwargs):
        return self.facade.describe_selection_feedback(**kwargs)

    def describe_job_run_conflict(self, **kwargs):
        return self.facade.describe_job_run_conflict(**kwargs)

    def describe_job_start_failure(self, **kwargs):
        return self.facade.describe_job_start_failure(**kwargs)

    def describe_validation_feedback(self, combined):
        return self.facade.describe_validation_feedback(copy.deepcopy(combined))

    def describe_node_detail(self, node_type_id, *, preview_headers=None):
        return self.facade.describe_node_detail(node_type_id, preview_headers=preview_headers)

    def plan_status_text(self, plan=None, *, current_plan_path=None):
        return self.facade.plan_status_text(plan, current_plan_path=current_plan_path)

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
        return self.facade.apply_plan_command(
            copy.deepcopy(plan),
            command,
            preview_headers=preview_headers,
            table_names=table_names,
            table_columns=table_columns,
        )

    def validate_plan(self, plan):
        return self.engine.validate_plan(copy.deepcopy(plan))

    def list_plan_templates(self, plan_dir):
        return self.facade.list_plan_templates(plan_dir)

    def load_plan_template(self, path, *, migrate=True):
        return self.facade.load_plan_template(path, migrate=migrate)

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
        return self.facade.save_plan_template(
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
        return self.facade.validate_plan_template(copy.deepcopy(plan))

    def import_table_file(self, path):
        return self.facade.import_table_file(path)

    def start_job(self, job_action, plan, input_table=None, **options):
        return self.facade.start_workflow_job(
            job_action,
            copy.deepcopy(plan),
            input_table=input_table,
            **options,
        )

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

    def build_output_settings(self, payload=None, **fallbacks):
        return self.facade.build_output_settings(payload, **fallbacks)

    def describe_output_form(self, payload=None, **fallbacks):
        return self.facade.describe_output_form(payload, **fallbacks)

    def list_preview_sources(self, **kwargs):
        return self.facade.list_preview_sources(**kwargs)

    def load_preview_source(self, source, **kwargs):
        return self.facade.load_preview_source(copy.deepcopy(source), **kwargs)

    def validate_workflow_request(self, plan, **options):
        return self.facade.validate_workflow_request(copy.deepcopy(plan), **options)

    def finalize_job_result(self, status, **options):
        return self.facade.finalize_job_result(copy.deepcopy(status), **options)

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

    def create_table_handle(self, table_or_source=None, **kwargs):
        return self.engine.create_table_handle(copy.deepcopy(table_or_source), **kwargs)

    def get_table_handle_page(self, handle, *, limit=None, offset=0):
        return self.engine.get_table_handle_page(handle, limit=limit, offset=offset)

    def list_table_handles(self):
        return self.engine.list_table_handles()

    def release_table_handle(self, handle):
        return self.engine.release_table_handle(handle)

    def build_table_access(self, node):
        return self.engine.build_table_access(copy.deepcopy(node))

    def precheck_access(self, plan, **options):
        return self.engine.precheck_access(copy.deepcopy(plan), **options)

    def format_access_issue(self, issue):
        return self.engine.format_access_issue(copy.deepcopy(issue))

    def record_access_audit(self, event):
        return self.engine.record_access_audit(copy.deepcopy(event))

    def list_access_audit_logs(self, *, selected_status="全部", keyword=""):
        return self.engine.list_access_audit_logs(
            selected_status=selected_status,
            keyword=keyword,
        )

    def format_access_audit_event(self, event):
        return self.engine.format_access_audit_event(copy.deepcopy(event))

    def list_plugins(self, *, plugins_dir=None, refresh=None):
        return self.engine.list_plugins(plugins_dir=plugins_dir, refresh=refresh)

    def get_plugin_schema(self, plugin_id, preview_headers=None, table_names=None, table_columns=None):
        return self.engine.get_plugin_schema(
            plugin_id,
            preview_headers=preview_headers,
            table_names=table_names,
            table_columns=table_columns,
        )

    def make_plugin_default_config(self, plugin_id):
        return self.engine.make_plugin_default_config(plugin_id)

    def analyze_jumps(self, plan):
        return self.engine.analyze_jumps(copy.deepcopy(plan))

    def validate_jumps(self, plan):
        return self.engine.validate_jumps(copy.deepcopy(plan))

    def format_jump_issue(self, issue):
        return self.engine.format_jump_issue(copy.deepcopy(issue))

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
