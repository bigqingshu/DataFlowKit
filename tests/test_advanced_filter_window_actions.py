# -*- coding: utf-8 -*-
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from workflow import advanced_filter_window_actions as actions


class FakeVar:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class FakeListbox:
    def __init__(self, values=None, selection=None):
        self.values = list(values or [])
        self._selection = tuple(selection or [])

    def curselection(self):
        return self._selection

    def delete(self, start, end=None):
        if start == 0:
            self.values = []
            return
        if end is None:
            del self.values[start]
            return
        del self.values[start:end + 1]

    def insert(self, index, value):
        self.values.append(value)

    def get(self, start, end=None):
        if end is None:
            return self.values[start]
        return tuple(self.values[start:])


class FakeCombo(dict):
    def __init__(self):
        super().__init__()
        self["values"] = []


class FakeTree:
    def __init__(self, rows=None, selection=None):
        self.rows = list(rows or [])
        self._selection = tuple(selection or [])

    def selection(self):
        return self._selection

    def index(self, item):
        return int(item)

    def get_children(self):
        return tuple(str(index) for index in range(len(self.rows)))

    def delete(self, *items):
        self.rows = []

    def insert(self, parent, index, values=None):
        self.rows.append(tuple(values or ()))

    def heading(self, col, text=""):
        pass

    def column(self, col, **kwargs):
        pass

    def __setitem__(self, key, value):
        setattr(self, key, value)


class FakeWindow:
    def __init__(self, db_path="fake.db"):
        self.app = type("FakeApp", (), {})()
        self.app.headers = []
        self.app.rows = []
        self.app.raw_data = ""
        self.app.info_var = FakeVar()
        self.app.refresh_tree_called = False
        self.app.refresh_tree = lambda: setattr(self.app, "refresh_tree_called", True)
        self.app.format_db_value = lambda value: "" if value is None else str(value)
        self.app.get_db_path = lambda: db_path
        self.app.get_table_columns = lambda table: ["id", "name"]
        self.app.get_table_names = lambda: ["orders", "people"]

        self.conditions = []
        self.join_rules = []
        self.output_fields = []
        self.field_display_cache = ["orders.id", "orders.person_id", "people.id", "people.name"]
        self.tables_cache = ["orders", "people"]
        self.columns_cache = {}
        self.preview_headers = []
        self.preview_rows = []
        self.filter_field_var = FakeVar("orders.id")
        self.filter_operator_var = FakeVar("包含")
        self.filter_value_var = FakeVar("A")
        self.logic_var = FakeVar("AND")
        self.join_left_var = FakeVar("orders.person_id")
        self.join_operator_var = FakeVar("等于")
        self.join_right_var = FakeVar("people.id")
        self.join_logic_var = FakeVar("AND")
        self.result_limit_var = FakeVar("5000")
        self.max_intermediate_var = FakeVar("200000")
        self.save_table_var = FakeVar("out")
        self.main_table_var = FakeVar("")
        self.add_table_var = FakeVar("people")
        self.status_var = FakeVar()
        self.main_table_combo = FakeCombo()
        self.add_table_combo = FakeCombo()
        self.filter_field_combo = FakeCombo()
        self.join_left_combo = FakeCombo()
        self.join_right_combo = FakeCombo()
        self.conditions_tree = FakeTree()
        self.join_tree = FakeTree()
        self.preview_tree = FakeTree()
        self.available_fields_listbox = FakeListbox(selection=(1, 3))
        self.output_fields_listbox = FakeListbox(selection=(0,))
        self.selected_tables_listbox = FakeListbox(values=["orders"])

    def refresh_conditions_tree(self):
        return actions.refresh_conditions_tree(self)

    def refresh_join_tree(self):
        return actions.refresh_join_tree(self)

    def refresh_output_fields_listbox(self):
        return actions.refresh_output_fields_listbox(self)

    def refresh_preview_tree(self):
        return actions.refresh_preview_tree(self)

    def preview_result(self):
        return actions.preview_result(self)

    def get_output_fields(self):
        return actions.get_output_fields(self)

    def build_result_records(self):
        return actions.build_result_records(self)

    def load_table_records(self, table_name):
        return [{"orders.id": "1", "orders.name": "Alpha"}, {"orders.id": "2", "orders.name": "Beta"}]

    def get_int_setting(self, var, default_value):
        return actions.get_int_setting(var, default_value)

    def get_selected_tables(self):
        return actions.get_selected_tables(self)

    def get_current_selected_source_table(self):
        return actions.get_current_selected_source_table(self)

    def reset_selected_tables_to_main(self):
        return actions.reset_selected_tables_to_main(self)

    def refresh_fields(self):
        return actions.refresh_fields(self)

    def refresh_tables(self):
        self.refresh_tables_called = True

    def remove_invalid_rules_and_outputs(self):
        return actions.remove_invalid_rules_and_outputs(self)

    def export_template_data(self):
        return actions.export_template_data(self)

    def apply_template_data(self, data):
        return actions.apply_template_data(self, data)


class AdvancedFilterWindowActionsTests(unittest.TestCase):
    def test_source_table_actions_refresh_select_and_fields(self):
        window = FakeWindow()

        actions.refresh_tables(window)
        self.assertEqual(window.tables_cache, ["orders", "people"])
        self.assertEqual(window.main_table_combo["values"], ["orders", "people"])
        self.assertEqual(window.main_table_var.get(), "orders")
        self.assertEqual(window.selected_tables_listbox.values, ["orders"])
        self.assertEqual(window.field_display_cache, ["orders.id", "orders.name"])
        self.assertIn("已读取数据库表：2 个", window.status_var.get())

        window.add_table_var.set("people")
        actions.add_selected_table(window)
        self.assertEqual(window.selected_tables_listbox.values, ["orders", "people"])
        self.assertEqual(window.field_display_cache, ["orders.id", "orders.name", "people.id", "people.name"])

        window.selected_tables_listbox._selection = (1,)
        actions.remove_selected_table(window)
        self.assertEqual(window.selected_tables_listbox.values, ["orders"])

        window.selected_tables_listbox._selection = (0,)
        with patch.object(actions.messagebox, "showwarning") as showwarning:
            actions.remove_selected_table(window)
        showwarning.assert_called_once()
        self.assertEqual(window.selected_tables_listbox.values, ["orders"])

    def test_preview_selected_source_table_reads_table_manager(self):
        window = FakeWindow()
        window.main_table_var.set("orders")
        window.columns_cache["orders"] = ["id", "name"]

        class FakeManager:
            def __init__(self, db_path, node_type=""):
                self.db_path = db_path
                self.node_type = node_type

            def read_table(self, table_name, limit=None):
                return {
                    "headers": ["id", "name"],
                    "rows": [["1", "Alpha"]],
                }

        with patch.object(actions, "TableAccessManager", FakeManager):
            actions.preview_selected_source_table(window)

        self.assertEqual(window.preview_headers, ["id", "name"])
        self.assertEqual(window.preview_rows, [["1", "Alpha"]])
        self.assertEqual(window.preview_tree.rows, [("1", "Alpha")])
        self.assertIn("已预览选中表格：orders", window.status_var.get())

    def test_condition_actions_update_state_and_tree(self):
        window = FakeWindow()

        actions.add_condition(window)
        self.assertEqual(window.conditions, [{"field": "orders.id", "op": "包含", "value": "A"}])
        self.assertEqual(window.conditions_tree.rows, [("orders.id", "包含", "A")])
        self.assertEqual(window.filter_value_var.get(), "")

        window.conditions_tree._selection = ("0",)
        actions.delete_selected_condition(window)
        self.assertEqual(window.conditions, [])
        self.assertEqual(window.conditions_tree.rows, [])

        window.filter_field_var.set("")
        with patch.object(actions.messagebox, "showwarning") as showwarning:
            actions.add_condition(window)
        showwarning.assert_called_once()

    def test_join_and_output_actions_update_widgets(self):
        window = FakeWindow()

        actions.add_join_rule(window)
        self.assertEqual(window.join_rules, [{"left": "orders.person_id", "op": "等于", "right": "people.id"}])
        self.assertEqual(window.join_tree.rows, [("orders.person_id", "等于", "people.id")])

        window.join_tree._selection = ("0",)
        actions.delete_selected_join_rule(window)
        self.assertEqual(window.join_rules, [])
        self.assertEqual(window.join_tree.rows, [])

        actions.add_output_fields(window)
        self.assertEqual(window.output_fields, ["orders.person_id", "people.name"])
        self.assertEqual(window.output_fields_listbox.values, ["orders.person_id", "people.name"])

        actions.remove_output_fields(window)
        self.assertEqual(window.output_fields, ["people.name"])
        self.assertEqual(window.output_fields_listbox.values, ["people.name"])

        actions.clear_output_fields(window)
        self.assertEqual(window.output_fields, [])
        self.assertEqual(window.output_fields_listbox.values, [])

    def test_remove_invalid_rules_and_outputs_refreshes_all_widgets(self):
        window = FakeWindow()
        window.conditions = [
            {"field": "orders.id", "op": "等于", "value": "1"},
            {"field": "bad", "op": "等于", "value": "2"},
        ]
        window.join_rules = [
            {"left": "orders.person_id", "op": "等于", "right": "people.id"},
            {"left": "orders.id", "op": "等于", "right": "bad"},
        ]
        window.output_fields = ["people.name", "bad"]

        actions.remove_invalid_rules_and_outputs(window)

        self.assertEqual(window.conditions, [{"field": "orders.id", "op": "等于", "value": "1"}])
        self.assertEqual(window.join_rules, [{"left": "orders.person_id", "op": "等于", "right": "people.id"}])
        self.assertEqual(window.output_fields, ["people.name"])
        self.assertEqual(window.conditions_tree.rows, [("orders.id", "等于", "1")])
        self.assertEqual(window.join_tree.rows, [("orders.person_id", "等于", "people.id")])
        self.assertEqual(window.output_fields_listbox.values, ["people.name"])

    def test_preview_dedupe_and_load_to_main_actions(self):
        window = FakeWindow()
        window.output_fields = ["orders.id", "orders.name"]

        actions.preview_result(window)
        self.assertEqual(window.preview_headers, ["orders.id", "orders.name"])
        self.assertEqual(window.preview_rows, [["1", "Alpha"], ["2", "Beta"]])
        self.assertIn("预览完成：2 行", window.status_var.get())

        window.preview_rows = [["1", "Alpha"], ["1", "Alpha"], ["2", "Beta"]]
        actions.remove_duplicate_preview_rows(window)
        self.assertEqual(window.preview_rows, [["1", "Alpha"], ["2", "Beta"]])
        self.assertIn("删除 1 行", window.status_var.get())

        actions.load_preview_to_main(window)
        self.assertEqual(window.app.headers, ["orders.id", "orders.name"])
        self.assertEqual(window.app.rows, [["1", "Alpha"], ["2", "Beta"]])
        self.assertTrue(window.app.refresh_tree_called)

    def test_save_result_and_template_actions(self):
        with TemporaryDirectory() as temp_dir:
            window = FakeWindow(str(Path(temp_dir) / "advanced_filter.db"))
            window.preview_headers = ["orders.id"]
            window.preview_rows = [["1"], ["2"]]

            with patch.object(actions.messagebox, "showinfo") as showinfo:
                actions.save_result_to_table(window)
        showinfo.assert_called_once()
        self.assertEqual(window.status_var.get(), "保存成功：out，2 行。")
        self.assertTrue(window.refresh_tables_called)

        data = actions.export_template_data(window)
        self.assertEqual(data["main_table"], "")
        self.assertEqual(data["selected_tables"], ["orders"])
        self.assertEqual(data["save_table"], "out")

        actions.apply_template_data(window, {
            "main_table": "orders",
            "selected_tables": ["orders", "missing"],
            "conditions": [{"field": "orders.id", "op": "等于", "value": "1"}],
            "join_rules": [],
            "output_fields": ["orders.name", "missing"],
            "logic": "OR",
            "join_logic": "AND",
            "result_limit": "12",
            "max_intermediate": "34",
            "save_table": "templated",
        })

        self.assertEqual(window.selected_tables_listbox.values, ["orders"])
        self.assertEqual(window.conditions, [{"field": "orders.id", "op": "等于", "value": "1"}])
        self.assertEqual(window.output_fields, ["orders.name"])
        self.assertEqual(window.logic_var.get(), "OR")
        self.assertEqual(window.result_limit_var.get(), "12")
        self.assertEqual(window.save_table_var.get(), "templated")


if __name__ == "__main__":
    unittest.main()
