# -*- coding: utf-8 -*-
"""Workflow plan migration helpers shared by all frontends.

The migration layer is intentionally UI-free.  It upgrades legacy workflow
plans that still use Chinese ``type`` names into protocol-friendly plans with
stable ``node_type_id`` fields while preserving unknown fields for backwards
compatibility.
"""

from __future__ import annotations

import copy
import uuid

from workflow.protocol_nodes import (
    DEFAULT_NODE_VERSION,
    WORKFLOW_PROTOCOL_VERSION,
    display_type_for_node,
    stable_node_type_id_for_node,
)


def migrate_plan(
    plan,
    *,
    target_version=WORKFLOW_PROTOCOL_VERSION,
    node_id_factory=None,
):
    """Return a migrated copy of *plan* plus a small migration report.

    The input object is never mutated.  ``plan`` may be either a workflow plan
    dict or a raw node list because the headless engine accepts both shapes.
    """

    factory = node_id_factory or _default_node_id
    summary = _new_summary()
    issues = []

    if isinstance(plan, list):
        migrated_nodes, changed = _migrate_node_list(
            plan,
            factory,
            issues,
            summary,
            path="",
            nested=False,
        )
        return _result(migrated_nodes, changed, issues, summary, target_version)

    if not isinstance(plan, dict):
        issues.append(_issue("error", "invalid_plan", "plan 必须是 dict 或节点 list", path=""))
        return _result(copy.deepcopy(plan), False, issues, summary, target_version)

    migrated = copy.deepcopy(plan)
    changed = False

    if "template_type" not in migrated:
        migrated["template_type"] = "workflow_plan"
        summary["plan_defaults_added"] += 1
        changed = True
    if "version" not in migrated:
        migrated["version"] = str(target_version or WORKFLOW_PROTOCOL_VERSION)
        summary["plan_defaults_added"] += 1
        changed = True
    if "plan_name" not in migrated:
        migrated["plan_name"] = "工作流计划"
        summary["plan_defaults_added"] += 1
        changed = True

    nodes = migrated.get("nodes")
    if nodes is None:
        migrated["nodes"] = []
        summary["plan_defaults_added"] += 1
        issues.append(_issue("warning", "missing_nodes", "计划缺少 nodes，已按空节点列表处理。", path="/nodes"))
        changed = True
    elif not isinstance(nodes, list):
        issues.append(_issue("error", "invalid_nodes", "plan.nodes 必须是 list。", path="/nodes"))
    else:
        migrated_nodes, nodes_changed = _migrate_node_list(
            nodes,
            factory,
            issues,
            summary,
            path="/nodes",
            nested=False,
        )
        if nodes_changed:
            migrated["nodes"] = migrated_nodes
            changed = True

    return _result(migrated, changed, issues, summary, target_version)


def migrate_node(node, *, node_id_factory=None, path=""):
    """Return a migrated node copy and report data for single-node callers."""

    factory = node_id_factory or _default_node_id
    summary = _new_summary()
    issues = []
    migrated, changed = _migrate_node(node, factory, issues, summary, path=path or "/node", nested=False)
    return _result(migrated, changed, issues, summary, WORKFLOW_PROTOCOL_VERSION)


def _migrate_node_list(nodes, factory, issues, summary, *, path, nested):
    migrated = []
    changed = False
    for index, node in enumerate(nodes):
        child_path = f"{path}/{index}" if path else f"/{index}"
        item, item_changed = _migrate_node(
            node,
            factory,
            issues,
            summary,
            path=child_path,
            nested=nested,
        )
        migrated.append(item)
        changed = changed or item_changed
    return migrated, changed


def _migrate_node(node, factory, issues, summary, *, path, nested):
    summary["nodes_seen"] += 1
    if nested:
        summary["nested_nodes_seen"] += 1
    if not isinstance(node, dict):
        issues.append(_issue("error", "invalid_node", "节点必须是 object。", path=path))
        return copy.deepcopy(node), False

    migrated = copy.deepcopy(node)
    changed = False

    if not migrated.get("node_id"):
        migrated["node_id"] = str(factory())
        summary["node_ids_added"] += 1
        changed = True

    if "enabled" not in migrated:
        migrated["enabled"] = True
        summary["enabled_defaults_added"] += 1
        changed = True

    config = migrated.get("config")
    if not isinstance(config, dict):
        if config is None:
            migrated["config"] = {}
            summary["config_defaults_added"] += 1
            changed = True
        else:
            issues.append(_issue("error", "invalid_config", "node.config 必须是 object。", path=f"{path}/config"))
            return migrated, changed

    node_type_id = stable_node_type_id_for_node(migrated)
    if node_type_id and not migrated.get("node_type_id"):
        migrated["node_type_id"] = node_type_id
        summary["node_type_ids_added"] += 1
        changed = True
    elif not node_type_id:
        issues.append(_issue("warning", "missing_node_type", "节点缺少 type/node_type_id，无法补齐稳定类型。", path=path))

    if node_type_id and not migrated.get("type"):
        migrated["type"] = display_type_for_node(migrated)
        summary["legacy_types_added"] += 1
        changed = True

    if not migrated.get("node_version"):
        migrated["node_version"] = DEFAULT_NODE_VERSION
        summary["node_versions_added"] += 1
        changed = True

    config = migrated.get("config")
    if isinstance(config, dict) and isinstance(config.get("nodes"), list):
        child_nodes, child_changed = _migrate_node_list(
            config.get("nodes", []),
            factory,
            issues,
            summary,
            path=f"{path}/config/nodes",
            nested=True,
        )
        if child_changed:
            migrated["config"] = dict(config)
            migrated["config"]["nodes"] = child_nodes
            changed = True
    elif isinstance(config, dict) and "nodes" in config and config.get("nodes") is not None:
        issues.append(_issue("error", "invalid_nested_nodes", "node.config.nodes 必须是 list。", path=f"{path}/config/nodes"))

    if changed:
        summary["nodes_changed"] += 1
    return migrated, changed


def _result(plan, changed, issues, summary, target_version):
    return {
        "ok": not any(issue.get("severity") == "error" for issue in issues),
        "changed": bool(changed),
        "protocol_version": str(target_version or WORKFLOW_PROTOCOL_VERSION),
        "plan": plan,
        "issues": issues,
        "summary": dict(summary),
    }


def _new_summary():
    return {
        "nodes_seen": 0,
        "nested_nodes_seen": 0,
        "nodes_changed": 0,
        "node_ids_added": 0,
        "node_type_ids_added": 0,
        "node_versions_added": 0,
        "legacy_types_added": 0,
        "enabled_defaults_added": 0,
        "config_defaults_added": 0,
        "plan_defaults_added": 0,
    }


def _issue(severity, code, message, *, path=""):
    return {
        "severity": severity,
        "code": code,
        "message": message,
        "path": path,
    }


def _default_node_id():
    return "node_" + uuid.uuid4().hex
