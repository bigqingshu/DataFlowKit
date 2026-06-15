# -*- coding: utf-8 -*-
"""Pure data-shaping workflow nodes."""

import re

from core.data_utils import normalize_rows, safe_cell


def field_index(headers, field):
    if field not in headers:
        raise ValueError(f"字段不存在：{field}")
    return headers.index(field)


def get_unique_header(base_name, headers):
    name = str(base_name or "新字段").strip() or "新字段"
    if name not in headers:
        return name
    counter = 2
    while f"{name}_{counter}" in headers:
        counter += 1
    return f"{name}_{counter}"


def ensure_field_exists(headers, rows, field_name):
    field_name = str(field_name or "新字段").strip() or "新字段"
    headers = list(headers)
    rows = normalize_rows(rows, len(headers))
    if field_name in headers:
        return headers, rows, headers.index(field_name)
    new_name = get_unique_header(field_name, headers)
    headers.append(new_name)
    for row in rows:
        row.append("")
    return headers, rows, len(headers) - 1


def parse_int(value, name):
    try:
        return int(str(value).strip())
    except Exception:
        raise ValueError(f"{name} 必须是整数。")


def parse_row_number(value, name="行号"):
    n = parse_int(value, name)
    if n < 1:
        raise ValueError(f"{name} 必须大于等于 1。")
    return n


def get_positive_int(value, default_value):
    try:
        n = int(str(value).strip())
        return n if n > 0 else default_value
    except Exception:
        return default_value


def compare_values(text, op, value, case_sensitive=True):
    text = "" if text is None else str(text)
    value = "" if value is None else str(value)
    t = text if case_sensitive else text.lower()
    v = value if case_sensitive else value.lower()
    if op == "等于" or op == "完全相等":
        return t == v
    if op == "不等于":
        return t != v
    if op == "包含":
        return v in t
    if op == "不包含":
        return v not in t
    if op == "开头是":
        return t.startswith(v)
    if op == "结尾是":
        return t.endswith(v)
    if op == "为空":
        return text == ""
    if op == "不为空":
        return text != ""
    if op == "正则匹配":
        flags = 0 if case_sensitive else re.IGNORECASE
        return re.search(value, text, flags) is not None
    if op in ["大于", "小于", "大于等于", "小于等于"]:
        try:
            a = float(text)
            b = float(value)
        except Exception:
            return False
        if op == "大于":
            return a > b
        if op == "小于":
            return a < b
        if op == "大于等于":
            return a >= b
        if op == "小于等于":
            return a <= b
    return False


def apply_delete_columns_node(headers, rows, config):
    delete_fields = set(config.get("fields", []))
    keep_indexes = [i for i, header in enumerate(headers) if header not in delete_fields]
    new_headers = [headers[i] for i in keep_indexes]
    normalized = normalize_rows(rows, len(headers))
    new_rows = [[safe_cell(row, i) for i in keep_indexes] for row in normalized]
    return new_headers, new_rows, f"删除 {len(headers)-len(new_headers)} 列"


def apply_move_columns_node(headers, rows, config):
    order = list(config.get("order", []))
    final_order = [header for header in order if header in headers]
    for header in headers:
        if header not in final_order:
            final_order.append(header)
    indexes = [headers.index(header) for header in final_order]
    normalized = normalize_rows(rows, len(headers))
    new_rows = [[safe_cell(row, i) for i in indexes] for row in normalized]
    return final_order, new_rows, "已调整列顺序"


def apply_copy_column_node(headers, rows, config):
    src_idx = field_index(headers, config.get("source_field", ""))
    headers = list(headers)
    new_rows = normalize_rows(rows, len(headers))
    values = []
    trim_value = bool(config.get("trim_value", False))
    empty_default = str(config.get("empty_default", ""))
    for row in new_rows:
        value = safe_cell(row, src_idx)
        if trim_value:
            value = value.strip()
        if value == "" and empty_default != "":
            value = empty_default
        values.append(value)
    if config.get("output_mode", "生成新字段") == "覆盖已有字段":
        headers, new_rows, target_idx = ensure_field_exists(headers, new_rows, config.get("target_field", ""))
        for i, row in enumerate(new_rows):
            row[target_idx] = values[i]
        return headers, new_rows, f"复制列并覆盖字段 {headers[target_idx]}"
    new_header = get_unique_header(config.get("new_field", "复制列"), headers)
    headers.append(new_header)
    for i, row in enumerate(new_rows):
        row.append(values[i])
    return headers, new_rows, f"复制列为新字段 {new_header}"


def apply_copy_row_node(headers, rows, config):
    headers = list(headers)
    new_rows = normalize_rows(rows, len(headers))
    if not new_rows:
        raise ValueError("当前没有可复制的数据行。")
    source_idx = parse_row_number(config.get("source_row", "1"), "源行号") - 1
    if source_idx < 0 or source_idx >= len(new_rows):
        raise ValueError("源行号超出当前数据范围。")
    copy_count = get_positive_int(config.get("copy_count", "1"), 1)
    copies = [list(new_rows[source_idx]) for _ in range(copy_count)]
    mode = config.get("insert_mode", "表尾")
    if mode == "表尾":
        insert_at = len(new_rows)
    elif mode == "原行下方":
        insert_at = source_idx + 1
    else:
        insert_row = parse_row_number(config.get("insert_row", "1"), "指定行号") - 1
        insert_row = max(0, min(insert_row, len(new_rows)))
        insert_at = insert_row if mode == "指定行前" else min(insert_row + 1, len(new_rows))
    new_rows[insert_at:insert_at] = copies
    return headers, new_rows, f"复制第 {source_idx + 1} 行 {copy_count} 次"


def parse_row_spec_to_indexes(spec, max_rows):
    indexes = set()
    text = str(spec or "").replace("，", ",").strip()
    if not text:
        return indexes
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        part_norm = part.replace("~", "-").replace("～", "-")
        if "-" in part_norm:
            left, right = part_norm.split("-", 1)
            try:
                start = int(left.strip())
                end = int(right.strip())
            except Exception:
                continue
            if start > end:
                start, end = end, start
            for row_no in range(start, end + 1):
                if 1 <= row_no <= max_rows:
                    indexes.add(row_no - 1)
        else:
            try:
                row_no = int(part_norm)
            except Exception:
                continue
            if 1 <= row_no <= max_rows:
                indexes.add(row_no - 1)
    return indexes


def apply_delete_rows_node(headers, rows, config):
    headers = list(headers)
    normalized = normalize_rows(rows, len(headers))
    total = len(normalized)
    mode = config.get("delete_mode", "按行号列表")
    delete_indexes = set()

    if mode == "按行号列表":
        delete_indexes = parse_row_spec_to_indexes(config.get("row_spec", ""), total)

    elif mode == "按行号范围":
        start_row = parse_row_number(config.get("start_row", "1"), "起始行")
        end_row = parse_row_number(config.get("end_row", "1"), "结束行")
        if start_row > end_row:
            start_row, end_row = end_row, start_row
        start_row = max(1, start_row)
        end_row = min(total, end_row)
        if start_row <= end_row:
            delete_indexes = set(range(start_row - 1, end_row))

    elif mode == "按条件删除":
        field = config.get("condition_field", "")
        if field not in headers:
            raise ValueError(f"条件字段不存在：{field}")
        idx = headers.index(field)
        op = config.get("condition_op", "包含")
        value = config.get("condition_value", "")
        case_sensitive = bool(config.get("case_sensitive", True))
        for row_idx, row in enumerate(normalized):
            if compare_values(safe_cell(row, idx), op, value, case_sensitive=case_sensitive):
                delete_indexes.add(row_idx)

    elif mode == "删除空行":
        empty_mode = config.get("empty_mode", "整行为空")
        if empty_mode == "指定字段为空":
            field = config.get("empty_field", "")
            if field not in headers:
                raise ValueError(f"空行判断字段不存在：{field}")
            idx = headers.index(field)
            for row_idx, row in enumerate(normalized):
                if safe_cell(row, idx).strip() == "":
                    delete_indexes.add(row_idx)
        else:
            for row_idx, row in enumerate(normalized):
                if all(safe_cell(row, i).strip() == "" for i in range(len(headers))):
                    delete_indexes.add(row_idx)
    else:
        raise ValueError(f"未知删除行方式：{mode}")

    if not delete_indexes:
        return headers, normalized, "未删除任何行"
    new_rows = [row for i, row in enumerate(normalized) if i not in delete_indexes]
    return headers, new_rows, f"删除 {len(delete_indexes)} 行"
