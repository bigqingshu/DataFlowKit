# -*- coding: utf-8 -*-
"""Shared issue schema helpers for workflow/engine APIs."""

from __future__ import annotations


KNOWN_SEVERITIES = {"error", "warning", "info"}


def make_issue(
    severity,
    code,
    message,
    *,
    path="",
    node_index=None,
    node_type="",
    node_type_id="",
    suggestion="",
    source="",
    **extra,
):
    """Return a normalized issue object that can be shown by any frontend."""

    normalized_severity = str(severity or "error").strip().lower()
    if normalized_severity not in KNOWN_SEVERITIES:
        normalized_severity = "error"
    payload = {
        "severity": normalized_severity,
        "code": str(code or "unknown_issue"),
        "message": str(message or ""),
    }
    if path:
        payload["path"] = str(path)
    if node_index is not None:
        payload["node_index"] = int(node_index)
    if node_type:
        payload["node_type"] = str(node_type)
    if node_type_id:
        payload["node_type_id"] = str(node_type_id)
    if suggestion:
        payload["suggestion"] = str(suggestion)
    if source:
        payload["source"] = str(source)
    payload.update(extra)
    return payload


def normalize_issue(issue, *, default_severity="error"):
    """Return *issue* as a normalized issue dict while preserving extensions."""

    if not isinstance(issue, dict):
        return make_issue(default_severity, "invalid_issue", str(issue or ""))
    payload = dict(issue)
    severity = str(payload.get("severity") or default_severity or "error").strip().lower()
    if severity not in KNOWN_SEVERITIES:
        severity = str(default_severity or "error").strip().lower()
    if severity not in KNOWN_SEVERITIES:
        severity = "error"
    payload["severity"] = severity
    payload["code"] = str(payload.get("code") or "unknown_issue")
    payload["message"] = str(payload.get("message") or "")
    return payload


def normalize_issues(issues, *, default_severity="error"):
    return [
        normalize_issue(issue, default_severity=default_severity)
        for issue in (issues or [])
    ]


def is_error_issue(issue):
    return normalize_issue(issue).get("severity") == "error"


def has_error_issues(issues):
    return any(is_error_issue(issue) for issue in (issues or []))
