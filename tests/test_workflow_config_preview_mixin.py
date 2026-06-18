# -*- coding: utf-8 -*-
import unittest

from workflow.workflow_config_preview_mixin import WorkflowConfigPreviewMixin


class FakeWindow(WorkflowConfigPreviewMixin):
    def __init__(self):
        self.calls = []

    def run_plan(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs.get("return_context"):
            return ["H"], [["R"]], [], {"transit_tables": {"x": 1}}
        return ["H"], [["R"]]


class WorkflowConfigPreviewMixinTests(unittest.TestCase):
    def test_preview_context_uses_expected_flags(self):
        window = FakeWindow()
        context = window.make_config_preview_context()
        self.assertTrue(context["is_config_probe"])
        self.assertTrue(context["allow_selected_columns_write_in_preview"])
        self.assertTrue(context["selected_columns_config_preview_only"])

    def test_headers_rows_before_uses_preview_context(self):
        window = FakeWindow()
        headers, rows = window.get_headers_rows_before(3)
        self.assertEqual(headers, ["H"])
        self.assertEqual(rows, [["R"]])
        self.assertEqual(window.calls[0]["stop_index"], 2)
        self.assertTrue(window.calls[0]["raise_error"])
        self.assertTrue(window.calls[0]["initial_context"]["is_config_probe"])

    def test_transit_context_before_falls_back_to_preview_context(self):
        window = FakeWindow()
        self.assertTrue(window.get_transit_context_before(0)["is_config_probe"])
        self.assertEqual(window.get_transit_context_before(3)["transit_tables"], {"x": 1})


if __name__ == "__main__":
    unittest.main()
