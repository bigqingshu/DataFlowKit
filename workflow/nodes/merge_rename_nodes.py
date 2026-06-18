# -*- coding: utf-8 -*-
"""Merge columns and rename columns workflow nodes."""

from core.data_utils import make_unique_headers, normalize_rows, safe_cell
from workflow.nodes.data_common import field_index, get_unique_header, parse_separator_text


def _check_cancelled(context, index):
    callback = (context or {}).get("check_cancelled")
    if callable(callback):
        callback(index)


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
