# -*- coding: utf-8 -*-
"""Tkinter UI helpers for the workflow jump manager window."""

import tkinter as tk
from tkinter import messagebox, ttk


def jump_relation_tag(relation):
    if not relation.get("enabled", True):
        return "disabled"
    status = relation.get("status", "")
    if status.startswith("有效"):
        return "ok"
    if "不存在" in status or "重复" in status:
        return "error"
    return "warning"


def show_jump_precheck_dialog(window, issues, title="跳转校验", allow_continue=False):
    issues = list(issues or [])
    result = {"continue": not allow_continue}
    win = tk.Toplevel(window.window)
    win.title(title)
    win.geometry("1180x620")
    win.minsize(900, 480)
    win.transient(window.window)

    main = ttk.Frame(win, padding=8)
    main.pack(fill=tk.BOTH, expand=True)
    summary_var = tk.StringVar(value=window.jump_validation_summary_text(issues))
    ttk.Label(main, textvariable=summary_var, font=("TkDefaultFont", 10, "bold")).pack(anchor=tk.W, pady=(0, 6))
    ttk.Label(main, text="跳转目标无效时运行会默认不跳转；这里用于提前发现配置风险。", foreground="gray").pack(anchor=tk.W, pady=(0, 6))

    tree_wrap = ttk.Frame(main)
    tree_wrap.pack(fill=tk.BOTH, expand=True)
    columns = ("severity", "item", "message", "suggestion")
    tree = ttk.Treeview(tree_wrap, columns=columns, show="headings", height=18)
    for col, text, width in [
        ("severity", "级别", 70),
        ("item", "对象", 180),
        ("message", "问题", 420),
        ("suggestion", "建议", 360),
    ]:
        tree.heading(col, text=text)
        tree.column(col, width=width, anchor=tk.W)
    tree.tag_configure("error", foreground="#b00020")
    tree.tag_configure("warning", foreground="#8a5a00")
    tree.tag_configure("info", foreground="#335c99")
    yscroll = ttk.Scrollbar(tree_wrap, orient=tk.VERTICAL, command=tree.yview)
    xscroll = ttk.Scrollbar(tree_wrap, orient=tk.HORIZONTAL, command=tree.xview)
    tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
    tree.grid(row=0, column=0, sticky="nsew")
    yscroll.grid(row=0, column=1, sticky="ns")
    xscroll.grid(row=1, column=0, sticky="ew")
    tree_wrap.rowconfigure(0, weight=1)
    tree_wrap.columnconfigure(0, weight=1)

    for idx, issue in enumerate(issues):
        sev = issue.get("severity", "info")
        tree.insert(
            "",
            tk.END,
            iid=str(idx),
            values=(sev, issue.get("item", ""), issue.get("message", ""), issue.get("suggestion", "")),
            tags=(sev,),
        )

    def show_detail(event=None):
        sel = tree.selection()
        if not sel:
            return
        issue = issues[int(sel[0])]
        messagebox.showinfo("跳转校验详情", window.jump_issue_detail_text(issue), parent=win)

    def open_manager():
        result["continue"] = False
        win.destroy()
        window.open_jump_manager_window()

    tree.bind("<Double-1>", show_detail)

    bottom = ttk.Frame(win, padding=(8, 0, 8, 8))
    bottom.pack(fill=tk.X)
    ttk.Button(bottom, text="打开跳转管理", command=open_manager).pack(side=tk.LEFT, padx=4)
    ttk.Button(bottom, text="详情", command=show_detail).pack(side=tk.LEFT, padx=4)
    if allow_continue:
        def continue_run():
            result["continue"] = True
            win.destroy()

        def cancel_run():
            result["continue"] = False
            win.destroy()

        ttk.Button(bottom, text="继续运行", command=continue_run).pack(side=tk.RIGHT, padx=4)
        ttk.Button(bottom, text="取消运行", command=cancel_run).pack(side=tk.RIGHT, padx=4)
        win.protocol("WM_DELETE_WINDOW", cancel_run)
    else:
        ttk.Button(bottom, text="关闭", command=win.destroy).pack(side=tk.RIGHT, padx=4)

    window.center_toplevel(win, window.window, 1180, 620)
    try:
        win.grab_set()
    except Exception:
        pass
    window.window.wait_window(win)
    return bool(result.get("continue"))


def open_jump_manager_window(window):
    window.ensure_node_tree_identity(window.nodes)
    win = tk.Toplevel(window.window)
    win.title("跳转管理")
    win.geometry("1360x740")
    win.minsize(1050, 560)
    win.transient(window.window)

    main = ttk.Frame(win, padding=8)
    main.pack(fill=tk.BOTH, expand=True)
    summary_var = tk.StringVar()
    ttk.Label(
        main,
        text="跳转系统只管理锚点与跳转关系，不管理表映射、字段映射或字段权限。",
        foreground="gray",
    ).pack(anchor=tk.W, pady=(0, 4))
    ttk.Label(main, textvariable=summary_var, font=("TkDefaultFont", 10, "bold")).pack(anchor=tk.W, pady=(0, 6))

    panes = ttk.Panedwindow(main, orient=tk.HORIZONTAL)
    panes.pack(fill=tk.BOTH, expand=True)

    left = ttk.LabelFrame(panes, text="锚点", padding=6)
    middle = ttk.LabelFrame(panes, text="跳转关系", padding=6)
    right = ttk.Frame(panes)
    panes.add(left, weight=1)
    panes.add(middle, weight=2)
    panes.add(right, weight=2)

    anchor_tree = ttk.Treeview(left, columns=("index", "anchor", "name", "refs", "status"), show="headings", height=20)
    for col, text, width in [
        ("index", "#", 45),
        ("anchor", "锚点ID", 150),
        ("name", "名称", 120),
        ("refs", "引用", 55),
        ("status", "状态", 85),
    ]:
        anchor_tree.heading(col, text=text)
        anchor_tree.column(col, width=width, anchor=tk.W)
    anchor_scroll = ttk.Scrollbar(left, orient=tk.VERTICAL, command=anchor_tree.yview)
    anchor_tree.configure(yscrollcommand=anchor_scroll.set)
    anchor_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    anchor_scroll.pack(side=tk.RIGHT, fill=tk.Y)
    anchor_tree.tag_configure("disabled", foreground="#777777")
    anchor_tree.tag_configure("error", foreground="#b00020")

    relation_tree = ttk.Treeview(
        middle,
        columns=("source", "kind", "flag", "value", "target", "status"),
        show="headings",
        height=20,
    )
    for col, text, width in [
        ("source", "来源节点", 190),
        ("kind", "类型", 70),
        ("flag", "标志", 120),
        ("value", "条件值", 90),
        ("target", "目标锚点", 140),
        ("status", "状态", 190),
    ]:
        relation_tree.heading(col, text=text)
        relation_tree.column(col, width=width, anchor=tk.W)
    rel_y = ttk.Scrollbar(middle, orient=tk.VERTICAL, command=relation_tree.yview)
    rel_x = ttk.Scrollbar(middle, orient=tk.HORIZONTAL, command=relation_tree.xview)
    relation_tree.configure(yscrollcommand=rel_y.set, xscrollcommand=rel_x.set)
    relation_tree.grid(row=0, column=0, sticky="nsew")
    rel_y.grid(row=0, column=1, sticky="ns")
    rel_x.grid(row=1, column=0, sticky="ew")
    middle.rowconfigure(0, weight=1)
    middle.columnconfigure(0, weight=1)
    relation_tree.tag_configure("ok", foreground="#1b5e20")
    relation_tree.tag_configure("warning", foreground="#8a5a00")
    relation_tree.tag_configure("error", foreground="#b00020")
    relation_tree.tag_configure("disabled", foreground="#777777")

    detail_frame = ttk.LabelFrame(right, text="详情", padding=6)
    detail_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 6))
    detail_text = tk.Text(detail_frame, height=12, wrap=tk.WORD)
    detail_text.pack(fill=tk.BOTH, expand=True)
    detail_text.configure(state=tk.DISABLED)

    issue_frame = ttk.LabelFrame(right, text="校验结果", padding=6)
    issue_frame.pack(fill=tk.BOTH, expand=True)
    issue_tree = ttk.Treeview(issue_frame, columns=("severity", "item", "message", "suggestion"), show="headings", height=10)
    for col, text, width in [
        ("severity", "级别", 70),
        ("item", "对象", 130),
        ("message", "问题", 220),
        ("suggestion", "建议", 220),
    ]:
        issue_tree.heading(col, text=text)
        issue_tree.column(col, width=width, anchor=tk.W)
    issue_scroll = ttk.Scrollbar(issue_frame, orient=tk.VERTICAL, command=issue_tree.yview)
    issue_tree.configure(yscrollcommand=issue_scroll.set)
    issue_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    issue_scroll.pack(side=tk.RIGHT, fill=tk.Y)
    issue_tree.tag_configure("error", foreground="#b00020")
    issue_tree.tag_configure("warning", foreground="#8a5a00")
    issue_tree.tag_configure("info", foreground="#335c99")

    state = {"anchors": [], "relations": [], "issues": []}

    def set_detail(text):
        detail_text.configure(state=tk.NORMAL)
        detail_text.delete("1.0", tk.END)
        detail_text.insert("1.0", text or "")
        detail_text.configure(state=tk.DISABLED)

    def refresh_all():
        window.ensure_node_tree_identity(window.nodes)
        anchors_info = window.collect_jump_anchors()
        relations = window.collect_jump_relations(anchors_info=anchors_info)
        issues = window.validate_jump_relations()
        state["anchors"] = anchors_info.get("all", [])
        state["relations"] = relations
        state["issues"] = issues

        refs = {}
        for rel in relations:
            target = str(rel.get("target_anchor_id", "") or "").strip()
            if target:
                refs[target] = refs.get(target, 0) + 1

        anchor_tree.delete(*anchor_tree.get_children())
        for idx, anchor in enumerate(state["anchors"]):
            anchor_id = anchor.get("anchor_id", "")
            status = "启用" if anchor.get("enabled") else "禁用"
            tag = ""
            if not anchor.get("enabled"):
                tag = "disabled"
            if anchor_id and len((anchors_info.get("by_id") or {}).get(anchor_id, [])) > 1:
                status = "重复"
                tag = "error"
            anchor_tree.insert(
                "",
                tk.END,
                iid=str(idx),
                values=(anchor.get("node_index", -1) + 1, anchor_id, anchor.get("anchor_name", ""), refs.get(anchor_id, 0), status),
                tags=(tag,),
            )

        relation_tree.delete(*relation_tree.get_children())
        for idx, rel in enumerate(relations):
            relation_tree.insert(
                "",
                tk.END,
                iid=str(idx),
                values=(
                    rel.get("source_label", ""),
                    rel.get("kind", ""),
                    rel.get("flag_name", ""),
                    rel.get("condition_value", ""),
                    rel.get("target_anchor_id", ""),
                    rel.get("status", ""),
                ),
                tags=(jump_relation_tag(rel),),
            )

        issue_tree.delete(*issue_tree.get_children())
        for idx, issue in enumerate(issues):
            issue_tree.insert(
                "",
                tk.END,
                iid=str(idx),
                values=(issue.get("severity", ""), issue.get("item", ""), issue.get("message", ""), issue.get("suggestion", "")),
                tags=(issue.get("severity", ""),),
            )
        summary_var.set(
            f"锚点 {len(state['anchors'])} 个，跳转关系 {len(relations)} 条。"
            + window.jump_validation_summary_text(issues)
        )
        if state["anchors"]:
            anchor_tree.selection_set("0")
            anchor_tree.focus("0")
            show_anchor_detail()
        else:
            set_detail("当前工作流还没有跳转锚点节点。")

    def show_anchor_detail(event=None):
        sel = anchor_tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        anchors = state.get("anchors", [])
        if idx < 0 or idx >= len(anchors):
            return
        anchor = anchors[idx]
        anchor_id = anchor.get("anchor_id", "")
        refs = [rel for rel in state.get("relations", []) if rel.get("target_anchor_id") == anchor_id]
        lines = [
            f"锚点节点：{anchor.get('node_index', -1) + 1}",
            f"锚点ID：{anchor_id}",
            f"显示名称：{anchor.get('anchor_name', '')}",
            f"启用：{'是' if anchor.get('enabled') else '否'}",
            f"说明：{anchor.get('description', '') or '-'}",
            "",
            f"引用关系：{len(refs)} 条",
        ]
        for rel in refs[:20]:
            lines.append(f"- {rel.get('source_label', '')} / {rel.get('kind', '')} / {rel.get('condition_value', '')}")
        if len(refs) > 20:
            lines.append(f"... 仅显示前 20 条，共 {len(refs)} 条。")
        set_detail("\n".join(lines))

    def show_relation_detail(event=None):
        sel = relation_tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        relations = state.get("relations", [])
        if idx < 0 or idx >= len(relations):
            return
        rel = relations[idx]
        lines = [
            f"来源节点：{rel.get('source_label', '')}",
            f"跳转类型：{rel.get('kind', '')}",
            f"读取标志：{rel.get('flag_name', '') or '-'}",
            f"条件值：{rel.get('condition_value', '') or '-'}",
            f"目标锚点：{rel.get('target_anchor_id', '') or '-'}",
            f"状态：{rel.get('status', '')}",
            "",
            "运行规则：",
            "目标有效时跳到锚点节点；锚点节点自身不计算，随后继续执行锚点后的节点。",
            "目标缺失、禁用、不存在或重复时，默认不跳转并继续后续节点。",
        ]
        set_detail("\n".join(lines))

    def show_issue_detail(event=None):
        sel = issue_tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        issues = state.get("issues", [])
        if 0 <= idx < len(issues):
            set_detail(window.jump_issue_detail_text(issues[idx]))

    anchor_tree.bind("<<TreeviewSelect>>", show_anchor_detail)
    relation_tree.bind("<<TreeviewSelect>>", show_relation_detail)
    issue_tree.bind("<<TreeviewSelect>>", show_issue_detail)
    relation_tree.bind("<Double-1>", show_relation_detail)
    issue_tree.bind("<Double-1>", show_issue_detail)

    bottom = ttk.Frame(win, padding=(8, 0, 8, 8))
    bottom.pack(fill=tk.X)
    ttk.Button(bottom, text="刷新", command=refresh_all).pack(side=tk.LEFT, padx=4)
    ttk.Button(bottom, text="关闭", command=win.destroy).pack(side=tk.RIGHT, padx=4)

    refresh_all()
    window.center_toplevel(win, window.window, 1360, 740)
