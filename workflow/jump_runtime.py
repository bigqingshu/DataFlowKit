# -*- coding: utf-8 -*-
"""Runtime helpers for workflow jump nodes."""

from datetime import datetime


def append_jump_runtime_log(context, event, now_factory=None):
    if not isinstance(context, dict):
        return None
    payload = dict(event or {})
    now = now_factory() if callable(now_factory) else datetime.now()
    payload.setdefault("time", now.strftime("%Y-%m-%d %H:%M:%S"))
    current = context.get("current_node_info", {}) if isinstance(context.get("current_node_info"), dict) else {}
    payload.setdefault("node_id", current.get("node_id", ""))
    payload.setdefault("node_name", current.get("node_name", ""))
    payload.setdefault("node_type", current.get("node_type", ""))
    payload.setdefault("node_index", current.get("node_index", ""))
    context.setdefault("jump_logs", []).append(payload)
    return payload


def apply_jump_anchor_node(window, headers, rows, config, context=None):
    anchor_id = str(config.get("anchor_id", "") or "").strip()
    anchor_name = str(config.get("anchor_name", "") or "").strip()
    detail = f"定位锚点：{anchor_id or '未命名'}"
    if anchor_name:
        detail += f" / {anchor_name}"
    window.append_jump_runtime_log(context, {
        "event": "anchor",
        "anchor_id": anchor_id,
        "anchor_name": anchor_name,
        "status": "ok",
        "message": detail,
    })
    return list(headers), [list(r) for r in rows], detail


def resolve_jump_target_control(window, anchor_id, context=None, anchors_info=None, nodes=None, source="跳转"):
    target_idx, message = window.resolve_jump_anchor_index(anchor_id, anchors_info=anchors_info, nodes=nodes)
    if target_idx is None:
        window.append_jump_runtime_log(context, {
            "event": source,
            "target_anchor_id": str(anchor_id or "").strip(),
            "status": "warning",
            "message": message + "，默认不跳转",
        })
        return {"jump_to": None, "message": message + "，默认不跳转", "status": "warning"}
    window.append_jump_runtime_log(context, {
        "event": source,
        "target_anchor_id": str(anchor_id or "").strip(),
        "target_index": target_idx,
        "status": "ok",
        "message": f"跳转到锚点 {anchor_id}（节点 {target_idx + 1}）",
    })
    return {"jump_to": target_idx, "message": f"跳转到锚点 {anchor_id}（节点 {target_idx + 1}）", "status": "ok"}


def apply_unconditional_jump_node(window, headers, rows, config, context=None, anchors_info=None, nodes=None):
    target = str(config.get("target_anchor_id", "") or "").strip()
    ctrl = window.resolve_jump_target_control(target, context=context, anchors_info=anchors_info, nodes=nodes, source="unconditional_jump")
    return list(headers), [list(r) for r in rows], "无条件跳转：" + ctrl.get("message", ""), ctrl
