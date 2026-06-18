# -*- coding: utf-8 -*-
"""Row data mapping workflow node."""

from core.data_utils import normalize_rows, safe_cell
from workflow.nodes.data_common import get_positive_int, get_unique_header, parse_row_number, row_is_empty


def get_row_mapping_end_index(rows, start_idx, config, col_count=None):
    """计算行数据映射节点的结束行下标，返回包含式 end_idx。"""
    total = len(rows)
    if total <= 0:
        return -1
    end_mode = config.get("end_mode", "填充到数据边界")
    if end_mode == "固定行数":
        count = get_positive_int(config.get("count", "1"), 1)
        return min(total - 1, start_idx + count - 1)
    if end_mode == "填充到指定行":
        end_row = parse_row_number(config.get("end_row", "1"), "结束行号") - 1
        return min(total - 1, max(start_idx, end_row))
    return total - 1


def apply_row_data_mapping_node(headers, rows, config):
    """按当前行号同步取值，把每行指定字段展开成多行输出。"""
    headers = list(headers)
    normalized = normalize_rows(rows, len(headers))
    if not normalized:
        return headers, normalized, "当前无数据，未展开"

    value_fields = [field for field in config.get("value_fields", []) if field in headers]
    if not value_fields:
        raise ValueError("请至少选择一个取值字段。")
    keep_fields = [field for field in config.get("keep_fields", []) if field in headers and field not in []]

    start_idx = parse_row_number(config.get("start_row", "1"), "起始行号") - 1
    if start_idx >= len(normalized):
        raise ValueError("起始行号超出当前数据范围。")
    end_idx = get_row_mapping_end_index(normalized, start_idx, config, len(headers))

    value_indexes = [(field, headers.index(field)) for field in value_fields]
    keep_indexes = [(field, headers.index(field)) for field in keep_fields]
    empty_mode = config.get("empty_mode", "跳过空值")
    empty_fixed = str(config.get("empty_fixed", "未填写"))
    trim_value = bool(config.get("trim_value", True))

    out_headers = []
    for field, _ in keep_indexes:
        if field not in out_headers:
            out_headers.append(field)

    if bool(config.get("output_original_row", True)):
        row_field = get_unique_header(config.get("original_row_field", "原始行号"), out_headers)
        out_headers.append(row_field)
    else:
        row_field = None

    if bool(config.get("output_source_field", True)):
        source_field = get_unique_header(config.get("source_field_name", "来源字段"), out_headers)
        out_headers.append(source_field)
    else:
        source_field = None

    value_field = get_unique_header(config.get("output_value_field", "输出内容"), out_headers)
    out_headers.append(value_field)

    if bool(config.get("output_status", True)):
        status_field = get_unique_header(config.get("status_field", "状态"), out_headers)
        out_headers.append(status_field)
    else:
        status_field = None

    out_rows = []
    skipped_empty = 0
    stopped_by_empty_row = False
    for row_idx in range(start_idx, end_idx + 1):
        if row_idx < 0 or row_idx >= len(normalized):
            continue
        row = normalized[row_idx]
        if config.get("end_mode") == "遇到空行停止" and row_is_empty(row, len(headers)):
            stopped_by_empty_row = True
            break

        keep_values = [safe_cell(row, index) for _, index in keep_indexes]
        for field_name, field_idx in value_indexes:
            value = safe_cell(row, field_idx)
            if trim_value:
                value = value.strip()
            status = "成功"
            if value == "":
                if empty_mode == "跳过空值":
                    skipped_empty += 1
                    continue
                if empty_mode == "填写固定值":
                    value = empty_fixed
                    status = "空值已填固定值"
                else:
                    status = "空值"

            out_row = list(keep_values)
            if row_field is not None:
                out_row.append(str(row_idx + 1))
            if source_field is not None:
                out_row.append(field_name)
            out_row.append(value)
            if status_field is not None:
                out_row.append(status)
            out_rows.append(out_row)

    stat = f"按行取值展开 {len(out_rows)} 行"
    if skipped_empty:
        stat += f"，跳过空值 {skipped_empty} 个"
    if stopped_by_empty_row:
        stat += "，遇到空行停止"
    return out_headers, out_rows, stat
