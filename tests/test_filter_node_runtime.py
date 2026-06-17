# -*- coding: utf-8 -*-
import unittest

from workflow import filter_node_runtime


class FilterNodeRuntimeTests(unittest.TestCase):
    def test_apply_filter_node_for_window_loads_external_records_and_runs_core(self):
        calls = []

        class Window:
            def get_plan_filter_available_fields(self, headers, extra_tables, context=None):
                calls.append(("fields", list(headers), list(extra_tables), context))
                return ["当前表.Code", "t.Name"]

            def load_plan_table_records(self, table_name, context=None, required_fields=None):
                calls.append(("load", table_name, context, required_fields))
                return [{"t.Code": "A", "t.Name": "Alpha"}]

            def apply_filter_node(self, *_args, **_kwargs):
                raise AssertionError("runtime should call the pure filter core directly")

        context = {}
        headers, rows, stat = filter_node_runtime.apply_filter_node_for_window(
            Window(),
            ["Code"],
            [["A"], ["B"]],
            {
                "conditions": [],
                "join_rules": [{"left": "当前表.Code", "op": "等于", "right": "t.Code"}],
                "extra_tables": ["t"],
                "output_fields": ["当前表.Code", "t.Name"],
            },
            context=context,
        )

        self.assertEqual(headers, ["Code", "t.Name"])
        self.assertEqual(rows, [["A", "Alpha"]])
        self.assertIn("筛选/匹配后 1 行", stat)
        self.assertEqual(calls[0], ("fields", ["Code"], ["t"], context))
        self.assertEqual(calls[1][0], "load")
        self.assertEqual(calls[1][1], "t")
        self.assertIs(calls[1][2], context)
        self.assertEqual(calls[1][3], {"t.Code", "t.Name"})

    def test_apply_filter_node_for_window_config_probe_skips_external_load(self):
        calls = []

        class Window:
            def get_plan_filter_available_fields(self, headers, extra_tables, context=None):
                return ["当前表.Code", "t.Name"]

            def load_plan_table_records(self, *_args, **_kwargs):
                calls.append("load")
                raise AssertionError("config probe should not load table rows")

        headers, rows, stat = filter_node_runtime.apply_filter_node_for_window(
            Window(),
            ["Code"],
            [["A"]],
            {"conditions": [], "join_rules": [], "extra_tables": ["t"], "output_fields": []},
            context={"is_config_probe": True},
        )

        self.assertEqual(headers, ["Code", "t.Name"])
        self.assertEqual(rows, [])
        self.assertIn("配置探测", stat)
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
