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


def parse_positive_int_setting(value, default_value):
    try:
        parsed = int(str(value).strip())
        if parsed <= 0:
            return default_value
        return parsed
    except Exception:
        return default_value
