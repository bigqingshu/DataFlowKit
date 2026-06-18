# -*- coding: utf-8 -*-
"""Display and summary helpers for table-access precheck."""


RISKY_TABLE_PERMISSIONS = {
    "replace_table": "替换整表",
    "clear_table": "清空表/字段",
    "drop_table": "删除表",
    "delete_rows": "删除行",
    "alter_schema": "改表结构",
}

WRITE_TABLE_PERMISSIONS = {
    "write_table",
    "create_table",
    "append_rows",
    "update_rows",
    "clear_table",
    "replace_table",
    "alter_schema",
    "delete_rows",
    "drop_table",
}


def table_access_entry_table_label(entry):
    entry = entry or {}
    table = str(entry.get("table", "") or "").strip()
    pattern = str(entry.get("table_pattern", "") or "").strip()
    if table:
        return table
    if pattern:
        return f"范围:{pattern}"
    return ""


def table_access_operation_summary(entry, write_mode_formatter=None):
    entry = entry or {}
    table = table_access_entry_table_label(entry)
    perms = entry.get("permissions") or {}
    mode = str(entry.get("write_mode", "") or "").strip()
    ops = []
    if entry.get("is_current_table") or table == "__CURRENT_TABLE__":
        if perms.get("write_table") or perms.get("update_rows"):
            return "当前表写入(只记录)" if entry.get("log_only") else "当前表写入"
        if perms.get("read_table"):
            return "当前表读取"
        return "当前表"
    if perms.get("read_table"):
        ops.append("读表")
    if perms.get("write_table"):
        ops.append("写表")
    if perms.get("create_table"):
        ops.append("新建")
    if perms.get("append_rows"):
        ops.append("追加")
    if perms.get("update_rows"):
        ops.append("更新")
    if perms.get("clear_table"):
        ops.append("清空")
    if perms.get("replace_table"):
        ops.append("替换")
    if perms.get("delete_rows"):
        ops.append("删行")
    if perms.get("drop_table"):
        ops.append("删表")
    if not ops:
        return "无操作"
    text = "/".join(ops)
    if not mode:
        return text
    mode_text = write_mode_formatter(mode) if callable(write_mode_formatter) else mode
    return f"{text}；{mode_text}" if mode_text else text


def table_access_entry_status(entry):
    entry = entry or {}
    table = table_access_entry_table_label(entry)
    perms = entry.get("permissions") or {}
    if not table:
        return "未绑定"
    if entry.get("is_current_table") or table == "__CURRENT_TABLE__":
        if perms.get("write_table") or perms.get("update_rows"):
            return "写入只记录" if entry.get("log_only") else "当前表写入"
        return "当前表读取" if perms.get("read_table") else "当前表"
    if not any(bool(v) for v in perms.values()):
        return "未授权"
    risky = [key for key in RISKY_TABLE_PERMISSIONS if perms.get(key)]
    if risky:
        return "危险写入"
    if perms.get("write_table") or perms.get("append_rows") or perms.get("update_rows"):
        return "已授权"
    if perms.get("read_table"):
        return "只读"
    return "待检查"


def normalize_precheck_transit_name(table_name):
    text = str(table_name or "").strip()
    if text.startswith("中转:"):
        return text.split(":", 1)[1].strip()
    return text


def make_table_access_precheck_issue(
    severity,
    node_label,
    node,
    entry,
    message,
    suggestion="",
    category="permission",
    blocking=None,
    write_mode_formatter=None,
):
    entry = entry or {}
    if blocking is None:
        blocking = severity in ("error", "warning")
    return {
        "severity": severity,
        "category": category,
        "blocking": bool(blocking),
        "node": node_label,
        "node_type": (node or {}).get("type", ""),
        "node_name": (node or {}).get("name", ""),
        "role": entry.get("role", ""),
        "source_type": entry.get("source_type", ""),
        "table": table_access_entry_table_label(entry),
        "operation": table_access_operation_summary(entry, write_mode_formatter=write_mode_formatter),
        "message": message,
        "suggestion": suggestion,
    }


def table_access_precheck_sort_key(issue):
    order = {"error": 0, "warning": 1, "info": 2, "ok": 3}
    return (
        order.get(issue.get("severity"), 9),
        str(issue.get("node", "")),
        str(issue.get("table", "")),
    )


def table_access_precheck_actionable(issues):
    return [issue for issue in (issues or []) if issue.get("severity") in ("error", "warning")]


def table_access_precheck_blocking(issues):
    return [issue for issue in (issues or []) if bool(issue.get("blocking"))]


def table_access_precheck_summary_text(issues):
    counts = {"error": 0, "warning": 0, "info": 0, "ok": 0}
    for issue in issues or []:
        sev = issue.get("severity", "info")
        counts[sev] = counts.get(sev, 0) + 1
    if not issues:
        return "权限预检完成：未发现需要处理的表权限问题。"
    blocking_count = len(table_access_precheck_blocking(issues))
    return (
        "权限预检完成："
        f"错误 {counts.get('error', 0)} 项，"
        f"警告 {counts.get('warning', 0)} 项，"
        f"提示 {counts.get('info', 0)} 项，"
        f"阻断 {blocking_count} 项。"
    )


def iter_nodes_for_table_access_precheck(nodes, stop_index=None, prefix=""):
    for idx, node in enumerate(nodes or []):
        if stop_index is not None and not prefix and idx > int(stop_index):
            break
        node_type = (node or {}).get("type", "")
        label = f"{prefix}{idx + 1}.{node_type}"
        yield label, node
        cfg = (node or {}).get("config", {}) if isinstance(node, dict) else {}
        child_nodes = cfg.get("nodes") if isinstance(cfg, dict) else None
        if isinstance(child_nodes, list):
            child_prefix = f"{label} > "
            yield from iter_nodes_for_table_access_precheck(child_nodes, stop_index=None, prefix=child_prefix)
