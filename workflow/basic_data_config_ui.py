# -*- coding: utf-8 -*-
"""Tkinter UI helpers for common data-transform workflow node configurations."""

import tkinter as tk
from tkinter import ttk


def build_replace_config(window, config, headers):
    frame = ttk.LabelFrame(window.config_frame, text="批量替换节点", padding=8)
    frame.pack(fill=tk.X, pady=8)
    frame.columnconfigure(1, weight=1)
    frame.columnconfigure(3, weight=1)
    headers = list(headers)

    target_var = window.add_labeled_combo(frame, "目标字段：", config.get("target_field", ""), headers, 0, 0, 24, readonly=False)
    replace_mode_var = window.add_labeled_combo(frame, "替换方式：", config.get("replace_mode", "局部替换匹配字符串"), window.REPLACE_MODES, 0, 2, 22)
    count_var = window.add_labeled_entry(frame, "次数：", config.get("replace_count", "0"), 0, 4, 8)

    legacy_source = config.get("value_source", "手动输入")
    match_source_default = config.get("match_value_source") or legacy_source or "手动输入"
    replace_source_default = config.get("replace_value_source") or legacy_source or "手动输入"
    if match_source_default not in window.REPLACE_VALUE_SOURCES:
        match_source_default = "手动输入"
    if replace_source_default not in window.REPLACE_VALUE_SOURCES:
        replace_source_default = "手动输入"
    match_field_default = config.get("match_value_field", "") if config.get("match_value_field", "") in headers else (headers[0] if headers else "")
    repl_field_default = config.get("replace_value_field", "") if config.get("replace_value_field", "") in headers else (headers[0] if headers else "")

    match_box = ttk.LabelFrame(frame, text="1. 匹配命中值", padding=6)
    match_box.grid(row=1, column=0, columnspan=6, sticky="ew", padx=2, pady=(8, 2))
    match_box.columnconfigure(1, weight=1)
    match_box.columnconfigure(3, weight=1)
    mode_var = window.add_labeled_combo(match_box, "匹配方式：", config.get("match_mode", "包含"), window.REPLACE_MATCH_MODES, 0, 0, 16)
    match_source_var = window.add_labeled_combo(match_box, "匹配值来源：", match_source_default, window.REPLACE_VALUE_SOURCES, 0, 2, 12)
    match_var = window.add_labeled_entry(match_box, "匹配值：", config.get("match_value", ""), 1, 0, 28)
    match_field_var = window.add_labeled_combo(match_box, "匹配值字段：", match_field_default, headers, 1, 2, 24, readonly=False)
    match_row_policy_var = window.add_labeled_combo(match_box, "匹配取行：", config.get("match_row_policy", "当前行"), window.REPLACE_ROW_POLICIES, 2, 0, 12)
    match_row_index_var = window.add_labeled_entry(match_box, "固定行号：", config.get("match_row_index", "1"), 2, 2, 8)

    replace_box = ttk.LabelFrame(frame, text="2. 替换为", padding=6)
    replace_box.grid(row=2, column=0, columnspan=6, sticky="ew", padx=2, pady=2)
    replace_box.columnconfigure(1, weight=1)
    replace_box.columnconfigure(3, weight=1)
    replace_source_var = window.add_labeled_combo(replace_box, "替换值来源：", replace_source_default, window.REPLACE_VALUE_SOURCES, 0, 0, 12)
    repl_var = window.add_labeled_entry(replace_box, "替换值：", config.get("replace_value", ""), 0, 2, 28)
    repl_field_var = window.add_labeled_combo(replace_box, "替换值字段：", repl_field_default, headers, 1, 0, 24, readonly=False)
    replace_row_policy_var = window.add_labeled_combo(replace_box, "替换取行：", config.get("replace_row_policy", "当前行"), window.REPLACE_ROW_POLICIES, 1, 2, 12)
    replace_row_index_var = window.add_labeled_entry(replace_box, "固定行号：", config.get("replace_row_index", "1"), 2, 0, 8)

    case_var = tk.BooleanVar(value=config.get("case_sensitive", True))
    ttk.Checkbutton(frame, text="区分大小写", variable=case_var).grid(row=3, column=0, sticky=tk.W, padx=4, pady=4)
    skip_empty_var = tk.BooleanVar(value=bool(config.get("skip_empty_match_value", True)))
    ttk.Checkbutton(frame, text="列匹配值为空时跳过", variable=skip_empty_var).grid(row=3, column=1, columnspan=2, sticky=tk.W, padx=4, pady=4)
    ttk.Label(
        frame,
        text="说明：旧配置仍按“本行匹配字段→本行替换字段”执行；新配置可分别指定匹配值/替换值来源和取行策略。次数 0 表示全部替换。",
        foreground="gray",
        wraplength=980,
    ).grid(row=4, column=0, columnspan=6, sticky=tk.W, padx=4, pady=(2, 4))

    for var, key in [
        (target_var, "target_field"),
        (mode_var, "match_mode"),
        (match_var, "match_value"),
        (repl_var, "replace_value"),
        (replace_mode_var, "replace_mode"),
        (count_var, "replace_count"),
        (match_source_var, "match_value_source"),
        (replace_source_var, "replace_value_source"),
        (match_field_var, "match_value_field"),
        (repl_field_var, "replace_value_field"),
        (match_row_policy_var, "match_row_policy"),
        (match_row_index_var, "match_row_index"),
        (replace_row_policy_var, "replace_row_policy"),
        (replace_row_index_var, "replace_row_index"),
    ]:
        window.sync_var_to_config(var, config, key)

    def sync_legacy_value_source(*_):
        config["value_source"] = "列字段" if (match_source_var.get() == "列字段" or replace_source_var.get() == "列字段") else "手动输入"

    match_source_var.trace_add("write", sync_legacy_value_source)
    replace_source_var.trace_add("write", sync_legacy_value_source)
    sync_legacy_value_source()
    window.sync_bool_to_config(case_var, config, "case_sensitive")
    window.sync_bool_to_config(skip_empty_var, config, "skip_empty_match_value")


def build_extract_config(window, config, headers):
    headers = list(headers)
    top = ttk.LabelFrame(window.config_frame, text="数据提取节点", padding=8)
    top.pack(fill=tk.X, pady=8)
    source_var = window.add_labeled_combo(top, "源字段：", config.get("source_field", ""), headers, 0, 0, 24, readonly=False)
    method_var = window.add_labeled_combo(top, "提取方式：", config.get("method", "正则提取"), window.EXTRACT_METHODS, 0, 2, 18)
    output_var = window.add_labeled_combo(top, "输出方式：", config.get("output_mode", "生成新字段"), window.OUTPUT_MODES, 1, 0, 14)
    new_field_var = window.add_labeled_entry(top, "新字段名：", config.get("new_field", "提取结果"), 1, 2, 24)
    unmatched_var = window.add_labeled_combo(top, "未匹配时：", config.get("unmatched_mode", "留空"), window.UNMATCHED_MODES, 2, 0, 14)
    unmatched_fixed_var = window.add_labeled_entry(top, "固定值：", config.get("unmatched_fixed", "未匹配"), 2, 2, 20)
    case_var = tk.BooleanVar(value=config.get("case_sensitive", True))
    strip_var = tk.BooleanVar(value=config.get("strip_result", True))
    ttk.Checkbutton(top, text="区分大小写", variable=case_var).grid(row=3, column=0, sticky=tk.W, padx=4, pady=4)
    ttk.Checkbutton(top, text="结果去除首尾空格", variable=strip_var).grid(row=3, column=1, sticky=tk.W, padx=4, pady=4)
    for var, key in [
        (source_var, "source_field"),
        (method_var, "method"),
        (output_var, "output_mode"),
        (new_field_var, "new_field"),
        (unmatched_var, "unmatched_mode"),
        (unmatched_fixed_var, "unmatched_fixed"),
    ]:
        window.sync_var_to_config(var, config, key)
    window.sync_bool_to_config(case_var, config, "case_sensitive")
    window.sync_bool_to_config(strip_var, config, "strip_result")

    params = ttk.LabelFrame(window.config_frame, text="提取参数：填写当前方式需要的参数即可", padding=8)
    params.pack(fill=tk.X)
    regex_var = window.add_labeled_entry(params, "Python正则：", config.get("regex_pattern", ""), 0, 0, 48)
    group_var = window.add_labeled_entry(params, "分组：", config.get("regex_group", "0"), 0, 2, 8)
    find_all_var = tk.BooleanVar(value=config.get("regex_find_all", False))
    ttk.Checkbutton(params, text="正则提取全部匹配", variable=find_all_var).grid(row=0, column=4, sticky=tk.W, padx=4, pady=4)
    joiner_var = window.add_labeled_entry(params, "全部连接符：", config.get("regex_joiner", ";"), 1, 0, 10)
    start_var = window.add_labeled_entry(params, "起始位置：", config.get("start_pos", "1"), 1, 2, 8)
    len_var = window.add_labeled_entry(params, "提取长度：", config.get("extract_len", "1"), 1, 4, 8)
    base_var = window.add_labeled_combo(params, "位置规则：", config.get("position_base", "从1开始"), ["从1开始", "从0开始"], 2, 0, 10)
    n_var = window.add_labeled_entry(params, "N位：", config.get("n_chars", "1"), 2, 2, 8)
    delimiter_var = window.add_labeled_entry(params, "分隔符：", config.get("delimiter", "-"), 2, 4, 10)
    part_var = window.add_labeled_entry(params, "第几段：", config.get("part_index", "1"), 3, 0, 8)
    ignore_empty_var = tk.BooleanVar(value=config.get("ignore_empty_part", False))
    ttk.Checkbutton(params, text="忽略空段", variable=ignore_empty_var).grid(row=3, column=2, sticky=tk.W, padx=4, pady=4)
    before_var = window.add_labeled_entry(params, "开始关键字：", config.get("before_key", ""), 3, 4, 18)
    after_var = window.add_labeled_entry(params, "结束关键字：", config.get("after_key", ""), 4, 0, 18)
    occ_var = window.add_labeled_entry(params, "第几个匹配：", config.get("between_occurrence", "1"), 4, 2, 8)
    marker_var = window.add_labeled_entry(params, "指定字符：", config.get("marker", "-"), 4, 4, 12)
    find_mode_var = window.add_labeled_combo(params, "查找位置：", config.get("find_mode", "第一次出现"), ["第一次出现", "最后一次出现"], 5, 0, 12)
    prefix_var = window.add_labeled_entry(params, "删除前缀：", config.get("prefix", ""), 5, 2, 16)
    suffix_var = window.add_labeled_entry(params, "删除后缀：", config.get("suffix", ""), 5, 4, 16)
    for var, key in [
        (regex_var, "regex_pattern"),
        (group_var, "regex_group"),
        (joiner_var, "regex_joiner"),
        (start_var, "start_pos"),
        (len_var, "extract_len"),
        (base_var, "position_base"),
        (n_var, "n_chars"),
        (delimiter_var, "delimiter"),
        (part_var, "part_index"),
        (before_var, "before_key"),
        (after_var, "after_key"),
        (occ_var, "between_occurrence"),
        (marker_var, "marker"),
        (find_mode_var, "find_mode"),
        (prefix_var, "prefix"),
        (suffix_var, "suffix"),
    ]:
        window.sync_var_to_config(var, config, key)
    window.sync_bool_to_config(find_all_var, config, "regex_find_all")
    window.sync_bool_to_config(ignore_empty_var, config, "ignore_empty_part")


def build_format_datetime_config(window, config, headers):
    headers = list(headers)
    frame = ttk.LabelFrame(window.config_frame, text="格式规范化 / 日期时间解析节点", padding=8)
    frame.pack(fill=tk.BOTH, expand=True, pady=8)
    ttk.Label(
        frame,
        text="把固定位置、分隔符或常见写法的日期/时间统一成标准格式。例如：260603 → 2026-06-03，20：09 → 20:09。",
        foreground="gray",
        wraplength=1180,
    ).grid(row=0, column=0, columnspan=8, sticky=tk.W, padx=4, pady=(0, 6))

    source_var = window.add_labeled_combo(frame, "源字段：", config.get("source_field", headers[0] if headers else ""), headers, 1, 0, 24, readonly=False)
    parse_type_var = window.add_labeled_combo(frame, "解析为：", config.get("parse_type", "日期"), window.FORMAT_PARSE_TYPES, 1, 2, 14)
    structure_var = window.add_labeled_combo(frame, "输入结构：", config.get("input_structure", "固定位置"), window.FORMAT_INPUT_STRUCTURES, 1, 4, 18)
    strip_var = tk.BooleanVar(value=bool(config.get("strip_value", True)))
    ttk.Checkbutton(frame, text="去除首尾空格", variable=strip_var).grid(row=1, column=6, sticky=tk.W, padx=4, pady=4)

    separate_time_var = tk.BooleanVar(value=bool(config.get("use_separate_time_field", False)))
    ttk.Checkbutton(frame, text="日期时间使用单独时间字段", variable=separate_time_var).grid(row=2, column=0, columnspan=2, sticky=tk.W, padx=4, pady=4)
    time_source_var = window.add_labeled_combo(frame, "时间字段：", config.get("time_source_field", headers[1] if len(headers) > 1 else (headers[0] if headers else "")), headers, 2, 2, 24, readonly=False)

    pos_frame = ttk.LabelFrame(frame, text="固定位置规则（位置从1开始时：260603 = 年1-2、月3-4、日5-6；2009 = 时1-2、分3-4）", padding=6)
    pos_frame.grid(row=3, column=0, columnspan=8, sticky="ew", padx=4, pady=(8, 4))
    base_var = window.add_labeled_combo(pos_frame, "位置规则：", config.get("position_base", "从1开始"), ["从1开始", "从0开始"], 0, 0, 10)
    y_start_var = window.add_labeled_entry(pos_frame, "年起始：", config.get("year_start", "1"), 0, 2, 6)
    y_len_var = window.add_labeled_entry(pos_frame, "年长度：", config.get("year_len", "2"), 0, 4, 6)
    m_start_var = window.add_labeled_entry(pos_frame, "月起始：", config.get("month_start", "3"), 1, 0, 6)
    m_len_var = window.add_labeled_entry(pos_frame, "月长度：", config.get("month_len", "2"), 1, 2, 6)
    d_start_var = window.add_labeled_entry(pos_frame, "日起始：", config.get("day_start", "5"), 1, 4, 6)
    d_len_var = window.add_labeled_entry(pos_frame, "日长度：", config.get("day_len", "2"), 1, 6, 6)
    h_start_var = window.add_labeled_entry(pos_frame, "时起始：", config.get("hour_start", "1"), 2, 0, 6)
    h_len_var = window.add_labeled_entry(pos_frame, "时长度：", config.get("hour_len", "2"), 2, 2, 6)
    min_start_var = window.add_labeled_entry(pos_frame, "分起始：", config.get("minute_start", "3"), 2, 4, 6)
    min_len_var = window.add_labeled_entry(pos_frame, "分长度：", config.get("minute_len", "2"), 2, 6, 6)
    sec_start_var = window.add_labeled_entry(pos_frame, "秒起始：", config.get("second_start", "5"), 3, 0, 6)
    sec_len_var = window.add_labeled_entry(pos_frame, "秒长度：", config.get("second_len", "0"), 3, 2, 6)

    sep_frame = ttk.LabelFrame(frame, text="分隔符 / 自动识别规则", padding=6)
    sep_frame.grid(row=4, column=0, columnspan=8, sticky="ew", padx=4, pady=4)
    date_delim_var = window.add_labeled_combo(sep_frame, "日期分隔符：", config.get("date_delimiter", "自动识别"), ["自动识别", "-", "/", ".", "年/月/日", "自定义"], 0, 0, 12)
    custom_date_var = window.add_labeled_entry(sep_frame, "自定义日期分隔符：", config.get("custom_date_delimiter", "-"), 0, 2, 10)
    time_delim_var = window.add_labeled_combo(sep_frame, "时间分隔符：", config.get("time_delimiter", "自动识别"), ["自动识别", ":", "：", "-", ".", "时/分/秒", "自定义"], 1, 0, 12)
    custom_time_var = window.add_labeled_entry(sep_frame, "自定义时间分隔符：", config.get("custom_time_delimiter", ":"), 1, 2, 10)
    order_var = window.add_labeled_combo(sep_frame, "日期顺序：", config.get("date_order", "年-月-日"), window.FORMAT_DATE_ORDERS, 2, 0, 12)
    year_rule_var = window.add_labeled_combo(sep_frame, "两位年份：", config.get("year_rule", "20xx"), window.FORMAT_YEAR_RULES, 2, 2, 12)
    pivot_var = window.add_labeled_entry(sep_frame, "自动窗口分界：", config.get("auto_window_pivot", "80"), 2, 4, 8)
    ambiguous_policy_var = window.add_labeled_combo(
        sep_frame,
        "月日歧义：",
        config.get("ambiguous_date_policy", "警告"),
        window.DATE_AMBIGUOUS_POLICIES,
        3,
        0,
        12,
    )
    ttk.Label(sep_frame, text="自动窗口示例：00-79→2000-2079，80-99→1980-1999。", foreground="gray").grid(row=4, column=0, columnspan=6, sticky=tk.W, padx=4, pady=(2, 4))

    out_frame = ttk.LabelFrame(frame, text="输出设置", padding=6)
    out_frame.grid(row=5, column=0, columnspan=8, sticky="ew", padx=4, pady=(8, 4))
    output_mode_var = window.add_labeled_combo(out_frame, "输出方式：", config.get("output_mode", "生成新字段"), window.FORMAT_OUTPUT_MODES, 0, 0, 14)
    new_field_var = window.add_labeled_entry(out_frame, "新字段名：", config.get("new_field", "标准日期"), 0, 2, 22)
    date_tpl_var = window.add_labeled_entry(out_frame, "日期模板：", config.get("output_template", "{YYYY}-{MM}-{DD}"), 1, 0, 26)
    time_tpl_var = window.add_labeled_entry(out_frame, "时间模板：", config.get("time_output_template", "{HH}:{mm}"), 1, 2, 22)
    dt_tpl_var = window.add_labeled_entry(out_frame, "日期时间模板：", config.get("datetime_output_template", "{YYYY}-{MM}-{DD} {HH}:{mm}"), 1, 4, 30)
    component_prefix_var = window.add_labeled_entry(out_frame, "多字段前缀：", config.get("component_prefix", "解析"), 2, 0, 12)
    unmatched_var = window.add_labeled_combo(out_frame, "解析失败：", config.get("unmatched_mode", "留空"), window.UNMATCHED_MODES, 2, 2, 12)
    unmatched_fixed_var = window.add_labeled_entry(out_frame, "失败固定值：", config.get("unmatched_fixed", "未匹配"), 2, 4, 14)
    status_var = tk.BooleanVar(value=bool(config.get("output_status", True)))
    ttk.Checkbutton(out_frame, text="生成解析状态字段", variable=status_var).grid(row=3, column=0, sticky=tk.W, padx=4, pady=4)
    status_field_var = window.add_labeled_entry(out_frame, "状态字段名：", config.get("status_field", "格式解析状态"), 3, 2, 20)
    ttk.Label(
        out_frame,
        text="模板可用：{YYYY} {YY} {MM} {M} {DD} {D} {HH} {H} {mm} {m} {ss} {s}。生成多个字段会输出标准值和年/月/日/时/分/秒组件。",
        foreground="gray",
        wraplength=1180,
    ).grid(row=4, column=0, columnspan=8, sticky=tk.W, padx=4, pady=(2, 4))

    for var, key in [
        (source_var, "source_field"),
        (time_source_var, "time_source_field"),
        (parse_type_var, "parse_type"),
        (structure_var, "input_structure"),
        (base_var, "position_base"),
        (y_start_var, "year_start"),
        (y_len_var, "year_len"),
        (m_start_var, "month_start"),
        (m_len_var, "month_len"),
        (d_start_var, "day_start"),
        (d_len_var, "day_len"),
        (h_start_var, "hour_start"),
        (h_len_var, "hour_len"),
        (min_start_var, "minute_start"),
        (min_len_var, "minute_len"),
        (sec_start_var, "second_start"),
        (sec_len_var, "second_len"),
        (date_delim_var, "date_delimiter"),
        (time_delim_var, "time_delimiter"),
        (custom_date_var, "custom_date_delimiter"),
        (custom_time_var, "custom_time_delimiter"),
        (order_var, "date_order"),
        (ambiguous_policy_var, "ambiguous_date_policy"),
        (year_rule_var, "year_rule"),
        (pivot_var, "auto_window_pivot"),
        (output_mode_var, "output_mode"),
        (new_field_var, "new_field"),
        (date_tpl_var, "output_template"),
        (time_tpl_var, "time_output_template"),
        (dt_tpl_var, "datetime_output_template"),
        (component_prefix_var, "component_prefix"),
        (unmatched_var, "unmatched_mode"),
        (unmatched_fixed_var, "unmatched_fixed"),
        (status_field_var, "status_field"),
    ]:
        window.sync_var_to_config(var, config, key)
    window.sync_bool_to_config(strip_var, config, "strip_value")
    window.sync_bool_to_config(separate_time_var, config, "use_separate_time_field")
    window.sync_bool_to_config(status_var, config, "output_status")


def build_current_datetime_column_config(window, config, headers):
    headers = list(headers)
    frame = ttk.LabelFrame(window.config_frame, text="新建日期时间列 / 获取计算机时间节点", padding=8)
    frame.pack(fill=tk.X, pady=8)
    ttk.Label(
        frame,
        text="从当前计算机获取运行时日期时间，并按自定义格式写入新字段或覆盖已有字段。适合生成执行时间、导出时间、处理时间戳。",
        foreground="gray",
        wraplength=1180,
    ).grid(row=0, column=0, columnspan=8, sticky=tk.W, padx=4, pady=(0, 6))

    output_mode_var = window.add_labeled_combo(frame, "输出方式：", config.get("output_mode", "生成新字段"), window.CURRENT_DATETIME_OUTPUT_MODES, 1, 0, 14)
    new_field_var = window.add_labeled_entry(frame, "新字段名：", config.get("new_field", "当前日期时间"), 1, 2, 24)
    target_default = config.get("target_field", headers[0] if headers else "")
    target_var = window.add_labeled_combo(frame, "覆盖字段：", target_default, headers, 1, 4, 24, readonly=False)
    time_mode_var = window.add_labeled_combo(frame, "取时方式：", config.get("time_mode", "整次运行固定同一时间"), window.CURRENT_DATETIME_TIME_MODES, 2, 0, 20)
    format_mode_var = window.add_labeled_combo(frame, "格式模式：", config.get("format_mode", "占位符模板"), window.CURRENT_DATETIME_FORMAT_MODES, 2, 2, 16)
    template_var = window.add_labeled_entry(frame, "占位符模板：", config.get("template", "{YYYY}-{MM}-{DD} {HH}:{mm}:{ss}"), 3, 0, 42)
    strftime_var = window.add_labeled_entry(frame, "strftime格式：", config.get("strftime_template", "%Y-%m-%d %H:%M:%S"), 3, 2, 32)

    preset_frame = ttk.LabelFrame(frame, text="常用格式参考", padding=6)
    preset_frame.grid(row=4, column=0, columnspan=8, sticky="ew", padx=4, pady=(8, 4))
    ttk.Label(
        preset_frame,
        text="占位符：{YYYY} {YY} {MM} {M} {DD} {D} {HH} {H} {mm} {m} {ss} {s} {fff} {ffffff} {timestamp} {unix_ms}。",
        foreground="gray",
        wraplength=1180,
    ).grid(row=0, column=0, columnspan=8, sticky=tk.W, padx=4, pady=(0, 4))

    presets = [
        ("日期时间", "{YYYY}-{MM}-{DD} {HH}:{mm}:{ss}"),
        ("日期", "{YYYY}-{MM}-{DD}"),
        ("时间", "{HH}:{mm}:{ss}"),
        ("紧凑日期时间", "{YYYY}{MM}{DD}_{HH}{mm}{ss}"),
        ("中文日期时间", "{YYYY}年{M}月{D}日 {HH}:{mm}:{ss}"),
        ("Unix秒", "{timestamp}"),
    ]

    def set_template(value):
        template_var.set(value)
        config["template"] = value

    for i, (label, value) in enumerate(presets):
        ttk.Button(preset_frame, text=label, command=lambda v=value: set_template(v)).grid(row=1 + i // 4, column=i % 4, sticky=tk.W, padx=4, pady=3)

    ttk.Label(
        frame,
        text="说明：整次运行固定同一时间 = 所有行写入同一个运行开始时间；逐行实时获取 = 每行写入时重新读取当前时间。Python strftime 使用 %Y-%m-%d %H:%M:%S 这类格式。",
        foreground="gray",
        wraplength=1180,
    ).grid(row=5, column=0, columnspan=8, sticky=tk.W, padx=4, pady=(4, 0))

    for var, key in [
        (output_mode_var, "output_mode"),
        (new_field_var, "new_field"),
        (target_var, "target_field"),
        (time_mode_var, "time_mode"),
        (format_mode_var, "format_mode"),
        (template_var, "template"),
        (strftime_var, "strftime_template"),
    ]:
        window.sync_var_to_config(var, config, key)


def refresh_new_columns_preview(window, config, headers, columns_text_widget, preview_tree):
    config["columns_text"] = columns_text_widget.get("1.0", "end-1c")
    preview_tree.delete(*preview_tree.get_children())
    try:
        specs = window.parse_new_columns_specs(config)
        existing = set(headers)
        temp_headers = list(headers)
        for index, (name, value) in enumerate(specs, start=1):
            status = "将新建"
            final_name = name
            if name in existing or name in temp_headers:
                mode = config.get("conflict_mode", "自动改名")
                if mode == "自动改名":
                    final_name = window.get_unique_header(name, temp_headers)
                    status = f"同名，自动改名为 {final_name}"
                elif mode == "跳过已有字段":
                    status = "同名，将跳过"
                elif mode == "覆盖已有字段":
                    status = "同名，将覆盖整列默认值"
                elif mode == "存在则报错":
                    status = "同名，执行时报错"
            if status.startswith("将新建") or "自动改名" in status:
                temp_headers.append(final_name)
            preview_tree.insert("", tk.END, values=(index, final_name, value, status))
    except Exception as exc:
        preview_tree.insert("", tk.END, values=("错误", "", "", str(exc)))


def set_new_columns_example(window, config, headers, columns_text_widget, preview_tree, text):
    columns_text_widget.delete("1.0", tk.END)
    columns_text_widget.insert("1.0", text)
    refresh_new_columns_preview(window, config, headers, columns_text_widget, preview_tree)


def build_new_columns_config(window, config, headers):
    headers = list(headers)
    frame = ttk.LabelFrame(window.config_frame, text="新建列节点（可一次新建多个字段）", padding=8)
    frame.pack(fill=tk.BOTH, expand=True, pady=8)
    ttk.Label(
        frame,
        text="一次性给当前工作表新增多个字段。每行填写一个字段名；也可写成 字段名=默认值，用于给不同字段设置不同默认值。",
        foreground="gray",
        wraplength=1180,
    ).grid(row=0, column=0, columnspan=8, sticky=tk.W, padx=4, pady=(0, 6))

    help_text = (
        "示例：字段A  /  字段B=默认值B  /  字段C=0    "
        "说明：每行一个字段；选择【按列配置值】时，等号右侧作为该列默认值；未填写等号则使用统一默认值或空值。"
    )
    ttk.Label(frame, text=help_text, foreground="gray", justify=tk.LEFT, wraplength=1300).grid(
        row=1,
        column=0,
        columnspan=8,
        sticky=tk.W,
        padx=4,
        pady=(0, 6),
    )

    ttk.Label(frame, text="新建字段列表：").grid(row=2, column=0, sticky=tk.NW, padx=4, pady=4)
    text_wrap = ttk.Frame(frame)
    text_wrap.grid(row=2, column=1, columnspan=7, sticky="nsew", padx=4, pady=4)
    columns_text_widget = tk.Text(text_wrap, width=90, height=10, wrap="none")
    y_scroll = ttk.Scrollbar(text_wrap, orient=tk.VERTICAL, command=columns_text_widget.yview)
    columns_text_widget.configure(yscrollcommand=y_scroll.set)
    columns_text_widget.grid(row=0, column=0, sticky="nsew")
    y_scroll.grid(row=0, column=1, sticky="ns")
    text_wrap.rowconfigure(0, weight=1)
    text_wrap.columnconfigure(0, weight=1)
    columns_text_widget.insert("1.0", str(config.get("columns_text", "新字段1\n新字段2") or ""))

    def sync_columns_text(event=None):
        config["columns_text"] = columns_text_widget.get("1.0", "end-1c")

    columns_text_widget.bind("<KeyRelease>", sync_columns_text)
    columns_text_widget.bind("<FocusOut>", sync_columns_text)

    value_mode_var = window.add_labeled_combo(frame, "填充值模式：", config.get("value_mode", "统一默认值"), window.NEW_COLUMNS_VALUE_MODES, 3, 0, 16)
    default_value_var = window.add_labeled_entry(frame, "统一默认值：", config.get("default_value", ""), 3, 2, 28)
    conflict_var = window.add_labeled_combo(frame, "同名字段处理：", config.get("conflict_mode", "自动改名"), window.NEW_COLUMNS_CONFLICT_MODES, 3, 4, 16)

    strip_var = tk.BooleanVar(value=bool(config.get("strip_column_name", True)))
    allow_empty_var = tk.BooleanVar(value=bool(config.get("allow_empty_name", False)))
    ttk.Checkbutton(frame, text="字段名前后去空格", variable=strip_var).grid(row=4, column=0, columnspan=2, sticky=tk.W, padx=4, pady=4)
    ttk.Checkbutton(frame, text="允许空字段名自动命名", variable=allow_empty_var).grid(row=4, column=2, columnspan=3, sticky=tk.W, padx=4, pady=4)
    ttk.Label(
        frame,
        text="同名字段处理：自动改名会生成 字段_2；跳过已有字段不会新增；覆盖已有字段会把该列整列写成默认值；存在则报错用于防止误覆盖。",
        foreground="gray",
        wraplength=1300,
    ).grid(row=5, column=0, columnspan=8, sticky=tk.W, padx=4, pady=(8, 4))

    preview_frame = ttk.LabelFrame(frame, text="字段解析预览", padding=6)
    preview_frame.grid(row=6, column=0, columnspan=8, sticky="nsew", padx=4, pady=(8, 4))
    preview_tree = ttk.Treeview(preview_frame, columns=("序号", "字段名", "默认值", "状态"), show="headings", height=7)
    for col, width in [("序号", 70), ("字段名", 260), ("默认值", 320), ("状态", 360)]:
        preview_tree.heading(col, text=col)
        preview_tree.column(col, width=width, anchor=tk.W, stretch=False)
    preview_y = ttk.Scrollbar(preview_frame, orient=tk.VERTICAL, command=preview_tree.yview)
    preview_tree.configure(yscrollcommand=preview_y.set)
    preview_tree.grid(row=0, column=0, sticky="nsew")
    preview_y.grid(row=0, column=1, sticky="ns")
    preview_frame.rowconfigure(0, weight=1)
    preview_frame.columnconfigure(0, weight=1)

    btns = ttk.Frame(frame)
    btns.grid(row=7, column=0, columnspan=8, sticky=tk.W, padx=4, pady=6)
    refresh_preview = lambda: refresh_new_columns_preview(window, config, headers, columns_text_widget, preview_tree)
    ttk.Button(btns, text="刷新字段预览", command=refresh_preview).pack(side=tk.LEFT, padx=4)
    ttk.Button(
        btns,
        text="示例：3个空列",
        command=lambda: set_new_columns_example(window, config, headers, columns_text_widget, preview_tree, "字段A\n字段B\n字段C"),
    ).pack(side=tk.LEFT, padx=4)
    ttk.Button(
        btns,
        text="示例：带默认值",
        command=lambda: set_new_columns_example(window, config, headers, columns_text_widget, preview_tree, "处理状态=未处理\n备注=\n数量=0"),
    ).pack(side=tk.LEFT, padx=4)

    for var, key in [
        (value_mode_var, "value_mode"),
        (default_value_var, "default_value"),
        (conflict_var, "conflict_mode"),
    ]:
        window.sync_var_to_config(var, config, key)
    window.sync_bool_to_config(strip_var, config, "strip_column_name")
    window.sync_bool_to_config(allow_empty_var, config, "allow_empty_name")
    frame.rowconfigure(5, weight=1)
    frame.columnconfigure(1, weight=1)
    refresh_preview()
