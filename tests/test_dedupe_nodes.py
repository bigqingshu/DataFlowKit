# -*- coding: utf-8 -*-
import unittest

from workflow.nodes import data_nodes
from workflow.nodes.dedupe_nodes import apply_dedupe_node


class DedupeNodesTests(unittest.TestCase):
    def test_data_nodes_keeps_dedupe_compat_export(self):
        self.assertIs(data_nodes.apply_dedupe_node, apply_dedupe_node)

    def test_dedupe_node_outputs_deduped_rows_and_markers(self):
        headers, rows, message = apply_dedupe_node(
            ["ID", "Name"],
            [["A", "x"], [" A ", "y"], ["B", "z"], ["", "blank"]],
            {
                "key_fields": ["ID"],
                "trim": True,
                "output_mode": "输出去重后的数据",
                "add_marker_columns": False,
            },
        )
        self.assertEqual(headers, ["ID", "Name"])
        self.assertEqual(rows, [["A", "x"], ["B", "z"], ["", "blank"]])
        self.assertEqual(message, "去重完成：原 4 行，输出 3 行，重复组 1 个，重复行 2 行，模式：输出去重后的数据")

        headers, rows, message = apply_dedupe_node(
            ["ID", "重复组编号"],
            [["A", "old"], ["A", "old2"], ["B", "unique"]],
            {"key_fields": ["ID"], "output_mode": "原表增加重复标记列", "duplicate_group_field": "重复组编号"},
        )
        self.assertEqual(headers, ["ID", "重复组编号", "重复组编号_2", "重复状态", "组内序号", "重复次数", "是否保留"])
        self.assertEqual(rows[0], ["A", "old", "DUP_0001", "重复", "1", "2", "是"])
        self.assertEqual(message, "去重完成：原 3 行，输出 3 行，重复组 1 个，重复行 2 行，模式：增加重复标记列")

    def test_dedupe_node_stat_output_and_cancel(self):
        headers, rows, message = apply_dedupe_node(
            ["ID", "Name"],
            [["A", "x"], ["A", "y"], ["B", "z"], ["", "blank"]],
            {"key_fields": ["ID"], "empty_key_policy": "空键跳过去重", "output_mode": "输出重复统计表"},
        )
        self.assertEqual(headers, ["ID", "重复次数", "重复组编号", "是否重复"])
        self.assertEqual(rows, [["A", "2", "DUP_0001", "是"], ["B", "1", "", "否"], ["", "1", "", "空键跳过"]])
        self.assertEqual(message, "去重统计：共 3 个统计项，重复组 1 个")

        with self.assertRaisesRegex(RuntimeError, "用户取消"):
            apply_dedupe_node(
                ["A"],
                [["x"]],
                {"key_fields": ["A"]},
                context={"check_cancelled": lambda _index: (_ for _ in ()).throw(RuntimeError("用户取消"))},
            )


if __name__ == "__main__":
    unittest.main()
