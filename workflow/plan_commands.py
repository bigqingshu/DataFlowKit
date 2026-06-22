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
    - ``update_node_fields``
    - ``patch_node_config``
    - ``update_config_list``
    - ``set_jump_rule``
    - ``delete_jump_rule``
    - ``move_jump_rule``
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
    elif command_type == "update_node_fields":
        index = _optional_int(command.get("index"))
        if _validate_indexes([index], len(nodes), issues, "/command/index"):
            patch = command.get("fields")
            if not isinstance(patch, dict):
                issues.append(_issue("error", "invalid_fields", "update_node_fields.fields 必须是 object。", path="/command/fields"))
            else:
                updated = _apply_node_field_patch(nodes[index], patch, issues, path="/command/fields")
                nodes[index] = _normalize_command_node(updated, factory, issues, path="/command/node")
                selected_index = index
                changed = True
    elif command_type == "patch_node_config":
        index = _optional_int(command.get("index"))
        if _validate_indexes([index], len(nodes), issues, "/command/index"):
            config_patch = command.get("config")
            if not isinstance(config_patch, dict):
                issues.append(_issue("error", "invalid_config", "patch_node_config.config 必须是 object。", path="/command/config"))
            else:
                updated = copy.deepcopy(nodes[index])
                config = updated.get("config")
                if not isinstance(config, dict):
                    config = {}
                updated["config"] = config
                for key, value in config_patch.items():
                    if value is None:
                        config.pop(key, None)
                    else:
                        config[key] = copy.deepcopy(value)
                nodes[index] = _normalize_command_node(updated, factory, issues, path="/command/node")
                selected_index = index
                changed = True
    elif command_type == "update_config_list":
        index = _optional_int(command.get("index"))
        if _validate_indexes([index], len(nodes), issues, "/command/index"):
            updated = copy.deepcopy(nodes[index])
            config = updated.get("config")
            if not isinstance(config, dict):
                config = {}
                updated["config"] = config
            field = str(command.get("field") or "").strip()
            if not field:
                issues.append(_issue("error", "missing_field", "update_config_list 缺少 field。", path="/command/field"))
            else:
                action = str(command.get("action") or "").strip().lower()
                changed = _apply_config_list_command(config, field, action, command, issues, path="/command")
                if changed:
                    nodes[index] = _normalize_command_node(updated, factory, issues, path="/command/node")
                    selected_index = index
    elif command_type in {"set_jump_rule", "delete_jump_rule", "move_jump_rule"}:
        index = _optional_int(command.get("index"))
        if _validate_indexes([index], len(nodes), issues, "/command/index"):
            updated = copy.deepcopy(nodes[index])
            config = updated.get("config")
            if not isinstance(config, dict):
                config = {}
                updated["config"] = config
            changed = _apply_jump_rule_command(config, command_type, command, issues, path="/command")
            if changed:
                nodes[index] = _normalize_command_node(updated, factory, issues, path="/command/node")
                selected_index = index
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


def _apply_node_field_patch(node, patch, issues, *, path):
    result = copy.deepcopy(node)
    protected = {"config", "nodes"}
    for key, value in patch.items():
        if key in protected:
            issues.append(_issue("error", "reserved_field_patch", f"{key} 不能通过 update_node_fields 修改。", path=f"{path}/{key}"))
            continue
        if value is None:
            result.pop(key, None)
        else:
            result[key] = copy.deepcopy(value)
    return result


def _apply_config_list_command(config, field, action, command, issues, *, path):
    current = config.get(field)
    if current is None:
        current = []
        config[field] = current
    if not isinstance(current, list):
        issues.append(_issue("error", "invalid_list_field", f"{field} 不是 list，不能使用 update_config_list。", path=f"{path}/field"))
        return False

    if action == "append":
        current.append(copy.deepcopy(command.get("item")))
        return True
    if action == "insert":
        target_index = _optional_int(command.get("item_index", command.get("at")))
        if target_index is None:
            issues.append(_issue("error", "missing_item_index", "insert 需要 item_index。", path=f"{path}/item_index"))
            return False
        current.insert(max(0, min(target_index, len(current))), copy.deepcopy(command.get("item")))
        return True
    if action == "update":
        item_index = _optional_int(command.get("item_index"))
        if not _validate_list_indexes([item_index], len(current), issues, f"{path}/item_index"):
            return False
        patch = command.get("item")
        if isinstance(current[item_index], dict) and isinstance(patch, dict):
            merged = copy.deepcopy(current[item_index])
            for key, value in patch.items():
                if value is None:
                    merged.pop(key, None)
                else:
                    merged[key] = copy.deepcopy(value)
            current[item_index] = merged
        else:
            current[item_index] = copy.deepcopy(patch)
        return True
    if action == "delete":
        item_index = _optional_int(command.get("item_index"))
        if not _validate_list_indexes([item_index], len(current), issues, f"{path}/item_index"):
            return False
        del current[item_index]
        return True
    if action == "move":
        item_index = _optional_int(command.get("item_index"))
        if not _validate_list_indexes([item_index], len(current), issues, f"{path}/item_index"):
            return False
        target_index = _move_target(command, item_index)
        if target_index is None or target_index < 0 or target_index >= len(current):
            issues.append(_issue("error", "move_out_of_range", "列表移动目标超出范围。", path=path))
            return False
        item = current.pop(item_index)
        current.insert(target_index, item)
        return item_index != target_index

    issues.append(_issue("error", "invalid_list_action", f"未知列表动作：{action}", path=f"{path}/action"))
    return False


def _apply_jump_rule_command(config, command_type, command, issues, *, path):
    jump_rules = config.get("jump_rules")
    if jump_rules is None:
        jump_rules = []
        config["jump_rules"] = jump_rules
    if not isinstance(jump_rules, list):
        issues.append(_issue("error", "invalid_list_field", "jump_rules 不是 list。", path=f"{path}/field"))
        return False

    if command_type == "set_jump_rule":
        item_index = _optional_int(command.get("item_index"))
        rule = copy.deepcopy(command.get("rule") or command.get("item") or {})
        if not isinstance(rule, dict):
            issues.append(_issue("error", "invalid_jump_rule", "set_jump_rule.rule 必须是 object。", path=f"{path}/rule"))
            return False
        if item_index is None:
            jump_rules.append(rule)
            return True
        if item_index < 0:
            issues.append(_issue("error", "invalid_item_index", f"列表项索引超出范围：{item_index}", path=f"{path}/item_index"))
            return False
        if item_index >= len(jump_rules):
            jump_rules.append(rule)
            return True
        merged = copy.deepcopy(jump_rules[item_index]) if isinstance(jump_rules[item_index], dict) else {}
        merged.update(rule)
        jump_rules[item_index] = merged
        return True

    if command_type == "delete_jump_rule":
        item_index = _optional_int(command.get("item_index"))
        if not _validate_list_indexes([item_index], len(jump_rules), issues, f"{path}/item_index"):
            return False
        del jump_rules[item_index]
        return True

    if command_type == "move_jump_rule":
        item_index = _optional_int(command.get("item_index"))
        if not _validate_list_indexes([item_index], len(jump_rules), issues, f"{path}/item_index"):
            return False
        target_index = _move_target(command, item_index)
        if target_index is None or target_index < 0 or target_index >= len(jump_rules):
            issues.append(_issue("error", "move_out_of_range", "跳转规则移动目标超出范围。", path=path))
            return False
        item = jump_rules.pop(item_index)
        jump_rules.insert(target_index, item)
        return item_index != target_index

    issues.append(_issue("error", "unknown_command", f"未知 jump rule command：{command_type}", path=f"{path}/type"))
    return False


def _validate_list_indexes(indexes, item_count, issues, path):
    if not indexes:
        issues.append(_issue("error", "missing_item_index", "命令缺少列表项索引。", path=path))
        return False
    for index in indexes:
        if index is None or index < 0 or index >= item_count:
            issues.append(_issue("error", "invalid_item_index", f"列表项索引超出范围：{index}", path=path))
            return False
    return True


def _default_node_id():
    return "node_" + uuid.uuid4().hex
