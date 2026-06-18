# -*- coding: utf-8 -*-
"""Datetime parsing and formatting workflow node."""

import re
from datetime import datetime

from core.data_utils import normalize_rows, safe_cell
from workflow.nodes.data_common import field_index, get_unique_header
from shared.datetime_parse_utils import (
    ambiguous_date_policy,
    ambiguous_delimited_date_warning,
    check_ambiguous_delimited_date,
    complete_year,
    normalize_datetime_text,
    parse_date_auto_common as shared_parse_date_auto_common,
)


def normalize_datetime_source_text(value):
    return normalize_datetime_text(value)


def parse_format_int(value, name, allow_zero=False):
    try:
        n = int(str(value).strip())
    except Exception:
        raise ValueError(f"{name} 必须是整数。")
    if allow_zero:
        if n < 0:
            raise ValueError(f"{name} 不能小于 0。")
    else:
        if n <= 0:
            raise ValueError(f"{name} 必须大于 0。")
    return n


def slice_by_position(text, start, length, base, name):
    length = parse_format_int(length, f"{name}长度", allow_zero=True)
    if length == 0:
        return ""
    start = parse_format_int(start, f"{name}起始")
    idx = start - 1 if base == "从1开始" else start
    if idx < 0 or idx + length > len(text):
        raise ValueError(f"{name}位置越界")
    return text[idx:idx + length]


def complete_format_year(value, config):
    return complete_year(value, config)


def build_date_parts(year, month, day, config):
    parsed_year = complete_format_year(year, config)
    try:
        parsed_month = int(str(month).strip())
        parsed_day = int(str(day).strip())
    except Exception:
        raise ValueError("月/日不是数字")
    try:
        datetime(parsed_year, parsed_month, parsed_day)
    except Exception:
        raise ValueError(f"日期无效：{parsed_year:04d}-{parsed_month:02d}-{parsed_day:02d}")
    return {"year": parsed_year, "month": parsed_month, "day": parsed_day}


def build_time_parts(hour, minute="0", second="0"):
    try:
        parsed_hour = int(str(hour).strip())
        parsed_minute = int(str(minute).strip()) if str(minute).strip() != "" else 0
        parsed_second = int(str(second).strip()) if str(second).strip() != "" else 0
    except Exception:
        raise ValueError("时/分/秒不是数字")
    if not (0 <= parsed_hour <= 23):
        raise ValueError("小时超出范围 0-23")
    if not (0 <= parsed_minute <= 59):
        raise ValueError("分钟超出范围 0-59")
    if not (0 <= parsed_second <= 59):
        raise ValueError("秒超出范围 0-59")
    return {"hour": parsed_hour, "minute": parsed_minute, "second": parsed_second}


def parse_date_fixed(text, config):
    base = config.get("position_base", "从1开始")
    year = slice_by_position(text, config.get("year_start", "1"), config.get("year_len", "2"), base, "年")
    month = slice_by_position(text, config.get("month_start", "3"), config.get("month_len", "2"), base, "月")
    day = slice_by_position(text, config.get("day_start", "5"), config.get("day_len", "2"), base, "日")
    return build_date_parts(year, month, day, config)


def parse_time_fixed(text, config):
    base = config.get("position_base", "从1开始")
    hour = slice_by_position(text, config.get("hour_start", "1"), config.get("hour_len", "2"), base, "时")
    minute = slice_by_position(text, config.get("minute_start", "3"), config.get("minute_len", "2"), base, "分")
    second = slice_by_position(text, config.get("second_start", "5"), config.get("second_len", "0"), base, "秒")
    return build_time_parts(hour, minute, second or "0")


def split_by_config_delimiter(text, kind, config):
    if kind == "date":
        mode = config.get("date_delimiter", "自动识别")
        custom = config.get("custom_date_delimiter", "-")
        if mode == "年/月/日":
            return re.findall(r"\d+", text)
        if mode == "自定义":
            if custom == "":
                raise ValueError("自定义日期分隔符不能为空")
            return text.split(custom)
        if mode == "自动识别":
            return re.findall(r"\d+", text)
        return text.split(mode)

    mode = config.get("time_delimiter", "自动识别")
    custom = config.get("custom_time_delimiter", ":")
    if mode == "时/分/秒":
        return re.findall(r"\d+", text)
    if mode == "自定义":
        if custom == "":
            raise ValueError("自定义时间分隔符不能为空")
        return text.split(custom)
    if mode == "自动识别":
        return re.findall(r"\d+", text)
    return text.split(mode)


def parse_date_delimited(text, config):
    parts = [part.strip() for part in split_by_config_delimiter(text, "date", config) if str(part).strip() != ""]
    if len(parts) < 3:
        raise ValueError("日期分隔后不足 3 段")
    order = config.get("date_order", "年-月-日")
    if order == "月-日-年":
        month, day, year = parts[0], parts[1], parts[2]
    elif order == "日-月-年":
        day, month, year = parts[0], parts[1], parts[2]
    else:
        year, month, day = parts[0], parts[1], parts[2]
    check_ambiguous_delimited_date(parts, order, config)
    return build_date_parts(year, month, day, config)


def parse_time_delimited(text, config):
    parts = [part.strip() for part in split_by_config_delimiter(text, "time", config) if str(part).strip() != ""]
    if len(parts) < 2:
        raise ValueError("时间分隔后不足 2 段")
    hour = parts[0]
    minute = parts[1]
    second = parts[2] if len(parts) >= 3 else "0"
    return build_time_parts(hour, minute, second)


def parse_date_auto_common(text, config):
    return shared_parse_date_auto_common(text, config)


def parse_time_auto_common(text, config):
    normalized = normalize_datetime_source_text(text)
    match = re.search(r"(?<!\d)(\d{1,2})\s*[:时]\s*(\d{1,2})(?:\s*[:分]\s*(\d{1,2}))?(?:\s*秒)?(?!\d)", normalized)
    if match:
        return build_time_parts(match.group(1), match.group(2), match.group(3) or "0")
    match = re.search(r"(?<!\d)(\d{6})(?!\d)", normalized)
    if match:
        value = match.group(1)
        return build_time_parts(value[:2], value[2:4], value[4:6])
    match = re.search(r"(?<!\d)(\d{4})(?!\d)", normalized)
    if match:
        value = match.group(1)
        return build_time_parts(value[:2], value[2:4], "0")
    raise ValueError("未识别到常见时间格式")


def parse_format_datetime_value(date_text, time_text, config):
    date_text = normalize_datetime_source_text(date_text)
    time_text = normalize_datetime_source_text(time_text)
    if config.get("strip_value", True):
        date_text = date_text.strip()
        time_text = time_text.strip()
    parse_type = config.get("parse_type", "日期")
    structure = config.get("input_structure", "固定位置")
    parts = {"year": None, "month": None, "day": None, "hour": None, "minute": None, "second": None}
    if parse_type in ("日期", "日期时间"):
        if structure == "固定位置":
            date_parts = parse_date_fixed(date_text, config)
        elif structure == "分隔符":
            date_parts = parse_date_delimited(date_text, config)
        else:
            date_parts = parse_date_auto_common(date_text, config)
        parts.update(date_parts)
    if parse_type in ("时间", "日期时间"):
        time_source = time_text if (parse_type == "日期时间" and config.get("use_separate_time_field", False)) else date_text
        if structure == "固定位置":
            time_parts = parse_time_fixed(time_source, config)
        elif structure == "分隔符":
            time_parts = parse_time_delimited(time_source, config)
        else:
            time_parts = parse_time_auto_common(time_source, config)
        parts.update(time_parts)
    return parts


def render_format_template(parts, template):
    year = parts.get("year")
    month = parts.get("month")
    day = parts.get("day")
    hour = parts.get("hour")
    minute = parts.get("minute")
    second = parts.get("second")
    values = {
        "YYYY": f"{year:04d}" if year is not None else "",
        "YY": f"{year % 100:02d}" if year is not None else "",
        "MM": f"{month:02d}" if month is not None else "",
        "M": str(month) if month is not None else "",
        "DD": f"{day:02d}" if day is not None else "",
        "D": str(day) if day is not None else "",
        "HH": f"{hour:02d}" if hour is not None else "",
        "H": str(hour) if hour is not None else "",
        "mm": f"{minute:02d}" if minute is not None else "",
        "m": str(minute) if minute is not None else "",
        "ss": f"{second:02d}" if second is not None else "",
        "s": str(second) if second is not None else "",
    }
    text = str(template or "")
    for key in sorted(values.keys(), key=len, reverse=True):
        text = text.replace("{" + key + "}", values[key])
    return text


def format_output_value(parts, config):
    parse_type = config.get("parse_type", "日期")
    if parse_type == "时间":
        template = config.get("time_output_template", "{HH}:{mm}")
    elif parse_type == "日期时间":
        template = config.get("datetime_output_template", "{YYYY}-{MM}-{DD} {HH}:{mm}")
    else:
        template = config.get("output_template", "{YYYY}-{MM}-{DD}")
    return render_format_template(parts, template)


def apply_unmatched_format_value(original, status, config):
    mode = config.get("unmatched_mode", "留空")
    if mode == "保留原值":
        return original, status
    if mode == "填写固定值":
        return str(config.get("unmatched_fixed", "未匹配")), status
    if mode == "跳过该行":
        return "", "跳过"
    return "", status


def build_format_component_columns(parts, parse_type, prefix):
    prefix = str(prefix or "解析").strip() or "解析"
    values = []
    if parse_type in ("日期", "日期时间"):
        values.extend([
            (f"{prefix}年", f"{parts.get('year'):04d}" if parts.get("year") is not None else ""),
            (f"{prefix}月", f"{parts.get('month'):02d}" if parts.get("month") is not None else ""),
            (f"{prefix}日", f"{parts.get('day'):02d}" if parts.get("day") is not None else ""),
        ])
    if parse_type in ("时间", "日期时间"):
        values.extend([
            (f"{prefix}时", f"{parts.get('hour'):02d}" if parts.get("hour") is not None else ""),
            (f"{prefix}分", f"{parts.get('minute'):02d}" if parts.get("minute") is not None else ""),
            (f"{prefix}秒", f"{parts.get('second'):02d}" if parts.get("second") is not None else ""),
        ])
    return values


def get_datetime_parse_warning(original, config, parts):
    warnings = []
    if config.get("input_structure") == "分隔符":
        values = [
            item.strip()
            for item in split_by_config_delimiter(
                normalize_datetime_source_text(original),
                "date",
                config,
            )
            if str(item).strip()
        ]
        order = config.get("date_order", "年-月-日")
        warning = ambiguous_delimited_date_warning(values, order)
        if warning and ambiguous_date_policy(config) != "允许":
            warnings.append(warning)
    if config.get("year_rule") == "不补全":
        year = parts.get("year")
        if year is not None and int(year) < 1000:
            warnings.append("年份未补全且不足四位")
    return "；".join(warnings)


def apply_format_datetime_node(headers, rows, config):
    source_idx = field_index(headers, config.get("source_field", ""))
    time_idx = None
    if config.get("parse_type") == "日期时间" and config.get("use_separate_time_field", False):
        time_idx = field_index(headers, config.get("time_source_field", ""))
    headers = list(headers)
    new_rows = normalize_rows(rows, len(headers))
    output_mode = config.get("output_mode", "生成新字段")
    parse_type = config.get("parse_type", "日期")
    main_field = str(config.get("new_field", "标准日期")).strip() or "标准日期"
    status_enabled = bool(config.get("output_status", True))
    status_field = str(config.get("status_field", "格式解析状态")).strip() or "格式解析状态"
    output_indexes = []
    status_idx = None

    if output_mode == "生成新字段":
        main_field = get_unique_header(main_field, headers)
        headers.append(main_field)
        output_indexes.append(("main", len(headers) - 1, main_field))
        for row in new_rows:
            row.append("")
    elif output_mode == "生成多个字段":
        main_field = get_unique_header(main_field, headers)
        headers.append(main_field)
        output_indexes.append(("main", len(headers) - 1, main_field))
        for row in new_rows:
            row.append("")
        for base_name, _dummy in build_format_component_columns({}, parse_type, config.get("component_prefix", "解析")):
            name = get_unique_header(base_name, headers)
            headers.append(name)
            output_indexes.append((base_name, len(headers) - 1, name))
            for row in new_rows:
                row.append("")
    else:
        output_indexes.append(("main", source_idx, headers[source_idx]))

    if status_enabled:
        status_name = get_unique_header(status_field, headers)
        headers.append(status_name)
        status_idx = len(headers) - 1
        for row in new_rows:
            row.append("")

    changed = 0
    skipped = 0
    failed = 0
    for row in new_rows:
        original = safe_cell(row, source_idx)
        time_text = safe_cell(row, time_idx) if time_idx is not None else original
        try:
            parts = parse_format_datetime_value(original, time_text, config)
            out_value = format_output_value(parts, config)
            warning = get_datetime_parse_warning(original, config, parts)
            status = "成功但存在歧义：" + warning if warning else "成功"
        except Exception as exc:
            failed += 1
            out_value, status = apply_unmatched_format_value(original, str(exc), config)
            parts = {"year": None, "month": None, "day": None, "hour": None, "minute": None, "second": None}

        if status == "跳过":
            skipped += 1
            if status_idx is not None:
                row[status_idx] = "跳过"
            continue

        component_values = dict(build_format_component_columns(parts, parse_type, config.get("component_prefix", "解析")))
        for kind, idx, name in output_indexes:
            if kind == "main":
                row[idx] = out_value
            else:
                row[idx] = component_values.get(kind, "")
        if status_idx is not None:
            row[status_idx] = status
        changed += 1

    return headers, new_rows, f"格式规范化完成：写入 {changed} 行，失败 {failed} 行，跳过 {skipped} 行"
