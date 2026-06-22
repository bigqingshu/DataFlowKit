# -*- coding: utf-8 -*-
"""UI-free workflow plan file helpers."""

from __future__ import annotations

import copy
from pathlib import Path

from shared.atomic_json_utils import atomic_write_json, load_json_with_backup


def list_plan_templates(plan_dir):
    """Return JSON workflow template candidates under *plan_dir*."""

    root = Path(plan_dir)
    if not root.exists():
        return []
    return [
        {
            "name": path.stem,
            "path": str(path),
            "suffix": path.suffix,
        }
        for path in sorted(root.glob("*.json"))
        if path.is_file()
    ]


def load_plan(path):
    """Load a workflow plan JSON object with backup recovery metadata."""

    target = Path(path)
    data, info = load_json_with_backup(target)
    if not isinstance(data, dict):
        raise ValueError("计划文件必须是 JSON object")
    return {
        "path": str(target),
        "plan": data,
        "info": dict(info or {}),
        "warning": (info or {}).get("warning", ""),
    }


def build_plan_document(
    plan,
    *,
    headers=None,
    rows=None,
    output_mode=None,
    output_table=None,
    backup_before_overwrite=None,
):
    """Return a plan copy with current table and output settings attached."""

    result = copy.deepcopy(plan) if isinstance(plan, dict) else {}
    if headers is not None:
        result["headers"] = list(headers)
    if rows is not None:
        result["rows"] = [list(row) for row in rows]
    if output_mode is not None:
        result["output_mode"] = str(output_mode)
    if output_table is not None:
        result["output_table"] = str(output_table)
    if backup_before_overwrite is not None:
        result["backup_before_overwrite"] = bool(backup_before_overwrite)
    return result


def save_plan(path, plan):
    """Persist a workflow plan JSON object atomically."""

    if not isinstance(plan, dict):
        raise ValueError("计划内容必须是 JSON object")
    target = atomic_write_json(path, plan)
    return {
        "ok": True,
        "path": str(target),
    }
