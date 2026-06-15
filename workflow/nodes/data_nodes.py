# -*- coding: utf-8 -*-
"""Pure data-shaping workflow nodes."""

import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

from core.data_utils import make_unique_headers, normalize_rows, safe_cell
from shared.datetime_parse_utils import (
    complete_year,
    normalize_datetime_text,
    parse_date_auto_common as shared_parse_date_auto_common,
)


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


def get_config_cell_value(headers, rows, config, target_row_idx=None):
    value_source = config.get("value_source", "手动输入值")
    if value_source == "同行来源字段":
        src_idx = field_index(headers, config.get("source_field", ""))
        if target_row_idx is None or target_row_idx < 0 or target_row_idx >= len(rows):
            return ""
        return safe_cell(rows[target_row_idx], src_idx)
    if value_source == "指定单元格值":
        src_idx = field_index(headers, config.get("source_field", ""))
        src_row = parse_row_number(config.get("source_row", "1"), "取值行号") - 1
        if src_row < 0 or src_row >= len(rows):
            return ""
        return safe_cell(rows[src_row], src_idx)
    return str(config.get("manual_value", ""))


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


def parse_numeric_value_for_column_op(value):
    """列数字运算专用数字解析：使用 Decimal 保留长整数和十进制精度。"""
    text = "" if value is None else str(value).strip()
    if text == "":
        raise ValueError("空值")
    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"不是有效数字：{text}") from exc


def format_numeric_column_result(value, config):
    value = value if isinstance(value, Decimal) else Decimal(str(value))
    decimal_places = str(config.get("decimal_places", "自动"))
    if decimal_places == "自动":
        if value == value.to_integral_value():
            return format(value.quantize(Decimal("1")), "f")
        return format(value.normalize(), "f")
    try:
        places = int(decimal_places)
    except Exception:
        places = 0
    return f"{value:.{max(0, places)}f}"


def get_numeric_node_row_indexes(headers, rows, config):
    mode = config.get("range_mode", "全部行")
    if not rows:
        return []
    if mode == "指定起止行":
        start = parse_row_number(config.get("start_row", "1"), "起始行号") - 1
        end = parse_row_number(config.get("end_row", "1"), "结束行号") - 1
        if start > end:
            start, end = end, start
        start = max(0, start)
        end = min(len(rows) - 1, end)
        return list(range(start, end + 1)) if start <= end else []
    if mode == "填充到参考列数据边界":
        start = parse_row_number(config.get("start_row", "1"), "起始行号") - 1
        end = last_non_empty_row_index_by_field(headers, rows, config.get("reference_field", ""))
        start = max(0, start)
        return list(range(start, end + 1)) if end >= start else []
    return list(range(len(rows)))


def numeric_node_fallback_value(original_value, policy, fixed_value, fail_text):
    if policy == "保留原值":
        return original_value
    if policy == "填写固定值":
        return fixed_value
    if policy in ["标记为计算失败", "标记为除零错误"]:
        return fail_text
    return ""


def apply_numeric_column_node(headers, rows, config, context=None):
    """列数字运算：对指定列进行加、减、乘、除。"""
    headers = list(headers)
    rows = normalize_rows(rows, len(headers))
    if not headers:
        return headers, rows, "列数字运算：无字段，未处理"

    target_field = config.get("target_field", "")
    target_idx = field_index(headers, target_field)
    output_mode = config.get("output_mode", "生成新字段")
    output_field = str(config.get("output_field", "计算结果")).strip() or "计算结果"
    max_expanded_rows = (context or {}).get("max_expanded_rows", MAX_EXPANDED_ROWS)

    if output_mode == "覆盖原字段":
        out_idx = target_idx
    elif output_mode == "写入已有字段":
        headers, rows, out_idx = ensure_field_exists(headers, rows, output_field)
    else:
        new_header = get_unique_header(output_field, headers)
        headers.append(new_header)
        for row in rows:
            row.append("")
        out_idx = len(headers) - 1

    operation = config.get("operation", "加")
    operand_source = config.get("operand_source", "固定值")
    row_indexes = get_numeric_node_row_indexes(headers, rows, config)
    non_number_policy = config.get("non_number_policy", "留空")
    divide_zero_policy = config.get("divide_zero_policy", "留空")
    non_number_fixed = str(config.get("non_number_fixed", ""))
    divide_zero_fixed = str(config.get("divide_zero_fixed", ""))

    operand_field_idx = None
    if operand_source == "另一列同行数值":
        operand_field_idx = field_index(headers, config.get("operand_field", ""))

    try:
        fixed_operand = Decimal(str(config.get("operand_value", "1")).strip())
    except Exception:
        fixed_operand = Decimal("0")
    try:
        row_offset = Decimal(str(config.get("row_offset", "0")).strip())
    except Exception:
        row_offset = Decimal("0")
    try:
        sequence_start = Decimal(str(config.get("sequence_start", "1")).strip())
        sequence_step = Decimal(str(config.get("sequence_step", "1")).strip())
    except Exception:
        sequence_start = Decimal("1")
        sequence_step = Decimal("1")

    changed = fail_count = zero_count = 0
    seq_counter = 0

    for item_index, row_idx in enumerate(row_indexes):
        _check_cancelled(context, item_index)
        rows = ensure_row_count(rows, row_idx + 1, len(headers), max_expanded_rows=max_expanded_rows)
        original_text = safe_cell(rows[row_idx], target_idx)
        try:
            base_value = parse_numeric_value_for_column_op(original_text)
        except Exception:
            rows[row_idx][out_idx] = numeric_node_fallback_value(
                original_text, non_number_policy, non_number_fixed, "计算失败"
            )
            fail_count += 1
            continue

        try:
            if operand_source == "固定值":
                operand = fixed_operand
            elif operand_source == "行号":
                operand = Decimal(row_idx + 1)
            elif operand_source == "行号+N":
                operand = Decimal(row_idx + 1) + row_offset
            elif operand_source == "序号":
                operand = sequence_start + sequence_step * seq_counter
            elif operand_source == "另一列同行数值":
                operand = parse_numeric_value_for_column_op(safe_cell(rows[row_idx], operand_field_idx))
            else:
                operand = fixed_operand
        except Exception:
            rows[row_idx][out_idx] = numeric_node_fallback_value(
                original_text, non_number_policy, non_number_fixed, "计算失败"
            )
            fail_count += 1
            seq_counter += 1
            continue

        if operation == "加":
            result = base_value + operand
        elif operation == "减":
            result = base_value - operand
        elif operation == "乘":
            result = base_value * operand
        elif operation == "除":
            if operand == 0:
                rows[row_idx][out_idx] = numeric_node_fallback_value(
                    original_text, divide_zero_policy, divide_zero_fixed, "除零错误"
                )
                zero_count += 1
                seq_counter += 1
                continue
            result = base_value / operand
        else:
            raise ValueError(f"未知运算方式：{operation}")

        rows[row_idx][out_idx] = format_numeric_column_result(result, config)
        changed += 1
        seq_counter += 1

    msg = f"列数字运算完成：成功 {changed} 行"
    if fail_count:
        msg += f"，非数字/运算失败 {fail_count} 行"
    if zero_count:
        msg += f"，除零 {zero_count} 行"
    if not row_indexes:
        msg += "，处理范围为空"
    return headers, rows, msg


def resolve_start_row_index_by_mode(headers, rows, target_field, config):
    mode = config.get("start_row_mode", "手动指定起始行")
    if mode == "目标列最后数据行之后":
        try:
            last_idx = last_non_empty_row_index_by_field(headers, rows, target_field)
        except Exception:
            last_idx = -1
        return max(0, last_idx + 1)
    if mode == "参考列最后数据行之后":
        last_idx = last_non_empty_row_index_by_field(headers, rows, config.get("reference_field", ""))
        return max(0, last_idx + 1)
    if mode == "整体表格最后行之后":
        return max(0, len(rows))
    return parse_row_number(config.get("start_row", "1"), "起始行号") - 1


def get_source_column_values_by_config(headers, rows, config):
    src_idx = field_index(headers, config.get("source_field", ""))
    normalized = normalize_rows(rows, len(headers))
    mode = config.get("source_range_mode", "来源列数据边界")
    start_row = parse_row_number(config.get("source_start_row", "1"), "来源起始行") - 1
    if mode == "整体表格数据边界":
        end_row = len(normalized) - 1
    elif mode == "手动指定范围":
        end_row = parse_row_number(config.get("source_end_row", "1"), "来源结束行") - 1
    else:
        end_row = last_non_empty_row_index_by_field(headers, normalized, config.get("source_field", ""))
    if end_row < 0 or start_row > end_row:
        return []
    start_row = max(0, start_row)
    end_row = min(end_row, len(normalized) - 1)
    return [safe_cell(normalized[r], src_idx) for r in range(start_row, end_row + 1)]


def get_source_area_values_by_config(headers, rows, config):
    normalized = normalize_rows(rows, len(headers))
    if not normalized:
        return []

    start_col = field_index(headers, config.get("source_field", ""))
    end_field = config.get("source_end_field", config.get("source_field", ""))
    end_col = field_index(headers, end_field)
    c1, c2 = sorted([start_col, end_col])

    mode = config.get("source_range_mode", "来源列数据边界")
    start_row = parse_row_number(config.get("source_start_row", "1"), "来源起始行") - 1
    if mode == "整体表格数据边界":
        end_row = len(normalized) - 1
    elif mode == "手动指定范围":
        end_row = parse_row_number(config.get("source_end_row", "1"), "来源结束行") - 1
    else:
        end_row = last_non_empty_row_index_by_field(headers, normalized, config.get("source_field", ""))

    if end_row < 0 or start_row > end_row:
        return []
    start_row = max(0, start_row)
    end_row = min(end_row, len(normalized) - 1)
    return [
        [safe_cell(normalized[r], c) for c in range(c1, c2 + 1)]
        for r in range(start_row, end_row + 1)
    ]


def get_source_row_multi_field_values_by_config(headers, rows, config):
    normalized = normalize_rows(rows, len(headers))
    src_row = parse_row_number(config.get("source_row", "1"), "取值行号") - 1
    if src_row < 0 or src_row >= len(normalized):
        return []
    start_idx = field_index(headers, config.get("source_field", ""))
    end_field = config.get("source_end_field", config.get("source_field", ""))
    end_idx = field_index(headers, end_field)
    c1, c2 = sorted([start_idx, end_idx])
    return [safe_cell(normalized[src_row], c) for c in range(c1, c2 + 1)]


def get_cycle_source_values_by_config(headers, rows, config, multi_field=False):
    if multi_field:
        source_area = get_source_area_values_by_config(headers, rows, config)
        raw_values = []
        for source_row in source_area:
            raw_values.extend(source_row)
    else:
        raw_values = get_source_column_values_by_config(headers, rows, config)

    empty_mode = config.get("source_empty_mode", "跳过空值")
    placeholder = str(config.get("source_empty_placeholder", ""))
    values = []
    for value in raw_values:
        text = "" if value is None else str(value)
        if text == "":
            if empty_mode == "跳过空值":
                continue
            if empty_mode == "替换为空值占位符":
                text = placeholder
        values.append(text)
    return values


def resolve_sequence_count_by_source(headers, rows, config):
    mode = config.get("count_source_mode", "使用结束条件")
    if mode == "整体表格数据行数":
        return max(0, len(rows))
    if mode == "指定参考列数据数量":
        last_idx = last_non_empty_row_index_by_field(headers, rows, config.get("reference_field", ""))
        return max(0, last_idx + 1)
    if mode == "来源列数据数量":
        return len(get_source_column_values_by_config(headers, rows, config))
    return None


def resolve_area_end_row_index(headers, rows, config):
    mode = config.get("end_row_mode", "手动指定结束行")
    if mode == "整体表格数据边界":
        return max(0, len(rows) - 1)
    if mode == "指定参考列数据边界":
        return last_non_empty_row_index_by_field(headers, rows, config.get("reference_field", ""))
    return parse_row_number(config.get("end_row", "1"), "结束行号") - 1


def get_fill_targets(
    headers,
    rows,
    target_field,
    start_row_value,
    direction,
    end_mode,
    count_value,
    end_row_value,
    end_field_value,
    reference_field_value="",
    allow_expand_rows=True,
    allow_expand_cols=False,
    max_expanded_rows=MAX_EXPANDED_ROWS,
    max_target_cells=MAX_TARGET_CELLS,
):
    headers, rows, target_col = ensure_field_exists(headers, rows, target_field)
    start_row = parse_row_number(start_row_value, "起始行号") - 1
    rows = ensure_row_count(rows, start_row + 1, len(headers), max_expanded_rows=max_expanded_rows)
    direction = direction or "向下"
    end_mode = end_mode or "固定数量"
    count = get_positive_int(count_value, 1)
    targets = []

    def ensure_cols(col_index):
        nonlocal headers, rows
        while col_index >= len(headers):
            headers.append(get_unique_header(f"填充列{len(headers)+1}", headers))
            for row in rows:
                row.append("")

    if direction in ["向下", "向上"]:
        if end_mode == "固定数量":
            end_row = start_row + count - 1 if direction == "向下" else start_row - count + 1
        elif end_mode == "填充到指定行":
            end_row = parse_row_number(end_row_value, "结束行号") - 1
        elif end_mode == "填充到参考列数据边界":
            ref_last = last_non_empty_row_index_by_field(headers, rows, reference_field_value)
            end_row = ref_last if direction == "向下" else 0
        elif end_mode in ["填充到数据边界", "填充到指定列"]:
            end_row = len(rows) - 1 if direction == "向下" else 0
        elif end_mode in ["遇到已有数据停止", "填充到空行前"]:
            end_row = len(rows) - 1 if direction == "向下" else 0
        else:
            end_row = len(rows) - 1 if direction == "向下" else 0
        target_count = abs(end_row - start_row) + 1
        ensure_target_cell_limit(1, target_count, max_target_cells=max_target_cells)
        if allow_expand_rows and direction == "向下" and end_row >= len(rows):
            rows = ensure_row_count(rows, end_row + 1, len(headers), max_expanded_rows=max_expanded_rows)
        step = 1 if direction == "向下" else -1
        r = start_row
        while 0 <= r < len(rows) and ((step > 0 and r <= end_row) or (step < 0 and r >= end_row)):
            if end_mode == "填充到空行前" and row_is_empty(rows[r], len(headers)):
                break
            targets.append((r, target_col))
            r += step
    else:
        if end_mode == "固定数量":
            end_col = target_col + count - 1 if direction == "向右" else target_col - count + 1
        elif end_mode == "填充到指定列":
            if end_field_value not in headers:
                if allow_expand_cols and direction == "向右":
                    headers, rows, end_col = ensure_field_exists(headers, rows, end_field_value)
                else:
                    raise ValueError(f"结束字段不存在：{end_field_value}")
            else:
                end_col = headers.index(end_field_value)
        else:
            end_col = len(headers) - 1 if direction == "向右" else 0
        target_count = abs(end_col - target_col) + 1
        ensure_target_cell_limit(1, target_count, max_target_cells=max_target_cells)
        if allow_expand_cols and direction == "向右" and end_col >= len(headers):
            ensure_cols(end_col)
        step = 1 if direction == "向右" else -1
        c = target_col
        while 0 <= c < len(headers) and ((step > 0 and c <= end_col) or (step < 0 and c >= end_col)):
            targets.append((start_row, c))
            c += step
    return headers, rows, targets


def should_write_cell(current_value, overwrite_rule):
    current = "" if current_value is None else str(current_value)
    if overwrite_rule == "覆盖所有目标单元格":
        return True, False
    if overwrite_rule == "只填充空单元格":
        return current == "", False
    if overwrite_rule == "遇到已有数据停止":
        return current == "", current != ""
    if overwrite_rule == "不覆盖已有数据，只跳过":
        return current == "", False
    return True, False


def format_sequence_value(value, config):
    zero_pad = get_positive_int(config.get("zero_pad", "0"), 0) if str(config.get("zero_pad", "0")).strip() != "0" else 0
    if abs(value - int(value)) < 1e-12:
        text = str(int(value))
        if zero_pad > 0:
            text = text.zfill(zero_pad)
    else:
        text = str(value).rstrip("0").rstrip(".") if "." in str(value) else str(value)
    return f"{config.get('prefix', '')}{text}{config.get('suffix', '')}"


def _check_cancelled(context, index):
    callback = (context or {}).get("check_cancelled")
    if callable(callback):
        callback(index)


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


def replace_row_index_for_policy(policy, current_index, pair_index, fixed_index):
    policy = str(policy or "当前行").strip()
    if policy == "第一行":
        return 0
    if policy == "固定行号":
        return fixed_index - 1
    if policy in ("按匹配行号", "按命中序号"):
        return pair_index
    return current_index


def replace_source_value(rows, source, field_idx, fixed_value, policy, current_index, pair_index, fixed_index):
    if source != "列字段":
        return fixed_value, True
    row_index = replace_row_index_for_policy(policy, current_index, pair_index, fixed_index)
    if row_index < 0 or row_index >= len(rows):
        return "", False
    return safe_cell(rows[row_index], field_idx), True


def replace_pair_count_for_row(new_rows, match_source, match_row_policy, replace_source, replace_row_policy):
    counts = []
    if match_source == "列字段" and match_row_policy in ("按匹配行号", "按命中序号"):
        counts.append(len(new_rows))
    if replace_source == "列字段" and replace_row_policy in ("按匹配行号", "按命中序号"):
        counts.append(len(new_rows))
    return max(counts) if counts else 1


def apply_replace_node(headers, rows, config, context=None):
    idx = field_index(headers, config.get("target_field", ""))
    match_mode = config.get("match_mode", "包含")
    replace_mode = config.get("replace_mode", "局部替换匹配字符串")
    case_sensitive = bool(config.get("case_sensitive", True))
    skip_empty_match_value = bool(config.get("skip_empty_match_value", True))
    legacy_value_source = config.get("value_source", "手动输入")
    match_source = config.get("match_value_source") or legacy_value_source or "手动输入"
    replace_source = config.get("replace_value_source") or legacy_value_source or "手动输入"
    match_source = "列字段" if match_source in ("列字段", "字段", "当前表字段") else "手动输入"
    replace_source = "列字段" if replace_source in ("列字段", "字段", "当前表字段") else "手动输入"
    match_row_policy = config.get("match_row_policy") or ("当前行" if legacy_value_source == "列字段" else "当前行")
    replace_row_policy = config.get("replace_row_policy") or ("当前行" if legacy_value_source == "列字段" else "当前行")
    match_row_index = max(1, safe_int(config.get("match_row_index", 1), 1))
    replace_row_index = max(1, safe_int(config.get("replace_row_index", 1), 1))
    replace_count = max(0, safe_int(config.get("replace_count", 0), 0))

    match_field_idx = field_index(headers, config.get("match_value_field", "")) if match_source == "列字段" else None
    replace_field_idx = field_index(headers, config.get("replace_value_field", "")) if replace_source == "列字段" else None
    static_match_value = str(config.get("match_value", ""))
    static_replace_value = str(config.get("replace_value", ""))
    if match_mode == "正则匹配" and match_source != "列字段":
        flags = 0 if case_sensitive else re.IGNORECASE
        try:
            re.compile(static_match_value, flags=flags)
        except re.error as exc:
            raise ValueError(f"批量替换正则错误：{exc}") from exc

    new_rows = normalize_rows(rows, len(headers))
    changed = 0
    skipped_empty = 0
    skipped_invalid_row = 0

    def replace_text(old, match_value, replace_value):
        if replace_mode == "整格替换为新值":
            return replace_value
        if match_mode == "正则匹配":
            flags = 0 if case_sensitive else re.IGNORECASE
            return re.sub(match_value, replace_value, old, count=replace_count, flags=flags)
        if match_value == "":
            return old
        if case_sensitive:
            return old.replace(match_value, replace_value, replace_count if replace_count else -1)
        return re.sub(re.escape(match_value), replace_value, old, count=replace_count, flags=re.IGNORECASE)

    for row_index, row in enumerate(new_rows):
        _check_cancelled(context, row_index)
        old = safe_cell(row, idx)
        new_value = old
        row_changed = False
        for pair_index in range(
            replace_pair_count_for_row(new_rows, match_source, match_row_policy, replace_source, replace_row_policy)
        ):
            match_value, match_row_ok = replace_source_value(
                new_rows, match_source, match_field_idx, static_match_value, match_row_policy, row_index, pair_index, match_row_index
            )
            replace_value, replace_row_ok = replace_source_value(
                new_rows, replace_source, replace_field_idx, static_replace_value, replace_row_policy, row_index, pair_index, replace_row_index
            )
            if not match_row_ok or not replace_row_ok:
                skipped_invalid_row += 1
                continue
            if skip_empty_match_value and match_value == "" and match_mode not in ("为空", "不为空"):
                skipped_empty += 1
                continue
            try:
                matched = compare_values(new_value, match_mode, match_value, case_sensitive)
            except re.error as exc:
                raise ValueError(
                    f"批量替换正则错误（第 {row_index + 1} 行，匹配值 {match_value!r}）：{exc}"
                ) from exc
            if not matched:
                continue
            try:
                updated = replace_text(new_value, match_value, replace_value)
            except re.error as exc:
                raise ValueError(
                    f"批量替换正则错误（第 {row_index + 1} 行，匹配值 {match_value!r}）：{exc}"
                ) from exc
            if updated != new_value:
                new_value = updated
                row_changed = True
        if new_value != old:
            row[idx] = new_value
        if row_changed:
            changed += 1

    extras = []
    if (match_source == "列字段" or replace_source == "列字段") and skipped_empty:
        extras.append(f"跳过空匹配值 {skipped_empty} 次")
    if skipped_invalid_row:
        extras.append(f"跳过无效取行 {skipped_invalid_row} 次")
    extra = "，" + "，".join(extras) if extras else ""
    return list(headers), new_rows, f"修改 {changed} 处{extra}"


def apply_merge_node(headers, rows, config, context=None):
    fields = list(config.get("fields", []))
    if not fields:
        raise ValueError("合并字段不能为空。")
    indexes = [field_index(headers, field) for field in fields]
    seps = [parse_separator_text(sep) for sep in list(config.get("separators", []))]
    if len(seps) < max(len(fields) - 1, 0):
        seps += [""] * (len(fields) - 1 - len(seps))

    output_field = get_unique_header(config.get("output_field", "合并结果"), headers)
    new_headers = list(headers) + [output_field]
    new_rows = normalize_rows(rows, len(headers))
    skip_empty = bool(config.get("skip_empty", True))
    trim_value = bool(config.get("trim_value", True))
    placeholder = str(config.get("empty_placeholder", ""))

    for row_index, row in enumerate(new_rows):
        _check_cancelled(context, row_index)
        pieces = []
        active_indexes = []
        for index, field_idx in enumerate(indexes):
            value = safe_cell(row, field_idx)
            if trim_value:
                value = value.strip()
            if value == "" and placeholder:
                value = placeholder
            if skip_empty and value == "":
                continue
            active_indexes.append(index)
            pieces.append(value)

        if not pieces:
            merged = ""
        elif skip_empty:
            merged = pieces[0]
            for piece_index in range(1, len(pieces)):
                original_gap_index = active_indexes[piece_index - 1]
                sep = seps[original_gap_index] if original_gap_index < len(seps) else ""
                merged += sep + pieces[piece_index]
        else:
            merged = pieces[0]
            for piece_index in range(1, len(pieces)):
                sep = seps[piece_index - 1] if piece_index - 1 < len(seps) else ""
                merged += sep + pieces[piece_index]
        row.append(merged)

    return new_headers, new_rows, f"新增字段 {output_field}"


def apply_rename_columns_node(headers, rows, config):
    headers = list(headers)
    new_headers = list(headers)
    mode = config.get("mode", "手动映射改名")
    trim_names = bool(config.get("trim_names", True))
    duplicate_policy = config.get("duplicate_policy", "自动追加编号")
    missing_policy = config.get("missing_policy", "跳过并记录警告")
    warnings = []
    changed = 0

    def clean_name(name):
        value = "" if name is None else str(name)
        return value.strip() if trim_names else value

    def field_scope_indexes():
        if config.get("scope", "全部字段") == "选中字段":
            selected = set(config.get("scope_fields", []))
            return [index for index, header in enumerate(headers) if header in selected]
        return list(range(len(headers)))

    if mode == "手动映射改名":
        old_to_new = {}
        for item in config.get("mappings", []):
            old = str(item.get("old", "")).strip()
            new = clean_name(item.get("new", ""))
            if old:
                old_to_new[old] = new
        for old, new in old_to_new.items():
            if old not in headers:
                message = f"字段不存在：{old}"
                if missing_policy == "报错并停止":
                    raise ValueError(message)
                warnings.append(message)
                continue
            idx = headers.index(old)
            if new:
                if new_headers[idx] != new:
                    changed += 1
                new_headers[idx] = new
    elif mode == "批量添加前缀":
        prefix = str(config.get("prefix", ""))
        for idx in field_scope_indexes():
            new_name = clean_name(prefix + str(headers[idx]))
            if new_headers[idx] != new_name:
                changed += 1
            new_headers[idx] = new_name
    elif mode == "批量添加后缀":
        suffix = str(config.get("suffix", ""))
        for idx in field_scope_indexes():
            new_name = clean_name(str(headers[idx]) + suffix)
            if new_headers[idx] != new_name:
                changed += 1
            new_headers[idx] = new_name
    elif mode == "批量替换字段名字符":
        match = str(config.get("replace_match", ""))
        repl = str(config.get("replace_value", ""))
        if not match:
            return list(headers), [list(row) for row in rows], "字段名替换匹配值为空，未修改"
        for idx in field_scope_indexes():
            new_name = clean_name(str(headers[idx]).replace(match, repl))
            if new_headers[idx] != new_name:
                changed += 1
            new_headers[idx] = new_name
    else:
        raise ValueError(f"未知改名模式：{mode}")

    for index, name in enumerate(new_headers):
        if str(name).strip() == "":
            new_headers[index] = f"列{index + 1}"
            warnings.append(f"第{index + 1}列字段名为空，已自动改为 列{index + 1}")

    if duplicate_policy == "自动追加编号":
        new_headers = make_unique_headers(new_headers)
    else:
        seen = set()
        duplicates = []
        for header in new_headers:
            if header in seen:
                duplicates.append(header)
            seen.add(header)
        if duplicates:
            raise ValueError("字段名重复：" + ", ".join(dict.fromkeys(duplicates)))

    message = f"已更改 {changed} 个字段名"
    if warnings:
        message += f"，警告 {len(warnings)} 项"
    return new_headers, [list(row) for row in rows], message


def apply_fill_value_node(headers, rows, config, context=None):
    headers = list(headers)
    rows = normalize_rows(rows, len(headers))
    value_source = config.get("value_source", "手动输入值")
    target_field = config.get("target_field", "")
    max_expanded_rows = (context or {}).get("max_expanded_rows", MAX_EXPANDED_ROWS)
    max_target_cells = (context or {}).get("max_target_cells", MAX_TARGET_CELLS)

    if value_source == "循环源列填充":
        effective_start_row = resolve_start_row_index_by_mode(headers, rows, target_field, config) + 1
        headers, rows, targets = get_fill_targets(
            headers,
            rows,
            target_field,
            str(effective_start_row),
            config.get("direction", "向下"),
            config.get("end_mode", "填充到数据边界"),
            config.get("count", "1"),
            config.get("end_row", "1"),
            config.get("end_field", ""),
            config.get("reference_field", ""),
            allow_expand_rows=True,
            allow_expand_cols=True,
            max_expanded_rows=max_expanded_rows,
            max_target_cells=max_target_cells,
        )
        cycle_values = get_cycle_source_values_by_config(headers, rows, config)
        if not cycle_values:
            return headers, rows, "循环源列无可用数据，未执行填充"
        overwrite_rule = config.get("overwrite_rule", "只填充空单元格")
        changed = skipped = write_index = 0
        for target_index, (r, c) in enumerate(targets):
            _check_cancelled(context, target_index)
            rows = ensure_row_count(rows, r + 1, len(headers), max_expanded_rows=max_expanded_rows)
            can_write, stop = should_write_cell(safe_cell(rows[r], c), overwrite_rule)
            if stop:
                break
            if can_write:
                rows[r][c] = cycle_values[write_index % len(cycle_values)]
                changed += 1
                write_index += 1
            else:
                skipped += 1
        return headers, rows, f"循环源列填充 {changed} 个单元格，跳过 {skipped} 个，循环周期 {len(cycle_values)}"

    if value_source == "来源列完整结构":
        headers, rows, target_col = ensure_field_exists(headers, rows, target_field)
        start_row = resolve_start_row_index_by_mode(headers, rows, target_field, config)
        values = get_source_column_values_by_config(headers, rows, config)
        if not values:
            return headers, rows, "来源列无可填充数据，未执行填充"
        rows = ensure_row_count(rows, start_row + len(values), len(headers), max_expanded_rows=max_expanded_rows)
        overwrite_rule = config.get("overwrite_rule", "只填充空单元格")
        changed = skipped = 0
        for offset, value in enumerate(values):
            _check_cancelled(context, offset)
            r = start_row + offset
            can_write, stop = should_write_cell(safe_cell(rows[r], target_col), overwrite_rule)
            if stop:
                break
            if can_write:
                rows[r][target_col] = value
                changed += 1
            else:
                skipped += 1
        return headers, rows, f"来源列完整结构填充 {changed} 个单元格，跳过 {skipped} 个"

    effective_start_row = resolve_start_row_index_by_mode(headers, rows, target_field, config) + 1
    headers, rows, targets = get_fill_targets(
        headers,
        rows,
        target_field,
        str(effective_start_row),
        config.get("direction", "向下"),
        config.get("end_mode", "填充到数据边界"),
        config.get("count", "1"),
        config.get("end_row", "1"),
        config.get("end_field", ""),
        config.get("reference_field", ""),
        allow_expand_rows=True,
        allow_expand_cols=True,
        max_expanded_rows=max_expanded_rows,
        max_target_cells=max_target_cells,
    )
    changed = skipped = 0
    overwrite_rule = config.get("overwrite_rule", "只填充空单元格")
    for target_index, (r, c) in enumerate(targets):
        _check_cancelled(context, target_index)
        rows = ensure_row_count(rows, r + 1, len(headers), max_expanded_rows=max_expanded_rows)
        can_write, stop = should_write_cell(safe_cell(rows[r], c), overwrite_rule)
        if stop:
            break
        if can_write:
            rows[r][c] = get_config_cell_value(headers, rows, config, target_row_idx=r)
            changed += 1
        else:
            skipped += 1
    return headers, rows, f"填充 {changed} 个单元格，跳过 {skipped} 个"


def apply_sequence_fill_node(headers, rows, config, context=None):
    headers = list(headers)
    rows = normalize_rows(rows, len(headers))
    max_expanded_rows = (context or {}).get("max_expanded_rows", MAX_EXPANDED_ROWS)
    max_target_cells = (context or {}).get("max_target_cells", MAX_TARGET_CELLS)
    try:
        start_value = float(str(config.get("start_value", "1")).strip())
        step = float(str(config.get("step", "1")).strip())
    except Exception:
        raise ValueError("起始值和步长必须是数字。")

    target_field = config.get("target_field", "")
    effective_start_row = resolve_start_row_index_by_mode(headers, rows, target_field, config) + 1
    count_override = resolve_sequence_count_by_source(headers, rows, config)
    end_mode = config.get("end_mode", "填充到数据边界")
    count_value = config.get("count", "1")
    if count_override is not None:
        end_mode = "固定数量"
        count_value = str(count_override)

    headers, rows, targets = get_fill_targets(
        headers,
        rows,
        target_field,
        str(effective_start_row),
        config.get("direction", "向下"),
        end_mode,
        count_value,
        config.get("end_row", "1"),
        config.get("end_field", ""),
        config.get("reference_field", ""),
        allow_expand_rows=True,
        allow_expand_cols=True,
        max_expanded_rows=max_expanded_rows,
        max_target_cells=max_target_cells,
    )
    changed = skipped = seq_index = 0
    overwrite_rule = config.get("overwrite_rule", "覆盖所有目标单元格")
    for target_index, (r, c) in enumerate(targets):
        _check_cancelled(context, target_index)
        rows = ensure_row_count(rows, r + 1, len(headers), max_expanded_rows=max_expanded_rows)
        can_write, stop = should_write_cell(safe_cell(rows[r], c), overwrite_rule)
        if stop:
            break
        if can_write:
            rows[r][c] = format_sequence_value(start_value + step * seq_index, config)
            changed += 1
            seq_index += 1
        else:
            skipped += 1
    return headers, rows, f"序列填充 {changed} 个单元格，跳过 {skipped} 个"


def apply_area_fill_node(headers, rows, config, context=None):
    headers = list(headers)
    rows = normalize_rows(rows, len(headers))
    max_expanded_rows = (context or {}).get("max_expanded_rows", MAX_EXPANDED_ROWS)
    max_target_cells = (context or {}).get("max_target_cells", MAX_TARGET_CELLS)
    if config.get("start_field", "") not in headers:
        headers, rows, start_col = ensure_field_exists(headers, rows, config.get("start_field", ""))
    else:
        start_col = headers.index(config.get("start_field", ""))
    if config.get("end_field", "") not in headers:
        headers, rows, end_col = ensure_field_exists(headers, rows, config.get("end_field", ""))
    else:
        end_col = headers.index(config.get("end_field", ""))

    start_row = resolve_start_row_index_by_mode(headers, rows, config.get("start_field", ""), config)
    value_source = config.get("value_source", "手动输入值")
    c1, c2 = sorted([start_col, end_col])
    overwrite_rule = config.get("overwrite_rule", "只填充空单元格")
    changed = skipped = 0

    if value_source == "循环源列填充":
        cycle_values = get_cycle_source_values_by_config(headers, rows, config, multi_field=True)
        if not cycle_values:
            return headers, rows, "循环源列无可用数据，未执行区域填充"
        end_row = resolve_area_end_row_index(headers, rows, config)
        if end_row < 0:
            return headers, rows, "参考列无数据，未执行区域填充"
        r1, r2 = sorted([start_row, end_row])
        ensure_target_cell_limit(r2 - r1 + 1, c2 - c1 + 1, max_target_cells=max_target_cells)
        rows = ensure_row_count(rows, r2 + 1, len(headers), max_expanded_rows=max_expanded_rows)
        stop_all = False
        write_index = 0
        for r in range(r1, r2 + 1):
            _check_cancelled(context, r - r1)
            if stop_all:
                break
            for c in range(c1, c2 + 1):
                can_write, stop = should_write_cell(safe_cell(rows[r], c), overwrite_rule)
                if stop:
                    stop_all = True
                    break
                if can_write:
                    rows[r][c] = cycle_values[write_index % len(cycle_values)]
                    changed += 1
                    write_index += 1
                else:
                    skipped += 1
        return headers, rows, f"循环源列区域填充 {changed} 个单元格，跳过 {skipped} 个，循环周期 {len(cycle_values)}（多源字段）"

    if value_source == "来源区域完整复制":
        source_area = get_source_area_values_by_config(headers, rows, config)
        if not source_area:
            return headers, rows, "来源区域为空或越界，未执行区域完整复制"
        source_height = len(source_area)
        source_width = max((len(row) for row in source_area), default=0)
        if source_height <= 0 or source_width <= 0:
            return headers, rows, "来源区域为空，未执行区域完整复制"
        ensure_target_cell_limit(source_height, source_width, max_target_cells=max_target_cells)

        headers, rows = ensure_column_count(headers, rows, start_col + source_width, "区域复制列")
        rows = ensure_row_count(rows, start_row + source_height, len(headers), max_expanded_rows=max_expanded_rows)
        stop_all = False
        for r_offset, source_row in enumerate(source_area):
            _check_cancelled(context, r_offset)
            if stop_all:
                break
            target_r = start_row + r_offset
            for c_offset, value in enumerate(source_row):
                target_c = start_col + c_offset
                can_write, stop = should_write_cell(safe_cell(rows[target_r], target_c), overwrite_rule)
                if stop:
                    stop_all = True
                    break
                if can_write:
                    rows[target_r][target_c] = value
                    changed += 1
                else:
                    skipped += 1
        return headers, rows, f"来源区域完整复制 {changed} 个单元格，跳过 {skipped} 个"

    if value_source == "来源列完整结构":
        values = get_source_column_values_by_config(headers, rows, config)
        if not values:
            return headers, rows, "来源列无可填充数据，未执行区域填充"
        ensure_target_cell_limit(len(values), c2 - c1 + 1, max_target_cells=max_target_cells)
        rows = ensure_row_count(rows, start_row + len(values), len(headers), max_expanded_rows=max_expanded_rows)
        stop_all = False
        for offset, value in enumerate(values):
            _check_cancelled(context, offset)
            if stop_all:
                break
            r = start_row + offset
            for c in range(c1, c2 + 1):
                can_write, stop = should_write_cell(safe_cell(rows[r], c), overwrite_rule)
                if stop:
                    stop_all = True
                    break
                if can_write:
                    rows[r][c] = value
                    changed += 1
                else:
                    skipped += 1
        return headers, rows, f"来源列完整结构区域填充 {changed} 个单元格，跳过 {skipped} 个"

    if value_source == "指定行多字段取值":
        values = get_source_row_multi_field_values_by_config(headers, rows, config)
        if not values:
            return headers, rows, "指定行多字段取值为空或越界，未执行区域填充"
        direction = config.get("multi_field_fill_direction", "横向填充")
        if direction == "纵向填充":
            ensure_target_cell_limit(len(values), c2 - c1 + 1, max_target_cells=max_target_cells)
            rows = ensure_row_count(rows, start_row + len(values), len(headers), max_expanded_rows=max_expanded_rows)
            stop_all = False
            for offset, value in enumerate(values):
                _check_cancelled(context, offset)
                if stop_all:
                    break
                r = start_row + offset
                for c in range(c1, c2 + 1):
                    can_write, stop = should_write_cell(safe_cell(rows[r], c), overwrite_rule)
                    if stop:
                        stop_all = True
                        break
                    if can_write:
                        rows[r][c] = value
                        changed += 1
                    else:
                        skipped += 1
        else:
            end_row = resolve_area_end_row_index(headers, rows, config)
            if end_row < 0:
                return headers, rows, "参考列无数据，未执行区域填充"
            r1, r2 = sorted([start_row, end_row])
            ensure_target_cell_limit(r2 - r1 + 1, min(c2 - c1 + 1, len(values)), max_target_cells=max_target_cells)
            rows = ensure_row_count(rows, r2 + 1, len(headers), max_expanded_rows=max_expanded_rows)
            target_cols = list(range(c1, c2 + 1))
            stop_all = False
            for r in range(r1, r2 + 1):
                _check_cancelled(context, r - r1)
                if stop_all:
                    break
                for offset, c in enumerate(target_cols):
                    if offset >= len(values):
                        break
                    value = values[offset]
                    can_write, stop = should_write_cell(safe_cell(rows[r], c), overwrite_rule)
                    if stop:
                        stop_all = True
                        break
                    if can_write:
                        rows[r][c] = value
                        changed += 1
                    else:
                        skipped += 1
        return headers, rows, f"指定行多字段取值区域填充 {changed} 个单元格，跳过 {skipped} 个"

    end_row = resolve_area_end_row_index(headers, rows, config)
    if end_row < 0:
        return headers, rows, "参考列无数据，未执行区域填充"
    r1, r2 = sorted([start_row, end_row])
    ensure_target_cell_limit(r2 - r1 + 1, c2 - c1 + 1, max_target_cells=max_target_cells)
    rows = ensure_row_count(rows, r2 + 1, len(headers), max_expanded_rows=max_expanded_rows)
    stop_all = False
    for r in range(r1, r2 + 1):
        _check_cancelled(context, r - r1)
        if stop_all:
            break
        for c in range(c1, c2 + 1):
            can_write, stop = should_write_cell(safe_cell(rows[r], c), overwrite_rule)
            if stop:
                stop_all = True
                break
            if can_write:
                rows[r][c] = get_config_cell_value(headers, rows, config, target_row_idx=r)
                changed += 1
            else:
                skipped += 1
    return headers, rows, f"区域填充 {changed} 个单元格，跳过 {skipped} 个"


def render_current_datetime_template(dt, config):
    mode = config.get("format_mode", "占位符模板")
    if mode == "Python strftime":
        fmt = str(config.get("strftime_template", "%Y-%m-%d %H:%M:%S") or "%Y-%m-%d %H:%M:%S")
        try:
            return dt.strftime(fmt)
        except Exception as exc:
            raise ValueError(f"strftime格式错误：{exc}") from exc

    values = {
        "YYYY": f"{dt.year:04d}",
        "YY": f"{dt.year % 100:02d}",
        "MM": f"{dt.month:02d}",
        "M": str(dt.month),
        "DD": f"{dt.day:02d}",
        "D": str(dt.day),
        "HH": f"{dt.hour:02d}",
        "H": str(dt.hour),
        "mm": f"{dt.minute:02d}",
        "m": str(dt.minute),
        "ss": f"{dt.second:02d}",
        "s": str(dt.second),
        "fff": f"{dt.microsecond // 1000:03d}",
        "ffffff": f"{dt.microsecond:06d}",
        "timestamp": str(int(dt.timestamp())),
        "unix_ms": str(int(dt.timestamp() * 1000)),
    }
    text = str(config.get("template", "{YYYY}-{MM}-{DD} {HH}:{mm}:{ss}") or "")
    for key in sorted(values.keys(), key=len, reverse=True):
        text = text.replace("{" + key + "}", values[key])
    return text


def parse_new_columns_specs(config):
    text = str(config.get("columns_text", "") or "")
    strip_name = bool(config.get("strip_column_name", True))
    allow_empty = bool(config.get("allow_empty_name", False))
    value_mode = config.get("value_mode", "统一默认值")
    default_value = str(config.get("default_value", "") or "")
    specs = []
    auto_index = 1
    for raw_line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw_line.strip() if strip_name else raw_line
        if line == "":
            continue
        if "=" in line:
            name, value = line.split("=", 1)
            name = name.strip() if strip_name else name
            if value_mode == "按列配置值":
                fill_value = value
            elif value_mode == "空值":
                fill_value = ""
            else:
                fill_value = default_value
        else:
            name = line
            fill_value = "" if value_mode == "空值" else default_value
        if name == "":
            if allow_empty:
                name = f"新字段{auto_index}"
                auto_index += 1
            else:
                raise ValueError("新建列节点存在空字段名。可删除空行，或勾选允许空字段名自动命名。")
        specs.append((name, "" if fill_value is None else str(fill_value)))
    if not specs:
        raise ValueError("新建列节点没有填写任何字段名。")
    return specs


def apply_new_columns_node(headers, rows, config):
    headers = list(headers)
    new_rows = normalize_rows(rows, len(headers))
    specs = parse_new_columns_specs(config)
    conflict_mode = config.get("conflict_mode", "自动改名")
    added = 0
    overwritten = 0
    skipped = 0
    output_names = []

    for name, fill_value in specs:
        if name in headers:
            if conflict_mode == "自动改名":
                final_name = get_unique_header(name, headers)
                headers.append(final_name)
                for row in new_rows:
                    row.append(fill_value)
                added += 1
                output_names.append(final_name)
            elif conflict_mode == "跳过已有字段":
                skipped += 1
                continue
            elif conflict_mode == "覆盖已有字段":
                idx = headers.index(name)
                for row in new_rows:
                    row[idx] = fill_value
                overwritten += 1
                output_names.append(name)
            elif conflict_mode == "存在则报错":
                raise ValueError(f"新建列节点字段已存在：{name}")
            else:
                raise ValueError(f"未知同名字段处理方式：{conflict_mode}")
        else:
            headers.append(name)
            for row in new_rows:
                row.append(fill_value)
            added += 1
            output_names.append(name)

    shown = ", ".join(output_names[:8])
    if len(output_names) > 8:
        shown += f" ... 共{len(output_names)}个"
    return headers, new_rows, f"新建列完成：新增 {added} 列，覆盖 {overwritten} 列，跳过 {skipped} 列；字段：{shown}"


def apply_current_datetime_column_node(headers, rows, config, now_func=None):
    headers = list(headers)
    new_rows = normalize_rows(rows, len(headers))
    output_mode = config.get("output_mode", "生成新字段")
    now_func = now_func or datetime.now

    if output_mode == "覆盖已有字段":
        target = str(config.get("target_field", "")).strip()
        if not target:
            raise ValueError("新建日期时间列节点选择了覆盖已有字段，但未选择覆盖字段。")
        output_idx = field_index(headers, target)
        output_name = headers[output_idx]
    else:
        output_name = get_unique_header(config.get("new_field", "当前日期时间"), headers)
        headers.append(output_name)
        output_idx = len(headers) - 1
        for row in new_rows:
            row.append("")

    fixed_time = now_func()
    same_time = config.get("time_mode", "整次运行固定同一时间") == "整次运行固定同一时间"
    changed = 0
    sample = ""
    for row in new_rows:
        dt = fixed_time if same_time else now_func()
        value = render_current_datetime_template(dt, config)
        row[output_idx] = value
        if sample == "":
            sample = value
        changed += 1

    if not new_rows:
        sample = render_current_datetime_template(fixed_time, config)
    return headers, new_rows, f"新建日期时间列完成：字段【{output_name}】，写入 {changed} 行，示例：{sample}"


def normalize_datetime_source_text(value):
    return normalize_datetime_text(value)


def parse_format_int(value, name, allow_zero=False):
    try:
        n = int(str(value).strip())
    except Exception:
        raise ValueError(f"{name} 必须是整数。")
    if allow_zero:
        if n < 0:
            raise ValueError(f"{name} 不能小于 0。")
    else:
        if n <= 0:
            raise ValueError(f"{name} 必须大于 0。")
    return n


def slice_by_position(text, start, length, base, name):
    length = parse_format_int(length, f"{name}长度", allow_zero=True)
    if length == 0:
        return ""
    start = parse_format_int(start, f"{name}起始")
    idx = start - 1 if base == "从1开始" else start
    if idx < 0 or idx + length > len(text):
        raise ValueError(f"{name}位置越界")
    return text[idx:idx + length]


def complete_format_year(value, config):
    return complete_year(value, config)


def build_date_parts(year, month, day, config):
    parsed_year = complete_format_year(year, config)
    try:
        parsed_month = int(str(month).strip())
        parsed_day = int(str(day).strip())
    except Exception:
        raise ValueError("月/日不是数字")
    try:
        datetime(parsed_year, parsed_month, parsed_day)
    except Exception:
        raise ValueError(f"日期无效：{parsed_year:04d}-{parsed_month:02d}-{parsed_day:02d}")
    return {"year": parsed_year, "month": parsed_month, "day": parsed_day}


def build_time_parts(hour, minute="0", second="0"):
    try:
        parsed_hour = int(str(hour).strip())
        parsed_minute = int(str(minute).strip()) if str(minute).strip() != "" else 0
        parsed_second = int(str(second).strip()) if str(second).strip() != "" else 0
    except Exception:
        raise ValueError("时/分/秒不是数字")
    if not (0 <= parsed_hour <= 23):
        raise ValueError("小时超出范围 0-23")
    if not (0 <= parsed_minute <= 59):
        raise ValueError("分钟超出范围 0-59")
    if not (0 <= parsed_second <= 59):
        raise ValueError("秒超出范围 0-59")
    return {"hour": parsed_hour, "minute": parsed_minute, "second": parsed_second}


def parse_date_fixed(text, config):
    base = config.get("position_base", "从1开始")
    year = slice_by_position(text, config.get("year_start", "1"), config.get("year_len", "2"), base, "年")
    month = slice_by_position(text, config.get("month_start", "3"), config.get("month_len", "2"), base, "月")
    day = slice_by_position(text, config.get("day_start", "5"), config.get("day_len", "2"), base, "日")
    return build_date_parts(year, month, day, config)


def parse_time_fixed(text, config):
    base = config.get("position_base", "从1开始")
    hour = slice_by_position(text, config.get("hour_start", "1"), config.get("hour_len", "2"), base, "时")
    minute = slice_by_position(text, config.get("minute_start", "3"), config.get("minute_len", "2"), base, "分")
    second = slice_by_position(text, config.get("second_start", "5"), config.get("second_len", "0"), base, "秒")
    return build_time_parts(hour, minute, second or "0")


def split_by_config_delimiter(text, kind, config):
    if kind == "date":
        mode = config.get("date_delimiter", "自动识别")
        custom = config.get("custom_date_delimiter", "-")
        if mode == "年/月/日":
            return re.findall(r"\d+", text)
        if mode == "自定义":
            if custom == "":
                raise ValueError("自定义日期分隔符不能为空")
            return text.split(custom)
        if mode == "自动识别":
            return re.findall(r"\d+", text)
        return text.split(mode)

    mode = config.get("time_delimiter", "自动识别")
    custom = config.get("custom_time_delimiter", ":")
    if mode == "时/分/秒":
        return re.findall(r"\d+", text)
    if mode == "自定义":
        if custom == "":
            raise ValueError("自定义时间分隔符不能为空")
        return text.split(custom)
    if mode == "自动识别":
        return re.findall(r"\d+", text)
    return text.split(mode)


def parse_date_delimited(text, config):
    parts = [part.strip() for part in split_by_config_delimiter(text, "date", config) if str(part).strip() != ""]
    if len(parts) < 3:
        raise ValueError("日期分隔后不足 3 段")
    order = config.get("date_order", "年-月-日")
    if order == "月-日-年":
        month, day, year = parts[0], parts[1], parts[2]
    elif order == "日-月-年":
        day, month, year = parts[0], parts[1], parts[2]
    else:
        year, month, day = parts[0], parts[1], parts[2]
    return build_date_parts(year, month, day, config)


def parse_time_delimited(text, config):
    parts = [part.strip() for part in split_by_config_delimiter(text, "time", config) if str(part).strip() != ""]
    if len(parts) < 2:
        raise ValueError("时间分隔后不足 2 段")
    hour = parts[0]
    minute = parts[1]
    second = parts[2] if len(parts) >= 3 else "0"
    return build_time_parts(hour, minute, second)


def parse_date_auto_common(text, config):
    return shared_parse_date_auto_common(text, config)


def parse_time_auto_common(text, config):
    normalized = normalize_datetime_source_text(text)
    match = re.search(r"(?<!\d)(\d{1,2})\s*[:时]\s*(\d{1,2})(?:\s*[:分]\s*(\d{1,2}))?(?:\s*秒)?(?!\d)", normalized)
    if match:
        return build_time_parts(match.group(1), match.group(2), match.group(3) or "0")
    match = re.search(r"(?<!\d)(\d{6})(?!\d)", normalized)
    if match:
        value = match.group(1)
        return build_time_parts(value[:2], value[2:4], value[4:6])
    match = re.search(r"(?<!\d)(\d{4})(?!\d)", normalized)
    if match:
        value = match.group(1)
        return build_time_parts(value[:2], value[2:4], "0")
    raise ValueError("未识别到常见时间格式")


def parse_format_datetime_value(date_text, time_text, config):
    date_text = normalize_datetime_source_text(date_text)
    time_text = normalize_datetime_source_text(time_text)
    if config.get("strip_value", True):
        date_text = date_text.strip()
        time_text = time_text.strip()
    parse_type = config.get("parse_type", "日期")
    structure = config.get("input_structure", "固定位置")
    parts = {"year": None, "month": None, "day": None, "hour": None, "minute": None, "second": None}
    if parse_type in ("日期", "日期时间"):
        if structure == "固定位置":
            date_parts = parse_date_fixed(date_text, config)
        elif structure == "分隔符":
            date_parts = parse_date_delimited(date_text, config)
        else:
            date_parts = parse_date_auto_common(date_text, config)
        parts.update(date_parts)
    if parse_type in ("时间", "日期时间"):
        time_source = time_text if (parse_type == "日期时间" and config.get("use_separate_time_field", False)) else date_text
        if structure == "固定位置":
            time_parts = parse_time_fixed(time_source, config)
        elif structure == "分隔符":
            time_parts = parse_time_delimited(time_source, config)
        else:
            time_parts = parse_time_auto_common(time_source, config)
        parts.update(time_parts)
    return parts


def render_format_template(parts, template):
    year = parts.get("year")
    month = parts.get("month")
    day = parts.get("day")
    hour = parts.get("hour")
    minute = parts.get("minute")
    second = parts.get("second")
    values = {
        "YYYY": f"{year:04d}" if year is not None else "",
        "YY": f"{year % 100:02d}" if year is not None else "",
        "MM": f"{month:02d}" if month is not None else "",
        "M": str(month) if month is not None else "",
        "DD": f"{day:02d}" if day is not None else "",
        "D": str(day) if day is not None else "",
        "HH": f"{hour:02d}" if hour is not None else "",
        "H": str(hour) if hour is not None else "",
        "mm": f"{minute:02d}" if minute is not None else "",
        "m": str(minute) if minute is not None else "",
        "ss": f"{second:02d}" if second is not None else "",
        "s": str(second) if second is not None else "",
    }
    text = str(template or "")
    for key in sorted(values.keys(), key=len, reverse=True):
        text = text.replace("{" + key + "}", values[key])
    return text


def format_output_value(parts, config):
    parse_type = config.get("parse_type", "日期")
    if parse_type == "时间":
        template = config.get("time_output_template", "{HH}:{mm}")
    elif parse_type == "日期时间":
        template = config.get("datetime_output_template", "{YYYY}-{MM}-{DD} {HH}:{mm}")
    else:
        template = config.get("output_template", "{YYYY}-{MM}-{DD}")
    return render_format_template(parts, template)


def apply_unmatched_format_value(original, status, config):
    mode = config.get("unmatched_mode", "留空")
    if mode == "保留原值":
        return original, status
    if mode == "填写固定值":
        return str(config.get("unmatched_fixed", "未匹配")), status
    if mode == "跳过该行":
        return "", "跳过"
    return "", status


def build_format_component_columns(parts, parse_type, prefix):
    prefix = str(prefix or "解析").strip() or "解析"
    values = []
    if parse_type in ("日期", "日期时间"):
        values.extend([
            (f"{prefix}年", f"{parts.get('year'):04d}" if parts.get("year") is not None else ""),
            (f"{prefix}月", f"{parts.get('month'):02d}" if parts.get("month") is not None else ""),
            (f"{prefix}日", f"{parts.get('day'):02d}" if parts.get("day") is not None else ""),
        ])
    if parse_type in ("时间", "日期时间"):
        values.extend([
            (f"{prefix}时", f"{parts.get('hour'):02d}" if parts.get("hour") is not None else ""),
            (f"{prefix}分", f"{parts.get('minute'):02d}" if parts.get("minute") is not None else ""),
            (f"{prefix}秒", f"{parts.get('second'):02d}" if parts.get("second") is not None else ""),
        ])
    return values


def get_datetime_parse_warning(original, config, parts):
    warnings = []
    if config.get("input_structure") == "分隔符":
        values = [
            item.strip()
            for item in split_by_config_delimiter(
                normalize_datetime_source_text(original),
                "date",
                config,
            )
            if str(item).strip()
        ]
        order = config.get("date_order", "年-月-日")
        if order in ("月-日-年", "日-月-年") and len(values) >= 2:
            try:
                first = int(values[0])
                second = int(values[1])
                if 1 <= first <= 12 and 1 <= second <= 12:
                    warnings.append("月和日均不超过12，请确认月日顺序")
            except Exception:
                pass
    if config.get("year_rule") == "不补全":
        year = parts.get("year")
        if year is not None and int(year) < 1000:
            warnings.append("年份未补全且不足四位")
    return "；".join(warnings)


def apply_format_datetime_node(headers, rows, config):
    source_idx = field_index(headers, config.get("source_field", ""))
    time_idx = None
    if config.get("parse_type") == "日期时间" and config.get("use_separate_time_field", False):
        time_idx = field_index(headers, config.get("time_source_field", ""))
    headers = list(headers)
    new_rows = normalize_rows(rows, len(headers))
    output_mode = config.get("output_mode", "生成新字段")
    parse_type = config.get("parse_type", "日期")
    main_field = str(config.get("new_field", "标准日期")).strip() or "标准日期"
    status_enabled = bool(config.get("output_status", True))
    status_field = str(config.get("status_field", "格式解析状态")).strip() or "格式解析状态"
    output_indexes = []
    status_idx = None

    if output_mode == "生成新字段":
        main_field = get_unique_header(main_field, headers)
        headers.append(main_field)
        output_indexes.append(("main", len(headers) - 1, main_field))
        for row in new_rows:
            row.append("")
    elif output_mode == "生成多个字段":
        main_field = get_unique_header(main_field, headers)
        headers.append(main_field)
        output_indexes.append(("main", len(headers) - 1, main_field))
        for row in new_rows:
            row.append("")
        for base_name, _dummy in build_format_component_columns({}, parse_type, config.get("component_prefix", "解析")):
            name = get_unique_header(base_name, headers)
            headers.append(name)
            output_indexes.append((base_name, len(headers) - 1, name))
            for row in new_rows:
                row.append("")
    else:
        output_indexes.append(("main", source_idx, headers[source_idx]))

    if status_enabled:
        status_name = get_unique_header(status_field, headers)
        headers.append(status_name)
        status_idx = len(headers) - 1
        for row in new_rows:
            row.append("")

    changed = 0
    skipped = 0
    failed = 0
    for row in new_rows:
        original = safe_cell(row, source_idx)
        time_text = safe_cell(row, time_idx) if time_idx is not None else original
        try:
            parts = parse_format_datetime_value(original, time_text, config)
            out_value = format_output_value(parts, config)
            warning = get_datetime_parse_warning(original, config, parts)
            status = "成功但存在歧义：" + warning if warning else "成功"
        except Exception as exc:
            failed += 1
            out_value, status = apply_unmatched_format_value(original, str(exc), config)
            parts = {"year": None, "month": None, "day": None, "hour": None, "minute": None, "second": None}

        if status == "跳过":
            skipped += 1
            if status_idx is not None:
                row[status_idx] = "跳过"
            continue

        component_values = dict(build_format_component_columns(parts, parse_type, config.get("component_prefix", "解析")))
        for kind, idx, name in output_indexes:
            if kind == "main":
                row[idx] = out_value
            else:
                row[idx] = component_values.get(kind, "")
        if status_idx is not None:
            row[status_idx] = status
        changed += 1

    return headers, new_rows, f"格式规范化完成：写入 {changed} 行，失败 {failed} 行，跳过 {skipped} 行"


def apply_unmatched_extract(text, status, config):
    mode = config.get("unmatched_mode", "留空")
    if mode == "留空":
        return "", status
    if mode == "保留原值":
        return text, status
    if mode == "填写固定值":
        return str(config.get("unmatched_fixed", "未匹配")), status
    if mode == "跳过该行":
        return "", "跳过"
    return "", status


def post_extract_result(result, config):
    result = "" if result is None else str(result)
    if config.get("strip_result", True):
        result = result.strip()
    return result


def extract_one_value(original, config):
    text = "" if original is None else str(original)
    method = config.get("method", "正则提取")
    case_sensitive = bool(config.get("case_sensitive", True))

    def norm(value):
        return value if case_sensitive else value.lower()

    try:
        if method == "正则提取":
            pattern = config.get("regex_pattern", "")
            if not pattern:
                raise ValueError("正则表达式不能为空。")
            flags = 0 if case_sensitive else re.IGNORECASE
            group_index = parse_int(config.get("regex_group", "0"), "提取分组")
            if config.get("regex_find_all", False):
                results = []
                for match in re.finditer(pattern, text, flags):
                    try:
                        results.append(match.group(group_index))
                    except IndexError:
                        return apply_unmatched_extract(text, "分组不存在", config)
                if not results:
                    return apply_unmatched_extract(text, "未匹配", config)
                return post_extract_result(str(config.get("regex_joiner", ";")).join(results), config), "成功"
            match = re.search(pattern, text, flags)
            if not match:
                return apply_unmatched_extract(text, "未匹配", config)
            try:
                return post_extract_result(match.group(group_index), config), "成功"
            except IndexError:
                return apply_unmatched_extract(text, "分组不存在", config)

        if method == "固定位置提取":
            start = parse_int(config.get("start_pos", "1"), "起始位置")
            length = parse_int(config.get("extract_len", "1"), "提取长度")
            start_idx = start - 1 if config.get("position_base", "从1开始") == "从1开始" else start
            if start_idx < 0 or start_idx >= len(text):
                return apply_unmatched_extract(text, "越界", config)
            return post_extract_result(text[start_idx:start_idx + length], config), "成功"

        if method == "从左取N位":
            n = parse_int(config.get("n_chars", "1"), "N")
            return post_extract_result(text[:max(n, 0)], config), "成功"

        if method == "从右取N位":
            n = parse_int(config.get("n_chars", "1"), "N")
            return post_extract_result(text[-n:] if n > 0 else "", config), "成功"

        if method == "按分隔符提取":
            delimiter = str(config.get("delimiter", "-"))
            if delimiter == "":
                raise ValueError("分隔符不能为空。")
            parts = text.split(delimiter)
            if config.get("ignore_empty_part", False):
                parts = [part for part in parts if part != ""]
            part_index = parse_int(config.get("part_index", "1"), "取第几段")
            if part_index == 0:
                raise ValueError("段序号不能为0。")
            idx = part_index - 1 if part_index > 0 else part_index
            if idx < -len(parts) or idx >= len(parts):
                return apply_unmatched_extract(text, "越界", config)
            return post_extract_result(parts[idx], config), "成功"

        if method == "前后关键字之间提取":
            start_key = str(config.get("before_key", ""))
            end_key = str(config.get("after_key", ""))
            if not start_key or not end_key:
                raise ValueError("开始关键字和结束关键字不能为空。")
            occurrence = parse_int(config.get("between_occurrence", "1"), "第几个匹配")
            search_text = norm(text)
            search_start = norm(start_key)
            search_end = norm(end_key)
            pos = 0
            found = None
            for _ in range(occurrence):
                start_pos = search_text.find(search_start, pos)
                if start_pos < 0:
                    return apply_unmatched_extract(text, "未匹配", config)
                content_start = start_pos + len(start_key)
                end_pos = search_text.find(search_end, content_start)
                if end_pos < 0:
                    return apply_unmatched_extract(text, "未匹配", config)
                found = text[content_start:end_pos]
                pos = end_pos + len(end_key)
            return post_extract_result(found, config), "成功"

        if method in ["指定字符前提取", "指定字符后提取"]:
            marker = str(config.get("marker", "-"))
            if marker == "":
                raise ValueError("指定字符不能为空。")
            search_text = norm(text)
            search_marker = norm(marker)
            idx = (
                search_text.rfind(search_marker)
                if config.get("find_mode", "第一次出现") == "最后一次出现"
                else search_text.find(search_marker)
            )
            if idx < 0:
                return apply_unmatched_extract(text, "未匹配", config)
            if method == "指定字符前提取":
                return post_extract_result(text[:idx], config), "成功"
            return post_extract_result(text[idx + len(marker):], config), "成功"

        if method == "删除前缀":
            prefix = str(config.get("prefix", ""))
            if prefix == "":
                raise ValueError("前缀不能为空。")
            if norm(text).startswith(norm(prefix)):
                return post_extract_result(text[len(prefix):], config), "成功"
            return apply_unmatched_extract(text, "未匹配", config)

        if method == "删除后缀":
            suffix = str(config.get("suffix", ""))
            if suffix == "":
                raise ValueError("后缀不能为空。")
            if norm(text).endswith(norm(suffix)):
                return post_extract_result(text[:-len(suffix)], config), "成功"
            return apply_unmatched_extract(text, "未匹配", config)

        raise ValueError(f"未知提取方式：{method}")
    except re.error as exc:
        raise ValueError(f"正则错误：{exc}") from exc


def apply_extract_node(headers, rows, config):
    idx = field_index(headers, config.get("source_field", ""))
    headers = list(headers)
    new_rows = normalize_rows(rows, len(headers))
    changed = 0
    skipped = 0

    if config.get("output_mode", "生成新字段") == "生成新字段":
        new_header = get_unique_header(config.get("new_field", "提取结果"), headers)
        headers.append(new_header)
        for row in new_rows:
            extracted, status = extract_one_value(safe_cell(row, idx), config)
            if status == "跳过":
                skipped += 1
                row.append("")
            else:
                row.append(extracted)
                changed += 1
    else:
        for row in new_rows:
            extracted, status = extract_one_value(safe_cell(row, idx), config)
            if status == "跳过":
                skipped += 1
                continue
            row[idx] = extracted
            changed += 1

    return headers, new_rows, f"写入 {changed} 行，跳过 {skipped} 行"
