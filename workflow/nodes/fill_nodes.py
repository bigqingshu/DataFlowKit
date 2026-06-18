# -*- coding: utf-8 -*-
"""Fill value, sequence fill, and area fill workflow nodes."""

from core.data_utils import normalize_rows, safe_cell
from workflow.nodes.data_common import (
    MAX_EXPANDED_ROWS,
    MAX_TARGET_CELLS,
    ensure_column_count,
    ensure_field_exists,
    ensure_row_count,
    ensure_target_cell_limit,
    field_index,
    get_positive_int,
    get_unique_header,
    last_non_empty_row_index_by_field,
    parse_row_number,
    row_is_empty,
)


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
