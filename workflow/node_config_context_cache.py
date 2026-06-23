# -*- coding: utf-8 -*-
"""UI-free helpers for reusing explicit preview results in node config forms."""

from __future__ import annotations

import copy
import json


def plan_context_signature(plan):
    """Return a stable signature for the parts of a plan that affect field flow."""
    if not isinstance(plan, dict):
        return ""
    payload = {
        "nodes": copy.deepcopy(plan.get("nodes") or []),
        "table_access_policy": plan.get("table_access_policy", ""),
    }
    try:
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    except TypeError:
        return str(payload)


def build_preview_context_cache(*, plan=None, stop_index=None, headers=None, rows=None):
    effective_stop_index = _effective_stop_index(plan, stop_index)
    cached_headers = [str(item) for item in (headers or []) if str(item).strip()]
    cached_rows = [list(row) for row in (rows or [])]
    return {
        "schema_version": "node_config_preview_context.v1",
        "plan_signature": plan_context_signature(plan),
        "stop_index": effective_stop_index,
        "headers": cached_headers,
        "rows": cached_rows,
        "row_count": len(cached_rows),
        "column_count": len(cached_headers),
    }


def resolve_node_config_headers(*, selected_index=None, current_headers=None, preview_cache=None, plan=None):
    current = [str(item) for item in (current_headers or []) if str(item).strip()]
    selected = _optional_int(selected_index)
    if selected is None:
        return _header_result(current, "current_headers", "selection_missing", selected, preview_cache)

    cache = preview_cache if isinstance(preview_cache, dict) else {}
    cached_headers = [str(item) for item in (cache.get("headers") or []) if str(item).strip()]
    if not cached_headers:
        return _header_result(current, "current_headers", "cache_empty", selected, cache)

    current_signature = plan_context_signature(plan)
    cache_signature = str(cache.get("plan_signature") or "")
    if cache_signature and current_signature and cache_signature != current_signature:
        return _header_result(current, "current_headers", "cache_stale_plan", selected, cache)

    stop_index = _optional_int(cache.get("stop_index"))
    if stop_index is None:
        return _header_result(current, "current_headers", "cache_stop_index_missing", selected, cache)

    if selected > 0 and stop_index == selected - 1:
        return _header_result(cached_headers, "preview_cache", "cache_matches_previous_node", selected, cache)

    return _header_result(current, "current_headers", "cache_not_for_selected_node", selected, cache)


def normalize_current_table_field_reference(field, headers):
    text = str(field or "").strip()
    header_set = set(headers or [])
    if text in header_set:
        return text
    prefix = "当前表."
    if text.startswith(prefix):
        stripped = text[len(prefix):]
        if stripped in header_set:
            return stripped
    return text


def _header_result(headers, source, reason, selected_index, cache):
    return {
        "headers": list(headers or []),
        "source": source,
        "reason": reason,
        "selected_index": selected_index,
        "cache_stop_index": _optional_int((cache or {}).get("stop_index")) if isinstance(cache, dict) else None,
    }


def _effective_stop_index(plan, stop_index):
    value = _optional_int(stop_index)
    if value is not None:
        return value
    if isinstance(plan, dict):
        nodes = plan.get("nodes") or []
        if nodes:
            return len(nodes) - 1
    return None


def _optional_int(value):
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
