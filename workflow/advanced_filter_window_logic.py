# -*- coding: utf-8 -*-
"""Logic helpers for the legacy AdvancedFilterWindow."""

from db import TableAccessManager


def format_advanced_filter_db_value(app, value):
    return app.format_db_value(value)


def load_advanced_filter_table_records(db_path, table_name, columns):
    data = TableAccessManager(
        db_path,
        node_type="高级筛选窗口读取",
    ).read_table(table_name)
    rows = [list(row) for row in data.get("rows", [])]

    records = []
    for row in rows:
        record = {}
        for idx, col in enumerate(columns):
            key = f"{table_name}.{col}"
            value = row[idx] if idx < len(row) else ""
            record[key] = value
        records.append(record)
    return records


def parse_advanced_filter_number(value):
    text = str(value).strip()
    if text == "":
        return None
    text = text.replace(",", "")
    return float(text)


def eval_advanced_filter_condition(record, cond):
    field = cond["field"]
    op = cond["op"]
    target = cond.get("value", "")

    value = record.get(field, "")
    value_text = "" if value is None else str(value)
    target_text = "" if target is None else str(target)

    if op == "等于":
        return value_text == target_text
    if op == "不等于":
        return value_text != target_text
    if op == "包含":
        return target_text in value_text
    if op == "不包含":
        return target_text not in value_text
    if op == "开头是":
        return value_text.startswith(target_text)
    if op == "结尾是":
        return value_text.endswith(target_text)
    if op == "为空":
        return value_text.strip() == ""
    if op == "不为空":
        return value_text.strip() != ""
    if op == "忽略大小写等于":
        return value_text.lower() == target_text.lower()
    if op == "忽略大小写包含":
        return target_text.lower() in value_text.lower()

    if op in ["大于", "小于", "大于等于", "小于等于"]:
        try:
            left = parse_advanced_filter_number(value_text)
            right = parse_advanced_filter_number(target_text)
            if left is None or right is None:
                return False

            if op == "大于":
                return left > right
            if op == "小于":
                return left < right
            if op == "大于等于":
                return left >= right
            if op == "小于等于":
                return left <= right
        except Exception:
            return False

    return False


def eval_advanced_filter_join_rule(record, rule):
    left_value = str(record.get(rule["left"], ""))
    right_value = str(record.get(rule["right"], ""))
    op = rule["op"]

    if op == "等于":
        return left_value == right_value
    if op == "不等于":
        return left_value != right_value
    if op == "左包含右":
        if right_value == "":
            return False
        return right_value in left_value
    if op == "右包含左":
        if left_value == "":
            return False
        return left_value in right_value
    if op == "双向包含":
        if left_value == "" or right_value == "":
            return False
        return left_value in right_value or right_value in left_value

    return False


def eval_advanced_filter_conditions(record, conditions, logic):
    if not conditions:
        return True

    results = [eval_advanced_filter_condition(record, cond) for cond in conditions]
    if logic == "OR":
        return any(results)
    return all(results)


def eval_advanced_filter_join_rules(record, join_rules, logic):
    if not join_rules:
        return True

    checks = []
    for rule in join_rules:
        if rule["left"] in record and rule["right"] in record:
            checks.append(eval_advanced_filter_join_rule(record, rule))

    if not checks:
        return True
    return any(checks) if logic == "OR" else all(checks)


def build_advanced_filter_result_records(
    selected_tables,
    table_records_map,
    conditions=None,
    condition_logic="AND",
    join_rules=None,
    join_logic="AND",
    result_limit=5000,
    max_intermediate=200000,
):
    if not selected_tables:
        raise ValueError("请至少选择一个数据表。")

    conditions = list(conditions or [])
    join_rules = list(join_rules or [])

    if len(selected_tables) == 1:
        records = table_records_map[selected_tables[0]]
        filtered = []
        for record in records:
            if eval_advanced_filter_conditions(record, conditions, condition_logic):
                filtered.append(record)
                if len(filtered) >= result_limit:
                    break
        return filtered

    combined_records = table_records_map[selected_tables[0]]

    for table in selected_tables[1:]:
        new_records = []
        right_records = table_records_map[table]

        for left_record in combined_records:
            for right_record in right_records:
                merged = {}
                merged.update(left_record)
                merged.update(right_record)

                if eval_advanced_filter_join_rules(merged, join_rules, join_logic):
                    new_records.append(merged)

                    if len(new_records) > max_intermediate:
                        raise RuntimeError(
                            f"中间结果超过上限 {max_intermediate} 行。"
                            "请增加匹配规则或筛选条件，避免笛卡尔组合过大。"
                        )

        combined_records = new_records

        if not combined_records:
            break

    filtered = []
    for record in combined_records:
        if eval_advanced_filter_conditions(record, conditions, condition_logic):
            filtered.append(record)
            if len(filtered) >= result_limit:
                break

    return filtered


def build_advanced_filter_template_data(
    main_table,
    selected_tables,
    conditions,
    logic,
    join_logic,
    join_rules,
    output_fields,
    result_limit,
    max_intermediate,
    save_table,
):
    return {
        "main_table": main_table,
        "selected_tables": list(selected_tables or []),
        "conditions": list(conditions or []),
        "logic": logic,
        "join_logic": join_logic,
        "join_rules": list(join_rules or []),
        "output_fields": list(output_fields or []),
        "result_limit": result_limit,
        "max_intermediate": max_intermediate,
        "save_table": save_table,
    }


def select_advanced_filter_template_tables(data, tables_cache):
    data = data or {}
    tables_cache = set(tables_cache or [])
    main_table = data.get("main_table", "")
    selected_tables = [table for table in data.get("selected_tables", []) if table in tables_cache]
    if not selected_tables and main_table in tables_cache:
        selected_tables = [main_table]
    return selected_tables


def normalize_advanced_filter_template_data(data, tables_cache, valid_fields, current_save_table=""):
    data = data or {}
    valid_fields = set(valid_fields or [])
    main_table = data.get("main_table", "")
    selected_tables = select_advanced_filter_template_tables(data, tables_cache)

    return {
        "main_table": main_table,
        "selected_tables": selected_tables,
        "conditions": [
            cond for cond in data.get("conditions", [])
            if cond.get("field") in valid_fields
        ],
        "join_rules": [
            rule for rule in data.get("join_rules", [])
            if rule.get("left") in valid_fields and rule.get("right") in valid_fields
        ],
        "output_fields": [
            field for field in data.get("output_fields", [])
            if field in valid_fields
        ],
        "logic": data.get("logic", "AND"),
        "join_logic": data.get("join_logic", "AND"),
        "result_limit": str(data.get("result_limit", "5000")),
        "max_intermediate": str(data.get("max_intermediate", "200000")),
        "save_table": str(data.get("save_table", current_save_table)),
    }


def build_advanced_filter_field_display_cache(selected_tables, columns_by_table):
    fields = []
    for table in selected_tables or []:
        for col in columns_by_table.get(table, []) or []:
            fields.append(f"{table}.{col}")
    return fields


def select_advanced_filter_combo_defaults(fields, filter_field="", join_left="", join_right=""):
    fields = list(fields or [])
    if not fields:
        return {
            "filter_field": filter_field,
            "join_left": join_left,
            "join_right": join_right,
        }

    return {
        "filter_field": filter_field if filter_field in fields else fields[0],
        "join_left": join_left if join_left in fields else fields[0],
        "join_right": join_right if join_right in fields else fields[min(1, len(fields) - 1)],
    }


def filter_advanced_filter_valid_state(conditions, join_rules, output_fields, valid_fields):
    valid = set(valid_fields or [])
    return {
        "conditions": [
            cond for cond in conditions or []
            if cond.get("field") in valid
        ],
        "join_rules": [
            rule for rule in join_rules or []
            if rule.get("left") in valid and rule.get("right") in valid
        ],
        "output_fields": [
            field for field in output_fields or []
            if field in valid
        ],
    }


def add_advanced_filter_condition(conditions, field, op, value):
    result = list(conditions or [])
    result.append({
        "field": field,
        "op": op,
        "value": value,
    })
    return result


def remove_advanced_filter_items_by_indexes(items, indexes):
    result = list(items or [])
    for index in sorted(indexes or [], reverse=True):
        if 0 <= index < len(result):
            result.pop(index)
    return result


def clear_advanced_filter_items():
    return []


def add_advanced_filter_join_rule(join_rules, left, op, right):
    result = list(join_rules or [])
    result.append({
        "left": left,
        "op": op,
        "right": right,
    })
    return result


def add_advanced_filter_output_fields(output_fields, available_fields, indexes):
    result = list(output_fields or [])
    available_fields = list(available_fields or [])
    for index in indexes or []:
        if 0 <= index < len(available_fields):
            field = available_fields[index]
            if field not in result:
                result.append(field)
    return result


def add_all_advanced_filter_output_fields(output_fields, available_fields):
    result = list(output_fields or [])
    for field in available_fields or []:
        if field not in result:
            result.append(field)
    return result


def remove_advanced_filter_output_fields(output_fields, indexes):
    return remove_advanced_filter_items_by_indexes(output_fields, indexes)


def get_advanced_filter_output_fields(output_fields, field_display_cache):
    if output_fields:
        return list(output_fields)
    return list(field_display_cache or [])


def build_advanced_filter_preview_rows(records, fields):
    return [
        [record.get(field, "") for field in fields]
        for record in records or []
    ]


def dedupe_advanced_filter_preview_rows(rows):
    seen = set()
    new_rows = []
    removed = 0
    for row in rows or []:
        key = tuple("" if value is None else str(value) for value in row)
        if key in seen:
            removed += 1
            continue
        seen.add(key)
        new_rows.append(list(row))
    return {
        "rows": new_rows,
        "removed": removed,
    }


def parse_positive_int_setting(value, default_value):
    try:
        parsed = int(str(value).strip())
        if parsed <= 0:
            return default_value
        return parsed
    except Exception:
        return default_value
