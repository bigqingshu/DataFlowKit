# -*- coding: utf-8 -*-
"""Tkinter UI helpers for the numeric-column workflow node configuration."""

import tkinter as tk
from tkinter import ttk


NUMERIC_OPERATION_VALUES = ["加", "减", "乘", "除"]
NUMERIC_OPERAND_SOURCE_VALUES = ["固定值", "行号", "行号+N", "序号", "另一列同行数值"]
NUMERIC_OUTPUT_MODE_VALUES = ["生成新字段", "覆盖原字段", "写入已有字段"]
NUMERIC_DECIMAL_PLACE_VALUES = ["自动", "0", "1", "2", "3", "4", "5", "6"]
NUMERIC_NON_NUMBER_POLICY_VALUES = ["留空", "保留原值", "填写固定值", "标记为计算失败"]
NUMERIC_DIVIDE_ZERO_POLICY_VALUES = ["留空", "保留原值", "填写固定值", "标记为除零错误"]
NUMERIC_RANGE_MODE_VALUES = ["全部行", "指定起止行", "填充到参考列数据边界"]


def get_numeric_column_default_fields(config, headers):
    headers = list(headers)
    first = headers[0] if headers else ""
    second = headers[1] if len(headers) > 1 else first
    target_default = config.get("target_field") if config.get("target_field") in headers else (config.get("target_field") or first)
    operand_field_default = config.get("operand_field") if config.get("operand_field") in headers else (config.get("operand_field") or second)
    ref_default = config.get("reference_field") if config.get("reference_field") in headers else (config.get("reference_field") or first)
    return {
        "target_default": target_default,
        "operand_field_default": operand_field_default,
        "ref_default": ref_default,
    }


def build_numeric_column_header(frame):
    ttk.Label(
        frame,
        text="对指定列的数字批量加、减、乘、除。结果可生成新字段、覆盖原字段或写入已有字段；运算值可来自固定值、行号、序号或另一列同行值。",
        foreground="gray",
        wraplength=1050,
    ).grid(row=0, column=0, columnspan=8, sticky=tk.W, padx=4, pady=(0, 6))


def build_numeric_column_target_section(window, frame, config, headers, defaults):
    target_var = window.add_labeled_combo(
        frame,
        "目标字段：",
        defaults["target_default"],
        headers,
        1,
        0,
        24,
        readonly=False,
    )
    op_var = window.add_labeled_combo(
        frame,
        "运算方式：",
        config.get("operation", "加"),
        NUMERIC_OPERATION_VALUES,
        1,
        2,
        12,
    )
    operand_source_var = window.add_labeled_combo(
        frame,
        "运算值来源：",
        config.get("operand_source", "固定值"),
        NUMERIC_OPERAND_SOURCE_VALUES,
        1,
        4,
        18,
    )
    window.sync_var_to_config(target_var, config, "target_field")
    window.sync_var_to_config(op_var, config, "operation")
    window.sync_var_to_config(operand_source_var, config, "operand_source")
    return {
        "target_var": target_var,
        "op_var": op_var,
        "operand_source_var": operand_source_var,
    }


def build_numeric_column_operand_section(window, frame, config, headers, defaults):
    operand_value_var = window.add_labeled_entry(frame, "固定值：", config.get("operand_value", "1"), 2, 0, 12)
    operand_field_var = window.add_labeled_combo(
        frame,
        "同行来源字段：",
        defaults["operand_field_default"],
        headers,
        2,
        2,
        24,
        readonly=False,
    )
    row_offset_var = window.add_labeled_entry(frame, "N值：", config.get("row_offset", "0"), 2, 4, 10)
    seq_start_var = window.add_labeled_entry(frame, "序号起始：", config.get("sequence_start", "1"), 3, 0, 12)
    seq_step_var = window.add_labeled_entry(frame, "序号步长：", config.get("sequence_step", "1"), 3, 2, 12)
    for var, key in [
        (operand_value_var, "operand_value"),
        (operand_field_var, "operand_field"),
        (row_offset_var, "row_offset"),
        (seq_start_var, "sequence_start"),
        (seq_step_var, "sequence_step"),
    ]:
        window.sync_var_to_config(var, config, key)
    return {
        "operand_value_var": operand_value_var,
        "operand_field_var": operand_field_var,
        "row_offset_var": row_offset_var,
        "seq_start_var": seq_start_var,
        "seq_step_var": seq_step_var,
    }


def build_numeric_column_output_section(window, frame, config, headers, defaults):
    output_mode_var = window.add_labeled_combo(
        frame,
        "输出方式：",
        config.get("output_mode", "生成新字段"),
        NUMERIC_OUTPUT_MODE_VALUES,
        4,
        0,
        16,
    )
    target_default = defaults["target_default"]
    output_field_default = config.get("output_field", f"{target_default}_计算结果" if target_default else "计算结果")
    output_field_var = window.add_labeled_combo(
        frame,
        "输出字段：",
        output_field_default,
        headers,
        4,
        2,
        24,
        readonly=False,
    )
    decimal_var = window.add_labeled_combo(
        frame,
        "小数位：",
        config.get("decimal_places", "自动"),
        NUMERIC_DECIMAL_PLACE_VALUES,
        4,
        4,
        10,
    )
    window.sync_var_to_config(output_mode_var, config, "output_mode")
    window.sync_var_to_config(output_field_var, config, "output_field")
    window.sync_var_to_config(decimal_var, config, "decimal_places")
    return {
        "output_mode_var": output_mode_var,
        "output_field_var": output_field_var,
        "decimal_var": decimal_var,
    }


def build_numeric_column_fallback_section(window, frame, config):
    non_number_var = window.add_labeled_combo(
        frame,
        "非数字处理：",
        config.get("non_number_policy", "留空"),
        NUMERIC_NON_NUMBER_POLICY_VALUES,
        5,
        0,
        16,
    )
    non_number_fixed_var = window.add_labeled_entry(frame, "非数字固定值：", config.get("non_number_fixed", ""), 5, 2, 18)
    div_zero_var = window.add_labeled_combo(
        frame,
        "除零处理：",
        config.get("divide_zero_policy", "留空"),
        NUMERIC_DIVIDE_ZERO_POLICY_VALUES,
        5,
        4,
        16,
    )
    div_zero_fixed_var = window.add_labeled_entry(frame, "除零固定值：", config.get("divide_zero_fixed", ""), 5, 6, 18)
    for var, key in [
        (non_number_var, "non_number_policy"),
        (non_number_fixed_var, "non_number_fixed"),
        (div_zero_var, "divide_zero_policy"),
        (div_zero_fixed_var, "divide_zero_fixed"),
    ]:
        window.sync_var_to_config(var, config, key)
    return {
        "non_number_var": non_number_var,
        "non_number_fixed_var": non_number_fixed_var,
        "div_zero_var": div_zero_var,
        "div_zero_fixed_var": div_zero_fixed_var,
    }


def build_numeric_column_range_section(window, frame, config, headers, defaults):
    range_var = window.add_labeled_combo(
        frame,
        "处理范围：",
        config.get("range_mode", "全部行"),
        NUMERIC_RANGE_MODE_VALUES,
        6,
        0,
        18,
    )
    start_row_var = window.add_labeled_entry(frame, "起始行号：", config.get("start_row", "1"), 6, 2, 10)
    end_row_var = window.add_labeled_entry(frame, "结束行号：", config.get("end_row", "1"), 6, 4, 10)
    ref_var = window.add_labeled_combo(
        frame,
        "参考边界列：",
        defaults["ref_default"],
        headers,
        6,
        6,
        24,
        readonly=False,
    )
    for var, key in [
        (range_var, "range_mode"),
        (start_row_var, "start_row"),
        (end_row_var, "end_row"),
        (ref_var, "reference_field"),
    ]:
        window.sync_var_to_config(var, config, key)
    return {
        "range_var": range_var,
        "start_row_var": start_row_var,
        "end_row_var": end_row_var,
        "ref_var": ref_var,
    }


def build_numeric_column_footer(frame):
    ttk.Label(
        frame,
        text="提示：行号按 1、2、3 计算；序号可自定义起始值和步长；除法遇到 0 会按除零处理规则输出。",
        foreground="gray",
        wraplength=1050,
    ).grid(row=7, column=0, columnspan=8, sticky=tk.W, padx=4, pady=(6, 0))


def build_numeric_column_config(window, config, headers):
    """Build the numeric-column node configuration UI."""
    frame = ttk.LabelFrame(window.config_frame, text="列数字运算节点", padding=8)
    frame.pack(fill=tk.BOTH, expand=True, pady=8)
    headers = list(headers)
    defaults = get_numeric_column_default_fields(config, headers)

    build_numeric_column_header(frame)
    build_numeric_column_target_section(window, frame, config, headers, defaults)
    build_numeric_column_operand_section(window, frame, config, headers, defaults)
    build_numeric_column_output_section(window, frame, config, headers, defaults)
    build_numeric_column_fallback_section(window, frame, config)
    build_numeric_column_range_section(window, frame, config, headers, defaults)
    build_numeric_column_footer(frame)
