# -*- coding: utf-8 -*-
"""Tkinter UI helpers for ordinary table-edit workflow node configurations."""

import tkinter as tk
from tkinter import ttk


START_ROW_MODE_VALUES = ["手动指定起始行", "目标列最后数据行之后", "参考列最后数据行之后", "整体表格最后行之后"]
FILL_DIRECTION_VALUES = ["向下", "向上", "向右", "向左"]
FILL_VALUE_SOURCE_VALUES = ["手动输入值", "指定单元格值", "同行来源字段", "来源列完整结构", "循环源列填充"]
AREA_VALUE_SOURCE_VALUES = [
    "手动输入值",
    "指定单元格值",
    "同行来源字段",
    "来源列完整结构",
    "循环源列填充",
    "指定行多字段取值",
    "来源区域完整复制",
]
SOURCE_RANGE_MODE_VALUES = ["来源列数据边界", "整体表格数据边界", "手动指定范围"]
SOURCE_EMPTY_MODE_VALUES = ["跳过空值", "保留空值参与循环", "替换为空值占位符"]
FILL_END_MODE_VALUES = [
    "固定数量",
    "遇到已有数据停止",
    "填充到数据边界",
    "填充到参考列数据边界",
    "填充到指定行",
    "填充到指定列",
    "填充到空行前",
]
OVERWRITE_RULE_VALUES = ["覆盖所有目标单元格", "只填充空单元格", "遇到已有数据停止", "不覆盖已有数据，只跳过"]


def _sync_vars(window, config, pairs):
    for var, key in pairs:
        window.sync_var_to_config(var, config, key)


def _header_default(config, key, headers, fallback=""):
    value = config.get(key)
    if value in headers:
        return value
    return fallback


def build_copy_column_config(window, config, headers):
    frame = ttk.LabelFrame(window.config_frame, text="复制列节点", padding=8)
    frame.pack(fill=tk.BOTH, expand=True, pady=8)
    ttk.Label(
        frame,
        text="把一个字段复制为新字段，或覆盖到已有字段。适合在批量替换前备份原列。",
        foreground="gray",
    ).grid(row=0, column=0, columnspan=6, sticky=tk.W, padx=4, pady=(0, 6))
    headers = list(headers)
    source_default = config.get("source_field") if config.get("source_field") in headers else (headers[0] if headers else "")
    target_default = config.get("target_field") if config.get("target_field") in headers else source_default
    source_var = window.add_labeled_combo(frame, "源字段：", source_default, headers, 1, 0, 24, readonly=False)
    mode_var = window.add_labeled_combo(frame, "输出方式：", config.get("output_mode", "生成新字段"), ["生成新字段", "覆盖已有字段"], 1, 2, 16)
    new_field_var = window.add_labeled_entry(frame, "新字段名：", config.get("new_field", "复制列"), 2, 0, 24)
    target_var = window.add_labeled_combo(frame, "覆盖目标字段：", target_default, headers, 2, 2, 24, readonly=False)
    _sync_vars(
        window,
        config,
        [
            (source_var, "source_field"),
            (mode_var, "output_mode"),
            (new_field_var, "new_field"),
            (target_var, "target_field"),
        ],
    )
    trim_var = tk.BooleanVar(value=bool(config.get("trim_value", False)))
    ttk.Checkbutton(frame, text="复制前去除首尾空格", variable=trim_var).grid(row=3, column=0, columnspan=2, sticky=tk.W, padx=4, pady=4)
    window.sync_bool_to_config(trim_var, config, "trim_value")
    empty_var = window.add_labeled_entry(frame, "空值默认值：", config.get("empty_default", ""), 3, 2, 20)
    window.sync_var_to_config(empty_var, config, "empty_default")


def build_copy_row_config(window, config, headers):
    frame = ttk.LabelFrame(window.config_frame, text="复制行节点", padding=8)
    frame.pack(fill=tk.BOTH, expand=True, pady=8)
    ttk.Label(
        frame,
        text="复制指定行 N 次，并插入到表尾、原行下方或指定行前后。行号从 1 开始。",
        foreground="gray",
    ).grid(row=0, column=0, columnspan=6, sticky=tk.W, padx=4, pady=(0, 6))
    source_row_var = window.add_labeled_entry(frame, "源行号：", config.get("source_row", "1"), 1, 0, 10)
    count_var = window.add_labeled_entry(frame, "复制次数：", config.get("copy_count", "1"), 1, 2, 10)
    mode_var = window.add_labeled_combo(frame, "插入位置：", config.get("insert_mode", "表尾"), ["表尾", "原行下方", "指定行前", "指定行后"], 2, 0, 14)
    insert_row_var = window.add_labeled_entry(frame, "指定行号：", config.get("insert_row", "1"), 2, 2, 10)
    _sync_vars(
        window,
        config,
        [
            (source_row_var, "source_row"),
            (count_var, "copy_count"),
            (mode_var, "insert_mode"),
            (insert_row_var, "insert_row"),
        ],
    )


def build_delete_rows_config(window, config, headers):
    frame = ttk.LabelFrame(window.config_frame, text="删除行节点", padding=8)
    frame.pack(fill=tk.BOTH, expand=True, pady=8)
    ttk.Label(
        frame,
        text="按行号、行号范围、条件或空行规则删除数据行。行号从 1 开始，执行前建议先预览完整计划。",
        foreground="gray",
        wraplength=1050,
    ).grid(row=0, column=0, columnspan=8, sticky=tk.W, padx=4, pady=(0, 6))

    headers = list(headers)
    first = headers[0] if headers else ""
    mode_var = window.add_labeled_combo(
        frame,
        "删除方式：",
        config.get("delete_mode", "按行号列表"),
        ["按行号列表", "按行号范围", "按条件删除", "删除空行"],
        1,
        0,
        18,
    )
    row_spec_var = window.add_labeled_entry(frame, "行号列表：", config.get("row_spec", "1"), 1, 2, 28)
    ttk.Label(frame, text="示例：1,3,5-8", foreground="gray").grid(row=1, column=4, columnspan=2, sticky=tk.W, padx=4)

    start_var = window.add_labeled_entry(frame, "起始行：", config.get("start_row", "1"), 2, 0, 10)
    end_var = window.add_labeled_entry(frame, "结束行：", config.get("end_row", "1"), 2, 2, 10)

    cond_field_default = config.get("condition_field") if config.get("condition_field") in headers else (config.get("condition_field") or first)
    cond_field_var = window.add_labeled_combo(frame, "条件字段：", cond_field_default, headers, 3, 0, 24, readonly=False)
    cond_op_var = window.add_labeled_combo(frame, "条件操作：", config.get("condition_op", "包含"), window.FILTER_OPS, 3, 2, 14)
    cond_value_var = window.add_labeled_entry(frame, "条件值：", config.get("condition_value", ""), 3, 4, 24)

    case_var = tk.BooleanVar(value=bool(config.get("case_sensitive", True)))
    ttk.Checkbutton(frame, text="条件判断区分大小写", variable=case_var).grid(row=4, column=0, columnspan=2, sticky=tk.W, padx=4, pady=4)

    empty_mode_var = window.add_labeled_combo(frame, "空行判断：", config.get("empty_mode", "整行为空"), ["整行为空", "指定字段为空"], 5, 0, 16)
    empty_field_default = config.get("empty_field") if config.get("empty_field") in headers else (config.get("empty_field") or first)
    empty_field_var = window.add_labeled_combo(frame, "空字段：", empty_field_default, headers, 5, 2, 24, readonly=False)

    ttk.Label(
        frame,
        text="说明：按条件删除会删除满足条件的整行；删除空行可按整行为空或指定字段为空判断。",
        foreground="gray",
        wraplength=1050,
    ).grid(row=6, column=0, columnspan=8, sticky=tk.W, padx=4, pady=(8, 4))

    _sync_vars(
        window,
        config,
        [
            (mode_var, "delete_mode"),
            (row_spec_var, "row_spec"),
            (start_var, "start_row"),
            (end_var, "end_row"),
            (cond_field_var, "condition_field"),
            (cond_op_var, "condition_op"),
            (cond_value_var, "condition_value"),
            (empty_mode_var, "empty_mode"),
            (empty_field_var, "empty_field"),
        ],
    )
    window.sync_bool_to_config(case_var, config, "case_sensitive")


def build_fill_value_config(window, config, headers):
    frame = ttk.LabelFrame(window.config_frame, text="填充值节点", padding=8)
    frame.pack(fill=tk.BOTH, expand=True, pady=8)
    ttk.Label(
        frame,
        text="从指定字段/行开始，把手动值、指定单元格值或同行来源字段值按方向填充。支持整体数据边界和参考列数据边界。",
        foreground="gray",
        wraplength=1050,
    ).grid(row=0, column=0, columnspan=8, sticky=tk.W, padx=4, pady=(0, 6))
    headers = list(headers)
    first = headers[0] if headers else ""
    target_default = config.get("target_field") if config.get("target_field") in headers else (config.get("target_field") or first)
    target_var = window.add_labeled_combo(frame, "目标字段：", target_default, headers, 1, 0, 24, readonly=False)
    start_row_mode_var = window.add_labeled_combo(frame, "起始位置：", config.get("start_row_mode", "手动指定起始行"), START_ROW_MODE_VALUES, 1, 2, 20)
    start_row_var = window.add_labeled_entry(frame, "起始行号：", config.get("start_row", "1"), 1, 4, 10)
    direction_var = window.add_labeled_combo(frame, "填充方向：", config.get("direction", "向下"), FILL_DIRECTION_VALUES, 1, 6, 10)
    _sync_vars(
        window,
        config,
        [
            (target_var, "target_field"),
            (start_row_mode_var, "start_row_mode"),
            (start_row_var, "start_row"),
            (direction_var, "direction"),
        ],
    )

    source_var = window.add_labeled_combo(frame, "填充值来源：", config.get("value_source", "手动输入值"), FILL_VALUE_SOURCE_VALUES, 2, 0, 18)
    manual_var = window.add_labeled_entry(frame, "手动输入值：", config.get("manual_value", ""), 2, 2, 24)
    src_field_default = config.get("source_field") if config.get("source_field") in headers else first
    src_field_var = window.add_labeled_combo(frame, "取值/来源字段：", src_field_default, headers, 3, 0, 24, readonly=False)
    src_row_var = window.add_labeled_entry(frame, "取值行号：", config.get("source_row", "1"), 3, 2, 10)
    source_range_var = window.add_labeled_combo(frame, "来源范围：", config.get("source_range_mode", "来源列数据边界"), SOURCE_RANGE_MODE_VALUES, 3, 4, 18)
    source_start_var = window.add_labeled_entry(frame, "来源起始行：", config.get("source_start_row", "1"), 4, 0, 10)
    source_end_var = window.add_labeled_entry(frame, "来源结束行：", config.get("source_end_row", "1"), 4, 2, 10)
    _sync_vars(
        window,
        config,
        [
            (source_var, "value_source"),
            (manual_var, "manual_value"),
            (src_field_var, "source_field"),
            (src_row_var, "source_row"),
            (source_range_var, "source_range_mode"),
            (source_start_var, "source_start_row"),
            (source_end_var, "source_end_row"),
        ],
    )

    cycle_mode_var = window.add_labeled_combo(frame, "循环方式：", config.get("cycle_mode", "从头循环"), ["从头循环"], 5, 0, 14)
    source_empty_mode_var = window.add_labeled_combo(frame, "来源空值：", config.get("source_empty_mode", "跳过空值"), SOURCE_EMPTY_MODE_VALUES, 5, 2, 18)
    source_empty_placeholder_var = window.add_labeled_entry(frame, "空值占位符：", config.get("source_empty_placeholder", ""), 5, 4, 16)
    _sync_vars(
        window,
        config,
        [
            (cycle_mode_var, "cycle_mode"),
            (source_empty_mode_var, "source_empty_mode"),
            (source_empty_placeholder_var, "source_empty_placeholder"),
        ],
    )

    end_var = window.add_labeled_combo(frame, "结束条件：", config.get("end_mode", "填充到数据边界"), FILL_END_MODE_VALUES, 6, 0, 20)
    count_var = window.add_labeled_entry(frame, "固定数量：", config.get("count", "1"), 6, 2, 10)
    end_row_var = window.add_labeled_entry(frame, "结束行号：", config.get("end_row", "1"), 6, 4, 10)
    end_field_default = config.get("end_field") if config.get("end_field") in headers else target_default
    end_field_var = window.add_labeled_combo(frame, "结束字段：", end_field_default, headers, 7, 0, 24, readonly=False)
    ref_field_default = config.get("reference_field") if config.get("reference_field") in headers else (first or target_default)
    ref_field_var = window.add_labeled_combo(frame, "参考边界列：", ref_field_default, headers, 7, 2, 24, readonly=False)
    overwrite_var = window.add_labeled_combo(frame, "覆盖规则：", config.get("overwrite_rule", "只填充空单元格"), OVERWRITE_RULE_VALUES, 8, 0, 20)
    ttk.Label(
        frame,
        text="提示：选择“来源列完整结构”时，会把来源字段的一整段数据按顺序追加/填充到目标字段；选择“循环源列填充”时，会把来源字段的有效值作为循环周期，重复填充到参考列或表格边界。",
        foreground="gray",
        wraplength=1050,
    ).grid(row=9, column=0, columnspan=8, sticky=tk.W, padx=4, pady=(8, 2))
    _sync_vars(
        window,
        config,
        [
            (end_var, "end_mode"),
            (count_var, "count"),
            (end_row_var, "end_row"),
            (end_field_var, "end_field"),
            (ref_field_var, "reference_field"),
            (overwrite_var, "overwrite_rule"),
        ],
    )


def build_sequence_fill_config(window, config, headers):
    frame = ttk.LabelFrame(window.config_frame, text="序列填充节点", padding=8)
    frame.pack(fill=tk.BOTH, expand=True, pady=8)
    ttk.Label(
        frame,
        text="类似 Excel 下拉填充数字序列。步长为正数递增，负数递减；可按参考列/来源列数量生成。",
        foreground="gray",
        wraplength=1050,
    ).grid(row=0, column=0, columnspan=8, sticky=tk.W, padx=4, pady=(0, 6))
    headers = list(headers)
    first = headers[0] if headers else ""
    target_default = config.get("target_field") if config.get("target_field") in headers else (config.get("target_field") or first)
    target_var = window.add_labeled_combo(frame, "目标字段：", target_default, headers, 1, 0, 24, readonly=False)
    start_row_mode_var = window.add_labeled_combo(frame, "起始位置：", config.get("start_row_mode", "手动指定起始行"), START_ROW_MODE_VALUES, 1, 2, 20)
    start_row_var = window.add_labeled_entry(frame, "起始行号：", config.get("start_row", "1"), 1, 4, 10)
    direction_var = window.add_labeled_combo(frame, "填充方向：", config.get("direction", "向下"), FILL_DIRECTION_VALUES, 1, 6, 10)
    start_var = window.add_labeled_entry(frame, "起始值：", config.get("start_value", "1"), 2, 0, 12)
    step_var = window.add_labeled_entry(frame, "步长：", config.get("step", "1"), 2, 2, 12)
    zero_var = window.add_labeled_entry(frame, "补零位数：", config.get("zero_pad", "0"), 2, 4, 10)
    prefix_var = window.add_labeled_entry(frame, "前缀：", config.get("prefix", ""), 3, 0, 18)
    suffix_var = window.add_labeled_entry(frame, "后缀：", config.get("suffix", ""), 3, 2, 18)
    count_source_var = window.add_labeled_combo(
        frame,
        "数量来源：",
        config.get("count_source_mode", "使用结束条件"),
        ["使用结束条件", "整体表格数据行数", "指定参考列数据数量", "来源列数据数量"],
        4,
        0,
        18,
    )
    end_var = window.add_labeled_combo(frame, "结束条件：", config.get("end_mode", "填充到数据边界"), FILL_END_MODE_VALUES, 5, 0, 20)
    count_var = window.add_labeled_entry(frame, "固定数量：", config.get("count", "1"), 5, 2, 10)
    end_row_var = window.add_labeled_entry(frame, "结束行号：", config.get("end_row", "1"), 5, 4, 10)
    end_field_default = config.get("end_field") if config.get("end_field") in headers else target_default
    end_field_var = window.add_labeled_combo(frame, "结束字段：", end_field_default, headers, 6, 0, 24, readonly=False)
    ref_field_default = config.get("reference_field") if config.get("reference_field") in headers else (first or target_default)
    ref_field_var = window.add_labeled_combo(frame, "参考边界列：", ref_field_default, headers, 6, 2, 24, readonly=False)
    src_field_default = config.get("source_field") if config.get("source_field") in headers else first
    src_field_var = window.add_labeled_combo(frame, "来源列：", src_field_default, headers, 6, 4, 24, readonly=False)
    overwrite_var = window.add_labeled_combo(frame, "覆盖规则：", config.get("overwrite_rule", "覆盖所有目标单元格"), OVERWRITE_RULE_VALUES, 7, 0, 20)
    _sync_vars(
        window,
        config,
        [
            (target_var, "target_field"),
            (start_row_mode_var, "start_row_mode"),
            (start_row_var, "start_row"),
            (direction_var, "direction"),
            (start_var, "start_value"),
            (step_var, "step"),
            (zero_var, "zero_pad"),
            (prefix_var, "prefix"),
            (suffix_var, "suffix"),
            (count_source_var, "count_source_mode"),
            (src_field_var, "source_field"),
            (end_var, "end_mode"),
            (count_var, "count"),
            (end_row_var, "end_row"),
            (end_field_var, "end_field"),
            (ref_field_var, "reference_field"),
            (overwrite_var, "overwrite_rule"),
        ],
    )


def update_area_source_widgets(source_var, src_end_label, src_end_combo, multi_dir_label, multi_dir_combo):
    current_source = source_var.get()
    if current_source in ["循环源列填充", "指定行多字段取值", "来源区域完整复制"]:
        src_end_label.grid()
        src_end_combo.grid()
    else:
        src_end_label.grid_remove()
        src_end_combo.grid_remove()

    if current_source == "指定行多字段取值":
        multi_dir_label.grid()
        multi_dir_combo.grid()
    else:
        multi_dir_label.grid_remove()
        multi_dir_combo.grid_remove()


def build_area_fill_config(window, config, headers):
    frame = ttk.LabelFrame(window.config_frame, text="区域填充节点", padding=8)
    frame.pack(fill=tk.BOTH, expand=True, pady=8)
    ttk.Label(
        frame,
        text="对矩形区域批量填充固定值、指定单元格值或同行来源字段值。结束行可手动指定，也可跟随整体表格或参考列数据边界。",
        foreground="gray",
        wraplength=1050,
    ).grid(row=0, column=0, columnspan=8, sticky=tk.W, padx=4, pady=(0, 6))
    headers = list(headers)
    first = headers[0] if headers else ""
    second = headers[1] if len(headers) > 1 else first
    start_field_default = _header_default(config, "start_field", headers, first)
    end_field_default = _header_default(config, "end_field", headers, second)
    sf_var = window.add_labeled_combo(frame, "起始字段：", start_field_default, headers, 1, 0, 24, readonly=False)
    ef_var = window.add_labeled_combo(frame, "结束字段：", end_field_default, headers, 1, 2, 24, readonly=False)
    start_row_mode_var = window.add_labeled_combo(frame, "起始位置：", config.get("start_row_mode", "手动指定起始行"), START_ROW_MODE_VALUES, 2, 0, 20)
    sr_var = window.add_labeled_entry(frame, "起始行号：", config.get("start_row", "1"), 2, 2, 10)
    er_var = window.add_labeled_entry(frame, "结束行号：", config.get("end_row", "1"), 2, 4, 10)
    end_mode_var = window.add_labeled_combo(frame, "结束行来源：", config.get("end_row_mode", "手动指定结束行"), ["手动指定结束行", "整体表格数据边界", "指定参考列数据边界"], 3, 0, 18)
    ref_field_default = _header_default(config, "reference_field", headers, first)
    ref_field_var = window.add_labeled_combo(frame, "参考边界列：", ref_field_default, headers, 3, 2, 24, readonly=False)
    source_var = window.add_labeled_combo(frame, "填充值来源：", config.get("value_source", "手动输入值"), AREA_VALUE_SOURCE_VALUES, 4, 0, 20)
    manual_var = window.add_labeled_entry(frame, "手动输入值：", config.get("manual_value", ""), 4, 2, 24)
    src_field_default = _header_default(config, "source_field", headers, first)
    source_end_default = _header_default(config, "source_end_field", headers, end_field_default)
    src_field_var = window.add_labeled_combo(frame, "取值/来源字段：", src_field_default, headers, 5, 0, 20, readonly=False)

    src_end_label = ttk.Label(frame, text="取值/结束字段：")
    src_end_var = tk.StringVar(value=source_end_default)
    src_end_combo = ttk.Combobox(frame, textvariable=src_end_var, values=headers, width=20, state="normal")
    src_end_label.grid(row=5, column=2, sticky=tk.W, padx=4, pady=4)
    src_end_combo.grid(row=5, column=3, sticky=tk.W, padx=4, pady=4)

    src_row_var = window.add_labeled_entry(frame, "取值行号：", config.get("source_row", "1"), 5, 4, 10)
    multi_dir_label = ttk.Label(frame, text="多字段填充方向：")
    multi_dir_var = tk.StringVar(value=config.get("multi_field_fill_direction", "横向填充"))
    multi_dir_combo = ttk.Combobox(frame, textvariable=multi_dir_var, values=["横向填充", "纵向填充"], width=14, state="readonly")
    multi_dir_label.grid(row=5, column=6, sticky=tk.W, padx=4, pady=4)
    multi_dir_combo.grid(row=5, column=7, sticky=tk.W, padx=4, pady=4)
    source_var.trace_add(
        "write",
        lambda *_: update_area_source_widgets(source_var, src_end_label, src_end_combo, multi_dir_label, multi_dir_combo),
    )
    update_area_source_widgets(source_var, src_end_label, src_end_combo, multi_dir_label, multi_dir_combo)

    source_range_var = window.add_labeled_combo(frame, "来源范围：", config.get("source_range_mode", "来源列数据边界"), SOURCE_RANGE_MODE_VALUES, 6, 0, 18)
    source_start_var = window.add_labeled_entry(frame, "来源起始行：", config.get("source_start_row", "1"), 6, 2, 10)
    source_end_var = window.add_labeled_entry(frame, "来源结束行：", config.get("source_end_row", "1"), 6, 4, 10)
    cycle_mode_var = window.add_labeled_combo(frame, "循环方式：", config.get("cycle_mode", "从头循环"), ["从头循环"], 7, 0, 14)
    source_empty_mode_var = window.add_labeled_combo(frame, "来源空值：", config.get("source_empty_mode", "跳过空值"), SOURCE_EMPTY_MODE_VALUES, 7, 2, 18)
    source_empty_placeholder_var = window.add_labeled_entry(frame, "空值占位符：", config.get("source_empty_placeholder", ""), 7, 4, 16)
    overwrite_var = window.add_labeled_combo(frame, "覆盖规则：", config.get("overwrite_rule", "只填充空单元格"), OVERWRITE_RULE_VALUES, 8, 0, 20)
    ttk.Label(
        frame,
        text="提示：选择“来源列完整结构”时，会把来源字段的一整段数据顺序填入目标区域；选择“循环源列填充”时，默认使用“取值/来源字段”到“取值/结束字段”的多个源字段作为循环周期，按行优先重复填充到目标区域边界；选择“指定行多字段取值”时，会取指定行中“取值/来源字段”到“取值/结束字段”的多个值；选择“来源区域完整复制”时，会按统一左上角锚点完整复制源区域。",
        foreground="gray",
        wraplength=1050,
    ).grid(row=9, column=0, columnspan=8, sticky=tk.W, padx=4, pady=(8, 2))
    _sync_vars(
        window,
        config,
        [
            (sf_var, "start_field"),
            (ef_var, "end_field"),
            (start_row_mode_var, "start_row_mode"),
            (sr_var, "start_row"),
            (er_var, "end_row"),
            (end_mode_var, "end_row_mode"),
            (ref_field_var, "reference_field"),
            (source_var, "value_source"),
            (manual_var, "manual_value"),
            (src_field_var, "source_field"),
            (src_end_var, "source_end_field"),
            (src_row_var, "source_row"),
            (multi_dir_var, "multi_field_fill_direction"),
            (source_range_var, "source_range_mode"),
            (source_start_var, "source_start_row"),
            (source_end_var, "source_end_row"),
            (cycle_mode_var, "cycle_mode"),
            (source_empty_mode_var, "source_empty_mode"),
            (source_empty_placeholder_var, "source_empty_placeholder"),
            (overwrite_var, "overwrite_rule"),
        ],
    )


def build_delete_columns_config(window, config, headers):
    frame = ttk.LabelFrame(window.config_frame, text="删除列节点", padding=8)
    frame.pack(fill=tk.BOTH, expand=True, pady=8)
    ttk.Label(frame, text="勾选要删除的字段。建议只删除中间临时字段，执行前先预览。", foreground="gray").pack(anchor=tk.W)
    lb = tk.Listbox(frame, selectmode=tk.MULTIPLE, height=12, exportselection=False)
    lb.pack(fill=tk.BOTH, expand=True, pady=6)
    selected = set(config.get("fields", []))
    for index, header in enumerate(headers):
        lb.insert(tk.END, header)
        if header in selected:
            lb.selection_set(index)

    def sync(*_):
        config["fields"] = [lb.get(index) for index in lb.curselection()]

    lb.bind("<<ListboxSelect>>", sync)
    ttk.Button(frame, text="保存当前勾选", command=sync).pack(anchor=tk.W)


def normalize_column_order(config, headers):
    order = list(config.get("order", []))
    for header in headers:
        if header not in order:
            order.append(header)
    order = [header for header in order if header in headers]
    config["order"] = order
    return order


def sync_move_columns_order(config, listbox):
    config["order"] = list(listbox.get(0, tk.END))


def move_selected_column_order_item(config, listbox, delta):
    selected = listbox.curselection()
    if not selected:
        return
    index = selected[0]
    new_index = index + delta
    if new_index < 0 or new_index >= listbox.size():
        return
    value = listbox.get(index)
    listbox.delete(index)
    listbox.insert(new_index, value)
    listbox.selection_set(new_index)
    sync_move_columns_order(config, listbox)


def move_selected_column_order_to_top(config, listbox):
    selected = listbox.curselection()
    if not selected or selected[0] == 0:
        return
    value = listbox.get(selected[0])
    listbox.delete(selected[0])
    listbox.insert(0, value)
    listbox.selection_set(0)
    sync_move_columns_order(config, listbox)


def move_selected_column_order_to_bottom(config, listbox):
    selected = listbox.curselection()
    if not selected or selected[0] == listbox.size() - 1:
        return
    value = listbox.get(selected[0])
    listbox.delete(selected[0])
    listbox.insert(tk.END, value)
    listbox.selection_set(listbox.size() - 1)
    sync_move_columns_order(config, listbox)


def build_move_columns_config(window, config, headers):
    frame = ttk.LabelFrame(window.config_frame, text="移动列节点", padding=8)
    frame.pack(fill=tk.BOTH, expand=True, pady=8)
    ttk.Label(
        frame,
        text="调整字段顺序。执行时会按这里的顺序输出，未出现在列表中的字段会自动追加到最后。",
        foreground="gray",
    ).pack(anchor=tk.W)
    order = normalize_column_order(config, headers)
    body = ttk.Frame(frame)
    body.pack(fill=tk.BOTH, expand=True, pady=6)
    lb = tk.Listbox(body, height=14, exportselection=False)
    lb_scroll = ttk.Scrollbar(body, orient=tk.VERTICAL, command=lb.yview)
    lb.configure(yscrollcommand=lb_scroll.set)
    lb.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    lb_scroll.pack(side=tk.LEFT, fill=tk.Y)
    for header in order:
        lb.insert(tk.END, header)
    btns = ttk.Frame(body)
    btns.pack(side=tk.LEFT, fill=tk.Y, padx=6)
    for text, command in [
        ("上移", lambda: move_selected_column_order_item(config, lb, -1)),
        ("下移", lambda: move_selected_column_order_item(config, lb, 1)),
        ("置顶", lambda: move_selected_column_order_to_top(config, lb)),
        ("置底", lambda: move_selected_column_order_to_bottom(config, lb)),
    ]:
        ttk.Button(btns, text=text, command=command).pack(fill=tk.X, pady=2)
