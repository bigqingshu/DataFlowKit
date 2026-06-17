# -*- coding: utf-8 -*-
"""Main workflow window UI orchestration helpers."""

import tkinter as tk
from tkinter import messagebox, ttk


def show_table_access_precheck_dialog(window, issues, title="权限预检", allow_continue=False):
    issues = list(issues or [])
    result = {"continue": not allow_continue}
    win = tk.Toplevel(window.window)
    win.title(title)
    win.geometry("1280x680")
    win.minsize(980, 520)
    win.transient(window.window)

    main = ttk.Frame(win, padding=8)
    main.pack(fill=tk.BOTH, expand=True)
    summary_var = tk.StringVar(value=window.table_access_precheck_summary_text(issues))
    ttk.Label(main, textvariable=summary_var, font=("TkDefaultFont", 10, "bold")).pack(anchor=tk.W, pady=(0, 6))

    filter_frame = ttk.Frame(main)
    filter_frame.pack(fill=tk.X, pady=(0, 6))
    ttk.Label(filter_frame, text="级别：").pack(side=tk.LEFT, padx=(0, 4))
    severity_var = tk.StringVar(value="全部")
    severity_combo = ttk.Combobox(filter_frame, textvariable=severity_var, values=["全部", "error", "warning", "info"], width=10, state="readonly")
    severity_combo.pack(side=tk.LEFT, padx=(0, 8))
    ttk.Label(filter_frame, text="搜索：").pack(side=tk.LEFT, padx=(0, 4))
    search_var = tk.StringVar()
    search_entry = ttk.Entry(filter_frame, textvariable=search_var, width=34)
    search_entry.pack(side=tk.LEFT, padx=(0, 8))

    tree_wrap = ttk.Frame(main)
    tree_wrap.pack(fill=tk.BOTH, expand=True)
    columns = ("severity", "category", "blocking", "node", "source", "table", "role", "operation", "message", "suggestion")
    tree = ttk.Treeview(tree_wrap, columns=columns, show="headings", height=18)
    for col, text, width in [
        ("severity", "级别", 72),
        ("category", "类型", 72),
        ("blocking", "阻断", 52),
        ("node", "节点", 180),
        ("source", "来源", 82),
        ("table", "表", 150),
        ("role", "角色", 82),
        ("operation", "操作", 150),
        ("message", "问题", 320),
        ("suggestion", "建议", 260),
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

    def row_text(issue):
        return " ".join(str(issue.get(key, "") or "") for key in ["severity", "category", "blocking", "node", "source_type", "table", "role", "operation", "message", "suggestion"])

    def refresh_tree(*_):
        tree.delete(*tree.get_children())
        selected_sev = severity_var.get()
        keyword = search_var.get().strip().lower()
        visible = 0
        for idx, issue in enumerate(issues):
            sev = issue.get("severity", "info")
            if selected_sev != "全部" and sev != selected_sev:
                continue
            if keyword and keyword not in row_text(issue).lower():
                continue
            visible += 1
            tree.insert(
                "",
                tk.END,
                iid=str(idx),
                values=(
                    sev,
                    issue.get("category", ""),
                    "是" if issue.get("blocking") else "否",
                    issue.get("node", ""),
                    issue.get("source_type", ""),
                    issue.get("table", ""),
                    issue.get("role", ""),
                    issue.get("operation", ""),
                    issue.get("message", ""),
                    issue.get("suggestion", ""),
                ),
                tags=(sev,),
            )
        summary_var.set(window.table_access_precheck_summary_text(issues) + f" 当前显示 {visible} 项。")

    def show_detail(event=None):
        sel = tree.selection()
        if not sel:
            return
        issue = issues[int(sel[0])]
        detail = (
            f"级别：{issue.get('severity', '')}\n"
            f"类型：{issue.get('category', '')}\n"
            f"阻断执行：{'是' if issue.get('blocking') else '否'}\n"
            f"节点：{issue.get('node', '')}\n"
            f"表：{issue.get('source_type', '')} / {issue.get('table', '')}\n"
            f"角色：{issue.get('role', '')}\n"
            f"操作：{issue.get('operation', '')}\n\n"
            f"问题：{issue.get('message', '')}\n\n"
            f"建议：{issue.get('suggestion', '')}"
        )
        messagebox.showinfo("预检详情", detail, parent=win)

    tree.bind("<Double-1>", show_detail)
    severity_var.trace_add("write", refresh_tree)
    search_var.trace_add("write", refresh_tree)

    bottom = ttk.Frame(win, padding=(8, 0, 8, 8))
    bottom.pack(fill=tk.X)
    ttk.Button(bottom, text="打开字段权限层", command=lambda: (win.destroy(), window.open_table_access_window())).pack(side=tk.LEFT, padx=4)
    ttk.Button(bottom, text="详情", command=show_detail).pack(side=tk.LEFT, padx=4)
    if allow_continue:

        def continue_run():
            result["continue"] = True
            win.destroy()

        def cancel_run():
            result["continue"] = False
            win.destroy()

        ttk.Button(bottom, text="继续执行", command=continue_run).pack(side=tk.RIGHT, padx=4)
        ttk.Button(bottom, text="取消执行", command=cancel_run).pack(side=tk.RIGHT, padx=4)
        win.protocol("WM_DELETE_WINDOW", cancel_run)
    else:
        ttk.Button(bottom, text="关闭", command=win.destroy).pack(side=tk.RIGHT, padx=4)

    refresh_tree()
    window.center_toplevel(win, window.window, 1280, 680)
    try:
        win.grab_set()
    except Exception:
        pass
    window.window.wait_window(win)
    return bool(result.get("continue"))


def build_node_config(window, idx):
    window.clear_config_frame()
    node = window.nodes[idx]
    config = node.setdefault("config", {})
    try:
        available_headers, available_rows = window.get_headers_rows_before(idx)
    except Exception:
        available_headers = list(window.preview_headers)
        available_rows = [list(r) for r in window.preview_rows]

    title = ttk.Frame(window.config_frame)
    title.pack(fill=tk.X)
    ttk.Label(title, text=f"节点类型：{node.get('type')}   ").pack(side=tk.LEFT)
    ttk.Label(title, text="节点名称：").pack(side=tk.LEFT)
    name_var = tk.StringVar(value=node.get("name", node.get("type", "")))
    ttk.Entry(title, textvariable=name_var, width=28).pack(side=tk.LEFT, padx=4)
    ttk.Button(title, text="更新名称", command=lambda: window.update_node_name(idx, name_var)).pack(side=tk.LEFT, padx=4)
    ttk.Checkbutton(title, text="启用", variable=window.make_node_enabled_var(idx)).pack(side=tk.LEFT, padx=8)
    ttk.Button(title, text="字段权限层", command=lambda idx=idx: window.open_table_access_window(initial_index=idx)).pack(side=tk.LEFT, padx=4)

    node_type = node.get("type")
    if node_type == "节点组 / 子工作流":
        transit_context = window.get_transit_context_before(idx)
        window.build_group_node_config(config, available_headers, transit_context)
    elif node_type == "循环执行起点":
        transit_context = window.get_transit_context_before(idx)
        window.build_loop_start_config(config, available_headers, transit_context)
    elif node_type == "循环判断回跳":
        window.build_loop_judge_config(config, available_headers)
    elif node_type == "跳转锚点节点":
        window.build_jump_anchor_config(config)
    elif node_type == "无条件跳转节点":
        window.build_unconditional_jump_config(config)
    elif node_type == "条件判断节点":
        window.build_condition_check_config(config, available_headers)
    elif node_type == "条件跳转节点":
        window.build_conditional_jump_config(config)
    elif node_type == "批量替换":
        window.build_replace_config(config, available_headers)
    elif node_type == "数据提取":
        window.build_extract_config(config, available_headers)
    elif node_type == "格式规范化 / 日期时间解析":
        window.build_format_datetime_config(config, available_headers)
    elif node_type == "新建日期时间列":
        window.build_current_datetime_column_config(config, available_headers)
    elif node_type == "新建列":
        window.build_new_columns_config(config, available_headers)
    elif node_type == "合并列":
        window.build_merge_config(config, available_headers)
    elif node_type == "批量更改列名":
        window.build_rename_columns_config(config, available_headers)
    elif node_type == "去重 / 重复数据处理":
        window.build_dedupe_config(config, available_headers)
    elif node_type == "列数字运算":
        window.build_numeric_column_config(config, available_headers)
    elif node_type == "匹配值输出列名":
        transit_context = window.get_transit_context_before(idx)
        window.build_match_value_output_field_name_config(config, available_headers, transit_context)
    elif node_type == "插件节点":
        transit_context = window.get_transit_context_before(idx)
        window.build_plugin_node_config(config, available_headers, transit_context, available_rows)
    elif node_type == "复制列":
        window.build_copy_column_config(config, available_headers)
    elif node_type == "复制行":
        window.build_copy_row_config(config, available_headers)
    elif node_type == "删除行":
        window.build_delete_rows_config(config, available_headers)
    elif node_type == "填充值":
        window.build_fill_value_config(config, available_headers)
    elif node_type == "序列填充":
        window.build_sequence_fill_config(config, available_headers)
    elif node_type == "区域填充":
        window.build_area_fill_config(config, available_headers)
    elif node_type == "行数据映射填充":
        window.build_row_data_mapping_config(config, available_headers)
    elif node_type == "保存中转数据":
        window.build_save_transit_config(config, available_headers)
    elif node_type == "选定列写入指定表":
        transit_context = window.get_transit_context_before(idx)
        window.build_selected_columns_write_config(config, available_headers, idx, transit_context)
    elif node_type == "字段映射写入表":
        window.build_writeback_config(config, available_headers)
    elif node_type == "高级筛选":
        transit_context = window.get_transit_context_before(idx)
        window.build_filter_config(config, available_headers, transit_context)
    elif node_type == "删除列":
        window.build_delete_columns_config(config, available_headers)
    elif node_type == "移动列":
        window.build_move_columns_config(config, available_headers)
    elif node_type == "获取文件列表":
        window.build_file_list_config(config)
    elif node_type == "批量重命名":
        window.build_batch_rename_config(config, available_headers)
    else:
        ttk.Label(window.config_frame, text="未知节点类型。", foreground="red").pack(anchor=tk.W)


def build_ui(window):
    main = ttk.Frame(window.window, padding=8)
    main.pack(fill=tk.BOTH, expand=True)

    left = ttk.Frame(main)
    left.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 8))

    source_frame = ttk.LabelFrame(left, text="1. 输入数据源", padding=8)
    source_frame.pack(fill=tk.X)
    ttk.Label(source_frame, text=f"当前输入：{len(window.app.rows)} 行 × {len(window.app.headers)} 列").pack(anchor=tk.W)
    ttk.Button(source_frame, text="重新读取主界面当前预览", command=window.reload_from_app_preview).pack(fill=tk.X, pady=(6, 0))

    node_frame = ttk.LabelFrame(left, text="2. 工作流节点", padding=8)
    node_frame.pack(fill=tk.BOTH, expand=True, pady=8)

    add_frame = ttk.Frame(node_frame)
    add_frame.pack(fill=tk.X)
    window.node_type_combo = ttk.Combobox(add_frame, textvariable=window.node_type_var, values=window.get_node_type_values(), width=22, state="readonly")
    window.node_type_combo.pack(side=tk.LEFT, padx=(0, 4))
    ttk.Button(add_frame, text="添加节点", command=window.add_node).pack(side=tk.LEFT)
    ttk.Button(add_frame, text="刷新插件", command=window.refresh_plugins).pack(side=tk.LEFT, padx=(4, 0))

    node_list_wrap = ttk.Frame(node_frame)
    node_list_wrap.pack(fill=tk.BOTH, expand=True, pady=6)
    window.node_listbox = tk.Listbox(node_list_wrap, width=42, height=24, exportselection=False, selectmode=tk.EXTENDED)
    node_list_scroll = ttk.Scrollbar(node_list_wrap, orient=tk.VERTICAL, command=window.node_listbox.yview)
    window.node_listbox.configure(yscrollcommand=node_list_scroll.set)
    window.node_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    node_list_scroll.pack(side=tk.RIGHT, fill=tk.Y)
    window.node_listbox.bind("<<ListboxSelect>>", window.on_node_select)

    node_btns1 = ttk.Frame(node_frame)
    node_btns1.pack(fill=tk.X)
    for text_, cmd in [
        ("删除", window.delete_node),
        ("上移", window.move_node_up),
        ("下移", window.move_node_down),
        ("启用/禁用", window.toggle_node_enabled),
    ]:
        ttk.Button(node_btns1, text=text_, command=cmd).pack(side=tk.LEFT, padx=2, pady=2)

    node_btns2 = ttk.Frame(node_frame)
    node_btns2.pack(fill=tk.X)
    ttk.Button(node_btns2, text="复制节点", command=window.copy_node).pack(side=tk.LEFT, padx=2, pady=2)
    ttk.Button(node_btns2, text="合并为组", command=window.merge_selected_nodes_to_group).pack(side=tk.LEFT, padx=2, pady=2)
    ttk.Button(node_btns2, text="展开组", command=window.expand_selected_group).pack(side=tk.LEFT, padx=2, pady=2)
    ttk.Button(node_btns2, text="清空节点", command=window.clear_nodes).pack(side=tk.LEFT, padx=2, pady=2)

    node_btns3 = ttk.Frame(node_frame)
    node_btns3.pack(fill=tk.X)
    ttk.Button(node_btns3, text="字段权限层", command=window.open_table_access_window).pack(side=tk.LEFT, padx=2, pady=2)
    ttk.Button(node_btns3, text="权限预检", command=window.open_table_access_precheck_window).pack(side=tk.LEFT, padx=2, pady=2)
    ttk.Button(node_btns3, text="审计日志", command=window.open_table_access_audit_window).pack(side=tk.LEFT, padx=2, pady=2)
    ttk.Button(node_btns3, text="跳转管理", command=window.open_jump_manager_window).pack(side=tk.LEFT, padx=2, pady=2)

    policy_frame = ttk.Frame(node_frame)
    policy_frame.pack(fill=tk.X)
    ttk.Label(policy_frame, text="权限策略：").pack(side=tk.LEFT, padx=(2, 2), pady=2)
    ttk.Combobox(
        policy_frame,
        textvariable=window.table_access_policy_var,
        values=window.TABLE_ACCESS_POLICY_CHOICES,
        width=10,
        state="readonly",
    ).pack(side=tk.LEFT, padx=2, pady=2)

    tpl_frame = ttk.LabelFrame(left, text="3. 计划模板", padding=8)
    tpl_frame.pack(fill=tk.X)

    tpl_row1 = ttk.Frame(tpl_frame)
    tpl_row1.pack(fill=tk.X, pady=(0, 4))
    ttk.Button(tpl_row1, text="保存计划模板", command=window.save_plan_template).pack(side=tk.LEFT, padx=2)
    ttk.Button(tpl_row1, text="载入计划模板", command=window.load_plan_template).pack(side=tk.LEFT, padx=2)
    ttk.Button(tpl_row1, text="打开plan目录", command=window.open_plan_dir).pack(side=tk.LEFT, padx=2)

    tpl_row2 = ttk.Frame(tpl_frame)
    tpl_row2.pack(fill=tk.X)
    window.plan_template_combo = ttk.Combobox(
        tpl_row2,
        textvariable=window.plan_template_var,
        width=27,
        state="readonly",
    )
    window.plan_template_combo.pack(side=tk.LEFT, padx=2)
    window.plan_template_combo.configure(postcommand=lambda: window.refresh_plan_template_list(show_status=False))
    ttk.Button(tpl_row2, text="载入选中模板", command=window.load_selected_plan_template).pack(side=tk.LEFT, padx=2)
    ttk.Button(tpl_row2, text="刷新模板", command=window.refresh_plan_template_list).pack(side=tk.LEFT, padx=2)

    right = ttk.Frame(main)
    right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    window.config_outer = ttk.LabelFrame(right, text="4. 节点配置", padding=8)
    window.config_outer.pack(fill=tk.X)
    window.config_outer.configure(height=310)
    window.config_outer.pack_propagate(False)

    window.config_canvas = tk.Canvas(window.config_outer, highlightthickness=0)
    window.config_y_scroll = ttk.Scrollbar(window.config_outer, orient=tk.VERTICAL, command=window.config_canvas.yview)
    window.config_x_scroll = ttk.Scrollbar(window.config_outer, orient=tk.HORIZONTAL, command=window.config_canvas.xview)
    window.config_frame = ttk.Frame(window.config_canvas)

    window.config_canvas_window = window.config_canvas.create_window((0, 0), window=window.config_frame, anchor="nw")
    window.config_canvas.configure(
        yscrollcommand=window.config_y_scroll.set,
        xscrollcommand=window.config_x_scroll.set,
    )

    window.config_canvas.grid(row=0, column=0, sticky="nsew")
    window.config_y_scroll.grid(row=0, column=1, sticky="ns")
    window.config_x_scroll.grid(row=1, column=0, sticky="ew")
    window.config_outer.rowconfigure(0, weight=1)
    window.config_outer.columnconfigure(0, weight=1)

    window.config_frame.bind("<Configure>", window._on_config_frame_configure)
    window.config_canvas.bind("<Configure>", window._on_config_canvas_configure)
    window.config_canvas.bind("<Enter>", window._bind_config_mousewheel)
    window.config_canvas.bind("<Leave>", window._unbind_config_mousewheel)

    action_frame = ttk.Frame(right)
    action_frame.pack(fill=tk.X, pady=8)
    ttk.Button(action_frame, text="预览到当前节点", command=window.preview_to_selected_node).pack(side=tk.LEFT, padx=4)
    ttk.Button(action_frame, text="预览完整计划", command=window.preview_full_plan).pack(side=tk.LEFT, padx=4)
    ttk.Button(action_frame, text="执行计划", command=window.execute_plan).pack(side=tk.LEFT, padx=4)

    progress_frame = ttk.LabelFrame(right, text="执行进度", padding=8)
    progress_frame.pack(fill=tk.X, pady=(0, 8))
    window.workflow_progress_label = ttk.Label(progress_frame, textvariable=window.workflow_progress_text, anchor=tk.W)
    window.workflow_progress_label.grid(row=0, column=0, sticky="ew", padx=4, pady=(2, 0))
    window.workflow_progress_bar = ttk.Progressbar(progress_frame, variable=window.workflow_progress_var, maximum=100, mode="determinate")
    window.workflow_progress_bar.grid(row=1, column=0, sticky="ew", padx=4, pady=(2, 6))
    window.node_progress_label = ttk.Label(progress_frame, textvariable=window.node_progress_text, anchor=tk.W)
    window.node_progress_label.grid(row=2, column=0, sticky="ew", padx=4, pady=(2, 0))
    window.node_progress_bar = ttk.Progressbar(progress_frame, variable=window.node_progress_var, maximum=100, mode="determinate")
    window.node_progress_bar.grid(row=3, column=0, sticky="ew", padx=4, pady=(2, 6))
    worker_btns = ttk.Frame(progress_frame)
    worker_btns.grid(row=2, column=1, sticky=tk.E, padx=(8, 4), pady=0)
    window.workflow_cancel_button = ttk.Button(worker_btns, text="取消后台任务", command=window.cancel_background_workflow)
    window.workflow_cancel_button.pack(side=tk.LEFT, padx=2)
    window.workflow_cancel_button.configure(state="disabled")
    window.worker_status_label = ttk.Label(progress_frame, textvariable=window.worker_status_text, anchor=tk.W, wraplength=980, justify=tk.LEFT)
    window.worker_status_label.grid(row=4, column=0, columnspan=2, sticky="ew", padx=4, pady=(4, 0))
    progress_frame.columnconfigure(0, weight=1)

    def update_progress_wrap(event, label=window.worker_status_label):
        try:
            label.configure(wraplength=max(320, int(event.width) - 32))
        except Exception:
            pass

    progress_frame.bind("<Configure>", update_progress_wrap)

    output_frame = ttk.LabelFrame(right, text="5. 输出设置", padding=8)
    output_frame.pack(fill=tk.X)
    ttk.Label(output_frame, text="输出方式：").grid(row=0, column=0, sticky=tk.W, padx=4, pady=4)
    ttk.Combobox(
        output_frame,
        textvariable=window.output_mode_var,
        values=["输出到主界面预览区", "保存为SQLite新表", "覆盖当前表", "导出为xlsx"],
        width=20,
        state="readonly",
    ).grid(row=0, column=1, sticky=tk.W, padx=4, pady=4)
    ttk.Label(output_frame, text="输出表名：").grid(row=0, column=2, sticky=tk.W, padx=4, pady=4)
    ttk.Entry(output_frame, textvariable=window.output_table_var, width=36).grid(row=0, column=3, sticky=tk.W, padx=4, pady=4)
    ttk.Checkbutton(output_frame, text="覆盖前自动备份旧表", variable=window.backup_before_overwrite_var).grid(row=0, column=4, sticky=tk.W, padx=4, pady=4)

    preview_frame = ttk.LabelFrame(right, text="6. 结果预览", padding=6)
    preview_frame.pack(fill=tk.BOTH, expand=True, pady=8)

    preview_toolbar = ttk.Frame(preview_frame)
    preview_toolbar.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 4))
    ttk.Button(
        preview_toolbar,
        textvariable=window.preview_edit_btn_text,
        command=window.toggle_preview_edit_mode,
    ).pack(side=tk.LEFT, padx=4)

    ttk.Label(preview_toolbar, text="查看表：").pack(side=tk.LEFT, padx=(10, 2))
    window.preview_table_combo = ttk.Combobox(
        preview_toolbar,
        textvariable=window.preview_table_var,
        width=34,
        state="readonly",
    )
    window.preview_table_combo.pack(side=tk.LEFT, padx=2)
    window.preview_table_combo.configure(postcommand=lambda: window.refresh_preview_table_choices(show_status=False))
    ttk.Button(
        preview_toolbar,
        text="载入选中表",
        command=window.load_selected_preview_table,
    ).pack(side=tk.LEFT, padx=(4, 8))

    ttk.Label(
        preview_toolbar,
        text="开启后可双击下方预览单元格修改；再次预览/重新执行计划会重新生成预览。",
        foreground="gray",
    ).pack(side=tk.LEFT, padx=6)

    preview_search_frame = ttk.Frame(preview_frame)
    preview_search_frame.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 4))
    ttk.Label(preview_search_frame, text="搜索：").pack(side=tk.LEFT, padx=(4, 4))
    preview_search_entry = ttk.Entry(preview_search_frame, textvariable=window.preview_search_var, width=38)
    preview_search_entry.pack(side=tk.LEFT, padx=(4, 4))
    preview_search_entry.bind("<Return>", lambda e: window.search_preview_table(reset=True))
    ttk.Button(
        preview_search_frame,
        text="搜索",
        command=lambda: window.search_preview_table(reset=True),
    ).pack(side=tk.LEFT, padx=(12, 8))
    ttk.Button(
        preview_search_frame,
        text="上一个",
        command=window.search_preview_prev,
    ).pack(side=tk.LEFT, padx=(12, 8))
    ttk.Button(
        preview_search_frame,
        text="下一个",
        command=window.search_preview_next,
    ).pack(side=tk.LEFT, padx=(12, 8))
    ttk.Button(
        preview_search_frame,
        text="导出为 xlsx",
        command=window.export_preview_to_xlsx,
    ).pack(side=tk.LEFT, padx=(4, 8))

    window.preview_tree = ttk.Treeview(preview_frame, show="headings")
    y_scroll = ttk.Scrollbar(preview_frame, orient=tk.VERTICAL, command=window.preview_tree.yview)
    x_scroll = ttk.Scrollbar(preview_frame, orient=tk.HORIZONTAL, command=window.preview_tree.xview)
    window.preview_tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)
    window.preview_tree.grid(row=2, column=0, sticky="nsew")
    y_scroll.grid(row=2, column=1, sticky="ns")
    x_scroll.grid(row=3, column=0, sticky="ew")
    window.preview_tree.bind("<Double-1>", window.on_preview_tree_double_click)
    preview_frame.rowconfigure(2, weight=1)
    preview_frame.columnconfigure(0, weight=1)

    ttk.Label(right, textvariable=window.status_var, padding=(0, 4)).pack(fill=tk.X)
    window.show_empty_config()
