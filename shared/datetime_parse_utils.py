# -*- coding: utf-8 -*-
"""Shared date parsing helpers."""

import re
from datetime import datetime


DATE_INPUT_STRUCTURES = ["固定位置", "分隔符", "自动识别常见格式"]
DATE_YEAR_RULES = ["20xx", "19xx", "自动窗口", "不补全"]
DATE_ORDERS = ["年-月-日", "月-日-年", "日-月-年"]
DATE_AMBIGUOUS_POLICIES = ["警告", "报错", "允许"]


def normalize_datetime_text(value):
    text = "" if value is None else str(value)
    trans = str.maketrans({
        "０": "0", "１": "1", "２": "2", "３": "3", "４": "4",
        "５": "5", "６": "6", "７": "7", "８": "8", "９": "9",
        "：": ":", "／": "/", "－": "-", "—": "-", "–": "-",
        "．": ".", "。": ".", "　": " ",
    })
    return text.strip().translate(trans)


def complete_year(value, config=None):
    config = config or {}
    text = str(value or "").strip()
    if not text:
        raise ValueError("年份为空")
    if not re.fullmatch(r"\d{1,4}", text):
        raise ValueError(f"年份不是数字：{text}")
    number = int(text)
    if len(text) >= 3:
        return number
    rule = config.get("year_rule", "20xx")
    if rule == "20xx":
        return 2000 + number
    if rule == "19xx":
        return 1900 + number
    if rule == "不补全":
        return number
    try:
        pivot = int(str(config.get("auto_window_pivot", "80")).strip())
    except Exception:
        pivot = 80
    return 1900 + number if number >= pivot else 2000 + number


def build_date_parts(year, month, day, config=None):
    parsed_year = complete_year(year, config)
    try:
        parsed_month = int(str(month).strip())
        parsed_day = int(str(day).strip())
    except Exception as exc:
        raise ValueError("月/日不是数字") from exc
    try:
        datetime(parsed_year, parsed_month, parsed_day)
    except Exception as exc:
        raise ValueError(
            f"日期无效：{parsed_year:04d}-{parsed_month:02d}-{parsed_day:02d}"
        ) from exc
    return {
        "year": parsed_year,
        "month": parsed_month,
        "day": parsed_day,
    }


def ambiguous_delimited_date_warning(parts, order):
    if order not in ("月-日-年", "日-月-年") or len(parts) < 2:
        return ""
    try:
        first = int(str(parts[0]).strip())
        second = int(str(parts[1]).strip())
    except Exception:
        return ""
    if 1 <= first <= 12 and 1 <= second <= 12:
        return "月和日均不超过12，请确认月日顺序"
    return ""


def ambiguous_date_policy(config=None):
    value = str((config or {}).get("ambiguous_date_policy", "警告") or "警告").strip()
    return value if value in DATE_AMBIGUOUS_POLICIES else "警告"


def check_ambiguous_delimited_date(parts, order, config=None):
    warning = ambiguous_delimited_date_warning(parts, order)
    if warning and ambiguous_date_policy(config) == "报错":
        raise ValueError(f"日期顺序存在歧义：{warning}")
    return warning


def _parse_positive_int(value, name, allow_zero=False):
    try:
        number = int(str(value).strip())
    except Exception as exc:
        raise ValueError(f"{name} 必须是整数。") from exc
    if allow_zero:
        if number < 0:
            raise ValueError(f"{name} 不能小于 0。")
    elif number <= 0:
        raise ValueError(f"{name} 必须大于 0。")
    return number


def _slice_by_position(text, start, length, base, name):
    length_value = _parse_positive_int(length, f"{name}长度", allow_zero=True)
    if length_value == 0:
        return ""
    start_value = _parse_positive_int(start, f"{name}起始")
    index = start_value - 1 if base == "从1开始" else start_value
    if index < 0 or index + length_value > len(text):
        raise ValueError(f"{name}位置越界")
    return text[index:index + length_value]


def parse_date_fixed(text, config=None):
    config = config or {}
    base = config.get("position_base", "从1开始")
    year = _slice_by_position(
        text,
        config.get("year_start", "1"),
        config.get("year_len", "2"),
        base,
        "年",
    )
    month = _slice_by_position(
        text,
        config.get("month_start", "3"),
        config.get("month_len", "2"),
        base,
        "月",
    )
    day = _slice_by_position(
        text,
        config.get("day_start", "5"),
        config.get("day_len", "2"),
        base,
        "日",
    )
    return build_date_parts(year, month, day, config)


def _split_date(text, config):
    mode = config.get("date_delimiter", "自动识别")
    custom = config.get("custom_date_delimiter", "-")
    if mode in ("年/月/日", "自动识别"):
        return re.findall(r"\d+", text)
    if mode == "自定义":
        if custom == "":
            raise ValueError("自定义日期分隔符不能为空")
        return text.split(custom)
    return text.split(mode)


def parse_date_delimited(text, config=None):
    config = config or {}
    parts = [part.strip() for part in _split_date(text, config) if str(part).strip()]
    if len(parts) < 3:
        raise ValueError("日期分隔后不足 3 段")
    order = config.get("date_order", "年-月-日")
    if order == "月-日-年":
        month, day, year = parts[:3]
    elif order == "日-月-年":
        day, month, year = parts[:3]
    else:
        year, month, day = parts[:3]
    check_ambiguous_delimited_date(parts, order, config)
    return build_date_parts(year, month, day, config)


def parse_date_auto_common(text, config=None):
    config = config or {}
    normalized = normalize_datetime_text(text)
    for pattern in (
        r"(?<!\d)(\d{4})\s*[-/.年]\s*(\d{1,2})\s*[-/.月]\s*(\d{1,2})(?:\s*日)?(?!\d)",
        r"(?<!\d)(\d{2})\s*[-/.年]\s*(\d{1,2})\s*[-/.月]\s*(\d{1,2})(?:\s*日)?(?!\d)",
    ):
        match = re.search(pattern, normalized)
        if match:
            return build_date_parts(match.group(1), match.group(2), match.group(3), config)
    match = re.search(r"(?<!\d)(\d{8})(?!\d)", normalized)
    if match:
        value = match.group(1)
        return build_date_parts(value[:4], value[4:6], value[6:8], config)
    match = re.search(r"(?<!\d)(\d{6})(?!\d)", normalized)
    if match:
        value = match.group(1)
        return build_date_parts(value[:2], value[2:4], value[4:6], config)
    raise ValueError("未识别到常见日期格式")


def parse_date_value(text, config=None):
    config = dict(config or {})
    normalized = normalize_datetime_text(text)
    structure = config.get("input_structure", "自动识别常见格式")
    if structure == "固定位置":
        parts = parse_date_fixed(normalized, config)
    elif structure == "分隔符":
        parts = parse_date_delimited(normalized, config)
    else:
        parts = parse_date_auto_common(normalized, config)
    return parts["year"], parts["month"], parts["day"]


def default_date_parser_config():
    return {
        "input_structure": "自动识别常见格式",
        "position_base": "从1开始",
        "year_start": "1",
        "year_len": "2",
        "month_start": "3",
        "month_len": "2",
        "day_start": "5",
        "day_len": "2",
        "date_delimiter": "自动识别",
        "custom_date_delimiter": "-",
        "date_order": "年-月-日",
        "ambiguous_date_policy": "警告",
        "year_rule": "20xx",
        "auto_window_pivot": "80",
    }
