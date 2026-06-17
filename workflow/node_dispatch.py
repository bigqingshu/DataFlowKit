# -*- coding: utf-8 -*-
"""Regular node dispatch helpers for PlanWorkflowWindow.apply_node."""

from workflow.nodes.data_nodes import (
    apply_copy_column_node,
    apply_copy_row_node,
    apply_current_datetime_column_node,
    apply_delete_columns_node,
    apply_delete_rows_node,
    apply_extract_node,
    apply_format_datetime_node,
    apply_move_columns_node,
    apply_new_columns_node,
    apply_rename_columns_node,
)


def apply_workflow_node(window, headers, rows, node, execute_actions=False, context=None):
    node_type = node.get("type")
    config = node.get("config", {})
    if node_type == "节点组 / 子工作流":
        return window.apply_group_node(headers, rows, config, execute_actions=execute_actions, context=context)
    if node_type == "循环执行起点":
        h, r, stat, _ctrl = window.apply_loop_start_node(headers, rows, config, context=context)
        return h, r, stat
    if node_type == "循环判断回跳":
        h, r, stat, _ctrl = window.apply_loop_judge_node(headers, rows, config, context=context)
        return h, r, stat
    if node_type == "获取文件列表":
        return window.apply_file_list_node(headers, rows, config, context=context)
    if node_type == "批量替换":
        return window.apply_replace_node(headers, rows, config, context=context)
    if node_type == "数据提取":
        return apply_extract_node(headers, rows, config)
    if node_type == "格式规范化 / 日期时间解析":
        return apply_format_datetime_node(headers, rows, config)
    if node_type == "新建日期时间列":
        return apply_current_datetime_column_node(headers, rows, config)
    if node_type == "新建列":
        return apply_new_columns_node(headers, rows, config)
    if node_type == "合并列":
        return window.apply_merge_node(headers, rows, config, context=context)
    if node_type == "批量更改列名":
        return apply_rename_columns_node(headers, rows, config)
    if node_type == "去重 / 重复数据处理":
        return window.apply_dedupe_node(headers, rows, config, context=context)
    if node_type == "列数字运算":
        return window.apply_numeric_column_node(headers, rows, config, context=context)
    if node_type == "匹配值输出列名":
        return window.apply_match_value_output_field_name_node(headers, rows, config, context=context)
    if node_type == "插件节点":
        return window.apply_plugin_node(headers, rows, config, context=context, execute_actions=execute_actions)
    if node_type == "复制列":
        return apply_copy_column_node(headers, rows, config)
    if node_type == "复制行":
        return apply_copy_row_node(headers, rows, config)
    if node_type == "删除行":
        return apply_delete_rows_node(headers, rows, config)
    if node_type == "填充值":
        return window.apply_fill_value_node(headers, rows, config, context=context)
    if node_type == "序列填充":
        return window.apply_sequence_fill_node(headers, rows, config, context=context)
    if node_type == "区域填充":
        return window.apply_area_fill_node(headers, rows, config, context=context)
    if node_type == "行数据映射填充":
        return window.apply_row_data_mapping_node(headers, rows, config)
    if node_type == "保存中转数据":
        return window.apply_save_transit_node(headers, rows, config, context=context, execute_actions=execute_actions)
    if node_type == "选定列写入指定表":
        return window.apply_selected_columns_write_node(headers, rows, config, context=context, execute_actions=execute_actions)
    if node_type == "字段映射写入表":
        return window.apply_writeback_node(headers, rows, config, execute_actions=execute_actions, context=context)
    if node_type == "高级筛选":
        return window.apply_filter_node(headers, rows, config, context=context)
    if node_type == "删除列":
        return apply_delete_columns_node(headers, rows, config)
    if node_type == "移动列":
        return apply_move_columns_node(headers, rows, config)
    if node_type == "批量重命名":
        return window.apply_batch_rename_node(headers, rows, config, execute_actions=execute_actions, context=context)
    raise ValueError(f"未知节点类型：{node_type}")
