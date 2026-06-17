# -*- coding: utf-8 -*-
"""Tkinter UI helpers for loop, jump, and condition workflow node configurations."""

from datetime import datetime
import tkinter as tk
from tkinter import ttk


def _sync_vars(window, config, pairs):
    for var, key in pairs:
        window.sync_var_to_config(var, config, key)


def get_loop_source_headers_for_config(window, config, headers, transit_context, source_type_var, source_table_var, transit_var):
    source_type = source_type_var.get() or config.get("source_type", "当前表")
    if source_type == "SQLite表":
        table = source_table_var.get().strip() or config.get("source_table", "")
        try:
            return window.app.get_table_columns(table), f"SQLite:{table}" if table else "SQLite"
        except Exception:
            return [], f"SQLite:{table}" if table else "SQLite"
    if source_type == "中转副表":
        name = transit_var.get().strip() or config.get("transit_table", "")
        item = (transit_context or {}).get("transit_tables", {}).get(name, {})
        return list(item.get("headers", []) or []), f"中转:{name}" if name else "中转"
    return list(headers), "当前表"


def build_loop_start_config(window, config, headers, transit_context=None):
    frame = ttk.LabelFrame(window.config_frame, text="循环执行起点节点", padding=8)
    frame.pack(fill=tk.BOTH, expand=True, pady=8)
    ttk.Label(
        frame,
        text="从循环队列表中取第一条标志为 0 的数据，写入当前循环项表，并把标志改为 1。配合【循环判断回跳】可按行循环执行后续节点。",
        foreground="gray",
        wraplength=1050,
    ).grid(row=0, column=0, columnspan=6, sticky=tk.W, padx=4, pady=(0, 6))

    loop_var = window.add_labeled_entry(frame, "循环名称/ID：", config.get("loop_id", "loop"), 1, 0, 24)
    source_type_var = window.add_labeled_combo(frame, "来源类型：", config.get("source_type", "当前表"), ["当前表", "SQLite表", "中转副表"], 1, 2, 16)
    _sync_vars(window, config, [(loop_var, "loop_id"), (source_type_var, "source_type")])

    table_names = window.get_sqlite_table_names()
    source_table_var = window.add_labeled_combo(
        frame,
        "SQLite来源表：",
        config.get("source_table", table_names[0] if table_names else ""),
        table_names,
        2,
        0,
        28,
        readonly=False,
    )
    transit_names = sorted((transit_context or {}).get("transit_tables", {}).keys())
    transit_var = window.add_labeled_combo(
        frame,
        "中转副表：",
        config.get("transit_table", transit_names[0] if transit_names else ""),
        transit_names,
        2,
        2,
        28,
        readonly=False,
    )
    _sync_vars(window, config, [(source_table_var, "source_table"), (transit_var, "transit_table")])

    loop_source_headers, loop_source_name = get_loop_source_headers_for_config(
        window,
        config,
        headers,
        transit_context,
        source_type_var,
        source_table_var,
        transit_var,
    )

    flag_var = window.add_labeled_entry(frame, "执行标志字段：", config.get("flag_field", "执行标志"), 3, 0, 18)
    init_var = window.add_labeled_combo(
        frame,
        "标志初始化：",
        config.get("init_flag_mode", "空值填0，非0不执行"),
        ["空值填0，非0不执行", "强制重置全部为0", "保留已有标志位"],
        3,
        2,
        22,
    )
    _sync_vars(window, config, [(flag_var, "flag_field"), (init_var, "init_flag_mode")])

    boundary_var = window.add_labeled_combo(
        frame,
        "数据边界：",
        config.get("boundary_mode", "整体表格数据边界"),
        ["整体表格数据边界", "指定参考列数据边界", "手动指定行数"],
        4,
        0,
        22,
    )
    reference_var, reference_combo = window.add_labeled_combo_control(
        frame,
        "参考列：",
        config.get("reference_field", loop_source_headers[0] if loop_source_headers else ""),
        loop_source_headers,
        4,
        2,
        22,
        readonly=False,
    )
    count_var = window.add_labeled_entry(frame, "手动行数：", config.get("manual_count", "1"), 4, 4, 10)
    _sync_vars(window, config, [(boundary_var, "boundary_mode"), (reference_var, "reference_field"), (count_var, "manual_count")])

    out_var = window.add_labeled_entry(frame, "当前循环项中转名：", config.get("current_table_name", "当前循环项"), 5, 0, 24)
    max_var = window.add_labeled_entry(frame, "最大循环次数：", config.get("max_loop_count", "10000"), 5, 2, 12)
    running_var = window.add_labeled_combo(
        frame,
        "发现执行中1：",
        config.get("running_flag_policy", "执行中1标记失败3"),
        ["执行中1标记失败3", "执行中1重置为0", "保持不动"],
        5,
        4,
        18,
    )
    _sync_vars(window, config, [(out_var, "current_table_name"), (max_var, "max_loop_count"), (running_var, "running_flag_policy")])

    output_current_var = tk.BooleanVar(value=bool(config.get("output_current_as_table", True)))
    ttk.Checkbutton(frame, text="把当前循环项作为当前表传给后续节点", variable=output_current_var).grid(
        row=6,
        column=0,
        columnspan=3,
        sticky=tk.W,
        padx=4,
        pady=4,
    )
    window.sync_bool_to_config(output_current_var, config, "output_current_as_table")
    ttk.Label(
        frame,
        text="提示：一般应保持勾选。若关闭，循环体每轮会继续处理完整当前表，可能出现 4 行任务被执行成 4×4 行的效果。",
        foreground="gray",
        wraplength=900,
    ).grid(row=6, column=3, columnspan=3, sticky=tk.W, padx=4, pady=4)

    field_label = ttk.Label(frame, text=f"读取字段（来源：{loop_source_name}）：", foreground="gray")
    field_label.grid(row=7, column=0, sticky=tk.W, padx=4, pady=(8, 2))
    lb_frame = ttk.Frame(frame)
    lb_frame.grid(row=8, column=0, columnspan=6, sticky=tk.W, padx=4, pady=4)
    lb = tk.Listbox(lb_frame, selectmode=tk.MULTIPLE, height=min(10, max(4, len(loop_source_headers))), width=56, exportselection=False)
    scr = ttk.Scrollbar(lb_frame, orient=tk.VERTICAL, command=lb.yview)
    lb.configure(yscrollcommand=scr.set)
    selected = config.get("fields") or list(loop_source_headers[:3])
    for index, header in enumerate(loop_source_headers):
        lb.insert(tk.END, header)
        if header in selected:
            lb.selection_set(index)
    lb.pack(side=tk.LEFT, fill=tk.BOTH)
    scr.pack(side=tk.LEFT, fill=tk.Y)

    def update_fields(event=None):
        config["fields"] = [lb.get(index) for index in lb.curselection()]

    lb.bind("<<ListboxSelect>>", update_fields)

    def refresh_loop_source_fields(*_):
        config["source_type"] = source_type_var.get()
        config["source_table"] = source_table_var.get()
        config["transit_table"] = transit_var.get()
        source_headers, source_name = get_loop_source_headers_for_config(
            window,
            config,
            headers,
            transit_context,
            source_type_var,
            source_table_var,
            transit_var,
        )
        field_label.configure(text=f"读取字段（来源：{source_name}）：")
        window.refresh_combo_values(reference_combo, reference_var, source_headers, keep_custom=True, fallback=source_headers[0] if source_headers else "")
        selected_fields = config.get("fields") or list(source_headers[:3])
        selected_indices = window.refresh_listbox_values(lb, source_headers, selected_fields)
        if not selected_indices and source_headers:
            for index in range(min(3, len(source_headers))):
                lb.selection_set(index)
        update_fields()

    source_type_var.trace_add("write", refresh_loop_source_fields)
    source_table_var.trace_add("write", refresh_loop_source_fields)
    transit_var.trace_add("write", refresh_loop_source_fields)
    ttk.Button(lb_frame, text="全选", command=lambda: (lb.selection_set(0, tk.END), update_fields())).pack(side=tk.LEFT, padx=6)
    ttk.Button(lb_frame, text="全不选", command=lambda: (lb.selection_clear(0, tk.END), update_fields())).pack(side=tk.LEFT, padx=2)


def build_loop_judge_config(window, config, headers):
    frame = ttk.LabelFrame(window.config_frame, text="循环判断回跳节点", padding=8)
    frame.pack(fill=tk.BOTH, expand=True, pady=8)
    ttk.Label(
        frame,
        text="判断当前循环项处理结果，更新循环队列表标志；如果还有 0，则跳回对应的循环执行起点。",
        foreground="gray",
        wraplength=1050,
    ).grid(row=0, column=0, columnspan=6, sticky=tk.W, padx=4, pady=(0, 6))

    loop_ids = []
    for node in window.nodes:
        if node.get("type") == "循环执行起点":
            loop_id = node.get("config", {}).get("loop_id", "")
            if loop_id and loop_id not in loop_ids:
                loop_ids.append(loop_id)
    loop_var = window.add_labeled_combo(frame, "对应循环起点：", config.get("loop_id", loop_ids[0] if loop_ids else ""), loop_ids, 1, 0, 24, readonly=False)
    window.sync_var_to_config(loop_var, config, "loop_id")

    source_var = window.add_labeled_combo(frame, "判断数据来源：", config.get("condition_source", "当前表"), ["当前表", "当前循环项表"], 1, 2, 18)
    mode_var = window.add_labeled_combo(
        frame,
        "判断方式：",
        config.get("condition_mode", "始终成功"),
        ["始终成功", "字段等于", "字段不等于", "字段包含", "字段不为空", "结果表行数>0", "正则匹配"],
        2,
        0,
        18,
    )
    field_var = window.add_labeled_combo(frame, "判断字段：", config.get("condition_field", headers[0] if headers else ""), headers, 2, 2, 22, readonly=False)
    value_var = window.add_labeled_entry(frame, "判断值：", config.get("condition_value", "成功"), 3, 0, 24)
    _sync_vars(
        window,
        config,
        [
            (source_var, "condition_source"),
            (mode_var, "condition_mode"),
            (field_var, "condition_field"),
            (value_var, "condition_value"),
        ],
    )

    success_var = window.add_labeled_combo(frame, "满足条件：", config.get("on_success", "标记完成2并继续循环"), ["标记完成2并继续循环"], 4, 0, 24)
    fail_var = window.add_labeled_combo(
        frame,
        "不满足条件：",
        config.get("on_fail", "标记失败3并继续下一条"),
        ["标记失败3并继续下一条", "标记失败3并停止工作流", "重置为0稍后重试", "标记跳过4并继续下一条"],
        4,
        2,
        24,
    )
    end_var = window.add_labeled_combo(frame, "循环结束输出：", config.get("end_output_mode", "循环队列表"), ["循环队列表", "循环结果表", "保持当前表"], 5, 0, 18)
    result_name_var = window.add_labeled_entry(frame, "结果中转名：", config.get("result_table_name", "循环结果"), 5, 2, 18)
    _sync_vars(window, config, [(success_var, "on_success"), (fail_var, "on_fail"), (end_var, "end_output_mode"), (result_name_var, "result_table_name")])

    action_frame = ttk.Frame(frame)
    action_frame.grid(row=6, column=0, columnspan=6, sticky=tk.W, padx=4, pady=(10, 4))
    ttk.Button(action_frame, text="执行循环一次", command=window.execute_loop_once_from_selected_judge).pack(side=tk.LEFT, padx=(0, 8))
    ttk.Button(action_frame, text="重置单步循环缓存", command=window.reset_manual_loop_context).pack(side=tk.LEFT, padx=4)
    ttk.Label(action_frame, text="用于调试循环：每点一次只跑当前循环一轮，后续预览节点会优先接着该缓存继续执行。", foreground="gray").pack(side=tk.LEFT, padx=10)


def jump_anchor_choices(nodes):
    choices = []
    for node in nodes or []:
        if node.get("type") != "跳转锚点节点":
            continue
        config = node.get("config", {}) or {}
        anchor_id = str(config.get("anchor_id", "") or "").strip()
        if not anchor_id:
            continue
        name = str(config.get("anchor_name", "") or node.get("name", "") or "").strip()
        choices.append(f"{anchor_id} - {name}" if name else anchor_id)
    return choices


def anchor_id_from_choice(value):
    text = str(value or "").strip()
    if " - " in text:
        return text.split(" - ", 1)[0].strip()
    return text


def set_anchor_var_to_config(var, config, key):
    def sync(*_):
        config[key] = anchor_id_from_choice(var.get())

    sync()
    var.trace_add("write", sync)


def build_jump_anchor_config(window, config):
    config.setdefault("anchor_id", f"anchor_{datetime.now().strftime('%H%M%S')}")
    config.setdefault("anchor_name", config.get("anchor_id", "锚点"))
    config.setdefault("description", "")
    frame = ttk.LabelFrame(window.config_frame, text="跳转锚点节点", padding=8)
    frame.pack(fill=tk.BOTH, expand=True, pady=8)
    ttk.Label(
        frame,
        text="锚点节点只做定位，不参与计算、表映射、字段映射或权限控制。",
        foreground="gray",
    ).grid(row=0, column=0, columnspan=6, sticky=tk.W, padx=4, pady=(0, 6))
    anchor_var = window.add_labeled_entry(frame, "锚点ID：", config.get("anchor_id", ""), 1, 0, 26)
    name_var = window.add_labeled_entry(frame, "显示名称：", config.get("anchor_name", ""), 1, 2, 26)
    desc_var = window.add_labeled_entry(frame, "说明：", config.get("description", ""), 2, 0, 56)
    _sync_vars(window, config, [(anchor_var, "anchor_id"), (name_var, "anchor_name"), (desc_var, "description")])
    ttk.Button(frame, text="打开跳转管理", command=window.open_jump_manager_window).grid(row=3, column=0, sticky=tk.W, padx=4, pady=(8, 4))


def build_unconditional_jump_config(window, config):
    config.setdefault("target_anchor_id", "")
    config.setdefault("note", "")
    frame = ttk.LabelFrame(window.config_frame, text="无条件跳转节点", padding=8)
    frame.pack(fill=tk.BOTH, expand=True, pady=8)
    ttk.Label(
        frame,
        text="执行到这里时尝试跳到目标锚点；未绑定、锚点不存在或锚点禁用时默认不跳转。",
        foreground="gray",
    ).grid(row=0, column=0, columnspan=6, sticky=tk.W, padx=4, pady=(0, 6))
    target_var = window.add_labeled_combo(frame, "目标锚点：", config.get("target_anchor_id", ""), jump_anchor_choices(window.nodes), 1, 0, 34, readonly=False)
    note_var = window.add_labeled_entry(frame, "说明：", config.get("note", ""), 2, 0, 56)
    set_anchor_var_to_config(target_var, config, "target_anchor_id")
    window.sync_var_to_config(note_var, config, "note")
    ttk.Button(frame, text="打开跳转管理", command=window.open_jump_manager_window).grid(row=3, column=0, sticky=tk.W, padx=4, pady=(8, 4))


def build_condition_check_config(window, config, headers):
    config.setdefault("flag_name", f"condition_{datetime.now().strftime('%H%M%S')}")
    config.setdefault("condition_type", "表行数")
    config.setdefault("field", headers[0] if headers else "")
    config.setdefault("op", "大于")
    config.setdefault("value", "0")
    config.setdefault("case_sensitive", True)
    config.setdefault("true_value", "TRUE")
    config.setdefault("false_value", "FALSE")
    frame = ttk.LabelFrame(window.config_frame, text="条件判断节点", padding=8)
    frame.pack(fill=tk.BOTH, expand=True, pady=8)
    ttk.Label(
        frame,
        text="条件判断只计算结果并写入运行期标志，不负责跳转，也不做字段映射。第一版以当前表为判断对象。",
        foreground="gray",
    ).grid(row=0, column=0, columnspan=8, sticky=tk.W, padx=4, pady=(0, 6))
    flag_var = window.add_labeled_entry(frame, "输出标志：", config.get("flag_name", ""), 1, 0, 22)
    type_var = window.add_labeled_combo(
        frame,
        "判断类型：",
        config.get("condition_type", "表行数"),
        ["表行数", "字段值", "字段是否存在", "字段空值数量", "字段包含值数量"],
        1,
        2,
        18,
    )
    field_var = window.add_labeled_combo(frame, "字段：", config.get("field", headers[0] if headers else ""), headers, 2, 0, 24, readonly=False)
    op_var = window.add_labeled_combo(
        frame,
        "操作：",
        config.get("op", "大于"),
        ["等于", "不等于", "大于", "小于", "大于等于", "小于等于", "包含", "不包含", "为空", "不为空", "正则匹配"],
        2,
        2,
        14,
    )
    value_var = window.add_labeled_entry(frame, "比较值：", config.get("value", "0"), 2, 4, 22)
    true_var = window.add_labeled_entry(frame, "满足输出：", config.get("true_value", "TRUE"), 3, 0, 14)
    false_var = window.add_labeled_entry(frame, "不满足输出：", config.get("false_value", "FALSE"), 3, 2, 14)
    case_var = tk.BooleanVar(value=bool(config.get("case_sensitive", True)))
    ttk.Checkbutton(frame, text="区分大小写", variable=case_var).grid(row=3, column=4, sticky=tk.W, padx=4, pady=4)
    _sync_vars(
        window,
        config,
        [
            (flag_var, "flag_name"),
            (type_var, "condition_type"),
            (field_var, "field"),
            (op_var, "op"),
            (value_var, "value"),
            (true_var, "true_value"),
            (false_var, "false_value"),
        ],
    )
    case_var.trace_add("write", lambda *_: config.__setitem__("case_sensitive", bool(case_var.get())))


def build_conditional_jump_config(window, config):
    config.setdefault("flag_name", "")
    config.setdefault("jump_rules", [{"value": "TRUE", "target_anchor_id": ""}, {"value": "FALSE", "target_anchor_id": ""}])
    config.setdefault("default_anchor_id", "")
    frame = ttk.LabelFrame(window.config_frame, text="条件跳转节点", padding=8)
    frame.pack(fill=tk.BOTH, expand=True, pady=8)
    ttk.Label(
        frame,
        text="条件跳转只读取条件判断节点输出的标志；条件值未映射或目标锚点无效时默认不跳转。",
        foreground="gray",
    ).grid(row=0, column=0, columnspan=8, sticky=tk.W, padx=4, pady=(0, 6))
    flag_var = window.add_labeled_entry(frame, "读取标志：", config.get("flag_name", ""), 1, 0, 24)
    window.sync_var_to_config(flag_var, config, "flag_name")
    choices = jump_anchor_choices(window.nodes)
    rules_frame = ttk.LabelFrame(frame, text="条件值 -> 锚点", padding=6)
    rules_frame.grid(row=2, column=0, columnspan=8, sticky="nsew", padx=4, pady=6)
    rule_tree = ttk.Treeview(rules_frame, columns=("value", "anchor"), show="headings", height=5)
    rule_tree.heading("value", text="条件值")
    rule_tree.heading("anchor", text="目标锚点")
    rule_tree.column("value", width=120, anchor=tk.W)
    rule_tree.column("anchor", width=260, anchor=tk.W)
    rule_tree.grid(row=0, column=0, columnspan=5, sticky="nsew", padx=2, pady=2)
    value_var = tk.StringVar()
    anchor_var = tk.StringVar()
    ttk.Label(rules_frame, text="条件值").grid(row=1, column=0, sticky=tk.W, padx=2, pady=4)
    ttk.Entry(rules_frame, textvariable=value_var, width=16).grid(row=1, column=1, sticky=tk.W, padx=2, pady=4)
    ttk.Label(rules_frame, text="目标锚点").grid(row=1, column=2, sticky=tk.W, padx=2, pady=4)
    ttk.Combobox(rules_frame, textvariable=anchor_var, values=choices, width=34).grid(row=1, column=3, sticky=tk.W, padx=2, pady=4)

    def refresh_rules():
        rule_tree.delete(*rule_tree.get_children())
        for index, item in enumerate(config.get("jump_rules", []) or []):
            rule_tree.insert("", tk.END, iid=str(index), values=(item.get("value", ""), item.get("target_anchor_id", "")))

    def on_rule_select(event=None):
        selected = rule_tree.selection()
        if not selected:
            return
        index = int(selected[0])
        rules = config.get("jump_rules", []) or []
        if 0 <= index < len(rules):
            value_var.set(rules[index].get("value", ""))
            anchor_var.set(rules[index].get("target_anchor_id", ""))

    def save_rule():
        rules = config.setdefault("jump_rules", [])
        item = {"value": value_var.get().strip(), "target_anchor_id": anchor_id_from_choice(anchor_var.get())}
        selected = rule_tree.selection()
        if selected and 0 <= int(selected[0]) < len(rules):
            rules[int(selected[0])] = item
        else:
            rules.append(item)
        refresh_rules()

    def delete_rule():
        rules = config.setdefault("jump_rules", [])
        selected = rule_tree.selection()
        if selected and 0 <= int(selected[0]) < len(rules):
            del rules[int(selected[0])]
        refresh_rules()

    rule_tree.bind("<<TreeviewSelect>>", on_rule_select)
    ttk.Button(rules_frame, text="添加/保存规则", command=save_rule).grid(row=1, column=4, sticky=tk.W, padx=2, pady=4)
    ttk.Button(rules_frame, text="删除规则", command=delete_rule).grid(row=2, column=4, sticky=tk.W, padx=2, pady=4)
    default_var = window.add_labeled_combo(frame, "默认锚点：", config.get("default_anchor_id", ""), choices, 3, 0, 34, readonly=False)
    set_anchor_var_to_config(default_var, config, "default_anchor_id")
    ttk.Button(frame, text="打开跳转管理", command=window.open_jump_manager_window).grid(row=4, column=0, sticky=tk.W, padx=4, pady=(8, 4))
    refresh_rules()
