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

    def build_message_panel_state(self, **kwargs):
        return self.facade.build_message_panel_state(**kwargs)

    def describe_selection_feedback(self, **kwargs):
        return self.facade.describe_selection_feedback(**kwargs)

    def describe_picker_feedback(self, **kwargs):
        return self.facade.describe_picker_feedback(**kwargs)

    def describe_picker_context(self, **kwargs):
        return self.facade.describe_picker_context(**kwargs)

    def format_issues_text(self, issues):
        return self.facade.format_issues_text(copy.deepcopy(issues or []))

    def describe_job_run_conflict(self, **kwargs):
        return self.facade.describe_job_run_conflict(**kwargs)

    def describe_job_start_failure(self, **kwargs):
        return self.facade.describe_job_start_failure(**kwargs)

    def describe_job_started(self, **kwargs):
        return self.facade.describe_job_started(**kwargs)

    def describe_job_cancel_failure(self, **kwargs):
        return self.facade.describe_job_cancel_failure(**kwargs)

    def describe_job_poll_failure(self, **kwargs):
        return self.facade.describe_job_poll_failure(**kwargs)

    def describe_validation_feedback(self, combined):
        return self.facade.describe_validation_feedback(copy.deepcopy(combined))

    def describe_confirmation_prompt(self, **kwargs):
        return self.facade.describe_confirmation_prompt(**kwargs)

    def describe_plan_command_feedback(self, result, **kwargs):
        return self.facade.describe_plan_command_feedback(copy.deepcopy(result), **kwargs)

    def describe_plan_file_failure(self, **kwargs):
        return self.facade.describe_plan_file_failure(**kwargs)

    def describe_node_detail(self, node_type_id, *, preview_headers=None, table_names=None, table_columns=None):
        return self.facade.describe_node_detail(
            node_type_id,
            preview_headers=preview_headers,
            table_names=table_names,
            table_columns=table_columns,
        )

    def describe_node_config_context(
        self,
        node_type_id="",
        *,
        node=None,
        config=None,
        preview_headers=None,
        table_names=None,
        table_columns=None,
        transit_context=None,
    ):
        return self.facade.describe_node_config_context(
            node_type_id,
            node=copy.deepcopy(node),
            config=copy.deepcopy(config),
            preview_headers=preview_headers,
            table_names=table_names,
            table_columns=table_columns,
            transit_context=copy.deepcopy(transit_context),
        )

    def apply_node_config_command(
        self,
        node_type_id="",
        *,
        node=None,
        config=None,
        command=None,
        preview_headers=None,
        table_names=None,
        table_columns=None,
        transit_context=None,
    ):
        return self.facade.apply_node_config_command(
            node_type_id,
            node=copy.deepcopy(node),
            config=copy.deepcopy(config),
            command=copy.deepcopy(command),
            preview_headers=preview_headers,
            table_names=table_names,
            table_columns=table_columns,
            transit_context=copy.deepcopy(transit_context),
        )

    def resolve_node_config_options(
        self,
        node_type_id="",
        *,
        node=None,
        config=None,
        field_key="",
        current_values=None,
        preview_headers=None,
        table_names=None,
        table_columns=None,
        transit_context=None,
    ):
        return self.facade.resolve_node_config_options(
            node_type_id,
            node=copy.deepcopy(node),
            config=copy.deepcopy(config),
            field_key=field_key,
            current_values=copy.deepcopy(current_values),
            preview_headers=preview_headers,
            table_names=table_names,
            table_columns=table_columns,
            transit_context=copy.deepcopy(transit_context),
        )

    def build_output_panel_state(self, payload=None, **fallbacks):
        return self.facade.build_output_panel_state(payload, **fallbacks)

    def build_preview_panel_state(self, **kwargs):
        return self.facade.build_preview_panel_state(**kwargs)

    def apply_node_config_state(self, plan, **kwargs):
        return self.facade.apply_node_config_state(copy.deepcopy(plan), **kwargs)

    def plan_status_text(self, plan=None, *, current_plan_path=None):
        return self.facade.plan_status_text(plan, current_plan_path=current_plan_path)

    def get_node_ui_schema(self, node_type_id, preview_headers=None, table_names=None, table_columns=None):
        return self.engine.get_node_ui_schema(
            node_type_id,
            preview_headers=preview_headers,
            table_names=table_names,
            table_columns=table_columns,
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
        input_source=None,
        input_db_path=None,
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
            input_source=copy.deepcopy(input_source or {}),
            input_db_path=input_db_path,
            migrate=migrate,
        )

    def validate_plan_template(self, plan):
        return self.facade.validate_plan_template(copy.deepcopy(plan))

    def import_table_file(self, path):
        return self.facade.import_table_file(path)

    def describe_file_action(self, action, **kwargs):
        return self.facade.describe_file_action(action, **kwargs)

    def build_import_table_state(self, imported):
        return self.facade.build_import_table_state(copy.deepcopy(imported))

    def build_loaded_plan_state(self, loaded):
        return self.facade.build_loaded_plan_state(copy.deepcopy(loaded))

    def build_saved_plan_state(self, saved, plan=None):
        return self.facade.build_saved_plan_state(copy.deepcopy(saved), copy.deepcopy(plan))

    def build_template_list_state(self, listed, *, show_status=True):
        return self.facade.build_template_list_state(copy.deepcopy(listed), show_status=show_status)

    def build_plugin_list_state(self, listed, *, show_status=True):
        return self.facade.build_plugin_list_state(copy.deepcopy(listed), show_status=show_status)

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

    def parse_clipboard_table(self, text, *, first_row_header=True):
        return self.engine.parse_clipboard_table(text, first_row_header=first_row_header)

    def normalize_table_headers(self, headers):
        return self.engine.normalize_table_headers(headers)

    def promote_first_row_to_headers(self, table):
        return self.engine.promote_first_row_to_headers(copy.deepcopy(table))

    def patch_table_cell(self, table, *, row=None, column=None, value=""):
        return self.engine.patch_table_cell(copy.deepcopy(table), row=row, column=column, value=value)

    def search_table(self, table, keyword, *, current_index=-1, offset=0, reset=True):
        return self.engine.search_table(
            copy.deepcopy(table),
            keyword,
            current_index=current_index,
            offset=offset,
            reset=reset,
        )

    def build_table_search_navigation(self, matches, *, current_index=-1, offset=0, reset=False):
        return self.engine.build_table_search_navigation(
            copy.deepcopy(matches or []),
            current_index=current_index,
            offset=offset,
            reset=reset,
        )

    def build_data_source_state(self, table=None, *, source=None, dirty=False, display_name=""):
        return self.engine.build_data_source_state(
            copy.deepcopy(table or {}),
            source=copy.deepcopy(source or {}),
            dirty=dirty,
            display_name=display_name,
        )

    def describe_data_source_actions(self, table=None, *, source=None, dirty=False):
        return self.engine.describe_data_source_actions(
            copy.deepcopy(table or {}),
            source=copy.deepcopy(source or {}),
            dirty=dirty,
        )

    def build_data_source_panel_state(
        self,
        table=None,
        *,
        source=None,
        dirty=False,
        display_name="",
        partial=False,
        page_info=None,
        search_navigation=None,
    ):
        return self.engine.build_data_source_panel_state(
            copy.deepcopy(table or {}),
            source=copy.deepcopy(source or {}),
            dirty=dirty,
            display_name=display_name,
            partial=partial,
            page_info=copy.deepcopy(page_info or {}),
            search_navigation=copy.deepcopy(search_navigation or {}),
        )

    def build_data_source_manager_state(
        self,
        table=None,
        *,
        source=None,
        dirty=False,
        display_name="",
        partial=False,
        page_info=None,
        search_navigation=None,
        db_path="",
        table_names=None,
        selected_table="",
    ):
        return self.engine.build_data_source_manager_state(
            copy.deepcopy(table or {}),
            source=copy.deepcopy(source or {}),
            dirty=dirty,
            display_name=display_name,
            partial=partial,
            page_info=copy.deepcopy(page_info or {}),
            search_navigation=copy.deepcopy(search_navigation or {}),
            db_path=db_path,
            table_names=list(table_names or []),
            selected_table=selected_table,
        )

    def describe_data_source_service(self):
        return self.engine.describe_data_source_service()

    def describe_table_save_modes(self):
        return self.engine.describe_table_save_modes()

    def normalize_table_save_mode(self, mode):
        return self.engine.normalize_table_save_mode(mode)

    def save_table(self, table=None, *, db_path=None, table_name=None, mode="replace"):
        return self.engine.save_table(
            copy.deepcopy(table or {}),
            db_path=db_path,
            table_name=table_name,
            mode=mode,
        )

    def delete_table(self, *, db_path=None, table_name=None, backup=True, confirmed=False):
        return self.engine.delete_table(
            db_path=db_path,
            table_name=table_name,
            backup=backup,
            confirmed=confirmed,
        )

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

    def describe_plugin_config(self, plugin_id, *, config=None, input_table=None, context=None):
        return self.engine.describe_plugin_config(
            plugin_id,
            config=copy.deepcopy(config),
            input_table=copy.deepcopy(input_table),
            context=copy.deepcopy(context),
        )

    def resolve_plugin_parameter_options(self, plugin_id, *, field_key="", param_key="", config=None, input_table=None, context=None):
        return self.engine.resolve_plugin_parameter_options(
            plugin_id,
            field_key=field_key,
            param_key=param_key,
            config=copy.deepcopy(config),
            input_table=copy.deepcopy(input_table),
            context=copy.deepcopy(context),
        )

    def resolve_plugin_config_options(
        self,
        plugin_id,
        *,
        field_key="",
        current_values=None,
        view_id="",
        section="",
        config=None,
        input_table=None,
        context=None,
    ):
        return self.engine.resolve_plugin_config_options(
            plugin_id,
            field_key=field_key,
            current_values=copy.deepcopy(current_values),
            view_id=view_id,
            section=section,
            config=copy.deepcopy(config),
            input_table=copy.deepcopy(input_table),
            context=copy.deepcopy(context),
        )

    def preview_plugin_config_effect(self, plugin_id, *, config=None, input_table=None, context=None):
        return self.engine.preview_plugin_config_effect(
            plugin_id,
            config=copy.deepcopy(config),
            input_table=copy.deepcopy(input_table),
            context=copy.deepcopy(context),
        )

    def validate_plugin_config_patch(self, plugin_id, *, patch=None, config=None, input_table=None, context=None):
        return self.engine.validate_plugin_config_patch(
            plugin_id,
            patch=copy.deepcopy(patch),
            config=copy.deepcopy(config),
            input_table=copy.deepcopy(input_table),
            context=copy.deepcopy(context),
        )

    def apply_plugin_config_patch(self, plugin_id, *, patch=None, config=None, input_table=None, context=None):
        return self.engine.apply_plugin_config_patch(
            plugin_id,
            patch=copy.deepcopy(patch),
            config=copy.deepcopy(config),
            input_table=copy.deepcopy(input_table),
            context=copy.deepcopy(context),
        )

    def make_plugin_default_config(self, plugin_id):
        return self.engine.make_plugin_default_config(plugin_id)

    def run_plugin_custom_config_window(self, plugin_id, *, config=None, input_table=None, context=None, parent=None):
        return self.engine.run_plugin_custom_config_window(
            plugin_id,
            config=copy.deepcopy(config),
            input_table=copy.deepcopy(input_table),
            context=copy.deepcopy(context),
            parent=parent,
        )

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
