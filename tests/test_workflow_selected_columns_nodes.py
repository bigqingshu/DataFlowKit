# -*- coding: utf-8 -*-
import unittest

from workflow.nodes.selected_columns_nodes import (
    SELECTED_COLUMNS_PREVIEW_HEADERS,
    apply_selected_columns_to_memory_table,
    build_selected_columns_write_payload,
    build_selected_columns_write_preview_rows,
    get_selected_columns_write_skip_stat,
    get_selected_columns_write_selected_fields,
    make_selected_columns_target_fields,
    normalize_selected_columns_write_mode,
    resolve_selected_columns_write_target,
    selected_columns_should_write,
)


class WorkflowSelectedColumnsNodesTests(unittest.TestCase):
    def test_selected_fields_fallback_and_target_field_deduping(self):
        self.assertEqual(
            get_selected_columns_write_selected_fields({"selected_fields": ["B", "X"]}, ["A", "B"]),
            ["B"],
        )
        self.assertEqual(
            get_selected_columns_write_selected_fields({"selected_fields": ["X"]}, ["A", "B"]),
            ["A", "B"],
        )

        self.assertEqual(
            make_selected_columns_target_fields(
                {
                    "field_name_mode": "手动字段映射",
                    "field_mappings": [
                        {"source_field": "A", "target_field": "T"},
                        {"source_field": "B", "target_field": "T"},
                        {"source_field": "C", "target_field": ""},
                    ],
                },
                ["A", "B", "C"],
            ),
            ["T", "T_2", "C"],
        )
        self.assertEqual(
            make_selected_columns_target_fields({"field_name_mode": "添加前缀", "target_prefix": "pre_"}, ["A"]),
            ["pre_A"],
        )
        self.assertEqual(
            make_selected_columns_target_fields({"field_name_mode": "添加后缀", "target_suffix": "_out"}, ["A"]),
            ["A_out"],
        )

    def test_write_mode_and_overwrite_rules(self):
        self.assertEqual(normalize_selected_columns_write_mode("复制列到目标表新建字段"), "局部覆盖，保留目标原行数")
        self.assertEqual(normalize_selected_columns_write_mode("按来源完整结构写入"), "按来源完整结构覆盖")
        self.assertEqual(normalize_selected_columns_write_mode("bad"), "局部覆盖，保留目标原行数")

        self.assertTrue(selected_columns_should_write("old", "new", "覆盖全部"))
        self.assertTrue(selected_columns_should_write("", "new", "只写入空单元格"))
        self.assertFalse(selected_columns_should_write("old", "new", "只写入空单元格"))
        self.assertTrue(selected_columns_should_write("old", "new", "目标已有值且不同才覆盖"))
        self.assertFalse(selected_columns_should_write("same", "same", "目标已有值且不同才覆盖"))

    def test_apply_selected_columns_to_memory_table_local_overwrite(self):
        headers, rows = apply_selected_columns_to_memory_table(
            ["ID", "A"],
            [["1", ""], ["2", "keep"], ["3", "tail"]],
            ["A", "B"],
            [["x", "b1"], ["y", "b2"]],
            {"write_mode": "局部覆盖，保留目标原行数", "overwrite_rule": "只写入空单元格"},
        )

        self.assertEqual(headers, ["ID", "A", "B"])
        self.assertEqual(rows, [["1", "x", "b1"], ["2", "keep", "b2"], ["3", "tail", ""]])

    def test_apply_selected_columns_to_memory_table_clear_and_full_structure_modes(self):
        headers, rows = apply_selected_columns_to_memory_table(
            ["ID", "A", "B"],
            [["1", "old", "keep"], ["2", "old2", "tail"]],
            ["A"],
            [["new"]],
            {"write_mode": "清空目标字段后覆盖，保留目标原行数", "overwrite_rule": "覆盖全部"},
        )

        self.assertEqual(headers, ["ID", "A", "B"])
        self.assertEqual(rows, [["1", "new", "keep"], ["2", "", "tail"]])

        headers, rows = apply_selected_columns_to_memory_table(
            ["ID", "A", "B"],
            [["1", "old", "keep"], ["2", "old2", "tail"]],
            ["A"],
            [["new"]],
            {"write_mode": "按来源完整结构覆盖", "overwrite_rule": "覆盖全部"},
        )

        self.assertEqual(headers, ["ID", "A", "B"])
        self.assertEqual(rows, [["", "new", ""]])

    def test_apply_selected_columns_to_memory_table_rebuild_mode(self):
        headers, rows = apply_selected_columns_to_memory_table(
            ["ID", "A"],
            [["1", "old"]],
            ["X", "Y"],
            [["x1", "y1"], ["x2"]],
            {"write_mode": "覆盖重建目标表"},
        )

        self.assertEqual(headers, ["X", "Y"])
        self.assertEqual(rows, [["x1", "y1"], ["x2"]])

    def test_build_selected_columns_write_payload(self):
        selected_fields, target_fields, selected_rows = build_selected_columns_write_payload(
            {
                "selected_fields": ["B", "A"],
                "field_name_mode": "添加后缀",
                "target_suffix": "_out",
            },
            ["A", "B"],
            [["a1", "b1"], ["a2"]],
        )

        self.assertEqual(selected_fields, ["B", "A"])
        self.assertEqual(target_fields, ["B_out", "A_out"])
        self.assertEqual(selected_rows, [["b1", "a1"], ["", "a2"]])

    def test_write_target_resolution_and_skip_stats(self):
        self.assertEqual(resolve_selected_columns_write_target({"target_type": "当前工作表"}), ("当前工作表", "当前工作表"))
        self.assertEqual(
            resolve_selected_columns_write_target({"target_type": "中转副表", "target_transit_table": "T"}),
            ("中转副表", "T"),
        )
        self.assertEqual(
            resolve_selected_columns_write_target({"target_type": "SQLite表", "target_table": ""}),
            ("SQLite表", "选定列结果"),
        )

        stat = get_selected_columns_write_skip_stat(
            {"enable_write": False},
            "来源",
            ["A", "B"],
            [["a", "b"]],
        )
        self.assertIn("未勾选实际写入", stat)
        self.assertIn("2 列 × 1 行", stat)

        stat = get_selected_columns_write_skip_stat(
            {"enable_write": True},
            "来源",
            ["A"],
            [["a"]],
            execute_actions=False,
            allow_preview_write=False,
        )
        self.assertIn("预览计划", stat)

        stat = get_selected_columns_write_skip_stat(
            {"enable_write": True, "target_type": "SQLite表"},
            "来源",
            ["A"],
            [["a"]],
            allow_preview_write=True,
            config_preview_only=True,
        )
        self.assertIn("配置界面预运行", stat)

        self.assertEqual(
            get_selected_columns_write_skip_stat(
                {"enable_write": True, "target_type": "当前工作表"},
                "来源",
                ["A"],
                [["a"]],
                allow_preview_write=True,
            ),
            "",
        )

    def test_build_selected_columns_write_preview_rows(self):
        headers, rows = build_selected_columns_write_preview_rows(
            {
                "selected_fields": ["A", "B"],
                "field_name_mode": "使用原字段名",
                "overwrite_rule": "只写入空单元格",
                "write_mode": "局部覆盖，保留目标原行数",
            },
            ["A", "B"],
            [["a1", "b1"], ["a2", "b2"]],
            "当前工作流表",
            ["A"],
            [["old"]],
            "目标表",
        )

        self.assertEqual(headers, SELECTED_COLUMNS_PREVIEW_HEADERS)
        self.assertEqual(rows[0], ["当前工作流表", "1", "A", "a1", "目标表", "1", "A", "old", "按覆盖策略跳过"])
        self.assertEqual(rows[1], ["当前工作流表", "1", "B", "b1", "目标表", "1", "B", "", "新建字段；写入/覆盖"])
        self.assertEqual(rows[2][-1], "新增目标行；写入/覆盖")

        _headers, rows = build_selected_columns_write_preview_rows(
            {"selected_fields": ["A"], "write_mode": "覆盖重建目标表"},
            ["A"],
            [["a1"]],
            "来源",
            ["A"],
            [["old"]],
            "目标",
        )

        self.assertEqual(rows[0][-1], "重建目标表后写入")


if __name__ == "__main__":
    unittest.main()
