# -*- coding: utf-8 -*-
"""Backend service for workflow plan templates."""

from __future__ import annotations

import copy
from pathlib import Path

from engine.issue_schema import has_error_issues, make_issue
from engine.plan_io import build_plan_document, list_plan_templates, load_plan, save_plan
from workflow.plan_migration import migrate_plan


WORKFLOW_PLAN_TEMPLATE_TYPE = "workflow_plan"


class PlanTemplateService:
    """UI-free plan template operations shared by Qt, stdio, and future clients."""

    def __init__(self, *, node_id_factory=None):
        self.node_id_factory = node_id_factory

    def list_templates(self, plan_dir):
        root = Path(plan_dir)
        return {
            "ok": True,
            "plan_dir": str(root),
            "templates": list_plan_templates(root),
        }

    def validate_template(self, plan):
        issues = validate_plan_template(plan)
        return {
            "ok": not has_error_issues(issues),
            "issues": issues,
        }

    def load_template(self, path, *, migrate=True, target_version=None):
        loaded = load_plan(path)
        plan = loaded["plan"]
        migration = None
        if migrate:
            migration = migrate_plan(
                plan,
                target_version=target_version,
                node_id_factory=self.node_id_factory,
            )
            plan = migration.get("plan")

        validation = self.validate_template(plan)
        issues = list((migration or {}).get("issues", [])) + list(validation.get("issues", []))
        ok = not has_error_issues(issues)
        warning = loaded.get("warning") or _first_non_error_message(issues)
        return {
            "ok": ok,
            "path": loaded["path"],
            "plan": plan,
            "info": dict(loaded.get("info") or {}),
            "warning": warning,
            "issues": issues,
            "migration": migration,
        }

    def save_template(
        self,
        path,
        plan,
        *,
        headers=None,
        rows=None,
        output_mode=None,
        output_table=None,
        backup_before_overwrite=None,
        db_path=None,
        output_path=None,
        input_source=None,
        input_db_path=None,
        migrate=True,
        target_version=None,
    ):
        target = Path(path)
        document = build_plan_document(
            plan,
            headers=headers,
            rows=rows,
            output_mode=output_mode,
            output_table=output_table,
            backup_before_overwrite=backup_before_overwrite,
            db_path=db_path,
            output_path=output_path,
            input_source=input_source,
            input_db_path=input_db_path,
        )
        if not str(document.get("plan_name") or "").strip():
            document["plan_name"] = target.stem or "工作流计划"

        migration = None
        if migrate:
            migration = migrate_plan(
                document,
                target_version=target_version,
                node_id_factory=self.node_id_factory,
            )
            document = migration.get("plan")

        validation = self.validate_template(document)
        issues = list((migration or {}).get("issues", [])) + list(validation.get("issues", []))
        if has_error_issues(issues):
            return {
                "ok": False,
                "path": str(target),
                "plan": document,
                "issues": issues,
                "migration": migration,
            }

        saved = save_plan(target, document)
        return {
            "ok": True,
            "path": saved["path"],
            "plan": document,
            "issues": issues,
            "migration": migration,
        }


def validate_plan_template(plan):
    issues = []
    if not isinstance(plan, dict):
        return [
            make_issue(
                "error",
                "invalid_plan_template",
                "计划模板必须是 JSON object。",
                path="",
                source="PlanTemplateService",
            )
        ]

    template_type = str(plan.get("template_type") or "").strip()
    if template_type and template_type != WORKFLOW_PLAN_TEMPLATE_TYPE:
        issues.append(make_issue(
            "error",
            "invalid_template_type",
            "template_type 必须是 workflow_plan。",
            path="/template_type",
            source="PlanTemplateService",
        ))
    elif not template_type:
        issues.append(make_issue(
            "warning",
            "missing_template_type",
            "计划模板缺少 template_type，迁移时会补为 workflow_plan。",
            path="/template_type",
            source="PlanTemplateService",
        ))

    nodes = plan.get("nodes")
    if nodes is None:
        issues.append(make_issue(
            "warning",
            "missing_nodes",
            "计划模板缺少 nodes，迁移时会按空节点列表处理。",
            path="/nodes",
            source="PlanTemplateService",
        ))
    elif not isinstance(nodes, list):
        issues.append(make_issue(
            "error",
            "invalid_nodes",
            "计划模板 nodes 必须是 list。",
            path="/nodes",
            source="PlanTemplateService",
        ))
    return issues


def _first_non_error_message(issues):
    for issue in issues or []:
        if issue.get("severity") in {"warning", "info"}:
            return issue.get("message", "")
    return ""
