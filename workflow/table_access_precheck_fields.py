# -*- coding: utf-8 -*-
"""Field-level helpers for table-access precheck."""

from workflow.table_access_precheck_display import make_table_access_precheck_issue


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


def table_access_field_items(entry):
    mapping = (entry or {}).get("field_mapping") or {}
    if isinstance(mapping, dict):
        items = []
        for key, value in mapping.items():
            if isinstance(value, dict):
                items.append((str(key), value))
        return items
    if isinstance(mapping, list):
        items = []
        for idx, value in enumerate(mapping):
            if isinstance(value, dict):
                key = value.get("key") or f"field_{idx + 1}"
                items.append((str(key), value))
        return items
    return []


def find_table_access_field_rule(entry, target="", source="", field_index=None):
    target = str(target or "").strip()
    source = str(source or "").strip()
    mapping_mode = str((entry or {}).get("field_mapping_mode", "") or "").strip()
    by_order = mapping_mode in {"by_order", "按列顺序", "按顺序", "order"}
    field_pos = None
    if field_index is not None:
        try:
            field_pos = int(field_index) + 1
        except Exception:
            field_pos = None
    for _, item in table_access_field_items(entry):
        if not isinstance(item, dict):
            continue
        rule_mode = str(item.get("match_mode", "") or "").strip()
        if (by_order or rule_mode in {"by_order", "按列顺序", "按顺序", "order"}) and field_pos is not None:
            for key in ("target_index", "source_index", "index", "column_index"):
                raw_index = item.get(key)
                if raw_index in ("", None):
                    continue
                try:
                    if int(raw_index) == field_pos:
                        return item
                except Exception:
                    continue
        candidates = [
            str(item.get("target_field", "") or "").strip(),
            str(item.get("source_field", "") or "").strip(),
            str(item.get("field", "") or "").strip(),
            str(item.get("name", "") or "").strip(),
        ]
        if target and target in candidates:
            return item
        if source and source in candidates:
            return item
    return None


def evaluate_field_mapping_access(node_label, node, expected, actual, write_mode_formatter=None):
    expected_fields = (expected or {}).get("field_mapping") or {}
    actual_fields = (actual or {}).get("field_mapping") or {}
    if not isinstance(expected_fields, dict) or not isinstance(actual_fields, dict):
        return []

    issues = []
    for field_index, (_, field_rule) in enumerate(expected_fields.items()):
        if not isinstance(field_rule, dict):
            continue
        target = str(field_rule.get("target_field") or field_rule.get("source_field") or "").strip()
        source = str(field_rule.get("source_field") or "").strip()
        expected_fperms = field_rule.get("permissions") or {}
        if not target:
            continue
        actual_rule = find_table_access_field_rule(actual, target=target, source=source, field_index=field_index)
        if actual_rule is None:
            continue
        actual_fperms = actual_rule.get("permissions") or {}
        issues.extend(evaluate_field_access(
            node_label,
            node,
            expected,
            target,
            expected_fperms,
            actual_fperms,
            write_mode_formatter=write_mode_formatter,
        ))
    return issues
