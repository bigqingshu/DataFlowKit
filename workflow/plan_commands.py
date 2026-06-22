# -*- coding: utf-8 -*-
"""Pure workflow-plan editing commands shared by frontend shells."""

from __future__ import annotations

import copy
import uuid

from engine.issue_schema import has_error_issues, make_issue
from workflow.default_configs import default_config_for_type, default_name_for_node
from workflow.plan_migration import migrate_node
from workflow.protocol_nodes import (
    DEFAULT_NODE_VERSION,
    display_type_for_node,
    display_type_for_node_type_id,
    normalize_node_type_id,
)


def apply_plan_command(
    plan,
    command,
    *,
    preview_headers=None,
    table_names=None,
    table_columns=None,
    node_id_factory=None,
):
    """Apply a UI-neutral edit command to a workflow plan copy.

    Supported command types:

    - ``insert_node``
    - ``delete_nodes``
    - ``move_node``
    - ``duplicate_node``
    - ``toggle_node_enabled``
    - ``replace_node``
    - ``clear_nodes``
    """

    factory = node_id_factory or _default_node_id
    issues = []
    if not isinstance(command, dict):
        issues.append(_issue("error", "invalid_command", "command 必须是 object。", path="/command"))
        return _result(copy.deepcopy(plan), False, None, issues, "")

    plan_copy, nodes, shape_ok = _copy_plan_and_nodes(plan, issues)
    command_type = str(command.get("type") or command.get("command") or "").strip()
    if not shape_ok:
        return _result(plan_copy, False, None, issues, command_type)
    if not command_type:
        issues.append(_issue("error", "missing_command_type", "command 缺少 type。", path="/command/type"))
        return _result(plan_copy, False, None, issues, command_type)

    changed = False
    selected_index = None

    if command_type == "insert_node":
        node = _node_from_insert_command(
            command,
            factory,
            issues,
            preview_headers=preview_headers,
            table_names=table_names,
            table_columns=table_columns,
        )
        if node is not None:
            selected_index = _insert_index(command, len(nodes))
            nodes.insert(selected_index, node)
            changed = True
    elif command_type == "delete_nodes":
        indexes = _command_indexes(command)
        if _validate_indexes(indexes, len(nodes), issues, "/command/indexes"):
            first = indexes[0]
            for index in reversed(indexes):
                del nodes[index]
            selected_index = min(first, len(nodes) - 1) if nodes else None
            changed = True
    elif command_type == "move_node":
        index = _optional_int(command.get("index"))
        target = _move_target(command, index)
        if _validate_indexes([index], len(nodes), issues, "/command/index") and target is not None:
            if target < 0 or target >= len(nodes):
                issues.append(_issue("error", "move_out_of_range", "移动目标超出节点范围。", path="/command"))
            else:
                item = nodes.pop(index)
                nodes.insert(target, item)
                selected_index = target
                changed = index != target
    elif command_type == "duplicate_node":
        index = _optional_int(command.get("index"))
        if _validate_indexes([index], len(nodes), issues, "/command/index"):
            new_node = copy.deepcopy(nodes[index])
            new_node["node_id"] = str(factory())
            base_name = new_node.get("name") or display_type_for_node(new_node) or new_node.get("node_type_id") or "节点"
            new_node["name"] = f"{base_name}_复制"
            nodes.insert(index + 1, new_node)
            selected_index = index + 1
            changed = True
    elif command_type == "toggle_node_enabled":
        index = _optional_int(command.get("index"))
        if _validate_indexes([index], len(nodes), issues, "/command/index"):
            if "enabled" in command:
                nodes[index]["enabled"] = bool(command.get("enabled"))
            else:
                nodes[index]["enabled"] = not bool(nodes[index].get("enabled", True))
            selected_index = index
            changed = True
    elif command_type == "replace_node":
        index = _optional_int(command.get("index"))
        if _validate_indexes([index], len(nodes), issues, "/command/index"):
            node = command.get("node")
            if not isinstance(node, dict):
                issues.append(_issue("error", "invalid_node", "replace_node.node 必须是 object。", path="/command/node"))
            else:
                nodes[index] = _normalize_command_node(node, factory, issues, path="/command/node")
                selected_index = index
                changed = True
    elif command_type == "clear_nodes":
        if nodes:
            del nodes[:]
            changed = True
        selected_index = None
    else:
        issues.append(_issue("error", "unknown_command", f"未知 plan command：{command_type}", path="/command/type"))

    return _result(plan_copy, changed, selected_index, issues, command_type)


def _copy_plan_and_nodes(plan, issues):
    if isinstance(plan, list):
        nodes = copy.deepcopy(plan)
        return nodes, nodes, True
    if not isinstance(plan, dict):
        issues.append(_issue("error", "invalid_plan", "plan 必须是 object 或节点 list。", path="/plan"))
        return copy.deepcopy(plan), [], False
    result = copy.deepcopy(plan)
    nodes = result.setdefault("nodes", [])
    if not isinstance(nodes, list):
        issues.append(_issue("error", "invalid_nodes", "plan.nodes 必须是 list。", path="/plan/nodes"))
        return result, [], False
    return result, nodes, True


def _node_from_insert_command(
    command,
    factory,
    issues,
    *,
    preview_headers=None,
    table_names=None,
    table_columns=None,
):
    if isinstance(command.get("node"), dict):
        return _normalize_command_node(command.get("node"), factory, issues, path="/command/node")
    node_type = command.get("node_type_id") or command.get("node_type") or command.get("type")
    node_type_id = normalize_node_type_id(node_type)
    if not node_type_id:
        issues.append(_issue("error", "missing_node_type", "insert_node 缺少 node_type_id。", path="/command/node_type_id"))
        return None
    display_name = display_type_for_node_type_id(node_type_id)
    node = {
        "node_id": str(factory()),
        "node_type_id": node_type_id,
        "node_version": DEFAULT_NODE_VERSION,
        "name": command.get("name") or default_name_for_node(display_name),
        "enabled": True,
        "config": default_config_for_type(
            display_name,
            preview_headers=preview_headers,
            table_names=table_names,
            table_columns=table_columns,
        ),
    }
    if bool(command.get("include_legacy_type", True)):
        node["type"] = display_name
    return node


def _normalize_command_node(node, factory, issues, *, path):
    result = migrate_node(node, node_id_factory=factory, path=path)
    issues.extend(result.get("issues", []))
    return result.get("plan")


def _insert_index(command, node_count):
    if command.get("index") is not None:
        index = _optional_int(command.get("index"))
    elif command.get("after_index") is not None:
        index = _optional_int(command.get("after_index")) + 1
    else:
        index = node_count
    if index is None:
        index = node_count
    return max(0, min(index, node_count))


def _move_target(command, index):
    if index is None:
        return None
    if command.get("to_index") is not None:
        return _optional_int(command.get("to_index"))
    direction = str(command.get("direction") or "").strip().lower()
    if direction in ("up", "上移", "-1"):
        return index - 1
    if direction in ("down", "下移", "1"):
        return index + 1
    offset = command.get("offset")
    if offset is not None:
        return index + int(offset)
    return None


def _command_indexes(command):
    if isinstance(command.get("indexes"), list):
        raw = command.get("indexes")
    elif command.get("index") is not None:
        raw = [command.get("index")]
    else:
        raw = []
    return sorted({_optional_int(value) for value in raw})


def _validate_indexes(indexes, node_count, issues, path):
    if not indexes:
        issues.append(_issue("error", "missing_index", "命令缺少节点索引。", path=path))
        return False
    for index in indexes:
        if index is None or index < 0 or index >= node_count:
            issues.append(_issue("error", "invalid_index", f"节点索引超出范围：{index}", path=path))
            return False
    return True


def _optional_int(value):
    if value is None or value == "":
        return None
    return int(value)


def _result(plan, changed, selected_index, issues, command_type):
    return {
        "ok": not has_error_issues(issues),
        "changed": bool(changed),
        "command": command_type,
        "plan": plan,
        "selected_index": selected_index,
        "issues": issues,
    }


def _issue(severity, code, message, *, path=""):
    return make_issue(severity, code, message, path=path)


def _default_node_id():
    return "node_" + uuid.uuid4().hex
