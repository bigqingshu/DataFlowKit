# -*- coding: utf-8 -*-
import unittest
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


class FakeWindow:
    def __init__(self):
        self.conditions = []
        self.join_rules = []
        self.output_fields = []
        self.field_display_cache = ["orders.id", "orders.person_id", "people.id", "people.name"]
        self.filter_field_var = FakeVar("orders.id")
        self.filter_operator_var = FakeVar("包含")
        self.filter_value_var = FakeVar("A")
        self.join_left_var = FakeVar("orders.person_id")
        self.join_operator_var = FakeVar("等于")
        self.join_right_var = FakeVar("people.id")
        self.conditions_tree = FakeTree()
        self.join_tree = FakeTree()
        self.available_fields_listbox = FakeListbox(selection=(1, 3))
        self.output_fields_listbox = FakeListbox(selection=(0,))

    def refresh_conditions_tree(self):
        return actions.refresh_conditions_tree(self)

    def refresh_join_tree(self):
        return actions.refresh_join_tree(self)

    def refresh_output_fields_listbox(self):
        return actions.refresh_output_fields_listbox(self)


class AdvancedFilterWindowActionsTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
