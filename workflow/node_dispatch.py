# -*- coding: utf-8 -*-
"""Regular node dispatch helpers for PlanWorkflowWindow.apply_node."""

from workflow.nodes.data_nodes import (
    apply_area_fill_node,
    apply_fill_value_node,
    apply_dedupe_node,
    apply_match_value_output_field_name_node,
    apply_row_data_mapping_node,
    apply_sequence_fill_node,
)
from workflow.nodes.new_column_nodes import (
    apply_current_datetime_column_node,
    apply_new_columns_node,
)
from workflow.nodes.datetime_format_nodes import apply_format_datetime_node
from workflow.nodes.extract_nodes import apply_extract_node
from workflow.nodes.merge_rename_nodes import apply_merge_node, apply_rename_columns_node
from workflow.nodes.numeric_column_nodes import apply_numeric_column_node
from workflow.nodes.replace_nodes import apply_replace_node
from workflow.nodes.table_edit_nodes import (
    apply_copy_column_node,
    apply_copy_row_node,
    apply_delete_columns_node,
    apply_delete_rows_node,
    apply_move_columns_node,
)
from workflow.file_node_runtime import (
    apply_batch_rename_node_for_window,
    apply_file_list_node_for_window,
)
from workflow.filter_node_runtime import apply_filter_node_for_window
from workflow.group_runtime import apply_group_node as apply_group_node_for_window
from workflow.loop_node_runtime import (
    apply_loop_judge_node_for_window,
    apply_loop_start_node_for_window,
)
from workflow.output_node_runtime import (
    apply_save_transit_node_for_window,
    apply_selected_columns_write_node_for_window,
    apply_writeback_node_for_window,
)
from workflow.plugin_node_runtime import apply_plugin_node_for_window


def make_window_data_node_context(window, context):
    node_context = dict(context or {})
    node_context["check_cancelled"] = lambda index: window.check_workflow_cancelled_periodically(context, index)
    node_context["max_expanded_rows"] = window.MAX_EXPANDED_ROWS
    node_context["max_target_cells"] = window.MAX_TARGET_CELLS
    return node_context


def make_match_value_output_context(window, config, context):
    node_context = make_window_data_node_context(window, context)
    lookup_columns, lookup_records = window.load_lookup_table_for_match_value_output(config, context=context)
    node_context["lookup_columns"] = lookup_columns
    node_context["lookup_records"] = lookup_records
    return node_context


def dispatch_control_flow_node(window, headers, rows, node_type, config, context, execute_actions=False):
    if node_type == "节点组 / 子工作流":
        return apply_group_node_for_window(window, headers, rows, config, execute_actions=execute_actions, context=context)
    if node_type == "循环执行起点":
        h, r, stat, _ctrl = apply_loop_start_node_for_window(window, headers, rows, config, context=context)
        return h, r, stat
    if node_type == "循环判断回跳":
        h, r, stat, _ctrl = apply_loop_judge_node_for_window(window, headers, rows, config, context=context)
        return h, r, stat
    return None


def dispatch_data_node(window, headers, rows, node_type, config, context, execute_actions=False):
    if node_type == "批量替换":
        return apply_replace_node(headers, rows, config, context=make_window_data_node_context(window, context))
    if node_type == "数据提取":
        return apply_extract_node(headers, rows, config)
    if node_type == "格式规范化 / 日期时间解析":
        return apply_format_datetime_node(headers, rows, config)
    if node_type == "新建日期时间列":
        return apply_current_datetime_column_node(headers, rows, config)
    if node_type == "新建列":
        return apply_new_columns_node(headers, rows, config)
    if node_type == "合并列":
        return apply_merge_node(headers, rows, config, context=make_window_data_node_context(window, context))
    if node_type == "批量更改列名":
        return apply_rename_columns_node(headers, rows, config)
    if node_type == "去重 / 重复数据处理":
        return apply_dedupe_node(headers, rows, config, context=make_window_data_node_context(window, context))
    if node_type == "列数字运算":
        return apply_numeric_column_node(headers, rows, config, context=make_window_data_node_context(window, context))
    if node_type == "复制列":
        return apply_copy_column_node(headers, rows, config)
    if node_type == "复制行":
        return apply_copy_row_node(headers, rows, config)
    if node_type == "删除行":
        return apply_delete_rows_node(headers, rows, config)
    if node_type == "填充值":
        return apply_fill_value_node(headers, rows, config, context=make_window_data_node_context(window, context))
    if node_type == "序列填充":
        return apply_sequence_fill_node(headers, rows, config, context=make_window_data_node_context(window, context))
    if node_type == "区域填充":
        return apply_area_fill_node(headers, rows, config, context=make_window_data_node_context(window, context))
    if node_type == "行数据映射填充":
        return apply_row_data_mapping_node(headers, rows, config)
    if node_type == "删除列":
        return apply_delete_columns_node(headers, rows, config)
    if node_type == "移动列":
        return apply_move_columns_node(headers, rows, config)
    return None


def dispatch_lookup_data_node(window, headers, rows, node_type, config, context, execute_actions=False):
    if node_type == "匹配值输出列名":
        return apply_match_value_output_field_name_node(
            headers,
            rows,
            config,
            context=make_match_value_output_context(window, config, context),
        )
    return None


def dispatch_window_runtime_node(window, headers, rows, node_type, config, context, execute_actions=False):
    if node_type == "获取文件列表":
        return apply_file_list_node_for_window(window, headers, rows, config, context=context)
    if node_type == "插件节点":
        return apply_plugin_node_for_window(window, headers, rows, config, context=context, execute_actions=execute_actions)
    if node_type == "保存中转数据":
        return apply_save_transit_node_for_window(
            window,
            headers,
            rows,
            config,
            context=context,
            execute_actions=execute_actions,
        )
    if node_type == "选定列写入指定表":
        return apply_selected_columns_write_node_for_window(
            window,
            headers,
            rows,
            config,
            context=context,
            execute_actions=execute_actions,
        )
    if node_type == "字段映射写入表":
        return apply_writeback_node_for_window(
            window,
            headers,
            rows,
            config,
            execute_actions=execute_actions,
            context=context,
        )
    if node_type == "高级筛选":
        return apply_filter_node_for_window(window, headers, rows, config, context=context)
    if node_type == "批量重命名":
        return apply_batch_rename_node_for_window(
            window,
            headers,
            rows,
            config,
            execute_actions=execute_actions,
            context=context,
        )
    return None


def apply_workflow_node(window, headers, rows, node, execute_actions=False, context=None):
    node_type = node.get("type")
    config = node.get("config", {})

    for dispatcher in (
        dispatch_control_flow_node,
        dispatch_data_node,
        dispatch_lookup_data_node,
        dispatch_window_runtime_node,
    ):
        result = dispatcher(
            window,
            headers,
            rows,
            node_type,
            config,
            context,
            execute_actions=execute_actions,
        )
        if result is not None:
            return result

    raise ValueError(f"未知节点类型：{node_type}")
