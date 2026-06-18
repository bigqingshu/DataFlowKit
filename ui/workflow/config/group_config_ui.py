# -*- coding: utf-8 -*-
"""Tkinter UI helpers for group/subworkflow node configuration."""

import json
import tkinter as tk
from tkinter import ttk, messagebox as tk_messagebox

from workflow.nodes.group_nodes import (
    apply_group_mapping,
    apply_inferred_group_inputs,
    auto_group_mapping_by_name,
    build_group_output_config_state,
    ensure_group_config_defaults,
    group_input_fields_text,
    group_mapping_detail,
    group_mapping_rows,
    group_mapping_selection_detail,
    group_node_label,
    group_selected_input_state,
    group_source_field_combo_state,
    update_group_input_fields_config,
    use_source_headers_as_group_inputs,
    group_infer_input_apply_decision,
)


def _messagebox(messagebox_module=None):
    return messagebox_module or tk_messagebox


def build_group_node_config(window, config, headers, transit_context=None):
    frame = ttk.LabelFrame(window.config_frame, text="节点组 / 子工作流", padding=8)
    frame.pack(fill=tk.BOTH, expand=True, pady=8)
    ttk.Label(
        frame,
        text="把多个普通节点封装成可复用子工作流。推荐方式：先定义组入口字段，再把当前表/中转副表/SQLite表字段映射到入口字段；组内节点只使用这些标准入口字段。",
        foreground="gray",
        wraplength=1120,
    ).grid(row=0, column=0, columnspan=8, sticky=tk.W, padx=4, pady=(0, 6))

    ensure_group_config_defaults(config)

    name_var = window.add_labeled_entry(frame, "组名称：", config.get("group_name", "节点组"), 1, 0, 26)
    window.sync_var_to_config(name_var, config, "group_name")
    desc_var = window.add_labeled_entry(frame, "说明：", config.get("description", ""), 1, 2, 62)
    window.sync_var_to_config(desc_var, config, "description")

    build_group_input_mapping_section(window, frame, config, headers, transit_context=transit_context, row=2)
    build_group_output_section(window, frame, config, row=3)
    build_group_inner_nodes_section(window, frame, config, row=4)

    ttk.Label(frame, text="提示：推荐组内节点只使用上方定义的标准入口字段；若入口字段留空，则兼容旧版，组内直接处理入口数据源整表。", foreground="gray", wraplength=1120).grid(row=5, column=0, columnspan=8, sticky=tk.W, padx=4, pady=6)
    return frame


def build_group_input_source_controls(window, input_frame, config, transit_context=None):
    source_values = ["当前工作表", "中转副表", "SQLite表"]
    source_type_var = window.add_labeled_combo(input_frame, "入口数据源：", config.get("input_source_type", "当前工作表"), source_values, 0, 0, 16)
    window.sync_var_to_config(source_type_var, config, "input_source_type")

    sqlite_tables = window.get_sqlite_table_names()
    sqlite_var = window.add_labeled_combo(input_frame, "SQLite表：", config.get("input_sqlite_table", sqlite_tables[0] if sqlite_tables else ""), sqlite_tables, 0, 2, 26, readonly=False)
    window.sync_var_to_config(sqlite_var, config, "input_sqlite_table")

    transit_tables = sorted((transit_context or {}).get("transit_tables", {}).keys())
    transit_var = window.add_labeled_combo(input_frame, "中转副表：", config.get("input_transit_table", transit_tables[0] if transit_tables else ""), transit_tables, 0, 4, 26, readonly=False)
    window.sync_var_to_config(transit_var, config, "input_transit_table")
    return {
        "source_type_var": source_type_var,
        "sqlite_var": sqlite_var,
        "transit_var": transit_var,
        "sqlite_tables": sqlite_tables,
        "transit_tables": transit_tables,
    }


def build_group_input_fields_controls(window, input_frame, config, refresh_mapping):
    fields_text = group_input_fields_text(config)
    input_fields_var = window.add_labeled_entry(input_frame, "组入口字段：", fields_text, 1, 0, 70)
    ttk.Label(input_frame, text="留空=兼容旧版，直接把入口数据源整表传入组内；填写后才按映射生成标准入口表。", foreground="gray").grid(row=1, column=2, columnspan=5, sticky=tk.W, padx=4, pady=4)

    def update_input_fields(*_):
        update_group_input_fields_config(config, input_fields_var.get())
        refresh_mapping()

    input_fields_var.trace_add("write", update_input_fields)

    missing_var = window.add_labeled_combo(input_frame, "缺失字段：", config.get("missing_input_policy", "缺失填空"), ["缺失填空", "缺失报错"], 2, 0, 14)
    window.sync_var_to_config(missing_var, config, "missing_input_policy")
    return {"input_fields_var": input_fields_var, "missing_var": missing_var}


def build_group_mapping_tree_control(input_frame):
    mapping_wrap = ttk.Frame(input_frame)
    mapping_wrap.grid(row=3, column=0, columnspan=8, sticky="ew", padx=4, pady=(4, 2))
    mapping_wrap.columnconfigure(0, weight=1)
    mapping_tree = ttk.Treeview(mapping_wrap, columns=("入口字段", "外部字段", "默认值"), show="headings", height=5)
    for col, width in [("入口字段", 180), ("外部字段", 260), ("默认值", 180)]:
        mapping_tree.heading(col, text=col)
        mapping_tree.column(col, width=width, anchor=tk.W, stretch=False)
    mapping_y = ttk.Scrollbar(mapping_wrap, orient=tk.VERTICAL, command=mapping_tree.yview)
    mapping_tree.configure(yscrollcommand=mapping_y.set)
    mapping_tree.grid(row=0, column=0, sticky="ew")
    mapping_y.grid(row=0, column=1, sticky="ns")
    return {"mapping_wrap": mapping_wrap, "mapping_tree": mapping_tree, "mapping_y": mapping_y}


def build_group_mapping_edit_controls(input_frame):
    map_edit = ttk.Frame(input_frame)
    map_edit.grid(row=4, column=0, columnspan=8, sticky=tk.W, padx=4, pady=(2, 4))
    selected_input_var = tk.StringVar(value="")
    source_field_var = tk.StringVar(value="")
    default_value_var = tk.StringVar(value="")
    ttk.Label(map_edit, text="组入口字段：").pack(side=tk.LEFT, padx=(0, 2))
    selected_input_combo = ttk.Combobox(map_edit, textvariable=selected_input_var, values=[], width=20, state="readonly")
    selected_input_combo.pack(side=tk.LEFT, padx=(0, 6))
    ttk.Label(map_edit, text="映射外部字段：").pack(side=tk.LEFT, padx=(0, 2))
    source_field_combo = ttk.Combobox(map_edit, textvariable=source_field_var, values=[], width=30, state="readonly")
    source_field_combo.pack(side=tk.LEFT, padx=(0, 6))
    ttk.Label(map_edit, text="缺失默认值：").pack(side=tk.LEFT, padx=(0, 2))
    default_value_entry = ttk.Entry(map_edit, textvariable=default_value_var, width=20)
    default_value_entry.pack(side=tk.LEFT, padx=(0, 6))
    return {
        "map_edit": map_edit,
        "selected_input_var": selected_input_var,
        "source_field_var": source_field_var,
        "default_value_var": default_value_var,
        "selected_input_combo": selected_input_combo,
        "source_field_combo": source_field_combo,
        "default_value_entry": default_value_entry,
    }


def build_group_mapping_action_buttons(map_edit, apply_mapping, auto_mapping, use_source_headers, infer_inputs):
    buttons = {
        "apply_mapping": ttk.Button(map_edit, text="应用映射", command=apply_mapping),
        "auto_mapping": ttk.Button(map_edit, text="同名自动映射", command=auto_mapping),
        "use_source_headers": ttk.Button(map_edit, text="用来源字段作为入口", command=use_source_headers),
        "infer_inputs": ttk.Button(map_edit, text="从组内节点推导入口字段", command=infer_inputs),
    }
    for button in buttons.values():
        button.pack(side=tk.LEFT, padx=2)
    return buttons


def build_group_input_mapping_section(window, frame, config, headers, transit_context=None, row=2):
    input_frame = ttk.LabelFrame(frame, text="入口字段映射", padding=6)
    input_frame.grid(row=row, column=0, columnspan=8, sticky="ew", padx=4, pady=6)
    input_frame.columnconfigure(1, weight=1)

    callbacks = {}
    source_controls = build_group_input_source_controls(window, input_frame, config, transit_context=transit_context)
    source_type_var = source_controls["source_type_var"]
    sqlite_var = source_controls["sqlite_var"]
    transit_var = source_controls["transit_var"]

    fields_controls = build_group_input_fields_controls(window, input_frame, config, lambda: callbacks["refresh_mapping_tree"]())
    input_fields_var = fields_controls["input_fields_var"]

    tree_controls = build_group_mapping_tree_control(input_frame)
    mapping_tree = tree_controls["mapping_tree"]

    edit_controls = build_group_mapping_edit_controls(input_frame)
    selected_input_var = edit_controls["selected_input_var"]
    source_field_var = edit_controls["source_field_var"]
    default_value_var = edit_controls["default_value_var"]
    selected_input_combo = edit_controls["selected_input_combo"]
    source_field_combo = edit_controls["source_field_combo"]

    def get_source_headers_for_mapping():
        source_type = source_type_var.get() or config.get("input_source_type", "当前工作表")
        return window.get_group_config_source_headers(
            source_type,
            headers,
            transit_context=transit_context,
            transit_name=transit_var.get().strip() or config.get("input_transit_table", ""),
            sqlite_table=sqlite_var.get().strip() or config.get("input_sqlite_table", ""),
        )

    callbacks.update(window.create_group_input_mapping_callbacks(
        config,
        transit_context,
        get_source_headers_for_mapping,
        mapping_tree,
        selected_input_combo,
        selected_input_var,
        source_field_combo,
        source_field_var,
        default_value_var,
        input_fields_var,
    ))
    mapping_tree.bind("<<TreeviewSelect>>", callbacks["on_mapping_select"])
    selected_input_combo.bind("<<ComboboxSelected>>", callbacks["sync_mapping_edit_from_selected"])

    build_group_mapping_action_buttons(
        edit_controls["map_edit"],
        callbacks["apply_mapping_one"],
        callbacks["auto_mapping_by_name"],
        callbacks["use_current_headers_as_inputs"],
        callbacks["infer_inputs_from_inner_nodes"],
    )
    for v in (source_type_var, sqlite_var, transit_var):
        v.trace_add("write", lambda *_: callbacks["refresh_source_field_combo"]())
    callbacks["refresh_mapping_tree"]()
    return input_frame


def build_group_output_section(window, frame, config, row=3):
    output_frame = ttk.LabelFrame(frame, text="输出设置", padding=6)
    output_frame.grid(row=row, column=0, columnspan=8, sticky="ew", padx=4, pady=6)
    output_state = build_group_output_config_state(config)

    main_out_var = window.add_labeled_combo(output_frame, "主输出：", output_state["main_output_mode"], output_state["main_output_choices"], 0, 0, 18)
    window.sync_var_to_config(main_out_var, config, "main_output_mode")
    scope_var = window.add_labeled_combo(output_frame, "组内中转：", output_state["transit_scope"], output_state["transit_scope_choices"], 0, 2, 18)
    window.sync_var_to_config(scope_var, config, "transit_scope")

    save_transit_var = tk.BooleanVar(value=output_state["save_to_transit"])
    ttk.Checkbutton(output_frame, text="同时保存到中转副表", variable=save_transit_var).grid(row=1, column=0, sticky=tk.W, padx=4, pady=4)
    window.sync_bool_to_config(save_transit_var, config, "save_to_transit")
    transit_name_var = window.add_labeled_entry(output_frame, "中转表名：", output_state["output_transit_name"], 1, 1, 24)
    window.sync_var_to_config(transit_name_var, config, "output_transit_name")
    transit_conflict_var = window.add_labeled_combo(output_frame, "同名处理：", output_state["output_transit_conflict_mode"], output_state["output_transit_conflict_choices"], 1, 3, 18)
    window.sync_var_to_config(transit_conflict_var, config, "output_transit_conflict_mode")

    save_sqlite_var = tk.BooleanVar(value=output_state["save_to_sqlite"])
    ttk.Checkbutton(output_frame, text="执行计划时保存到 SQLite", variable=save_sqlite_var).grid(row=2, column=0, sticky=tk.W, padx=4, pady=4)
    window.sync_bool_to_config(save_sqlite_var, config, "save_to_sqlite")
    sqlite_name_var = window.add_labeled_entry(output_frame, "SQLite表名：", output_state["output_sqlite_table"], 2, 1, 24)
    window.sync_var_to_config(sqlite_name_var, config, "output_sqlite_table")
    sqlite_mode_var = window.add_labeled_combo(output_frame, "写入模式：", output_state["output_sqlite_mode"], output_state["output_sqlite_mode_choices"], 2, 3, 20)
    window.sync_var_to_config(sqlite_mode_var, config, "output_sqlite_mode")
    sqlite_preview_var = tk.BooleanVar(value=output_state["sqlite_save_in_preview"])
    ttk.Checkbutton(output_frame, text="预览也允许写 SQLite（慎用）", variable=sqlite_preview_var).grid(row=3, column=0, columnspan=3, sticky=tk.W, padx=4, pady=4)
    window.sync_bool_to_config(sqlite_preview_var, config, "sqlite_save_in_preview")
    ttk.Label(output_frame, text=output_state["hint_text"], foreground="gray").grid(row=3, column=3, columnspan=3, sticky=tk.W, padx=4, pady=4)
    return output_frame


def refresh_group_source_field_combo(source_field_combo, source_field_var, source_headers):
    state = group_source_field_combo_state(source_field_var.get(), source_headers)
    source_field_combo["values"] = state["values"]
    source_field_var.set(state["value"])
    return list(state["values"][1:])


def sync_group_mapping_edit_from_selected(
    config,
    mapping_tree,
    selected_input_var,
    source_field_var,
    default_value_var,
    refresh_source_fields,
):
    key = selected_input_var.get().strip()
    detail = group_mapping_detail(config, key)
    refresh_source_fields()
    source_field_var.set(detail["source_field"])
    default_value_var.set(detail["default_value"])
    for iid in mapping_tree.get_children():
        vals = mapping_tree.item(iid, "values")
        if vals and str(vals[0]) == key:
            mapping_tree.selection_set(iid)
            mapping_tree.focus(iid)
            mapping_tree.see(iid)
            break


def refresh_group_selected_input_combo(config, selected_input_combo, selected_input_var, sync_detail=None):
    state = group_selected_input_state(config, selected_input_var.get().strip())
    fields = state["values"]
    selected_input_combo["values"] = fields
    selected_input_var.set(state["value"])
    if callable(sync_detail):
        sync_detail()
    return fields


def refresh_group_mapping_tree(config, mapping_tree, refresh_selected_inputs):
    mapping_tree.delete(*mapping_tree.get_children())
    for row_values in group_mapping_rows(config):
        mapping_tree.insert("", tk.END, values=row_values)
    refresh_selected_inputs()


def apply_group_mapping_from_controls(config, selected_input_var, source_field_var, default_value_var, refresh_mapping, messagebox_module=None):
    result = apply_group_mapping(
        config,
        selected_input_var.get(),
        source_field_var.get(),
        default_value_var.get(),
    )
    if not result["ok"]:
        _messagebox(messagebox_module).showwarning("提示", result["message"])
        return False
    refresh_mapping()
    return True


def auto_group_mapping_by_name_from_source(config, get_source_headers, refresh_mapping):
    auto_group_mapping_by_name(config, get_source_headers())
    refresh_mapping()
    return True


def use_group_source_headers_as_inputs(config, get_source_headers, set_input_fields_text, refresh_mapping):
    vals = get_source_headers()
    use_source_headers_as_group_inputs(config, vals)
    set_input_fields_text(",".join(vals))
    refresh_mapping()
    return vals


def create_group_input_mapping_callbacks(
    window,
    config,
    transit_context,
    get_source_headers,
    mapping_tree,
    selected_input_combo,
    selected_input_var,
    source_field_combo,
    source_field_var,
    default_value_var,
    input_fields_var,
    messagebox_module=None,
):
    def refresh_source_field_combo():
        return refresh_group_source_field_combo(
            source_field_combo,
            source_field_var,
            get_source_headers(),
        )

    def sync_mapping_edit_from_selected(event=None):
        sync_group_mapping_edit_from_selected(
            config,
            mapping_tree,
            selected_input_var,
            source_field_var,
            default_value_var,
            refresh_source_field_combo,
        )

    def refresh_selected_input_combo(sync_detail=True):
        return refresh_group_selected_input_combo(
            config,
            selected_input_combo,
            selected_input_var,
            sync_detail=sync_mapping_edit_from_selected if sync_detail else None,
        )

    def refresh_mapping_tree():
        refresh_group_mapping_tree(
            config,
            mapping_tree,
            lambda: refresh_selected_input_combo(sync_detail=True),
        )

    def on_mapping_select(event=None):
        sel = mapping_tree.selection()
        if not sel:
            return
        vals = mapping_tree.item(sel[0], "values")
        if not vals:
            return
        detail = group_mapping_selection_detail(vals)
        selected_input_var.set(detail["key"])
        refresh_source_field_combo()
        source_field_var.set(detail["source_field"])
        default_value_var.set(detail["default_value"])

    def apply_mapping_one():
        apply_group_mapping_from_controls(
            config,
            selected_input_var,
            source_field_var,
            default_value_var,
            refresh_mapping_tree,
            messagebox_module=messagebox_module,
        )

    def auto_mapping_by_name():
        auto_group_mapping_by_name_from_source(config, get_source_headers, refresh_mapping_tree)

    def use_current_headers_as_inputs():
        use_group_source_headers_as_inputs(
            config,
            get_source_headers,
            input_fields_var.set,
            refresh_mapping_tree,
        )

    def infer_inputs_from_inner_nodes():
        window.infer_and_apply_group_input_fields_for_config(
            config,
            transit_context,
            get_source_headers,
            input_fields_var.set,
            refresh_mapping_tree,
        )

    return {
        "refresh_source_field_combo": refresh_source_field_combo,
        "refresh_selected_input_combo": refresh_selected_input_combo,
        "sync_mapping_edit_from_selected": sync_mapping_edit_from_selected,
        "refresh_mapping_tree": refresh_mapping_tree,
        "on_mapping_select": on_mapping_select,
        "apply_mapping_one": apply_mapping_one,
        "auto_mapping_by_name": auto_mapping_by_name,
        "use_current_headers_as_inputs": use_current_headers_as_inputs,
        "infer_inputs_from_inner_nodes": infer_inputs_from_inner_nodes,
    }


def infer_and_apply_group_input_fields_for_config(
    window,
    config,
    transit_context,
    get_source_headers,
    set_input_fields_text,
    refresh_mapping,
    messagebox_module=None,
):
    msg = _messagebox(messagebox_module)
    inferred, details = window.infer_group_input_fields_from_nodes(
        config.get("nodes", []),
        context=transit_context,
    )
    detail_text = window.format_group_input_infer_details(inferred, details)
    decision = group_infer_input_apply_decision(config, inferred)
    if decision["action"] == "show_empty":
        msg.showinfo("入口字段推导", decision["message_prefix"] + "\n\n" + detail_text)
        return False

    if decision["action"] == "show_detail":
        answer = msg.askyesnocancel(
            "入口字段推导",
            "已从组内节点推导出入口字段：\n"
            + ", ".join(inferred)
            + "\n\n是否覆盖现有组入口字段？\n\n"
            + "是：覆盖现有入口字段\n"
            + "否：合并到现有入口字段\n"
            + "取消：只查看结果，不应用"
        )
        if answer is None:
            msg.showinfo("入口字段推导明细", detail_text)
            return False
        decision = group_infer_input_apply_decision(config, inferred, answer=answer)

    source_headers = get_source_headers()
    new_fields = apply_inferred_group_inputs(config, inferred, source_headers, merge=decision["merge"])
    set_input_fields_text(",".join(new_fields))
    refresh_mapping()
    msg.showinfo("入口字段推导完成", detail_text)
    return True


def build_group_inner_nodes_section(window, frame, config, row, messagebox_module=None):
    msg = _messagebox(messagebox_module)
    inner_frame = ttk.LabelFrame(frame, text="组内节点", padding=6)
    inner_frame.grid(row=row, column=0, columnspan=8, sticky="nsew", padx=4, pady=6)
    inner_frame.columnconfigure(0, weight=1)
    inner_frame.rowconfigure(1, weight=1)

    add_row = ttk.Frame(inner_frame)
    add_row.grid(row=0, column=0, sticky="ew", pady=(0, 4))
    inner_type_var = tk.StringVar(value="批量替换")
    inner_values = window.get_group_inner_node_type_values()
    ttk.Combobox(add_row, textvariable=inner_type_var, values=inner_values, width=26, state="readonly").pack(side=tk.LEFT, padx=(0, 4))

    list_wrap = ttk.Frame(inner_frame)
    list_wrap.grid(row=1, column=0, sticky="nsew")
    list_wrap.columnconfigure(0, weight=1)
    list_wrap.rowconfigure(0, weight=1)
    group_list = tk.Listbox(list_wrap, height=9, exportselection=False)
    yscroll = ttk.Scrollbar(list_wrap, orient=tk.VERTICAL, command=group_list.yview)
    group_list.configure(yscrollcommand=yscroll.set)
    group_list.grid(row=0, column=0, sticky="nsew")
    yscroll.grid(row=0, column=1, sticky="ns")

    def refresh_group_list(select_idx=None):
        group_list.delete(0, tk.END)
        for i, n in enumerate(config.setdefault("nodes", [])):
            group_list.insert(tk.END, group_node_label(i, n))
        if select_idx is not None and 0 <= select_idx < len(config.get("nodes", [])):
            group_list.selection_set(select_idx)
            group_list.activate(select_idx)

    def get_group_selected_index():
        sel = group_list.curselection()
        return int(sel[0]) if sel else None

    def add_inner_node():
        try:
            select_idx = window.add_group_inner_node_to_config(config, inner_type_var.get())
            refresh_group_list(select_idx)
        except Exception as e:
            msg.showerror("添加失败", str(e))

    def apply_inner_action(action, delta=0):
        i = get_group_selected_index()
        select_idx = window.apply_group_inner_node_list_action_to_config(config, i, action, delta=delta)
        refresh_group_list(select_idx)

    def edit_inner_json():
        i = get_group_selected_index()
        nodes = config.setdefault("nodes", [])
        if i is None:
            msg.showwarning("提示", "请先选择一个组内节点。")
            return
        win = tk.Toplevel(window.window)
        win.title("编辑组内节点 JSON")
        win.geometry("760x560")
        txt = tk.Text(win, wrap="none")
        txt.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        txt.insert("1.0", json.dumps(nodes[i], ensure_ascii=False, indent=2))
        btns = ttk.Frame(win)
        btns.pack(fill=tk.X, padx=8, pady=(0, 8))

        def save_json():
            try:
                window.save_group_inner_node_json_text(config, i, txt.get("1.0", tk.END))
                refresh_group_list(i)
                win.destroy()
            except Exception as e:
                msg.showerror("JSON错误", str(e))

        ttk.Button(btns, text="保存", command=save_json).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="取消", command=win.destroy).pack(side=tk.LEFT, padx=4)

    ttk.Button(add_row, text="添加内部节点", command=add_inner_node).pack(side=tk.LEFT, padx=2)
    ttk.Button(add_row, text="保存组模板", command=lambda: window.save_group_template_from_config(config)).pack(side=tk.LEFT, padx=2)
    ttk.Button(add_row, text="载入组模板", command=lambda: window.load_group_template_into_config(config)).pack(side=tk.LEFT, padx=2)
    ttk.Button(add_row, text="打开groups目录", command=window.open_group_dir).pack(side=tk.LEFT, padx=2)

    btn_row = ttk.Frame(inner_frame)
    btn_row.grid(row=2, column=0, sticky=tk.W, pady=(4, 0))
    for text_, cmd in [
        ("删除", lambda: apply_inner_action("delete")),
        ("上移", lambda: apply_inner_action("move", delta=-1)),
        ("下移", lambda: apply_inner_action("move", delta=1)),
        ("复制", lambda: apply_inner_action("copy")),
        ("启用/禁用", lambda: apply_inner_action("toggle")),
        ("编辑JSON", edit_inner_json),
    ]:
        ttk.Button(btn_row, text=text_, command=cmd).pack(side=tk.LEFT, padx=2)

    refresh_group_list()
    return inner_frame
