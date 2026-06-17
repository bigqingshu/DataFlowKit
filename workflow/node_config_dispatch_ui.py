# -*- coding: utf-8 -*-
"""Dispatch node configuration UI builders by workflow node type."""

from tkinter import ttk


CONFIG_ONLY_BUILDERS = {
    "跳转锚点节点": "build_jump_anchor_config",
    "无条件跳转节点": "build_unconditional_jump_config",
    "条件跳转节点": "build_conditional_jump_config",
    "获取文件列表": "build_file_list_config",
}

HEADER_BUILDERS = {
    "循环判断回跳": "build_loop_judge_config",
    "条件判断节点": "build_condition_check_config",
    "批量替换": "build_replace_config",
    "数据提取": "build_extract_config",
    "格式规范化 / 日期时间解析": "build_format_datetime_config",
    "新建日期时间列": "build_current_datetime_column_config",
    "新建列": "build_new_columns_config",
    "合并列": "build_merge_config",
    "批量更改列名": "build_rename_columns_config",
    "去重 / 重复数据处理": "build_dedupe_config",
    "列数字运算": "build_numeric_column_config",
    "复制列": "build_copy_column_config",
    "复制行": "build_copy_row_config",
    "删除行": "build_delete_rows_config",
    "填充值": "build_fill_value_config",
    "序列填充": "build_sequence_fill_config",
    "区域填充": "build_area_fill_config",
    "行数据映射填充": "build_row_data_mapping_config",
    "保存中转数据": "build_save_transit_config",
    "字段映射写入表": "build_writeback_config",
    "删除列": "build_delete_columns_config",
    "移动列": "build_move_columns_config",
    "批量重命名": "build_batch_rename_config",
}

TRANSIT_HEADER_BUILDERS = {
    "节点组 / 子工作流": "build_group_node_config",
    "循环执行起点": "build_loop_start_config",
    "匹配值输出列名": "build_match_value_output_field_name_config",
    "高级筛选": "build_filter_config",
}


def _call_window_builder(window, method_name, *args):
    return getattr(window, method_name)(*args)


def dispatch_node_config_builder(window, idx, node_type, config, available_headers, available_rows):
    """Call the concrete config UI builder for one workflow node type."""
    if node_type in CONFIG_ONLY_BUILDERS:
        return _call_window_builder(window, CONFIG_ONLY_BUILDERS[node_type], config)

    if node_type in HEADER_BUILDERS:
        return _call_window_builder(window, HEADER_BUILDERS[node_type], config, available_headers)

    if node_type in TRANSIT_HEADER_BUILDERS:
        transit_context = window.get_transit_context_before(idx)
        return _call_window_builder(
            window,
            TRANSIT_HEADER_BUILDERS[node_type],
            config,
            available_headers,
            transit_context,
        )

    if node_type == "插件节点":
        transit_context = window.get_transit_context_before(idx)
        return window.build_plugin_node_config(
            config,
            available_headers,
            transit_context,
            available_rows,
        )

    if node_type == "选定列写入指定表":
        transit_context = window.get_transit_context_before(idx)
        return window.build_selected_columns_write_config(
            config,
            available_headers,
            idx,
            transit_context,
        )

    ttk.Label(window.config_frame, text="未知节点类型。", foreground="red").pack(anchor="w")
    return None
