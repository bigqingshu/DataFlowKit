# -*- coding: utf-8 -*-
"""Workflow JSON protocol adapter helpers shared by current and future UIs."""

import copy

from workflow.protocol_nodes import (
    DEFAULT_NODE_VERSION,
    DISPLAY_TYPE_BY_NODE_TYPE_ID,
    NODE_TYPE_ID_BY_DISPLAY_TYPE,
    WORKFLOW_PROTOCOL_VERSION,
    display_type_for_node as _display_type_for_node,
    stable_node_type_id_for_node,
)


def stable_node_type_id(node):
    """Return the stable protocol node type id for a node instance."""

    return stable_node_type_id_for_node(node)


def display_type_for_node(node):
    """Return current display type, falling back from node_type_id when possible."""

    return _display_type_for_node(node)


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
