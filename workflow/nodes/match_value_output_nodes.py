# -*- coding: utf-8 -*-
"""Match-value output workflow node."""

import re

from core.data_utils import normalize_rows, safe_cell
from workflow.nodes.data_common import field_index


def match_value_output_column_match(source_value, lookup_value, mode):
    """匹配值输出列名节点的匹配规则。"""
    source_value = "" if source_value is None else str(source_value)
    lookup_value = "" if lookup_value is None else str(lookup_value)
    if mode == "完全相等":
        return source_value == lookup_value
    if mode == "当前值包含匹配值":
        return lookup_value != "" and lookup_value in source_value
    if mode == "匹配值包含当前值":
        return source_value != "" and source_value in lookup_value
    if mode == "忽略大小写完全相等":
        return source_value.lower() == lookup_value.lower()
    if mode == "忽略大小写当前值包含匹配值":
        return lookup_value != "" and lookup_value.lower() in source_value.lower()
    if mode == "忽略大小写匹配值包含当前值":
        return source_value != "" and source_value.lower() in lookup_value.lower()
    if mode == "正则匹配":
        if not lookup_value:
            return False
        try:
            return re.search(lookup_value, source_value) is not None
        except re.error:
            return False
    return False


def apply_match_value_output_field_name_node(headers, rows, config, context=None):
    """匹配值输出列名：用当前表字段值匹配目标记录多个字段，输出命中的字段名。"""
    headers = list(headers)
    rows = normalize_rows(rows, len(headers))
    source_field = str(config.get("source_field", "")).strip()
    lookup_table = str(config.get("lookup_table", "")).strip()
    lookup_fields = [str(field).strip() for field in config.get("lookup_fields", []) if str(field).strip()]
    match_mode = config.get("match_mode", "完全相等")
    if not source_field:
        raise ValueError("请选择当前表匹配字段。")
    if source_field not in headers:
        raise ValueError(f"当前表字段不存在：{source_field}")
    if not lookup_table:
        raise ValueError("请选择匹配表或中转副表。")
    if not lookup_fields:
        raise ValueError("请选择至少一个参与匹配的目标表字段。")

    lookup_columns = list((context or {}).get("lookup_columns", []))
    lookup_records = list((context or {}).get("lookup_records", []))
    missing = [field for field in lookup_fields if field not in lookup_columns]
    if missing:
        raise ValueError("匹配表字段不存在：" + ", ".join(missing))

    output_field = str(config.get("output_field", "匹配字段名")).strip() or "匹配字段名"
    output_match_value = bool(config.get("output_match_value", True))
    match_value_field = str(config.get("match_value_field", "匹配值")).strip() or "匹配值"
    output_match_row = bool(config.get("output_match_row", True))
    match_row_field = str(config.get("match_row_field", "匹配行号")).strip() or "匹配行号"
    output_status = bool(config.get("output_status", True))
    status_field = str(config.get("status_field", "匹配状态")).strip() or "匹配状态"
    multi_policy = config.get("multi_match_policy", "合并所有字段名")
    sep = str(config.get("multi_match_separator", ";"))
    no_match_value = str(config.get("no_match_value", "未匹配"))
    skip_empty_lookup_value = bool(config.get("skip_empty_lookup_value", True))

    source_idx = field_index(headers, source_field)
    out_headers = list(headers)
    out_rows = [list(row) for row in rows]

    def ensure_field(name):
        if not name:
            return None
        if name not in out_headers:
            out_headers.append(name)
            for output_row in out_rows:
                output_row.append("")
        return out_headers.index(name)

    out_idx = ensure_field(output_field)
    match_val_idx = ensure_field(match_value_field) if output_match_value else None
    match_row_idx = ensure_field(match_row_field) if output_match_row else None
    status_idx = ensure_field(status_field) if output_status else None

    success_count = 0
    multi_count = 0
    no_count = 0

    def unique_join(values):
        result = []
        seen = set()
        for value in values:
            text = "" if value is None else str(value)
            if text not in seen:
                result.append(text)
                seen.add(text)
        return sep.join(result)

    for row_index, row in enumerate(out_rows):
        _check_cancelled(context, row_index)
        source_value = safe_cell(row, source_idx)
        matches = []
        if source_value != "":
            for record in lookup_records:
                for field in lookup_fields:
                    lookup_value = str(record.get(field, ""))
                    if skip_empty_lookup_value and lookup_value == "":
                        continue
                    if match_value_output_column_match(source_value, lookup_value, match_mode):
                        matches.append({
                            "field": field,
                            "value": lookup_value,
                            "row_index": record.get("__row_index__", ""),
                        })

        if not matches:
            no_count += 1
            if out_idx is not None:
                row[out_idx] = no_match_value
            if match_val_idx is not None:
                row[match_val_idx] = ""
            if match_row_idx is not None:
                row[match_row_idx] = ""
            if status_idx is not None:
                row[status_idx] = "未匹配"
            continue

        if len(matches) == 1:
            match = matches[0]
            success_count += 1
            if out_idx is not None:
                row[out_idx] = match["field"]
            if match_val_idx is not None:
                row[match_val_idx] = match["value"]
            if match_row_idx is not None:
                row[match_row_idx] = str(match["row_index"])
            if status_idx is not None:
                row[status_idx] = "成功"
        else:
            multi_count += 1
            if multi_policy == "取第一个匹配字段名":
                match = matches[0]
                if out_idx is not None:
                    row[out_idx] = match["field"]
                if match_val_idx is not None:
                    row[match_val_idx] = match["value"]
                if match_row_idx is not None:
                    row[match_row_idx] = str(match["row_index"])
                if status_idx is not None:
                    row[status_idx] = f"多匹配取第一，共{len(matches)}项"
            elif multi_policy == "标记为多匹配":
                if out_idx is not None:
                    row[out_idx] = "多匹配"
                if match_val_idx is not None:
                    row[match_val_idx] = unique_join([match["value"] for match in matches])
                if match_row_idx is not None:
                    row[match_row_idx] = unique_join([match["row_index"] for match in matches])
                if status_idx is not None:
                    row[status_idx] = f"多匹配，共{len(matches)}项"
            else:
                if out_idx is not None:
                    row[out_idx] = unique_join([match["field"] for match in matches])
                if match_val_idx is not None:
                    row[match_val_idx] = unique_join([match["value"] for match in matches])
                if match_row_idx is not None:
                    row[match_row_idx] = unique_join([match["row_index"] for match in matches])
                if status_idx is not None:
                    row[status_idx] = f"多匹配，共{len(matches)}项"

    msg = f"匹配值输出列名完成：成功 {success_count} 行，多匹配 {multi_count} 行，未匹配 {no_count} 行"
    return out_headers, out_rows, msg


def _check_cancelled(context, index):
    callback = (context or {}).get("check_cancelled")
    if callable(callback):
        callback(index)
