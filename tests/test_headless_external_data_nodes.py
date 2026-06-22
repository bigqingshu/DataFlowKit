# -*- coding: utf-8 -*-
import unittest

from engine.headless import HeadlessWorkflowEngine


class HeadlessExternalDataNodesTests(unittest.TestCase):
    def test_match_value_output_uses_context_table_source(self):
        engine = HeadlessWorkflowEngine()
        plan = {
            "nodes": [{
                "node_type_id": "core.match_value_output",
                "config": {
                    "source_field": "Source",
                    "lookup_table": "lookup",
                    "lookup_fields": ["ColA", "ColB"],
                    "match_mode": "完全相等",
                    "multi_match_policy": "合并所有字段名",
                    "multi_match_separator": "|",
                },
            }],
            "headers": ["Source"],
            "rows": [["beta"], ["alpha"], ["none"]],
        }

        result = engine.preview_plan(
            plan,
            initial_context={
                "table_sources": {
                    "lookup": {
                        "type": "inline",
                        "headers": ["ColA", "ColB"],
                        "rows": [["alpha", "beta"], ["gamma", "alpha"]],
                    }
                }
            },
        )

        self.assertEqual(result.headers, ["Source", "匹配字段名", "匹配值", "匹配行号", "匹配状态"])
        self.assertEqual(result.rows[0], ["beta", "ColB", "beta", "1", "成功"])
        self.assertEqual(result.rows[1], ["alpha", "ColA|ColB", "alpha", "1|2", "多匹配，共2项"])
        self.assertEqual(result.rows[2], ["none", "未匹配", "", "", "未匹配"])
        self.assertIn("匹配值输出列名完成", result.logs[0])

    def test_filter_node_uses_context_table_source(self):
        engine = HeadlessWorkflowEngine()
        plan = {
            "nodes": [{
                "node_type_id": "core.filter",
                "config": {
                    "extra_tables": ["lookup"],
                    "join_rules": [{"left": "当前表.Code", "op": "等于", "right": "lookup.Code"}],
                    "output_fields": ["当前表.Code", "lookup.Name"],
                    "result_limit": "100",
                },
            }],
            "headers": ["Code"],
            "rows": [["A"], ["B"]],
        }

        result = engine.preview_plan(
            plan,
            initial_context={
                "table_sources": {
                    "lookup": {
                        "type": "inline",
                        "headers": ["Code", "Name"],
                        "rows": [["A", "Alpha"], ["C", "Gamma"]],
                    }
                }
            },
        )

        self.assertEqual(result.headers, ["Code", "lookup.Name"])
        self.assertEqual(result.rows, [["A", "Alpha"]])
        self.assertIn("筛选/匹配后 1 行", result.logs[0])


if __name__ == "__main__":
    unittest.main()
