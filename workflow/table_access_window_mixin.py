# -*- coding: utf-8 -*-
"""PlanWorkflowWindow table-access compatibility mixin."""

from workflow.table_access_core_mixin import TableAccessCoreMixin
from workflow.table_access_precheck_mixin import TableAccessPrecheckMixin
from workflow.table_access_window_ui_mixin import TableAccessWindowUiMixin


class TableAccessWindowMixin(
    TableAccessCoreMixin,
    TableAccessPrecheckMixin,
    TableAccessWindowUiMixin,
):
    """Compatibility methods used by table-access UI and runtime modules."""

    pass
