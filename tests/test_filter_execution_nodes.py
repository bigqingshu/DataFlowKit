# -*- coding: utf-8 -*-
import unittest

from workflow.nodes.filter_execution_nodes import (
    apply_filter_node,
    build_plan_filter_right_index,
    get_plan_filter_hash_join_rules,
    iter_plan_filter_join_candidates,
    record_passes_plan_conditions,
    record_passes_plan_join_rules,
    record_survives_available_plan_conditions,
)


class FilterExecutionNodesTests(unittest.TestCase):
    def test_conditions_and_join_rules(self):
        record = {"当前表.A": "x", "当前表.B": "x", "t.C": "xyz"}

        self.assertTrue(record_passes_plan_conditions(
            record,
            [{"field": "当前表.A", "op": "等于", "value_source": "字段值", "value": "当前表.B"}],
            "AND",
        ))
        self.assertFalse(record_passes_plan_conditions(
            record,
            [{"field": "当前表.A", "op": "等于", "value_source": "字段值", "value": "当前表.Missing"}],
            "AND",
        ))
        self.assertTrue(record_survives_available_plan_conditions(
            {"当前表.A": "x"},
            [
                {"field": "当前表.A", "op": "等于", "value": "x"},
                {"field": "t.C", "op": "等于", "value": "z"},
            ],
            "OR",
        ))
        self.assertTrue(record_passes_plan_join_rules(
            record,
            [{"left": "当前表.A", "op": "等于", "right": "当前表.B"}],
        ))
        self.assertTrue(record_passes_plan_join_rules(
            {"当前表.A": "x"},
            [{"left": "当前表.A", "op": "等于", "right": "t.C"}],
        ))
        self.assertFalse(record_passes_plan_join_rules(
            {"当前表.A": "x", "t.C": "y"},
            [{"left": "当前表.A", "op": "等于", "right": "t.C"}],
        ))

    def test_hash_join_candidates(self):
        right_records = [{"t.C": "x", "t.Name": "n1"}, {"t.C": "y", "t.Name": "n2"}]
        join_rules = [{"left": "当前表.A", "op": "等于", "right": "t.C"}]
        hash_rules = get_plan_filter_hash_join_rules("t", join_rules, "AND", right_records)
        right_index, missing = build_plan_filter_right_index(right_records, hash_rules)

        self.assertEqual(hash_rules, [("当前表.A", "t.C")])
        self.assertEqual(missing, [])
        self.assertEqual(
            iter_plan_filter_join_candidates({"当前表.A": "x"}, right_records, hash_rules, right_index, missing),
            [right_records[0]],
        )

    def test_filter_node_filters_joins_and_rejects_large_cross_join(self):
        headers, rows, message = apply_filter_node(
            ["A", "B"],
            [["x", "1"], ["x", "1"], ["y", "2"]],
            {
                "conditions": [{"field": "当前表.A", "op": "等于", "value": "x"}],
                "output_fields": ["当前表.A", "当前表.B"],
                "remove_duplicates": True,
            },
            context={
                "lookup_fields": ["当前表.A", "当前表.B"],
                "output_headers": ["A", "B"],
                "current_required": {"A", "B"},
                "table_required": {},
                "table_records": {},
            },
        )

        self.assertEqual(headers, ["A", "B"])
        self.assertEqual(rows, [["x", "1"]])
        self.assertEqual(message, "筛选/匹配后 1 行，已去除重复内容 1 行；优化：提前过滤 1 行")

        headers, rows, message = apply_filter_node(
            ["Code"],
            [["A"], ["B"]],
            {
                "conditions": [],
                "join_rules": [{"left": "当前表.Code", "op": "等于", "right": "t.Code"}],
                "extra_tables": ["t"],
                "output_fields": ["当前表.Code", "t.Name"],
            },
            context={
                "lookup_fields": ["当前表.Code", "t.Name"],
                "output_headers": ["Code", "t.Name"],
                "current_required": {"Code"},
                "table_required": {"t": {"t.Code", "t.Name"}},
                "table_records": {
                    "t": [
                        {"t.Code": "A", "t.Name": "Alpha"},
                        {"t.Code": "C", "t.Name": "Gamma"},
                    ]
                },
            },
        )

        self.assertEqual(headers, ["Code", "t.Name"])
        self.assertEqual(rows, [["A", "Alpha"]])
        self.assertEqual(message, "筛选/匹配后 1 行；优化：字段裁剪 1 表，等值索引匹配 1 表")

        with self.assertRaisesRegex(RuntimeError, "可能形成全组合"):
            apply_filter_node(
                ["A"],
                [["1"], ["2"]],
                {
                    "conditions": [],
                    "join_rules": [],
                    "extra_tables": ["t"],
                    "output_fields": ["当前表.A", "t.B"],
                    "max_intermediate": "3",
                },
                context={
                    "lookup_fields": ["当前表.A", "t.B"],
                    "output_headers": ["A", "t.B"],
                    "current_required": {"A"},
                    "table_required": {"t": {"t.B"}},
                    "table_records": {"t": [{"t.B": "x"}, {"t.B": "y"}]},
                },
            )


if __name__ == "__main__":
    unittest.main()
