# -*- coding: utf-8 -*-
"""Pure helpers for group/subworkflow nodes."""

import copy
import json
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


GROUP_CONFIG_DEFAULTS = {
    "input_source_type": "当前工作表",
    "input_sqlite_table": "",
    "input_transit_table": "",
    "input_fields": list,
    "input_mapping": dict,
    "input_defaults": dict,
    "missing_input_policy": "缺失填空",
    "main_output_mode": "输出为当前工作表",
    "save_to_transit": False,
    "output_transit_conflict_mode": "覆盖整表",
    "save_to_sqlite": False,
    "output_sqlite_mode": "自动加时间戳新表",
    "sqlite_save_in_preview": False,
    "transit_scope": "组内中转私有",
    "nodes": list,
}

GROUP_MAIN_OUTPUT_CHOICES = ["输出为当前工作表", "透传原当前表"]
GROUP_TRANSIT_SCOPE_CHOICES = ["组内中转私有", "允许输出到外部"]
GROUP_TRANSIT_CONFLICT_CHOICES = ["覆盖整表", "追加行", "自动加时间戳新建"]
GROUP_SQLITE_MODE_CHOICES = ["覆盖表", "追加到已有表", "自动加时间戳新表", "不覆盖，存在则报错"]
GROUP_OUTPUT_HINT_TEXT = "建议：中转副表可用于后续节点预览；SQLite 默认只在【执行计划】时保存，避免刷新配置界面误写库。"
GROUP_FORBIDDEN_INNER_NODE_TYPES = ("循环执行起点", "循环判断回跳")


def ensure_group_config_defaults(config):
    for key, default in GROUP_CONFIG_DEFAULTS.items():
        if key not in config:
            config[key] = default() if callable(default) else default
    fallback_name = config.get("group_name", "节点组结果")
    config.setdefault("output_transit_name", fallback_name)
    config.setdefault("output_sqlite_table", fallback_name)
    return config


def build_group_output_config_state(config):
    group_name = config.get("group_name", "节点组结果")
    return {
        "main_output_mode": config.get("main_output_mode", "输出为当前工作表"),
        "main_output_choices": list(GROUP_MAIN_OUTPUT_CHOICES),
        "transit_scope": config.get("transit_scope", "组内中转私有"),
        "transit_scope_choices": list(GROUP_TRANSIT_SCOPE_CHOICES),
        "save_to_transit": bool(config.get("save_to_transit", False)),
        "output_transit_name": config.get("output_transit_name") or group_name,
        "output_transit_conflict_mode": config.get("output_transit_conflict_mode", "覆盖整表"),
        "output_transit_conflict_choices": list(GROUP_TRANSIT_CONFLICT_CHOICES),
        "save_to_sqlite": bool(config.get("save_to_sqlite", False)),
        "output_sqlite_table": config.get("output_sqlite_table") or group_name,
        "output_sqlite_mode": config.get("output_sqlite_mode", "自动加时间戳新表"),
        "output_sqlite_mode_choices": list(GROUP_SQLITE_MODE_CHOICES),
        "sqlite_save_in_preview": bool(config.get("sqlite_save_in_preview", False)),
        "hint_text": GROUP_OUTPUT_HINT_TEXT,
    }


def group_input_fields_text(config):
    return ",".join(parse_group_input_fields(config))


def update_group_input_fields_config(config, text):
    fields = unique_keep_order([x.strip() for x in re.split(r"[,，;；\n]+", str(text or "")) if x.strip()])
    config["input_fields"] = fields
    config.setdefault("input_mapping", {})
    config.setdefault("input_defaults", {})
    valid = set(fields)
    config["input_mapping"] = {k: v for k, v in config.get("input_mapping", {}).items() if k in valid}
    config["input_defaults"] = {k: v for k, v in config.get("input_defaults", {}).items() if k in valid}
    return fields


def group_source_headers_for_mapping(source_type, current_headers, transit_tables=None, transit_name="", sqlite_columns=None):
    source_type = source_type or "当前工作表"
    if source_type == "当前工作表":
        return list(current_headers or [])
    if source_type == "中转副表":
        item = (transit_tables or {}).get(transit_name, {})
        return list((item or {}).get("headers", []) or [])
    if source_type == "SQLite表":
        return list(sqlite_columns or [])
    return list(current_headers or [])


def group_source_field_combo_state(current_value, source_headers):
    values = [""] + list(source_headers or [])
    value = current_value if current_value in values else ""
    return {"values": values, "value": value}


def group_selected_input_state(config, current_value):
    fields = parse_group_input_fields(config)
    value = current_value if current_value in fields else (fields[0] if fields else "")
    return {"values": fields, "value": value}


def group_mapping_rows(config):
    fields = parse_group_input_fields(config)
    mapping = config.setdefault("input_mapping", {})
    defaults = config.setdefault("input_defaults", {})
    return [(field, mapping.get(field, ""), defaults.get(field, "")) for field in fields]


def group_mapping_detail(config, key):
    mapping = config.setdefault("input_mapping", {})
    defaults = config.setdefault("input_defaults", {})
    key = str(key or "").strip()
    return {
        "source_field": mapping.get(key, "") if key else "",
        "default_value": defaults.get(key, "") if key else "",
    }


def group_mapping_selection_detail(values):
    values = list(values or [])
    return {
        "key": str(values[0]) if values else "",
        "source_field": str(values[1]) if len(values) > 1 else "",
        "default_value": str(values[2]) if len(values) > 2 else "",
    }


def apply_group_mapping(config, key, source_field, default_value):
    key = str(key or "").strip()
    if not key:
        return {"ok": False, "message": "请先在组入口字段下拉框中选择一个入口字段。"}
    if key not in parse_group_input_fields(config):
        return {"ok": False, "message": f"入口字段不存在：{key}\n请先在上方“组入口字段”中添加。"}
    config.setdefault("input_mapping", {})[key] = str(source_field or "").strip()
    config.setdefault("input_defaults", {})[key] = default_value
    return {"ok": True, "message": ""}


def auto_group_mapping_by_name(config, source_headers):
    source_headers = list(source_headers or [])
    lower_map = {str(header).lower(): header for header in source_headers}
    mapping = config.setdefault("input_mapping", {})
    for field in parse_group_input_fields(config):
        if field in source_headers:
            mapping[field] = field
        elif not mapping.get(field):
            mapping[field] = lower_map.get(str(field).lower(), "")
    return mapping


def use_source_headers_as_group_inputs(config, source_headers):
    headers = list(source_headers or [])
    config["input_fields"] = headers
    config["input_mapping"] = {header: header for header in headers}
    config.setdefault("input_defaults", {})
    return headers


def apply_inferred_group_inputs(config, inferred, source_headers, merge=False):
    inferred = list(inferred or [])
    current = parse_group_input_fields(config)
    new_fields = unique_keep_order(current + inferred) if merge else inferred
    old_mapping = dict(config.get("input_mapping", {}) or {})
    old_defaults = dict(config.get("input_defaults", {}) or {})
    source_headers = list(source_headers or [])
    lower_source = {str(header).lower(): header for header in source_headers}
    config["input_fields"] = list(new_fields)
    new_mapping = {}
    for field in new_fields:
        if old_mapping.get(field):
            new_mapping[field] = old_mapping.get(field)
        elif field in source_headers:
            new_mapping[field] = field
        else:
            new_mapping[field] = lower_source.get(str(field).lower(), "")
    config["input_mapping"] = new_mapping
    config["input_defaults"] = {field: old_defaults.get(field, "") for field in new_fields}
    return new_fields


def group_infer_input_apply_decision(config, inferred, answer=None):
    inferred = list(inferred or [])
    if not inferred:
        return {
            "action": "show_empty",
            "merge": False,
            "fields_text": "",
            "message_prefix": "没有从组内节点推导到需要外部传入的入口字段。",
        }
    current = parse_group_input_fields(config)
    if not current:
        return {
            "action": "apply",
            "merge": False,
            "fields_text": ",".join(inferred),
            "message_prefix": "",
        }
    if answer is None:
        return {
            "action": "show_detail",
            "merge": False,
            "fields_text": "",
            "message_prefix": "",
        }
    merge = not bool(answer)
    fields = unique_keep_order(current + inferred) if merge else inferred
    return {
        "action": "apply",
        "merge": merge,
        "fields_text": ",".join(fields),
        "message_prefix": "",
    }


def group_node_label(index, node):
    mark = "✓" if node.get("enabled", True) else "×"
    return f"{index + 1:02d}. [{mark}] {node.get('type','')} - {node.get('name','')}"


def group_node_labels(nodes):
    return [group_node_label(index, node) for index, node in enumerate(nodes or [])]


def group_inner_node_type_values(node_type_values, forbidden_types=None):
    forbidden = set(forbidden_types or GROUP_FORBIDDEN_INNER_NODE_TYPES)
    return [value for value in list(node_type_values or []) if value not in forbidden]


def make_group_inner_node(
    node_type,
    plugin_display_map=None,
    plugin_registry=None,
    plugin_config_factory=None,
    default_name_factory=None,
    default_config_factory=None,
    forbidden_types=None,
):
    forbidden = tuple(forbidden_types or GROUP_FORBIDDEN_INNER_NODE_TYPES)
    if node_type in forbidden:
        raise ValueError("第一版节点组不支持组内循环执行起点 / 循环判断回跳。")

    plugin_display_map = plugin_display_map or {}
    plugin_registry = plugin_registry or {}
    if node_type in plugin_display_map:
        plugin_id = plugin_display_map[node_type]
        plugin_info = plugin_registry.get(plugin_id, {}).get("info", {})
        config = plugin_config_factory(plugin_id) if callable(plugin_config_factory) else {}
        return {
            "enabled": True,
            "type": "插件节点",
            "name": plugin_info.get("name", plugin_id),
            "config": copy.deepcopy(config),
        }

    name = default_name_factory(node_type) if callable(default_name_factory) else node_type
    config = default_config_factory(node_type) if callable(default_config_factory) else {}
    return {
        "enabled": True,
        "type": node_type,
        "name": name,
        "config": copy.deepcopy(config),
    }


def add_group_inner_node(config, node_type, **kwargs):
    node = make_group_inner_node(node_type, **kwargs)
    nodes = config.setdefault("nodes", [])
    if not isinstance(nodes, list):
        nodes = []
        config["nodes"] = nodes
    nodes.append(node)
    return node, len(nodes) - 1


def delete_group_inner_node(nodes, index):
    result = list(nodes or [])
    if index is None or index < 0 or index >= len(result):
        return result, None
    del result[index]
    next_index = min(index, len(result) - 1) if result else None
    return result, next_index


def move_group_inner_node(nodes, index, delta):
    result = list(nodes or [])
    if index is None:
        return result, None
    target = index + delta
    if index < 0 or index >= len(result) or target < 0 or target >= len(result):
        return result, index
    result[index], result[target] = result[target], result[index]
    return result, target


def copy_group_inner_node(nodes, index):
    result = [copy.deepcopy(node) for node in (nodes or [])]
    if index is None or index < 0 or index >= len(result):
        return result, None
    new_node = copy.deepcopy(result[index])
    new_node["name"] = f"{new_node.get('name', new_node.get('type'))}_复制"
    result.insert(index + 1, new_node)
    return result, index + 1


def toggle_group_inner_node_enabled(nodes, index):
    result = [copy.deepcopy(node) for node in (nodes or [])]
    if index is None or index < 0 or index >= len(result):
        return result, None
    result[index]["enabled"] = not result[index].get("enabled", True)
    return result, index


def apply_group_inner_node_list_action(nodes, index, action, delta=0):
    if action == "delete":
        return delete_group_inner_node(nodes, index)
    if action == "move":
        return move_group_inner_node(nodes, index, delta)
    if action == "copy":
        return copy_group_inner_node(nodes, index)
    if action == "toggle":
        return toggle_group_inner_node_enabled(nodes, index)
    raise ValueError(f"未知组内节点操作：{action}")


def parse_group_inner_node_json(text, forbidden_types=None):
    forbidden = tuple(forbidden_types or GROUP_FORBIDDEN_INNER_NODE_TYPES)
    try:
        data = json.loads(text)
    except Exception as exc:
        raise ValueError(str(exc)) from exc
    if not isinstance(data, dict) or "type" not in data:
        raise ValueError("节点 JSON 必须是包含 type 的对象。")
    if data.get("type") in forbidden:
        raise ValueError("第一版节点组不支持组内循环节点。")
    return data


def apply_group_template_config(config, template_config):
    if not isinstance(template_config, dict):
        raise ValueError("组模板配置必须是对象。")
    config.clear()
    config.update(template_config)
    return config


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
