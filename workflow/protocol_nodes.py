# -*- coding: utf-8 -*-
"""UI-free workflow node protocol catalog.

This module is the shared node identity layer between the current Tkinter UI,
the headless engine, and future frontends.  Execution code should use
``node_type_id`` as the stable key and treat the legacy Chinese ``type`` field
as display/compatibility data only.
"""

WORKFLOW_PROTOCOL_VERSION = "1.0"
DEFAULT_NODE_VERSION = "1.0.0"


NODE_TYPE_DEFINITIONS = [
    {"node_type_id": "core.file_list", "display_name": "获取文件列表", "category": "文件处理"},
    {"node_type_id": "core.group", "display_name": "节点组 / 子工作流", "category": "流程控制"},
    {"node_type_id": "core.loop_start", "display_name": "循环执行起点", "category": "流程控制"},
    {"node_type_id": "core.jump_anchor", "display_name": "跳转锚点节点", "category": "流程控制"},
    {"node_type_id": "core.unconditional_jump", "display_name": "无条件跳转节点", "category": "流程控制"},
    {"node_type_id": "core.condition_check", "display_name": "条件判断节点", "category": "流程控制"},
    {"node_type_id": "core.conditional_jump", "display_name": "条件跳转节点", "category": "流程控制"},
    {"node_type_id": "core.replace", "display_name": "批量替换", "category": "数据处理"},
    {"node_type_id": "core.extract", "display_name": "数据提取", "category": "数据处理"},
    {"node_type_id": "core.datetime_format", "display_name": "格式规范化 / 日期时间解析", "category": "数据处理"},
    {"node_type_id": "core.current_datetime_column", "display_name": "新建日期时间列", "category": "数据处理"},
    {"node_type_id": "core.new_columns", "display_name": "新建列", "category": "数据处理"},
    {"node_type_id": "core.merge_columns", "display_name": "合并列", "category": "数据处理"},
    {"node_type_id": "core.rename_columns", "display_name": "批量更改列名", "category": "数据处理"},
    {"node_type_id": "core.dedupe", "display_name": "去重 / 重复数据处理", "category": "数据处理"},
    {"node_type_id": "core.numeric_column", "display_name": "列数字运算", "category": "数据处理"},
    {"node_type_id": "core.match_value_output", "display_name": "匹配值输出列名", "category": "数据处理"},
    {"node_type_id": "core.copy_column", "display_name": "复制列", "category": "数据处理"},
    {"node_type_id": "core.copy_row", "display_name": "复制行", "category": "数据处理"},
    {"node_type_id": "core.delete_rows", "display_name": "删除行", "category": "数据处理"},
    {"node_type_id": "core.fill_value", "display_name": "填充值", "category": "数据处理"},
    {"node_type_id": "core.sequence_fill", "display_name": "序列填充", "category": "数据处理"},
    {"node_type_id": "core.area_fill", "display_name": "区域填充", "category": "数据处理"},
    {"node_type_id": "core.row_data_mapping", "display_name": "行数据映射填充", "category": "数据处理"},
    {"node_type_id": "core.save_transit", "display_name": "保存中转数据", "category": "输出"},
    {"node_type_id": "core.selected_columns_write", "display_name": "选定列写入指定表", "category": "输出"},
    {"node_type_id": "core.writeback", "display_name": "字段映射写入表", "category": "输出"},
    {"node_type_id": "core.filter", "display_name": "高级筛选", "category": "数据处理"},
    {"node_type_id": "core.delete_columns", "display_name": "删除列", "category": "数据处理"},
    {"node_type_id": "core.move_columns", "display_name": "移动列", "category": "数据处理"},
    {"node_type_id": "core.batch_rename", "display_name": "批量重命名", "category": "文件处理"},
    {"node_type_id": "core.loop_judge", "display_name": "循环判断回跳", "category": "流程控制"},
    {"node_type_id": "core.plugin", "display_name": "插件节点", "category": "插件"},
]


NODE_TYPE_ID_BY_DISPLAY_TYPE = {
    item["display_name"]: item["node_type_id"] for item in NODE_TYPE_DEFINITIONS
}

DISPLAY_TYPE_BY_NODE_TYPE_ID = {
    item["node_type_id"]: item["display_name"] for item in NODE_TYPE_DEFINITIONS
}


HEADLESS_DATA_NODE_TYPE_IDS = {
    "core.replace",
    "core.extract",
    "core.datetime_format",
    "core.current_datetime_column",
    "core.new_columns",
    "core.merge_columns",
    "core.rename_columns",
    "core.dedupe",
    "core.numeric_column",
    "core.copy_column",
    "core.copy_row",
    "core.delete_rows",
    "core.fill_value",
    "core.sequence_fill",
    "core.area_fill",
    "core.row_data_mapping",
    "core.delete_columns",
    "core.move_columns",
    "core.save_transit",
}

HEADLESS_CONTROL_NODE_TYPE_IDS = {
    "core.jump_anchor",
    "core.unconditional_jump",
    "core.condition_check",
    "core.conditional_jump",
}

HEADLESS_NODE_TYPE_IDS = HEADLESS_DATA_NODE_TYPE_IDS | HEADLESS_CONTROL_NODE_TYPE_IDS


def normalize_node_type_id(value):
    """Return a stable node_type_id from either a stable id or legacy display type."""

    text = str(value or "").strip()
    if not text:
        return ""
    if text.startswith("plugin."):
        return text
    if text in DISPLAY_TYPE_BY_NODE_TYPE_ID:
        return text
    return NODE_TYPE_ID_BY_DISPLAY_TYPE.get(text, text)


def display_type_for_node_type_id(node_type_id):
    """Return the legacy/current display type for a stable node id."""

    stable_id = normalize_node_type_id(node_type_id)
    if stable_id.startswith("plugin."):
        return "插件节点"
    return DISPLAY_TYPE_BY_NODE_TYPE_ID.get(stable_id, stable_id)


def stable_node_type_id_for_node(node):
    """Resolve a node instance or a raw type/id value to a stable node_type_id."""

    if not isinstance(node, dict):
        return normalize_node_type_id(node)

    existing = normalize_node_type_id(node.get("node_type_id", ""))
    if existing:
        return existing

    display_type = str(node.get("type", "") or "").strip()
    if display_type == "插件节点":
        plugin_id = str(((node.get("config") or {}).get("plugin_id", "")) or "").strip()
        if plugin_id:
            if plugin_id.startswith("plugin."):
                return plugin_id
            return "plugin." + plugin_id
    return normalize_node_type_id(display_type)


def display_type_for_node(node):
    """Resolve the human display type for a node instance or raw type/id value."""

    if not isinstance(node, dict):
        return display_type_for_node_type_id(node)

    display = str(node.get("type", "") or "").strip()
    if display:
        return display
    return display_type_for_node_type_id(stable_node_type_id_for_node(node))


def is_headless_supported_node_type(node_type):
    return normalize_node_type_id(node_type) in HEADLESS_NODE_TYPE_IDS


def node_type_definition_for(node_type):
    node_type_id = normalize_node_type_id(node_type)
    display_name = display_type_for_node_type_id(node_type_id)
    for item in NODE_TYPE_DEFINITIONS:
        if item["node_type_id"] == node_type_id:
            result = dict(item)
            result["supported_headless"] = node_type_id in HEADLESS_NODE_TYPE_IDS
            return result
    return {
        "node_type_id": node_type_id,
        "display_name": display_name,
        "category": "未知",
        "supported_headless": node_type_id in HEADLESS_NODE_TYPE_IDS,
    }


def list_node_type_definitions(include_unsupported=True):
    result = []
    for item in NODE_TYPE_DEFINITIONS:
        node_type_id = item["node_type_id"]
        if not include_unsupported and node_type_id not in HEADLESS_NODE_TYPE_IDS:
            continue
        payload = dict(item)
        payload["supported_headless"] = node_type_id in HEADLESS_NODE_TYPE_IDS
        result.append(payload)
    return result


def list_node_type_ids(include_unsupported=True):
    return [
        item["node_type_id"]
        for item in list_node_type_definitions(include_unsupported=include_unsupported)
    ]
