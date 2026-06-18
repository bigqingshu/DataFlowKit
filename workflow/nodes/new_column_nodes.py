# -*- coding: utf-8 -*-
"""New-column workflow nodes."""

from datetime import datetime

from core.data_utils import normalize_rows
from workflow.nodes.data_common import field_index, get_unique_header


def render_current_datetime_template(dt, config):
    mode = config.get("format_mode", "占位符模板")
    if mode == "Python strftime":
        fmt = str(config.get("strftime_template", "%Y-%m-%d %H:%M:%S") or "%Y-%m-%d %H:%M:%S")
        try:
            return dt.strftime(fmt)
        except Exception as exc:
            raise ValueError(f"strftime格式错误：{exc}") from exc

    values = {
        "YYYY": f"{dt.year:04d}",
        "YY": f"{dt.year % 100:02d}",
        "MM": f"{dt.month:02d}",
        "M": str(dt.month),
        "DD": f"{dt.day:02d}",
        "D": str(dt.day),
        "HH": f"{dt.hour:02d}",
        "H": str(dt.hour),
        "mm": f"{dt.minute:02d}",
        "m": str(dt.minute),
        "ss": f"{dt.second:02d}",
        "s": str(dt.second),
        "fff": f"{dt.microsecond // 1000:03d}",
        "ffffff": f"{dt.microsecond:06d}",
        "timestamp": str(int(dt.timestamp())),
        "unix_ms": str(int(dt.timestamp() * 1000)),
    }
    text = str(config.get("template", "{YYYY}-{MM}-{DD} {HH}:{mm}:{ss}") or "")
    for key in sorted(values.keys(), key=len, reverse=True):
        text = text.replace("{" + key + "}", values[key])
    return text


def parse_new_columns_specs(config):
    text = str(config.get("columns_text", "") or "")
    strip_name = bool(config.get("strip_column_name", True))
    allow_empty = bool(config.get("allow_empty_name", False))
    value_mode = config.get("value_mode", "统一默认值")
    default_value = str(config.get("default_value", "") or "")
    specs = []
    auto_index = 1
    for raw_line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw_line.strip() if strip_name else raw_line
        if line == "":
            continue
        if "=" in line:
            name, value = line.split("=", 1)
            name = name.strip() if strip_name else name
            if value_mode == "按列配置值":
                fill_value = value
            elif value_mode == "空值":
                fill_value = ""
            else:
                fill_value = default_value
        else:
            name = line
            fill_value = "" if value_mode == "空值" else default_value
        if name == "":
            if allow_empty:
                name = f"新字段{auto_index}"
                auto_index += 1
            else:
                raise ValueError("新建列节点存在空字段名。可删除空行，或勾选允许空字段名自动命名。")
        specs.append((name, "" if fill_value is None else str(fill_value)))
    if not specs:
        raise ValueError("新建列节点没有填写任何字段名。")
    return specs


def apply_new_columns_node(headers, rows, config):
    headers = list(headers)
    new_rows = normalize_rows(rows, len(headers))
    specs = parse_new_columns_specs(config)
    conflict_mode = config.get("conflict_mode", "自动改名")
    added = 0
    overwritten = 0
    skipped = 0
    output_names = []

    for name, fill_value in specs:
        if name in headers:
            if conflict_mode == "自动改名":
                final_name = get_unique_header(name, headers)
                headers.append(final_name)
                for row in new_rows:
                    row.append(fill_value)
                added += 1
                output_names.append(final_name)
            elif conflict_mode == "跳过已有字段":
                skipped += 1
                continue
            elif conflict_mode == "覆盖已有字段":
                idx = headers.index(name)
                for row in new_rows:
                    row[idx] = fill_value
                overwritten += 1
                output_names.append(name)
            elif conflict_mode == "存在则报错":
                raise ValueError(f"新建列节点字段已存在：{name}")
            else:
                raise ValueError(f"未知同名字段处理方式：{conflict_mode}")
        else:
            headers.append(name)
            for row in new_rows:
                row.append(fill_value)
            added += 1
            output_names.append(name)

    shown = ", ".join(output_names[:8])
    if len(output_names) > 8:
        shown += f" ... 共{len(output_names)}个"
    return headers, new_rows, f"新建列完成：新增 {added} 列，覆盖 {overwritten} 列，跳过 {skipped} 列；字段：{shown}"


def apply_current_datetime_column_node(headers, rows, config, now_func=None):
    headers = list(headers)
    new_rows = normalize_rows(rows, len(headers))
    output_mode = config.get("output_mode", "生成新字段")
    now_func = now_func or datetime.now

    if output_mode == "覆盖已有字段":
        target = str(config.get("target_field", "")).strip()
        if not target:
            raise ValueError("新建日期时间列节点选择了覆盖已有字段，但未选择覆盖字段。")
        output_idx = field_index(headers, target)
        output_name = headers[output_idx]
    else:
        output_name = get_unique_header(config.get("new_field", "当前日期时间"), headers)
        headers.append(output_name)
        output_idx = len(headers) - 1
        for row in new_rows:
            row.append("")

    fixed_time = now_func()
    same_time = config.get("time_mode", "整次运行固定同一时间") == "整次运行固定同一时间"
    changed = 0
    sample = ""
    for row in new_rows:
        dt = fixed_time if same_time else now_func()
        value = render_current_datetime_template(dt, config)
        row[output_idx] = value
        if sample == "":
            sample = value
        changed += 1

    if not new_rows:
        sample = render_current_datetime_template(fixed_time, config)
    return headers, new_rows, f"新建日期时间列完成：字段【{output_name}】，写入 {changed} 行，示例：{sample}"
