# -*- coding: utf-8 -*-
"""UI-free jump analysis service for workflow plans."""

from __future__ import annotations

import copy

from engine.issue_schema import has_error_issues, make_issue
from workflow.jump_analysis import (
    collect_jump_anchors,
    collect_jump_relations,
    jump_issue_detail_text,
    jump_validation_summary_text,
    validate_jump_relations,
)
from workflow.protocol_nodes import display_type_for_node


class JumpAnalysisService:
    def analyze_plan(self, plan=None, *, nodes=None):
        node_list = _legacy_jump_nodes(_extract_nodes(plan, nodes))
        anchors_info = collect_jump_anchors(node_list)
        relations = collect_jump_relations(node_list, anchors_info=anchors_info)
        raw_issues = validate_jump_relations(node_list)
        issues = [_normalize_jump_issue(issue) for issue in raw_issues]
        return {
            "ok": not has_error_issues(issues),
            "anchors": _public_anchors(anchors_info.get("all", [])),
            "relations": _public_relations(relations),
            "issues": issues,
            "summary": jump_validation_summary_text(raw_issues),
            "counts": _issue_counts(issues),
        }

    def describe_manager_state(self, plan=None, *, nodes=None):
        analysis = self.analyze_plan(plan, nodes=nodes)
        anchors = list(analysis.get("anchors") or [])
        relations = list(analysis.get("relations") or [])
        issues = list(analysis.get("issues") or [])
        reference_counts = {}
        for relation in relations:
            target = str(relation.get("target_anchor_id") or "").strip()
            if target:
                reference_counts[target] = reference_counts.get(target, 0) + 1
        anchor_rows = []
        for anchor in anchors:
            item = copy.deepcopy(anchor)
            anchor_id = str(item.get("anchor_id") or "").strip()
            item["reference_count"] = int(reference_counts.get(anchor_id, 0))
            item["status"] = _anchor_status(anchor, anchors)
            anchor_rows.append(item)
        return {
            "ok": analysis.get("ok", True),
            "schema_version": "jump_manager_state.v1",
            "provider": "JumpAnalysisService.describe_manager_state",
            "summary": analysis.get("summary", ""),
            "counts": {
                "anchors": len(anchor_rows),
                "relations": len(relations),
                "issues": len(issues),
                "errors": int((analysis.get("counts") or {}).get("error", 0) or 0),
                "warnings": int((analysis.get("counts") or {}).get("warning", 0) or 0),
                "infos": int((analysis.get("counts") or {}).get("info", 0) or 0),
            },
            "layout": _jump_manager_layout(),
            "ui_hints": _jump_manager_ui_hints(),
            "actions": _jump_manager_actions(),
            "anchors": anchor_rows,
            "relations": relations,
            "issues": issues,
            "analysis": analysis,
        }

    def validate_jumps(self, plan=None, *, nodes=None):
        analysis = self.analyze_plan(plan, nodes=nodes)
        return {
            "ok": analysis["ok"],
            "issues": analysis["issues"],
            "summary": analysis["summary"],
            "counts": analysis["counts"],
            "anchor_count": len(analysis["anchors"]),
            "relation_count": len(analysis["relations"]),
        }

    def format_issue(self, issue):
        raw = (issue or {}).get("raw_issue")
        if raw:
            return jump_issue_detail_text(raw)
        lines = [
            f"级别：{(issue or {}).get('severity', '')}",
            f"问题：{(issue or {}).get('message', '')}",
        ]
        if (issue or {}).get("suggestion"):
            lines.append(f"建议：{issue.get('suggestion')}")
        return "\n".join(lines)


def _extract_nodes(plan, nodes):
    if nodes is not None:
        return list(nodes or [])
    if isinstance(plan, dict):
        return list(plan.get("nodes") or [])
    return []


def _legacy_jump_nodes(nodes):
    result = []
    for node in nodes or []:
        if not isinstance(node, dict):
            continue
        item = copy.deepcopy(node)
        item["type"] = display_type_for_node(item)
        result.append(item)
    return result


def _normalize_jump_issue(issue):
    relation = issue.get("relation") or {}
    anchor = issue.get("anchor") or {}
    node_index = None
    if relation:
        node_index = relation.get("source_index")
    elif anchor:
        node_index = anchor.get("node_index")
    severity = issue.get("severity", "info")
    code = {
        "error": "jump_validation_error",
        "warning": "jump_validation_warning",
        "info": "jump_validation_info",
    }.get(severity, "jump_validation_issue")
    return make_issue(
        severity,
        code,
        issue.get("message", ""),
        path=f"/nodes/{node_index}" if node_index is not None else "/nodes",
        node_index=node_index,
        source="JumpAnalysisService",
        suggestion=issue.get("suggestion", ""),
        item=issue.get("item", ""),
        relation=_public_relation(relation) if relation else {},
        anchor=_public_anchor(anchor) if anchor else {},
        raw_issue=_public_raw_issue(issue),
    )


def _public_raw_issue(issue):
    result = dict(issue or {})
    if result.get("relation"):
        result["relation"] = _public_relation(result["relation"])
    if result.get("anchor"):
        result["anchor"] = _public_anchor(result["anchor"])
    return result


def _public_anchors(anchors):
    return [_public_anchor(anchor) for anchor in anchors or []]


def _public_anchor(anchor):
    if not isinstance(anchor, dict):
        return {}
    return {
        "anchor_id": anchor.get("anchor_id", ""),
        "anchor_name": anchor.get("anchor_name", ""),
        "description": anchor.get("description", ""),
        "node_index": anchor.get("node_index"),
        "node_id": anchor.get("node_id", ""),
        "node_name": anchor.get("node_name", ""),
        "enabled": bool(anchor.get("enabled", True)),
    }


def _public_relations(relations):
    return [_public_relation(relation) for relation in relations or []]


def _public_relation(relation):
    if not isinstance(relation, dict):
        return {}
    return {
        "source_index": relation.get("source_index"),
        "source_label": relation.get("source_label", ""),
        "source_type": relation.get("source_type", ""),
        "kind": relation.get("kind", ""),
        "flag_name": relation.get("flag_name", ""),
        "condition_value": relation.get("condition_value", ""),
        "target_anchor_id": relation.get("target_anchor_id", ""),
        "enabled": bool(relation.get("enabled", True)),
        "is_default": bool(relation.get("is_default", False)),
        "rule_index": relation.get("rule_index"),
        "status": relation.get("status", ""),
    }


def _anchor_status(anchor, anchors):
    if not bool((anchor or {}).get("enabled", True)):
        return "disabled"
    anchor_id = str((anchor or {}).get("anchor_id") or "").strip()
    if not anchor_id:
        return "error"
    same_id = [
        item for item in anchors or []
        if str((item or {}).get("anchor_id") or "").strip() == anchor_id
    ]
    if len(same_id) > 1:
        return "duplicate"
    return "active"


def _jump_manager_layout():
    return {
        "schema_version": "jump_manager_layout.v1",
        "default_section": "relations",
        "sections": [
            {
                "section_id": "anchors",
                "title": "锚点",
                "kind": "table",
                "row_key": "anchor_id",
                "columns": [
                    {"key": "node_index", "label": "#", "type": "number"},
                    {"key": "anchor_id", "label": "锚点ID", "type": "text"},
                    {"key": "anchor_name", "label": "名称", "type": "text"},
                    {"key": "reference_count", "label": "引用", "type": "number"},
                    {"key": "status", "label": "状态", "type": "status"},
                ],
            },
            {
                "section_id": "relations",
                "title": "跳转关系",
                "kind": "table",
                "row_key": "source_index",
                "columns": [
                    {"key": "source_label", "label": "来源节点", "type": "text"},
                    {"key": "kind", "label": "类型", "type": "text"},
                    {"key": "flag_name", "label": "标志", "type": "text"},
                    {"key": "condition_value", "label": "条件值", "type": "text"},
                    {"key": "target_anchor_id", "label": "目标锚点", "type": "text"},
                    {"key": "status", "label": "状态", "type": "status"},
                ],
            },
            {
                "section_id": "issues",
                "title": "校验结果",
                "kind": "table",
                "row_key": "path",
                "columns": [
                    {"key": "severity", "label": "级别", "type": "severity"},
                    {"key": "item", "label": "对象", "type": "text"},
                    {"key": "message", "label": "问题", "type": "text"},
                    {"key": "suggestion", "label": "建议", "type": "text"},
                ],
            },
        ],
    }


def _jump_manager_ui_hints():
    return {
        "schema_version": "jump_manager_ui_hints.v1",
        "preferred_navigation": "three_pane",
        "default_detail_source": "selection",
        "status_colors": {
            "active": "success",
            "disabled": "muted",
            "duplicate": "error",
            "error": "error",
            "warning": "warning",
            "ok": "success",
        },
        "empty_text": {
            "anchors": "当前工作流还没有跳转锚点节点。",
            "relations": "当前工作流还没有跳转关系。",
            "issues": "当前没有跳转校验问题。",
        },
    }


def _jump_manager_actions():
    return {
        "schema_version": "jump_manager_actions.v1",
        "action_order": ["refresh", "validate", "format_issue"],
        "actions": {
            "refresh": {
                "action_id": "refresh",
                "label": "刷新",
                "engine_action": "describe_jump_manager_state",
                "enabled": True,
            },
            "validate": {
                "action_id": "validate",
                "label": "校验",
                "engine_action": "validate_jumps",
                "enabled": True,
            },
            "format_issue": {
                "action_id": "format_issue",
                "label": "查看问题详情",
                "engine_action": "format_jump_issue",
                "enabled": True,
                "requires_selection": True,
                "selection_source": "issues",
            },
        },
    }


def _issue_counts(issues):
    counts = {"error": 0, "warning": 0, "info": 0}
    for issue in issues or []:
        severity = issue.get("severity", "info")
        counts[severity] = counts.get(severity, 0) + 1
    return counts
