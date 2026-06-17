# -*- coding: utf-8 -*-
import unittest

from workflow.nodes.transit_nodes import (
    append_headers_rows,
    apply_save_transit_node,
    make_unique_transit_name,
    normalize_save_transit_config,
    plan_save_transit_memory_write,
)


class WorkflowTransitNodesTests(unittest.TestCase):
    def test_make_unique_transit_name_adds_suffix(self):
        tables = {"中转数据": {}, "中转数据_2": {}}

        self.assertEqual(make_unique_transit_name("", tables), "中转数据_3")
        self.assertEqual(make_unique_transit_name("新表", tables), "新表")

    def test_append_headers_rows_aligns_union_headers_and_stringifies_none(self):
        headers, rows = append_headers_rows(
            ["A", "B"],
            [["a1", None], ["a2"]],
            ["B", "C"],
            [["b3", "c3"]],
        )

        self.assertEqual(headers, ["A", "B", "C"])
        self.assertEqual(rows, [["a1", "", ""], ["a2", "", ""], ["", "b3", "c3"]])

    def test_normalize_save_transit_config_defaults_and_flags(self):
        options = normalize_save_transit_config({
            "transit_name": "  ",
            "save_memory": False,
            "save_sqlite": True,
            "sqlite_table": " sql name ",
            "sqlite_mode": "追加写入",
            "save_xlsx": True,
            "xlsx_path": " out.xlsx ",
        })

        self.assertEqual(options["base_name"], "中转数据")
        self.assertFalse(options["save_memory"])
        self.assertTrue(options["save_sqlite"])
        self.assertEqual(options["sqlite_table_raw"], "sql name")
        self.assertEqual(options["sqlite_mode"], "追加写入")
        self.assertEqual(options["xlsx_path"], "out.xlsx")

    def test_plan_save_transit_memory_write_overwrites(self):
        plan = plan_save_transit_memory_write(
            ["A"],
            [["x"]],
            {},
            {"base_name": "副表", "append_memory": False},
        )

        self.assertEqual(plan["operation"], "write_transit_table")
        self.assertEqual(plan["write_mode"], "覆盖")
        self.assertEqual(plan["headers"], ["A"])
        self.assertEqual(plan["rows"], [["x"]])
        self.assertEqual(plan["status"], "内存副表：副表")
        self.assertIn("1 行 × 1 列", plan["log_message"])

    def test_plan_save_transit_memory_write_appends_existing_table(self):
        transit_tables = {"副表": {"headers": ["A", "B"], "rows": [["old", "b"]]}}

        plan = plan_save_transit_memory_write(
            ["B", "C"],
            [["new-b", "c"]],
            transit_tables,
            {"base_name": "副表", "append_memory": True},
        )

        self.assertEqual(plan["operation"], "append_transit_table")
        self.assertEqual(plan["write_mode"], "追加")
        self.assertEqual(plan["headers"], ["A", "B", "C"])
        self.assertEqual(plan["rows"], [["old", "b", ""], ["", "new-b", "c"]])
        self.assertEqual(plan["appended_rows"], 1)
        self.assertIn("累计 2 行", plan["status"])

    def test_apply_save_transit_node_writes_memory_and_preserves_input(self):
        context = {"transit_tables": {}}

        headers, rows, message = apply_save_transit_node(
            ["A"],
            [["x"], ["y", "extra"]],
            {"transit_name": "副表"},
            context=context,
        )

        self.assertEqual(headers, ["A"])
        self.assertEqual(rows, [["x"], ["y", "extra"]])
        self.assertEqual(context["transit_tables"], {})
        self.assertEqual(message, "内存副表：副表")
        self.assertEqual(context["save_transit_memory_plan"]["table_name"], "副表")
        self.assertEqual(context["save_transit_memory_plan"]["rows"], [["x"], ["y"]])
        self.assertEqual(context["save_transit_headers"], ["A"])
        self.assertEqual(context["save_transit_rows"], [["x"], ["y"]])

    def test_apply_save_transit_node_preview_sqlite_xlsx_and_no_target(self):
        context = {"transit_tables": {}}
        _headers, _rows, message = apply_save_transit_node(
            ["A"],
            [["x"]],
            {"save_memory": False, "save_sqlite": True, "save_xlsx": True},
            context=context,
        )

        self.assertEqual(message, "SQLite表：预览模式未写入；xlsx：预览模式未导出")
        self.assertEqual(context["transit_tables"], {})

        _headers, _rows, message = apply_save_transit_node(
            ["A"],
            [["x"]],
            {"save_memory": False, "save_sqlite": True, "save_xlsx": True},
            context={"transit_tables": {}},
            execute_actions=True,
        )

        self.assertEqual(message, "")

        _headers, _rows, message = apply_save_transit_node(
            ["A"],
            [["x"]],
            {"save_memory": False, "save_sqlite": False, "save_xlsx": False},
            context={"transit_tables": {}},
        )

        self.assertEqual(message, "未选择保存位置，仅透传数据")


if __name__ == "__main__":
    unittest.main()
