# -*- coding: utf-8 -*-
import unittest
from unittest.mock import patch

from workflow.workflow_config_ui_helpers_mixin import WorkflowConfigUiHelpersMixin


class FakeVar:
    def __init__(self, value=None):
        self.value = value
        self.callbacks = []

    def get(self):
        return self.value

    def set(self, value):
        self.value = value
        for cb in list(self.callbacks):
            cb()

    def trace_add(self, mode, callback):
        self.callbacks.append(lambda: callback())


class FakeCombo(dict):
    def configure(self, **kwargs):
        self.update(kwargs)


class FakeListbox:
    def __init__(self):
        self.values = []
        self.selected = []

    def delete(self, start, end):
        self.values = []
        self.selected = []

    def insert(self, end, value):
        self.values.append(value)

    def selection_set(self, index):
        self.selected.append(index)


class FakeWindow(WorkflowConfigUiHelpersMixin):
    def __init__(self):
        self.nodes = [{"enabled": True}, {"enabled": False}]
        self.changes = []

    def refresh_node_list(self, select_index=None, reveal=True):
        self.changes.append((select_index, reveal))


class WorkflowConfigUiHelpersMixinTests(unittest.TestCase):
    def test_sync_helpers_update_config(self):
        window = FakeWindow()
        config = {}
        text_var = FakeVar("abc")
        bool_var = FakeVar(True)
        window.sync_var_to_config(text_var, config, "text")
        window.sync_bool_to_config(bool_var, config, "flag")
        text_var.set("def")
        bool_var.set(False)
        self.assertEqual(config, {"text": "def", "flag": False})

    def test_refresh_combo_and_listbox_helpers(self):
        window = FakeWindow()
        combo = FakeCombo()
        var = FakeVar("")
        window.refresh_combo_values(combo, var, ["A", "B"], fallback="B")
        self.assertEqual(combo["values"], ["A", "B"])
        self.assertEqual(var.get(), "B")

        listbox = FakeListbox()
        indices = window.refresh_listbox_values(listbox, ["X", "Y", "Z"], ["Y", "Z"])
        self.assertEqual(indices, [1, 2])
        self.assertEqual(listbox.selected, [1, 2])

    def test_make_node_enabled_var_triggers_refresh(self):
        window = FakeWindow()
        with patch("workflow.workflow_config_ui_helpers_mixin.tk.BooleanVar", new=FakeVar):
            var = window.make_node_enabled_var(1)
            var.set(True)
        self.assertTrue(window.nodes[1]["enabled"])
        self.assertEqual(window.changes[-1], (1, True))


if __name__ == "__main__":
    unittest.main()
