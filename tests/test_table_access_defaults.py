# -*- coding: utf-8 -*-
import unittest

from workflow.table_access_defaults import build_default_table_access_for_node


def permission_set(read=False, write=False, create=False, append=False, update=False,
                   clear=False, replace=False, alter=False, delete=False, drop=False):
    return {
        "read_table": bool(read),
        "write_table": bool(write),
        "create_table": bool(create),
        "append_rows": bool(append),
        "update_rows": bool(update),
        "clear_table": bool(clear),
        "replace_table": bool(replace),
        "alter_schema": bool(alter),
        "delete_rows": bool(delete),
        "drop_table": bool(drop),
    }


def make_entry(role, table, source_type="SQLite表", is_current_table=False, permissions=None,
               write_mode="", field_mapping=None, log_only=False, table_pattern="", pattern_type="glob",
               declared_by=""):
    return {
        "role": role,
        "table": table,
        "source_type": source_type,
        "is_current_table": bool(is_current_table),
        "permissions": permissions or permission_set(read=True),
        "write_mode": str(write_mode or "").strip(),
        "field_mapping_mode": "by_name",
        "field_mapping": field_mapping or {},
        "log_only": bool(log_only),
        "table_pattern": str(table_pattern or "").strip(),
        "pattern_type": str(pattern_type or "glob").strip(),
        "declared_by": str(declared_by or "").strip(),
    }


def build(node, **kwargs):
    return build_default_table_access_for_node(
        node,
        make_entry,
        permission_set,
        **kwargs,
    )


class TableAccessDefaultsTests(unittest.TestCase):
    def test_base_current_table_entries(self):
        access = build({"type": "新建列", "config": {}})
        self.assertEqual(access["version"], 1)
        self.assertTrue(access["auto_generated"])
        current = access["tables"][0]
        self.assertEqual(current["role"], "current")
        self.assertEqual(current["table"], "__CURRENT_TABLE__")
        self.assertTrue(current["is_current_table"])
        self.assertTrue(current["permissions"]["write_table"])
        self.assertTrue(current["permissions"]["update_rows"])
        self.assertTrue(current["log_only"])

        condition = build({"type": "条件判断节点", "config": {}})["tables"][0]
        self.assertTrue(condition["permissions"]["read_table"])
        self.assertFalse(condition["permissions"]["write_table"])
        self.assertEqual(condition["write_mode"], "read_current_table")

        self.assertEqual(build({"type": "跳转锚点节点", "config": {}})["tables"], [])

    def test_filter_and_lookup_defaults(self):
        access = build({
            "type": "高级筛选",
            "config": {"extra_tables": ["lookup", "中转:tmp", ""]},
        })
        lookup_entries = [entry for entry in access["tables"] if entry["role"] == "lookup"]
        self.assertEqual([entry["table"] for entry in lookup_entries], ["lookup", "中转:tmp"])
        self.assertEqual(lookup_entries[1]["source_type"], "中转副表")

        lookup = build({
            "type": "匹配值输出列名",
            "config": {
                "lookup_table": "dict",
                "lookup_source_type": "SQLite表",
                "lookup_fields": ["编码", "", "名称"],
            },
        })["tables"][-1]
        self.assertEqual(lookup["table"], "dict")
        self.assertEqual(sorted(lookup["field_mapping"]), ["名称", "编码"])

    def test_selected_columns_write_defaults(self):
        access = build(
            {
                "type": "选定列写入指定表",
                "config": {
                    "source_type": "中转副表",
                    "source_transit_table": "input_tmp",
                    "target_type": "SQLite表",
                    "target_table": "target",
                    "enable_write": True,
                    "write_mode": "raw_full",
                },
            },
            normalize_selected_columns_write_mode=lambda mode: "按来源完整结构覆盖" if mode == "raw_full" else mode,
        )
        source = [entry for entry in access["tables"] if entry["role"] == "source"][0]
        target = [entry for entry in access["tables"] if entry["role"] == "target"][0]
        self.assertEqual(source["source_type"], "中转副表")
        self.assertEqual(source["table"], "input_tmp")
        self.assertEqual(target["table"], "target")
        self.assertTrue(target["permissions"]["replace_table"])
        self.assertTrue(target["permissions"]["alter_schema"])
        self.assertEqual(target["write_mode"], "按来源完整结构覆盖")

    def test_group_plugin_loop_and_branch_defaults(self):
        group = build(
            {
                "type": "节点组 / 子工作流",
                "config": {
                    "input_source_type": "SQLite表",
                    "input_sqlite_table": "src",
                    "save_to_transit": True,
                    "output_transit_name": "group_tmp",
                    "output_transit_conflict_mode": "追加模式",
                },
            },
            normalize_group_transit_conflict_mode=lambda mode: "追加" if mode == "追加模式" else mode,
        )
        group_output = [entry for entry in group["tables"] if entry["role"] == "output"][0]
        self.assertTrue(group_output["permissions"]["append_rows"])
        self.assertFalse(group_output["permissions"]["replace_table"])

        plugin = build(
            {
                "type": "插件节点",
                "config": {
                    "plugin_id": "p1",
                    "input_tables": [{"source_type": "SQLite表", "alias": "input", "sqlite_table": "src"}],
                    "save_output_as_transit": True,
                    "transit_name": "plugin_tmp",
                    "transit_conflict_mode": "覆盖",
                    "save_plugin_log_sqlite": True,
                },
            },
            get_plugin_table_access_specs=lambda config: [{
                "role": "declared",
                "table_pattern": "out_*",
                "permissions": {"write_table": True},
            }],
            make_plugin_declared_access_entry=lambda plugin_id, spec: make_entry(
                spec["role"],
                spec.get("table", ""),
                table_pattern=spec.get("table_pattern", ""),
                permissions=permission_set(write=True),
                declared_by=plugin_id,
            ),
        )
        self.assertTrue(any(entry["role"] == "input" and entry["table"] == "src" for entry in plugin["tables"]))
        self.assertTrue(any(entry["role"] == "output" and entry["table"] == "plugin_tmp" for entry in plugin["tables"]))
        self.assertTrue(any(entry["role"] == "sqlite_log" and entry["table"] == "_plugin_log" for entry in plugin["tables"]))
        declared = [entry for entry in plugin["tables"] if entry["declared_by"] == "p1"][0]
        self.assertEqual(declared["table_pattern"], "out_*")

        loop_start = build({
            "type": "循环执行起点",
            "config": {"source_type": "SQLite表", "source_table": "queue", "current_table_name": "cur"},
        })
        self.assertTrue(any(entry["role"] == "loop_current" and entry["table"] == "cur" for entry in loop_start["tables"]))

        loop_judge = build({
            "type": "循环判断回跳",
            "config": {"loop_id": "L1", "result_table_name": ""},
        })
        self.assertTrue(any(entry["role"] == "loop_result" and entry["table"] == "循环结果" for entry in loop_judge["tables"]))
        self.assertTrue(any(entry["role"] == "loop_queue" and entry["table"] == "循环队列_L1" for entry in loop_judge["tables"]))

        branch = build({
            "type": "条件分支跳转",
            "config": {"source_type": "中转副表", "transit_table": "branch_tmp"},
        })
        self.assertEqual(branch["tables"][0]["role"], "current")
        self.assertTrue(any(entry["role"] == "branch_source" and entry["source_type"] == "中转副表" for entry in branch["tables"]))


if __name__ == "__main__":
    unittest.main()
