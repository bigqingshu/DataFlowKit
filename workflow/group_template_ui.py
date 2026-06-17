# -*- coding: utf-8 -*-
"""Group/subworkflow template and list-action helpers."""

import copy
import os
from datetime import datetime
from tkinter import filedialog as tk_filedialog
from tkinter import messagebox as tk_messagebox
from tkinter import simpledialog as tk_simpledialog

from workflow.nodes.group_nodes import parse_group_input_fields


def _messagebox(messagebox_module=None):
    return messagebox_module or tk_messagebox


def _filedialog(filedialog_module=None):
    return filedialog_module or tk_filedialog


def _simpledialog(simpledialog_module=None):
    return simpledialog_module or tk_simpledialog


def build_group_node_from_selection(name, selected_nodes):
    return {
        "enabled": True,
        "type": "节点组 / 子工作流",
        "name": name,
        "config": {
            "group_name": name,
            "description": "由主工作流节点合并生成",
            "input_source_type": "当前工作表",
            "input_sqlite_table": "",
            "input_transit_table": "",
            "input_fields": [],
            "input_mapping": {},
            "input_defaults": {},
            "missing_input_policy": "缺失填空",
            "nodes": selected_nodes,
            "transit_scope": "组内中转私有",
            "allow_loop_nodes": False,
            "main_output_mode": "输出为当前工作表",
            "save_to_transit": False,
            "output_transit_name": name,
            "output_transit_conflict_mode": "覆盖整表",
            "save_to_sqlite": False,
            "output_sqlite_table": name,
            "output_sqlite_mode": "自动加时间戳新表",
            "sqlite_save_in_preview": False,
        },
    }


def validate_group_template_data(data):
    if not isinstance(data, dict):
        return False, "组模板内容不是 JSON 对象。"
    if data.get("template_type") != "workflow_group":
        return False, "template_type 不是 workflow_group。"
    if not isinstance(data.get("nodes"), list):
        return False, "nodes 字段不存在或不是列表。"
    return True, ""


def build_group_template_data(config, group_name=None):
    name = str(group_name or config.get("group_name") or "节点组").strip() or "节点组"
    return {
        "template_type": "workflow_group",
        "version": "2.0",
        "group_name": name,
        "description": config.get("description", ""),
        "input_source_type": config.get("input_source_type", "当前工作表"),
        "input_sqlite_table": config.get("input_sqlite_table", ""),
        "input_transit_table": config.get("input_transit_table", ""),
        "input_fields": parse_group_input_fields(config),
        "input_mapping": config.get("input_mapping", {}),
        "input_defaults": config.get("input_defaults", {}),
        "missing_input_policy": config.get("missing_input_policy", "缺失填空"),
        "transit_scope": config.get("transit_scope", "组内中转私有"),
        "main_output_mode": config.get("main_output_mode", "输出为当前工作表"),
        "save_to_transit": bool(config.get("save_to_transit", False)),
        "output_transit_name": config.get("output_transit_name", name),
        "output_transit_conflict_mode": config.get("output_transit_conflict_mode", "覆盖整表"),
        "save_to_sqlite": bool(config.get("save_to_sqlite", False)),
        "output_sqlite_table": config.get("output_sqlite_table", name),
        "output_sqlite_mode": config.get("output_sqlite_mode", "自动加时间戳新表"),
        "sqlite_save_in_preview": bool(config.get("sqlite_save_in_preview", False)),
        "nodes": config.get("nodes", []),
    }


def group_config_from_template_data(data):
    ok, reason = validate_group_template_data(data)
    if not ok:
        raise ValueError(reason)
    return {
        "group_name": data.get("group_name", "节点组"),
        "description": data.get("description", ""),
        "input_source_type": data.get("input_source_type", "当前工作表"),
        "input_sqlite_table": data.get("input_sqlite_table", ""),
        "input_transit_table": data.get("input_transit_table", ""),
        "input_fields": data.get("input_fields", []),
        "input_mapping": data.get("input_mapping", {}),
        "input_defaults": data.get("input_defaults", {}),
        "missing_input_policy": data.get("missing_input_policy", "缺失填空"),
        "transit_scope": data.get("transit_scope", "组内中转私有"),
        "allow_loop_nodes": False,
        "main_output_mode": data.get("main_output_mode", "输出为当前工作表"),
        "save_to_transit": bool(data.get("save_to_transit", False)),
        "output_transit_name": data.get("output_transit_name", data.get("group_name", "节点组结果")),
        "output_transit_conflict_mode": data.get("output_transit_conflict_mode", "覆盖整表"),
        "save_to_sqlite": bool(data.get("save_to_sqlite", False)),
        "output_sqlite_table": data.get("output_sqlite_table", data.get("group_name", "节点组结果")),
        "output_sqlite_mode": data.get("output_sqlite_mode", "自动加时间戳新表"),
        "sqlite_save_in_preview": bool(data.get("sqlite_save_in_preview", False)),
        "nodes": data.get("nodes", []),
    }


def merge_selected_nodes_to_group(window, messagebox_module=None, simpledialog_module=None, now_factory=None):
    msg = _messagebox(messagebox_module)
    dialog = _simpledialog(simpledialog_module)
    sels = sorted(int(i) for i in window.node_listbox.curselection())
    if len(sels) < 2:
        msg.showwarning("提示", "请先在节点列表中选择至少 2 个连续或多个节点，再合并为组。")
        return False
    selected_nodes = [copy.deepcopy(window.nodes[i]) for i in sels]
    for node in selected_nodes:
        if node.get("type") in ("循环执行起点", "循环判断回跳"):
            msg.showwarning("暂不支持", "第一版节点组不支持把循环执行起点 / 循环判断回跳合并进组。")
            return False
    now = now_factory() if callable(now_factory) else datetime.now()
    name = dialog.askstring("节点组名称", "请输入节点组名称：", initialvalue=f"节点组_{now.strftime('%H%M%S')}", parent=window.window)
    if not name:
        return False
    group_node = build_group_node_from_selection(name, selected_nodes)
    insert_at = sels[0]
    for i in reversed(sels):
        del window.nodes[i]
    window.nodes.insert(insert_at, group_node)
    window.refresh_node_list(select_index=insert_at, reveal=True)
    window.build_node_config(insert_at)
    window.status_var.set(f"已合并 {len(selected_nodes)} 个节点为组：{name}")
    return True


def expand_selected_group(window, messagebox_module=None):
    msg = _messagebox(messagebox_module)
    idx = window.get_selected_node_index()
    if idx is None:
        return False
    node = window.nodes[idx]
    if node.get("type") != "节点组 / 子工作流":
        msg.showwarning("提示", "当前选中的不是节点组。")
        return False
    inner_nodes = copy.deepcopy(node.get("config", {}).get("nodes", []))
    if not inner_nodes:
        msg.showwarning("提示", "该节点组内部没有节点。")
        return False
    if not msg.askyesno("确认展开", f"是否将节点组【{node.get('name','节点组')}】展开为 {len(inner_nodes)} 个普通节点？"):
        return False
    window.nodes[idx:idx + 1] = inner_nodes
    window.refresh_node_list(select_index=idx, reveal=True)
    window.rebuild_current_config()
    window.status_var.set(f"已展开节点组：{node.get('name','节点组')}")
    return True


def get_group_dir(window, get_app_dir):
    base_dir = getattr(window.app, "app_dir", get_app_dir())
    group_dir = os.path.join(base_dir, "groups")
    os.makedirs(group_dir, exist_ok=True)
    return group_dir


def save_group_template_from_config(window, config, atomic_write_json, messagebox_module=None, filedialog_module=None):
    msg = _messagebox(messagebox_module)
    dialog = _filedialog(filedialog_module)
    os.makedirs(window.group_dir, exist_ok=True)
    default_name = window.sanitize_plan_file_name(config.get("group_name") or "节点组") + ".group.json"
    path = dialog.asksaveasfilename(
        title="保存节点组模板",
        initialdir=window.group_dir,
        initialfile=default_name,
        defaultextension=".json",
        filetypes=[("节点组模板", "*.json"), ("所有文件", "*.*")],
    )
    if not path:
        return False
    group_name = os.path.splitext(os.path.basename(path))[0].replace(".group", "").strip() or config.get("group_name") or "节点组"
    data = window.build_group_template_data(config, group_name=group_name)
    try:
        atomic_write_json(path, data)
        config["group_name"] = data.get("group_name", group_name)
        window.status_var.set(f"节点组模板已保存：{path}")
        return True
    except Exception as e:
        msg.showerror("保存失败", str(e))
        return False


def load_group_template_dialog(window, load_json_file_with_recovery, messagebox_module=None, filedialog_module=None):
    msg = _messagebox(messagebox_module)
    dialog = _filedialog(filedialog_module)
    os.makedirs(window.group_dir, exist_ok=True)
    path = dialog.askopenfilename(
        title="载入节点组模板",
        initialdir=window.group_dir,
        filetypes=[("节点组模板", "*.json"), ("所有文件", "*.*")],
    )
    if not path:
        return None
    try:
        data = load_json_file_with_recovery(path, parent=window.window)
        ok, reason = window.validate_group_template_data(data)
        if not ok:
            raise ValueError(reason)
        window.status_var.set(f"节点组模板已载入：{path}")
        return data
    except Exception as e:
        msg.showerror("载入失败", str(e))
        return None


def open_group_dir(window, messagebox_module=None):
    msg = _messagebox(messagebox_module)
    os.makedirs(window.group_dir, exist_ok=True)
    try:
        if hasattr(os, "startfile"):
            os.startfile(window.group_dir)
        else:
            msg.showinfo("groups目录", window.group_dir)
        return True
    except Exception as e:
        msg.showerror("打开失败", f"无法打开 groups 目录：\n{window.group_dir}\n\n{e}")
        return False
