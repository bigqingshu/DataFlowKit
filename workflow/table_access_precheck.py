# -*- coding: utf-8 -*-
"""Pure helpers for workflow table-access precheck."""

import re

from shared.table_access_policy import table_pattern_matches
from workflow.table_access_precheck_display import (
    RISKY_TABLE_PERMISSIONS,
    WRITE_TABLE_PERMISSIONS,
    iter_nodes_for_table_access_precheck,
    make_table_access_precheck_issue,
    normalize_precheck_transit_name,
    table_access_entry_status,
    table_access_entry_table_label,
    table_access_operation_summary,
    table_access_precheck_actionable,
    table_access_precheck_blocking,
    table_access_precheck_sort_key,
    table_access_precheck_summary_text,
)
from workflow.table_access_precheck_fields import (
    evaluate_field_access,
    evaluate_field_mapping_access,
    find_table_access_field_rule,
    table_access_field_items,
)


def _has_any_permission(permissions, keys):
    return any((permissions or {}).get(key) for key in keys)


def _permission_labels(keys, permission_label_map=None):
    labels = permission_label_map or {}
    return "、".join(labels.get(key, key) for key in keys)


def make_workflow_output_access_entry(output_table, output_mode):
    return {
        "role": "workflow_output",
        "table": str(output_table or "").strip(),
        "table_pattern": "",
        "pattern_type": "glob",
        "declared_by": "",
        "source_type": "SQLite表",
        "is_current_table": False,
        "permissions": {
            "read_table": True,
            "write_table": True,
            "create_table": True,
            "append_rows": False,
            "update_rows": False,
            "clear_table": False,
            "replace_table": output_mode == "覆盖当前表",
            "alter_schema": False,
            "delete_rows": False,
            "drop_table": False,
        },
        "write_mode": str(output_mode or "").strip(),
        "field_mapping_mode": "by_name",
        "field_mapping": {},
        "log_only": False,
    }


def evaluate_workflow_output_precheck(output_mode, output_table, db_path="", write_mode_formatter=None):
    if output_mode not in ("保存为SQLite新表", "覆盖当前表"):
        return []
    entry = make_workflow_output_access_entry(output_table, output_mode)
    node = {"type": "工作流输出"}
    issues = []
    if not db_path:
        issues.append(make_table_access_precheck_issue(
            "error",
            "工作流输出",
            node,
            entry,
            "输出方式需要 SQLite 数据库，但当前未设置数据库路径。",
            "先在主界面选择或创建 SQLite 数据库。",
            write_mode_formatter=write_mode_formatter,
        ))
    if not str(output_table or "").strip():
        issues.append(make_table_access_precheck_issue(
            "error",
            "工作流输出",
            node,
            entry,
            "输出方式需要表名，但输出表名为空。",
            "填写输出表名后再执行。",
            write_mode_formatter=write_mode_formatter,
        ))
    if output_mode == "覆盖当前表":
        issues.append(make_table_access_precheck_issue(
            "warning",
            "工作流输出",
            node,
            entry,
            f"执行后会覆盖 SQLite 表：{str(output_table or '').strip()}",
            "确认备份设置和目标表无误。",
            category="risk",
            blocking=False,
            write_mode_formatter=write_mode_formatter,
        ))
    return issues


def evaluate_plugin_access_declaration_precheck(
    node_label,
    node,
    config,
    needs_declaration,
    has_declaration,
    write_mode_formatter=None,
):
    if (node or {}).get("type", "") != "插件节点":
        return []
    if not needs_declaration or has_declaration:
        return []
    plugin_id = str((config or {}).get("plugin_id", "") or "").strip()
    entry = {
        "role": "plugin_declared",
        "source_type": "SQLite表",
        "table": plugin_id,
    }
    return [make_table_access_precheck_issue(
        "warning",
        node_label,
        node,
        entry,
        "插件标记为数据库写入风险，但未声明表权限规格。",
        "为插件补充 get_table_access_spec() 或 PLUGIN_INFO.table_access_spec，便于执行前确认写库范围。",
        write_mode_formatter=write_mode_formatter,
    )]


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


def sanitize_table_name_for_match(name):
    name = str(name or "").strip()
    if not name:
        return ""
    name = re.sub(r"\W+", "_", name, flags=re.UNICODE)
    if re.match(r"^\d", name):
        name = "t_" + name
    return name


def table_access_entry_match_score(actual, expected):
    actual = actual or {}
    expected = expected or {}
    actual_table = str(actual.get("table", "") or "").strip()
    expected_table = str(expected.get("table", "") or "").strip()
    actual_pattern = str(actual.get("table_pattern", "") or "").strip()
    expected_pattern = str(expected.get("table_pattern", "") or "").strip()
    if expected_pattern:
        if actual_pattern == expected_pattern:
            score = 3
        elif actual_table and table_pattern_matches(actual_table, expected_pattern, expected.get("pattern_type", "glob")):
            score = 2
        else:
            return 0
    elif actual_pattern and expected_table:
        if table_pattern_matches(expected_table, actual_pattern, actual.get("pattern_type", "glob")):
            score = 2
        else:
            return 0
    else:
        if not expected_table:
            return 0
        actual_names = {actual_table, sanitize_table_name_for_match(actual_table)}
        expected_names = {expected_table, sanitize_table_name_for_match(expected_table)}
        actual_names.discard("")
        expected_names.discard("")
        if not actual_names.intersection(expected_names):
            return 0
        score = 1
    actual_source = str(actual.get("source_type", "") or "").strip()
    expected_source = str(expected.get("source_type", "") or "").strip()
    if expected_source and actual_source == expected_source:
        score += 2
    elif expected_source and actual_source and actual_source != expected_source:
        return 0
    if str(actual.get("role", "") or "").strip() == str(expected.get("role", "") or "").strip():
        score += 1
    return score


def find_matching_table_access_entry(actual_tables, expected):
    best = None
    best_score = 0
    for entry in actual_tables or []:
        if not isinstance(entry, dict):
            continue
        score = table_access_entry_match_score(entry, expected)
        if score > best_score:
            best = entry
            best_score = score
    return best


def evaluate_node_table_access_precheck(
    node_label,
    node,
    expected_access,
    actual_access,
    permission_label_map=None,
    execute_actions=True,
    db_path="",
    db_exists=None,
    sqlite_tables=None,
    produced_transit=None,
    needs_plugin_declaration=False,
    has_plugin_declaration=False,
    write_mode_formatter=None,
):
    issues = []
    produced_transit = set(produced_transit or set())
    node_type = (node or {}).get("type", "")
    config = (node or {}).get("config", {}) if isinstance(node, dict) else {}
    issues.extend(evaluate_plugin_access_declaration_precheck(
        node_label,
        node,
        config,
        needs_declaration=node_type == "插件节点" and needs_plugin_declaration,
        has_declaration=node_type == "插件节点" and has_plugin_declaration,
        write_mode_formatter=write_mode_formatter,
    ))

    actual_tables = actual_access.get("tables", []) if isinstance(actual_access, dict) else []
    matched_actual_ids = set()
    produced_names = []
    for expected in (expected_access or {}).get("tables", []):
        if not isinstance(expected, dict):
            continue
        actual = find_matching_table_access_entry(actual_tables, expected)
        if actual is not None:
            matched_actual_ids.add(id(actual))

        expected_result = evaluate_expected_table_access(
            node_label,
            node,
            expected,
            actual=actual,
            permission_label_map=permission_label_map,
            execute_actions=execute_actions,
            db_path=db_path,
            db_exists=db_exists,
            sqlite_tables=sqlite_tables,
            produced_transit=produced_transit,
            write_mode_formatter=write_mode_formatter,
        )
        issues.extend(expected_result.get("issues", []))
        for transit_name in expected_result.get("produced_transit", []) or []:
            produced_transit.add(transit_name)
            produced_names.append(transit_name)
        if expected_result.get("skip"):
            continue
        if actual is not None:
            issues.extend(evaluate_field_mapping_access(
                node_label,
                node,
                expected,
                actual,
                write_mode_formatter=write_mode_formatter,
            ))

    for actual in actual_tables:
        if not isinstance(actual, dict) or id(actual) in matched_actual_ids:
            continue
        issues.extend(evaluate_unmatched_actual_table_access(
            node_label,
            node,
            actual,
            write_mode_formatter=write_mode_formatter,
        ))

    return {
        "issues": issues,
        "produced_transit": produced_names,
        "matched_actual_ids": matched_actual_ids,
    }


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


