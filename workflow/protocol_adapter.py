# -*- coding: utf-8 -*-
"""Workflow JSON protocol adapter helpers shared by current and future UIs."""

import copy


WORKFLOW_PROTOCOL_VERSION = "1.0"
DEFAULT_NODE_VERSION = "1.0.0"


NODE_TYPE_ID_BY_DISPLAY_TYPE = {
    "获取文件列表": "core.file_list",
    "批量重命名": "core.batch_rename",
    "批量替换": "core.replace",
    "数据提取": "core.extract",
    "格式规范化 / 日期时间解析": "core.datetime_format",
    "新建日期时间列": "core.current_datetime_column",
    "新建列": "core.new_columns",
    "合并列": "core.merge_columns",
    "批量更改列名": "core.rename_columns",
    "去重 / 重复数据处理": "core.dedupe",
    "列数字运算": "core.numeric_column",
    "匹配值输出列名": "core.match_value_output",
    "复制列": "core.copy_column",
    "复制行": "core.copy_row",
    "删除列": "core.delete_columns",
    "删除行": "core.delete_rows",
    "移动列": "core.move_columns",
    "填充值": "core.fill_value",
    "序列填充": "core.sequence_fill",
    "区域填充": "core.area_fill",
    "行数据映射填充": "core.row_data_mapping",
    "高级筛选": "core.filter",
    "保存中转数据": "core.save_transit",
    "选定列写入指定表": "core.selected_columns_write",
    "字段映射写入表": "core.writeback",
    "节点组 / 子工作流": "core.group",
    "循环执行起点": "core.loop_start",
    "循环判断回跳": "core.loop_judge",
    "跳转锚点节点": "core.jump_anchor",
    "无条件跳转节点": "core.unconditional_jump",
    "条件判断节点": "core.condition_check",
    "条件跳转节点": "core.conditional_jump",
    "插件节点": "core.plugin",
}


DISPLAY_TYPE_BY_NODE_TYPE_ID = {
    value: key for key, value in NODE_TYPE_ID_BY_DISPLAY_TYPE.items()
}


def stable_node_type_id(node):
    """Return the stable protocol node type id for a node instance."""

    if not isinstance(node, dict):
        return ""
    existing = str(node.get("node_type_id", "") or "").strip()
    if existing:
        return existing
    display_type = str(node.get("type", "") or "").strip()
    if display_type == "插件节点":
        plugin_id = str(((node.get("config") or {}).get("plugin_id", "")) or "").strip()
        if plugin_id:
            return "plugin." + plugin_id
    return NODE_TYPE_ID_BY_DISPLAY_TYPE.get(display_type, display_type)


def display_type_for_node(node):
    """Return current display type, falling back from node_type_id when possible."""

    if not isinstance(node, dict):
        return ""
    display = str(node.get("type", "") or "").strip()
    if display:
        return display
    node_type_id = str(node.get("node_type_id", "") or "").strip()
    if node_type_id.startswith("plugin."):
        return "插件节点"
    return DISPLAY_TYPE_BY_NODE_TYPE_ID.get(node_type_id, node_type_id)


def upgrade_node_for_protocol(node, *, ensure_node_id=None):
    """Return a protocol 1.0 compatible copy of a node instance."""

    if not isinstance(node, dict):
        return node
    result = copy.deepcopy(node)
    if callable(ensure_node_id):
        ensure_node_id(result)
    result.setdefault("enabled", True)
    result.setdefault("config", {})
    result["type"] = display_type_for_node(result)
    result["node_type_id"] = stable_node_type_id(result)
    result.setdefault("node_version", DEFAULT_NODE_VERSION)
    result.setdefault("ui", {})
    result.setdefault("extensions", {})
    config = result.get("config")
    if isinstance(config, dict) and isinstance(config.get("nodes"), list):
        result["config"] = dict(config)
        result["config"]["nodes"] = [
            upgrade_node_for_protocol(child, ensure_node_id=ensure_node_id)
            for child in config.get("nodes", [])
        ]
    return result


def upgrade_nodes_for_protocol(nodes, *, ensure_node_id=None):
    return [
        upgrade_node_for_protocol(node, ensure_node_id=ensure_node_id)
        for node in (nodes or [])
    ]


def build_workflow_plan_payload(
    *,
    plan_name,
    nodes,
    output_mode="输出到主界面预览区",
    output_table="",
    backup_before_overwrite=True,
    table_access_policy="audit",
    headers=None,
    rows=None,
    metadata=None,
    ui=None,
    extensions=None,
    ensure_node_id=None,
):
    """Build a workflow_plan payload compatible with protocol 1.0."""

    payload = {
        "template_type": "workflow_plan",
        "version": WORKFLOW_PROTOCOL_VERSION,
        "plan_name": str(plan_name or "工作流计划"),
        "nodes": upgrade_nodes_for_protocol(nodes, ensure_node_id=ensure_node_id),
        "output_mode": output_mode,
        "output_table": output_table,
        "backup_before_overwrite": bool(backup_before_overwrite),
        "table_access_policy": table_access_policy,
        "metadata": dict(metadata or {}),
        "ui": dict(ui or {}),
        "extensions": dict(extensions or {}),
    }
    if headers is not None:
        payload["headers"] = list(headers)
    if rows is not None:
        payload["rows"] = [list(row) for row in rows]
    return payload


def build_runtime_request(request_id, action, payload=None, *, api_version="1.0"):
    return {
        "request_id": str(request_id or ""),
        "api_version": str(api_version or "1.0"),
        "action": str(action or ""),
        "payload": dict(payload or {}),
    }
