# -*- coding: utf-8 -*-
"""PlanWorkflowWindow mixin for workflow table runtime wrappers."""

from workflow import table_runtime_services as workflow_table_runtime_services


class WorkflowTableRuntimeMixin:
    """Compatibility methods used by table access, SQLite reads, and output services."""

    def get_table_manager(self, context=None, node=None, node_type="", node_name=""):
        return workflow_table_runtime_services.get_table_manager(
            self,
            context=context,
            node=node,
            node_type=node_type,
            node_name=node_name,
        )

    def get_workflow_output_manager(self, table_name, overwrite=False, context=None):
        return workflow_table_runtime_services.get_workflow_output_manager(
            self,
            table_name,
            overwrite=overwrite,
            context=context,
        )

    def transit_write_permissions_for_mode(self, exists=False, write_mode="", partial=False):
        return workflow_table_runtime_services.transit_write_permissions_for_mode(
            exists=exists,
            write_mode=write_mode,
            partial=partial,
        )

    def check_transit_table_permission(self, context, table_name, permissions, operation="transit_table",
                                       fields=None, field_action=None, write_mode="", node_type=""):
        return workflow_table_runtime_services.check_transit_table_permission(
            self,
            context,
            table_name,
            permissions,
            operation=operation,
            fields=fields,
            field_action=field_action,
            write_mode=write_mode,
            node_type=node_type,
        )

    def check_transit_table_write_permission(self, context, table_name, exists=False, write_mode="",
                                             fields=None, partial=False, node_type="", operation="write_transit_table"):
        return workflow_table_runtime_services.check_transit_table_write_permission(
            self,
            context,
            table_name,
            exists=exists,
            write_mode=write_mode,
            fields=fields,
            partial=partial,
            node_type=node_type,
            operation=operation,
        )

    def log_transit_table_event(self, manager, operation, table_name, headers=None, rows=None, message="", **extra):
        return workflow_table_runtime_services.log_transit_table_event(
            manager,
            operation,
            table_name,
            headers=headers,
            rows=rows,
            message=message,
            **extra,
        )

    def check_current_table_permission(self, context, headers, write=False, operation="current_table"):
        return workflow_table_runtime_services.check_current_table_permission(
            self,
            context,
            headers,
            write=write,
            operation=operation,
        )

    def log_current_table_transform(self, manager, before_shape, headers, rows, node_type=""):
        return workflow_table_runtime_services.log_current_table_transform(
            manager,
            before_shape,
            headers,
            rows,
            node_type=node_type,
        )

    def get_workflow_output_mode(self, context=None):
        snapshot = self.get_workflow_snapshot(context)
        value = str(snapshot.get("output_mode") or "").strip()
        if value:
            return value
        try:
            return self.output_mode_var.get()
        except Exception:
            return "输出到主界面预览区"

    def get_workflow_output_table(self, context=None):
        snapshot = self.get_workflow_snapshot(context)
        value = str(snapshot.get("output_table") or snapshot.get("workflow_name") or "").strip()
        if value:
            return value
        try:
            return self.output_table_var.get().strip()
        except Exception:
            return ""

    def get_workflow_backup_before_overwrite(self, context=None):
        snapshot = self.get_workflow_snapshot(context)
        if "backup_before_overwrite" in snapshot:
            return bool(snapshot.get("backup_before_overwrite"))
        try:
            return bool(self.backup_before_overwrite_var.get())
        except Exception:
            return True

    def get_workflow_sqlite_columns(self, table_name, context=None):
        return workflow_table_runtime_services.get_workflow_sqlite_columns(self, table_name, context=context)

    def load_plan_table_records(self, table_name, context=None, required_fields=None):
        return workflow_table_runtime_services.load_plan_table_records(
            self,
            table_name,
            context=context,
            required_fields=required_fields,
        )

    def save_result_to_sqlite_append(self, headers, rows, table_name_raw, context=None):
        return workflow_table_runtime_services.save_result_to_sqlite_append(
            self,
            headers,
            rows,
            table_name_raw,
            context=context,
        )

    def sqlite_table_exists_by_name(self, table_name, context=None):
        return workflow_table_runtime_services.sqlite_table_exists_by_name(self, table_name, context=context)

    def load_target_table_rows_for_writeback(self, table_name, context=None):
        return workflow_table_runtime_services.load_target_table_rows_for_writeback(
            self,
            table_name,
            context=context,
        )

    def backup_sqlite_table_for_writeback(self, table_name, context=None):
        return workflow_table_runtime_services.backup_sqlite_table_for_writeback(self, table_name, context=context)

    def apply_writeback_updates_to_sqlite(self, table_name, actions, context=None):
        return workflow_table_runtime_services.apply_writeback_updates_to_sqlite(
            self,
            table_name,
            actions,
            context=context,
        )

    def apply_writeback_transaction_to_sqlite(self, table_name, actions, target_fields, context=None):
        return workflow_table_runtime_services.apply_writeback_transaction_to_sqlite(
            self,
            table_name,
            actions,
            target_fields,
            context=context,
        )

    def clear_writeback_target_fields_in_sqlite(self, table_name, target_fields, context=None):
        return workflow_table_runtime_services.clear_writeback_target_fields_in_sqlite(
            self,
            table_name,
            target_fields,
            context=context,
        )

    def load_lookup_table_for_match_value_output(self, config, context=None):
        return workflow_table_runtime_services.load_lookup_table_for_match_value_output(
            self,
            config,
            context=context,
        )

    def save_result_to_sqlite(self, headers, rows, table_name_raw, overwrite=False, backup=True, context=None):
        return workflow_table_runtime_services.save_result_to_sqlite(
            self,
            headers,
            rows,
            table_name_raw,
            overwrite=overwrite,
            backup=backup,
            context=context,
        )
