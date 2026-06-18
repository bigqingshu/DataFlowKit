# -*- coding: utf-8 -*-
"""Default workflow node configuration wrappers."""

from workflow.default_configs import default_config_for_type as build_default_config_for_type
from workflow.workflow_task_snapshot_mixin import get_workflow_task_app_dir


SQLITE_DEFAULT_NODE_TYPES = {"匹配值输出列名", "选定列写入指定表", "字段映射写入表"}


class WorkflowDefaultConfigMixin:
    """Compatibility method for building node defaults with window context."""

    def default_config_for_type(self, node_type):
        table_names = []
        if node_type in SQLITE_DEFAULT_NODE_TYPES:
            try:
                table_names = self.app.get_table_names()
            except Exception:
                pass
        table_columns = {}
        for table in table_names[:1]:
            try:
                table_columns[table] = self.app.get_table_columns(table)
            except Exception:
                table_columns[table] = []
        return build_default_config_for_type(
            node_type,
            preview_headers=self.preview_headers,
            table_names=table_names,
            table_columns=table_columns,
            app_dir=get_workflow_task_app_dir(self),
        )
