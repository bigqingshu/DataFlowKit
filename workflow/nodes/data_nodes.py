# -*- coding: utf-8 -*-
"""Pure data-shaping workflow nodes."""

from core.data_utils import normalize_rows, safe_cell


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

