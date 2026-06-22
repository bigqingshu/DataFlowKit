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


def _issue_counts(issues):
    counts = {"error": 0, "warning": 0, "info": 0}
    for issue in issues or []:
        severity = issue.get("severity", "info")
        counts[severity] = counts.get(severity, 0) + 1
    return counts
