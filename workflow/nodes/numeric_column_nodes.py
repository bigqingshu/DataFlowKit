# -*- coding: utf-8 -*-
"""Numeric column operation workflow node."""

from decimal import Decimal, InvalidOperation

from core.data_utils import normalize_rows, safe_cell
from workflow.nodes.data_common import (
    MAX_EXPANDED_ROWS,
    ensure_field_exists,
    ensure_row_count,
    field_index,
    get_unique_header,
    last_non_empty_row_index_by_field,
    parse_row_number,
)


def _check_cancelled(context, index):
    callback = (context or {}).get("check_cancelled")
    if callable(callback):
        callback(index)


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
