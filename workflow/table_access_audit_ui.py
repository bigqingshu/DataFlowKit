# -*- coding: utf-8 -*-
"""Table-access audit log window and data helpers."""

import csv
import json
import tkinter as tk
from tkinter import filedialog, messagebox, ttk


AUDIT_STATUS_CHOICES = ["全部", "ok", "warning", "denied", "missing", "compat"]

AUDIT_TREE_COLUMNS = [
    ("time", "时间", 145),
    ("node", "节点", 155),
    ("source", "来源", 82),
    ("table", "表", 150),
    ("operation", "操作", 150),
    ("status", "状态", 78),
    ("mode", "模式", 110),
    ("policy", "策略", 70),
    ("message", "信息", 360),
]

AUDIT_STATUS_TAG_COLORS = {
    "ok": "#1b5e20",
    "warning": "#8a5a00",
    "denied": "#b00020",
    "missing": "#b00020",
    "compat": "#555555",
}


def table_access_log_text(event):
    try:
        return json.dumps(event, ensure_ascii=False, default=str)
    except Exception:
        return str(event)


def table_access_audit_log_row(event):
    node = event.get("node_name") or event.get("node_type") or event.get("node_id") or ""
    source = event.get("source_type") or event.get("access_source_type") or ""
    mode = event.get("write_mode") or event.get("mode") or ""
    return (
        event.get("time", ""),
        node,
        source,
        event.get("table_name", ""),
        event.get("operation_checked") or event.get("operation", ""),
        event.get("status", ""),
        mode,
        event.get("policy", ""),
        event.get("message", ""),
    )


def filter_table_access_audit_logs(logs, selected_status="全部", keyword="", log_text_func=None):
    logs = list(logs or [])
    log_text_func = log_text_func or table_access_log_text
    keyword = str(keyword or "").strip().lower()
    selected_status = str(selected_status or "全部")
    visible = []
    counts = {}
    for idx, event in enumerate(logs):
        status = str(event.get("status", "") or "")
        counts[status] = counts.get(status, 0) + 1
        if selected_status != "全部" and status != selected_status:
            continue
        text = log_text_func(event).lower()
        if keyword and keyword not in text:
            continue
        tag = status if status in AUDIT_STATUS_TAG_COLORS else ""
        visible.append({
            "index": idx,
            "event": event,
            "row": table_access_audit_log_row(event),
            "tag": tag,
        })
    count_text = "，".join(f"{k or '无状态'} {v}" for k, v in sorted(counts.items()))
    summary = f"最近日志 {len(logs)} 条，当前显示 {len(visible)} 条" + (f"（{count_text}）" if count_text else "")
    return {
        "visible": visible,
        "counts": counts,
        "summary": summary,
    }


def table_access_audit_csv_fieldnames(logs):
    return sorted({key for event in logs or [] if isinstance(event, dict) for key in event.keys()})


def table_access_audit_csv_row(event, fieldnames):
    row = {}
    for key in fieldnames:
        value = event.get(key, "") if isinstance(event, dict) else ""
        if isinstance(value, (list, dict)):
            value = json.dumps(value, ensure_ascii=False)
        row[key] = value
    return row


def export_table_access_audit_logs(logs, path):
    fieldnames = table_access_audit_csv_fieldnames(logs)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for event in logs:
            writer.writerow(table_access_audit_csv_row(event, fieldnames))


def open_table_access_audit_window(window):
    logs_state = {"logs": list(window.last_table_access_logs or [])}
    win = tk.Toplevel(window.window)
    win.title("表访问权限审计日志")
    win.geometry("1320x700")
    win.minsize(980, 520)
    win.transient(window.window)

    main = ttk.Frame(win, padding=8)
    main.pack(fill=tk.BOTH, expand=True)
    summary_var = tk.StringVar()

    filter_frame = ttk.Frame(main)
    filter_frame.pack(fill=tk.X, pady=(0, 6))
    ttk.Label(filter_frame, textvariable=summary_var, font=("TkDefaultFont", 10, "bold")).pack(side=tk.LEFT, padx=(0, 16))
    ttk.Label(filter_frame, text="状态：").pack(side=tk.LEFT, padx=(0, 4))
    status_var = tk.StringVar(value="全部")
    status_combo = ttk.Combobox(filter_frame, textvariable=status_var, values=AUDIT_STATUS_CHOICES, width=10, state="readonly")
    status_combo.pack(side=tk.LEFT, padx=(0, 8))
    ttk.Label(filter_frame, text="搜索：").pack(side=tk.LEFT, padx=(0, 4))
    search_var = tk.StringVar()
    ttk.Entry(filter_frame, textvariable=search_var, width=34).pack(side=tk.LEFT, padx=(0, 8))

    tree_wrap = ttk.Frame(main)
    tree_wrap.pack(fill=tk.BOTH, expand=True)
    columns = tuple(col for col, _, _ in AUDIT_TREE_COLUMNS)
    tree = ttk.Treeview(tree_wrap, columns=columns, show="headings", height=20)
    for col, text, width in AUDIT_TREE_COLUMNS:
        tree.heading(col, text=text)
        tree.column(col, width=width, anchor=tk.W)
    for tag, color in AUDIT_STATUS_TAG_COLORS.items():
        tree.tag_configure(tag, foreground=color)
    yscroll = ttk.Scrollbar(tree_wrap, orient=tk.VERTICAL, command=tree.yview)
    xscroll = ttk.Scrollbar(tree_wrap, orient=tk.HORIZONTAL, command=tree.xview)
    tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
    tree.grid(row=0, column=0, sticky="nsew")
    yscroll.grid(row=0, column=1, sticky="ns")
    xscroll.grid(row=1, column=0, sticky="ew")
    tree_wrap.rowconfigure(0, weight=1)
    tree_wrap.columnconfigure(0, weight=1)

    def refresh_tree(*_):
        tree.delete(*tree.get_children())
        result = filter_table_access_audit_logs(
            logs_state["logs"],
            selected_status=status_var.get(),
            keyword=search_var.get(),
            log_text_func=window.table_access_log_text,
        )
        for item in result["visible"]:
            tree.insert("", tk.END, iid=str(item["index"]), values=item["row"], tags=(item["tag"],))
        summary_var.set(result["summary"])

    def reload_logs():
        logs_state["logs"] = list(window.last_table_access_logs or [])
        refresh_tree()

    def clear_logs():
        window.last_table_access_logs = []
        logs_state["logs"] = []
        refresh_tree()

    def show_log_detail(event=None):
        sel = tree.selection()
        if not sel:
            return
        item = logs_state["logs"][int(sel[0])]
        messagebox.showinfo("审计日志详情", window.table_access_log_text(item), parent=win)

    def export_logs():
        if not logs_state["logs"]:
            messagebox.showwarning("提示", "当前没有可导出的审计日志。", parent=win)
            return
        path = filedialog.asksaveasfilename(
            title="导出表访问审计日志",
            defaultextension=".csv",
            filetypes=[("CSV文件", "*.csv"), ("所有文件", "*.*")],
            parent=win,
        )
        if not path:
            return
        export_table_access_audit_logs(logs_state["logs"], path)
        messagebox.showinfo("导出完成", f"已导出审计日志：\n{path}", parent=win)

    tree.bind("<Double-1>", show_log_detail)
    status_var.trace_add("write", refresh_tree)
    search_var.trace_add("write", refresh_tree)

    bottom = ttk.Frame(win, padding=(8, 0, 8, 8))
    bottom.pack(fill=tk.X)
    ttk.Button(bottom, text="刷新最近日志", command=reload_logs).pack(side=tk.LEFT, padx=4)
    ttk.Button(bottom, text="导出CSV", command=export_logs).pack(side=tk.LEFT, padx=4)
    ttk.Button(bottom, text="清空最近日志", command=clear_logs).pack(side=tk.LEFT, padx=4)
    ttk.Button(bottom, text="详情", command=show_log_detail).pack(side=tk.LEFT, padx=4)
    ttk.Button(bottom, text="关闭", command=win.destroy).pack(side=tk.RIGHT, padx=4)

    refresh_tree()
    if not logs_state["logs"]:
        summary_var.set("最近日志 0 条。先预览或执行一次工作流后，这里会显示表访问审计。")
    window.center_toplevel(win, window.window, 1320, 700)
