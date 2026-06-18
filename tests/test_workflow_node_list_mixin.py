# -*- coding: utf-8 -*-
import unittest
from unittest.mock import patch

from workflow.workflow_node_list_mixin import WorkflowNodeListMixin


class FakeVar:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class FakeListbox:
    def __init__(self):
        self.values = []
        self.selected = []
        self.active = None
        self.seen = []

    def curselection(self):
        return tuple(self.selected)

    def delete(self, start, end):
        self.values = []
        self.selected = []

    def insert(self, end, value):
        self.values.append(value)

    def selection_clear(self, start, end):
        self.selected = []

    def selection_set(self, index):
        self.selected = [index]

    def activate(self, index):
        self.active = index

    def see(self, index):
        self.seen.append(index)


class FakeWindow(WorkflowNodeListMixin):
    def __init__(self):
        self.nodes = []
        self.node_listbox = FakeListbox()
        self.node_type_var = FakeVar("批量替换")
        self.status_var = FakeVar("")
        self.selected_node_index = None
        self.plugin_display_map = {}
        self.plugin_registry = {}
        self.built = []
        self.empty_count = 0
        self.identity_calls = []
        self.tree_identity_calls = []

    def default_name_for_node(self, node_type):
        return {"批量替换": "批量替换"}.get(node_type, node_type)

    def default_config_for_type(self, node_type):
        return {"node_type": node_type}

    def default_config_for_plugin(self, plugin_id):
        return {"plugin_id": plugin_id, "params": {}}

    def ensure_node_identity(self, node, force_new=False):
        self.identity_calls.append((node, force_new))
        if force_new or not node.get("node_id"):
            node["node_id"] = f"id_{len(self.identity_calls)}"

    def ensure_node_tree_identity(self, nodes, force_new=False):
        self.tree_identity_calls.append((nodes, force_new))
        for node in nodes:
            self.ensure_node_identity(node, force_new=force_new)

    def build_node_config(self, idx):
        self.built.append(idx)

    def show_empty_config(self):
        self.empty_count += 1


class WorkflowNodeListMixinTests(unittest.TestCase):
    def test_add_normal_node_appends_and_selects_it(self):
        window = FakeWindow()

        window.add_node()

        self.assertEqual(len(window.nodes), 1)
        self.assertEqual(window.nodes[0]["type"], "批量替换")
        self.assertEqual(window.nodes[0]["name"], "批量替换")
        self.assertEqual(window.nodes[0]["config"], {"node_type": "批量替换"})
        self.assertEqual(window.node_listbox.selected, [0])
        self.assertEqual(window.built, [0])
        self.assertIn("已追加节点：批量替换", window.status_var.get())

    def test_add_plugin_node_inserts_after_selected_node(self):
        window = FakeWindow()
        window.nodes = [{"enabled": True, "type": "批量替换", "name": "旧节点"}]
        window.node_listbox.selected = [0]
        window.node_type_var.set("插件 / Demo")
        window.plugin_display_map = {"插件 / Demo": "demo_plugin"}
        window.plugin_registry = {"demo_plugin": {"info": {"name": "Demo"}}}

        window.add_node()

        self.assertEqual([node["name"] for node in window.nodes], ["旧节点", "Demo"])
        self.assertEqual(window.nodes[1]["type"], "插件节点")
        self.assertEqual(window.nodes[1]["config"]["plugin_id"], "demo_plugin")
        self.assertEqual(window.node_listbox.selected, [1])
        self.assertEqual(window.built, [1])
        self.assertIn("已在当前节点下方插入：Demo", window.status_var.get())

    def test_move_and_toggle_selected_node(self):
        window = FakeWindow()
        window.nodes = [
            {"enabled": True, "type": "A", "name": "A"},
            {"enabled": True, "type": "B", "name": "B"},
            {"enabled": True, "type": "C", "name": "C"},
        ]
        window.node_listbox.selected = [1]

        window.move_node_up()
        self.assertEqual([node["name"] for node in window.nodes], ["B", "A", "C"])
        self.assertEqual(window.node_listbox.selected, [0])
        self.assertEqual(window.built[-1], 0)

        window.move_node_down()
        self.assertEqual([node["name"] for node in window.nodes], ["A", "B", "C"])
        self.assertEqual(window.node_listbox.selected, [1])
        self.assertEqual(window.built[-1], 1)

        window.toggle_node_enabled()
        self.assertFalse(window.nodes[1]["enabled"])
        self.assertIn("[×] 2. B：B", window.node_listbox.values)

    def test_copy_node_forces_new_identity(self):
        window = FakeWindow()
        window.nodes = [{"enabled": True, "type": "批量替换", "name": "源", "node_id": "old"}]
        window.node_listbox.selected = [0]

        window.copy_node()

        self.assertEqual([node["name"] for node in window.nodes], ["源", "源_复制"])
        self.assertEqual(window.nodes[1]["node_id"], "id_1")
        self.assertTrue(any(force_new for _, force_new in window.tree_identity_calls))
        self.assertEqual(window.node_listbox.selected, [1])
        self.assertEqual(window.built, [1])

    def test_clear_nodes_honors_confirmation(self):
        window = FakeWindow()
        window.nodes = [{"enabled": True, "type": "A", "name": "A"}]

        with patch("workflow.workflow_node_list_mixin.messagebox.askyesno", return_value=False):
            window.clear_nodes()
        self.assertEqual(len(window.nodes), 1)
        self.assertEqual(window.empty_count, 0)

        with patch("workflow.workflow_node_list_mixin.messagebox.askyesno", return_value=True):
            window.clear_nodes()
        self.assertEqual(window.nodes, [])
        self.assertEqual(window.empty_count, 1)
        self.assertIsNone(window.selected_node_index)

    def test_update_node_name_refreshes_current_row(self):
        window = FakeWindow()
        window.nodes = [{"enabled": True, "type": "批量替换", "name": "旧名"}]

        window.update_node_name(0, FakeVar(" 新名 "))

        self.assertEqual(window.nodes[0]["name"], "新名")
        self.assertEqual(window.node_listbox.selected, [0])
        self.assertIn("新名", window.node_listbox.values[0])


if __name__ == "__main__":
    unittest.main()
