# -*- coding: utf-8 -*-
"""Pure helpers for analyzing workflow jump nodes and validation issues."""


def jump_node_label(idx, node):
    node_type = node.get("type", "")
    name = str(node.get("name", "") or "").strip()
    label = f"{idx + 1}.{node_type}"
    if name:
        label += f" / {name}"
    return label


def collect_jump_anchors(nodes=None):
    anchors = []
    by_id = {}
    for idx, node in enumerate(nodes or []):
        if node.get("type") != "跳转锚点节点":
            continue
        cfg = node.get("config", {}) or {}
        anchor_id = str(cfg.get("anchor_id", "") or "").strip()
        entry = {
            "anchor_id": anchor_id,
            "anchor_name": str(cfg.get("anchor_name", "") or node.get("name", "") or "").strip(),
            "description": str(cfg.get("description", "") or "").strip(),
            "node_index": idx,
            "node_id": node.get("node_id", ""),
            "node_name": node.get("name", ""),
            "enabled": bool(node.get("enabled", True)),
            "node": node,
        }
        anchors.append(entry)
        if anchor_id:
            by_id.setdefault(anchor_id, []).append(entry)
    return {"all": anchors, "by_id": by_id}


def collect_condition_flag_producers(nodes=None):
    flags = {}
    for idx, node in enumerate(nodes or []):
        if node.get("type") != "条件判断节点" or not node.get("enabled", True):
            continue
        flag_name = str((node.get("config", {}) or {}).get("flag_name", "") or "").strip()
        if not flag_name:
            continue
        flags.setdefault(flag_name, []).append({
            "node_index": idx,
            "node": node,
            "label": jump_node_label(idx, node),
        })
    return flags


def resolve_jump_anchor_index(anchor_id, anchors_info=None, nodes=None):
    anchor_id = str(anchor_id or "").strip()
    if not anchor_id:
        return None, "目标锚点未配置"
    anchors_info = anchors_info if isinstance(anchors_info, dict) else collect_jump_anchors(nodes=nodes)
    matches = list((anchors_info.get("by_id") or {}).get(anchor_id, []) or [])
    if not matches:
        return None, f"目标锚点不存在：{anchor_id}"
    enabled = [item for item in matches if item.get("enabled")]
    if not enabled:
        return None, f"目标锚点已禁用：{anchor_id}"
    if len(enabled) > 1:
        return None, f"目标锚点重复：{anchor_id}"
    target_idx = int(enabled[0].get("node_index", -1))
    return target_idx, f"有效：节点 {target_idx + 1}"


def jump_relation_status_text(relation, anchors_info=None, nodes=None):
    if not relation.get("enabled", True):
        return "跳转节点已禁用"
    target = str(relation.get("target_anchor_id", "") or "").strip()
    if not target:
        return "未配置目标锚点"
    target_idx, message = resolve_jump_anchor_index(target, anchors_info=anchors_info, nodes=nodes)
    if target_idx is None:
        return message
    return f"有效 -> 节点 {target_idx + 1}"


def collect_jump_relations(nodes=None, anchors_info=None):
    node_list = list(nodes or [])
    anchors_info = anchors_info if isinstance(anchors_info, dict) else collect_jump_anchors(nodes=node_list)
    relations = []
    for idx, node in enumerate(node_list):
        node_type = node.get("type", "")
        cfg = node.get("config", {}) or {}
        enabled = bool(node.get("enabled", True))
        if node_type == "无条件跳转节点":
            relation = {
                "source_index": idx,
                "source_label": jump_node_label(idx, node),
                "source_type": node_type,
                "kind": "无条件",
                "flag_name": "",
                "condition_value": "始终",
                "target_anchor_id": str(cfg.get("target_anchor_id", "") or "").strip(),
                "enabled": enabled,
                "is_default": False,
                "node": node,
            }
            relation["status"] = jump_relation_status_text(relation, anchors_info=anchors_info, nodes=node_list)
            relations.append(relation)
        elif node_type == "条件跳转节点":
            flag_name = str(cfg.get("flag_name", "") or "").strip()
            rules = cfg.get("jump_rules", [])
            if not isinstance(rules, list):
                rules = []
            for rule_idx, rule in enumerate(rules):
                if not isinstance(rule, dict):
                    continue
                relation = {
                    "source_index": idx,
                    "source_label": jump_node_label(idx, node),
                    "source_type": node_type,
                    "kind": "条件",
                    "flag_name": flag_name,
                    "condition_value": str(rule.get("value", "") or "").strip(),
                    "target_anchor_id": str(rule.get("target_anchor_id", "") or "").strip(),
                    "enabled": enabled,
                    "is_default": False,
                    "rule_index": rule_idx,
                    "node": node,
                }
                relation["status"] = jump_relation_status_text(relation, anchors_info=anchors_info, nodes=node_list)
                relations.append(relation)
            default_anchor = str(cfg.get("default_anchor_id", "") or "").strip()
            if default_anchor:
                relation = {
                    "source_index": idx,
                    "source_label": jump_node_label(idx, node),
                    "source_type": node_type,
                    "kind": "默认",
                    "flag_name": flag_name,
                    "condition_value": "DEFAULT",
                    "target_anchor_id": default_anchor,
                    "enabled": enabled,
                    "is_default": True,
                    "node": node,
                }
                relation["status"] = jump_relation_status_text(relation, anchors_info=anchors_info, nodes=node_list)
                relations.append(relation)
            if not rules and not default_anchor:
                relation = {
                    "source_index": idx,
                    "source_label": jump_node_label(idx, node),
                    "source_type": node_type,
                    "kind": "条件",
                    "flag_name": flag_name,
                    "condition_value": "",
                    "target_anchor_id": "",
                    "enabled": enabled,
                    "is_default": False,
                    "node": node,
                    "status": "未配置跳转规则",
                }
                relations.append(relation)
    return relations


def add_jump_validation_issue(issues, severity, item, message, suggestion="", relation=None, anchor=None):
    issues.append({
        "severity": severity,
        "item": item,
        "message": message,
        "suggestion": suggestion,
        "relation": relation,
        "anchor": anchor,
    })


def next_enabled_node_after_anchor(anchor, nodes=None):
    node_list = list(nodes or [])
    start = int(anchor.get("node_index", -1)) + 1
    for idx in range(start, len(node_list)):
        if (node_list[idx] or {}).get("enabled", True):
            return idx
    return None


def validate_jump_relations(nodes=None):
    node_list = list(nodes or [])
    anchors_info = collect_jump_anchors(nodes=node_list)
    relations = collect_jump_relations(nodes=node_list, anchors_info=anchors_info)
    flag_producers = collect_condition_flag_producers(nodes=node_list)
    issues = []

    for anchor in anchors_info.get("all", []):
        anchor_id = anchor.get("anchor_id", "")
        label = f"{anchor.get('node_index', -1) + 1}.锚点"
        if not anchor_id:
            add_jump_validation_issue(
                issues, "error", label, "锚点ID为空，其他跳转节点无法引用它。",
                "给锚点填写唯一、稳定的锚点ID。", anchor=anchor
            )
        if anchor.get("enabled") and next_enabled_node_after_anchor(anchor, nodes=node_list) is None:
            add_jump_validation_issue(
                issues, "warning", anchor_id or label, "锚点后没有可执行节点。",
                "如果该锚点不是终点，请在锚点后添加处理节点。", anchor=anchor
            )

    for anchor_id, matches in (anchors_info.get("by_id") or {}).items():
        enabled_matches = [m for m in matches if m.get("enabled")]
        if len(matches) > 1:
            add_jump_validation_issue(
                issues, "error", anchor_id, f"锚点ID重复：{len(matches)} 个节点使用同一个ID。",
                "保留一个锚点ID，其他锚点改名；重复锚点运行时默认不跳转。",
                anchor=matches[0],
            )
        if matches and not enabled_matches:
            add_jump_validation_issue(
                issues, "warning", anchor_id, "该锚点当前全部处于禁用状态。",
                "启用目标锚点，或调整跳转节点目标。", anchor=matches[0]
            )

    referenced = {str(rel.get("target_anchor_id", "") or "").strip() for rel in relations if str(rel.get("target_anchor_id", "") or "").strip()}
    for anchor in anchors_info.get("all", []):
        anchor_id = anchor.get("anchor_id", "")
        if anchor_id and anchor.get("enabled") and anchor_id not in referenced:
            add_jump_validation_issue(
                issues, "info", anchor_id, "锚点未被任何跳转节点引用。",
                "如果只是流程定位标记可以保留；如果希望跳到这里，请在跳转节点中绑定它。", anchor=anchor
            )

    checked_flag_nodes = set()
    for rel in relations:
        if not rel.get("enabled", True):
            continue
        source_idx = int(rel.get("source_index", -1))
        source_label = rel.get("source_label", "")
        target = str(rel.get("target_anchor_id", "") or "").strip()
        if rel.get("source_type") == "条件跳转节点":
            flag_name = str(rel.get("flag_name", "") or "").strip()
            flag_key = (source_idx, flag_name)
            if flag_key not in checked_flag_nodes:
                checked_flag_nodes.add(flag_key)
                if not flag_name:
                    add_jump_validation_issue(
                        issues, "warning", source_label, "条件跳转节点未填写读取标志。",
                        "填写条件判断节点输出的标志名；未填写时运行默认不跳转。", relation=rel
                    )
                elif flag_name not in flag_producers:
                    add_jump_validation_issue(
                        issues, "warning", source_label, f"未找到条件标志来源：{flag_name}",
                        "在该节点之前添加条件判断节点，或确认标志名完全一致。", relation=rel
                    )
                elif all(item.get("node_index", 0) > source_idx for item in flag_producers.get(flag_name, [])):
                    add_jump_validation_issue(
                        issues, "warning", source_label, f"条件标志 {flag_name} 的生成节点位于跳转节点之后。",
                        "把条件判断节点移到条件跳转节点之前。", relation=rel
                    )
            if not str(rel.get("condition_value", "") or "").strip() and not rel.get("is_default"):
                add_jump_validation_issue(
                    issues, "warning", source_label, "条件规则的条件值为空。",
                    "填写 TRUE/FALSE 或条件判断节点实际输出值；空值规则很容易误判。", relation=rel
                )

        if not target:
            add_jump_validation_issue(
                issues, "warning", source_label, "跳转目标锚点未配置，运行时默认不跳转。",
                "选择一个锚点；如果确实希望未命中时继续执行，可以保留默认锚点为空。", relation=rel
            )
            continue

        target_idx, message = resolve_jump_anchor_index(target, anchors_info=anchors_info, nodes=node_list)
        if target_idx is None:
            add_jump_validation_issue(
                issues, "error", source_label, message,
                "检查锚点ID是否存在、是否启用，以及是否重复。", relation=rel
            )
            continue
        if target_idx == source_idx:
            add_jump_validation_issue(
                issues, "error", source_label, "跳转目标指向当前节点，可能形成自跳转。",
                "改为跳到独立锚点，或删除该规则。", relation=rel
            )
        elif target_idx < source_idx:
            add_jump_validation_issue(
                issues, "warning", source_label, f"目标锚点在当前节点之前：节点 {target_idx + 1}",
                "这会形成回跳路径，请确认有条件能够退出，避免死循环。", relation=rel
            )

    severity_order = {"error": 0, "warning": 1, "info": 2}
    issues.sort(key=lambda item: (severity_order.get(item.get("severity"), 9), item.get("item", "")))
    return issues


def jump_validation_summary_text(issues):
    issues = list(issues or [])
    if not issues:
        return "跳转校验完成：未发现明显问题。"
    counts = {}
    for issue in issues:
        sev = issue.get("severity", "info")
        counts[sev] = counts.get(sev, 0) + 1
    parts = []
    if counts.get("error"):
        parts.append(f"错误 {counts['error']}")
    if counts.get("warning"):
        parts.append(f"警告 {counts['warning']}")
    if counts.get("info"):
        parts.append(f"提示 {counts['info']}")
    return "跳转校验完成：" + "，".join(parts)


def jump_issue_detail_text(issue):
    if not issue:
        return ""
    lines = [
        f"级别：{issue.get('severity', '')}",
        f"对象：{issue.get('item', '')}",
        f"问题：{issue.get('message', '')}",
    ]
    if issue.get("suggestion"):
        lines.append(f"建议：{issue.get('suggestion')}")
    rel = issue.get("relation") or {}
    if rel:
        lines.extend([
            "",
            "关系：",
            f"来源：{rel.get('source_label', '')}",
            f"类型：{rel.get('kind', '')}",
            f"读取标志：{rel.get('flag_name', '')}",
            f"条件值：{rel.get('condition_value', '')}",
            f"目标锚点：{rel.get('target_anchor_id', '')}",
            f"状态：{rel.get('status', '')}",
        ])
    anchor = issue.get("anchor") or {}
    if anchor:
        lines.extend([
            "",
            "锚点：",
            f"节点：{anchor.get('node_index', -1) + 1}",
            f"锚点ID：{anchor.get('anchor_id', '')}",
            f"名称：{anchor.get('anchor_name', '')}",
            f"启用：{'是' if anchor.get('enabled') else '否'}",
        ])
    return "\n".join(lines)
