# -*- coding: utf-8 -*-
"""Pure helpers for group/subworkflow nodes."""

import copy
import re

from core.data_utils import normalize_rows, safe_cell


GROUP_CONTEXT_KEYS_TO_INHERIT = [
    "workflow_snapshot",
    "allow_selected_columns_write_in_preview",
    "selected_columns_config_preview_only",
    "progress_callback",
    "cancel_event",
    "table_access_policy",
]


def unique_keep_order(values):
    """按原顺序去重，保留第一个非空字符串。"""
    result = []
    seen = set()
    for value in values or []:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def parse_group_input_fields(config):
    """解析节点组入口字段。为空时表示兼容旧版：直接传入来源整表。"""
    raw = config.get("input_fields", [])
    if isinstance(raw, str):
        fields = [x.strip() for x in re.split(r"[,，;；\n]+", raw) if x.strip()]
    elif isinstance(raw, (list, tuple)):
        fields = [str(x).strip() for x in raw if str(x).strip()]
    else:
        fields = []
    return unique_keep_order(fields)


def normalize_group_transit_conflict_mode(mode):
    text = str(mode or "覆盖整表")
    if "追加" in text:
        return "追加"
    if "时间戳" in text or "新建" in text:
        return "自动加时间戳"
    return "覆盖"


def normalize_group_sqlite_mode(mode):
    text = str(mode or "自动加时间戳新表")
    if "追加" in text:
        return "append"
    if "覆盖" in text:
        return "replace"
    if "报错" in text or "不覆盖" in text:
        return "fail"
    return "timestamp"


def build_group_input_table(source_headers, source_rows, config):
    """
    根据入口字段和映射生成组内标准表。
    - input_fields 为空：兼容旧版，直接把来源整表传给组内。
    - input_fields 非空：组内 headers 固定为 input_fields，rows 按 input_mapping 取值。
    """
    input_fields = parse_group_input_fields(config)
    if not input_fields:
        return list(source_headers), [list(r) for r in source_rows], "入口字段未设置，使用来源整表"

    source_headers = list(source_headers or [])
    source_rows = [list(r) for r in normalize_rows(source_rows, len(source_headers))]
    mapping = config.get("input_mapping", {}) or {}
    defaults = config.get("input_defaults", {}) or {}
    missing_policy = config.get("missing_input_policy", "缺失填空")
    src_index = {h: i for i, h in enumerate(source_headers)}

    missing = []
    result_rows = []
    for row in source_rows:
        out = []
        for field in input_fields:
            mapped = str(mapping.get(field, "")).strip()
            if mapped and mapped in src_index:
                out.append(safe_cell(row, src_index[mapped]))
            else:
                if mapped:
                    missing.append(f"{field}->{mapped}")
                else:
                    missing.append(field)
                out.append(str(defaults.get(field, "")))
        result_rows.append(out)

    if missing_policy == "缺失报错" and missing:
        show = "、".join(unique_keep_order(missing)[:20])
        raise ValueError(f"节点组入口映射缺失字段：{show}")

    return input_fields, result_rows, f"入口字段映射 {len(input_fields)} 列"


def ensure_group_parent_context(parent_context):
    parent = parent_context if parent_context is not None else {
        "transit_tables": {},
        "loop_states": {},
        "loop_results": {},
    }
    parent.setdefault("transit_tables", {})
    parent.setdefault("loop_states", {})
    parent.setdefault("loop_results", {})
    return parent


def make_group_child_context(parent_context, config):
    """为子工作流创建上下文。默认隔离，避免组内保存的临时中转污染父级。"""
    parent_context = ensure_group_parent_context(parent_context)

    if config.get("transit_scope", "组内中转私有") == "允许输出到外部":
        # 兼容旧版“允许输出到外部”：组内保存中转数据可直接进入父级 context。
        return parent_context

    child = {
        "transit_tables": copy.deepcopy(parent_context.get("transit_tables", {})),
        "loop_states": {},
        "loop_results": {},
        "group_runtime": True,
        "group_name": config.get("group_name", "节点组"),
    }
    for key in GROUP_CONTEXT_KEYS_TO_INHERIT:
        if key in parent_context:
            child[key] = parent_context[key]
    return child


def build_empty_group_stat(group_name, source_name, input_stat, output_parts=None, passthrough_current=False):
    output_parts = list(output_parts or [])
    output_text = ("；" + "；".join(output_parts)) if output_parts else ""
    if passthrough_current:
        return f"节点组【{group_name}】为空，透传原当前表；{input_stat}" + output_text
    return f"节点组【{group_name}】为空，输出入口表；来源={source_name}；{input_stat}" + output_text


def build_group_node_log(index, node_type, before_shape, after_shape, stat):
    return f"{index}.{node_type} {before_shape[0]}×{before_shape[1]}→{after_shape[0]}×{after_shape[1]} {stat}"


def merge_group_child_audit_logs(parent_context, child_context):
    if child_context is parent_context:
        return
    child_logs = child_context.get("table_access_logs", []) if isinstance(child_context, dict) else []
    if child_logs:
        parent_context.setdefault("table_access_logs", []).extend(child_logs)
        child_context["table_access_logs"] = []


def build_group_final_output(headers, rows, cur_headers, cur_rows, config):
    if config.get("main_output_mode", "输出为当前工作表") == "透传原当前表":
        return list(headers), [list(r) for r in rows], "主输出=透传原当前表"
    return list(cur_headers), [list(r) for r in cur_rows], "主输出=组结果作为当前表"


def build_group_status_text(group_name, source_name, input_stat, main_stat, logs=None, output_parts=None, log_limit=5):
    logs = list(logs or [])
    output_parts = list(output_parts or [])
    short = "；".join(logs[:log_limit])
    if len(logs) > log_limit:
        short += f"；... 共 {len(logs)} 个内部节点"
    parts = [f"来源={source_name}", input_stat, main_stat]
    if output_parts:
        parts.extend(output_parts)
    if short:
        parts.append(short)
    return f"节点组【{group_name}】完成：" + "；".join(parts)
