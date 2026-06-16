# -*- coding: utf-8 -*-
import unittest

from workflow.table_access_window_ui import (
    clear_field_mapping,
    delete_field_mapping_entry,
    field_mapping_item,
    field_mapping_mode_display,
    field_mapping_mode_value,
    load_field_form,
    render_field_mapping_tree,
    render_table_access_tree,
    reset_field_form,
    selected_field_key,
    upsert_field_mapping_entry,
)


class DummyTree:
    def __init__(self):
        self.rows = {}
        self.selected = None
        self.focused = None

    def delete(self, *items):
        if not items:
            return
        for item in items:
            self.rows.pop(item, None)

    def get_children(self):
        return list(self.rows)

    def insert(self, parent, index, iid=None, values=()):
        self.rows[str(iid)] = tuple(values)

    def selection_set(self, iid):
        self.selected = str(iid)

    def focus(self, iid):
        self.focused = str(iid)


class DummyVar:
    def __init__(self, value=None):
        self.value = value

    def set(self, value):
        self.value = value

    def get(self):
        return self.value


class TableAccessWindowUiTests(unittest.TestCase):
    def test_mode_display_and_value(self):
        self.assertEqual(field_mapping_mode_display({"field_mapping_mode": "by_order"}), "按列顺序")
        self.assertEqual(field_mapping_mode_display({"field_mapping_mode": "manual"}), "手动")
        self.assertEqual(field_mapping_mode_display({"field_mapping_mode": "by_name"}), "按字段名")
        self.assertEqual(field_mapping_mode_value("按列顺序"), "by_order")
        self.assertEqual(field_mapping_mode_value("手动"), "manual")
        self.assertEqual(field_mapping_mode_value("按字段名"), "by_name")

    def test_render_table_and_field_trees(self):
        table_tree = DummyTree()
        entries = [{
            "role": "target",
            "table": "src",
            "permissions": {"read_table": True},
            "write_mode": "append",
        }]
        selected = render_table_access_tree(
            table_tree,
            entries,
            table_label=lambda entry: entry["table"],
            operation_summary=lambda entry: "读表",
            permission_summary=lambda entry: "读表",
            write_mode_text=lambda mode: "追加行",
            entry_status=lambda entry: "只读",
            select_index=0,
        )
        self.assertEqual(selected, 0)
        self.assertEqual(table_tree.rows["0"], ("target", "src", "读表", "否", "读表", "追加行", "只读"))
        self.assertEqual(table_tree.selected, "0")

        field_tree = DummyTree()
        entry = {
            "field_mapping": {
                "a": {
                    "source_index": 1,
                    "source_field": "A",
                    "target_index": 2,
                    "target_field": "B",
                    "permissions": {"read_field": True, "write_field": False},
                }
            }
        }
        keys = render_field_mapping_tree(
            field_tree,
            entry,
            bool_text=lambda value: "是" if value else "否",
            permission_status=lambda item: "只读",
        )
        self.assertEqual(keys, ["a"])
        self.assertEqual(field_tree.rows["0"], (1, "A", 2, "B", "是", "否", "否", "否", "只读"))

    def test_field_form_and_mapping_operations(self):
        vars_ = {
            "source": DummyVar(),
            "target": DummyVar(),
            "source_index": DummyVar(),
            "target_index": DummyVar(),
            "perms": {
                "read_field": DummyVar(False),
                "write_field": DummyVar(False),
                "create_field": DummyVar(False),
                "protect_field": DummyVar(False),
            },
        }
        item = {
            "source_field": "A",
            "target_field": "B",
            "source_index": "1",
            "target_index": "2",
            "permissions": {"read_field": True, "protect_field": True},
        }
        load_field_form(
            item,
            vars_["source"],
            vars_["target"],
            vars_["source_index"],
            vars_["target_index"],
            vars_["perms"],
        )
        self.assertEqual(vars_["source"].get(), "A")
        self.assertTrue(vars_["perms"]["read_field"].get())
        self.assertTrue(vars_["perms"]["protect_field"].get())

        reset_field_form(
            vars_["source"],
            vars_["target"],
            vars_["source_index"],
            vars_["target_index"],
            vars_["perms"],
            write_enabled=True,
        )
        self.assertEqual(vars_["source"].get(), "")
        self.assertTrue(vars_["perms"]["read_field"].get())
        self.assertTrue(vars_["perms"]["write_field"].get())
        self.assertFalse(vars_["perms"]["protect_field"].get())

        entry = {}
        key = upsert_field_mapping_entry(
            entry,
            None,
            " A ",
            " B ",
            "1",
            "2",
            "by_name",
            {"read_field": True},
            lambda mapping, source, target: "generated",
        )
        self.assertEqual(key, "generated")
        self.assertEqual(field_mapping_item(entry, "generated")["source_field"], "A")
        self.assertEqual(selected_field_key(["0"], ["generated"]), "generated")
        self.assertTrue(delete_field_mapping_entry(entry, "generated"))
        self.assertEqual(entry["field_mapping"], {})

        entry["field_mapping"] = {"x": {"target_field": "X"}}
        clear_field_mapping(entry)
        self.assertEqual(entry["field_mapping"], {})


if __name__ == "__main__":
    unittest.main()
