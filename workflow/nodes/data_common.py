# -*- coding: utf-8 -*-
"""Shared helpers for pure data-shaping workflow nodes."""

import re

from core.data_utils import normalize_rows, safe_cell


MAX_EXPANDED_ROWS = 200000
MAX_TARGET_CELLS = 1000000


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


def ensure_row_count(rows, row_count, col_count, max_expanded_rows=MAX_EXPANDED_ROWS):
    if row_count > max_expanded_rows:
        raise ValueError(
            f"目标行数 {row_count} 超过安全上限 {max_expanded_rows}，"
            "请缩小填充范围或分批处理。"
        )
    rows = normalize_rows(rows, col_count)
    while len(rows) < row_count:
        rows.append([""] * col_count)
    return rows


def ensure_target_cell_limit(row_count, col_count, max_target_cells=MAX_TARGET_CELLS):
    total = max(0, int(row_count)) * max(0, int(col_count))
    if total > max_target_cells:
        raise ValueError(
            f"目标单元格数量 {total} 超过安全上限 {max_target_cells}，"
            "请缩小处理区域或分批执行。"
        )
    return total


def ensure_column_count(headers, rows, col_count, base_name="区域复制列"):
    headers = list(headers)
    rows = normalize_rows(rows, len(headers))
    while len(headers) < col_count:
        new_name = get_unique_header(f"{base_name}{len(headers) + 1}", headers)
        headers.append(new_name)
        for row in rows:
            row.append("")
    return headers, rows


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


def safe_int(value, default=0):
    try:
        return int(str(value).strip())
    except Exception:
        return default


def parse_separator_text(text):
    value = "" if text is None else str(text)
    replacements = [
        ("{Windows换行}", "\r\n"),
        ("{windows换行}", "\r\n"),
        ("{换行符}", "\n"),
        ("{换行}", "\n"),
        ("{newline}", "\n"),
        ("{NEWLINE}", "\n"),
        ("{制表符}", "\t"),
        ("{tab}", "\t"),
        ("{TAB}", "\t"),
        ("{空格}", " "),
        ("{space}", " "),
        ("{SPACE}", " "),
        ("{空字符}", ""),
        ("{empty}", ""),
        ("{EMPTY}", ""),
    ]
    for key, real in replacements:
        value = value.replace(key, real)
    value = value.replace("\\r\\n", "\r\n")
    value = value.replace("\\n", "\n")
    value = value.replace("\\t", "\t")
    return value


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


def row_is_empty(row, col_count):
    fixed = list(row) + [""] * max(0, col_count - len(row))
    return all(str(value).strip() == "" for value in fixed[:col_count])


def last_non_empty_row_index_by_field(headers, rows, field_name):
    idx = field_index(headers, field_name)
    normalized = normalize_rows(rows, len(headers))
    for row_idx in range(len(normalized) - 1, -1, -1):
        if safe_cell(normalized[row_idx], idx).strip() != "":
            return row_idx
    return -1
