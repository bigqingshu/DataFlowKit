# -*- coding: utf-8 -*-
"""Pure helpers for the selected-columns write workflow node."""

from core.data_utils import normalize_rows


SELECTED_COLUMNS_PREVIEW_HEADERS = ["来源表", "来源行", "来源字段", "来源值", "目标表", "目标行", "目标字段", "原值", "动作"]


def get_selected_columns_write_selected_fields(config, source_headers):
    fields = [field for field in (config.get("selected_fields", []) or []) if field in source_headers]
    if not fields:
        fields = list(source_headers)
    return fields


def make_selected_columns_target_fields(config, selected_fields):
    mode = config.get("field_name_mode", "使用原字段名")
    mapping = {
        item.get("source_field", ""): (item.get("target_field", "") or item.get("source_field", ""))
        for item in (config.get("field_mappings", []) or [])
    }
    result = []
    used = {}
    for field in selected_fields:
        if mode == "添加前缀":
            name = f"{config.get('target_prefix', '')}{field}"
        elif mode == "添加后缀":
            name = f"{field}{config.get('target_suffix', '')}"
        elif mode == "手动字段映射":
            name = mapping.get(field, field)
        else:
            name = field
        name = str(name or field).strip() or field
        base = name
        if base in used:
            used[base] += 1
            name = f"{base}_{used[base]}"
        else:
            used[base] = 1
        while name in result:
            used[base] = used.get(base, 1) + 1
            name = f"{base}_{used[base]}"
        result.append(name)
    return result


def selected_columns_should_write(old_value, new_value, overwrite_rule):
    old = "" if old_value is None else str(old_value)
    new = "" if new_value is None else str(new_value)
    if overwrite_rule == "覆盖全部":
        return True
    if overwrite_rule == "只写入空单元格":
        return old == ""
    if overwrite_rule == "目标已有值则跳过":
        return old == ""
    if overwrite_rule == "目标已有值且不同才覆盖":
        return old != new
    return old == ""


def normalize_selected_columns_write_mode(write_mode):
    """统一“选定列写入指定表”的写入范围。"""
    mode = str(write_mode or "局部覆盖，保留目标原行数").strip()
    legacy_map = {
        "复制列到目标表新建字段": "局部覆盖，保留目标原行数",
        "追加到目标表末尾": "局部覆盖，保留目标原行数",
        "按来源完整结构写入": "按来源完整结构覆盖",
    }
    mode = legacy_map.get(mode, mode)
    valid = [
        "局部覆盖，保留目标原行数",
        "清空目标字段后覆盖，保留目标原行数",
        "按来源完整结构覆盖",
        "覆盖重建目标表",
    ]
    if mode not in valid:
        return "局部覆盖，保留目标原行数"
    return mode


def build_selected_columns_write_preview_rows(
    config,
    source_headers,
    source_rows,
    source_name,
    target_headers,
    target_rows,
    target_name,
):
    selected_fields = get_selected_columns_write_selected_fields(config, source_headers)
    target_fields = make_selected_columns_target_fields(config, selected_fields)
    src_indexes = [source_headers.index(field) for field in selected_fields]
    target_index = {header: i for i, header in enumerate(target_headers)}
    write_mode = normalize_selected_columns_write_mode(config.get("write_mode", "复制列到目标表新建字段"))
    overwrite_rule = config.get("overwrite_rule", "只写入空单元格")
    preview_rows = []

    for r_idx, src_row in enumerate(normalize_rows(source_rows, len(source_headers)), start=1):
        target_row_no = r_idx
        for source_field, target_field, src_col in zip(selected_fields, target_fields, src_indexes):
            new_value = src_row[src_col] if src_col < len(src_row) else ""
            old_value = ""
            field_exists = target_field in target_index
            row_exists = target_row_no <= len(target_rows)
            if field_exists and row_exists:
                target_col = target_index[target_field]
                old_row = target_rows[target_row_no - 1]
                if target_col < len(old_row):
                    old_value = old_row[target_col]
            if write_mode == "覆盖重建目标表":
                action = "重建目标表后写入"
            elif write_mode == "按来源完整结构覆盖":
                action = "按来源完整结构覆盖：目标多余旧行将被丢弃"
            elif write_mode == "清空目标字段后覆盖，保留目标原行数":
                action = "先清空目标字段整列，再按来源行写入"
            else:
                parts = []
                if not field_exists:
                    parts.append("新建字段")
                if not row_exists:
                    parts.append("新增目标行")
                if selected_columns_should_write(old_value, new_value, overwrite_rule):
                    parts.append("写入/覆盖")
                else:
                    parts.append("按覆盖策略跳过")
                action = "；".join(parts)
            preview_rows.append([
                source_name,
                str(r_idx),
                source_field,
                new_value,
                target_name,
                str(target_row_no),
                target_field,
                old_value,
                action,
            ])
    return list(SELECTED_COLUMNS_PREVIEW_HEADERS), preview_rows


def apply_selected_columns_to_memory_table(target_headers, target_rows, selected_target_headers, selected_rows, config):
    """把选定列数据写入内存表，返回新的 headers/rows。"""
    target_headers = list(target_headers or [])
    target_rows = [list(row) for row in (target_rows or [])]
    write_mode = normalize_selected_columns_write_mode(config.get("write_mode", "局部覆盖，保留目标原行数"))
    overwrite_rule = config.get("overwrite_rule", "只写入空单元格")

    if write_mode == "覆盖重建目标表":
        return list(selected_target_headers), [list(row) for row in selected_rows]

    headers_out = list(target_headers)
    for header in selected_target_headers:
        if header not in headers_out:
            headers_out.append(header)

    if write_mode == "按来源完整结构覆盖":
        rows_out = [[""] * len(headers_out) for _ in selected_rows]
    else:
        rows_out = normalize_rows(target_rows, len(headers_out))
        while len(rows_out) < len(selected_rows):
            rows_out.append([""] * len(headers_out))
        if write_mode == "清空目标字段后覆盖，保留目标原行数":
            for row in rows_out:
                while len(row) < len(headers_out):
                    row.append("")
                for header in selected_target_headers:
                    row[headers_out.index(header)] = ""

    selected_idx = {header: i for i, header in enumerate(selected_target_headers)}
    for r_idx, selected_row in enumerate(selected_rows):
        if r_idx >= len(rows_out):
            break
        while len(rows_out[r_idx]) < len(headers_out):
            rows_out[r_idx].append("")
        for header in selected_target_headers:
            target_col = headers_out.index(header)
            new_value = selected_row[selected_idx[header]] if selected_idx[header] < len(selected_row) else ""
            old_value = rows_out[r_idx][target_col] if target_col < len(rows_out[r_idx]) else ""
            if selected_columns_should_write(old_value, new_value, overwrite_rule):
                rows_out[r_idx][target_col] = new_value
    return headers_out, rows_out


def build_selected_columns_write_payload(config, source_headers, source_rows):
    selected_fields = get_selected_columns_write_selected_fields(config, source_headers)
    target_fields = make_selected_columns_target_fields(config, selected_fields)
    src_indexes = [source_headers.index(field) for field in selected_fields]
    selected_rows = []
    for row in normalize_rows(source_rows, len(source_headers)):
        selected_rows.append([row[i] if i < len(row) else "" for i in src_indexes])
    return selected_fields, target_fields, selected_rows
