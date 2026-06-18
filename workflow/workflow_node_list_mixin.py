# -*- coding: utf-8 -*-
"""Node list selection, refresh, and mutation helpers for workflow windows."""

import copy
import tkinter as tk
from tkinter import messagebox


class WorkflowNodeListMixin:
    """Compatibility methods for editing the workflow node list."""

    def get_selected_node_index(self):
        sel = self.node_listbox.curselection()
        if not sel:
            return None
        return sel[0]

    def on_node_select(self, event=None):
        idx = self.get_selected_node_index()
        self.selected_node_index = idx
        self.rebuild_current_config()

    def rebuild_current_config(self):
        idx = self.get_selected_node_index()
        if idx is None or idx < 0 or idx >= len(self.nodes):
            self.show_empty_config()
            return
        self.build_node_config(idx)

    def refresh_node_list(self, select_index=None, reveal=True):
        self.ensure_node_tree_identity(self.nodes)
        selected = self.get_selected_node_index() if select_index is None else select_index
        self.node_listbox.delete(0, tk.END)
        for idx, node in enumerate(self.nodes, start=1):
            mark = "√" if node.get("enabled", True) else "×"
            self.node_listbox.insert(tk.END, f"[{mark}] {idx}. {node.get('type')}：{node.get('name', '')}")
        if selected is not None and self.nodes:
            selected = min(selected, len(self.nodes) - 1)
            self.selected_node_index = selected
            self.node_listbox.selection_clear(0, tk.END)
            self.node_listbox.selection_set(selected)
            self.node_listbox.activate(selected)
            if reveal:
                self.node_listbox.see(selected)
        elif not self.nodes:
            self.selected_node_index = None

    def add_node(self):
        node_type = self.node_type_var.get()
        if node_type in getattr(self, "plugin_display_map", {}):
            plugin_id = self.plugin_display_map[node_type]
            plugin_info = self.plugin_registry.get(plugin_id, {}).get("info", {})
            node = {
                "enabled": True,
                "type": "插件节点",
                "name": plugin_info.get("name", plugin_id),
                "config": self.default_config_for_plugin(plugin_id),
            }
        else:
            node = {
                "enabled": True,
                "type": node_type,
                "name": self.default_name_for_node(node_type),
                "config": self.default_config_for_type(node_type),
            }
        self.ensure_node_identity(node)
        selected = self.node_listbox.curselection()
        insert_at = int(selected[0]) + 1 if len(selected) == 1 else len(self.nodes)
        self.nodes.insert(insert_at, node)
        self.refresh_node_list(select_index=insert_at, reveal=True)
        self.build_node_config(insert_at)
        if len(selected) == 1:
            self.status_var.set(f"已在当前节点下方插入：{node.get('name', node.get('type', '节点'))}")
        else:
            self.status_var.set(f"已追加节点：{node.get('name', node.get('type', '节点'))}")

    def delete_node(self):
        idx = self.get_selected_node_index()
        if idx is None:
            return
        del self.nodes[idx]
        self.refresh_node_list()
        self.rebuild_current_config()

    def move_node_up(self):
        idx = self.get_selected_node_index()
        if idx is None or idx <= 0:
            return
        self.nodes[idx - 1], self.nodes[idx] = self.nodes[idx], self.nodes[idx - 1]
        self.refresh_node_list(select_index=idx - 1, reveal=True)
        self.rebuild_current_config()

    def move_node_down(self):
        idx = self.get_selected_node_index()
        if idx is None or idx >= len(self.nodes) - 1:
            return
        self.nodes[idx + 1], self.nodes[idx] = self.nodes[idx], self.nodes[idx + 1]
        self.refresh_node_list(select_index=idx + 1, reveal=True)
        self.rebuild_current_config()

    def toggle_node_enabled(self):
        idx = self.get_selected_node_index()
        if idx is None:
            return
        self.nodes[idx]["enabled"] = not self.nodes[idx].get("enabled", True)
        self.refresh_node_list(select_index=idx, reveal=True)

    def copy_node(self):
        idx = self.get_selected_node_index()
        if idx is None:
            return
        new_node = copy.deepcopy(self.nodes[idx])
        new_node["name"] = f"{new_node.get('name', new_node.get('type'))}_复制"
        self.ensure_node_tree_identity([new_node], force_new=True)
        self.nodes.insert(idx + 1, new_node)
        self.refresh_node_list(select_index=idx + 1, reveal=True)
        self.rebuild_current_config()

    def clear_nodes(self):
        if self.nodes and not messagebox.askyesno("确认", "是否清空所有计划节点？"):
            return
        self.nodes.clear()
        self.refresh_node_list()
        self.show_empty_config()

    def update_node_name(self, idx, name_var):
        if 0 <= idx < len(self.nodes):
            self.nodes[idx]["name"] = name_var.get().strip() or self.nodes[idx]["type"]
            self.refresh_node_list(select_index=idx, reveal=True)
