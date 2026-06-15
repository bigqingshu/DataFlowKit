# -*- coding: utf-8 -*-
"""Pure helpers for the writeback workflow node."""

from core.data_utils import normalize_rows, safe_cell


WRITEBACK_PREVIEW_HEADERS = ["当前行号", "目标rowid", "目标行号", "行类型", "匹配状态", "目标字段", "原值", "新值", "动作"]


def compare_writeback_values(left, op, right):
    left = "" if left is None else str(left)
    right = "" if right is None else str(right)
    if op == "等于":
        return left == right
    if op == "不等于":
        return left != right
    if op in ["当前包含目标", "当前包含外部"]:
        return right != "" and right in left
    if op in ["目标包含当前", "外部包含当前"]:
        return left != "" and left in right
    if op == "双向包含":
        return (right != "" and right in left) or (left != "" and left in right)
    return left == right


def build_writeback_preview_rows(actions):
    preview_rows = [[
        a.get("source_row", ""),
        a.get("target_rowid", ""),
        a.get("target_row_index", ""),
        "新增行" if a.get("is_new_row") else "已有行",
        a.get("match_status", ""),
        a.get("target_field", ""),
        a.get("old_value", ""),
        a.get("new_value", ""),
        a.get("action", ""),
    ] for a in (actions or [])]
    return list(WRITEBACK_PREVIEW_HEADERS), preview_rows


def count_writeback_actions(actions):
    actions = list(actions or [])
    write_count = sum(1 for a in actions if a.get("write"))
    new_row_count = len({
        a.get("new_row_key")
        for a in actions
        if a.get("write") and a.get("is_new_row") and a.get("new_row_key")
    })
    return {
        "total": len(actions),
        "write_count": write_count,
        "new_row_count": new_row_count,
    }


def get_writeback_target_fields(config):
    fields = []
    for mapping in (config.get("field_mappings", []) or []):
        target_field = str(mapping.get("target_field", "")).strip()
        if target_field and target_field not in fields:
            fields.append(target_field)
    return fields


def build_writeback_preview_stat(write_range_mode, actions, target_fields=None, full_rows=None, target_columns=None):
    counts = count_writeback_actions(actions)
    if write_range_mode == "按来源完整结构覆盖":
        return (
            f"完整结构覆盖预览 {counts['total']} 条动作，待写入 {counts['write_count']} 个单元格"
            f"；目标表最终 {len(full_rows or [])} 行 × {len(target_columns or [])} 列"
        )
    stat = f"写入预览 {counts['total']} 条动作，待写入 {counts['write_count']} 个单元格"
    if write_range_mode == "清空目标字段后覆盖，保留目标原行数":
        stat += f"；执行时会先清空 {len(list(target_fields or []))} 个目标字段的整列旧值"
    if counts["new_row_count"]:
        stat += f"，将新增目标行 {counts['new_row_count']} 行"
    return stat


def build_writeback_execute_stat(table_name, actual, cleared=0, backup_name=""):
    stat = f"已写入目标表 {table_name}：{actual} 处"
    if cleared:
        stat += f"，已先清空目标字段 {cleared} 列"
    if backup_name:
        stat += f"，备份表：{backup_name}"
    return stat


def build_writeback_full_structure_execute_stat(saved, full_rows, target_columns):
    return f"已按来源完整结构覆盖 SQLite 表：{saved}（{len(full_rows)} 行 × {len(target_columns)} 列）"


def build_writeback_full_structure_rows_for_sqlite(headers, rows, config, target_columns):
    """按来源完整结构生成 SQLite 目标表的新 rows，并生成预览动作。"""
    mappings = list(config.get("field_mappings", []))
    if not mappings:
        raise ValueError("请至少添加一条字段映射规则。")
    source_empty_policy = config.get("source_empty_policy", "跳过")
    source_empty_fixed = str(config.get("source_empty_fixed", ""))
    normalized_rows = normalize_rows(rows, len(headers))
    source_field_index = {h: i for i, h in enumerate(headers)}
    target_index = {h: i for i, h in enumerate(target_columns)}
    new_rows = [[""] * len(target_columns) for _ in normalized_rows]
    actions = []

    def append_action(src_idx, status, target_field="", new_value="", action="跳过", write=False):
        actions.append({
            "source_row": src_idx + 1,
            "target_rowid": "",
            "target_row_index": src_idx + 1,
            "match_status": status,
            "target_field": target_field,
            "old_value": "",
            "new_value": new_value,
            "action": action,
            "write": bool(write),
            "is_new_row": True,
            "new_row_key": f"full_{src_idx + 1}",
        })

    for src_idx, row in enumerate(normalized_rows):
        source_record = {h: safe_cell(row, i) for i, h in enumerate(headers)}
        for mapping in mappings:
            sf = str(mapping.get("source_field", "")).strip()
            tf = str(mapping.get("target_field", "")).strip()
            if sf not in source_field_index:
                append_action(src_idx, f"来源字段不存在：{sf}", target_field=tf)
                continue
            if tf not in target_index:
                append_action(src_idx, f"目标字段不存在：{tf}", target_field=tf)
                continue
            new_value = source_record.get(sf, "")
            if new_value == "":
                if source_empty_policy == "跳过":
                    append_action(src_idx, "来源为空", target_field=tf, new_value=new_value, action="跳过")
                    continue
                if source_empty_policy == "写入固定值":
                    new_value = source_empty_fixed
            new_rows[src_idx][target_index[tf]] = new_value
            append_action(src_idx, "成功", target_field=tf, new_value=new_value, action="完整结构覆盖写入", write=True)
    return actions, new_rows


def build_writeback_actions(headers, rows, config, target_columns, target_records):
    use_match_rules = bool(config.get("use_match_rules", True))
    match_rules = list(config.get("match_rules", []))
    mappings = list(config.get("field_mappings", []))
    if use_match_rules and not match_rules:
        raise ValueError("已启用匹配规则定位目标行，请至少添加一条匹配规则；如果想按行号顺序写入，请关闭该选项。")
    if not mappings:
        raise ValueError("请至少添加一条字段映射规则。")

    target_records = [dict(record) for record in (target_records or [])]
    normalized_rows = normalize_rows(rows, len(headers))
    overwrite_policy = config.get("overwrite_policy", "目标已有值且不同才覆盖")
    write_range_mode = config.get("write_range_mode", "局部覆盖，保留目标原行数")
    if write_range_mode == "清空目标字段后覆盖，保留目标原行数":
        # 清空后目标字段为空，应按来源重新写入，避免“相同则跳过”导致清空后缺值。
        overwrite_policy = "覆盖全部"
    source_empty_policy = config.get("source_empty_policy", "跳过")
    source_empty_fixed = str(config.get("source_empty_fixed", ""))
    multi_match_policy = config.get("multi_match_policy", "跳过并记录")
    duplicate_policy = config.get("duplicate_target_policy", "跳过重复并记录异常")
    sequential_insert_missing_rows = bool(config.get("sequential_insert_missing_rows", True))

    actions = []
    touched_target_rowids = set()
    source_field_index = {h: i for i, h in enumerate(headers)}

    def append_status(src_idx, target_record, status, target_field="", old_value="", new_value="", action="跳过", write=False):
        is_new = bool(target_record.get("__is_new__", False)) if target_record else False
        actions.append({
            "source_row": src_idx + 1,
            "target_rowid": target_record.get("__rowid__", "") if target_record else "",
            "target_row_index": target_record.get("__row_index__", "") if target_record else "",
            "match_status": status,
            "target_field": target_field,
            "old_value": old_value,
            "new_value": new_value,
            "action": action,
            "write": bool(write),
            "is_new_row": is_new,
            "new_row_key": target_record.get("__new_row_key__", "") if target_record else "",
        })

    for src_idx, row in enumerate(normalized_rows):
        source_record = {h: safe_cell(row, i) for i, h in enumerate(headers)}
        matched = []

        if use_match_rules:
            for target_record in target_records:
                ok = True
                for rule in match_rules:
                    sf = rule.get("source_field", "")
                    tf = rule.get("target_field", "")
                    op = rule.get("operator", "等于")
                    if sf not in source_field_index or tf not in target_columns:
                        ok = False
                        break
                    if not compare_writeback_values(source_record.get(sf, ""), op, target_record.get(tf, "")):
                        ok = False
                        break
                if ok:
                    matched.append(target_record)
        else:
            # 关闭匹配规则后，以“来源当前表完整数据结构”为边界：
            # 当前表第 N 行 -> 目标表第 N 行；目标表行数不足时，可自动新增目标行。
            if src_idx < len(target_records):
                matched = [target_records[src_idx]]
            elif sequential_insert_missing_rows:
                matched = [{
                    "__rowid__": "",
                    "__row_index__": f"新增第{src_idx + 1}行",
                    "__is_new__": True,
                    "__new_row_key__": f"source_{src_idx + 1}",
                }]
            else:
                matched = []

        if not matched:
            status_text = "未匹配" if use_match_rules else "按来源完整结构写入失败：目标表行数不足且未启用自动新增行"
            append_status(src_idx, None, status_text, action="跳过")
            continue
        if len(matched) > 1:
            if multi_match_policy == "只更新第一行":
                matched = matched[:1]
            elif multi_match_policy == "全部更新":
                pass
            else:
                append_status(src_idx, None, f"多匹配{len(matched)}行", action="跳过")
                continue

        for target_record in matched:
            target_rowid = target_record.get("__rowid__")
            is_new_target_row = bool(target_record.get("__is_new__", False))
            if (not is_new_target_row) and target_rowid in touched_target_rowids and duplicate_policy in ["跳过重复并记录异常", "第一个有效"]:
                append_status(src_idx, target_record, "重复目标行", action="跳过")
                continue

            for mapping in mappings:
                sf = mapping.get("source_field", "")
                tf = mapping.get("target_field", "")
                if sf not in source_field_index:
                    append_status(src_idx, target_record, f"来源字段不存在：{sf}", target_field=tf, action="跳过")
                    continue
                if tf not in target_columns:
                    append_status(src_idx, target_record, f"目标字段不存在：{tf}", target_field=tf, action="跳过")
                    continue

                new_value = source_record.get(sf, "")
                old_value = target_record.get(tf, "")
                if new_value == "":
                    if source_empty_policy == "跳过":
                        append_status(src_idx, target_record, "来源为空", target_field=tf, old_value=old_value, new_value=new_value, action="跳过")
                        continue
                    if source_empty_policy == "写入固定值":
                        new_value = source_empty_fixed
                    # 写入空值则保持 new_value = ""

                write = False
                action_text = "跳过"
                if overwrite_policy == "覆盖全部":
                    write = True
                    action_text = "将覆盖"
                elif overwrite_policy == "只覆盖目标为空的字段":
                    if old_value == "":
                        write = True
                        action_text = "目标为空，将写入"
                    else:
                        action_text = "目标已有值，跳过"
                elif overwrite_policy == "目标已有值则跳过":
                    if old_value == "":
                        write = True
                        action_text = "目标为空，将写入"
                    else:
                        action_text = "目标已有值，跳过"
                else:  # 目标已有值且不同才覆盖
                    if old_value != new_value:
                        write = True
                        action_text = "不同，将覆盖"
                    else:
                        action_text = "相同，跳过"

                append_status(src_idx, target_record, "成功", target_field=tf, old_value=old_value, new_value=new_value, action=action_text, write=write)
                if write:
                    # 更新内存中的目标记录，便于同一目标字段后续判断使用最新值。
                    target_record[tf] = new_value

            touched_target_rowids.add(target_rowid)

    return actions


def apply_external_table_to_current_node(headers, rows, config, source_columns, source_records):
    """把 SQLite 其他表数据写入当前工作流表。可覆盖已有字段，也可创建新字段。"""
    use_match_rules = bool(config.get("use_match_rules", True))
    match_rules = list(config.get("match_rules", []))
    mappings = list(config.get("field_mappings", []))
    if use_match_rules and not match_rules:
        raise ValueError("已启用匹配规则定位对应行，请至少添加一条匹配规则；如果想按行号顺序写入，请关闭该选项。")
    if not mappings:
        raise ValueError("请至少添加一条字段映射规则。")

    source_records = [dict(record) for record in (source_records or [])]
    current_headers = list(headers)
    current_rows = [list(r) for r in normalize_rows(rows, len(current_headers))]
    current_index = {h: i for i, h in enumerate(current_headers)}
    source_index = {h: i for i, h in enumerate(source_columns)}
    overwrite_policy = config.get("overwrite_policy", "目标已有值且不同才覆盖")
    write_range_mode = config.get("write_range_mode", "局部覆盖，保留目标原行数")
    if write_range_mode in ["清空目标字段后覆盖，保留目标原行数", "按来源完整结构覆盖"]:
        # 这两种模式会先清空/重建目标结构，应按来源重新写入。
        overwrite_policy = "覆盖全部"
    source_empty_policy = config.get("source_empty_policy", "跳过")
    source_empty_fixed = str(config.get("source_empty_fixed", ""))
    multi_match_policy = config.get("multi_match_policy", "跳过并记录")
    duplicate_policy = config.get("duplicate_target_policy", "跳过重复并记录异常")
    insert_missing_rows = bool(config.get("sequential_insert_missing_rows", True))

    # 映射右侧允许输入新字段名。先把所有目标字段补到当前表头。
    for mapping in mappings:
        tf = str(mapping.get("target_field", "")).strip()
        if tf and tf not in current_index:
            current_index[tf] = len(current_headers)
            current_headers.append(tf)
            for row in current_rows:
                row.append("")

    # 按来源完整结构覆盖：当前表输出行数等于 SQLite 来源表行数，目标旧的多余行被丢弃。
    # 未映射字段保持空值，避免旧值残留到后续文件生成/批量处理。
    if write_range_mode == "按来源完整结构覆盖":
        new_rows = [[""] * len(current_headers) for _ in source_records]
        actions = []
        for src_idx, source_record in enumerate(source_records):
            for mapping in mappings:
                sf = str(mapping.get("source_field", "")).strip()
                tf = str(mapping.get("target_field", "")).strip()
                if sf not in source_columns:
                    actions.append({"write": False})
                    continue
                if not tf:
                    actions.append({"write": False})
                    continue
                if tf not in current_index:
                    current_index[tf] = len(current_headers)
                    current_headers.append(tf)
                    for row in new_rows:
                        row.append("")
                new_value = source_record.get(sf, "")
                if new_value == "":
                    if source_empty_policy == "跳过":
                        actions.append({"write": False})
                        continue
                    if source_empty_policy == "写入固定值":
                        new_value = source_empty_fixed
                new_rows[src_idx][current_index[tf]] = new_value
                actions.append({"write": True})
        write_count = sum(1 for a in actions if a.get("write"))
        stat = f"其他表写入当前表：按来源完整结构覆盖，输出 {len(new_rows)} 行 × {len(current_headers)} 列，写入 {write_count} 个单元格"
        return current_headers, new_rows, stat

    if write_range_mode == "清空目标字段后覆盖，保留目标原行数":
        clear_fields = []
        for mapping in mappings:
            tf = str(mapping.get("target_field", "")).strip()
            if tf and tf in current_index and tf not in clear_fields:
                clear_fields.append(tf)
        for row in current_rows:
            while len(row) < len(current_headers):
                row.append("")
            for tf in clear_fields:
                row[current_index[tf]] = ""

    actions = []
    touched_current_rows = set()

    def append_action(cur_row_index, source_record, status, target_field="", old_value="", new_value="", action="跳过", write=False, is_new_current_row=False):
        actions.append({
            "current_row": cur_row_index + 1 if isinstance(cur_row_index, int) else cur_row_index,
            "source_rowid": source_record.get("__rowid__", "") if source_record else "",
            "source_row_index": source_record.get("__row_index__", "") if source_record else "",
            "match_status": status,
            "target_field": target_field,
            "old_value": old_value,
            "new_value": new_value,
            "action": action,
            "write": bool(write),
            "is_new_current_row": bool(is_new_current_row),
        })

    def ensure_current_row(index):
        is_new = False
        while index >= len(current_rows):
            current_rows.append([""] * len(current_headers))
            is_new = True
        # 如果新增字段后历史行长度不足，这里补齐。
        while len(current_rows[index]) < len(current_headers):
            current_rows[index].append("")
        return is_new

    # 处理边界：按当前表行逐行处理；关闭匹配且来源表更长时，可按来源完整结构扩展当前表行。
    total_rows = len(current_rows)
    if not use_match_rules and insert_missing_rows:
        total_rows = max(len(current_rows), len(source_records))

    for cur_idx in range(total_rows):
        is_new_current_row = ensure_current_row(cur_idx)
        current_record = {h: safe_cell(current_rows[cur_idx], i) for i, h in enumerate(current_headers)}
        matched = []

        if use_match_rules:
            for source_record in source_records:
                ok = True
                for rule in match_rules:
                    cf = rule.get("source_field", "")   # 当前表字段
                    sf = rule.get("target_field", "")   # 外部来源表字段
                    op = rule.get("operator", "等于")
                    if cf not in current_index or sf not in source_index:
                        ok = False
                        break
                    if not compare_writeback_values(current_record.get(cf, ""), op, source_record.get(sf, "")):
                        ok = False
                        break
                if ok:
                    matched.append(source_record)
        else:
            if cur_idx < len(source_records):
                matched = [source_records[cur_idx]]
            else:
                matched = []

        if not matched:
            append_action(cur_idx, None, "未匹配来源表行" if use_match_rules else "来源表行数不足", action="跳过", is_new_current_row=is_new_current_row)
            continue
        if len(matched) > 1:
            if multi_match_policy == "只更新第一行":
                matched = matched[:1]
            elif multi_match_policy == "全部更新":
                pass
            else:
                append_action(cur_idx, None, f"多匹配来源{len(matched)}行", action="跳过", is_new_current_row=is_new_current_row)
                continue

        if cur_idx in touched_current_rows and duplicate_policy in ["跳过重复并记录异常", "第一个有效"]:
            append_action(cur_idx, matched[0] if matched else None, "重复当前目标行", action="跳过", is_new_current_row=is_new_current_row)
            continue

        for source_record in matched:
            for mapping in mappings:
                sf = str(mapping.get("source_field", "")).strip()   # 来源表字段
                tf = str(mapping.get("target_field", "")).strip()   # 当前表字段 / 新字段名
                if sf not in source_columns:
                    append_action(cur_idx, source_record, f"来源字段不存在：{sf}", target_field=tf, action="跳过", is_new_current_row=is_new_current_row)
                    continue
                if not tf:
                    append_action(cur_idx, source_record, "目标字段为空", target_field=tf, action="跳过", is_new_current_row=is_new_current_row)
                    continue
                if tf not in current_index:
                    current_index[tf] = len(current_headers)
                    current_headers.append(tf)
                    for row in current_rows:
                        row.append("")
                target_col = current_index[tf]
                while len(current_rows[cur_idx]) < len(current_headers):
                    current_rows[cur_idx].append("")

                new_value = source_record.get(sf, "")
                old_value = safe_cell(current_rows[cur_idx], target_col)
                if new_value == "":
                    if source_empty_policy == "跳过":
                        append_action(cur_idx, source_record, "来源为空", target_field=tf, old_value=old_value, new_value=new_value, action="跳过", is_new_current_row=is_new_current_row)
                        continue
                    if source_empty_policy == "写入固定值":
                        new_value = source_empty_fixed

                write = False
                action_text = "跳过"
                if overwrite_policy == "覆盖全部":
                    write = True
                    action_text = "将覆盖/写入"
                elif overwrite_policy == "只覆盖目标为空的字段":
                    if old_value == "":
                        write = True
                        action_text = "目标为空，将写入"
                    else:
                        action_text = "目标已有值，跳过"
                elif overwrite_policy == "目标已有值则跳过":
                    if old_value == "":
                        write = True
                        action_text = "目标为空，将写入"
                    else:
                        action_text = "目标已有值，跳过"
                else:
                    if old_value != new_value:
                        write = True
                        action_text = "不同，将覆盖"
                    else:
                        action_text = "相同，跳过"

                if write:
                    current_rows[cur_idx][target_col] = new_value
                append_action(cur_idx, source_record, "成功", target_field=tf, old_value=old_value, new_value=new_value, action=action_text, write=write, is_new_current_row=is_new_current_row)

            touched_current_rows.add(cur_idx)

    write_count = sum(1 for a in actions if a.get("write"))
    new_field_count = max(0, len(current_headers) - len(headers))
    new_row_count = max(0, len(current_rows) - len(rows))
    stat = f"其他表写入当前表：处理动作 {len(actions)} 条，写入 {write_count} 个单元格"
    if new_field_count:
        stat += f"，新增字段 {new_field_count} 个"
    if new_row_count:
        stat += f"，新增当前行 {new_row_count} 行"
    return current_headers, current_rows, stat
