# -*- coding: utf-8 -*-
"""Batch replace workflow node."""

import re

from core.data_utils import normalize_rows, safe_cell
from workflow.nodes.data_common import compare_values, field_index, safe_int


def _check_cancelled(context, index):
    callback = (context or {}).get("check_cancelled")
    if callable(callback):
        callback(index)


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
