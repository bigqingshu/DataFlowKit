# -*- coding: utf-8 -*-
"""Dedupe workflow node."""

from core.data_utils import make_unique_headers_for_append, normalize_rows, safe_cell


def _check_cancelled(context, index):
    callback = (context or {}).get("check_cancelled")
    if callable(callback):
        callback(index)


def apply_dedupe_node(headers, rows, config, context=None):
    """去重 / 重复数据处理节点。"""
    headers = list(headers)
    normalized = normalize_rows(rows, len(headers))
    if not headers:
        return headers, normalized, "去重：无字段，未处理"

    mode = config.get("dedupe_mode", "指定字段/组合字段去重")
    key_fields = list(config.get("key_fields", []))
    trim = bool(config.get("trim", True))
    ignore_case = bool(config.get("ignore_case", False))
    empty_key_policy = config.get("empty_key_policy", "空键参与去重")
    keep_policy = config.get("keep_policy", "保留第一条")
    output_mode = config.get("output_mode", "输出去重后的数据")
    add_marker = bool(config.get("add_marker_columns", True)) or output_mode == "原表增加重复标记列"

    if mode == "整行去重":
        key_indices = list(range(len(headers)))
        key_names = list(headers)
    else:
        if not key_fields:
            raise ValueError("去重节点需要至少选择一个去重字段。")
        missing = [field for field in key_fields if field not in headers]
        if missing:
            raise ValueError("去重字段不存在：" + ", ".join(missing))
        key_indices = [headers.index(field) for field in key_fields]
        key_names = list(key_fields)

    def normalize_key_value(value):
        text = "" if value is None else str(value)
        if trim:
            text = text.strip()
        if ignore_case:
            text = text.lower()
        return text

    groups = {}
    order = []
    skipped_empty = []
    for row_idx, row in enumerate(normalized):
        _check_cancelled(context, row_idx)
        key = tuple(normalize_key_value(safe_cell(row, index)) for index in key_indices)
        if empty_key_policy == "空键跳过去重" and all(value == "" for value in key):
            skipped_empty.append(row_idx)
            continue
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(row_idx)

    keep_indices = set(skipped_empty)
    duplicate_rows = set()
    group_info = {}
    duplicate_group_count = 0

    def non_empty_count(row):
        return sum(1 for cell in row if str(cell).strip() != "")

    for group_index, key in enumerate(order):
        _check_cancelled(context, group_index)
        indexes = groups[key]
        is_duplicate = len(indexes) > 1
        if is_duplicate:
            duplicate_group_count += 1
            group_id = f"DUP_{duplicate_group_count:04d}"
            duplicate_rows.update(indexes)
        else:
            group_id = ""

        if keep_policy == "保留最后一条":
            keep_idx = indexes[-1]
        elif keep_policy == "保留非空字段最多":
            keep_idx = max(indexes, key=lambda index: (non_empty_count(normalized[index]), -index))
        else:
            # “保留第一条”和“不删除，仅标记”都把第一条作为保留标记。
            keep_idx = indexes[0]

        keep_indices.add(keep_idx)
        for pos, row_idx in enumerate(indexes, start=1):
            group_info[row_idx] = {
                "key": key,
                "group_id": group_id,
                "group_index": pos,
                "group_count": len(indexes),
                "is_duplicate": is_duplicate,
                "keep": row_idx == keep_idx,
            }

    for row_idx in skipped_empty:
        group_info[row_idx] = {
            "key": tuple("" for _ in key_indices),
            "group_id": "",
            "group_index": 1,
            "group_count": 1,
            "is_duplicate": False,
            "keep": True,
            "empty_skipped": True,
        }

    if output_mode == "原表增加重复标记列" or keep_policy == "不删除，仅标记":
        selected_indices = list(range(len(normalized)))
        add_marker = True
    elif output_mode == "输出重复项数据":
        selected_indices = [index for index in range(len(normalized)) if index in duplicate_rows]
    elif output_mode == "输出唯一项数据":
        selected_indices = [index for index in range(len(normalized)) if index not in duplicate_rows]
    elif output_mode == "输出重复统计表":
        stat_headers = list(key_names) + ["重复次数", "重复组编号", "是否重复"]
        stat_rows = []
        duplicate_group_no = 0
        for group_index, key in enumerate(order):
            _check_cancelled(context, group_index)
            indexes = groups[key]
            is_duplicate = len(indexes) > 1
            if is_duplicate:
                duplicate_group_no += 1
                gid = f"DUP_{duplicate_group_no:04d}"
            else:
                gid = ""
            stat_rows.append(list(key) + [str(len(indexes)), gid, "是" if is_duplicate else "否"])
        # 空键跳过去重的行单独记为未参与。
        if skipped_empty:
            stat_rows.append(["" for _ in key_names] + [str(len(skipped_empty)), "", "空键跳过"])
        return stat_headers, stat_rows, f"去重统计：共 {len(stat_rows)} 个统计项，重复组 {duplicate_group_count} 个"
    else:
        selected_indices = [index for index in range(len(normalized)) if index in keep_indices]

    out_headers = list(headers)
    if add_marker:
        marker_fields = [
            config.get("duplicate_group_field", "重复组编号") or "重复组编号",
            config.get("duplicate_status_field", "重复状态") or "重复状态",
            config.get("duplicate_index_field", "组内序号") or "组内序号",
            config.get("duplicate_count_field", "重复次数") or "重复次数",
            config.get("keep_flag_field", "是否保留") or "是否保留",
        ]
        marker_fields = make_unique_headers_for_append(out_headers, marker_fields)
        out_headers += marker_fields

    out_rows = []
    for output_index, row_index in enumerate(selected_indices):
        _check_cancelled(context, output_index)
        row = list(normalized[row_index])
        info = group_info.get(row_index, {})
        if add_marker:
            if info.get("empty_skipped"):
                status = "空键跳过"
            elif info.get("is_duplicate"):
                status = "重复"
            else:
                status = "唯一"
            row += [
                info.get("group_id", ""),
                status,
                str(info.get("group_index", "")),
                str(info.get("group_count", "")),
                "是" if info.get("keep") else "否",
            ]
        out_rows.append(row)

    total = len(normalized)
    output_count = len(out_rows)
    duplicate_row_count = len(duplicate_rows)
    if output_mode == "输出去重后的数据":
        action = "输出去重后的数据"
    elif output_mode == "输出重复项数据":
        action = "输出重复项数据"
    elif output_mode == "输出唯一项数据":
        action = "输出唯一项数据"
    else:
        action = "增加重复标记列"
    return out_headers, out_rows, (
        f"去重完成：原 {total} 行，输出 {output_count} 行，"
        f"重复组 {duplicate_group_count} 个，重复行 {duplicate_row_count} 行，模式：{action}"
    )
