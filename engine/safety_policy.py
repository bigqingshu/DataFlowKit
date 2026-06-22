# -*- coding: utf-8 -*-
"""Safety policy helpers for preview, dry-run, and real execution modes."""

from __future__ import annotations

from dataclasses import dataclass


PREVIEW_MODES = {"preview", "预览"}
DRY_RUN_MODES = {"dry_run", "dry-run", "dryrun", "simulate", "simulation", "试运行"}
RUN_MODES = {"run", "execute", "执行", "运行"}


@dataclass(frozen=True)
class SafetyPolicy:
    mode: str
    execute_actions: bool
    dry_run: bool
    reason: str = ""

    @property
    def preview(self):
        return self.mode == "preview"

    def to_dict(self):
        return {
            "mode": self.mode,
            "execute_actions": bool(self.execute_actions),
            "dry_run": bool(self.dry_run),
            "preview": bool(self.preview),
            "reason": self.reason,
        }


def resolve_safety_policy(mode=None, *, execute_actions=False, dry_run=False):
    """Resolve user intent into the effective side-effect policy."""

    normalized_mode = _normalize_mode(mode)
    if normalized_mode == "preview":
        return SafetyPolicy(
            mode="preview",
            execute_actions=False,
            dry_run=True,
            reason="preview mode never executes side-effect actions",
        )
    if bool(dry_run) or normalized_mode == "dry_run":
        return SafetyPolicy(
            mode="dry_run",
            execute_actions=False,
            dry_run=True,
            reason="dry_run requested; side-effect actions are disabled",
        )
    return SafetyPolicy(
        mode="run",
        execute_actions=bool(execute_actions),
        dry_run=False,
        reason="execute_actions requested" if execute_actions else "side-effect actions disabled",
    )


def _normalize_mode(mode):
    text = str(mode or "run").strip()
    lower = text.lower()
    if lower in PREVIEW_MODES or text in PREVIEW_MODES:
        return "preview"
    if lower in DRY_RUN_MODES or text in DRY_RUN_MODES:
        return "dry_run"
    if lower in RUN_MODES or text in RUN_MODES:
        return "run"
    return "run"
