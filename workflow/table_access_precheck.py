# -*- coding: utf-8 -*-
"""Pure helpers for workflow table-access precheck."""


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


def _has_any_permission(permissions, keys):
    return any((permissions or {}).get(key) for key in keys)


def _permission_labels(keys, permission_label_map=None):
    labels = permission_label_map or {}
    return "、".join(labels.get(key, key) for key in keys)


def evaluate_expected_table_access(
    node_label,
    node,
    expected,
    actual=None,
    permission_label_map=None,
    execute_actions=True,
    db_path="",
    db_exists=None,
    sqlite_tables=None,
    produced_transit=None,
    write_mode_formatter=None,
):
    """Compare one expected table-access entry with its actual grant."""
    if not isinstance(expected, dict):
        return {"skip": True, "issues": [], "produced_transit": []}

    raw_table = str(expected.get("table", "") or "").strip()
    table_pattern = str(expected.get("table_pattern", "") or "").strip()
    table = raw_table or table_pattern
    dynamic_table = bool(table_pattern)
    source_type = str(expected.get("source_type", "") or "").strip()
    expected_perms = expected.get("permissions") or {}
    required = [key for key, value in expected_perms.items() if value]
    produced_transit = set(produced_transit or set())
    issues = []

    if expected.get("is_current_table") or raw_table == "__CURRENT_TABLE__":
        return {"skip": True, "issues": [], "produced_transit": []}
    if not table:
        issues.append(make_table_access_precheck_issue(
            "warning",
            node_label,
            node,
            expected,
            "节点配置会访问表，但表名为空。",
            "回到节点配置或字段权限层中补齐表名。",
            write_mode_formatter=write_mode_formatter,
        ))
        return {"skip": True, "issues": issues, "produced_transit": []}

    if actual is None:
        severity = "error" if _has_any_permission(expected_perms, WRITE_TABLE_PERMISSIONS) else "warning"
        issues.append(make_table_access_precheck_issue(
            severity,
            node_label,
            node,
            expected,
            "当前 table_access 中缺少该表角色。",
            "打开字段权限层，重建默认映射或手动添加表角色。",
            write_mode_formatter=write_mode_formatter,
        ))
        actual_perms = {}
    else:
        actual_perms = actual.get("permissions") or {}
        missing = [key for key in required if not bool(actual_perms.get(key))]
        if missing:
            missing_text = _permission_labels(missing, permission_label_map)
            severity = "error" if _has_any_permission({key: True for key in missing}, WRITE_TABLE_PERMISSIONS) else "warning"
            issues.append(make_table_access_precheck_issue(
                severity,
                node_label,
                node,
                expected,
                f"实际授权缺少：{missing_text}。",
                "在字段权限层中补齐权限，或调整节点写入设置。",
                write_mode_formatter=write_mode_formatter,
            ))

    effective_perms = actual_perms or expected_perms
    risky = [label for key, label in RISKY_TABLE_PERMISSIONS.items() if effective_perms.get(key)]
    if risky and _has_any_permission(effective_perms, WRITE_TABLE_PERMISSIONS):
        severity = "warning" if execute_actions else "info"
        issues.append(make_table_access_precheck_issue(
            severity,
            node_label,
            node,
            expected,
            "包含高风险写入权限：" + "、".join(risky),
            "执行前确认目标表和备份策略。",
            category="risk",
            blocking=False,
            write_mode_formatter=write_mode_formatter,
        ))
    if (
        expected.get("declared_by")
        and source_type == "SQLite表"
        and table_pattern in {"*", "%"}
        and _has_any_permission(effective_perms, WRITE_TABLE_PERMISSIONS)
    ):
        issues.append(make_table_access_precheck_issue(
            "warning" if execute_actions else "info",
            node_label,
            node,
            expected,
            "插件声明的动态写表范围过宽。",
            "尽量设置表名前缀或更窄的 table_pattern，避免插件写入任意 SQLite 表。",
            category="risk",
            blocking=False,
            write_mode_formatter=write_mode_formatter,
        ))

    read_write_keys = ("read_table", "write_table", "create_table", "append_rows", "update_rows", "replace_table")
    write_read_exempt_keys = ("write_table", "create_table", "replace_table")
    if source_type == "SQLite表":
        if _has_any_permission(expected_perms, read_write_keys) and not db_path:
            issues.append(make_table_access_precheck_issue(
                "error",
                node_label,
                node,
                expected,
                "节点需要访问 SQLite 表，但当前未设置数据库路径。",
                "先在主界面选择或创建 SQLite 数据库。",
                write_mode_formatter=write_mode_formatter,
            ))
        if db_path and db_exists is False and expected_perms.get("read_table") and not _has_any_permission(expected_perms, write_read_exempt_keys):
            issues.append(make_table_access_precheck_issue(
                "error",
                node_label,
                node,
                expected,
                f"SQLite 数据库文件不存在，无法读取表：{table}",
                "检查数据库路径，或先创建/导入该数据库。",
                write_mode_formatter=write_mode_formatter,
            ))
        if (
            not dynamic_table
            and sqlite_tables is not None
            and expected_perms.get("read_table")
            and not _has_any_permission(expected_perms, write_read_exempt_keys)
            and table not in sqlite_tables
        ):
            issues.append(make_table_access_precheck_issue(
                "error",
                node_label,
                node,
                expected,
                f"SQLite 来源表不存在：{table}",
                "检查表名或先创建/导入该表。",
                write_mode_formatter=write_mode_formatter,
            ))

    produced_names = []
    if source_type == "中转副表":
        transit_name = normalize_precheck_transit_name(table)
        is_writer = _has_any_permission(expected_perms, ("write_table", "create_table", "append_rows", "update_rows", "replace_table"))
        is_reader = expected_perms.get("read_table") and not is_writer
        if is_reader and transit_name and transit_name not in produced_transit:
            issues.append(make_table_access_precheck_issue(
                "warning",
                node_label,
                node,
                expected,
                f"读取的中转副表在当前节点之前未看到生成者：{table}",
                "确认前面有保存中转/插件输出/循环结果节点，或先运行生成该中转副表。",
                write_mode_formatter=write_mode_formatter,
            ))
        if is_writer and transit_name:
            produced_names.append(transit_name)

    return {
        "skip": False,
        "issues": issues,
        "actual_perms": actual_perms,
        "expected_perms": expected_perms,
        "effective_perms": effective_perms,
        "produced_transit": produced_names,
        "table": table,
        "source_type": source_type,
    }


def evaluate_field_access(node_label, node, expected, target, expected_fperms, actual_fperms, write_mode_formatter=None):
    issues = []
    if expected_fperms.get("write_field") and actual_fperms.get("protect_field"):
        issues.append(make_table_access_precheck_issue(
            "error",
            node_label,
            node,
            expected,
            f"字段被保护但节点需要写入：{target}",
            "取消字段保护，或调整节点输出字段。",
            write_mode_formatter=write_mode_formatter,
        ))
    if expected_fperms.get("read_field") and "read_field" in actual_fperms and not actual_fperms.get("read_field"):
        issues.append(make_table_access_precheck_issue(
            "warning",
            node_label,
            node,
            expected,
            f"字段读权限被关闭：{target}",
            "补齐字段读权限，或从节点配置中移除该字段。",
            write_mode_formatter=write_mode_formatter,
        ))
    return issues


def evaluate_unmatched_actual_table_access(node_label, node, actual, write_mode_formatter=None):
    if not isinstance(actual, dict):
        return []
    if actual.get("is_current_table") or actual.get("table") == "__CURRENT_TABLE__":
        return []
    status = table_access_entry_status(actual)
    if status in ("未绑定", "未授权"):
        return [make_table_access_precheck_issue(
            "warning",
            node_label,
            node,
            actual,
            f"手动表角色状态异常：{status}",
            "删除无效表角色，或补齐表名/权限。",
            write_mode_formatter=write_mode_formatter,
        )]
    if status == "危险写入":
        return [make_table_access_precheck_issue(
            "warning",
            node_label,
            node,
            actual,
            "手动表角色包含高风险写入权限。",
            "确认这是节点真实需要的写入范围。",
            category="risk",
            blocking=False,
            write_mode_formatter=write_mode_formatter,
        )]
    return []


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
