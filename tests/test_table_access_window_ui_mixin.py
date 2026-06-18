# -*- coding: utf-8 -*-
import unittest

from workflow.table_access_window_mixin import TableAccessWindowMixin
from workflow.table_access_precheck_mixin import TableAccessPrecheckMixin
from workflow.table_access_window_ui_mixin import TableAccessWindowUiMixin


class TableAccessWindowUiMixinTests(unittest.TestCase):
    def test_table_access_window_mixin_inherits_precheck_wrappers(self):
        self.assertTrue(issubclass(TableAccessWindowMixin, TableAccessPrecheckMixin))
        self.assertIs(
            TableAccessWindowMixin.build_table_access_precheck,
            TableAccessPrecheckMixin.build_table_access_precheck,
        )
        self.assertIs(
            TableAccessWindowMixin.confirm_table_access_precheck,
            TableAccessPrecheckMixin.confirm_table_access_precheck,
        )

    def test_table_access_window_mixin_inherits_ui_wrappers(self):
        self.assertTrue(issubclass(TableAccessWindowMixin, TableAccessWindowUiMixin))
        self.assertIs(
            TableAccessWindowMixin.open_table_access_window,
            TableAccessWindowUiMixin.open_table_access_window,
        )
        self.assertIs(
            TableAccessWindowMixin.create_table_access_window_callbacks,
            TableAccessWindowUiMixin.create_table_access_window_callbacks,
        )


if __name__ == "__main__":
    unittest.main()
