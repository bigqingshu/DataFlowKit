# -*- coding: utf-8 -*-
import argparse
import copy
import json
import re
import sys
import traceback
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from shared.datetime_parse_utils import (
    DATE_INPUT_STRUCTURES,
    DATE_ORDERS,
    DATE_YEAR_RULES,
    default_date_parser_config,
    parse_date_value,
)
from shared.atomic_json_utils import atomic_write_json, load_json_with_backup

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, simpledialog, ttk
except Exception:  # pragma: no cover
    tk = None
    ttk = None
    messagebox = None
    simpledialog = None
    filedialog = None


PLUGIN_INFO = {
    "id": "visual_mapping_write_plan_v1",
    "name": "可视化映射写入计划V1",
    "version": "1.0.0",
    "api_version": "1.0",
    "category": "文档处理",
    "description": "接收文档读取表和新内容表，通过可视化单元格映射生成 Word/Excel 写入节点可直接使用的写入计划表。",
    "input_type": "table",
    "output_type": "table",
    "danger_level": "safe_readonly",
}

SETTINGS_FILE = "visual_mapping_write_plan_settings.json"
CONFIG_SCHEMA_VERSION = "DataFlowKit.visual_mapping.config.v1"
CONFIG_PROTOCOL_FAMILY = "plugin_complex_config"
CONFIG_ACTION_STATE_SCHEMA_VERSION = "plugin_config_action_state.v1"
CONFIG_SECTIONS = {"rules", "features", "global_rules", "linked_rules"}
MAX_AREA_SCAN_ROWS = 100000
FEATURE_ANY_LABEL = "不限制"
SHEET_ALL_LABEL = "所有表"
BATCH_TARGET_CONDITION_VALUE = "条件命中值"
BATCH_TARGET_FULL_TEXT = "原文整格"
BATCH_TARGET_FULL_MATCH = "完整正则匹配"
BATCH_TARGET_CHOICES = [BATCH_TARGET_CONDITION_VALUE, BATCH_TARGET_FULL_TEXT, BATCH_TARGET_FULL_MATCH]
REPLACE_ROW_MATCH_INDEX = "按匹配行号"
REPLACE_ROW_CONTENT_ROW = "当前内容行"
REPLACE_ROW_FIRST = "第一行"
REPLACE_ROW_FIXED = "固定行号"
REPLACE_ROW_HIT_INDEX = "按命中序号"
REPLACE_ROW_POLICY_CHOICES = [
    REPLACE_ROW_MATCH_INDEX,
    REPLACE_ROW_CONTENT_ROW,
    REPLACE_ROW_FIRST,
    REPLACE_ROW_FIXED,
    REPLACE_ROW_HIT_INDEX,
]
LINKED_RULE_ANY = "任意已变化规则"
LINK_TARGET_TRIGGER_OFFSET = "触发格偏移"
LINK_TARGET_FIXED_CELL = "指定坐标"
LINK_TARGET_ANCHOR_OFFSET = "锚点偏移"
LINK_TARGET_MODES = [LINK_TARGET_TRIGGER_OFFSET, LINK_TARGET_FIXED_CELL, LINK_TARGET_ANCHOR_OFFSET]
LINK_VALUE_FIXED = "固定值"
LINK_VALUE_TRIGGER_NEW = "触发新值"
LINK_VALUE_TRIGGER_OLD = "触发旧值"
LINK_VALUE_CONTENT_FIELD = "新内容字段"
LINK_VALUE_TEMPLATE = "模板"
LINK_VALUE_SOURCES = [LINK_VALUE_FIXED, LINK_VALUE_TRIGGER_NEW, LINK_VALUE_TRIGGER_OLD, LINK_VALUE_CONTENT_FIELD, LINK_VALUE_TEMPLATE]
LINK_WRITE_REPLACE = "值替换"
LINK_WRITE_APPEND = "值追加"
LINK_WRITE_PREPEND = "值前置"
LINK_WRITE_REGEX = "正则替换"
LINK_WRITE_MODES = [LINK_WRITE_REPLACE, LINK_WRITE_APPEND, LINK_WRITE_PREPEND, LINK_WRITE_REGEX]
LINK_OVERFLOW_SKIP = "区域满时跳过"
LINK_OVERFLOW_MIN_MARKER_ROW = "区域满时替换最小圈号行"
LINK_OVERFLOW_MIN_DATE_ROW = "区域满时替换最早日期行"
LINK_OVERFLOW_SLOT_RULE = "按槽位判定替换"
LINK_OVERFLOW_POLICIES = [
    LINK_OVERFLOW_SKIP,
    LINK_OVERFLOW_SLOT_RULE,
    LINK_OVERFLOW_MIN_MARKER_ROW,
    LINK_OVERFLOW_MIN_DATE_ROW,
]
SLOT_MODE_SEQUENCE_DATE = "文档统一序号优先（日期兜底）"
SLOT_MODE_SEQUENCE_ONLY = "仅文档统一序号"
SLOT_MODE_DATE_ONLY = "仅日期"
SLOT_JUDGEMENT_MODES = [
    SLOT_MODE_SEQUENCE_DATE,
    SLOT_MODE_SEQUENCE_ONLY,
    SLOT_MODE_DATE_ONLY,
]
SLOT_INVALID_SKIP = "跳过"
SLOT_INVALID_FIRST_ROW = "使用最上方行"
SLOT_INVALID_ERROR = "报错"
SLOT_INVALID_POLICIES = [SLOT_INVALID_SKIP, SLOT_INVALID_FIRST_ROW, SLOT_INVALID_ERROR]
LINK_ACTION_SHARED_SLOT = "共享槽位偏移"
LINK_ACTION_TRIGGER_OFFSET = "触发格偏移"
LINK_ACTION_TARGET_MODES = [LINK_ACTION_SHARED_SLOT, LINK_ACTION_TRIGGER_OFFSET]
DIRECT_WRITE_STRATEGY = "直接定位写入"
GLOBAL_SCOPE_SPECIAL_OBJECTS = "全文及特殊对象"
CONFIG_WINDOW_WIDTH = 1360
CONFIG_WINDOW_HEIGHT = 820
CONFIG_WINDOW_MIN_WIDTH = 1120
CONFIG_WINDOW_MIN_HEIGHT = 650

OUTPUT_HEADERS = [
    "source_file",
    "target_file",
    "block_type",
    "sheet_name",
    "row_index",
    "col_index",
    "cell_address",
    "text",
    "old_text",
    "mapping_field",
    "content_row",
    "match_status",
    "match_rule",
    "anchor_rule",
    "source_match_detail",
    "anchor_match_detail",
    "write_note",
    "write_strategy",
    "meta_json",
    "replace_scope",
    "rule_old_text",
    "rule_new_text",
]


def get_parameter_schema():
    return [
        {"name": "doc_table_alias", "label": "文档读取表别名", "type": "input_table_select", "default": "当前表"},
        {"name": "content_table_alias", "label": "新内容表别名", "type": "input_table_select", "default": "新内容表"},
        {"name": "replace_aux_table_alias", "label": "替换辅助表别名", "type": "input_table_select", "default": "替换辅助表"},
        {"name": "source_file_field", "label": "源文件字段", "type": "dynamic_select", "default": "source_file", "allow_custom": True},
        {"name": "planned_file_field", "label": "拟定新文件字段", "type": "dynamic_select", "default": "target_file", "allow_custom": True},
        {
            "name": "empty_policy",
            "label": "新内容为空时",
            "type": "select",
            "choices": ["跳过", "写入空字符串", "报错"],
            "default": "跳过",
        },
        {
            "name": "debug_output",
            "label": "输出失败调试行",
            "type": "bool",
            "default": False,
        },
        {"name": "config_name", "label": "配置名称", "type": "dynamic_select", "default": "default", "allow_custom": True},
    ]


def get_output_schema(params=None, input_data=None, context=None):
    return {
        "type": "table",
        "headers": list(OUTPUT_HEADERS),
        "rows": [],
        "meta": {"plugin": PLUGIN_INFO["id"], "lazy_schema": True},
    }


def get_dynamic_parameter_options(param_name, params, context):
    params = dict(params or {})
    tables = _all_tables({}, context or {})
    if param_name in ("doc_table_alias", "content_table_alias", "replace_aux_table_alias"):
        return list(tables.keys()) or ["当前表"]
    if param_name == "config_name":
        settings = _load_settings(context or {})
        return sorted((settings.get("configs") or {"default": {}}).keys()) or ["default"]
    if param_name == "source_file_field":
        table, _alias = _pick_table({}, context or {}, params.get("doc_table_alias", "当前表"), "当前表")
        return list(table.get("headers", []) or [])
    if param_name == "planned_file_field":
        table, _alias = _pick_table({}, context or {}, params.get("content_table_alias", "新内容表"), "")
        return list(table.get("headers", []) or [])
    return []


def describe_config(params, context):
    params = dict(params or {})
    context = dict(context or {})
    settings = _load_settings(context)
    configs = settings.get("configs") or {}
    config_name = _as_text(params.get("config_name") or "default") or "default"
    cfg = _ensure_config(copy.deepcopy(configs.get(config_name) or _empty_config()))
    tables = _all_tables({}, context)
    doc_table, doc_alias = _pick_table({}, context, params.get("doc_table_alias", "当前表"), "当前表")
    content_table, content_alias = _pick_table({}, context, params.get("content_table_alias", "新内容表"), "")
    aux_table, aux_alias = _pick_optional_table({}, context, params.get("replace_aux_table_alias", "替换辅助表"))
    content_fields, content_rows = _content_rows(content_table)
    aux_fields, aux_rows = _content_rows(aux_table)
    source_records = _doc_records(doc_table, params)
    table_names = list(tables.keys())
    sheet_names = _unique_nonempty([rec.get("sheet_name") for rec in source_records])
    feature_names = _unique_nonempty([item.get("name") for item in cfg.get("features", []) if isinstance(item, dict)])
    normal_rule_names = [item.get("name") or item.get("id") for item in cfg.get("rules", []) if isinstance(item, dict)]
    global_rule_names = [
        f"全局:{name}"
        for name in (_as_text(item.get("name") or item.get("id")) for item in cfg.get("global_rules", []) if isinstance(item, dict))
        if name
    ]
    rule_names = _unique_nonempty(normal_rule_names + global_rule_names)
    linked_trigger_options = _linked_trigger_options(cfg)
    summary = {
        "config_name": config_name,
        "available_configs": sorted(configs.keys()) or ["default"],
        "rules": len(cfg.get("rules", []) or []),
        "features": len(cfg.get("features", []) or []),
        "global_rules": len(cfg.get("global_rules", []) or []),
        "linked_rules": len(cfg.get("linked_rules", []) or []),
        "doc_table_alias": doc_alias,
        "content_table_alias": content_alias,
        "replace_aux_table_alias": aux_alias,
        "doc_records": len(source_records),
        "content_rows": len(content_rows),
        "aux_rows": len(aux_rows),
    }
    config_base_path = ["plugin_settings", "configs", config_name]
    models = {
        "rule_default": _default_rule_for_cell({}),
        "feature_default": _ensure_feature({}, 1),
        "global_rule_default": _ensure_global_rule({}, 1),
        "linked_rule_default": _default_linked_rule(1),
        "empty_config": _empty_config(),
    }
    patch_operations = [
        "append_item",
        "update_item",
        "replace_item",
        "remove_item",
        "delete_item",
        "move_item",
        "set_enabled",
    ]
    editor_specs = [
        {
            "view_id": "visual_mapping.rules",
            "title": "单元格映射规则",
            "kind": "structured_list",
            "editor_kind": "visual_mapping.rules",
            "config_path": config_base_path + ["rules"],
            "item_count": summary["rules"],
            "columns": [
                {"key": "enabled", "label": "启用"},
                {"key": "name", "label": "规则"},
                {"key": "feature_name", "label": "表特征"},
                {"key": "content_field", "label": "写入字段"},
                {"key": "source", "label": "来源单元格"},
            ],
            "items": _summarize_visual_mapping_rules(cfg.get("rules", []), limit=200),
        },
        {
            "view_id": "visual_mapping.features",
            "title": "表特征",
            "kind": "structured_list",
            "editor_kind": "visual_mapping.features",
            "config_path": config_base_path + ["features"],
            "item_count": summary["features"],
            "columns": [
                {"key": "name", "label": "名称"},
                {"key": "condition_count", "label": "条件数"},
                {"key": "logic", "label": "连接"},
            ],
            "items": _summarize_visual_mapping_features(cfg.get("features", []), limit=200),
        },
        {
            "view_id": "visual_mapping.global_rules",
            "title": "全局搜索替换规则",
            "kind": "structured_list",
            "editor_kind": "visual_mapping.global_rules",
            "config_path": config_base_path + ["global_rules"],
            "item_count": summary["global_rules"],
            "columns": [
                {"key": "enabled", "label": "启用"},
                {"key": "name", "label": "规则"},
                {"key": "scope", "label": "范围"},
                {"key": "condition_count", "label": "条件数"},
                {"key": "batch_rule_count", "label": "批量规则"},
            ],
            "items": _summarize_visual_mapping_global_rules(cfg.get("global_rules", []), limit=200),
        },
        {
            "view_id": "visual_mapping.linked_rules",
            "title": "联动写入规则",
            "kind": "structured_list",
            "editor_kind": "visual_mapping.linked_rules",
            "config_path": config_base_path + ["linked_rules"],
            "item_count": summary["linked_rules"],
            "columns": [
                {"key": "enabled", "label": "启用"},
                {"key": "name", "label": "规则"},
                {"key": "trigger", "label": "触发"},
                {"key": "target_mode", "label": "定位"},
                {"key": "value_source", "label": "写入来源"},
                {"key": "action_count", "label": "动作数"},
            ],
            "items": _summarize_visual_mapping_linked_rules(cfg.get("linked_rules", []), limit=200),
        },
    ]
    section_model_keys = {
        "rules": "rule_default",
        "features": "feature_default",
        "global_rules": "global_rule_default",
        "linked_rules": "linked_rule_default",
    }
    patch_sections = {}
    for spec in editor_specs:
        section = _as_text((spec.get("config_path") or [""])[-1])
        model_key = section_model_keys.get(section, "")
        item_identity = _visual_mapping_section_item_identity(section)
        spec["section"] = section
        spec["item_identity"] = copy.deepcopy(item_identity)
        spec["selection"] = {
            "mode": "single",
            "target": "item",
            "default_index": 0,
            "empty_text": f"暂无{spec.get('title') or '配置项'}",
            "identity": copy.deepcopy(item_identity),
        }
        spec["patch_target"] = {
            "section": section,
            "path": copy.deepcopy(spec.get("config_path") or []),
            "target_index_field": "target_index",
            "target_id_field": "target_id",
            "target_id_fields": list(item_identity.get("target_id_fields") or []),
            "target_id_requires_unique_match": True,
            "fallback_target_index": True,
        }
        spec["patch_operations"] = list(patch_operations)
        spec["append_value"] = {}
        spec["item_schema"] = {
            "type": "object",
            "model_key": model_key,
            "display_columns": copy.deepcopy(spec.get("columns") or []),
            "columns": _visual_mapping_item_schema_columns(
                section,
                table_names=table_names,
                content_fields=content_fields,
                aux_fields=aux_fields,
                feature_names=feature_names,
                sheet_names=sheet_names,
                rule_names=rule_names,
                linked_trigger_options=linked_trigger_options,
            ),
            "detail_sections": _visual_mapping_item_schema_detail_sections(
                section,
                table_names=table_names,
                content_fields=content_fields,
                aux_fields=aux_fields,
                sheet_names=sheet_names,
                rule_names=rule_names,
                linked_trigger_options=linked_trigger_options,
            ),
        }
        if model_key:
            spec["item_model_key"] = model_key
            spec["item_default"] = copy.deepcopy(models.get(model_key) or {})
        patch_sections[section] = {
            "section": section,
            "view_id": spec.get("view_id"),
            "path": copy.deepcopy(spec.get("config_path") or []),
            "model_key": model_key,
            "operations": list(patch_operations),
            "item_identity": copy.deepcopy(item_identity),
            "target_id_fields": list(item_identity.get("target_id_fields") or []),
            "supports_target_id": True,
        }
        spec["patch_schema"] = _visual_mapping_patch_schema(
            config_name,
            operations=patch_operations,
            sections={section: patch_sections[section]},
        )
    views = [{
        "view_id": "visual_mapping.overview",
        "title": "映射配置总览",
        "kind": "summary",
        "protocol": "DataFlowKit.visual_mapping.config.v1",
        "summary": summary,
        "config_path": config_base_path,
    }] + editor_specs
    actions = [
        {
            "action_id": f"visual_mapping.edit.{spec['editor_kind'].split('.')[-1]}",
            "label": f"编辑{spec['title']}",
            "kind": "config_editor",
            "editor_kind": spec["editor_kind"],
            "config_path": spec["config_path"],
            "view_id": spec["view_id"],
            "patch_target": copy.deepcopy(spec["patch_target"]),
        }
        for spec in editor_specs
    ]
    patch_schema = _visual_mapping_patch_schema(
        config_name,
        operations=patch_operations,
        sections=patch_sections,
    )
    warning_schema = _visual_mapping_warning_schema(config_name)
    layout = _visual_mapping_config_layout(views)
    ui_hints = _visual_mapping_config_ui_hints(views)
    protocol_manifest = _visual_mapping_protocol_manifest(
        config_name,
        views=views,
        actions=actions,
        models=models,
        patch_schema=patch_schema,
        warning_schema=warning_schema,
        layout=layout,
        ui_hints=ui_hints,
    )
    return {
        "schema_version": CONFIG_SCHEMA_VERSION,
        "protocol_family": CONFIG_PROTOCOL_FAMILY,
        "plugin_id": PLUGIN_INFO["id"],
        "config_key": config_name,
        "protocol_manifest": protocol_manifest,
        "summary": summary,
        "views": views,
        "actions": actions,
        "layout": layout,
        "ui_hints": ui_hints,
        "context": {
            "table_names": table_names,
            "doc_headers": list(doc_table.get("headers", []) or []),
            "content_fields": content_fields,
            "aux_fields": aux_fields,
            "sheet_names": sheet_names,
            "feature_names": feature_names,
            "rule_names": rule_names,
            "linked_trigger_options": linked_trigger_options,
            "choices": {
                "match_modes": ["包含", "等于", "不等于", "正则匹配", "正则不匹配", "为空", "非空"],
                "batch_targets": list(BATCH_TARGET_CHOICES),
                "replace_row_policies": list(REPLACE_ROW_POLICY_CHOICES),
                "linked_target_modes": list(LINK_TARGET_MODES),
                "linked_value_sources": list(LINK_VALUE_SOURCES),
                "linked_write_modes": list(LINK_WRITE_MODES),
                "linked_overflow_policies": list(LINK_OVERFLOW_POLICIES),
                "slot_judgement_modes": list(SLOT_JUDGEMENT_MODES),
                "slot_invalid_policies": list(SLOT_INVALID_POLICIES),
            },
        },
        "models": models,
        "patch_schema": patch_schema,
        "warning_schema": warning_schema,
        "warnings": _normalize_config_warnings(context.get("settings_warnings") or []),
        "capabilities": {
            "schema_config": True,
            "dynamic_options": True,
            "config_patch": True,
            "config_effect_preview": True,
            "preview_config_effect": True,
            "protocol_manifest": True,
            "structured_warnings": True,
            "action_state": True,
            "layout_hints": True,
            "ui_hints": True,
            "legacy_custom_config": True,
            "supported_sections": sorted(CONFIG_SECTIONS),
            "supported_patch_operations": patch_operations,
            "view_kinds": ["summary", "structured_list"],
        },
    }


def resolve_config_options(params, context, field_key="", current_values=None, view_id="", section=""):
    described = describe_config(params, context)
    field_key = _as_text(field_key).strip()
    view_id = _as_text(view_id).strip()
    section = _as_text(section).strip()
    current_values = current_values if isinstance(current_values, dict) else {}
    context_payload = described.get("context") if isinstance(described.get("context"), dict) else {}
    views = [view for view in (described.get("views") or []) if isinstance(view, dict)]
    field_schema = _visual_mapping_find_option_field_schema(
        views,
        field_key=field_key,
        view_id=view_id,
        section=section,
    )
    options_source = field_schema.get("options_source") if isinstance(field_schema.get("options_source"), dict) else {}
    choices = []
    source = "unknown"
    empty_text = "字段暂不支持共享候选。"
    source_type = _as_text(options_source.get("type")).strip()
    source_key = _as_text(options_source.get("key")).strip()
    if source_type == "visual_mapping_context" and source_key:
        source = source_key
        choices = context_payload.get(source_key) or []
        empty_text = _visual_mapping_options_empty_text(source_key)
    elif field_schema.get("choices") is not None:
        source = "field_choices"
        choices = field_schema.get("choices") or []
        empty_text = "当前字段没有可选项。"
    elif field_key in {"config_name", "params.config_name"}:
        source = "available_configs"
        choices = (described.get("summary") or {}).get("available_configs") or []
        empty_text = "当前没有可用配置。"
    return {
        "ok": True,
        "schema_version": "DataFlowKit.plugin_config_options.v1",
        "protocol_family": CONFIG_PROTOCOL_FAMILY,
        "plugin_id": PLUGIN_INFO["id"],
        "config_key": described.get("config_key") or _as_text((params or {}).get("config_name")) or "default",
        "view_id": view_id or field_schema.get("view_id", ""),
        "section": section or field_schema.get("section", ""),
        "field_key": field_key,
        "source": source,
        "options_source": copy.deepcopy(options_source),
        "choices": _unique_nonempty(choices),
        "candidate_count": len(_unique_nonempty(choices)),
        "empty_text": empty_text,
        "allow_custom": bool(field_schema.get("allow_custom", True)),
        "current_values": copy.deepcopy(current_values),
        "context": {
            "table_names": list(context_payload.get("table_names") or []),
            "content_fields": list(context_payload.get("content_fields") or []),
            "aux_fields": list(context_payload.get("aux_fields") or []),
            "sheet_names": list(context_payload.get("sheet_names") or []),
            "feature_names": list(context_payload.get("feature_names") or []),
            "rule_names": list(context_payload.get("rule_names") or []),
            "linked_trigger_options": list(context_payload.get("linked_trigger_options") or []),
        },
        "issues": [],
    }


def _visual_mapping_protocol_manifest(
    config_name,
    *,
    views=None,
    actions=None,
    models=None,
    patch_schema=None,
    warning_schema=None,
    layout=None,
    ui_hints=None,
):
    view_items = []
    for view in views or []:
        if not isinstance(view, dict):
            continue
        item_schema = view.get("item_schema") if isinstance(view.get("item_schema"), dict) else {}
        detail_sections = [
            str(section.get("key") or "").strip()
            for section in item_schema.get("detail_sections") or []
            if isinstance(section, dict) and str(section.get("key") or "").strip()
        ]
        view_items.append({
            "view_id": view.get("view_id"),
            "title": view.get("title"),
            "kind": view.get("kind"),
            "editor_kind": view.get("editor_kind"),
            "section": view.get("section"),
            "config_path": copy.deepcopy(view.get("config_path") or []),
            "item_model_key": view.get("item_model_key"),
            "item_identity": copy.deepcopy(view.get("item_identity") or {}),
            "selection": copy.deepcopy(view.get("selection") or {}),
            "patch_target": copy.deepcopy(view.get("patch_target") or {}),
            "detail_sections": detail_sections,
            "patch_operations": copy.deepcopy(view.get("patch_operations") or []),
        })
    action_items = []
    for action in actions or []:
        if not isinstance(action, dict):
            continue
        action_items.append({
            "action_id": action.get("action_id"),
            "kind": action.get("kind"),
            "view_id": action.get("view_id"),
            "config_path": copy.deepcopy(action.get("config_path") or []),
            "patch_target": copy.deepcopy(action.get("patch_target") or {}),
        })
    patch_schema = patch_schema if isinstance(patch_schema, dict) else {}
    warning_schema = warning_schema if isinstance(warning_schema, dict) else {}
    return {
        "schema_version": "DataFlowKit.visual_mapping.protocol_manifest.v1",
        "protocol_family": CONFIG_PROTOCOL_FAMILY,
        "plugin_id": PLUGIN_INFO["id"],
        "config_key": config_name,
        "interfaces": {
            "describe_config": True,
            "validate_config_patch": True,
            "apply_config_patch": True,
            "preview_config_effect": True,
        },
        "views": view_items,
        "actions": action_items,
        "models": sorted((models or {}).keys()),
        "action_state": _visual_mapping_action_state_schema(),
        "patch": {
            "schema_version": patch_schema.get("schema_version"),
            "kind": patch_schema.get("kind"),
            "operations": [
                operation.get("operation")
                for operation in patch_schema.get("operations") or []
                if isinstance(operation, dict) and operation.get("operation")
            ],
            "sections": sorted((patch_schema.get("sections") or {}).keys()),
            "target_id_supported": bool(patch_schema.get("target_id_supported", False)),
            "target_id_fields": copy.deepcopy(patch_schema.get("target_id_fields") or {}),
            "result_schema": (patch_schema.get("result_schema") or {}).get("schema_version"),
            "target_schema": (patch_schema.get("target_schema") or {}).get("schema_version"),
        },
        "warnings": {
            "schema_version": warning_schema.get("schema_version"),
            "kind": warning_schema.get("kind"),
            "fields": [
                field.get("key")
                for field in warning_schema.get("fields") or []
                if isinstance(field, dict) and field.get("key")
            ],
        },
        "layout": {
            "schema_version": (layout or {}).get("schema_version"),
            "default_view_id": (layout or {}).get("default_view_id"),
            "view_order": copy.deepcopy((layout or {}).get("view_order") or []),
            "primary_views": copy.deepcopy((layout or {}).get("primary_views") or []),
            "advanced_views": copy.deepcopy((layout or {}).get("advanced_views") or []),
            "preferred_navigation": (layout or {}).get("preferred_navigation"),
        },
        "ui_hints": {
            "schema_version": (ui_hints or {}).get("schema_version"),
            "display_mode": (ui_hints or {}).get("display_mode"),
            "navigation": (ui_hints or {}).get("navigation"),
            "density": (ui_hints or {}).get("density"),
            "default_view_id": (ui_hints or {}).get("default_view_id"),
            "view_hint_ids": sorted(((ui_hints or {}).get("view_hints") or {}).keys()),
        },
        "config_effect": {
            "schema_version": "DataFlowKit.visual_mapping.config_effect.v1",
            "provider": "preview_config_effect",
            "view_id": "plugin.config_effect",
        },
    }


def _visual_mapping_action_state_schema():
    button_keys = [
        "append_item",
        "update_item",
        "delete_item",
        "set_enabled",
        "move_item_-1",
        "move_item_1",
    ]
    return {
        "schema_version": CONFIG_ACTION_STATE_SCHEMA_VERSION,
        "protocol_family": CONFIG_PROTOCOL_FAMILY,
        "kind": "structured_list_action_state",
        "provider": "PluginService.describe_plugin_config",
        "description": "由服务层根据 view.patch_operations、selection 和 actions 生成结构化列表按钮状态，供 Qt/.NET/Web 统一渲染。",
        "applies_to_view_kind": "structured_list",
        "view_kinds": ["structured_list"],
        "button_keys": button_keys,
        "button_order": button_keys,
        "boundary_sensitive_buttons": ["move_item_-1", "move_item_1"],
        "selection_required_buttons": ["update_item", "delete_item", "set_enabled", "move_item_-1", "move_item_1"],
        "operation_aliases": {
            "update_item": "replace_item",
            "remove_item": "delete_item",
        },
        "fields": [
            {"key": "schema_version", "type": "string", "required": True},
            {"key": "view_id", "type": "string", "required": True},
            {"key": "editor_kind", "type": "string", "required": False},
            {"key": "section", "type": "string", "required": False},
            {"key": "action_id", "type": "string", "required": False},
            {"key": "item_count", "type": "integer", "required": True},
            {"key": "selected_index", "type": "integer", "required": False},
            {"key": "supported_operations", "type": "list", "required": True},
            {"key": "button_order", "type": "list", "required": True},
            {"key": "buttons", "type": "object", "required": True},
        ],
        "button_fields": [
            {"key": "key", "type": "string", "required": True},
            {"key": "label", "type": "string", "required": True},
            {"key": "operation", "type": "string", "required": True},
            {"key": "effective_operation", "type": "string", "required": False},
            {"key": "target_offset", "type": "integer", "required": False},
            {"key": "visible", "type": "boolean", "required": True},
            {"key": "enabled", "type": "boolean", "required": True},
            {"key": "requires_selection", "type": "boolean", "required": True},
            {"key": "disabled_reason", "type": "string", "required": False},
            {"key": "action_id", "type": "string", "required": False},
        ],
    }


def _visual_mapping_config_layout(views=None):
    view_order = [
        str(view.get("view_id") or "").strip()
        for view in views or []
        if isinstance(view, dict) and str(view.get("view_id") or "").strip()
    ]
    primary_views = [
        view_id
        for view_id in view_order
        if view_id in {"visual_mapping.overview", "visual_mapping.rules", "visual_mapping.features"}
    ]
    advanced_views = [view_id for view_id in view_order if view_id not in primary_views]
    view_groups = [
        {
            "group_id": "visual_mapping.primary",
            "title": "主要配置",
            "view_ids": primary_views,
        },
        {
            "group_id": "visual_mapping.advanced",
            "title": "高级规则",
            "view_ids": advanced_views,
        },
    ]
    return {
        "schema_version": "DataFlowKit.visual_mapping.layout.v1",
        "protocol_family": CONFIG_PROTOCOL_FAMILY,
        "default_view_id": "visual_mapping.rules" if "visual_mapping.rules" in view_order else (view_order[0] if view_order else ""),
        "view_order": view_order,
        "primary_views": primary_views,
        "advanced_views": advanced_views,
        "view_groups": [group for group in view_groups if group["view_ids"]],
        "preferred_navigation": "tabs",
    }


def _visual_mapping_config_ui_hints(views=None):
    view_titles = {
        str(view.get("view_id") or ""): str(view.get("title") or "")
        for view in views or []
        if isinstance(view, dict) and str(view.get("view_id") or "")
    }
    view_hints = {
        "visual_mapping.overview": {
            "description": "查看当前配置、输入表和规则数量。",
            "empty_text": "当前没有可用映射配置摘要。",
            "role": "summary",
        },
        "visual_mapping.rules": {
            "description": "维护普通单元格到新内容字段的映射规则。",
            "empty_text": "暂无单元格映射规则，可新增规则或导入旧配置。",
            "primary_action": "visual_mapping.edit.rules",
            "role": "primary_editor",
        },
        "visual_mapping.features": {
            "description": "定义用于筛选工作表或表格区域的特征条件。",
            "empty_text": "暂无表特征。没有特征时，规则可选择“不限制”。",
            "primary_action": "visual_mapping.edit.features",
            "role": "supporting_editor",
        },
        "visual_mapping.global_rules": {
            "description": "维护全文和特殊对象的全局搜索替换规则。",
            "empty_text": "暂无全局搜索替换规则。",
            "primary_action": "visual_mapping.edit.global_rules",
            "role": "advanced_editor",
        },
        "visual_mapping.linked_rules": {
            "description": "维护某条规则命中后触发的联动写入动作。",
            "empty_text": "暂无联动写入规则。",
            "primary_action": "visual_mapping.edit.linked_rules",
            "role": "advanced_editor",
        },
    }
    return {
        "schema_version": "DataFlowKit.visual_mapping.ui_hints.v1",
        "protocol_family": CONFIG_PROTOCOL_FAMILY,
        "display_mode": "workflow_panel",
        "navigation": "tabs",
        "density": "compact",
        "default_view_id": "visual_mapping.rules",
        "view_hints": {
            view_id: dict({"title": view_titles.get(view_id, "")}, **hint)
            for view_id, hint in view_hints.items()
            if view_id in view_titles
        },
        "operation_hints": {
            "append_item": "新增一条配置项。",
            "replace_item": "替换当前选中的配置项。",
            "delete_item": "删除当前选中的配置项。",
            "move_item": "调整配置项顺序。",
            "set_enabled": "切换配置项启用状态。",
        },
    }


def _visual_mapping_warning_schema(config_name):
    return {
        "schema_version": CONFIG_SCHEMA_VERSION,
        "protocol_family": CONFIG_PROTOCOL_FAMILY,
        "kind": "config_warning",
        "config_key": _as_text(config_name) or "default",
        "levels": ["info", "warning", "error"],
        "fields": [
            {"key": "code", "type": "string", "required": True},
            {"key": "level", "type": "string", "required": True, "choices": ["info", "warning", "error"]},
            {"key": "message", "type": "string", "required": True},
            {"key": "plugin_id", "type": "string", "required": False},
            {"key": "view_id", "type": "string", "required": False},
            {"key": "field", "type": "string", "required": False},
            {"key": "path", "type": "string", "required": False},
            {"key": "config_path", "type": "path", "required": False},
            {"key": "hint", "type": "string", "required": False},
            {"key": "target", "type": "object", "required": False},
        ],
        "target_schema": {
            "schema_version": "plugin_config_warning_target.v1",
            "provider": "PluginService.describe_plugin_config",
            "fields": [
                {"key": "view_id", "type": "string", "required": False},
                {"key": "field", "type": "string", "required": False},
                {"key": "path", "type": "string", "required": False},
                {"key": "focus_path", "type": "string", "required": False},
                {"key": "config_path", "type": "path", "required": False},
                {"key": "config_path_text", "type": "string", "required": False},
                {"key": "can_focus_view", "type": "boolean", "required": True},
                {"key": "can_focus_field", "type": "boolean", "required": True},
            ],
        },
        "target_mapping": [
            {"source": "view_id", "target": "target.view_id"},
            {"source": "field", "target": "target.field"},
            {"source": "path", "target": "target.focus_path"},
            {"source": "config_path", "target": "target.config_path"},
        ],
    }


def _visual_mapping_patch_schema(config_name, *, operations=None, sections=None):
    operation_items = []
    sections = copy.deepcopy(sections or {})
    target_id_fields = {
        section: list((spec or {}).get("target_id_fields") or [])
        for section, spec in sections.items()
        if isinstance(spec, dict) and (spec.get("target_id_fields") or [])
    }
    operation_defs = {
        "append_item": {
            "label": "新增项",
            "path_kind": "section",
            "requires": ["section", "payload"],
        },
        "replace_item": {
            "label": "替换项",
            "aliases": ["update_item"],
            "path_kind": "item",
            "requires": ["section", "target_index", "payload"],
        },
        "delete_item": {
            "label": "删除项",
            "aliases": ["remove_item"],
            "path_kind": "item",
            "requires": ["section", "target_index"],
        },
        "move_item": {
            "label": "移动项",
            "path_kind": "item",
            "requires": ["section", "target_index", "to_index"],
        },
        "set_enabled": {
            "label": "设置启用状态",
            "path_kind": "item",
            "requires": ["section", "target_index", "payload.enabled"],
        },
    }
    for operation in operations or []:
        item = copy.deepcopy(operation_defs.get(operation) or {})
        item["operation"] = operation
        operation_items.append(item)
    return {
        "schema_version": CONFIG_SCHEMA_VERSION,
        "protocol_family": CONFIG_PROTOCOL_FAMILY,
        "kind": "config_patch",
        "config_key": _as_text(config_name) or "default",
        "operation_aliases": {
            "update_item": "replace_item",
            "remove_item": "delete_item",
        },
        "fields": [
            {"key": "schema_version", "type": "string", "required": False, "default": CONFIG_SCHEMA_VERSION},
            {"key": "protocol_family", "type": "string", "required": False, "default": CONFIG_PROTOCOL_FAMILY},
            {"key": "plugin_id", "type": "string", "required": False, "default": PLUGIN_INFO["id"]},
            {"key": "config_key", "type": "string", "required": False, "default": _as_text(config_name) or "default"},
            {"key": "config_name", "type": "string", "required": False, "default": _as_text(config_name) or "default"},
            {"key": "view_id", "type": "string", "required": False},
            {"key": "editor_kind", "type": "string", "required": False},
            {"key": "action_id", "type": "string", "required": False},
            {"key": "section", "type": "string", "required": True, "choices": sorted(CONFIG_SECTIONS)},
            {"key": "operation", "type": "string", "required": True},
            {"key": "path", "type": "path", "required": False},
            {"key": "target_index", "type": "integer", "required": False},
            {"key": "target_id", "type": "string", "required": False},
            {"key": "to_index", "type": "integer", "required": False},
            {"key": "payload", "type": "object", "required": False},
        ],
        "operations": operation_items,
        "sections": sections,
        "target_id_supported": bool(target_id_fields),
        "target_id_fields": target_id_fields,
        "result_schema": {
            "schema_version": "plugin_config_patch_result.v1",
            "provider": "PluginService.apply_plugin_config_patch",
            "fields": [
                {"key": "changed", "type": "boolean", "required": True},
                {"key": "message", "type": "string", "required": False},
                {"key": "patch_summary", "type": "object", "required": True},
                {"key": "target", "type": "object", "required": True},
                {"key": "description_summary", "type": "object", "required": False},
                {"key": "config_effect_summary", "type": "object", "required": False},
            ],
        },
        "target_schema": {
            "schema_version": "plugin_config_patch_target.v1",
            "provider": "PluginService.apply_plugin_config_patch",
            "fields": [
                {"key": "operation", "type": "string", "required": False},
                {"key": "view_id", "type": "string", "required": False},
                {"key": "editor_kind", "type": "string", "required": False},
                {"key": "action_id", "type": "string", "required": False},
                {"key": "section", "type": "string", "required": False},
                {"key": "path", "type": "path", "required": False},
                {"key": "path_text", "type": "string", "required": False},
                {"key": "target_index", "type": "integer", "required": False},
                {"key": "target_id", "type": "string", "required": False},
                {"key": "to_index", "type": "integer", "required": False},
                {"key": "focus_path", "type": "string", "required": False},
                {"key": "can_focus_view", "type": "boolean", "required": True},
                {"key": "can_focus_item", "type": "boolean", "required": True},
            ],
        },
    }


def preview_config_effect(params, context):
    params = dict(params or {})
    context = dict(context or {})
    described = describe_config(params, context)
    summary = copy.deepcopy(described.get("summary") or {})
    table_context = described.get("context") or {}
    config_name = _as_text(params.get("config_name") or summary.get("config_name") or "default") or "default"
    tables = _all_tables({}, context)
    doc_table, doc_alias = _pick_table({}, context, params.get("doc_table_alias", "当前表"), "当前表")
    content_table, content_alias = _pick_table({}, context, params.get("content_table_alias", "新内容表"), "")
    aux_table, aux_alias = _pick_optional_table({}, context, params.get("replace_aux_table_alias", "替换辅助表"))

    def table_effect(role, alias, table, *, required=True):
        headers = list((table or {}).get("headers") or [])
        rows = list((table or {}).get("rows") or [])
        return {
            "role": role,
            "alias": alias,
            "required": bool(required),
            "available": bool(headers or rows),
            "headers": headers,
            "row_count": len(rows),
        }

    required_input_tables = [
        table_effect("doc_table", doc_alias, doc_table, required=True),
        table_effect("content_table", content_alias, content_table, required=True),
        table_effect("replace_aux_table", aux_alias, aux_table, required=False),
    ]
    warnings = list(described.get("warnings") or [])
    if not table_context.get("content_fields"):
        warnings.append(_config_warning(
            "visual_mapping_no_content_fields",
            "新内容表没有可用字段，映射规则可能无法选择写入字段。",
            view_id="visual_mapping.rules",
            field="mapping.content_field",
        ))
    if not table_context.get("sheet_names"):
        warnings.append(_config_warning(
            "visual_mapping_no_sheet_names",
            "当前文档读取表没有识别到工作表名称，来源单元格候选可能不足。",
            view_id="visual_mapping.rules",
            field="source_locator.sheet_name",
        ))

    result = {
        "schema_version": "DataFlowKit.visual_mapping.config_effect.v1",
        "protocol_family": CONFIG_PROTOCOL_FAMILY,
        "plugin_id": PLUGIN_INFO["id"],
        "config_key": config_name,
        "summary": {
            "配置名称": config_name,
            "可用输入表": sorted(tables.keys()),
            "单元格映射规则": summary.get("rules", 0),
            "表特征": summary.get("features", 0),
            "全局搜索替换规则": summary.get("global_rules", 0),
            "联动写入规则": summary.get("linked_rules", 0),
            "文档记录数": summary.get("doc_records", 0),
            "新内容行数": summary.get("content_rows", 0),
            "辅助替换行数": summary.get("aux_rows", 0),
        },
        "required_input_tables": required_input_tables,
        "expected_output_fields": list(OUTPUT_HEADERS),
        "side_effects": [
            {
                "kind": "read_plugin_settings",
                "label": "读取视觉映射插件配置",
                "config_key": config_name,
            },
            {
                "kind": "read_input_tables",
                "label": "读取文档读取表、新内容表和可选替换辅助表",
                "aliases": [item["alias"] for item in required_input_tables if item.get("alias")],
            },
            {
                "kind": "file_write",
                "label": "正式执行时会按规则写入或生成目标设计文件",
                "execute_actions_only": True,
            },
        ],
        "warning_schema": _visual_mapping_warning_schema(config_name),
        "warnings": _normalize_config_warnings(warnings),
        "issues": [],
    }
    result["effect_state"] = _visual_mapping_config_effect_state(result)
    return result


def _visual_mapping_config_effect_state(effect):
    effect = effect if isinstance(effect, dict) else {}
    warnings = list(effect.get("warnings") or [])
    issues = list(effect.get("issues") or [])
    if issues:
        status = "error"
    elif warnings:
        status = "warning"
    else:
        status = "ok"
    output_fields = [str(item) for item in (effect.get("expected_output_fields") or []) if str(item).strip()]
    side_effects = [copy.deepcopy(item) for item in (effect.get("side_effects") or []) if isinstance(item, dict)]
    table_rows = []
    for item in effect.get("required_input_tables") or []:
        if not isinstance(item, dict):
            continue
        table_rows.append({
            "alias": _as_text(item.get("alias")),
            "role": _as_text(item.get("role")),
            "required": bool(item.get("required", True)),
            "available": bool(item.get("available")),
            "row_count": int(item.get("row_count") or 0),
            "headers": [str(header) for header in (item.get("headers") or [])],
        })
    summary = copy.deepcopy(effect.get("summary") or {})
    return {
        "schema_version": "plugin_config_effect_state.v1",
        "plugin_id": _as_text(effect.get("plugin_id")),
        "effect_schema_version": _as_text(effect.get("schema_version")),
        "protocol_family": _as_text(effect.get("protocol_family")),
        "config_key": _as_text(effect.get("config_key")),
        "status": status,
        "status_message": _visual_mapping_config_effect_status_message(
            status,
            table_rows,
            output_fields,
            side_effects,
            warnings,
            issues,
        ),
        "summary": summary,
        "summary_rows": [
            {"key": str(key), "label": str(key), "value": copy.deepcopy(value)}
            for key, value in summary.items()
        ],
        "required_input_tables": table_rows,
        "expected_output_fields": output_fields,
        "side_effects": side_effects,
        "warning_count": len(warnings),
        "issue_count": len(issues),
    }


def _visual_mapping_config_effect_status_message(status, table_rows, output_fields, side_effects, warnings, issues):
    if status == "error":
        return f"配置效果预览存在问题：{len(issues)} 项。"
    parts = [
        f"输入表 {len(table_rows)} 个",
        f"输出字段 {len(output_fields)} 个",
        f"运行影响 {len(side_effects)} 项",
    ]
    if status == "warning":
        parts.append(f"提示 {len(warnings)} 项")
    return "配置效果预览：" + "，".join(parts) + "。"


def _visual_mapping_find_option_field_schema(views, *, field_key="", view_id="", section=""):
    field_key = _as_text(field_key).strip()
    view_id = _as_text(view_id).strip()
    section = _as_text(section).strip()
    if not field_key:
        return {}
    for view in views or []:
        if not isinstance(view, dict):
            continue
        current_view_id = _as_text(view.get("view_id")).strip()
        current_section = _as_text(view.get("section")).strip()
        if view_id and current_view_id != view_id:
            continue
        if section and current_section != section:
            continue
        candidates = []
        item_schema = view.get("item_schema") if isinstance(view.get("item_schema"), dict) else {}
        candidates.extend(_visual_mapping_schema_fields(item_schema.get("columns") or []))
        for detail in item_schema.get("detail_sections") or []:
            if not isinstance(detail, dict):
                continue
            candidates.extend(_visual_mapping_schema_fields(detail.get("fields") or []))
            detail_item_schema = detail.get("item_schema") if isinstance(detail.get("item_schema"), dict) else {}
            candidates.extend(_visual_mapping_schema_fields(detail_item_schema.get("columns") or []))
        for field in candidates:
            if _as_text(field.get("key")).strip() == field_key:
                result = copy.deepcopy(field)
                result.setdefault("view_id", current_view_id)
                result.setdefault("section", current_section)
                return result
    return {}


def _visual_mapping_schema_fields(fields):
    return [field for field in (fields or []) if isinstance(field, dict)]


def _visual_mapping_options_empty_text(source_key):
    return {
        "table_names": "当前没有可用输入表。",
        "content_fields": "新内容表没有可选字段。",
        "aux_fields": "替换辅助表没有可选字段。",
        "sheet_names": "当前没有可选工作表。",
        "feature_names": "当前没有可选表特征。",
        "rule_names": "当前没有可选规则。",
        "linked_trigger_options": "当前没有可选触发规则。",
    }.get(_as_text(source_key).strip(), "当前没有可选项。")


def _visual_mapping_item_schema_columns(
    section,
    *,
    table_names=None,
    content_fields=None,
    aux_fields=None,
    feature_names=None,
    sheet_names=None,
    rule_names=None,
    linked_trigger_options=None,
):
    _ = table_names, aux_fields
    content_fields = list(content_fields or [])
    feature_names = list(feature_names or [])
    sheet_names = list(sheet_names or [])
    rule_names = list(rule_names or [])
    linked_trigger_options = list(linked_trigger_options or [])

    def field(key, label, field_type="text", **extra):
        item = {"key": key, "label": label, "type": field_type, "config_path": [part for part in key.split(".") if part]}
        item.update(extra)
        return item

    def select_field(key, label, choices, **extra):
        allow_custom = bool(extra.pop("allow_custom", True))
        return field(key, label, "select", choices=list(choices or []), allow_custom=allow_custom, **extra)

    common = [
        field("enabled", "启用", "bool"),
        field("name", "名称"),
    ]
    if section == "rules":
        return common + [
            select_field(
                "feature_name",
                "表特征",
                [""] + feature_names,
                options_source={"type": "visual_mapping_context", "key": "feature_names"},
            ),
            select_field(
                "mapping.content_field",
                "写入字段",
                content_fields,
                options_source={"type": "visual_mapping_context", "key": "content_fields"},
            ),
            select_field(
                "source_locator.sheet_name",
                "工作表",
                sheet_names,
                options_source={"type": "visual_mapping_context", "key": "sheet_names"},
            ),
            field("source_locator.row_index", "行号", "number", min=0, step=1),
            field("source_locator.col_index", "列号", "number", min=0, step=1),
        ]
    if section == "features":
        return common + [
            select_field("logic", "条件连接", ["AND", "OR"], allow_custom=False),
        ]
    if section == "global_rules":
        return common + [
            select_field(
                "feature_name",
                "表特征",
                [""] + feature_names,
                options_source={"type": "visual_mapping_context", "key": "feature_names"},
            ),
            select_field("scope", "范围", ["全部", "段落", "表格单元格", GLOBAL_SCOPE_SPECIAL_OBJECTS], allow_custom=False),
            select_field("condition_logic", "条件连接", ["AND", "OR"], allow_custom=False),
            select_field("batch_target_scope", "批量作用对象", BATCH_TARGET_CHOICES, allow_custom=False),
        ]
    if section == "linked_rules":
        return common + [
            select_field(
                "trigger_rule",
                "触发规则",
                linked_trigger_options,
                options_source={"type": "visual_mapping_context", "key": "linked_trigger_options"},
            ),
            select_field("target_mode", "定位方式", LINK_TARGET_MODES, allow_custom=False),
            select_field(
                "sheet_name",
                "工作表",
                sheet_names,
                options_source={"type": "visual_mapping_context", "key": "sheet_names"},
            ),
            select_field("value_source", "写入来源", LINK_VALUE_SOURCES, allow_custom=False),
            select_field(
                "value_field",
                "新内容字段",
                content_fields,
                options_source={"type": "visual_mapping_context", "key": "content_fields"},
            ),
            select_field("write_mode", "写入方式", LINK_WRITE_MODES, allow_custom=False),
            select_field("overflow_policy", "溢出处理", LINK_OVERFLOW_POLICIES, allow_custom=False),
        ]
    return common


def _visual_mapping_item_schema_detail_sections(
    section,
    *,
    table_names=None,
    content_fields=None,
    aux_fields=None,
    sheet_names=None,
    rule_names=None,
    linked_trigger_options=None,
):
    table_names = list(table_names or [])
    content_fields = list(content_fields or [])
    aux_fields = list(aux_fields or [])
    sheet_names = list(sheet_names or [])
    rule_names = list(rule_names or [])
    linked_trigger_options = list(linked_trigger_options or [])
    source_choices = ["手动输入"] + [item for item in table_names if item != "手动输入"]
    value_fields = _unique_nonempty(content_fields + aux_fields)
    match_modes = ["包含", "等于", "不等于", "正则匹配", "正则不匹配", "为空", "非空"]

    def field(key, label, field_type="text", **extra):
        item = {"key": key, "label": label, "type": field_type, "config_path": [part for part in key.split(".") if part]}
        item.update(extra)
        return item

    def select_field(key, label, choices, **extra):
        allow_custom = bool(extra.pop("allow_custom", True))
        return field(key, label, "select", choices=list(choices or []), allow_custom=allow_custom, **extra)

    def structured_section(key, title, columns, *, item_default=None):
        return {
            "key": key,
            "title": title,
            "kind": "structured_list",
            "config_path": [key],
            "patch_operations": ["append_item", "update_item", "replace_item", "delete_item", "move_item", "set_enabled"],
            "item_default": copy.deepcopy(item_default or {}),
            "item_schema": {
                "type": "object",
                "columns": columns,
            },
        }

    def form_section(key, title, fields):
        return {
            "key": key,
            "title": title,
            "kind": "form",
            "config_path": [key],
            "fields": fields,
        }

    feature_condition_columns = [
        select_field("join", "连接", ["AND", "OR"], allow_custom=False),
        select_field("sheet_name", "工作表", sheet_names, options_source={"type": "visual_mapping_context", "key": "sheet_names"}),
        field("row_index", "行号", "number", min=0, step=1),
        field("col_index", "列号", "number", min=0, step=1),
        select_field("mode", "匹配方式", match_modes, allow_custom=False),
        field("value", "匹配值"),
    ]
    simple_condition_columns = [
        select_field("join", "连接", ["AND", "OR"], allow_custom=False),
        select_field("mode", "匹配方式", match_modes, allow_custom=False),
        field("value", "匹配值"),
    ]
    batch_rule_columns = [
        field("enabled", "启用", "bool"),
        select_field("match_mode", "匹配方式", match_modes, allow_custom=False),
        select_field("match_value_source", "匹配值来源", source_choices, options_source={"type": "visual_mapping_context", "key": "table_names"}),
        field("match_value", "匹配值"),
        select_field("match_value_field", "匹配字段", value_fields, options_source={"type": "visual_mapping_context", "key": "content_fields"}),
        select_field("match_row_policy", "匹配行策略", REPLACE_ROW_POLICY_CHOICES, allow_custom=False),
        field("match_row_index", "匹配固定行", "number", min=1, step=1),
        select_field("replace_mode", "替换方式", ["局部替换匹配字符串", "整格替换为新值"], allow_custom=False),
        select_field("replace_value_source", "替换值来源", source_choices, options_source={"type": "visual_mapping_context", "key": "table_names"}),
        field("replace_value", "替换值"),
        select_field("replace_value_field", "替换字段", value_fields, options_source={"type": "visual_mapping_context", "key": "content_fields"}),
        select_field("replace_row_policy", "替换行策略", REPLACE_ROW_POLICY_CHOICES, allow_custom=False),
        field("replace_row_index", "替换固定行", "number", min=1, step=1),
        field("case_sensitive", "区分大小写", "bool"),
        field("skip_empty_match_value", "跳过空匹配值", "bool"),
        field("count", "替换次数", "number", min=0, step=1),
    ]
    anchor_fields = [
        field("enabled", "启用", "bool"),
        select_field("axis", "方向", ["行", "列"], allow_custom=False),
        field("index", "行/列序号", "number", min=1, step=1),
        select_field("match_mode", "匹配方式", match_modes, allow_custom=False),
        field("value", "匹配值"),
        field("row_offset", "行偏移", "number", step=1),
        field("col_offset", "列偏移", "number", step=1),
    ]
    source_match_fields = [
        field("enabled", "启用", "bool"),
        select_field("logic", "条件连接", ["AND", "OR"], allow_custom=False),
        select_field("mode", "匹配方式", match_modes, allow_custom=False),
        field("value", "匹配值"),
    ]
    linked_action_columns = [
        field("enabled", "启用", "bool"),
        field("name", "动作名称"),
        select_field("target_mode", "目标方式", LINK_ACTION_TARGET_MODES, allow_custom=False),
        field("row_offset", "行偏移", "number", step=1),
        field("col_offset", "列偏移", "number", step=1),
        select_field("value_source", "写入来源", LINK_VALUE_SOURCES, allow_custom=False),
        field("fixed_value", "固定值"),
        select_field("value_field", "新内容字段", content_fields, options_source={"type": "visual_mapping_context", "key": "content_fields"}),
        field("value_template", "模板"),
        select_field("write_mode", "写入方式", LINK_WRITE_MODES, allow_custom=False),
        select_field("empty_policy", "空值策略", ["允许", "跳过"], allow_custom=False),
    ]

    if section == "rules":
        return [
            form_section("source_match", "输入源匹配", source_match_fields),
            form_section("anchor", "锚点定位", anchor_fields),
            structured_section("conditions", "内容条件", simple_condition_columns, item_default={"join": "AND", "mode": "包含", "value": ""}),
            structured_section("batch_rules", "批量替换规则", batch_rule_columns, item_default={"enabled": True, "match_mode": "包含", "match_value_source": "手动输入", "replace_mode": "局部替换匹配字符串", "replace_value_source": "手动输入"}),
        ]
    if section == "features":
        return [
            structured_section("conditions", "特征条件", feature_condition_columns, item_default={"join": "AND", "sheet_name": "", "row_index": "1", "col_index": "1", "mode": "包含", "value": ""}),
        ]
    if section == "global_rules":
        return [
            structured_section("conditions", "命中条件", simple_condition_columns, item_default={"join": "AND", "mode": "包含", "value": ""}),
            structured_section("batch_rules", "批量替换规则", batch_rule_columns, item_default={"enabled": True, "match_mode": "包含", "match_value_source": "手动输入", "replace_mode": "局部替换匹配字符串", "replace_value_source": "手动输入"}),
        ]
    if section == "linked_rules":
        return [
            form_section("anchor", "锚点定位", anchor_fields),
            structured_section("conditions", "触发文本条件", simple_condition_columns, item_default={"join": "AND", "mode": "包含", "value": ""}),
            structured_section("actions", "联动动作", linked_action_columns, item_default={"enabled": True, "name": "新动作", "target_mode": LINK_ACTION_SHARED_SLOT, "value_source": LINK_VALUE_TEMPLATE, "write_mode": LINK_WRITE_REPLACE}),
        ]
    return []


def validate_config_patch(params, context, patch):
    try:
        normalized = _normalize_config_patch(params or {}, patch or {})
        _preview_config_patch(params or {}, context or {}, normalized)
    except ValueError as exc:
        return {
            "ok": False,
            "message": str(exc),
            "issues": [_config_patch_issue("visual_mapping_config_patch_invalid", str(exc))],
        }
    return {"ok": True, "patch": normalized, "issues": []}


def apply_config_patch(params, context, patch):
    params = dict(params or {})
    context = dict(context or {})
    normalized = _normalize_config_patch(params, patch or {})
    settings = _load_settings(context)
    configs = settings.setdefault("configs", {})
    config_name, section = _config_patch_target(params, normalized)
    cfg = _ensure_config(copy.deepcopy(configs.get(config_name) or _empty_config()))
    _apply_config_patch_to_section(cfg, section, normalized)
    configs[config_name] = cfg
    _save_settings(context, settings)
    return {
        "ok": True,
        "params": params,
        "changed": True,
        "patch": normalized,
        "message": f"已更新配置 {config_name} 的 {section}",
    }


def _as_text(value):
    return "" if value is None else str(value).strip()


def _cell_text(value):
    return "" if value is None else str(value)


def _minimal_text_change(old_text, new_text):
    old_text = _cell_text(old_text)
    new_text = _cell_text(new_text)
    if old_text == new_text:
        return "", ""
    prefix = 0
    max_prefix = min(len(old_text), len(new_text))
    while prefix < max_prefix and old_text[prefix] == new_text[prefix]:
        prefix += 1
    suffix = 0
    max_suffix = min(len(old_text) - prefix, len(new_text) - prefix)
    while suffix < max_suffix and old_text[len(old_text) - 1 - suffix] == new_text[len(new_text) - 1 - suffix]:
        suffix += 1
    old_end = len(old_text) - suffix if suffix else len(old_text)
    new_end = len(new_text) - suffix if suffix else len(new_text)
    left = prefix
    right_old = old_end
    right_new = new_end
    while True:
        old_part = old_text[left:right_old]
        new_part = new_text[left:right_new]
        if old_part and old_text.count(old_part) == 1:
            return old_part, new_part
        if left <= 0 and right_old >= len(old_text):
            return old_text, new_text
        if left > 0:
            left -= 1
        if right_old < len(old_text):
            right_old += 1
            right_new += 1


def _ui_feature_name(value):
    value = _as_text(value)
    return value if value and value != FEATURE_ANY_LABEL else FEATURE_ANY_LABEL


def _cfg_feature_name(value):
    value = _as_text(value)
    return "" if value in ("", FEATURE_ANY_LABEL, "不限", "全部") else value


def _ui_sheet_name(value):
    value = _as_text(value)
    return value if value and value != SHEET_ALL_LABEL else SHEET_ALL_LABEL


def _cfg_sheet_name(value):
    value = _as_text(value)
    return "" if value in ("", SHEET_ALL_LABEL, "全部", "所有", "*") else value


def _center_window(win, parent=None, width=None, height=None):
    try:
        win.update_idletasks()
        w = int(width or win.winfo_width() or win.winfo_reqwidth() or 600)
        h = int(height or win.winfo_height() or win.winfo_reqheight() or 400)
        if parent is not None and parent.winfo_exists():
            parent.update_idletasks()
            px = parent.winfo_rootx()
            py = parent.winfo_rooty()
            pw = parent.winfo_width()
            ph = parent.winfo_height()
            if pw <= 1 or ph <= 1:
                px = py = 0
                pw = win.winfo_screenwidth()
                ph = win.winfo_screenheight()
        else:
            px = py = 0
            pw = win.winfo_screenwidth()
            ph = win.winfo_screenheight()
        x = max(0, px + (pw - w) // 2)
        y = max(0, py + (ph - h) // 2)
        win.geometry(f"{w}x{h}+{x}+{y}" if width or height else f"+{x}+{y}")
    except Exception:
        pass


def _show_centered_window(win, parent=None, width=None, height=None):
    _center_window(win, parent, width, height)
    try:
        win.deiconify()
    except Exception:
        pass
    try:
        win.lift()
    except Exception:
        pass
    try:
        win.focus_set()
    except Exception:
        pass


def _make_floating_child(parent, title):
    dlg = tk.Toplevel(parent)
    try:
        dlg.withdraw()
    except Exception:
        pass
    dlg.title(title)
    dlg.transient(parent)
    try:
        dlg.resizable(True, True)
    except Exception:
        pass
    return dlg


def _make_scrollable_listbox(parent, **kwargs):
    frame = ttk.Frame(parent)
    listbox = tk.Listbox(frame, **kwargs)
    scrollbar = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=listbox.yview)
    listbox.configure(yscrollcommand=scrollbar.set)
    listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    return frame, listbox


def _to_int(value, default=0):
    try:
        if value in (None, ""):
            return default
        return int(str(value).strip(), 0)
    except Exception:
        return default


def _safe_cell(row, idx):
    return row[idx] if 0 <= idx < len(row) else ""


def _row_dict(headers, row):
    return {h: _safe_cell(row, i) for i, h in enumerate(headers)}


def _plugin_data_dir(context):
    path = _as_text((context or {}).get("plugin_data_dir"))
    if not path:
        path = str(Path(__file__).resolve().parent.parent / "plugin_data" / PLUGIN_INFO["id"])
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _settings_path(context):
    return _plugin_data_dir(context) / SETTINGS_FILE


def _empty_config():
    return {"rules": [], "features": [], "global_rules": [], "linked_rules": []}


def _default_sequence_symbols():
    chars = "⓪①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳㉑㉒㉓㉔㉕㉖㉗㉘㉙㉚㉛㉜㉝㉞㉟㊱㊲㊳㊴㊵㊶㊷㊸㊹㊺㊻㊼㊽㊾㊿"
    return [{"index": index, "symbol": char} for index, char in enumerate(chars)]


def _default_date_presets():
    presets = []
    common = default_date_parser_config()
    presets.append({"name": "自动识别常见格式", "config": common})
    for name, delimiter in (
        ("YYYY-MM-DD", "-"),
        ("YYYY/MM/DD", "/"),
        ("YYYY.MM.DD", "."),
        ("YYYY年MM月DD日", "年/月/日"),
    ):
        config = default_date_parser_config()
        config.update({
            "input_structure": "分隔符",
            "date_delimiter": delimiter,
            "date_order": "年-月-日",
            "year_rule": "20xx",
        })
        presets.append({"name": name, "config": config})
    for name, year_len in (("YYYYMMDD", "4"), ("YYMMDD", "2")):
        config = default_date_parser_config()
        config.update({
            "input_structure": "固定位置",
            "year_len": year_len,
            "month_start": "5" if year_len == "4" else "3",
            "day_start": "7" if year_len == "4" else "5",
        })
        presets.append({"name": name, "config": config})
    return presets


def _default_slot_judgement():
    return {
        "mode": SLOT_MODE_SEQUENCE_DATE,
        "sequence_start": 1,
        "sequence_col_offset": 0,
        "date_col_offset": 0,
        "sequence_group": "文档统一序号",
        "sequence_overflow": "括号数字",
        "sequence_symbols": _default_sequence_symbols(),
        "date_presets": _default_date_presets(),
        "active_date_preset": "自动识别常见格式",
        "date_parser": default_date_parser_config(),
        "invalid_policy": SLOT_INVALID_SKIP,
    }


def _ensure_slot_judgement(value):
    result = copy.deepcopy(value) if isinstance(value, dict) else {}
    defaults = _default_slot_judgement()
    for key, default in defaults.items():
        if key not in result:
            result[key] = copy.deepcopy(default)
    if not isinstance(result.get("sequence_symbols"), list):
        result["sequence_symbols"] = _default_sequence_symbols()
    if not isinstance(result.get("date_presets"), list):
        result["date_presets"] = _default_date_presets()
    if not isinstance(result.get("date_parser"), dict):
        result["date_parser"] = default_date_parser_config()
    return result


def _ensure_linked_rule(rule):
    if not isinstance(rule, dict):
        rule = {}
    rule.setdefault("event_tags", [])
    rule.setdefault("trigger_tags", [])
    rule["slot_judgement"] = _ensure_slot_judgement(rule.get("slot_judgement"))
    if "actions" in rule and not isinstance(rule.get("actions"), list):
        rule["actions"] = []
    return rule


def _ensure_config(cfg):
    if not isinstance(cfg, dict):
        cfg = {}
    cfg.setdefault("rules", [])
    cfg.setdefault("features", [])
    cfg.setdefault("global_rules", [])
    cfg.setdefault("linked_rules", [])
    cfg["linked_rules"] = [_ensure_linked_rule(rule) for rule in cfg["linked_rules"] if isinstance(rule, dict)]
    return cfg


def _config_patch_issue(code, message, path="/patch"):
    return {"level": "error", "code": code, "message": message, "path": path, "source": PLUGIN_INFO["id"]}


def _config_warning(code, message, *, level="warning", view_id="", field="", hint="", path="", config_path=None):
    warning = {
        "code": code,
        "level": level,
        "message": message,
        "plugin_id": PLUGIN_INFO["id"],
    }
    if view_id:
        warning["view_id"] = view_id
    if field:
        warning["field"] = field
    if config_path is not None:
        warning["config_path"] = list(config_path)
    elif field:
        warning["config_path"] = [part for part in _as_text(field).split(".") if part]
    if hint:
        warning["hint"] = hint
    warning["path"] = path or _warning_default_path(warning)
    return warning


def _normalize_config_warnings(warnings):
    result = []
    for index, warning in enumerate(warnings or [], start=1):
        if isinstance(warning, dict):
            item = copy.deepcopy(warning)
            item.setdefault("level", "warning")
            item.setdefault("code", f"plugin_warning_{index}")
            item["message"] = _as_text(item.get("message") or item.get("text"))
            if not item["message"]:
                continue
            item.setdefault("plugin_id", PLUGIN_INFO["id"])
            if item.get("field") and not item.get("config_path"):
                item["config_path"] = [part for part in _as_text(item.get("field")).split(".") if part]
            item.setdefault("path", _warning_default_path(item, index=index))
            result.append(item)
        else:
            message = _as_text(warning)
            if message:
                result.append(_config_warning(
                    f"plugin_warning_{index}",
                    message,
                    view_id="visual_mapping.overview",
                    path="/plugin_settings",
                    hint="请检查插件配置文件或备份恢复信息。",
                ))
    return result


def _warning_default_path(warning, *, index=0):
    view_id = _as_text((warning or {}).get("view_id"))
    field = _as_text((warning or {}).get("field"))
    code = _as_text((warning or {}).get("code"))
    if view_id and field:
        return f"/views/{view_id}/fields/{field}"
    if view_id:
        return f"/views/{view_id}"
    if field:
        return f"/fields/{field}"
    if code:
        return f"/warnings/{code}"
    return f"/warnings/{index or 0}"


def _config_patch_target(params, patch):
    patch = patch or {}
    target = patch.get("path") or patch.get("target") or []
    config_name = _as_text(
        patch.get("config_name")
        or patch.get("config_key")
        or (params or {}).get("config_name")
        or "default"
    ) or "default"
    section = _as_text(patch.get("section") or "")
    if isinstance(target, str):
        target = [part for part in target.split(".") if part]
    if isinstance(target, (list, tuple)) and target:
        if len(target) >= 4 and target[0] == "plugin_settings" and target[1] == "configs":
            config_name = _as_text(target[2]) or config_name
            section = _as_text(target[3]) or section
        elif len(target) == 1:
            section = _as_text(target[0]) or section
    section = section or "rules"
    if section not in CONFIG_SECTIONS:
        raise ValueError(f"当前不支持修改 {section}，支持：{', '.join(sorted(CONFIG_SECTIONS))}")
    return config_name, section


def _normalize_config_patch(params, patch):
    patch = copy.deepcopy(patch or {})
    config_name, section = _config_patch_target(params, patch)
    operation = _as_text(patch.get("operation") or "replace_item") or "replace_item"
    operation_alias = {
        "update_item": "replace_item",
        "remove_item": "delete_item",
    }
    operation = operation_alias.get(operation, operation)
    path = patch.get("path") or patch.get("target") or ["plugin_settings", "configs", config_name, section]
    if isinstance(path, str):
        path = [part for part in path.split(".") if part]
    normalized = {
        "schema_version": _as_text(patch.get("schema_version") or CONFIG_SCHEMA_VERSION),
        "protocol_family": _as_text(patch.get("protocol_family") or CONFIG_PROTOCOL_FAMILY),
        "plugin_id": _as_text(patch.get("plugin_id") or PLUGIN_INFO["id"]),
        "config_key": config_name,
        "config_name": config_name,
        "section": section,
        "operation": operation,
        "path": list(path or ["plugin_settings", "configs", config_name, section]),
    }
    for key in ("view_id", "editor_kind", "action_id", "target_id", "enabled"):
        if key in patch:
            normalized[key] = copy.deepcopy(patch.get(key))
    if "target_index" in patch:
        normalized["target_index"] = patch.get("target_index")
    elif "index" in patch:
        normalized["target_index"] = patch.get("index")
    elif isinstance(path, (list, tuple)) and len(path) >= 5:
        normalized["target_index"] = path[4]
    if "payload" in patch:
        normalized["payload"] = copy.deepcopy(patch.get("payload"))
    elif "value" in patch:
        normalized["payload"] = copy.deepcopy(patch.get("value"))
    elif operation == "set_enabled" and "enabled" in normalized:
        normalized["payload"] = {"enabled": bool(normalized.get("enabled"))}
    if operation == "set_enabled" and "enabled" not in normalized:
        payload = normalized.get("payload")
        if isinstance(payload, dict) and "enabled" in payload:
            normalized["enabled"] = payload.get("enabled")
    if "to_index" in patch:
        normalized["to_index"] = patch.get("to_index")
    normalized["path"] = _canonical_config_patch_path(normalized)
    return normalized


def _canonical_config_patch_path(patch):
    path = list((patch or {}).get("path") or [])
    operation = _as_text((patch or {}).get("operation") or "")
    if operation in {"replace_item", "delete_item", "move_item", "set_enabled"} and len(path) == 4:
        if "target_index" in (patch or {}):
            path.append((patch or {}).get("target_index"))
    return path


def _preview_config_patch(params, context, patch):
    settings = _load_settings(context)
    configs = settings.setdefault("configs", {})
    config_name, section = _config_patch_target(params, patch)
    cfg = _ensure_config(copy.deepcopy(configs.get(config_name) or _empty_config()))
    _apply_config_patch_to_section(cfg, section, patch)
    return cfg


def _apply_config_patch_to_section(cfg, section, patch):
    items = cfg.setdefault(section, [])
    if not isinstance(items, list):
        items = []
        cfg[section] = items
    operation = _as_text((patch or {}).get("operation") or "replace_item")
    if operation == "append_item":
        items.append(_ensure_config_section_item(section, (patch or {}).get("payload"), len(items) + 1))
        return
    if operation == "replace_item":
        index = _config_patch_item_index(patch, items, section)
        items[index] = _ensure_config_section_item(section, (patch or {}).get("payload"), index + 1)
        return
    if operation == "delete_item":
        index = _config_patch_item_index(patch, items, section)
        items.pop(index)
        return
    if operation == "move_item":
        index = _config_patch_item_index(patch, items, section)
        to_index = _to_int((patch or {}).get("to_index"), index)
        if to_index < 0 or to_index >= len(items):
            raise ValueError("目标位置超出范围")
        item = items.pop(index)
        items.insert(to_index, item)
        return
    if operation == "set_enabled":
        index = _config_patch_item_index(patch, items, section)
        if not isinstance(items[index], dict):
            items[index] = _ensure_config_section_item(section, items[index], index + 1)
        payload = (patch or {}).get("payload")
        if "enabled" in (patch or {}):
            enabled_value = (patch or {}).get("enabled")
        elif isinstance(payload, dict) and "enabled" in payload:
            enabled_value = payload.get("enabled")
        else:
            enabled_value = payload if payload is not None else True
        items[index]["enabled"] = enabled_value if isinstance(enabled_value, bool) else _truthy(enabled_value)
        return
    raise ValueError(f"不支持的配置修改操作：{operation}")


def _config_patch_index(patch, length, section="rules"):
    if length <= 0:
        raise ValueError(f"{section} 列表为空")
    index = _to_int((patch or {}).get("target_index"), -1)
    if index < 0:
        index = _to_int((patch or {}).get("index"), -1)
    if index < 0 or index >= length:
        raise ValueError(f"{section} 索引超出范围")
    return index


def _config_patch_item_index(patch, items, section="rules"):
    target_id = _as_text((patch or {}).get("target_id"))
    if target_id:
        return _config_patch_target_id_index(target_id, items, section)
    return _config_patch_index(patch, len(items), section)


def _config_patch_target_id_index(target_id, items, section="rules"):
    fields = _visual_mapping_section_item_identity(section).get("target_id_fields") or ["name"]
    matches = []
    for index, item in enumerate(items or []):
        if not isinstance(item, dict):
            continue
        for field in fields:
            if _as_text(item.get(field)) == target_id:
                matches.append(index)
                break
    if not matches:
        raise ValueError(f"{section} 未找到 target_id：{target_id}")
    if len(matches) > 1:
        raise ValueError(f"{section} target_id 不唯一：{target_id}")
    return matches[0]


def _ensure_config_section_item(section, item, index=1):
    if section == "rules":
        return _ensure_mapping_rule(item, index)
    if section == "features":
        return _ensure_feature(item, index)
    if section == "global_rules":
        return _ensure_global_rule(item, index)
    if section == "linked_rules":
        return _ensure_linked_rule_item(item, index)
    return copy.deepcopy(item) if isinstance(item, dict) else {}


def _ensure_feature(feature, index=1):
    result = copy.deepcopy(feature) if isinstance(feature, dict) else {}
    result.setdefault("name", f"feature_{index}")
    result.setdefault("enabled", True)
    if not isinstance(result.get("conditions"), list):
        result["conditions"] = []
    result.setdefault("logic", "AND")
    return result


def _ensure_global_rule(rule, index=1):
    result = copy.deepcopy(rule) if isinstance(rule, dict) else {}
    result.setdefault("name", f"global_rule_{index}")
    result.setdefault("enabled", True)
    if not isinstance(result.get("conditions"), list):
        result["conditions"] = []
    if not isinstance(result.get("batch_rules"), list):
        result["batch_rules"] = []
    return result


def _ensure_linked_rule_item(rule, index=1):
    result = _ensure_linked_rule(copy.deepcopy(rule) if isinstance(rule, dict) else {})
    result.setdefault("name", f"linked_rule_{index}")
    result.setdefault("enabled", True)
    return result


def _ensure_mapping_rule(rule, index=1):
    result = copy.deepcopy(rule) if isinstance(rule, dict) else {}
    result.setdefault("id", _as_text(result.get("name")) or f"rule_{index}")
    result.setdefault("name", _as_text(result.get("id")) or f"rule_{index}")
    result.setdefault("enabled", True)
    if not isinstance(result.get("source_locator"), dict):
        result["source_locator"] = {}
    if not isinstance(result.get("source_match"), dict):
        result["source_match"] = {"enabled": False, "mode": "包含", "value": ""}
    if not isinstance(result.get("anchor"), dict):
        result["anchor"] = {"enabled": False}
    if not isinstance(result.get("mapping"), dict):
        result["mapping"] = {"content_field": "", "empty_policy": "跟随节点设置"}
    return result


def _visual_mapping_section_item_identity(section):
    section = _as_text(section)
    fields_by_section = {
        "rules": ["id", "name"],
        "features": ["name"],
        "global_rules": ["name"],
        "linked_rules": ["name"],
    }
    labels = {
        "rules": "规则",
        "features": "表特征",
        "global_rules": "全局规则",
        "linked_rules": "联动规则",
    }
    target_id_fields = fields_by_section.get(section, ["name"])
    return {
        "schema_version": CONFIG_SCHEMA_VERSION,
        "kind": "visual_mapping_item_identity",
        "section": section,
        "label": labels.get(section, "配置项"),
        "index_base": 0,
        "display_index_base": 1,
        "target_index_field": "target_index",
        "target_id_field": "target_id",
        "target_id_fields": target_id_fields,
        "target_id_match": "first_unique_nonempty",
        "target_id_requires_unique_match": True,
    }


def _unique_nonempty(values):
    result = []
    for value in values or []:
        text = _as_text(value)
        if text and text not in result:
            result.append(text)
    return result


def _summarize_visual_mapping_rules(rules, limit=200):
    items = []
    for index, rule in enumerate([r for r in (rules or []) if isinstance(r, dict)], start=1):
        locator = rule.get("source_locator") if isinstance(rule.get("source_locator"), dict) else {}
        mapping = rule.get("mapping") if isinstance(rule.get("mapping"), dict) else {}
        item = copy.deepcopy(rule)
        item.update({
            "index": index,
            "id": _as_text(rule.get("id")),
            "name": _as_text(rule.get("name") or rule.get("id")) or f"rule_{index}",
            "enabled": bool(rule.get("enabled", True)),
            "feature_name": _as_text(rule.get("feature_name")),
            "content_field": _as_text(mapping.get("content_field")),
            "source": _format_visual_mapping_locator(locator),
            "source_match_enabled": bool((rule.get("source_match") or {}).get("enabled", False)),
            "anchor_enabled": bool((rule.get("anchor") or {}).get("enabled", False)),
            "batch_rule_count": len(_batch_rules_for_rule(rule)),
        })
        items.append(item)
        if len(items) >= limit:
            break
    return items


def _summarize_visual_mapping_features(features, limit=200):
    items = []
    for index, feature in enumerate([f for f in (features or []) if isinstance(f, dict)], start=1):
        item = copy.deepcopy(feature)
        item.update({
            "index": index,
            "name": _as_text(feature.get("name")) or f"feature_{index}",
            "enabled": bool(feature.get("enabled", True)),
            "logic": _as_text(feature.get("logic") or "AND") or "AND",
            "condition_count": len(feature.get("conditions", []) or []),
        })
        items.append(item)
        if len(items) >= limit:
            break
    return items


def _summarize_visual_mapping_global_rules(rules, limit=200):
    items = []
    for index, rule in enumerate([r for r in (rules or []) if isinstance(r, dict)], start=1):
        item = copy.deepcopy(rule)
        item.update({
            "index": index,
            "name": _as_text(rule.get("name")) or f"global_{index}",
            "enabled": bool(rule.get("enabled", True)),
            "feature_name": _as_text(rule.get("feature_name")),
            "scope": _as_text(rule.get("scope") or "全部") or "全部",
            "sheet_name": _as_text(rule.get("sheet_name")),
            "condition_count": len(rule.get("conditions", []) or []),
            "batch_rule_count": len(_batch_rules_for_rule(rule)),
            "event_tags": _normalize_event_tags(rule.get("event_tags")),
        })
        items.append(item)
        if len(items) >= limit:
            break
    return items


def _summarize_visual_mapping_linked_rules(rules, limit=200):
    items = []
    for index, rule in enumerate([_ensure_linked_rule(copy.deepcopy(r)) for r in (rules or []) if isinstance(r, dict)], start=1):
        item = copy.deepcopy(rule)
        item.update({
            "index": index,
            "name": _as_text(rule.get("name")) or f"linked_{index}",
            "enabled": bool(rule.get("enabled", True)),
            "trigger": _as_text(rule.get("trigger_rule") or LINKED_RULE_ANY) or LINKED_RULE_ANY,
            "trigger_tags": _normalize_event_tags(rule.get("trigger_tags")),
            "target_mode": _as_text(rule.get("target_mode") or LINK_TARGET_TRIGGER_OFFSET) or LINK_TARGET_TRIGGER_OFFSET,
            "value_source": _as_text(rule.get("value_source") or LINK_VALUE_TEMPLATE) or LINK_VALUE_TEMPLATE,
            "write_mode": _as_text(rule.get("write_mode") or LINK_WRITE_REPLACE) or LINK_WRITE_REPLACE,
            "area_enabled": bool(rule.get("area_enabled", False)),
            "overflow_policy": _as_text(rule.get("overflow_policy") or LINK_OVERFLOW_SKIP) or LINK_OVERFLOW_SKIP,
            "action_count": len(rule.get("actions", []) or []),
        })
        items.append(item)
        if len(items) >= limit:
            break
    return items


def _format_visual_mapping_locator(locator):
    sheet = _as_text(locator.get("sheet_name"))
    row = _as_text(locator.get("row_index"))
    col = _as_text(locator.get("col_index"))
    address = _as_text(locator.get("cell_address"))
    if address:
        return f"{sheet} {address}".strip()
    if row or col:
        return f"{sheet} R{row}C{col}".strip()
    return sheet


def _load_settings(context):
    path = _settings_path(context)
    default = {"version": 1, "configs": {"default": _empty_config()}}
    data, info = load_json_with_backup(path, default=default)
    if not isinstance(data, dict):
        raise ValueError("settings root must be object")
    warning = info.get("warning", "")
    if warning and isinstance(context, dict):
        warnings = context.setdefault("settings_warnings", [])
        if warning not in warnings:
            warnings.append(warning)
    data.setdefault("version", 1)
    data.setdefault("configs", {})
    data["configs"].setdefault("default", _empty_config())
    for name, cfg in list(data["configs"].items()):
        data["configs"][name] = _ensure_config(cfg)
    return data


def _save_settings(context, data):
    path = _settings_path(context)
    atomic_write_json(path, data)
    return str(path)


def _get_config(params, context):
    settings = _load_settings(context)
    name = _as_text((params or {}).get("config_name", "default")) or "default"
    cfg = copy.deepcopy(settings.get("configs", {}).get(name, _empty_config()))
    _ensure_config(cfg)
    return name, cfg, settings


def _save_config(params, context, cfg):
    name = _as_text((params or {}).get("config_name", "default")) or "default"
    settings = _load_settings(context)
    settings.setdefault("configs", {})[name] = copy.deepcopy(_ensure_config(cfg))
    return _save_settings(context, settings)


def _all_tables(input_data, context):
    tables = {}
    if isinstance(input_data, dict):
        for key, value in (input_data.get("tables") or {}).items():
            if isinstance(value, dict):
                tables[str(key)] = value
        if input_data.get("type") == "table" or "headers" in input_data or "rows" in input_data:
            tables.setdefault("当前表", input_data)
            tables.setdefault("workflow_current", input_data)
            tables.setdefault("primary", input_data)
    for key, value in ((context or {}).get("input_tables") or {}).items():
        if isinstance(value, dict):
            tables.setdefault(str(key), value)
    return tables


def _pick_table(input_data, context, alias, fallback="当前表"):
    tables = _all_tables(input_data, context)
    alias = _as_text(alias)
    if alias and alias in tables:
        return tables[alias], alias
    if fallback in tables:
        return tables[fallback], fallback
    if tables:
        key = next(iter(tables.keys()))
        return tables[key], key
    return {"type": "table", "headers": [], "rows": []}, ""


def _pick_optional_table(input_data, context, alias):
    tables = _all_tables(input_data, context)
    alias = _as_text(alias)
    if alias and alias in tables:
        return tables[alias], alias
    return {"type": "table", "headers": [], "rows": []}, ""


def _truthy(value):
    if isinstance(value, bool):
        return value
    return _as_text(value).lower() in ("1", "true", "yes", "y", "是", "合并")


def _parse_meta_json(value):
    text = _as_text(value)
    if not text:
        return {}
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _normalize_doc_record(headers, row, row_no, params=None):
    d = _row_dict(headers, row)
    params = params or {}
    source_field = _as_text(params.get("source_file_field", "source_file")) or "source_file"
    source_file = _as_text(d.get(source_field) if source_field in d else "")
    if not source_file:
        source_file = _as_text(d.get("source_file") or d.get("file_path") or d.get("完整路径") or d.get("文件路径"))
    sheet_name = _as_text(d.get("sheet_name") or d.get("table_name") or d.get("sheet") or d.get("表名"))
    block_type = _as_text(d.get("block_type") or d.get("类型"))
    row_index = _to_int(d.get("row_index"), 0)
    col_index = _to_int(d.get("col_index"), 0)
    cell_address = _as_text(d.get("cell_address") or d.get("地址"))
    text = _cell_text(d.get("text") if "text" in d else d.get("内容"))
    meta = _parse_meta_json(d.get("meta_json"))
    is_merged = _truthy(d.get("is_merged", meta.get("is_merged", False)))
    is_merge_origin = not is_merged or _truthy(d.get("is_merge_origin", meta.get("is_merge_origin", True)))
    row_span = max(1, _to_int(d.get("row_span", meta.get("row_span", 1)), 1))
    col_span = max(1, _to_int(d.get("col_span", meta.get("col_span", 1)), 1))
    merge_origin_row = _to_int(d.get("merge_origin_row", meta.get("merge_origin_row", row_index)), row_index)
    merge_origin_col = _to_int(d.get("merge_origin_col", meta.get("merge_origin_col", col_index)), col_index)
    merged_range = _as_text(d.get("merged_range") or meta.get("merged_range", ""))
    normalized_meta = dict(meta)
    normalized_meta.update({
        "is_merged": is_merged,
        "is_merge_origin": is_merge_origin,
        "row_span": row_span,
        "col_span": col_span,
        "merge_origin_row": merge_origin_row,
        "merge_origin_col": merge_origin_col,
        "merged_range": merged_range,
    })
    if not sheet_name:
        sheet_name = "table_1" if block_type.startswith("word_table") else "Sheet1"
    return {
        "raw": d,
        "meta": normalized_meta,
        "meta_json": json.dumps(normalized_meta, ensure_ascii=False),
        "source_row": row_no,
        "source_file": source_file,
        "block_type": block_type,
        "sheet_name": sheet_name,
        "row_index": row_index,
        "col_index": col_index,
        "cell_address": cell_address,
        "text": text,
        "is_merged": is_merged,
        "is_merge_origin": is_merge_origin,
        "row_span": row_span,
        "col_span": col_span,
        "merge_origin_row": merge_origin_row,
        "merge_origin_col": merge_origin_col,
        "merged_range": merged_range,
    }


def _doc_records(table, params=None):
    headers = list(table.get("headers", []) or [])
    rows = [list(r) for r in (table.get("rows", []) or [])]
    records = [_normalize_doc_record(headers, row, i, params) for i, row in enumerate(rows, start=1)]
    return [r for r in records if r.get("is_merge_origin", True)]


def _content_rows(table):
    headers = list(table.get("headers", []) or [])
    rows = [list(r) for r in (table.get("rows", []) or [])]
    field_names = [_as_text(v) or f"字段{i + 1}" for i, v in enumerate(headers)]
    data_rows = rows
    used = {}
    unique_fields = []
    for field in field_names:
        base = field or "字段"
        if base in used:
            used[base] += 1
            field = f"{base}_{used[base]}"
        else:
            used[base] = 1
        unique_fields.append(field)
    records = []
    for row_no, row in enumerate(data_rows, start=1):
        rec = {field: _safe_cell(row, i) for i, field in enumerate(unique_fields)}
        rec["__content_row__"] = row_no
        records.append(rec)
    return unique_fields, records


def _table_row_context(tables, content_alias="", aux_alias=""):
    rows_by_alias = {}
    fields_by_alias = {}
    for alias, table in (tables or {}).items():
        if not isinstance(table, dict):
            continue
        fields, rows = _content_rows(table)
        alias = _as_text(alias)
        rows_by_alias[alias] = rows
        fields_by_alias[alias] = fields
    return {
        "rows_by_alias": rows_by_alias,
        "fields_by_alias": fields_by_alias,
        "content_alias": _as_text(content_alias),
        "aux_alias": _as_text(aux_alias),
    }


def _match_text(text, match_cfg):
    cfg = match_cfg or {}
    if not cfg.get("enabled", False):
        return True, "未启用输入源匹配"
    mode = _as_text(cfg.get("mode") or cfg.get("operator") or "包含") or "包含"
    value = _as_text(cfg.get("value"))
    text = _cell_text(text)
    if cfg.get("regex", False) and mode in ("包含", "contains"):
        mode = "regex"
    try:
        if mode in ("包含", "contains"):
            return value in text, f"包含 {value}"
        if mode in ("等于", "==", "equals"):
            return text == value, f"等于 {value}"
        if mode in ("不等于", "!=", "not_equals"):
            return text != value, f"不等于 {value}"
        if mode in ("正则", "正则匹配", "regex"):
            return re.search(value, text) is not None, f"正则 {value}"
        if mode in ("正则不匹配", "not_regex"):
            return re.search(value, text) is None, f"正则不匹配 {value}"
        if mode in ("为空", "empty"):
            return text == "", "为空"
        if mode in ("非空", "not_empty"):
            return text != "", "非空"
    except Exception as exc:
        return False, f"匹配异常：{exc}"
    return True, f"未知匹配方式按通过处理：{mode}"


def _legacy_conditions_from_match_cfg(cfg, mode_key="mode", value_key="value"):
    cfg = cfg or {}
    conditions = [item for item in (cfg.get("conditions") or []) if isinstance(item, dict)]
    if conditions:
        return conditions
    mode = _as_text(cfg.get(mode_key) or cfg.get("operator") or "包含") or "包含"
    value = _as_text(cfg.get(value_key))
    return [{
        "join": "AND",
        "mode": mode,
        "value_source": "手动输入",
        "value": value,
        "value_field": "",
        "row_policy": REPLACE_ROW_CONTENT_ROW,
        "row_index": "1",
    }]


def _doc_record_field_value(record, field):
    field = _as_text(field)
    if not field:
        return ""
    if isinstance(record, dict) and field in record:
        return record.get(field)
    raw = (record or {}).get("raw") if isinstance(record, dict) else {}
    if isinstance(raw, dict) and field in raw:
        return raw.get(field)
    return ""


def _condition_value_from_source(cond, content=None, table_context=None, doc_record=None, source_records=None, match_index=0):
    cond = cond or {}
    source = _normalize_batch_table_source(cond.get("value_source") or cond.get("match_value_source") or "手动输入")
    field = _as_text(cond.get("value_field") or cond.get("match_value_field") or cond.get("field"))
    if _is_manual_batch_source(source):
        return _cell_text(cond.get("value") or cond.get("match_value")), "手动输入", True
    if source in ("文档读取表字段", "当前格字段", "doc_field"):
        if not field:
            return "", "文档读取表字段未设置字段", False
        return _cell_text(_doc_record_field_value(doc_record, field)), f"文档读取表字段 {field}", True

    table_context = table_context or {}
    rows_by_alias = table_context.get("rows_by_alias") or {}
    content_alias = _as_text(table_context.get("content_alias"))
    rows = rows_by_alias.get(source)
    if rows is None and source == content_alias:
        rows = [content or {}]
    if rows is None:
        return "", f"未找到来源表：{source}", False
    if not field:
        return "", f"未设置来源字段：{source}", False

    policy = _normalize_replace_row_policy(cond.get("row_policy") or cond.get("match_row_policy") or cond.get("match_value_row_policy"))
    rows = rows or []
    if policy == REPLACE_ROW_CONTENT_ROW:
        row_index = max(0, _to_int((content or {}).get("__content_row__"), 1) - 1)
        row = (content or {}) if source == content_alias else (rows[row_index] if 0 <= row_index < len(rows) else {})
        note = f"{source}.{field} 当前内容行第{row_index + 1}行"
    elif policy == REPLACE_ROW_FIRST:
        row_index = 0
        row = rows[0] if rows else {}
        note = f"{source}.{field} 第一行"
    elif policy == REPLACE_ROW_FIXED:
        row_index = max(0, _to_int(cond.get("row_index") or cond.get("match_row_index"), 1) - 1)
        row = rows[row_index] if 0 <= row_index < len(rows) else {}
        note = f"{source}.{field} 固定第{row_index + 1}行"
    elif policy == REPLACE_ROW_HIT_INDEX:
        row_index = max(0, int(match_index or 1) - 1)
        row = rows[row_index] if 0 <= row_index < len(rows) else {}
        note = f"{source}.{field} 按命中序号第{row_index + 1}行"
    else:
        row_index = max(0, int(match_index or 1) - 1)
        row = rows[row_index] if 0 <= row_index < len(rows) else {}
        note = f"{source}.{field} 按匹配行号第{row_index + 1}行"
    if not row:
        return "", f"{note}越界，可用{len(rows)}行", False
    return _cell_text(row.get(field)), note, True


def _match_text_with_sources(text, match_cfg, content=None, table_context=None, doc_record=None, source_records=None, match_index=0, mode_key="mode", value_key="value"):
    cfg = match_cfg or {}
    if not cfg.get("enabled", False):
        return True, "未启用输入源匹配"
    conditions = _legacy_conditions_from_match_cfg(cfg, mode_key, value_key)
    default_logic = _as_text(cfg.get("logic") or "AND") or "AND"
    text = _cell_text(text)
    result = None
    details = []
    for index, cond in enumerate(conditions):
        join = _condition_join(cond, index, default_logic)
        value, source_detail, source_ok = _condition_value_from_source(cond, content, table_context, doc_record, source_records, match_index)
        mode = _as_text(cond.get("mode") or "包含") or "包含"
        if source_ok:
            ok, detail = _match_text(text, {"enabled": True, "mode": mode, "value": value})
            detail = f"{detail}；来源={source_detail}"
        else:
            ok, detail = False, source_detail
        if result is None:
            result = ok
            details.append(f"{detail}=>{ok}")
        elif join == "OR":
            result = bool(result) or ok
            details.append(f"OR {detail}=>{ok}")
        else:
            result = bool(result) and ok
            details.append(f"AND {detail}=>{ok}")
    return bool(result), "；".join(details) if details else "未设置匹配条件"


def _cell_key(record):
    return f"{record.get('source_file','')}|{record.get('sheet_name','')}|{record.get('row_index','')}|{record.get('col_index','')}"


def _plan_object_key(target_file, record):
    if not isinstance(record, dict):
        return ""
    parts = [
        _as_text(target_file),
        _as_text(record.get("source_file")),
        _as_text(record.get("block_type")),
        _as_text(record.get("sheet_name")),
        _as_text(record.get("row_index")),
        _as_text(record.get("col_index")),
        _as_text(record.get("cell_address")),
    ]
    if not any(parts[1:]):
        return ""
    return "|".join(parts)


def _append_unique(values, value):
    value = _as_text(value)
    if value and value not in values:
        values.append(value)


def _build_doc_index(records):
    index = {}
    by_file_sheet = {}
    for rec in records:
        index[_cell_key(rec)] = rec
        fs = (rec.get("source_file", ""), rec.get("sheet_name", ""))
        by_file_sheet.setdefault(fs, []).append(rec)
    return index, by_file_sheet


def _match_anchor(records, anchor_cfg, content=None, table_context=None):
    cfg = anchor_cfg or {}
    if not cfg.get("enabled", False):
        return None, "未启用锚点"
    axis = _as_text(cfg.get("axis", "列")) or "列"
    index = _to_int(cfg.get("index"), 0)
    if index <= 0:
        return None, "锚点行/列未设置"
    candidates = []
    match_index = 0
    for rec in records:
        if axis in ("列", "column") and int(rec.get("col_index") or 0) != index:
            continue
        if axis in ("行", "row") and int(rec.get("row_index") or 0) != index:
            continue
        match_index += 1
        ok, detail = _match_text_with_sources(
            rec.get("text", ""),
            cfg,
            content=content,
            table_context=table_context,
            doc_record=rec,
            source_records=records,
            match_index=match_index,
            mode_key="match_mode",
            value_key="value",
        )
        if ok:
            candidates.append(rec)
    if not candidates:
        return None, "锚点未命中"
    return candidates[0], f"锚点命中 {len(candidates)} 个，使用第一个"


def _locate_target_record(rule, source_records, source_file, content=None, table_context=None):
    locator = rule.get("source_locator", {}) or {}
    sheet_name = _as_text(locator.get("sheet_name"))
    base_row = _to_int(locator.get("row_index"), 0)
    base_col = _to_int(locator.get("col_index"), 0)
    records = [r for r in source_records if (not sheet_name or r.get("sheet_name") == sheet_name)]
    anchor_cfg = rule.get("anchor", {}) or {}
    anchor_detail = "未启用锚点"
    if anchor_cfg.get("enabled", False):
        anchor_rec, anchor_detail = _match_anchor(records, anchor_cfg, content=content, table_context=table_context)
        if anchor_rec is None:
            return None, anchor_detail
        row_offset = _to_int(anchor_cfg.get("row_offset"), 0)
        col_offset = _to_int(anchor_cfg.get("col_offset"), 0)
        target_row = int(anchor_rec.get("row_index") or 0) + row_offset
        target_col = int(anchor_rec.get("col_index") or 0) + col_offset
    else:
        target_row = base_row
        target_col = base_col
    for rec in records:
        if rec.get("source_file", "") == source_file and int(rec.get("row_index") or 0) == target_row and int(rec.get("col_index") or 0) == target_col:
            return rec, anchor_detail
    return None, f"目标单元格未找到 R{target_row}C{target_col}"


def _condition_join(cond, index, default_logic="AND"):
    if index <= 0:
        return ""
    join = _as_text((cond or {}).get("join") or default_logic or "AND").upper()
    if join in ("OR", "或"):
        return "OR"
    return "AND"


def _match_condition_chain(text, conditions, default_logic="AND"):
    valid_conditions = [c for c in (conditions or []) if isinstance(c, dict)]
    if not valid_conditions:
        return True, "未设置匹配条件"
    result = None
    details = []
    for index, cond in enumerate(valid_conditions):
        ok, detail = _match_text(text, {
            "enabled": True,
            "mode": cond.get("mode", "包含"),
            "value": cond.get("value", ""),
        })
        join = _condition_join(cond, index, default_logic)
        if result is None:
            result = ok
            details.append(f"{detail}=>{ok}")
        elif join == "OR":
            result = bool(result) or ok
            details.append(f"OR {detail}=>{ok}")
        else:
            result = bool(result) and ok
            details.append(f"AND {detail}=>{ok}")
    return bool(result), "；".join(details)


def _extract_group_span(match, group_index=1):
    group_index = _to_int(group_index, 1)
    if group_index <= 0:
        return match.span(0), _cell_text(match.group(0)), "0"
    try:
        if match.lastindex and group_index <= match.lastindex and match.start(group_index) >= 0:
            return match.span(group_index), _cell_text(match.group(group_index)), str(group_index)
    except Exception:
        pass
    try:
        if match.lastindex:
            for index in range(1, match.lastindex + 1):
                if match.start(index) >= 0:
                    return match.span(index), _cell_text(match.group(index)), str(index)
    except Exception:
        pass
    return match.span(0), _cell_text(match.group(0)), "0"


def _condition_extract_items(text, conditions, default_logic="AND"):
    ok, detail = _match_condition_chain(text, conditions, default_logic)
    text = _cell_text(text)
    if not ok:
        return False, detail, []
    valid_conditions = [c for c in (conditions or []) if isinstance(c, dict)]
    if not valid_conditions:
        return True, detail, [{"span": (0, len(text)), "value": text, "note": "未设置匹配条件，使用全文"}]
    regex_items = []
    for cond in valid_conditions:
        mode = _as_text(cond.get("mode", "包含"))
        value = _as_text(cond.get("value"))
        if mode not in ("正则", "正则匹配", "regex") or not value:
            continue
        cond_ok, _cond_detail = _match_text(text, {"enabled": True, "mode": mode, "value": value})
        if not cond_ok:
            continue
        try:
            for match_index, match in enumerate(re.finditer(value, text), start=1):
                (start, end), extracted_value, used_group = _extract_group_span(match, 1)
                regex_items.append({
                    "span": (start, end),
                    "value": extracted_value,
                    "note": f"正则条件提取{match_index} 组{used_group}",
                    "full_span": match.span(0),
                    "full_match": _cell_text(match.group(0)),
                    "group": used_group,
                })
        except Exception as exc:
            return False, f"{detail}；条件提取异常：{exc}", []
        if regex_items:
            return True, detail, regex_items
    return True, detail, [{"span": (0, len(text)), "value": text, "note": "条件命中，使用全文"}]


def _target_items_for_batch_scope(text, condition_items, scope):
    text = _cell_text(text)
    scope = _normalize_batch_target_scope(scope)
    condition_items = [item for item in (condition_items or []) if isinstance(item, dict)]
    if scope == BATCH_TARGET_FULL_TEXT:
        seed = condition_items[0] if condition_items else {}
        condition_value = _cell_text(seed.get("value"))
        full_match = _cell_text(seed.get("full_match", condition_value))
        return [{
            "span": (0, len(text)),
            "value": text,
            "note": BATCH_TARGET_FULL_TEXT,
            "full_span": (0, len(text)),
            "full_match": full_match,
            "condition_value": condition_value,
            "group": _as_text(seed.get("group", "")),
        }]
    if scope == BATCH_TARGET_FULL_MATCH:
        targets = []
        seen = set()
        for item in condition_items:
            try:
                start, end = item.get("full_span", item.get("span", (0, len(text))))
                start = int(start)
                end = int(end)
            except Exception:
                start, end = 0, len(text)
            start = max(0, min(start, len(text)))
            end = max(start, min(end, len(text)))
            key = (start, end)
            if key in seen:
                continue
            seen.add(key)
            value = _cell_text(item.get("full_match", text[start:end]))
            targets.append({
                "span": (start, end),
                "value": value,
                "note": BATCH_TARGET_FULL_MATCH,
                "full_span": (start, end),
                "full_match": value,
                "condition_value": _cell_text(item.get("value")),
                "group": _as_text(item.get("group", "")),
            })
        return targets
    return condition_items


def _feature_condition_pass(condition, source_records, source_file="", sheet_name=""):
    cond = condition or {}
    cond_sheet = _cfg_sheet_name(cond.get("sheet_name")) or _cfg_sheet_name(sheet_name)
    row_index = _to_int(cond.get("row_index"), 0)
    col_index = _to_int(cond.get("col_index"), 0)
    candidates = []
    for rec in source_records:
        if source_file and rec.get("source_file", "") != source_file:
            continue
        if cond_sheet and rec.get("sheet_name", "") != cond_sheet:
            continue
        if row_index > 0 and int(rec.get("row_index") or 0) != row_index:
            continue
        if col_index > 0 and int(rec.get("col_index") or 0) != col_index:
            continue
        candidates.append(rec)
    if not candidates:
        loc = f"{cond_sheet or '*'} R{row_index or '*'}C{col_index or '*'}"
        return False, f"特征候选为空：{loc}"
    for rec in candidates:
        ok, detail = _match_text(rec.get("text", ""), {
            "enabled": True,
            "mode": cond.get("mode", "包含"),
            "value": cond.get("value", ""),
        })
        if ok:
            return True, f"命中 {rec.get('sheet_name','')} R{rec.get('row_index')}C{rec.get('col_index')}：{detail}"
    return False, f"候选 {len(candidates)} 个均未通过"


def _feature_pass(feature_name, features, source_records, source_file="", sheet_name=""):
    name = _cfg_feature_name(feature_name)
    if not name:
        return True, "未绑定表特征"
    feature = None
    for item in features or []:
        if isinstance(item, dict) and _as_text(item.get("name")) == name:
            feature = item
            break
    if feature is None:
        return False, f"表特征不存在：{name}"
    if not feature.get("enabled", True):
        return False, f"表特征已停用：{name}"
    conditions = [c for c in feature.get("conditions", []) if isinstance(c, dict)]
    if not conditions:
        return True, f"表特征 {name} 未设置条件，按通过处理"
    result = None
    details = []
    default_logic = _as_text(feature.get("logic", "AND")) or "AND"
    for index, cond in enumerate(conditions):
        ok, detail = _feature_condition_pass(cond, source_records, source_file, sheet_name)
        join = _condition_join(cond, index, default_logic)
        if result is None:
            result = ok
            details.append(f"{detail}=>{ok}")
        elif join == "OR":
            result = bool(result) or ok
            details.append(f"OR {detail}=>{ok}")
        else:
            result = bool(result) and ok
            details.append(f"AND {detail}=>{ok}")
    return bool(result), f"表特征 {name}：" + "；".join(details)


def _global_rule_records(rule, source_records):
    scope = _as_text(rule.get("scope", "全部")) or "全部"
    sheet_name = _cfg_sheet_name(rule.get("sheet_name"))
    result = []
    for rec in source_records:
        block_type = _as_text(rec.get("block_type"))
        if sheet_name and rec.get("sheet_name", "") != sheet_name:
            continue
        if scope in ("段落", "paragraph") and "paragraph" not in block_type:
            continue
        if scope in ("表格单元格", "table_cell") and "table" not in block_type and int(rec.get("row_index") or 0) <= 0:
            continue
        result.append(rec)
    return result


def _expand_template(text, content):
    template = _cell_text(text)
    missing = []

    def replace_match(match):
        key = _as_text(match.group(1))
        if key not in content:
            missing.append(key)
            return match.group(0)
        return _cell_text(content.get(key))

    result = re.sub(r"\{([^{}]+)\}", replace_match, template)
    if missing:
        raise ValueError("模板缺少字段：" + "、".join(dict.fromkeys(missing)))
    return result


def _normalize_batch_value_source(value):
    text = _as_text(value) or "手动输入"
    if text in ("辅助表字段", "辅助表", "aux_field", "列字段"):
        return "辅助表字段"
    if text in ("辅助表固定值", "aux_fixed"):
        return "辅助表固定值"
    if text in ("新内容字段", "内容字段", "content_field"):
        return "新内容字段"
    return "手动输入"


def _normalize_batch_table_source(value):
    text = _as_text(value)
    if not text or text in ("manual", "fixed", "固定值", "手工输入"):
        return "手动输入"
    return text


def _is_manual_batch_source(value):
    return _normalize_batch_table_source(value) == "手动输入"


def _legacy_batch_match_source(rule, params=None):
    source = _normalize_batch_value_source((rule or {}).get("value_source"))
    params = params or {}
    if source in ("辅助表字段", "辅助表固定值"):
        return _as_text(params.get("replace_aux_table_alias") or "替换辅助表")
    if source == "新内容字段":
        return _as_text(params.get("content_table_alias") or "新内容表")
    return "手动输入"


def _legacy_batch_replace_source(rule, params=None):
    source = _normalize_batch_value_source((rule or {}).get("value_source"))
    params = params or {}
    if source == "辅助表字段":
        return _as_text(params.get("replace_aux_table_alias") or "替换辅助表")
    if source == "新内容字段":
        return _as_text(params.get("content_table_alias") or "新内容表")
    return "手动输入"


def _batch_match_source(rule, params=None):
    return _normalize_batch_table_source((rule or {}).get("match_value_source") or _legacy_batch_match_source(rule, params))


def _batch_replace_source(rule, params=None):
    return _normalize_batch_table_source((rule or {}).get("replace_value_source") or _legacy_batch_replace_source(rule, params))


def _normalize_batch_target_scope(value):
    text = _as_text(value)
    if text in ("原文整格", "原文", "整格", "全文", "full_text", "source_text"):
        return BATCH_TARGET_FULL_TEXT
    if text in ("完整正则匹配", "完整匹配", "正则完整匹配", "full_match", "regex_match"):
        return BATCH_TARGET_FULL_MATCH
    return BATCH_TARGET_CONDITION_VALUE


def _batch_target_scope(rule):
    return _normalize_batch_target_scope((rule or {}).get("batch_target_scope") or (rule or {}).get("target_scope"))


def _normalize_replace_row_policy(value):
    text = _as_text(value)
    if text in ("当前内容行", "内容行", "当前新内容行", "content_row"):
        return REPLACE_ROW_CONTENT_ROW
    if text in ("第一行", "首行", "first"):
        return REPLACE_ROW_FIRST
    if text in ("固定行号", "固定行", "指定行", "fixed"):
        return REPLACE_ROW_FIXED
    if text in ("按命中序号", "命中序号", "hit_index"):
        return REPLACE_ROW_HIT_INDEX
    return REPLACE_ROW_MATCH_INDEX


def _batch_replace_row_policy(rule):
    return _normalize_replace_row_policy((rule or {}).get("replace_row_policy") or (rule or {}).get("row_policy"))


def _batch_match_row_policy(rule):
    return _normalize_replace_row_policy((rule or {}).get("match_row_policy") or (rule or {}).get("match_value_row_policy"))


def _short_preview_text(value, limit=90):
    text = _cell_text(value).replace("\r", "\\r").replace("\n", "\\n")
    limit = max(10, int(limit or 90))
    return text if len(text) <= limit else text[:limit] + "..."


def _canvas_preview_text(value):
    text = _cell_text(value)
    if text == "":
        return "[空字符串]"
    if text.strip() == "":
        return f"[空格 x {len(text)}]"
    return text


def _compare_batch_text(text, pattern, mode, case_sensitive=True):
    text = "" if text is None else str(text)
    pattern = "" if pattern is None else str(pattern)
    mode = _as_text(mode) or "包含"
    if mode == "为空":
        return text == ""
    if mode in ("不为空", "非空"):
        return text != ""
    if mode == "正则匹配":
        flags = 0 if case_sensitive else re.IGNORECASE
        return re.search(pattern, text, flags) is not None
    cmp_text = text if case_sensitive else text.lower()
    cmp_pattern = pattern if case_sensitive else pattern.lower()
    if mode in ("等于", "完全相等"):
        return cmp_text == cmp_pattern
    if mode == "不等于":
        return cmp_text != cmp_pattern
    if mode == "开头是":
        return cmp_text.startswith(cmp_pattern)
    if mode == "结尾是":
        return cmp_text.endswith(cmp_pattern)
    if mode == "不包含":
        return cmp_pattern not in cmp_text
    return cmp_pattern in cmp_text


def _replace_batch_text(text, match_value, replace_value, match_mode, replace_mode, case_sensitive=True, count=0):
    text = "" if text is None else str(text)
    match_value = "" if match_value is None else str(match_value)
    replace_value = "" if replace_value is None else str(replace_value)
    replace_mode = _as_text(replace_mode) or "局部替换匹配字符串"
    count = _to_int(count, 0)
    if replace_mode == "整格替换为新值":
        return replace_value, 1 if replace_value != text else 0
    if match_mode == "正则匹配":
        flags = 0 if case_sensitive else re.IGNORECASE
        return re.subn(match_value, replace_value, text, count=0 if count <= 0 else count, flags=flags)
    if not match_value:
        return text, 0
    if case_sensitive:
        replaced = text.count(match_value) if count <= 0 else min(text.count(match_value), count)
        return text.replace(match_value, replace_value, count if count > 0 else -1), replaced
    new_text, replaced = re.subn(re.escape(match_value), replace_value, text, count=0 if count <= 0 else count, flags=re.IGNORECASE)
    return new_text, replaced


def _batch_template_context(content, aux_row=None, extract=None, source_rows=None):
    data = dict(content or {})
    extract = extract or {}
    for key, value in extract.items():
        data[key] = value
    if aux_row:
        for key, value in aux_row.items():
            key = _as_text(key)
            if not key:
                continue
            data.setdefault(key, value)
            data[f"辅助.{key}"] = value
            data[f"aux.{key}"] = value
    for alias, row in (source_rows or {}).items():
        alias = _as_text(alias)
        if not alias or not isinstance(row, dict):
            continue
        for key, value in row.items():
            key = _as_text(key)
            if not key:
                continue
            data.setdefault(key, value)
            data[f"{alias}.{key}"] = value
    return data


def _batch_source_rows(source, table_context, content):
    source = _normalize_batch_table_source(source)
    if _is_manual_batch_source(source):
        return []
    table_context = table_context or {}
    content_alias = _as_text(table_context.get("content_alias"))
    if source == content_alias:
        return [content or {}]
    rows_by_alias = table_context.get("rows_by_alias") or {}
    if source not in rows_by_alias:
        raise ValueError(f"未找到来源表：{source}")
    return rows_by_alias.get(source) or []


def _batch_row_at(source, rows, index, content, table_context):
    source = _normalize_batch_table_source(source)
    if _is_manual_batch_source(source):
        return None
    if source == _as_text((table_context or {}).get("content_alias")):
        return content or {}
    return rows[index] if 0 <= index < len(rows or []) else {}


def _batch_replace_row_at(source, rows, pair_index, content, table_context, extract, rule):
    source = _normalize_batch_table_source(source)
    if _is_manual_batch_source(source):
        return None, "", True
    policy = _batch_replace_row_policy(rule)
    if source == _as_text((table_context or {}).get("content_alias")):
        return content or {}, f"替换行策略={policy}：当前内容行", True
    rows = rows or []
    if policy == REPLACE_ROW_CONTENT_ROW:
        row_index = max(0, _to_int((content or {}).get("__content_row__"), 1) - 1)
    elif policy == REPLACE_ROW_FIRST:
        row_index = 0
    elif policy == REPLACE_ROW_FIXED:
        row_index = max(0, _to_int((rule or {}).get("replace_row_index"), 1) - 1)
    elif policy == REPLACE_ROW_HIT_INDEX:
        row_index = max(0, _to_int((extract or {}).get("序号"), 1) - 1)
    else:
        row_index = pair_index
    note = f"替换行策略={policy}：第{row_index + 1}行"
    if policy == REPLACE_ROW_MATCH_INDEX:
        return (rows[row_index] if 0 <= row_index < len(rows) else {}), note, True
    if 0 <= row_index < len(rows):
        return rows[row_index], note, True
    return {}, f"{note}越界，可用{len(rows)}行", False


def _batch_match_row_at(source, rows, pair_index, content, table_context, extract, rule):
    source = _normalize_batch_table_source(source)
    if _is_manual_batch_source(source):
        return None, "", True
    policy = _batch_match_row_policy(rule)
    if source == _as_text((table_context or {}).get("content_alias")):
        return content or {}, f"匹配行策略={policy}：当前内容行", True
    rows = rows or []
    if policy == REPLACE_ROW_CONTENT_ROW:
        row_index = max(0, _to_int((content or {}).get("__content_row__"), 1) - 1)
    elif policy == REPLACE_ROW_FIRST:
        row_index = 0
    elif policy == REPLACE_ROW_FIXED:
        row_index = max(0, _to_int((rule or {}).get("match_row_index"), 1) - 1)
    elif policy == REPLACE_ROW_HIT_INDEX:
        row_index = max(0, _to_int((extract or {}).get("序号"), 1) - 1)
    else:
        row_index = pair_index
    note = f"匹配行策略={policy}：第{row_index + 1}行"
    if policy == REPLACE_ROW_MATCH_INDEX:
        return (rows[row_index] if 0 <= row_index < len(rows) else {}), note, True
    if 0 <= row_index < len(rows):
        return rows[row_index], note, True
    return {}, f"{note}越界，可用{len(rows)}行", False


def _iter_batch_rule_pairs(rule, content, aux_rows, extract, table_context=None, params=None):
    match_source = _batch_match_source(rule, params)
    replace_source = _batch_replace_source(rule, params)
    match_field = _as_text(rule.get("match_value_field"))
    replace_field = _as_text(rule.get("replace_value_field"))
    match_is_manual = _is_manual_batch_source(match_source)
    replace_is_manual = _is_manual_batch_source(replace_source)
    match_row_policy = _batch_match_row_policy(rule)
    replace_row_policy = _batch_replace_row_policy(rule)
    table_context = table_context or {}
    if not table_context:
        table_context = {
            "content_alias": _as_text((params or {}).get("content_table_alias") or "新内容表"),
            "rows_by_alias": {
                _as_text((params or {}).get("replace_aux_table_alias") or "替换辅助表"): list(aux_rows or []),
            },
        }
    if not match_is_manual and not match_field:
        raise ValueError(f"未设置匹配值字段：{match_source}")
    if not replace_is_manual and not replace_field:
        raise ValueError(f"未设置替换值字段：{replace_source}")
    match_rows = [] if match_is_manual else _batch_source_rows(match_source, table_context, content)
    replace_rows = [] if replace_is_manual else _batch_source_rows(replace_source, table_context, content)
    if not match_is_manual and match_row_policy == REPLACE_ROW_MATCH_INDEX:
        total_rows = len(match_rows)
    elif not replace_is_manual and replace_row_policy == REPLACE_ROW_MATCH_INDEX:
        total_rows = len(replace_rows)
    else:
        total_rows = 1
    skipped = 0
    for index in range(total_rows):
        match_row, match_row_note, match_row_ok = _batch_match_row_at(
            match_source,
            match_rows,
            index,
            content,
            table_context,
            extract,
            rule,
        )
        replace_row, replace_row_note, replace_row_ok = _batch_replace_row_at(
            replace_source,
            replace_rows,
            index,
            content,
            table_context,
            extract,
            rule,
        )
        source_rows = {}
        aux_alias = _as_text(table_context.get("aux_alias") or (params or {}).get("replace_aux_table_alias") or "替换辅助表")
        if isinstance(match_row, dict):
            source_rows[match_source] = match_row
        if isinstance(replace_row, dict):
            source_rows[replace_source] = replace_row
        aux_row = source_rows.get(aux_alias)
        if match_is_manual:
            match_value = _expand_template(rule.get("match_value", ""), _batch_template_context(content, aux_row, extract, source_rows))
        else:
            match_value = _cell_text((match_row or {}).get(match_field))
        if not match_is_manual and not match_row_ok:
            skipped += 1
            continue
        if not match_value and bool(rule.get("skip_empty_match_value", True)):
            skipped += 1
            continue
        if not replace_is_manual and not replace_row_ok:
            skipped += 1
            continue
        if replace_is_manual:
            replace_value = _expand_template(rule.get("replace_value", ""), _batch_template_context(content, aux_row, extract, source_rows))
        else:
            replace_value = _cell_text((replace_row or {}).get(replace_field))
        source_note = f"匹配[{match_source}:{match_field or '手动'}]→替换[{replace_source}:{replace_field or '手动'}]"
        if match_row_note:
            source_note += f"，{match_row_note}"
        if replace_row_note:
            source_note += f"，{replace_row_note}"
        yield match_value, replace_value, source_note, skipped


def _legacy_steps_to_batch_rules(steps):
    rows = []
    for step in steps or []:
        if not isinstance(step, dict):
            continue
        replacement_type = _as_text(step.get("replacement_type") or "固定值")
        if replacement_type in ("新内容字段", "字段", "content_field"):
            value_source = "新内容字段"
            replace_field = _as_text(step.get("replacement_field") or step.get("field"))
            replace_value = ""
        else:
            value_source = "手动输入"
            replace_field = ""
            replace_value = _as_text(step.get("replacement_value"))
        rows.append({
            "enabled": step.get("enabled", True),
            "match_mode": "正则匹配",
            "match_value_source": "手动输入",
            "match_value": _as_text(step.get("pattern") or step.get("regex")),
            "replace_value": replace_value,
            "replace_mode": "局部替换匹配字符串",
            "replace_value_source": "",
            "value_source": value_source,
            "match_value_field": "",
            "replace_value_field": replace_field,
            "case_sensitive": True,
            "skip_empty_match_value": True,
            "count": _as_text(step.get("count") or "0"),
        })
    return rows


def _batch_rules_for_rule(rule):
    return list(rule.get("batch_rules") or []) or _legacy_steps_to_batch_rules(rule.get("replace_steps") or [])


def _apply_batch_rules_to_value(value, rules, content, aux_rows, extract, table_context=None, params=None):
    text = _cell_text(value)
    valid_rules = [r for r in (rules or []) if isinstance(r, dict) and r.get("enabled", True)]
    if not valid_rules:
        return text, "未设置批量替换规则", None
    details = []
    for index, rule in enumerate(valid_rules, start=1):
        match_mode = _as_text(rule.get("match_mode")) or "包含"
        replace_mode = _as_text(rule.get("replace_mode")) or "局部替换匹配字符串"
        case_sensitive = bool(rule.get("case_sensitive", True))
        count = _to_int(rule.get("count"), 0)
        before_rule_text = text
        rule_changed = 0
        pair_count = 0
        skipped_empty = 0
        match_samples = []
        try:
            pairs = list(_iter_batch_rule_pairs(rule, content, aux_rows, extract, table_context, params))
        except Exception as exc:
            return text, "；".join(details), f"批量替换规则{index}异常：{exc}"
        source_note = f"{_batch_match_source(rule, params)}->{_batch_replace_source(rule, params)}"
        for match_value, replace_value, current_source_note, skipped in pairs:
            pair_count += 1
            source_note = current_source_note
            skipped_empty = max(skipped_empty, skipped)
            if len(match_samples) < 3:
                match_samples.append(f"{_short_preview_text(match_value, 40)}->{_short_preview_text(replace_value, 40)}")
            try:
                if not _compare_batch_text(text, match_value, match_mode, case_sensitive):
                    continue
                text, replaced = _replace_batch_text(text, match_value, replace_value, match_mode, replace_mode, case_sensitive, count)
            except Exception as exc:
                return text, "；".join(details), f"批量替换规则{index}异常：{exc}"
            rule_changed += replaced
        detail = (
            f"批量规则{index} {match_mode}/{replace_mode}，"
            f"匹配对象={_short_preview_text(before_rule_text)}，来源{source_note}，替换{rule_changed}次"
        )
        if match_samples:
            detail += "，匹配/替换样例=" + " | ".join(match_samples)
        if skipped_empty:
            detail += f"，跳过空匹配值或无效行{skipped_empty}行"
        if pair_count == 0:
            detail += "，无可用匹配值"
        details.append(detail)
    return text, "；".join(details), None


def _apply_replace_steps(old_text, rule, content, aux_rows=None, condition_items=None, table_context=None, params=None):
    text = _cell_text(old_text)
    rule = rule or {}
    batch_rules = _batch_rules_for_rule(rule)
    target_scope = _batch_target_scope(rule)
    if condition_items is None:
        cond_ok, cond_detail, condition_items = _condition_extract_items(text, rule.get("conditions", []), rule.get("condition_logic", "AND"))
        if not cond_ok:
            return text, cond_detail, None
    condition_items = [item for item in (condition_items or []) if isinstance(item, dict)]
    if not condition_items:
        return text, "匹配条件未提取到可替换值", None
    target_items = _target_items_for_batch_scope(text, condition_items, target_scope)
    if not target_items:
        return text, f"作用对象={target_scope}，未提取到可替换值", None
    parts = []
    last_pos = 0
    extracted = 0
    changed = 0
    detail_items = []
    for item in target_items:
        try:
            start, end = item.get("span", (0, len(text)))
            start = int(start)
            end = int(end)
        except Exception:
            start, end = 0, len(text)
        start = max(0, min(start, len(text)))
        end = max(start, min(end, len(text)))
        if start < last_pos:
            continue
        extracted += 1
        value = _cell_text(item.get("value"))
        condition_value = _cell_text(item.get("condition_value", value))
        full_match = _cell_text(item.get("full_match", value))
        extract = {
            "提取内容": condition_value,
            "匹配值": condition_value,
            "条件命中值": condition_value,
            "完整匹配": full_match,
            "作用对象": value,
            "批量匹配对象": value,
            "原文": text,
            "序号": extracted,
            "group": _as_text(item.get("group", "")),
            "组": _as_text(item.get("group", "")),
        }
        new_value, batch_detail, batch_error = _apply_batch_rules_to_value(value, batch_rules, content, aux_rows or [], extract, table_context, params)
        if batch_error:
            return old_text, "；".join(detail_items), batch_error
        parts.append(text[last_pos:start])
        parts.append(new_value)
        last_pos = end
        if new_value != value:
            changed += 1
        detail_items.append(f"{item.get('note', target_scope)}：匹配对象={value} -> {new_value}；{batch_detail}")
    parts.append(text[last_pos:])
    return "".join(parts), f"作用对象={target_scope}；提取 {extracted} 条，回填变化 {changed} 条；" + "；".join(detail_items[:10]), None


def _global_rule_fields(rule):
    fields = []
    for item in _batch_rules_for_rule(rule):
        if not isinstance(item, dict):
            continue
        match_source = _batch_match_source(item)
        replace_source = _batch_replace_source(item)
        match_field = _as_text(item.get("match_value_field"))
        replace_field = _as_text(item.get("replace_value_field"))
        match_label = _as_text(item.get("match_value")) if _is_manual_batch_source(match_source) else f"{match_source}.{match_field}"
        replace_label = _as_text(item.get("replace_value")) if _is_manual_batch_source(replace_source) else f"{replace_source}.{replace_field}"
        label = f"{match_label}->{replace_label}"
        if label and label not in fields:
            fields.append(label)
    return ",".join(fields) or f"全局规则:{_as_text(rule.get('name'))}"


def _planned_file_field(params):
    return _as_text(params.get("planned_file_field") or params.get("target_file_field") or "target_file") or "target_file"


def _target_file_for_content(content, params, source_file=""):
    field = _planned_file_field(params)
    value = _as_text((content or {}).get(field))
    if not value:
        return ""
    target_path = Path(value)
    if target_path.is_absolute():
        return value
    source_text = _as_text(source_file)
    if not source_text:
        return value
    source_parent = Path(source_text).parent
    if str(source_parent) in ("", "."):
        return value
    return str(source_parent / value)


def _source_files(records, params):
    values = []
    for rec in records:
        value = _as_text(rec.get("source_file"))
        if value and value not in values:
            values.append(value)
    return values or [""]


def _source_file_for_content(_content, source_files, content_index, total_contents, _params):
    if len(source_files) == 1:
        return source_files[0], "唯一源文件"
    if len(source_files) == total_contents and 0 <= content_index < len(source_files):
        return source_files[content_index], "按行号配对"
    return "", "无法确定源文件：请保证只有一个源文件，或源文件数量与新内容行数一致"


def _plan_state_for(states, order, source_file, target_file, rec, content=None):
    key = _plan_object_key(target_file, rec)
    if not key:
        key = f"{_as_text(target_file)}|{_as_text(source_file)}|{id(rec)}"
    state = states.get(key)
    if state is None:
        record = dict(rec or {})
        if not record.get("source_file"):
            record["source_file"] = source_file
        state = {
            "key": key,
            "source_file": source_file,
            "target_file": target_file,
            "record": record,
            "original_text": _cell_text(record.get("text", record.get("old_text", ""))),
            "current_text": _cell_text(record.get("text", record.get("old_text", ""))),
            "mapping_fields": [],
            "content_rows": [],
            "match_rules": [],
            "anchor_rules": [],
            "source_details": [],
            "anchor_details": [],
            "write_notes": [],
            "write_strategy": "",
            "content": content or {},
            "touched": False,
        }
        states[key] = state
        order.append(key)
    elif content:
        state["content"] = content
    return state


def _plan_state_record(state):
    rec = dict((state or {}).get("record") or {})
    rec["text"] = _cell_text((state or {}).get("current_text"))
    return rec


def _update_plan_state(
    state,
    new_text,
    *,
    rule_name="",
    mapping_field="",
    content_row="",
    source_detail="",
    anchor_detail="",
    write_note="",
    anchor_rule="",
    write_strategy="",
):
    before = _cell_text(state.get("current_text"))
    after = _cell_text(new_text)
    state["current_text"] = after
    state["touched"] = True
    _append_unique(state["mapping_fields"], mapping_field)
    _append_unique(state["content_rows"], content_row)
    _append_unique(state["match_rules"], rule_name)
    _append_unique(state["anchor_rules"], anchor_rule)
    _append_unique(state["source_details"], source_detail)
    _append_unique(state["anchor_details"], anchor_detail)
    _append_unique(state["write_notes"], write_note)
    if write_strategy:
        state["write_strategy"] = write_strategy
    return before, after


def _plan_state_to_output_row(state):
    rec = (state or {}).get("record") or {}
    rule_old_text, rule_new_text = _minimal_text_change(
        state.get("original_text", ""),
        state.get("current_text", ""),
    )
    return [
        state.get("source_file", ""),
        state.get("target_file", ""),
        rec.get("block_type", ""),
        rec.get("sheet_name", ""),
        rec.get("row_index", ""),
        rec.get("col_index", ""),
        rec.get("cell_address", ""),
        state.get("current_text", ""),
        state.get("original_text", ""),
        ",".join(state.get("mapping_fields", []) or []),
        ",".join(state.get("content_rows", []) or []),
        "通过",
        " -> ".join(state.get("match_rules", []) or []),
        " | ".join(state.get("anchor_rules", []) or []),
        "；".join(state.get("source_details", []) or []),
        "；".join(state.get("anchor_details", []) or []),
        "；".join(state.get("write_notes", []) or []),
        state.get("write_strategy", ""),
        rec.get("meta_json", json.dumps(rec.get("meta", {}), ensure_ascii=False)),
        "替换第一次",
        rule_old_text,
        rule_new_text,
    ]


def _sort_global_replace_output_rows(rows):
    rows = list(rows or [])
    target_order = {}

    def target_key(row):
        try:
            return _cell_text(row[1]) or _cell_text(row[0])
        except Exception:
            return ""

    for row in rows:
        key = target_key(row)
        if key not in target_order:
            target_order[key] = len(target_order)

    def sort_key(item):
        index, row = item
        try:
            old_text = _cell_text(row[8])
        except Exception:
            old_text = ""
        return (target_order.get(target_key(row), 0), -len(old_text), index)

    return [row for _index, row in sorted(enumerate(rows), key=sort_key)]


def _circled_number(value):
    return _sequence_symbol(value, _default_slot_judgement())


def _sequence_map(slot_rule):
    result = {}
    for item in (_ensure_slot_judgement(slot_rule).get("sequence_symbols") or []):
        if not isinstance(item, dict):
            continue
        index = _to_int(item.get("index"), -1)
        symbol = _cell_text(item.get("symbol", ""))
        if index >= 0 and symbol:
            result[index] = symbol
    return result


def _sequence_symbol(value, slot_rule):
    index = _to_int(value, 0)
    symbol = _sequence_map(slot_rule).get(index)
    if symbol:
        return symbol
    overflow = _as_text((_ensure_slot_judgement(slot_rule)).get("sequence_overflow") or "括号数字")
    if overflow == "报错":
        raise ValueError(f"统一序号 {index} 超出特殊字符映射范围")
    return f"({index})" if index >= 0 else ""


def _sequence_value(text, slot_rule):
    value = _cell_text(text)
    matches = []
    for index, symbol in _sequence_map(slot_rule).items():
        if symbol and symbol in value:
            matches.append((index, -len(symbol)))
    if matches:
        matches.sort()
        return matches[0][0]
    for match in re.finditer(r"\((\d+)\)", value):
        return _to_int(match.group(1), -1)
    return None


def _circled_number_value(text):
    return _sequence_value(text, _default_slot_judgement())


def _parse_date_value(text, config=None):
    try:
        return parse_date_value(text, config or default_date_parser_config())
    except Exception:
        return None


def _record_position_key(source_file, sheet_name, row_index, col_index):
    return (
        _as_text(source_file),
        _as_text(sheet_name),
        _to_int(row_index, 0),
        _to_int(col_index, 0),
    )


def _new_slot_context():
    return {
        "reserved": set(),
        "planned_values": {},
        "allocations": {},
        "sequence_max": {},
    }


def _slot_current_text(slot_context, rec):
    key = _record_position_key(
        rec.get("source_file", ""),
        rec.get("sheet_name", ""),
        rec.get("row_index"),
        rec.get("col_index"),
    )
    return _cell_text((slot_context or {}).get("planned_values", {}).get(key, rec.get("text", "")))


def _slot_set_planned_value(slot_context, rec, value):
    if slot_context is None:
        return
    key = _record_position_key(
        rec.get("source_file", ""),
        rec.get("sheet_name", ""),
        rec.get("row_index"),
        rec.get("col_index"),
    )
    slot_context.setdefault("planned_values", {})[key] = _cell_text(value)


def _slot_scope_key(rule, event, sheet_name, row_start, row_end):
    slot_rule = _ensure_slot_judgement(rule.get("slot_judgement"))
    return (
        _as_text(event.get("source_file", "")),
        _as_text(event.get("target_file", "")),
        _as_text(sheet_name),
        _as_text(slot_rule.get("sequence_group") or rule.get("name") or "文档统一序号"),
        _to_int(row_start, 0),
        _to_int(row_end, 0),
    )


def _slot_candidate_record(source_records, event, sheet_name, row_index, col_index):
    rec = _record_at_position(
        source_records,
        event.get("source_file", ""),
        sheet_name,
        row_index,
        col_index,
    )
    return rec or _synthetic_target_record(event, sheet_name, row_index, col_index)


def _linked_trigger_options(cfg):
    values = [LINKED_RULE_ANY]
    for rule in cfg.get("rules", []) or []:
        if isinstance(rule, dict):
            name = _as_text(rule.get("name")) or _as_text(rule.get("id"))
            if name and name not in values:
                values.append(name)
    for rule in cfg.get("global_rules", []) or []:
        if isinstance(rule, dict):
            name = _as_text(rule.get("name")) or _as_text(rule.get("id"))
            label = f"全局:{name}" if name else ""
            if label and label not in values:
                values.append(label)
    return values


def _event_template_context(event, content=None):
    data = dict(content or event.get("content") or {})
    now = datetime.now()
    data.update({
        "触发规则": event.get("match_rule", ""),
        "规则类型": event.get("kind", ""),
        "源文件": event.get("source_file", ""),
        "目标文件": event.get("target_file", ""),
        "表格": event.get("sheet_name", ""),
        "Sheet": event.get("sheet_name", ""),
        "行": event.get("row_index", ""),
        "列": event.get("col_index", ""),
        "原文": event.get("old_text", ""),
        "旧值": event.get("old_text", ""),
        "新值": event.get("new_text", ""),
        "触发新值": event.get("new_text", ""),
        "内容行": event.get("content_row", ""),
        "本页变化序号": event.get("page_change_index", ""),
        "本页变化总数": event.get("page_change_total", ""),
        "圈号": _circled_number(event.get("page_change_index", 0)),
        "统一序号": event.get("slot_sequence_symbol", _circled_number(event.get("page_change_index", 0))),
        "统一序号值": event.get("slot_sequence", event.get("page_change_index", "")),
        "变更字段": event.get("mapping_field", ""),
        "变更摘要": event.get("change_summary", f"{event.get('old_text', '')} -> {event.get('new_text', '')}"),
        "执行日期": now.strftime("%Y-%m-%d"),
        "执行时间": now.strftime("%Y-%m-%d %H:%M:%S"),
        "操作者": data.get("操作者") or data.get("签名") or data.get("姓名") or "",
    })
    return data


def _assign_link_event_counts(events):
    grouped = {}
    for event in events:
        key = (event.get("source_file", ""), event.get("sheet_name", ""), event.get("match_rule", ""))
        grouped.setdefault(key, []).append(event)
    for items in grouped.values():
        total = len(items)
        for index, event in enumerate(items, start=1):
            event["page_change_index"] = index
            event["page_change_total"] = total
            event["circled_index"] = _circled_number(index)


def _record_at_position(records, source_file, sheet_name, row_index, col_index):
    row_index = _to_int(row_index, 0)
    col_index = _to_int(col_index, 0)
    for rec in records or []:
        if source_file and rec.get("source_file", "") != source_file:
            continue
        if sheet_name and rec.get("sheet_name", "") != sheet_name:
            continue
        if int(rec.get("row_index") or 0) == row_index and int(rec.get("col_index") or 0) == col_index:
            return rec
    return None


def _synthetic_target_record(event, sheet_name, row_index, col_index):
    base = event.get("rec") or {}
    meta = dict(base.get("meta") or {})
    meta.update({
        "is_merged": False,
        "is_merge_origin": True,
        "row_span": 1,
        "col_span": 1,
        "merge_origin_row": _to_int(row_index, 0),
        "merge_origin_col": _to_int(col_index, 0),
        "merged_range": "",
    })
    return {
        "source_file": event.get("source_file", ""),
        "block_type": base.get("block_type", "word_table_cell"),
        "sheet_name": sheet_name or base.get("sheet_name", ""),
        "row_index": _to_int(row_index, 0),
        "col_index": _to_int(col_index, 0),
        "cell_address": f"R{_to_int(row_index, 0)}C{_to_int(col_index, 0)}",
        "text": "",
        "is_merge_origin": True,
        "is_merged": False,
        "row_span": 1,
        "col_span": 1,
        "merge_origin_row": _to_int(row_index, 0),
        "merge_origin_col": _to_int(col_index, 0),
        "merged_range": "",
        "meta": meta,
        "meta_json": json.dumps(meta, ensure_ascii=False),
    }


def _linked_rule_matches_event(rule, event):
    trigger_tags = _normalize_event_tags(rule.get("trigger_tags"))
    if trigger_tags:
        event_tags = set(_normalize_event_tags(event.get("event_tags")))
        return bool(event_tags.intersection(trigger_tags))
    trigger = _as_text(rule.get("trigger_rule") or LINKED_RULE_ANY)
    if not trigger or trigger == LINKED_RULE_ANY:
        return True
    return trigger == _as_text(event.get("match_rule")) or trigger == _as_text(event.get("rule_name"))


def _normalize_event_tags(value):
    if isinstance(value, (list, tuple, set)):
        values = value
    else:
        values = re.split(r"[,，;；\n]+", _cell_text(value))
    result = []
    for item in values:
        tag = _as_text(item)
        if tag and tag not in result:
            result.append(tag)
    return result


def _rule_event_tags(rule, default_tag=""):
    tags = _normalize_event_tags((rule or {}).get("event_tags"))
    stable_values = [
        (rule or {}).get("id"),
        ((rule or {}).get("mapping") or {}).get("content_field"),
        default_tag,
    ]
    for value in stable_values:
        tag = _as_text(value)
        if tag and tag not in tags:
            tags.append(tag)
    return tags


def _linked_actions(rule):
    actions = [item for item in (rule.get("actions") or []) if isinstance(item, dict) and item.get("enabled", True)]
    if actions:
        return actions
    return [{
        "name": _as_text(rule.get("name")) or "联动写入",
        "enabled": True,
        "target_mode": LINK_ACTION_SHARED_SLOT,
        "row_offset": 0,
        "col_offset": 0,
        "target_match": copy.deepcopy(rule.get("target_match") or {}),
        "value_source": rule.get("value_source", LINK_VALUE_TEMPLATE),
        "fixed_value": rule.get("fixed_value", ""),
        "value_field": rule.get("value_field", ""),
        "value_template": rule.get("value_template", "{触发新值}"),
        "write_mode": rule.get("write_mode", LINK_WRITE_REPLACE),
        "append_separator": rule.get("append_separator", ""),
        "regex_pattern": rule.get("regex_pattern", ""),
        "replace_count": rule.get("replace_count", "0"),
        "case_sensitive": rule.get("case_sensitive", True),
        "empty_policy": rule.get("empty_policy", "允许"),
    }]


def _linked_action_target(action, shared_target, event, source_records):
    mode = _as_text(action.get("target_mode") or LINK_ACTION_SHARED_SLOT)
    base = event.get("rec") if mode == LINK_ACTION_TRIGGER_OFFSET else shared_target
    base = base or shared_target or event.get("rec") or {}
    row_index = _to_int(base.get("row_index"), 0) + _to_int(action.get("row_offset"), 0)
    col_index = _to_int(base.get("col_index"), 0) + _to_int(action.get("col_offset"), 0)
    sheet_name = _cfg_sheet_name(action.get("sheet_name")) or base.get("sheet_name", event.get("sheet_name", ""))
    if row_index <= 0 or col_index <= 0:
        return None, f"动作目标坐标无效：R{row_index}C{col_index}"
    rec = _record_at_position(
        source_records,
        event.get("source_file", ""),
        sheet_name,
        row_index,
        col_index,
    )
    if rec is None:
        rec = _synthetic_target_record(event, sheet_name, row_index, col_index)
    return rec, f"{mode}：{sheet_name} R{row_index}C{col_index}"


def _release_slot_allocation(slot_context, target_rec):
    if slot_context is None or target_rec is None:
        return
    key = _record_position_key(
        target_rec.get("source_file", ""),
        target_rec.get("sheet_name", ""),
        target_rec.get("row_index"),
        target_rec.get("col_index"),
    )
    slot_context.setdefault("reserved", set()).discard(key)
    slot_context.setdefault("allocations", {}).pop(key, None)


def _prepare_linked_action_writes(
    rule,
    event,
    shared_target,
    source_records,
    table_context,
    slot_context,
):
    staged = []
    event_content = event.get("content") or {}
    for action_index, action in enumerate(_linked_actions(rule), start=1):
        target_rec, target_detail = _linked_action_target(action, shared_target, event, source_records)
        if target_rec is None:
            return [], target_detail
        target_text = _slot_current_text(slot_context, target_rec)
        target_match = action.get("target_match")
        if not isinstance(target_match, dict):
            target_match = rule.get("target_match") or {}
        ok, match_detail = _match_text_with_sources(
            target_text,
            target_match,
            content=event_content,
            table_context=table_context,
            doc_record=target_rec,
            source_records=source_records,
            match_index=event.get("page_change_index") or event.get("content_row") or 1,
        )
        if not ok:
            return [], f"动作{action_index}目标格匹配未通过：{match_detail}"
        effective = dict(rule)
        effective.update(action)
        raw_value = _linked_rule_value(effective, event)
        value = _linked_apply_write_mode(effective, target_text, raw_value)
        if value == "" and _as_text(effective.get("empty_policy") or "允许") == "跳过":
            return [], f"动作{action_index}写入结果为空，按策略跳过"
        staged.append({
            "action": action,
            "action_index": action_index,
            "target_rec": target_rec,
            "target_text": target_text,
            "value": value,
            "target_detail": target_detail,
            "match_detail": match_detail,
        })
    return staged, ""


def _linked_rule_value(rule, event):
    source = _as_text(rule.get("value_source") or LINK_VALUE_FIXED) or LINK_VALUE_FIXED
    content = event.get("content") or {}
    if source == LINK_VALUE_TRIGGER_NEW:
        return _cell_text(event.get("new_text"))
    if source == LINK_VALUE_TRIGGER_OLD:
        return _cell_text(event.get("old_text"))
    if source == LINK_VALUE_CONTENT_FIELD:
        field = _as_text(rule.get("value_field"))
        return _cell_text(content.get(field)) if field else ""
    if source == LINK_VALUE_TEMPLATE:
        return _expand_template(rule.get("value_template", ""), _event_template_context(event, content))
    return _cell_text(rule.get("fixed_value", ""))


def _linked_apply_write_mode(rule, old_text, value):
    mode = _as_text(rule.get("write_mode") or LINK_WRITE_REPLACE) or LINK_WRITE_REPLACE
    old_text = _cell_text(old_text)
    value = _cell_text(value)
    separator = _cell_text(rule.get("append_separator", ""))
    if mode == LINK_WRITE_APPEND:
        return old_text + (separator if old_text and value else "") + value
    if mode == LINK_WRITE_PREPEND:
        return value + (separator if old_text and value else "") + old_text
    if mode == LINK_WRITE_REGEX:
        pattern = _cell_text(rule.get("regex_pattern", ""))
        if not pattern:
            return old_text
        repl = value
        flags = 0 if bool(rule.get("case_sensitive", True)) else re.IGNORECASE
        return re.sub(pattern, repl, old_text, count=max(0, _to_int(rule.get("replace_count"), 0)), flags=flags)
    return value


def _linked_locate_base_target(rule, event, source_records, table_context=None):
    base = event.get("rec") or {}
    mode = _as_text(rule.get("target_mode") or LINK_TARGET_TRIGGER_OFFSET) or LINK_TARGET_TRIGGER_OFFSET
    source_file = event.get("source_file", "")
    sheet_name = _cfg_sheet_name(rule.get("sheet_name")) or event.get("sheet_name", "")
    if mode == LINK_TARGET_FIXED_CELL:
        row_index = _to_int(rule.get("row_index"), 0)
        col_index = _to_int(rule.get("col_index"), 0)
        if row_index <= 0 or col_index <= 0:
            return None, "指定坐标缺少行号或列号"
    elif mode == LINK_TARGET_ANCHOR_OFFSET:
        anchor = copy.deepcopy(rule.get("anchor") or {})
        anchor["enabled"] = True
        anchor_records = [r for r in source_records if (not sheet_name or r.get("sheet_name", "") == sheet_name)]
        anchor_rec, anchor_detail = _match_anchor(
            anchor_records,
            anchor,
            content=event.get("content") or {},
            table_context=table_context,
        )
        if anchor_rec is None:
            return None, f"锚点未定位：{anchor_detail}"
        row_index = int(anchor_rec.get("row_index") or 0) + _to_int(rule.get("row_offset"), 0)
        col_index = int(anchor_rec.get("col_index") or 0) + _to_int(rule.get("col_offset"), 0)
        sheet_name = anchor_rec.get("sheet_name", sheet_name)
    else:
        row_index = int(base.get("row_index") or 0) + _to_int(rule.get("row_offset"), 0)
        col_index = int(base.get("col_index") or 0) + _to_int(rule.get("col_offset"), 0)
        sheet_name = sheet_name or base.get("sheet_name", "")
    if row_index <= 0 or col_index <= 0:
        return None, f"目标坐标无效：R{row_index}C{col_index}"
    rec = _record_at_position(source_records, source_file, sheet_name, row_index, col_index)
    if rec is None:
        rec = _synthetic_target_record(event, sheet_name, row_index, col_index)
        return rec, f"{mode}：目标记录未在读取表中出现，按空格子生成写入计划 R{row_index}C{col_index}"
    return rec, f"{mode}：定位到 {sheet_name} R{row_index}C{col_index}"


def _linked_select_area_target(rule, base_rec, event, source_records, slot_context=None):
    if not bool(rule.get("area_enabled", False)):
        return base_rec, "未启用区域槽位", {}
    slot_context = slot_context if slot_context is not None else _new_slot_context()
    source_file = event.get("source_file", "")
    sheet_name = base_rec.get("sheet_name", event.get("sheet_name", ""))
    base_row = int(base_rec.get("row_index") or 0)
    base_col = int(base_rec.get("col_index") or 0)
    row_start = base_row + _to_int(rule.get("area_row_start_offset"), 0)
    row_end = base_row + _to_int(rule.get("area_row_end_offset"), 0)
    col_start = base_col + _to_int(rule.get("area_col_start_offset"), 0)
    col_end = base_col + _to_int(rule.get("area_col_end_offset"), 0)
    if row_start > row_end:
        row_start, row_end = row_end, row_start
    if col_start > col_end:
        col_start, col_end = col_end, col_start
    row_start = max(1, row_start)
    col_start = max(1, col_start)
    scan_rows = row_end - row_start + 1
    if scan_rows > MAX_AREA_SCAN_ROWS:
        return None, (
            f"区域槽位扫描行数 {scan_rows} 超过安全上限 {MAX_AREA_SCAN_ROWS}，"
            "请缩小区域范围"
        ), {}
    write_col = base_col + _to_int(
        rule.get("area_write_col_offset"),
        _to_int(rule.get("area_col_start_offset"), 0),
    )
    if write_col <= 0:
        write_col = col_start
    slot_rule = _ensure_slot_judgement(rule.get("slot_judgement"))
    sequence_col = base_col + _to_int(
        slot_rule.get("sequence_col_offset"),
        _to_int(rule.get("marker_col_offset"), 0),
    )
    date_col = base_col + _to_int(
        slot_rule.get("date_col_offset"),
        _to_int(rule.get("marker_col_offset"), 0),
    )
    sequence_col = max(1, sequence_col)
    date_col = max(1, date_col)
    scope_key = _slot_scope_key(rule, event, sheet_name, row_start, row_end)
    candidates = []
    max_sequence = _to_int(slot_rule.get("sequence_start"), 1) - 1
    for row_index in range(row_start, row_end + 1):
        write_rec = _slot_candidate_record(source_records, event, sheet_name, row_index, write_col)
        sequence_rec = _slot_candidate_record(source_records, event, sheet_name, row_index, sequence_col)
        date_rec = _slot_candidate_record(source_records, event, sheet_name, row_index, date_col)
        slot_key = _record_position_key(source_file, sheet_name, row_index, write_col)
        sequence_value = _sequence_value(_slot_current_text(slot_context, sequence_rec), slot_rule)
        if sequence_value is not None:
            max_sequence = max(max_sequence, sequence_value)
        candidates.append({
            "row": row_index,
            "write_rec": write_rec,
            "sequence_rec": sequence_rec,
            "date_rec": date_rec,
            "sequence": sequence_value,
            "date": _parse_date_value(
                _slot_current_text(slot_context, date_rec),
                slot_rule.get("date_parser"),
            ),
            "reserved": slot_key in slot_context.setdefault("reserved", set()),
            "empty": _slot_current_text(slot_context, write_rec) == "",
            "slot_key": slot_key,
        })
    known_max = slot_context.setdefault("sequence_max", {}).get(scope_key)
    if known_max is not None:
        max_sequence = max(max_sequence, known_max)
    for candidate in candidates:
        if candidate["empty"] and not candidate["reserved"]:
            next_sequence = max_sequence + 1
            slot_context["sequence_max"][scope_key] = next_sequence
            slot_context["reserved"].add(candidate["slot_key"])
            allocation = {
                "row_index": candidate["row"],
                "sequence": next_sequence,
                "sequence_symbol": _sequence_symbol(next_sequence, slot_rule),
                "sequence_rec": candidate["sequence_rec"],
                "date_rec": candidate["date_rec"],
                "scope_key": scope_key,
                "reused": False,
            }
            slot_context.setdefault("allocations", {})[candidate["slot_key"]] = allocation
            return (
                candidate["write_rec"],
                f"区域槽位：预留第一个空行 R{candidate['row']}C{write_col}；"
                f"统一序号={allocation['sequence_symbol']}",
                allocation,
            )
    overflow_policy = _as_text(rule.get("overflow_policy") or LINK_OVERFLOW_SKIP)
    if overflow_policy not in (
        LINK_OVERFLOW_SLOT_RULE,
        LINK_OVERFLOW_MIN_MARKER_ROW,
        LINK_OVERFLOW_MIN_DATE_ROW,
    ):
        return None, f"区域 R{row_start}C{col_start}:R{row_end}C{col_end} 已满", {}
    # 固定行号模式：跳过自动扫描，直接用指定行
    if _as_text(rule.get("overflow_target_mode") or "自动") == "固定行号":
        fixed_row = _to_int(rule.get("overflow_fixed_row"), 0)
        if fixed_row <= 0:
            return None, "满区固定行号未设置或无效", {}
        rec = _slot_candidate_record(source_records, event, sheet_name, fixed_row, write_col)
        slot_key = _record_position_key(source_file, sheet_name, fixed_row, write_col)
        slot_context["reserved"].add(slot_key)
        return rec, f"区域已满：使用固定目标行 R{fixed_row}C{write_col}", {
            "row_index": fixed_row,
            "scope_key": scope_key,
            "reused": True,
        }

    if overflow_policy == LINK_OVERFLOW_MIN_MARKER_ROW:
        judgement_mode = SLOT_MODE_SEQUENCE_ONLY
    elif overflow_policy == LINK_OVERFLOW_MIN_DATE_ROW:
        judgement_mode = SLOT_MODE_DATE_ONLY
    else:
        judgement_mode = _as_text(slot_rule.get("mode") or SLOT_MODE_SEQUENCE_DATE)

    available = [item for item in candidates if not item["reserved"]]
    sequence_candidates = [item for item in available if item["sequence"] is not None]
    date_candidates = [item for item in available if item["date"] is not None]
    selected = None
    detail = ""
    if judgement_mode in (SLOT_MODE_SEQUENCE_DATE, SLOT_MODE_SEQUENCE_ONLY) and sequence_candidates:
        min_sequence = min(item["sequence"] for item in sequence_candidates)
        tied = [item for item in sequence_candidates if item["sequence"] == min_sequence]
        dated_tied = [item for item in tied if item["date"] is not None]
        selected = min(dated_tied, key=lambda item: (item["date"], item["row"])) if dated_tied else min(tied, key=lambda item: item["row"])
        detail = f"最小统一序号 {_sequence_symbol(min_sequence, slot_rule)}"
        if len(tied) > 1 and selected.get("date") is not None:
            detail += f"；同序号按最早日期 {selected['date']}"
    elif judgement_mode in (SLOT_MODE_SEQUENCE_DATE, SLOT_MODE_DATE_ONLY) and date_candidates:
        selected = min(date_candidates, key=lambda item: (item["date"], item["row"]))
        detail = f"无有效统一序号，按最早日期 {selected['date']}" if judgement_mode == SLOT_MODE_SEQUENCE_DATE else f"最早日期 {selected['date']}"

    if selected is None:
        invalid_policy = _as_text(slot_rule.get("invalid_policy") or SLOT_INVALID_SKIP)
        if invalid_policy == SLOT_INVALID_FIRST_ROW and available:
            selected = min(available, key=lambda item: item["row"])
            detail = "序号和日期均无法判定，按配置使用最上方行"
        elif invalid_policy == SLOT_INVALID_ERROR:
            return None, "区域已满，统一序号和日期均无法判定", {}
        else:
            return None, "区域已满，且未找到可用的统一序号或日期", {}

    slot_context["reserved"].add(selected["slot_key"])
    allocation = {
        "row_index": selected["row"],
        "sequence": selected.get("sequence"),
        "sequence_symbol": (
            _sequence_symbol(selected["sequence"], slot_rule)
            if selected.get("sequence") is not None
            else ""
        ),
        "sequence_rec": selected["sequence_rec"],
        "date_rec": selected["date_rec"],
        "scope_key": scope_key,
        "reused": True,
    }
    slot_context.setdefault("allocations", {})[selected["slot_key"]] = allocation
    return (
        selected["write_rec"],
        f"区域已满：替换{detail}所在行 R{selected['row']}C{write_col}",
        allocation,
    )


def _build_linked_plan_rows(linked_rules, events, by_file, params, table_context=None, slot_context=None):
    rows = []
    matched = 0
    skipped = 0
    skip_reasons = {}
    slot_context = slot_context if slot_context is not None else _new_slot_context()
    enabled_rules = [r for r in (linked_rules or []) if isinstance(r, dict) and r.get("enabled", True)]
    if not enabled_rules or not events:
        return rows, matched, skipped, skip_reasons
    for rule in enabled_rules:
        for event in events:
            if not _linked_rule_matches_event(rule, event):
                continue
            source_records = by_file.get(event.get("source_file", ""), [])
            event_content = event.get("content") or {}
            base_rec, locate_detail = _linked_locate_base_target(
                rule,
                event,
                source_records,
                table_context=table_context,
            )
            if base_rec is None:
                skipped += 1
                skip_reasons[locate_detail] = skip_reasons.get(locate_detail, 0) + 1
                continue
            target_rec, area_detail, allocation = _linked_select_area_target(
                rule,
                base_rec,
                event,
                source_records,
                slot_context=slot_context,
            )
            if target_rec is None:
                skipped += 1
                skip_reasons[area_detail] = skip_reasons.get(area_detail, 0) + 1
                continue
            if allocation:
                event["slot_sequence"] = allocation.get("sequence", "")
                event["slot_sequence_symbol"] = allocation.get("sequence_symbol", "")
            staged, action_error = _prepare_linked_action_writes(
                rule,
                event,
                target_rec,
                source_records,
                table_context=table_context,
                slot_context=slot_context,
            )
            if action_error:
                _release_slot_allocation(slot_context, target_rec)
                skipped += 1
                skip_reasons[action_error] = skip_reasons.get(action_error, 0) + 1
                continue
            for item in staged:
                action = item["action"]
                action_rec = item["target_rec"]
                _slot_set_planned_value(slot_context, action_rec, item["value"])
                matched += 1
                rows.append([
                    event.get("source_file", ""),
                    event.get("target_file", ""),
                    action_rec.get("block_type", ""),
                    action_rec.get("sheet_name", ""),
                    action_rec.get("row_index", ""),
                    action_rec.get("col_index", ""),
                    action_rec.get("cell_address", ""),
                    item["value"],
                    item["target_text"],
                    _as_text(action.get("name")) or _as_text(rule.get("name")) or "联动写入动作",
                    event.get("content_row", ""),
                    "通过",
                    f"联动:{_as_text(rule.get('name')) or '未命名'}",
                    json.dumps(rule.get("anchor", {}), ensure_ascii=False),
                    f"触发={event.get('match_rule', '')}；{item['match_detail']}",
                    f"{locate_detail}；{item['target_detail']}",
                    f"联动方案；{area_detail}；动作 {item['action_index']}/{len(staged)}；"
                    f"触发格 {event.get('sheet_name', '')} R{event.get('row_index')}C{event.get('col_index')}；"
                    f"本页变化 {event.get('page_change_index')}/{event.get('page_change_total')}",
                    DIRECT_WRITE_STRATEGY,
                    action_rec.get("meta_json", json.dumps(action_rec.get("meta", {}), ensure_ascii=False)),
                    "",
                    "",
                    "",
                ])
    return rows, matched, skipped, skip_reasons


def _apply_linked_rules_to_plan_states(
    linked_rules,
    events,
    by_file,
    params,
    states,
    order,
    table_context=None,
    slot_context=None,
):
    matched = 0
    skipped = 0
    skip_reasons = {}
    slot_context = slot_context if slot_context is not None else _new_slot_context()
    enabled_rules = [r for r in (linked_rules or []) if isinstance(r, dict) and r.get("enabled", True)]
    if not enabled_rules or not events:
        return matched, skipped, skip_reasons
    for rule in enabled_rules:
        for event in events:
            if not _linked_rule_matches_event(rule, event):
                continue
            source_records = by_file.get(event.get("source_file", ""), [])
            event_content = event.get("content") or {}
            base_rec, locate_detail = _linked_locate_base_target(
                rule,
                event,
                source_records,
                table_context=table_context,
            )
            if base_rec is None:
                skipped += 1
                skip_reasons[locate_detail] = skip_reasons.get(locate_detail, 0) + 1
                continue
            target_rec, area_detail, allocation = _linked_select_area_target(
                rule,
                base_rec,
                event,
                source_records,
                slot_context=slot_context,
            )
            if target_rec is None:
                skipped += 1
                skip_reasons[area_detail] = skip_reasons.get(area_detail, 0) + 1
                continue
            if allocation:
                event["slot_sequence"] = allocation.get("sequence", "")
                event["slot_sequence_symbol"] = allocation.get("sequence_symbol", "")
            for rec in source_records:
                key = _record_position_key(
                    rec.get("source_file", ""),
                    rec.get("sheet_name", ""),
                    rec.get("row_index"),
                    rec.get("col_index"),
                )
                state_key = _plan_object_key(event.get("target_file", ""), rec)
                existing_state = states.get(state_key)
                if existing_state is not None:
                    slot_context.setdefault("planned_values", {})[key] = existing_state.get("current_text", rec.get("text", ""))
            staged, action_error = _prepare_linked_action_writes(
                rule,
                event,
                target_rec,
                source_records,
                table_context=table_context,
                slot_context=slot_context,
            )
            if action_error:
                _release_slot_allocation(slot_context, target_rec)
                skipped += 1
                skip_reasons[action_error] = skip_reasons.get(action_error, 0) + 1
                continue
            for item in staged:
                action = item["action"]
                action_rec = item["target_rec"]
                target_state = _plan_state_for(
                    states,
                    order,
                    event.get("source_file", ""),
                    event.get("target_file", ""),
                    action_rec,
                    event_content,
                )
                before, after = _update_plan_state(
                    target_state,
                    item["value"],
                    rule_name=f"联动:{_as_text(rule.get('name')) or '未命名'}",
                    mapping_field=_as_text(action.get("name")) or _as_text(rule.get("name")) or "联动写入动作",
                    content_row=event.get("content_row", ""),
                    source_detail=f"触发={event.get('match_rule', '')}；{item['match_detail']}",
                    anchor_detail=f"{locate_detail}；{item['target_detail']}",
                    write_note=f"联动方案；{area_detail}；动作 {item['action_index']}/{len(staged)}；"
                    f"触发格 {event.get('sheet_name', '')} R{event.get('row_index')}C{event.get('col_index')}；"
                    f"本页变化 {event.get('page_change_index')}/{event.get('page_change_total')}",
                    anchor_rule=json.dumps(rule.get("anchor", {}), ensure_ascii=False),
                    write_strategy=DIRECT_WRITE_STRATEGY,
                )
                _slot_set_planned_value(slot_context, action_rec, after)
                matched += 1
                if after != before:
                    event.setdefault("linked_results", []).append({
                        "rule_name": rule.get("name", ""),
                        "action_name": action.get("name", ""),
                        "old_text": before,
                        "new_text": after,
                        "target_key": target_state.get("key", ""),
                    })
    return matched, skipped, skip_reasons


def _preview_global_match_rows(global_rules, records, features, limit=500):
    rules = [r for r in (global_rules or []) if isinstance(r, dict) and r.get("enabled", True)]
    records = list(records or [])
    by_file = {}
    for rec in records:
        by_file.setdefault(rec.get("source_file", ""), []).append(rec)
    preview_rows = []
    total_matched = 0
    for rule in rules:
        for source_file, source_records in by_file.items():
            for rec in _global_rule_records(rule, source_records):
                feature_ok, feature_detail = _feature_pass(rule.get("feature_name", ""), features, source_records, source_file, rec.get("sheet_name", ""))
                if not feature_ok:
                    continue
                cond_ok, cond_detail, condition_items = _condition_extract_items(rec.get("text", ""), rule.get("conditions", []), rule.get("condition_logic", "AND"))
                if not cond_ok:
                    continue
                total_matched += 1
                if len(preview_rows) < limit:
                    values = "；".join([_cell_text(item.get("value")) for item in condition_items[:8]]) or rec.get("text", "")
                    preview_rows.append({
                        "rule_name": _as_text(rule.get("name")),
                        "source_file": source_file,
                        "block_type": rec.get("block_type", ""),
                        "sheet_name": rec.get("sheet_name", ""),
                        "row_index": rec.get("row_index", ""),
                        "col_index": rec.get("col_index", ""),
                        "cell_address": rec.get("cell_address", ""),
                        "location": f"{rec.get('sheet_name','')} R{rec.get('row_index')}C{rec.get('col_index')}",
                        "old_text": rec.get("text", ""),
                        "new_text": values,
                        "content_row": "",
                        "detail": f"{feature_detail}；{cond_detail}；命中值={values}",
                        "status": "条件命中",
                    })
    return preview_rows, total_matched, 0


def _preview_global_replace_rows(
    global_rules,
    records,
    features,
    contents,
    aux_rows,
    params,
    limit=500,
    include_unchanged=True,
    table_context=None,
):
    rules = [r for r in (global_rules or []) if isinstance(r, dict) and r.get("enabled", True)]
    contents = list(contents or []) or [{"__content_row__": ""}]
    records = list(records or [])
    by_file = {}
    for rec in records:
        by_file.setdefault(rec.get("source_file", ""), []).append(rec)
    source_files = _source_files(records, params)
    preview_rows = []
    total_changed = 0
    total_errors = 0
    total_skipped = 0

    def append_skip(rule, source_file, content, detail, status="跳过", rec=None):
        nonlocal total_skipped
        total_skipped += 1
        if len(preview_rows) >= limit:
            return
        preview_rows.append({
            "rule_name": _as_text(rule.get("name")),
            "source_file": source_file,
            "block_type": rec.get("block_type", "") if rec else "",
            "sheet_name": rec.get("sheet_name", "") if rec else "",
            "row_index": rec.get("row_index", "") if rec else "",
            "col_index": rec.get("col_index", "") if rec else "",
            "cell_address": rec.get("cell_address", "") if rec else "",
            "location": f"{rec.get('sheet_name','')} R{rec.get('row_index')}C{rec.get('col_index')}" if rec else "",
            "old_text": rec.get("text", "") if rec else "",
            "new_text": rec.get("text", "") if rec else "",
            "content_row": content.get("__content_row__", "") if isinstance(content, dict) else "",
            "detail": detail,
            "status": status,
        })

    for rule in rules:
        for content_index, content in enumerate(contents):
            source_file, source_note = _source_file_for_content(content, source_files, content_index, len(contents), params)
            if not source_file and source_files != [""]:
                append_skip(rule, "", content, source_note)
                continue
            target_file = _target_file_for_content(content, params, source_file)
            if not target_file:
                append_skip(rule, source_file, content, f"拟定新文件字段为空：{_planned_file_field(params)}；源文件选择={source_note}")
                continue
            source_records = by_file.get(source_file, [])
            candidates = _global_rule_records(rule, source_records)
            if not candidates:
                append_skip(rule, source_file, content, f"全局规则范围内无候选记录；源文件选择={source_note}")
                continue
            condition_checked = 0
            condition_hits = 0
            for rec in candidates:
                feature_ok, feature_detail = _feature_pass(rule.get("feature_name", ""), features, source_records, source_file, rec.get("sheet_name", ""))
                if not feature_ok:
                    continue
                condition_checked += 1
                cond_ok, cond_detail, condition_items = _condition_extract_items(rec.get("text", ""), rule.get("conditions", []), rule.get("condition_logic", "AND"))
                if not cond_ok:
                    continue
                condition_hits += 1
                new_text, replace_detail, replace_error = _apply_replace_steps(rec.get("text", ""), rule, content, aux_rows, condition_items, table_context, params)
                if replace_error:
                    total_errors += 1
                    if len(preview_rows) < limit:
                        preview_rows.append({
                            "rule_name": _as_text(rule.get("name")),
                            "source_file": source_file,
                            "block_type": rec.get("block_type", ""),
                            "sheet_name": rec.get("sheet_name", ""),
                            "row_index": rec.get("row_index", ""),
                            "col_index": rec.get("col_index", ""),
                            "cell_address": rec.get("cell_address", ""),
                            "location": f"{rec.get('sheet_name','')} R{rec.get('row_index')}C{rec.get('col_index')}",
                            "old_text": rec.get("text", ""),
                            "new_text": rec.get("text", ""),
                            "content_row": content.get("__content_row__", ""),
                            "detail": replace_error,
                            "status": "错误",
                        })
                    continue
                if new_text == rec.get("text", ""):
                    if include_unchanged and len(preview_rows) < limit:
                        preview_rows.append({
                            "rule_name": _as_text(rule.get("name")),
                            "source_file": source_file,
                            "block_type": rec.get("block_type", ""),
                            "sheet_name": rec.get("sheet_name", ""),
                            "row_index": rec.get("row_index", ""),
                            "col_index": rec.get("col_index", ""),
                            "cell_address": rec.get("cell_address", ""),
                            "location": f"{rec.get('sheet_name','')} R{rec.get('row_index')}C{rec.get('col_index')}",
                            "old_text": rec.get("text", ""),
                            "new_text": new_text,
                            "content_row": content.get("__content_row__", ""),
                            "detail": f"{feature_detail}；{cond_detail}；{replace_detail}；目标文件={target_file}；源文件选择={source_note}",
                            "status": "命中未变化",
                        })
                    continue
                total_changed += 1
                if len(preview_rows) < limit:
                    preview_rows.append({
                        "rule_name": _as_text(rule.get("name")),
                        "source_file": source_file,
                        "target_file": target_file,
                        "block_type": rec.get("block_type", ""),
                        "sheet_name": rec.get("sheet_name", ""),
                        "row_index": rec.get("row_index", ""),
                        "col_index": rec.get("col_index", ""),
                        "cell_address": rec.get("cell_address", ""),
                        "location": f"{rec.get('sheet_name','')} R{rec.get('row_index')}C{rec.get('col_index')}",
                        "old_text": rec.get("text", ""),
                        "new_text": new_text,
                        "content_row": content.get("__content_row__", ""),
                        "content": content,
                        "source_note": source_note,
                        "detail": f"{feature_detail}；{cond_detail}；{replace_detail}；目标文件={target_file}；源文件选择={source_note}",
                        "status": "替换",
                    })
            if condition_checked == 0:
                append_skip(rule, source_file, content, f"候选记录 {len(candidates)} 条，但表特征未通过；源文件选择={source_note}")
            elif condition_hits == 0:
                append_skip(rule, source_file, content, f"候选记录 {len(candidates)} 条，匹配条件未命中；源文件选择={source_note}")
    return preview_rows, total_changed, total_errors + total_skipped


def validate_params(params, input_data, context):
    doc_alias = _as_text((params or {}).get("doc_table_alias", "当前表")) or "当前表"
    content_alias = _as_text((params or {}).get("content_table_alias", "新内容表")) or "新内容表"
    tables = _all_tables(input_data, context)
    if doc_alias not in tables:
        return False, f"未找到文档读取表别名：{doc_alias}"
    if content_alias not in tables:
        return False, f"未找到新内容表别名：{content_alias}"
    doc_headers = {_as_text(item) for item in (tables.get(doc_alias, {}).get("headers") or [])}
    if not doc_headers.intersection({"text", "内容"}):
        return False, "文档读取表缺少文本字段：text/内容"
    content_headers = [_as_text(item) for item in (tables.get(content_alias, {}).get("headers") or []) if _as_text(item)]
    if not content_headers:
        return False, "新内容表没有可用字段"
    return True, ""


def run(input_data, params, context):
    params = dict(params or {})
    valid, message = validate_params(params, input_data, context)
    if not valid:
        return {
            "ok": False,
            "message": message,
            "output": {"type": "table", "headers": list(OUTPUT_HEADERS), "rows": [], "meta": {"plugin": PLUGIN_INFO["id"]}},
            "logs": [{"level": "ERROR", "message": message}],
            "summary": {"output_rows": 0, "matched": 0, "skipped": 0},
        }
    all_tables = _all_tables(input_data, context)
    doc_table, doc_alias = _pick_table(input_data, context, params.get("doc_table_alias", "当前表"), "当前表")
    content_table, content_alias = _pick_table(input_data, context, params.get("content_table_alias", "新内容表"), "")
    aux_table, aux_alias = _pick_optional_table(input_data, context, params.get("replace_aux_table_alias", "替换辅助表"))
    config_name, cfg, settings = _get_config(params, context)
    rules = [r for r in cfg.get("rules", []) if isinstance(r, dict) and r.get("enabled", True)]
    features = [f for f in cfg.get("features", []) if isinstance(f, dict)]
    global_rules = [r for r in cfg.get("global_rules", []) if isinstance(r, dict) and r.get("enabled", True)]
    linked_rules = [r for r in cfg.get("linked_rules", []) if isinstance(r, dict) and r.get("enabled", True)]
    debug_output = bool(params.get("debug_output", False))
    empty_policy = _as_text(params.get("empty_policy", "跳过")) or "跳过"
    content_fields, contents = _content_rows(content_table)
    aux_fields, aux_rows = _content_rows(aux_table)
    table_context = _table_row_context(all_tables, content_alias, aux_alias)
    records = _doc_records(doc_table, params)
    by_file = {}
    for rec in records:
        by_file.setdefault(rec.get("source_file", ""), []).append(rec)
    source_files = _source_files(records, params)

    out_headers = list(OUTPUT_HEADERS)
    out_rows = []
    logs = []
    skipped = 0
    matched = 0
    skip_reasons = {}
    trigger_events = []

    if not rules and not global_rules and not linked_rules:
        return {
            "ok": True,
            "message": "未配置映射规则、全局搜索替换规则或联动写入规则，未生成写入计划",
            "output": {"type": "table", "headers": out_headers, "rows": [], "meta": {"plugin": PLUGIN_INFO["id"]}},
            "logs": [{"level": "WARNING", "message": "请先打开插件自带设置窗口配置单元格映射规则、全局搜索替换规则或联动写入规则"}],
            "summary": {"rules": 0, "global_rules": 0, "linked_rules": 0, "output_rows": 0, "doc_table": doc_alias, "content_table": content_alias},
        }

    total = max(1, len(contents) * max(1, len(rules) + len(global_rules)))
    current = 0
    progress = (context or {}).get("report_progress")

    def add_debug_row(note, rule, content, source_file="", rec=None, status="跳过"):
        note_key = _as_text(note) or "未说明跳过原因"
        skip_reasons[note_key] = skip_reasons.get(note_key, 0) + 1
        if not debug_output:
            return
        out_rows.append([
            source_file,
            _target_file_for_content(content, params, source_file),
            rec.get("block_type", "") if rec else "",
            rec.get("sheet_name", "") if rec else "",
            rec.get("row_index", "") if rec else "",
            rec.get("col_index", "") if rec else "",
            rec.get("cell_address", "") if rec else "",
            "",
            rec.get("text", "") if rec else "",
            (rule.get("mapping") or {}).get("content_field") or (rule.get("mapping") or {}).get("field", ""),
            content.get("__content_row__", ""),
            status,
            rule.get("name", ""),
            json.dumps(rule.get("anchor", {}), ensure_ascii=False),
            "",
            "",
            note,
            "",
            rec.get("meta_json", json.dumps(rec.get("meta", {}), ensure_ascii=False)) if rec else "",
            "",
            "",
            "",
        ])

    plan_states = {}
    plan_order = []
    special_rows = []
    for content_index, content in enumerate(contents):
        source_file, source_note = _source_file_for_content(content, source_files, content_index, len(contents), params)
        if not source_file and source_files != [""]:
            skipped += len(rules) + len(global_rules)
            for rule in rules + global_rules:
                add_debug_row(source_note, rule, content)
            continue
        target_file = _target_file_for_content(content, params, source_file)
        if not target_file:
            skipped += 1
            for rule in rules:
                add_debug_row("拟定新文件字段为空", rule, content, source_file)
            for global_rule in global_rules:
                add_debug_row("拟定新文件字段为空", global_rule, content, source_file)
            continue
        source_records = by_file.get(source_file, [])
        for rule in rules:
            current += 1
            if callable(progress) and (current == 1 or current % 50 == 0 or current == total):
                progress(current, total, f"生成写入计划 {current}/{total}")
            locator = rule.get("source_locator", {}) or {}
            feature_ok, feature_detail = _feature_pass(rule.get("feature_name", ""), features, source_records, source_file, _as_text(locator.get("sheet_name")))
            if not feature_ok:
                skipped += 1
                add_debug_row(feature_detail, rule, content, source_file)
                continue
            rec, anchor_detail = _locate_target_record(rule, source_records, source_file, content=content, table_context=table_context)
            if rec is None:
                skipped += 1
                add_debug_row(anchor_detail, rule, content, source_file)
                continue
            ok, match_detail = _match_text_with_sources(
                rec.get("text", ""),
                rule.get("source_match", {}),
                content=content,
                table_context=table_context,
                doc_record=rec,
                source_records=source_records,
            )
            if not ok:
                skipped += 1
                add_debug_row("输入源内容匹配未通过", rule, content, source_file, rec)
                continue
            mapping = rule.get("mapping", {}) or {}
            field = _as_text(mapping.get("content_field") or mapping.get("field"))
            if not field:
                skipped += 1
                add_debug_row("未选择映射字段", rule, content, source_file, rec)
                continue
            value = _cell_text(content.get(field))
            if value == "" and empty_policy == "跳过":
                skipped += 1
                add_debug_row("映射字段为空，按策略跳过", rule, content, source_file, rec)
                continue
            if value == "" and empty_policy == "报错":
                raise ValueError(f"映射字段为空：{field}，新内容行 {content.get('__content_row__')}")
            matched += 1
            state = _plan_state_for(plan_states, plan_order, source_file, target_file, rec, content)
            before_text, after_text = _update_plan_state(
                state,
                value,
                rule_name=rule.get("name", ""),
                mapping_field=field,
                content_row=content.get("__content_row__", ""),
                source_detail=f"{feature_detail}；{match_detail}",
                anchor_detail=anchor_detail,
                write_note=f"普通映射；源文件选择={source_note}",
                anchor_rule=json.dumps(rule.get("anchor", {}), ensure_ascii=False),
            )
            if after_text != before_text:
                trigger_events.append({
                    "kind": "普通映射",
                    "rule_name": rule.get("name", ""),
                    "match_rule": rule.get("name", ""),
                    "event_tags": _rule_event_tags(rule, rule.get("name", "")),
                    "source_file": source_file,
                    "target_file": target_file,
                    "rec": rec,
                    "sheet_name": rec.get("sheet_name", ""),
                    "row_index": rec.get("row_index", ""),
                    "col_index": rec.get("col_index", ""),
                    "old_text": before_text,
                    "new_text": after_text,
                    "mapping_field": field,
                    "content": content,
                    "content_row": content.get("__content_row__", ""),
                    "source_note": source_note,
                })

        for global_rule in global_rules:
            current += 1
            if callable(progress) and (current == 1 or current % 50 == 0 or current == total):
                progress(min(current, total), total, f"生成全局替换计划 {min(current, total)}/{total}")
            candidates = _global_rule_records(global_rule, source_records)
            if not candidates:
                skipped += 1
                add_debug_row("全局规则范围内无候选记录", global_rule, content, source_file, status="跳过")
                continue
            rule_hit = 0
            for rec in candidates:
                feature_ok, feature_detail = _feature_pass(global_rule.get("feature_name", ""), features, source_records, source_file, rec.get("sheet_name", ""))
                if not feature_ok:
                    continue
                state = _plan_state_for(plan_states, plan_order, source_file, target_file, rec, content)
                current_rec = _plan_state_record(state)
                current_text = current_rec.get("text", "")
                cond_ok, cond_detail, condition_items = _condition_extract_items(current_text, global_rule.get("conditions", []), global_rule.get("condition_logic", "AND"))
                if not cond_ok:
                    continue
                value, replace_detail, replace_error = _apply_replace_steps(current_text, global_rule, content, aux_rows, condition_items, table_context, params)
                if replace_error:
                    skipped += 1
                    add_debug_row(replace_error, global_rule, content, source_file, rec)
                    continue
                if value == current_text:
                    skipped += 1
                    add_debug_row("全局规则命中但替换后内容无变化", global_rule, content, source_file, rec)
                    continue
                if value == "" and empty_policy == "跳过":
                    skipped += 1
                    add_debug_row("全局替换结果为空，按策略跳过", global_rule, content, source_file, rec)
                    continue
                if value == "" and empty_policy == "报错":
                    raise ValueError(f"全局替换结果为空：{global_rule.get('name', '')}，新内容行 {content.get('__content_row__')}")
                rule_hit += 1
                matched += 1
                special_scope = _as_text(global_rule.get("scope")) == GLOBAL_SCOPE_SPECIAL_OBJECTS
                state_was_touched = bool(state.get("touched"))
                if special_scope and not state_was_touched:
                    before_text = current_text
                    after_text = _cell_text(value)
                    state["current_text"] = after_text
                else:
                    before_text, after_text = _update_plan_state(
                        state,
                        value,
                        rule_name=f"全局:{global_rule.get('name', '')}",
                        mapping_field=_global_rule_fields(global_rule),
                        content_row=content.get("__content_row__", ""),
                        source_detail=f"{feature_detail}；{cond_detail}",
                        anchor_detail="",
                        write_note=f"全局搜索替换；{replace_detail}；源文件选择={source_note}",
                    )
                if special_scope:
                    special_rows.append([
                        source_file,
                        target_file,
                        "word_global_replace",
                        "",
                        "",
                        "",
                        "",
                        after_text,
                        before_text,
                        _global_rule_fields(global_rule),
                        content.get("__content_row__", ""),
                        "通过",
                        f"全局:{global_rule.get('name', '')}",
                        "",
                        f"{feature_detail}；{cond_detail}",
                        "",
                        f"全局搜索替换；{replace_detail}；源文件选择={source_note}",
                        "按old_text查找替换",
                        rec.get("meta_json", json.dumps(rec.get("meta", {}), ensure_ascii=False)),
                        "替换全部",
                        before_text,
                        after_text,
                    ])
                trigger_events.append({
                    "kind": "全局替换",
                    "rule_name": global_rule.get("name", ""),
                    "match_rule": f"全局:{global_rule.get('name', '')}",
                    "event_tags": _rule_event_tags(global_rule, global_rule.get("name", "")),
                    "source_file": source_file,
                    "target_file": target_file,
                    "rec": rec,
                    "sheet_name": rec.get("sheet_name", ""),
                    "row_index": rec.get("row_index", ""),
                    "col_index": rec.get("col_index", ""),
                    "old_text": before_text,
                    "new_text": after_text,
                    "mapping_field": _global_rule_fields(global_rule),
                    "content": content,
                    "content_row": content.get("__content_row__", ""),
                    "source_note": source_note,
                })
            if rule_hit == 0:
                skipped += 1
                add_debug_row("全局规则未命中任何可替换记录", global_rule, content, source_file, status="跳过")

    _assign_link_event_counts(trigger_events)
    linked_matched, linked_skipped, linked_skip_reasons = _apply_linked_rules_to_plan_states(
        linked_rules,
        trigger_events,
        by_file,
        params,
        plan_states,
        plan_order,
        table_context=table_context,
    )
    matched += linked_matched
    skipped += linked_skipped
    for reason, count in linked_skip_reasons.items():
        skip_reasons[reason] = skip_reasons.get(reason, 0) + count

    for key in plan_order:
        state = plan_states.get(key)
        if state and state.get("touched"):
            out_rows.append(_plan_state_to_output_row(state))
    out_rows.extend(_sort_global_replace_output_rows(special_rows))

    logs.append({"level": "INFO", "message": f"配置={config_name}，单元格规则 {len(rules)} 条，全局规则 {len(global_rules)} 条，联动规则 {len(linked_rules)} 条，生成 {matched} 条，跳过 {skipped} 条"})
    if skipped and skip_reasons:
        reason_text = "；".join([f"{reason}×{count}" for reason, count in sorted(skip_reasons.items(), key=lambda item: item[1], reverse=True)[:8]])
        level = "WARNING" if matched == 0 else "INFO"
        logs.append({"level": level, "message": f"写入计划跳过原因：{reason_text}"})
    return {
        "ok": True,
        "message": f"写入计划生成完成：{matched} 条",
        "output": {"type": "table", "headers": out_headers, "rows": out_rows, "meta": {"plugin": PLUGIN_INFO["id"]}},
        "logs": logs,
        "summary": {
            "doc_table": doc_alias,
            "content_table": content_alias,
            "replace_aux_table": aux_alias,
            "rules": len(rules),
            "features": len(features),
            "global_rules": len(global_rules),
            "linked_rules": len(linked_rules),
            "content_rows": len(contents),
            "replace_aux_rows": len(aux_rows),
            "source_files": len(source_files),
            "output_rows": len(out_rows),
            "matched": matched,
            "skipped": skipped,
            "trigger_events": len(trigger_events),
            "debug_output": debug_output,
        },
    }


def _group_doc_grid(records):
    groups = {}
    for rec in records:
        key = rec.get("sheet_name") or "table_1"
        groups.setdefault(key, {})[(int(rec.get("row_index") or 0), int(rec.get("col_index") or 0))] = rec
    return groups


def _default_rule_for_cell(rec):
    return {
        "id": f"{rec.get('sheet_name','')}:R{rec.get('row_index')}C{rec.get('col_index')}",
        "name": f"{rec.get('sheet_name','')}:R{rec.get('row_index')}C{rec.get('col_index')}",
        "enabled": True,
        "feature_name": "",
        "source_locator": {
            "source_file": rec.get("source_file", ""),
            "block_type": rec.get("block_type", ""),
            "sheet_name": rec.get("sheet_name", ""),
            "row_index": rec.get("row_index", 0),
            "col_index": rec.get("col_index", 0),
            "cell_address": rec.get("cell_address", ""),
        },
        "source_match": {"enabled": False, "mode": "包含", "value": rec.get("text", "")},
        "anchor": {"enabled": False, "axis": "列", "index": 1, "match_mode": "等于", "value": "", "row_offset": 0, "col_offset": 0},
        "mapping": {"content_field": "", "empty_policy": "跟随节点设置"},
    }


def _default_linked_rule(index=1):
    return {
        "name": f"linked_{index}",
        "enabled": True,
        "trigger_rule": LINKED_RULE_ANY,
        "trigger_tags": [],
        "target_mode": LINK_TARGET_TRIGGER_OFFSET,
        "sheet_name": "",
        "row_offset": 0,
        "col_offset": 0,
        "row_index": "",
        "col_index": "",
        "target_match": {"enabled": False, "mode": "包含", "value": ""},
        "anchor": {"enabled": False, "axis": "列", "index": 1, "match_mode": "等于", "value": ""},
        "value_source": LINK_VALUE_TEMPLATE,
        "fixed_value": "",
        "value_field": "",
        "value_template": "{触发新值}",
        "write_mode": LINK_WRITE_REPLACE,
        "append_separator": "",
        "regex_pattern": "",
        "replace_count": "0",
        "case_sensitive": True,
        "empty_policy": "允许",
        "area_enabled": False,
        "area_row_start_offset": 0,
        "area_row_end_offset": 0,
        "area_col_start_offset": 0,
        "area_col_end_offset": 0,
        "area_write_col_offset": 0,
        "marker_col_offset": 0,
        "overflow_policy": LINK_OVERFLOW_SKIP,
        "overflow_target_mode": "自动",
        "overflow_fixed_row": "",
        "slot_judgement": _default_slot_judgement(),
        "actions": [],
    }


def _linked_scheme_presets():
    change_log = _default_linked_rule()
    change_log_slot_judgement = _default_slot_judgement()
    change_log_slot_judgement.update({
        "sequence_col_offset": 0,
        "date_col_offset": 4,
    })
    change_log.update({
        "name": "设计文件变更记录",
        "trigger_tags": ["需要生成变更记录"],
        "target_mode": LINK_TARGET_ANCHOR_OFFSET,
        "anchor": {
            "enabled": True,
            "axis": "列",
            "index": 1,
            "match_mode": "等于",
            "value": "更改标记",
        },
        "area_enabled": True,
        "area_row_start_offset": 1,
        "area_row_end_offset": 10,
        "area_col_start_offset": 1,
        "area_col_end_offset": 4,
        "area_write_col_offset": 2,
        "overflow_policy": LINK_OVERFLOW_SLOT_RULE,
        "slot_judgement": change_log_slot_judgement,
        "actions": [
            {
                "name": "统一序号",
                "enabled": True,
                "target_mode": LINK_ACTION_SHARED_SLOT,
                "row_offset": 0,
                "col_offset": -2,
                "value_source": LINK_VALUE_TEMPLATE,
                "value_template": "{统一序号}",
                "write_mode": LINK_WRITE_REPLACE,
                "empty_policy": "允许",
            },
            {
                "name": "变更信息",
                "enabled": True,
                "target_mode": LINK_ACTION_SHARED_SLOT,
                "row_offset": 0,
                "col_offset": 0,
                "value_source": LINK_VALUE_TEMPLATE,
                "value_template": "{变更字段}：{旧值} → {新值}",
                "write_mode": LINK_WRITE_REPLACE,
                "empty_policy": "允许",
            },
            {
                "name": "署名",
                "enabled": True,
                "target_mode": LINK_ACTION_SHARED_SLOT,
                "row_offset": 0,
                "col_offset": 1,
                "value_source": LINK_VALUE_TEMPLATE,
                "value_template": "{操作者}",
                "write_mode": LINK_WRITE_REPLACE,
                "empty_policy": "跳过",
            },
            {
                "name": "日期",
                "enabled": True,
                "target_mode": LINK_ACTION_SHARED_SLOT,
                "row_offset": 0,
                "col_offset": 2,
                "value_source": LINK_VALUE_TEMPLATE,
                "value_template": "{执行日期}",
                "write_mode": LINK_WRITE_REPLACE,
                "empty_policy": "允许",
            },
        ],
    })
    signature = _default_linked_rule()
    signature.update({
        "name": "指定区域署名日期",
        "trigger_tags": ["需要署名"],
        "value_source": LINK_VALUE_TEMPLATE,
        "value_template": "{操作者} {执行日期}",
    })
    return {
        "设计文件变更记录（序号优先）": change_log,
        "指定区域署名日期": signature,
    }


def open_config_window(parent, current_params, context):
    if tk is None:
        raise RuntimeError("当前环境不支持 Tkinter，无法打开可视化映射窗口")

    params = dict(current_params or {})
    config_name, cfg, settings = _get_config(params, context)
    tables = (context or {}).get("input_tables") or {}
    table_aliases = list(tables.keys())
    if not table_aliases:
        table_aliases = ["当前表"]

    win = tk.Toplevel(parent)
    try:
        win.withdraw()
    except Exception:
        pass
    win.title("可视化映射写入计划设置")
    try:
        win.resizable(True, True)
        win.minsize(CONFIG_WINDOW_MIN_WIDTH, CONFIG_WINDOW_MIN_HEIGHT)
    except Exception:
        pass

    top = ttk.Frame(win, padding=8)
    top.pack(fill=tk.X)
    selector_row = ttk.Frame(top)
    selector_row.pack(fill=tk.X)
    action_row = ttk.Frame(top)
    action_row.pack(fill=tk.X, pady=(6, 0))
    ttk.Label(
        top,
        text="执行流程：普通映射规则顺序 -> 全局替换规则顺序 -> 联动写入规则顺序；后续阶段处理前一阶段的计划内当前值。",
        foreground="gray",
    ).pack(fill=tk.X, pady=(4, 0))
    ttk.Label(selector_row, text="文档读取表：").pack(side=tk.LEFT)
    doc_alias_var = tk.StringVar(value=params.get("doc_table_alias", "当前表"))
    doc_alias_combo = ttk.Combobox(selector_row, textvariable=doc_alias_var, values=table_aliases, width=18, state="readonly")
    doc_alias_combo.pack(side=tk.LEFT, padx=4)
    ttk.Label(selector_row, text="新内容表：").pack(side=tk.LEFT, padx=(12, 0))
    content_alias_var = tk.StringVar(value=params.get("content_table_alias", "新内容表"))
    content_alias_combo = ttk.Combobox(selector_row, textvariable=content_alias_var, values=table_aliases, width=18, state="readonly")
    content_alias_combo.pack(side=tk.LEFT, padx=4)
    ttk.Label(selector_row, text="替换辅助表：").pack(side=tk.LEFT, padx=(12, 0))
    aux_alias_var = tk.StringVar(value=params.get("replace_aux_table_alias", "替换辅助表"))
    aux_alias_combo = ttk.Combobox(selector_row, textvariable=aux_alias_var, values=table_aliases, width=18, state="readonly")
    aux_alias_combo.pack(side=tk.LEFT, padx=4)
    ttk.Label(selector_row, text="配置名：").pack(side=tk.LEFT, padx=(12, 0))
    config_name_var = tk.StringVar(value=params.get("config_name", config_name))
    config_name_combo = ttk.Combobox(selector_row, textvariable=config_name_var, values=sorted((settings.get("configs") or {}).keys()), width=18, state="normal")
    config_name_combo.pack(side=tk.LEFT, padx=4)
    ttk.Button(action_row, text="管理配置", command=lambda: manage_configs()).pack(side=tk.LEFT, padx=4)
    ttk.Button(action_row, text="管理表特征", command=lambda: manage_features()).pack(side=tk.LEFT, padx=4)
    ttk.Button(action_row, text="全局搜索替换规则窗口", command=lambda: manage_global_rules()).pack(side=tk.LEFT, padx=4)
    ttk.Button(action_row, text="联动写入规则", command=lambda: manage_linked_rules()).pack(side=tk.LEFT, padx=4)
    ttk.Button(action_row, text="全局替换预览", command=lambda: show_global_replace_preview()).pack(side=tk.LEFT, padx=4)

    status_var = tk.StringVar(value=_as_text((context or {}).get("plugin_config_data_note", "")))
    ttk.Label(action_row, textvariable=status_var, foreground="gray").pack(side=tk.LEFT, padx=10)

    top_fields = ttk.Frame(win, padding=(8, 0, 8, 4))
    top_fields.pack(fill=tk.X)
    source_file_field_var = tk.StringVar(value=params.get("source_file_field", "source_file"))
    planned_file_field_var = tk.StringVar(value=params.get("planned_file_field") or params.get("target_file_field", "target_file"))
    ttk.Label(top_fields, text="源文件字段：").pack(side=tk.LEFT)
    source_file_field_combo = ttk.Combobox(top_fields, textvariable=source_file_field_var, values=[], width=24, state="normal")
    source_file_field_combo.pack(side=tk.LEFT, padx=4)
    ttk.Label(top_fields, text="拟定新文件字段：").pack(side=tk.LEFT, padx=(12, 0))
    planned_file_field_combo = ttk.Combobox(top_fields, textvariable=planned_file_field_var, values=[], width=24, state="normal")
    planned_file_field_combo.pack(side=tk.LEFT, padx=4)

    main = ttk.PanedWindow(win, orient=tk.HORIZONTAL)
    main.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
    left = ttk.Frame(main, padding=6)
    center = ttk.Frame(main, padding=6)
    right = ttk.Frame(main, padding=6)
    main.add(left, weight=1)
    main.add(center, weight=5)
    main.add(right, weight=2)

    ttk.Label(left, text="表格 / Sheet").pack(anchor=tk.W)
    group_frame, group_lb = _make_scrollable_listbox(left, height=18, exportselection=False)
    group_frame.pack(fill=tk.BOTH, expand=True)

    ttk.Label(right, text="当前格信息").pack(anchor=tk.W)
    info_text = tk.Text(right, height=14, width=36)
    info_text.pack(fill=tk.X, pady=4)
    ttk.Label(right, text="已配置规则").pack(anchor=tk.W, pady=(8, 0))
    rule_frame, rule_lb = _make_scrollable_listbox(right, height=15, exportselection=False)
    rule_frame.pack(fill=tk.BOTH, expand=True)
    rule_button_row = ttk.Frame(right)
    rule_button_row.pack(fill=tk.X, pady=(6, 0))
    ttk.Button(rule_button_row, text="删除选中", command=lambda: delete_selected_rule()).pack(side=tk.LEFT, padx=2)
    ttk.Button(rule_button_row, text="启用/停用", command=lambda: toggle_selected_rule()).pack(side=tk.LEFT, padx=2)
    ttk.Button(rule_button_row, text="上移", command=lambda: move_selected_rule(-1)).pack(side=tk.LEFT, padx=2)
    ttk.Button(rule_button_row, text="下移", command=lambda: move_selected_rule(1)).pack(side=tk.LEFT, padx=2)
    ttk.Button(rule_button_row, text="编辑规则", command=lambda: edit_selected_rule()).pack(side=tk.LEFT, padx=2)

    grid_col_w = 180
    grid_row_h = 82
    grid_head_w = 48
    grid_head_h = 30
    corner_canvas = tk.Canvas(center, width=grid_head_w, height=grid_head_h, background="#e8edf3", highlightthickness=0)
    col_header_canvas = tk.Canvas(center, height=grid_head_h, background="#e8edf3", highlightthickness=0)
    row_header_canvas = tk.Canvas(center, width=grid_head_w, background="#e8edf3", highlightthickness=0)
    canvas = tk.Canvas(center, background="#f6f6f6", highlightthickness=0)

    def _sync_xview(*args):
        canvas.xview(*args)
        col_header_canvas.xview(*args)

    def _sync_yview(*args):
        canvas.yview(*args)
        row_header_canvas.yview(*args)

    def _on_body_xview(first, last):
        xscroll.set(first, last)
        col_header_canvas.xview_moveto(first)

    def _on_body_yview(first, last):
        yscroll.set(first, last)
        row_header_canvas.yview_moveto(first)

    yscroll = ttk.Scrollbar(center, orient=tk.VERTICAL, command=_sync_yview)
    xscroll = ttk.Scrollbar(center, orient=tk.HORIZONTAL, command=_sync_xview)
    canvas.configure(yscrollcommand=_on_body_yview, xscrollcommand=_on_body_xview)
    corner_canvas.grid(row=0, column=0, sticky="nsew")
    col_header_canvas.grid(row=0, column=1, sticky="ew")
    row_header_canvas.grid(row=1, column=0, sticky="ns")
    canvas.grid(row=1, column=1, sticky="nsew")
    yscroll.grid(row=1, column=2, sticky="ns")
    xscroll.grid(row=2, column=1, sticky="ew")
    center.rowconfigure(1, weight=1)
    center.columnconfigure(1, weight=1)

    state = {"records": [], "groups": {}, "selected_group": "", "selected_rec": None, "cell_regions": [], "preview_changes": {}, "focused_cell_key": ""}

    def config_names():
        return sorted((_load_settings(context).get("configs") or {"default": {}}).keys()) or ["default"]

    def refresh_config_combo():
        config_name_combo.configure(values=config_names())

    def current_feature_names(include_empty=True):
        names = []
        for feature in cfg.get("features", []) or []:
            if not isinstance(feature, dict):
                continue
            name = _as_text(feature.get("name"))
            if name and name not in names:
                names.append(name)
        names = sorted(names)
        return ([FEATURE_ANY_LABEL] if include_empty else []) + names

    def current_sheet_names(include_all=True):
        names = []
        for rec in state.get("records", []) or []:
            name = _as_text(rec.get("sheet_name"))
            if name and name not in names:
                names.append(name)
        names = sorted(names)
        return ([SHEET_ALL_LABEL] if include_all else []) + names

    def load_config_by_name(name):
        nonlocal config_name, cfg, settings
        name = _as_text(name) or "default"
        settings = _load_settings(context)
        settings.setdefault("configs", {}).setdefault(name, _empty_config())
        config_name = name
        cfg = copy.deepcopy(settings["configs"].get(name, _empty_config()))
        _ensure_config(cfg)
        params["config_name"] = name
        state["preview_changes"] = {}
        state["focused_cell_key"] = ""
        if config_name_var.get() != name:
            config_name_var.set(name)
        refresh_rules()
        if state.get("selected_group"):
            render_group(state["selected_group"])
        status_var.set(f"已切换配置：{name}；规则 {len(cfg.get('rules', []))} 条")

    def manage_configs():
        nonlocal config_name, cfg, settings
        dlg = _make_floating_child(win, "管理映射配置")
        body = ttk.Frame(dlg, padding=10)
        body.pack(fill=tk.BOTH, expand=True)
        lb_frame, lb = _make_scrollable_listbox(body, height=12, width=36, exportselection=False)
        lb_frame.grid(row=0, column=0, rowspan=6, sticky="nsew", padx=4, pady=4)
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)

        def reload_list(select_name=None):
            refresh_config_combo()
            names = config_names()
            lb.delete(0, tk.END)
            for name in names:
                lb.insert(tk.END, name)
            target = select_name or config_name_var.get()
            if target in names:
                lb.selection_clear(0, tk.END)
                lb.selection_set(names.index(target))
                lb.see(names.index(target))

        def selected_name():
            sel = lb.curselection()
            return lb.get(sel[0]) if sel else ""

        def ask_name(title, initial=""):
            if simpledialog is None:
                return ""
            return _as_text(simpledialog.askstring(title, "配置名称：", initialvalue=initial, parent=dlg))

        def add_config():
            name = ask_name("新建配置", "new_config")
            if not name:
                return
            settings = _load_settings(context)
            configs = settings.setdefault("configs", {})
            if name in configs:
                messagebox.showwarning("提示", f"配置已存在：{name}", parent=dlg)
                return
            configs[name] = _empty_config()
            _save_settings(context, settings)
            reload_list(name)

        def copy_config():
            old = selected_name() or config_name_var.get()
            if not old:
                return
            name = ask_name("复制配置", f"{old}_copy")
            if not name:
                return
            settings = _load_settings(context)
            configs = settings.setdefault("configs", {})
            if name in configs:
                messagebox.showwarning("提示", f"配置已存在：{name}", parent=dlg)
                return
            configs[name] = copy.deepcopy(configs.get(old, cfg))
            _save_settings(context, settings)
            reload_list(name)

        def rename_config():
            old = selected_name()
            if not old:
                return
            name = ask_name("重命名配置", old)
            if not name or name == old:
                return
            settings = _load_settings(context)
            configs = settings.setdefault("configs", {})
            if name in configs:
                messagebox.showwarning("提示", f"配置已存在：{name}", parent=dlg)
                return
            configs[name] = configs.pop(old, _empty_config())
            _save_settings(context, settings)
            if config_name_var.get() == old:
                load_config_by_name(name)
            reload_list(name)

        def delete_config():
            name = selected_name()
            if not name:
                return
            settings = _load_settings(context)
            configs = settings.setdefault("configs", {})
            if len(configs) <= 1:
                messagebox.showwarning("提示", "至少保留一个配置。", parent=dlg)
                return
            if not messagebox.askyesno("确认删除", f"删除配置：{name}？", parent=dlg):
                return
            configs.pop(name, None)
            _save_settings(context, settings)
            names = sorted(configs.keys()) or ["default"]
            if config_name_var.get() == name:
                load_config_by_name(names[0])
            reload_list(config_name_var.get())

        ttk.Button(body, text="新建", command=add_config).grid(row=0, column=1, sticky="ew", padx=4, pady=2)
        ttk.Button(body, text="复制当前", command=copy_config).grid(row=1, column=1, sticky="ew", padx=4, pady=2)
        ttk.Button(body, text="重命名", command=rename_config).grid(row=2, column=1, sticky="ew", padx=4, pady=2)
        ttk.Button(body, text="删除", command=delete_config).grid(row=3, column=1, sticky="ew", padx=4, pady=2)
        ttk.Button(body, text="切换到选中", command=lambda: (load_config_by_name(selected_name()), dlg.destroy()) if selected_name() else None).grid(row=4, column=1, sticky="ew", padx=4, pady=2)
        ttk.Button(body, text="关闭", command=dlg.destroy).grid(row=5, column=1, sticky="ew", padx=4, pady=2)
        reload_list()
        dlg.after_idle(lambda: _show_centered_window(dlg, win))

    def manage_features():
        cfg.setdefault("features", [])
        dlg = _make_floating_child(win, "管理表特征")
        body = ttk.Frame(dlg, padding=10)
        body.pack(fill=tk.BOTH, expand=True)
        body.columnconfigure(1, weight=1)
        body.columnconfigure(2, weight=1)
        body.rowconfigure(0, weight=1)

        left_panel = ttk.Frame(body)
        left_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        right_panel = ttk.Frame(body)
        right_panel.grid(row=0, column=1, sticky="nsew")
        right_panel.columnconfigure(1, weight=1)
        right_panel.rowconfigure(5, weight=1)

        feature_frame, feature_lb = _make_scrollable_listbox(left_panel, height=18, width=28, exportselection=False)
        feature_frame.pack(fill=tk.BOTH, expand=True)
        selected_idx = {"value": None}

        name_var = tk.StringVar(value="")
        enabled_var = tk.BooleanVar(value=True)
        logic_var = tk.StringVar(value="AND")
        ttk.Label(right_panel, text="特征名称：").grid(row=0, column=0, sticky=tk.W, pady=3)
        ttk.Entry(right_panel, textvariable=name_var, width=32).grid(row=0, column=1, sticky="ew", pady=3)
        ttk.Checkbutton(right_panel, text="启用", variable=enabled_var).grid(row=0, column=2, sticky=tk.W, padx=6)
        ttk.Label(right_panel, text="默认连接：").grid(row=1, column=0, sticky=tk.W, pady=3)
        ttk.Combobox(right_panel, textvariable=logic_var, values=["AND", "OR"], width=8, state="readonly").grid(row=1, column=1, sticky=tk.W, pady=3)

        columns = ("join", "sheet", "row", "col", "mode", "value")
        cond_tree_frame = ttk.Frame(right_panel)
        cond_tree_frame.rowconfigure(0, weight=1)
        cond_tree_frame.columnconfigure(0, weight=1)
        cond_tree = ttk.Treeview(cond_tree_frame, columns=columns, show="headings", height=8)
        for col, text, width in [
            ("join", "连接", 58),
            ("sheet", "表格/Sheet", 110),
            ("row", "行", 60),
            ("col", "列", 60),
            ("mode", "匹配", 90),
            ("value", "值/正则", 220),
        ]:
            cond_tree.heading(col, text=text)
            cond_tree.column(col, width=width, anchor=tk.W)
        cond_tree_frame.grid(row=5, column=0, columnspan=4, sticky="nsew", pady=(6, 4))
        cond_tree.grid(row=0, column=0, sticky="nsew")
        cond_scroll_y = ttk.Scrollbar(cond_tree_frame, orient=tk.VERTICAL, command=cond_tree.yview)
        cond_scroll_y.grid(row=0, column=1, sticky="ns")
        cond_scroll_x = ttk.Scrollbar(cond_tree_frame, orient=tk.HORIZONTAL, command=cond_tree.xview)
        cond_scroll_x.grid(row=1, column=0, sticky="ew")
        cond_tree.configure(yscrollcommand=cond_scroll_y.set, xscrollcommand=cond_scroll_x.set)

        input_row = ttk.Frame(right_panel)
        input_row.grid(row=6, column=0, columnspan=4, sticky="ew", pady=4)
        cond_join_var = tk.StringVar(value="AND")
        cond_sheet_var = tk.StringVar(value="")
        cond_row_var = tk.StringVar(value="")
        cond_col_var = tk.StringVar(value="")
        cond_mode_var = tk.StringVar(value="包含")
        cond_value_var = tk.StringVar(value="")
        ttk.Combobox(input_row, textvariable=cond_join_var, values=["AND", "OR"], width=6, state="readonly").pack(side=tk.LEFT, padx=2)
        ttk.Entry(input_row, textvariable=cond_sheet_var, width=14).pack(side=tk.LEFT, padx=2)
        ttk.Entry(input_row, textvariable=cond_row_var, width=6).pack(side=tk.LEFT, padx=2)
        ttk.Entry(input_row, textvariable=cond_col_var, width=6).pack(side=tk.LEFT, padx=2)
        ttk.Combobox(input_row, textvariable=cond_mode_var, values=["包含", "等于", "不等于", "正则匹配", "正则不匹配", "为空", "非空"], width=12, state="readonly").pack(side=tk.LEFT, padx=2)
        ttk.Entry(input_row, textvariable=cond_value_var, width=28).pack(side=tk.LEFT, padx=2, fill=tk.X, expand=True)

        def feature_label(feature):
            prefix = "" if feature.get("enabled", True) else "[停用] "
            name = _as_text(feature.get("name")) or "未命名特征"
            return f"{prefix}{name} ({len(feature.get('conditions', []) or [])} 条)"

        def serialize_conditions():
            rows = []
            for item_id in cond_tree.get_children():
                join, sheet, row, col, mode, value = cond_tree.item(item_id, "values")
                rows.append({
                    "join": _as_text(join) or "AND",
                    "sheet_name": _as_text(sheet),
                    "row_index": _as_text(row),
                    "col_index": _as_text(col),
                    "mode": _as_text(mode) or "包含",
                    "value": _as_text(value),
                })
            return rows

        def load_feature(index):
            if index is None or index < 0 or index >= len(cfg.get("features", [])):
                selected_idx["value"] = None
                return
            selected_idx["value"] = index
            feature = cfg["features"][index]
            name_var.set(_as_text(feature.get("name")))
            enabled_var.set(bool(feature.get("enabled", True)))
            logic_var.set(_as_text(feature.get("logic", "AND")) or "AND")
            cond_tree.delete(*cond_tree.get_children())
            for cond in feature.get("conditions", []) or []:
                cond_tree.insert("", tk.END, values=(
                    _as_text(cond.get("join") or "AND"),
                    _as_text(cond.get("sheet_name")),
                    _as_text(cond.get("row_index")),
                    _as_text(cond.get("col_index")),
                    _as_text(cond.get("mode") or "包含"),
                    _as_text(cond.get("value")),
                ))

        def refresh_feature_list(select_index=None):
            feature_lb.delete(0, tk.END)
            for feature in cfg.get("features", []) or []:
                feature_lb.insert(tk.END, feature_label(feature))
            if cfg.get("features"):
                idx = 0 if select_index is None else max(0, min(select_index, len(cfg["features"]) - 1))
                feature_lb.selection_set(idx)
                feature_lb.see(idx)
                load_feature(idx)

        def save_feature(show_msg=False):
            idx = selected_idx.get("value")
            if idx is None:
                return
            name = _as_text(name_var.get())
            if not name:
                messagebox.showwarning("提示", "特征名称不能为空。", parent=dlg)
                return
            cfg["features"][idx] = {
                "name": name,
                "enabled": bool(enabled_var.get()),
                "logic": logic_var.get() or "AND",
                "conditions": serialize_conditions(),
            }
            _save_config(params, context, cfg)
            refresh_feature_list(idx)
            refresh_rules()
            status_var.set(f"已保存表特征：{name}")
            if show_msg:
                messagebox.showinfo("保存完成", "表特征已保存。", parent=dlg)

        def add_feature():
            cfg.setdefault("features", []).append({
                "name": f"feature_{len(cfg.get('features', [])) + 1}",
                "enabled": True,
                "logic": "AND",
                "conditions": [{"join": "AND", "sheet_name": "", "row_index": "1", "col_index": "1", "mode": "包含", "value": ""}],
            })
            refresh_feature_list(len(cfg["features"]) - 1)

        def delete_feature():
            idx = selected_idx.get("value")
            if idx is None:
                return
            if not messagebox.askyesno("确认删除", "删除当前表特征？", parent=dlg):
                return
            cfg["features"].pop(idx)
            _save_config(params, context, cfg)
            selected_idx["value"] = None
            refresh_feature_list(0)
            refresh_rules()

        def add_condition():
            cond_tree.insert("", tk.END, values=(cond_join_var.get(), cond_sheet_var.get(), cond_row_var.get(), cond_col_var.get(), cond_mode_var.get(), cond_value_var.get()))

        def update_condition():
            sel = cond_tree.selection()
            if not sel:
                return
            cond_tree.item(sel[0], values=(cond_join_var.get(), cond_sheet_var.get(), cond_row_var.get(), cond_col_var.get(), cond_mode_var.get(), cond_value_var.get()))

        def delete_condition():
            for item_id in cond_tree.selection():
                cond_tree.delete(item_id)

        def on_feature_select(_event=None):
            sel = feature_lb.curselection()
            if sel:
                load_feature(int(sel[0]))

        def on_condition_select(_event=None):
            sel = cond_tree.selection()
            if not sel:
                return
            join, sheet, row, col, mode, value = cond_tree.item(sel[0], "values")
            cond_join_var.set(join or "AND")
            cond_sheet_var.set(sheet)
            cond_row_var.set(row)
            cond_col_var.set(col)
            cond_mode_var.set(mode or "包含")
            cond_value_var.set(value)

        feature_lb.bind("<<ListboxSelect>>", on_feature_select)
        cond_tree.bind("<<TreeviewSelect>>", on_condition_select)

        left_buttons = ttk.Frame(left_panel)
        left_buttons.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(left_buttons, text="增加", command=add_feature).pack(side=tk.LEFT, padx=2)
        ttk.Button(left_buttons, text="删除", command=delete_feature).pack(side=tk.LEFT, padx=2)
        ttk.Button(left_buttons, text="保存修改", command=lambda: save_feature(True)).pack(side=tk.LEFT, padx=2)

        cond_buttons = ttk.Frame(right_panel)
        cond_buttons.grid(row=7, column=0, columnspan=4, sticky=tk.E, pady=4)
        ttk.Button(cond_buttons, text="增加条件", command=add_condition).pack(side=tk.LEFT, padx=2)
        ttk.Button(cond_buttons, text="更新条件", command=update_condition).pack(side=tk.LEFT, padx=2)
        ttk.Button(cond_buttons, text="删除条件", command=delete_condition).pack(side=tk.LEFT, padx=2)
        ttk.Button(cond_buttons, text="关闭", command=dlg.destroy).pack(side=tk.RIGHT, padx=2)

        refresh_feature_list(0)
        dlg.after_idle(lambda: _show_centered_window(dlg, win, 860, 520))

    def manage_global_rules(initial_index=None):
        sync_params_from_ui()
        cfg.setdefault("global_rules", [])
        dlg = _make_floating_child(win, "全局搜索替换规则窗口")
        body = ttk.Frame(dlg, padding=10)
        body.pack(fill=tk.BOTH, expand=True)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        left_panel = ttk.Frame(body)
        left_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        editor_outer = ttk.Frame(body)
        editor_outer.grid(row=0, column=1, sticky="nsew")
        editor_outer.rowconfigure(0, weight=1)
        editor_outer.columnconfigure(0, weight=1)
        editor_canvas = tk.Canvas(editor_outer, highlightthickness=0)
        editor_canvas.grid(row=0, column=0, sticky="nsew")
        editor_scroll = ttk.Scrollbar(editor_outer, orient=tk.VERTICAL, command=editor_canvas.yview)
        editor_scroll.grid(row=0, column=1, sticky="ns")
        editor_canvas.configure(yscrollcommand=editor_scroll.set)
        right_panel = ttk.Frame(editor_canvas)
        right_panel_window = editor_canvas.create_window((0, 0), window=right_panel, anchor="nw")
        right_panel.columnconfigure(1, weight=1)
        right_panel.rowconfigure(7, weight=1)
        right_panel.rowconfigure(11, weight=1)

        def refresh_editor_scroll(_event=None):
            editor_canvas.configure(scrollregion=editor_canvas.bbox("all"))

        def resize_editor_width(event=None):
            if event is not None:
                editor_canvas.itemconfigure(right_panel_window, width=max(1, event.width))
            refresh_editor_scroll()

        def on_editor_wheel(event):
            delta = -1 if event.delta > 0 else 1
            editor_canvas.yview_scroll(delta * 3, "units")

        right_panel.bind("<Configure>", refresh_editor_scroll)
        editor_canvas.bind("<Configure>", resize_editor_width)
        editor_canvas.bind("<MouseWheel>", on_editor_wheel)
        preview_panel = ttk.Frame(body)
        preview_panel.grid(row=0, column=2, sticky="nsew", padx=(8, 0))
        preview_panel.columnconfigure(0, weight=1)
        preview_panel.rowconfigure(1, weight=1)

        rule_list_frame, rule_list = _make_scrollable_listbox(left_panel, height=22, width=32, exportselection=False)
        rule_list_frame.pack(fill=tk.BOTH, expand=True)
        selected_idx = {"value": None}

        name_var = tk.StringVar(value="")
        enabled_var = tk.BooleanVar(value=True)
        feature_var = tk.StringVar(value=FEATURE_ANY_LABEL)
        scope_var = tk.StringVar(value="全部")
        sheet_var = tk.StringVar(value=SHEET_ALL_LABEL)
        logic_var = tk.StringVar(value="AND")
        event_tags_var = tk.StringVar(value="")

        ttk.Label(right_panel, text="规则名称：").grid(row=0, column=0, sticky=tk.W, pady=3)
        ttk.Entry(right_panel, textvariable=name_var, width=30).grid(row=0, column=1, sticky="ew", pady=3)
        ttk.Checkbutton(right_panel, text="启用", variable=enabled_var).grid(row=0, column=2, sticky=tk.W, padx=6)
        ttk.Label(right_panel, text="表特征：").grid(row=1, column=0, sticky=tk.W, pady=3)
        feature_combo = ttk.Combobox(right_panel, textvariable=feature_var, values=current_feature_names(True), width=24, state="normal")
        feature_combo.grid(row=1, column=1, sticky=tk.W, pady=3)
        ttk.Label(right_panel, text="事件标签：").grid(row=1, column=2, sticky=tk.E, pady=3)
        ttk.Entry(right_panel, textvariable=event_tags_var, width=24).grid(row=1, column=3, sticky="ew", pady=3)
        ttk.Label(right_panel, text="范围：").grid(row=2, column=0, sticky=tk.W, pady=3)
        ttk.Combobox(
            right_panel,
            textvariable=scope_var,
            values=["全部", "段落", "表格单元格", GLOBAL_SCOPE_SPECIAL_OBJECTS],
            width=16,
            state="readonly",
        ).grid(row=2, column=1, sticky=tk.W, pady=3)
        ttk.Label(right_panel, text="表格/Sheet：").grid(row=2, column=2, sticky=tk.E, pady=3)
        sheet_combo = ttk.Combobox(right_panel, textvariable=sheet_var, values=current_sheet_names(True), width=18, state="normal")
        sheet_combo.grid(row=2, column=3, sticky=tk.W, pady=3)
        ttk.Label(right_panel, text="条件默认连接：").grid(row=3, column=0, sticky=tk.W, pady=3)
        ttk.Combobox(right_panel, textvariable=logic_var, values=["AND", "OR"], width=8, state="readonly").grid(row=3, column=1, sticky=tk.W, pady=3)
        ttk.Label(preview_panel, text="匹配/替换预览").grid(row=0, column=0, sticky=tk.W, pady=(0, 4))
        preview_text = tk.Text(preview_panel, height=26, width=30, wrap=tk.WORD)
        preview_text.grid(row=1, column=0, sticky="nsew")
        preview_scroll = ttk.Scrollbar(preview_panel, orient=tk.VERTICAL, command=preview_text.yview)
        preview_scroll.grid(row=1, column=1, sticky="ns")
        preview_text.configure(yscrollcommand=preview_scroll.set)
        preview_status_var = tk.StringVar(value="未刷新")
        ttk.Label(preview_panel, textvariable=preview_status_var, foreground="gray").grid(row=2, column=0, columnspan=2, sticky=tk.W, pady=(4, 0))

        cond_columns = ("join", "mode", "value")
        cond_tree_frame = ttk.Frame(right_panel)
        cond_tree_frame.rowconfigure(0, weight=1)
        cond_tree_frame.columnconfigure(0, weight=1)
        cond_tree = ttk.Treeview(cond_tree_frame, columns=cond_columns, show="headings", height=4)
        for col, text, width in [("join", "连接", 70), ("mode", "匹配", 120), ("value", "值/正则", 360)]:
            cond_tree.heading(col, text=text)
            cond_tree.column(col, width=width, anchor=tk.W)
        ttk.Label(right_panel, text="匹配条件").grid(row=6, column=0, columnspan=4, sticky=tk.W, pady=(8, 0))
        cond_tree_frame.grid(row=7, column=0, columnspan=4, sticky="nsew", pady=4)
        cond_tree.grid(row=0, column=0, sticky="nsew")
        cond_tree_scroll = ttk.Scrollbar(cond_tree_frame, orient=tk.VERTICAL, command=cond_tree.yview)
        cond_tree_scroll.grid(row=0, column=1, sticky="ns")
        cond_tree.configure(yscrollcommand=cond_tree_scroll.set)

        cond_input = ttk.Frame(right_panel)
        cond_input.grid(row=8, column=0, columnspan=4, sticky="ew", pady=2)
        cond_join_var = tk.StringVar(value="AND")
        cond_mode_var = tk.StringVar(value="正则匹配")
        cond_value_var = tk.StringVar(value="")
        ttk.Combobox(cond_input, textvariable=cond_join_var, values=["AND", "OR"], width=7, state="readonly").pack(side=tk.LEFT, padx=2)
        ttk.Combobox(cond_input, textvariable=cond_mode_var, values=["包含", "等于", "不等于", "正则匹配", "正则不匹配", "为空", "非空"], width=14, state="readonly").pack(side=tk.LEFT, padx=2)
        ttk.Entry(cond_input, textvariable=cond_value_var, width=48).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)

        batch_columns = (
            "match_mode",
            "match_source",
            "match_value",
            "match_field",
            "match_row_policy",
            "match_row_index",
            "replace_mode",
            "replace_source",
            "replace_value",
            "replace_field",
            "row_policy",
            "row_index",
            "case",
            "skip",
            "count",
        )
        batch_tree_frame = ttk.Frame(right_panel)
        batch_tree_frame.rowconfigure(0, weight=1)
        batch_tree_frame.columnconfigure(0, weight=1)
        batch_tree = ttk.Treeview(batch_tree_frame, columns=batch_columns, show="headings", height=4)
        for col, text, width in [
            ("match_mode", "匹配方式", 90),
            ("match_source", "匹配值来源", 120),
            ("match_value", "匹配值", 130),
            ("match_field", "匹配值字段", 130),
            ("match_row_policy", "匹配取行", 110),
            ("match_row_index", "匹配固定行", 86),
            ("replace_mode", "替换方式", 150),
            ("replace_source", "替换值来源", 120),
            ("replace_value", "替换值/模板", 150),
            ("replace_field", "替换值字段", 130),
            ("row_policy", "替换取行", 110),
            ("row_index", "固定行", 70),
            ("case", "大小写", 70),
            ("skip", "空值跳过", 80),
            ("count", "次数", 60),
        ]:
            batch_tree.heading(col, text=text)
            batch_tree.column(col, width=width, anchor=tk.W, stretch=False)
        ttk.Label(right_panel, text="批量替换规则列表（按顺序作用于批量作用对象）").grid(row=10, column=0, columnspan=4, sticky=tk.W, pady=(8, 0))
        batch_tree_frame.grid(row=11, column=0, columnspan=4, sticky="nsew", pady=4)
        batch_tree.grid(row=0, column=0, sticky="nsew")
        batch_tree_y_scroll = ttk.Scrollbar(batch_tree_frame, orient=tk.VERTICAL, command=batch_tree.yview)
        batch_tree_y_scroll.grid(row=0, column=1, sticky="ns")
        batch_tree_x_scroll = ttk.Scrollbar(batch_tree_frame, orient=tk.HORIZONTAL, command=batch_tree.xview)
        batch_tree_x_scroll.grid(row=1, column=0, sticky="ew")
        batch_tree.configure(yscrollcommand=batch_tree_y_scroll.set, xscrollcommand=batch_tree_x_scroll.set)

        batch_input = ttk.LabelFrame(right_panel, text="批量替换规则设置", padding=6)
        batch_input.grid(row=12, column=0, columnspan=4, sticky="ew", pady=2)
        batch_match_mode_var = tk.StringVar(value="包含")
        batch_match_source_var = tk.StringVar(value="手动输入")
        batch_match_value_var = tk.StringVar(value="")
        batch_replace_value_var = tk.StringVar(value="")
        batch_replace_mode_var = tk.StringVar(value="局部替换匹配字符串")
        batch_replace_source_var = tk.StringVar(value="手动输入")
        batch_match_field_var = tk.StringVar(value="")
        batch_replace_field_var = tk.StringVar(value="")
        batch_target_scope_var = tk.StringVar(value=BATCH_TARGET_FULL_TEXT)
        batch_match_row_policy_var = tk.StringVar(value=REPLACE_ROW_MATCH_INDEX)
        batch_match_row_index_var = tk.StringVar(value="1")
        batch_replace_row_policy_var = tk.StringVar(value=REPLACE_ROW_CONTENT_ROW)
        batch_replace_row_index_var = tk.StringVar(value="1")
        batch_case_var = tk.BooleanVar(value=True)
        batch_skip_empty_var = tk.BooleanVar(value=True)
        batch_count_var = tk.StringVar(value="0")
        batch_input.columnconfigure(0, weight=1)
        batch_input.columnconfigure(1, weight=1)
        target_panel = ttk.Frame(batch_input)
        target_panel.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 4))
        match_panel = ttk.LabelFrame(batch_input, text="1. 匹配命中值", padding=6)
        match_panel.grid(row=1, column=0, sticky="nsew", padx=(0, 4), pady=2)
        replace_panel = ttk.LabelFrame(batch_input, text="2. 替换为", padding=6)
        replace_panel.grid(row=1, column=1, sticky="nsew", padx=(4, 0), pady=2)
        option_panel = ttk.Frame(batch_input)
        option_panel.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        target_panel.columnconfigure(1, weight=0)
        target_panel.columnconfigure(3, weight=1)
        match_panel.columnconfigure(1, weight=1)
        replace_panel.columnconfigure(1, weight=1)
        option_panel.columnconfigure(4, weight=1)

        ttk.Label(target_panel, text="批量作用对象：").grid(row=0, column=0, sticky=tk.W, padx=4, pady=3)
        ttk.Combobox(target_panel, textvariable=batch_target_scope_var, values=BATCH_TARGET_CHOICES, width=16, state="readonly").grid(row=0, column=1, sticky=tk.W, padx=4, pady=3)
        ttk.Label(target_panel, text="先用上方条件初筛，再把这里选定的对象交给批量规则。", foreground="gray").grid(row=0, column=2, columnspan=2, sticky=tk.W, padx=12, pady=3)

        ttk.Label(match_panel, text="匹配方式：").grid(row=0, column=0, sticky=tk.W, padx=4, pady=3)
        ttk.Combobox(match_panel, textvariable=batch_match_mode_var, values=["包含", "完全相等", "不等于", "开头是", "结尾是", "正则匹配", "为空", "不为空"], width=14, state="readonly").grid(row=0, column=1, sticky="ew", padx=4, pady=3)
        ttk.Label(match_panel, text="匹配值来源：").grid(row=1, column=0, sticky=tk.W, padx=4, pady=3)
        batch_match_source_combo = ttk.Combobox(match_panel, textvariable=batch_match_source_var, values=[], width=16, state="readonly")
        batch_match_source_combo.grid(row=1, column=1, sticky="ew", padx=4, pady=3)
        ttk.Label(match_panel, text="匹配值：").grid(row=2, column=0, sticky=tk.W, padx=4, pady=3)
        batch_match_value_entry = ttk.Entry(match_panel, textvariable=batch_match_value_var, width=24)
        batch_match_value_entry.grid(row=2, column=1, sticky="ew", padx=4, pady=3)
        ttk.Label(match_panel, text="匹配值字段：").grid(row=3, column=0, sticky=tk.W, padx=4, pady=3)
        batch_match_field_combo = ttk.Combobox(match_panel, textvariable=batch_match_field_var, values=[], width=24, state="readonly")
        batch_match_field_combo.grid(row=3, column=1, sticky="ew", padx=4, pady=3)
        ttk.Label(match_panel, text="匹配取行：").grid(row=4, column=0, sticky=tk.W, padx=4, pady=3)
        batch_match_row_policy_combo = ttk.Combobox(match_panel, textvariable=batch_match_row_policy_var, values=REPLACE_ROW_POLICY_CHOICES, width=16, state="readonly")
        batch_match_row_policy_combo.grid(row=4, column=1, sticky="ew", padx=4, pady=3)
        ttk.Label(match_panel, text="固定行号：").grid(row=5, column=0, sticky=tk.W, padx=4, pady=3)
        batch_match_row_index_entry = ttk.Entry(match_panel, textvariable=batch_match_row_index_var, width=10)
        batch_match_row_index_entry.grid(row=5, column=1, sticky=tk.W, padx=4, pady=3)

        ttk.Label(replace_panel, text="替换方式：").grid(row=0, column=0, sticky=tk.W, padx=4, pady=3)
        ttk.Combobox(replace_panel, textvariable=batch_replace_mode_var, values=["局部替换匹配字符串", "整格替换为新值"], width=20, state="readonly").grid(row=0, column=1, sticky="ew", padx=4, pady=3)
        ttk.Label(replace_panel, text="替换值来源：").grid(row=1, column=0, sticky=tk.W, padx=4, pady=3)
        batch_replace_source_combo = ttk.Combobox(replace_panel, textvariable=batch_replace_source_var, values=[], width=16, state="readonly")
        batch_replace_source_combo.grid(row=1, column=1, sticky="ew", padx=4, pady=3)
        ttk.Label(replace_panel, text="替换值：").grid(row=2, column=0, sticky=tk.W, padx=4, pady=3)
        batch_replace_value_entry = ttk.Entry(replace_panel, textvariable=batch_replace_value_var, width=26)
        batch_replace_value_entry.grid(row=2, column=1, sticky="ew", padx=4, pady=3)
        ttk.Label(replace_panel, text="替换值字段：").grid(row=3, column=0, sticky=tk.W, padx=4, pady=3)
        batch_replace_field_combo = ttk.Combobox(replace_panel, textvariable=batch_replace_field_var, values=[], width=24, state="readonly")
        batch_replace_field_combo.grid(row=3, column=1, sticky="ew", padx=4, pady=3)
        ttk.Label(replace_panel, text="替换取行：").grid(row=4, column=0, sticky=tk.W, padx=4, pady=3)
        batch_replace_row_policy_combo = ttk.Combobox(replace_panel, textvariable=batch_replace_row_policy_var, values=REPLACE_ROW_POLICY_CHOICES, width=16, state="readonly")
        batch_replace_row_policy_combo.grid(row=4, column=1, sticky="ew", padx=4, pady=3)
        ttk.Label(replace_panel, text="固定行号：").grid(row=5, column=0, sticky=tk.W, padx=4, pady=3)
        batch_replace_row_index_entry = ttk.Entry(replace_panel, textvariable=batch_replace_row_index_var, width=10)
        batch_replace_row_index_entry.grid(row=5, column=1, sticky=tk.W, padx=4, pady=3)

        ttk.Checkbutton(option_panel, text="区分大小写", variable=batch_case_var).grid(row=0, column=0, sticky=tk.W, padx=4, pady=3)
        ttk.Checkbutton(option_panel, text="列匹配值为空时跳过", variable=batch_skip_empty_var).grid(row=0, column=1, sticky=tk.W, padx=12, pady=3)
        ttk.Label(option_panel, text="次数：").grid(row=0, column=2, sticky=tk.W, padx=(12, 4), pady=3)
        ttk.Entry(option_panel, textvariable=batch_count_var, width=8).grid(row=0, column=3, sticky=tk.W, padx=4, pady=3)
        ttk.Label(option_panel, text="0 表示全部；规则作用于上方选择的批量作用对象。", foreground="gray").grid(row=0, column=4, sticky=tk.W, padx=12, pady=3)

        def batch_source_choices():
            choices = ["手动输入"]
            for alias in table_aliases:
                alias = _as_text(alias)
                if alias and alias not in choices:
                    choices.append(alias)
            return choices

        def batch_source_fields(source):
            source = _normalize_batch_table_source(source)
            if _is_manual_batch_source(source):
                return []
            table = tables.get(source, {})
            fields, _rows = _content_rows(table)
            return fields

        def refresh_batch_source_options():
            choices = batch_source_choices()
            batch_match_source_combo.configure(values=choices)
            batch_replace_source_combo.configure(values=choices)
            if batch_match_source_var.get() not in choices:
                batch_match_source_var.set("手动输入")
            if batch_replace_source_var.get() not in choices:
                batch_replace_source_var.set("手动输入")

        def refresh_batch_row_controls():
            match_is_manual = _is_manual_batch_source(batch_match_source_var.get())
            replace_is_manual = _is_manual_batch_source(batch_replace_source_var.get())
            batch_match_row_policy_combo.configure(state="disabled" if match_is_manual else "readonly")
            match_fixed_enabled = (not match_is_manual) and _batch_match_row_policy({"match_row_policy": batch_match_row_policy_var.get()}) == REPLACE_ROW_FIXED
            batch_match_row_index_entry.configure(state="normal" if match_fixed_enabled else "disabled")
            batch_replace_row_policy_combo.configure(state="disabled" if replace_is_manual else "readonly")
            fixed_enabled = (not replace_is_manual) and _batch_replace_row_policy({"replace_row_policy": batch_replace_row_policy_var.get()}) == REPLACE_ROW_FIXED
            batch_replace_row_index_entry.configure(state="normal" if fixed_enabled else "disabled")

        def refresh_batch_field_combos(reset_invalid=True):
            refresh_batch_source_options()
            match_fields = batch_source_fields(batch_match_source_var.get())
            replace_fields = batch_source_fields(batch_replace_source_var.get())
            batch_match_field_combo.configure(values=match_fields, state="readonly" if match_fields else "disabled")
            batch_replace_field_combo.configure(values=replace_fields, state="readonly" if replace_fields else "disabled")
            batch_match_value_entry.configure(state="normal" if _is_manual_batch_source(batch_match_source_var.get()) else "disabled")
            batch_replace_value_entry.configure(state="normal" if _is_manual_batch_source(batch_replace_source_var.get()) else "disabled")
            refresh_batch_row_controls()
            if reset_invalid and batch_match_field_var.get() not in match_fields:
                batch_match_field_var.set("")
            if reset_invalid and batch_replace_field_var.get() not in replace_fields:
                batch_replace_field_var.set("")

        batch_match_source_combo.bind("<<ComboboxSelected>>", lambda _event=None: refresh_batch_field_combos(True))
        batch_replace_source_combo.bind("<<ComboboxSelected>>", lambda _event=None: refresh_batch_field_combos(True))
        batch_match_row_policy_combo.bind("<<ComboboxSelected>>", lambda _event=None: refresh_batch_row_controls())
        batch_replace_row_policy_combo.bind("<<ComboboxSelected>>", lambda _event=None: refresh_batch_row_controls())

        def rule_label(rule):
            prefix = "" if rule.get("enabled", True) else "[停用] "
            name = _as_text(rule.get("name")) or "未命名全局规则"
            return f"{prefix}{name} ({len(rule.get('conditions', []) or [])} 条条件/{len(_batch_rules_for_rule(rule))} 条批量规则)"

        def serialize_conditions():
            rows = []
            for item_id in cond_tree.get_children():
                join, mode, value = cond_tree.item(item_id, "values")
                rows.append({"join": _as_text(join) or "AND", "mode": _as_text(mode) or "包含", "value": _as_text(value)})
            return rows

        def serialize_batch_rules():
            rows = []
            for item_id in batch_tree.get_children():
                values = list(batch_tree.item(item_id, "values"))
                while len(values) < 15:
                    values.append("")
                (
                    match_mode,
                    match_source,
                    match_value,
                    match_field,
                    match_row_policy,
                    match_row_index,
                    replace_mode,
                    replace_source,
                    replace_value,
                    replace_field,
                    row_policy,
                    row_index,
                    case_text,
                    skip_text,
                    count,
                ) = values[:15]
                rows.append({
                    "enabled": True,
                    "match_mode": _as_text(match_mode) or "包含",
                    "match_value_source": _normalize_batch_table_source(match_source),
                    "match_value": _as_text(match_value),
                    "replace_value": _as_text(replace_value),
                    "replace_mode": _as_text(replace_mode) or "局部替换匹配字符串",
                    "replace_value_source": _normalize_batch_table_source(replace_source),
                    "value_source": "手动输入",
                    "match_value_field": _as_text(match_field),
                    "replace_value_field": _as_text(replace_field),
                    "match_row_policy": _normalize_replace_row_policy(match_row_policy),
                    "match_row_index": _as_text(match_row_index) or "1",
                    "replace_row_policy": _normalize_replace_row_policy(row_policy),
                    "replace_row_index": _as_text(row_index) or "1",
                    "case_sensitive": _as_text(case_text) not in ("否", "False", "false", "0"),
                    "skip_empty_match_value": _as_text(skip_text) not in ("否", "False", "false", "0"),
                    "count": _as_text(count) or "0",
                })
            return rows

        def current_batch_values():
            return (
                batch_match_mode_var.get(),
                batch_match_source_var.get(),
                batch_match_value_var.get(),
                batch_match_field_var.get(),
                _normalize_replace_row_policy(batch_match_row_policy_var.get()),
                batch_match_row_index_var.get() or "1",
                batch_replace_mode_var.get(),
                batch_replace_source_var.get(),
                batch_replace_value_var.get(),
                batch_replace_field_var.get(),
                _normalize_replace_row_policy(batch_replace_row_policy_var.get()),
                batch_replace_row_index_var.get() or "1",
                "是" if batch_case_var.get() else "否",
                "是" if batch_skip_empty_var.get() else "否",
                batch_count_var.get(),
            )

        def sync_editor_rows():
            cond_sel = cond_tree.selection()
            if cond_sel:
                cond_tree.item(cond_sel[0], values=(cond_join_var.get(), cond_mode_var.get(), cond_value_var.get()))
            elif not cond_tree.get_children() and _as_text(cond_value_var.get()):
                cond_tree.insert("", tk.END, values=(cond_join_var.get(), cond_mode_var.get(), cond_value_var.get()))
            batch_sel = batch_tree.selection()
            has_batch_input = any(_as_text(value) for value in (
                batch_match_value_var.get(),
                batch_replace_value_var.get(),
                batch_match_field_var.get(),
                batch_replace_field_var.get(),
            ))
            if batch_sel:
                batch_tree.item(batch_sel[0], values=current_batch_values())
            elif not batch_tree.get_children() and has_batch_input:
                batch_tree.insert("", tk.END, values=current_batch_values())

        def build_rule_from_editor():
            sync_editor_rows()
            return {
                "name": _as_text(name_var.get()) or "未命名全局规则",
                "enabled": bool(enabled_var.get()),
                "feature_name": _cfg_feature_name(feature_var.get()),
                "scope": scope_var.get() or "全部",
                "sheet_name": _cfg_sheet_name(sheet_var.get()),
                "event_tags": _normalize_event_tags(event_tags_var.get()),
                "condition_logic": logic_var.get() or "AND",
                "conditions": serialize_conditions(),
                "batch_target_scope": _normalize_batch_target_scope(batch_target_scope_var.get()),
                "batch_rules": serialize_batch_rules(),
            }

        def refresh_condition_preview():
            rule = build_rule_from_editor()
            records = list(state.get("records", []) or [])
            preview_text.configure(state="normal")
            preview_text.delete("1.0", tk.END)
            if not records:
                preview_text.insert(tk.END, "当前文档读取表没有可预览记录，请先刷新可视化。")
                preview_text.configure(state="disabled")
                preview_status_var.set("条件命中 0 条")
                return
            preview_rows, total_matched, total_errors = _preview_global_match_rows([rule], records, cfg.get("features", []), limit=500)
            for item in preview_rows:
                preview_text.insert(
                    tk.END,
                    f"[{item.get('status')}] {item.get('source_file')} {item.get('location')}\n"
                    f"原文：{item.get('old_text')}\n"
                    f"命中值：{item.get('new_text')}\n"
                    f"明细：{item.get('detail')}\n\n"
                )
            if total_matched > len(preview_rows):
                preview_text.insert(tk.END, "... 还有更多条件命中结果未显示，请缩小规则范围\n")
            if not preview_rows:
                preview_text.insert(tk.END, "当前匹配条件未命中记录。")
            preview_text.configure(state="disabled")
            preview_status_var.set(f"条件命中 {total_matched} 条，错误 {total_errors} 条，显示 {len(preview_rows)} 条")

        def refresh_match_preview():
            rule = build_rule_from_editor()
            records = list(state.get("records", []) or [])
            preview_text.configure(state="normal")
            preview_text.delete("1.0", tk.END)
            if not records:
                preview_text.insert(tk.END, "当前文档读取表没有可预览记录，请先刷新可视化。")
                preview_text.configure(state="disabled")
                preview_status_var.set("可替换 0 条")
                return
            sync_params_from_ui()
            contents = current_content_rows()
            preview_rows, total_changed, total_errors = _preview_global_replace_rows(
                [rule],
                records,
                cfg.get("features", []),
                contents,
                current_aux_rows(),
                params,
                limit=500,
                include_unchanged=True,
                table_context=current_table_context(),
            )
            for item in preview_rows:
                preview_text.insert(
                    tk.END,
                    f"[{item.get('status')}] {item.get('source_file')} {item.get('location')} 新内容行{item.get('content_row')}\n"
                    f"原文：{item.get('old_text')}\n"
                    f"替换：{item.get('new_text')}\n"
                    f"明细：{item.get('detail')}\n\n"
                )
            if total_changed > len([r for r in preview_rows if r.get("status") == "替换"]):
                preview_text.insert(tk.END, "... 还有更多替换结果未显示，请缩小规则范围\n")
            if not preview_rows:
                preview_text.insert(tk.END, "当前规则未产生可替换结果。")
            preview_text.configure(state="disabled")
            preview_status_var.set(f"可替换 {total_changed} 条，错误 {total_errors} 条，显示 {len(preview_rows)} 条")

        def load_rule(index):
            if index is None or index < 0 or index >= len(cfg.get("global_rules", [])):
                selected_idx["value"] = None
                return
            selected_idx["value"] = index
            rule = cfg["global_rules"][index]
            name_var.set(_as_text(rule.get("name")))
            enabled_var.set(bool(rule.get("enabled", True)))
            feature_var.set(_ui_feature_name(rule.get("feature_name")))
            scope_var.set(_as_text(rule.get("scope", "全部")) or "全部")
            sheet_var.set(_ui_sheet_name(rule.get("sheet_name")))
            event_tags_var.set("，".join(_normalize_event_tags(rule.get("event_tags"))))
            logic_var.set(_as_text(rule.get("condition_logic", "AND")) or "AND")
            batch_target_scope_var.set(_batch_target_scope(rule))
            cond_tree.delete(*cond_tree.get_children())
            for cond in rule.get("conditions", []) or []:
                cond_tree.insert("", tk.END, values=(_as_text(cond.get("join") or "AND"), _as_text(cond.get("mode") or "包含"), _as_text(cond.get("value"))))
            batch_tree.delete(*batch_tree.get_children())
            for item in _batch_rules_for_rule(rule):
                batch_tree.insert("", tk.END, values=(
                    _as_text(item.get("match_mode") or "包含"),
                    _batch_match_source(item, params),
                    _as_text(item.get("match_value")),
                    _as_text(item.get("match_value_field")),
                    _batch_match_row_policy(item),
                    _as_text(item.get("match_row_index") or "1"),
                    _as_text(item.get("replace_mode") or "局部替换匹配字符串"),
                    _batch_replace_source(item, params),
                    _as_text(item.get("replace_value")),
                    _as_text(item.get("replace_value_field")),
                    _batch_replace_row_policy(item),
                    _as_text(item.get("replace_row_index") or "1"),
                    "是" if bool(item.get("case_sensitive", True)) else "否",
                    "是" if bool(item.get("skip_empty_match_value", True)) else "否",
                    _as_text(item.get("count") or "0"),
                ))

        def refresh_global_list(select_index=None):
            rule_list.delete(0, tk.END)
            for rule in cfg.get("global_rules", []) or []:
                rule_list.insert(tk.END, rule_label(rule))
            feature_combo.configure(values=current_feature_names(True))
            sheet_combo.configure(values=current_sheet_names(True))
            refresh_batch_field_combos(False)
            if cfg.get("global_rules"):
                idx = 0 if select_index is None else max(0, min(select_index, len(cfg["global_rules"]) - 1))
                rule_list.selection_set(idx)
                rule_list.see(idx)
                load_rule(idx)

        def save_rule(show_msg=False):
            idx = selected_idx.get("value")
            if idx is None:
                return
            name = _as_text(name_var.get())
            if not name:
                messagebox.showwarning("提示", "规则名称不能为空。", parent=dlg)
                return
            rule_payload = build_rule_from_editor()
            rule_payload["name"] = name
            cfg["global_rules"][idx] = rule_payload
            _save_config(params, context, cfg)
            refresh_global_list(idx)
            refresh_rules()
            status_var.set(f"已保存全局搜索替换规则：{name}")
            if show_msg:
                messagebox.showinfo("保存完成", "全局搜索替换规则已保存。", parent=dlg)

        def add_rule():
            cfg.setdefault("global_rules", []).append({
                "name": f"global_{len(cfg.get('global_rules', [])) + 1}",
                "enabled": True,
                "feature_name": "",
                "scope": "全部",
                "sheet_name": "",
                "condition_logic": "AND",
                "conditions": [{"join": "AND", "mode": "正则匹配", "value": ""}],
                "batch_target_scope": BATCH_TARGET_FULL_TEXT,
                "batch_rules": [{
                    "enabled": True,
                    "match_mode": "包含",
                    "match_value_source": "手动输入",
                    "match_value": "",
                    "replace_value": "",
                    "replace_mode": "局部替换匹配字符串",
                    "replace_value_source": "手动输入",
                    "value_source": "手动输入",
                    "match_value_field": "",
                    "match_row_policy": REPLACE_ROW_MATCH_INDEX,
                    "match_row_index": "1",
                    "replace_value_field": "",
                    "replace_row_policy": REPLACE_ROW_CONTENT_ROW,
                    "replace_row_index": "1",
                    "case_sensitive": True,
                    "skip_empty_match_value": True,
                    "count": "0",
                }],
            })
            refresh_global_list(len(cfg["global_rules"]) - 1)

        def delete_rule():
            idx = selected_idx.get("value")
            if idx is None:
                return
            if not messagebox.askyesno("确认删除", "删除当前全局规则？", parent=dlg):
                return
            cfg["global_rules"].pop(idx)
            _save_config(params, context, cfg)
            selected_idx["value"] = None
            refresh_global_list(0)
            refresh_rules()

        def add_condition():
            cond_tree.insert("", tk.END, values=(cond_join_var.get(), cond_mode_var.get(), cond_value_var.get()))

        def update_condition():
            sel = cond_tree.selection()
            if sel:
                cond_tree.item(sel[0], values=(cond_join_var.get(), cond_mode_var.get(), cond_value_var.get()))

        def delete_condition():
            for item_id in cond_tree.selection():
                cond_tree.delete(item_id)

        def add_batch_rule():
            batch_tree.insert("", tk.END, values=current_batch_values())

        def update_batch_rule():
            sel = batch_tree.selection()
            if sel:
                batch_tree.item(sel[0], values=current_batch_values())

        def delete_batch_rule():
            for item_id in batch_tree.selection():
                batch_tree.delete(item_id)

        def on_rule_select(_event=None):
            sel = rule_list.curselection()
            if sel:
                load_rule(int(sel[0]))

        def on_condition_select(_event=None):
            sel = cond_tree.selection()
            if not sel:
                return
            join, mode, value = cond_tree.item(sel[0], "values")
            cond_join_var.set(join or "AND")
            cond_mode_var.set(mode or "包含")
            cond_value_var.set(value)

        def on_batch_rule_select(_event=None):
            sel = batch_tree.selection()
            if not sel:
                return
            values = list(batch_tree.item(sel[0], "values"))
            while len(values) < 15:
                values.append("")
            (
                match_mode,
                match_source,
                match_value,
                match_field,
                match_row_policy,
                match_row_index,
                replace_mode,
                replace_source,
                replace_value,
                replace_field,
                row_policy,
                row_index,
                case_text,
                skip_text,
                count,
            ) = values[:15]
            batch_match_mode_var.set(match_mode or "包含")
            batch_match_source_var.set(_normalize_batch_table_source(match_source))
            batch_match_value_var.set(match_value)
            batch_match_field_var.set(match_field)
            batch_match_row_policy_var.set(_normalize_replace_row_policy(match_row_policy))
            batch_match_row_index_var.set(match_row_index or "1")
            batch_replace_mode_var.set(replace_mode or "局部替换匹配字符串")
            batch_replace_source_var.set(_normalize_batch_table_source(replace_source))
            batch_replace_value_var.set(replace_value)
            batch_replace_field_var.set(replace_field)
            batch_replace_row_policy_var.set(_normalize_replace_row_policy(row_policy))
            batch_replace_row_index_var.set(row_index or "1")
            batch_case_var.set(_as_text(case_text) not in ("否", "False", "false", "0"))
            batch_skip_empty_var.set(_as_text(skip_text) not in ("否", "False", "false", "0"))
            batch_count_var.set(count or "0")
            refresh_batch_field_combos(False)

        rule_list.bind("<<ListboxSelect>>", on_rule_select)
        cond_tree.bind("<<TreeviewSelect>>", on_condition_select)
        batch_tree.bind("<<TreeviewSelect>>", on_batch_rule_select)

        left_buttons = ttk.Frame(left_panel)
        left_buttons.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(left_buttons, text="增加", command=add_rule).pack(side=tk.LEFT, padx=2)
        ttk.Button(left_buttons, text="删除", command=delete_rule).pack(side=tk.LEFT, padx=2)
        ttk.Button(left_buttons, text="保存修改", command=lambda: save_rule(True)).pack(side=tk.LEFT, padx=2)

        cond_buttons = ttk.Frame(right_panel)
        cond_buttons.grid(row=9, column=0, columnspan=4, sticky=tk.E, pady=2)
        ttk.Button(cond_buttons, text="匹配预览", command=refresh_condition_preview).pack(side=tk.LEFT, padx=12)
        ttk.Button(cond_buttons, text="增加条件", command=add_condition).pack(side=tk.LEFT, padx=2)
        ttk.Button(cond_buttons, text="更新条件", command=update_condition).pack(side=tk.LEFT, padx=2)
        ttk.Button(cond_buttons, text="删除条件", command=delete_condition).pack(side=tk.LEFT, padx=2)

        batch_buttons = ttk.Frame(right_panel)
        batch_buttons.grid(row=13, column=0, columnspan=4, sticky=tk.E, pady=2)
        ttk.Button(batch_buttons, text="增加批量规则", command=add_batch_rule).pack(side=tk.LEFT, padx=2)
        ttk.Button(batch_buttons, text="更新批量规则", command=update_batch_rule).pack(side=tk.LEFT, padx=2)
        ttk.Button(batch_buttons, text="删除批量规则", command=delete_batch_rule).pack(side=tk.LEFT, padx=2)
        ttk.Button(batch_buttons, text="执行替换预览", command=refresh_match_preview).pack(side=tk.LEFT, padx=12)
        ttk.Button(batch_buttons, text="关闭", command=dlg.destroy).pack(side=tk.RIGHT, padx=2)

        refresh_global_list(initial_index)
        dlg.after_idle(lambda: _show_centered_window(dlg, win, 1120, 720))

    def manage_linked_rules(initial_index=None):
        sync_params_from_ui()
        cfg.setdefault("linked_rules", [])
        dlg = _make_floating_child(win, "联动写入规则窗口")
        body = ttk.Frame(dlg, padding=10)
        body.pack(fill=tk.BOTH, expand=True)
        body.columnconfigure(1, weight=3)
        body.columnconfigure(2, weight=2)
        body.rowconfigure(0, weight=1)

        left_panel = ttk.Frame(body)
        left_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        editor_outer = ttk.Frame(body)
        editor_outer.grid(row=0, column=1, sticky="nsew")
        editor_outer.rowconfigure(0, weight=1)
        editor_outer.columnconfigure(0, weight=1)
        editor_canvas = tk.Canvas(editor_outer, highlightthickness=0)
        editor_canvas.grid(row=0, column=0, sticky="nsew")
        editor_scroll = ttk.Scrollbar(editor_outer, orient=tk.VERTICAL, command=editor_canvas.yview)
        editor_scroll.grid(row=0, column=1, sticky="ns")
        editor_canvas.configure(yscrollcommand=editor_scroll.set)
        editor = ttk.Frame(editor_canvas)
        editor_window = editor_canvas.create_window((0, 0), window=editor, anchor="nw")
        editor.columnconfigure(0, minsize=120)
        editor.columnconfigure(1, weight=1, minsize=170)
        editor.columnconfigure(2, minsize=120)
        editor.columnconfigure(3, weight=1, minsize=170)

        def refresh_editor_scroll(_event=None):
            editor_canvas.configure(scrollregion=editor_canvas.bbox("all"))

        def resize_editor_width(event=None):
            if event is not None:
                editor_canvas.itemconfigure(editor_window, width=max(1, event.width))
            refresh_editor_scroll()

        editor.bind("<Configure>", refresh_editor_scroll)
        editor_canvas.bind("<Configure>", resize_editor_width)
        editor_canvas.bind("<MouseWheel>", lambda event: editor_canvas.yview_scroll((-1 if event.delta > 0 else 1) * 3, "units"))

        preview_panel = ttk.Frame(body)
        preview_panel.grid(row=0, column=2, sticky="nsew", padx=(8, 0))
        preview_panel.rowconfigure(1, weight=1)
        preview_panel.columnconfigure(0, weight=1)

        rule_list_frame, rule_list = _make_scrollable_listbox(left_panel, height=22, width=28, exportselection=False)
        rule_list_frame.pack(fill=tk.BOTH, expand=True)
        selected_idx = {"value": None}

        name_var = tk.StringVar(value="")
        enabled_var = tk.BooleanVar(value=True)
        trigger_var = tk.StringVar(value=LINKED_RULE_ANY)
        trigger_tags_var = tk.StringVar(value="")
        target_mode_var = tk.StringVar(value=LINK_TARGET_TRIGGER_OFFSET)
        sheet_var = tk.StringVar(value=SHEET_ALL_LABEL)
        row_offset_var = tk.StringVar(value="0")
        col_offset_var = tk.StringVar(value="0")
        row_index_var = tk.StringVar(value="")
        col_index_var = tk.StringVar(value="")
        target_match_enabled_var = tk.BooleanVar(value=False)
        target_match_mode_var = tk.StringVar(value="包含")
        target_match_value_var = tk.StringVar(value="")
        anchor_enabled_var = tk.BooleanVar(value=False)
        anchor_axis_var = tk.StringVar(value="列")
        anchor_index_var = tk.StringVar(value="1")
        anchor_match_mode_var = tk.StringVar(value="等于")
        anchor_value_var = tk.StringVar(value="")
        value_source_var = tk.StringVar(value=LINK_VALUE_TEMPLATE)
        fixed_value_var = tk.StringVar(value="")
        value_field_var = tk.StringVar(value="")
        value_template_var = tk.StringVar(value="{触发新值}")
        write_mode_var = tk.StringVar(value=LINK_WRITE_REPLACE)
        append_separator_var = tk.StringVar(value="")
        regex_pattern_var = tk.StringVar(value="")
        replace_count_var = tk.StringVar(value="0")
        case_sensitive_var = tk.BooleanVar(value=True)
        empty_policy_var = tk.StringVar(value="允许")
        area_enabled_var = tk.BooleanVar(value=False)
        area_row_start_var = tk.StringVar(value="0")
        area_row_end_var = tk.StringVar(value="0")
        area_col_start_var = tk.StringVar(value="0")
        area_col_end_var = tk.StringVar(value="0")
        area_write_col_var = tk.StringVar(value="0")
        marker_col_var = tk.StringVar(value="0")
        overflow_var = tk.StringVar(value=LINK_OVERFLOW_SKIP)
        overflow_target_mode_var = tk.StringVar(value="自动")
        overflow_fixed_row_var = tk.StringVar(value="")
        slot_mode_var = tk.StringVar(value=SLOT_MODE_SEQUENCE_DATE)
        slot_judgement_state = {"value": _default_slot_judgement()}
        actions_state = {"items": []}
        value_hint_var = tk.StringVar(value="")
        area_hint_var = tk.StringVar(value="")

        row = 0
        ttk.Label(editor, text="1. 基础与触发", foreground="#0f172a").grid(row=row, column=0, columnspan=4, sticky=tk.W, pady=(0, 3))
        row += 1
        ttk.Label(editor, text="规则名称：").grid(row=row, column=0, sticky=tk.W, pady=3)
        ttk.Entry(editor, textvariable=name_var, width=24).grid(row=row, column=1, sticky="ew", pady=3)
        ttk.Checkbutton(editor, text="启用", variable=enabled_var).grid(row=row, column=2, sticky=tk.W, padx=6)
        row += 1
        ttk.Label(editor, text="触发规则：").grid(row=row, column=0, sticky=tk.W, pady=3)
        trigger_combo = ttk.Combobox(editor, textvariable=trigger_var, values=[], width=28, state="readonly")
        trigger_combo.grid(row=row, column=1, columnspan=3, sticky="ew", pady=3)
        row += 1
        ttk.Label(editor, text="触发标签：").grid(row=row, column=0, sticky=tk.W, pady=3)
        ttk.Entry(editor, textvariable=trigger_tags_var, width=42).grid(row=row, column=1, columnspan=3, sticky="ew", pady=3)
        row += 1
        ttk.Label(
            editor,
            text="多个标签用逗号分隔；填写后优先按稳定标签触发，规则改名不影响。",
            foreground="gray",
        ).grid(row=row, column=1, columnspan=3, sticky=tk.W, pady=(0, 3))
        row += 1
        ttk.Separator(editor).grid(row=row, column=0, columnspan=4, sticky="ew", pady=8)
        row += 1
        ttk.Label(editor, text="2. 写到哪里", foreground="#0f172a").grid(row=row, column=0, columnspan=4, sticky=tk.W, pady=(0, 3))
        row += 1
        ttk.Label(editor, text="目标定位：").grid(row=row, column=0, sticky=tk.W, pady=3)
        target_mode_combo = ttk.Combobox(editor, textvariable=target_mode_var, values=LINK_TARGET_MODES, width=18, state="readonly")
        target_mode_combo.grid(row=row, column=1, sticky=tk.W, pady=3)
        ttk.Label(editor, text="表格/Sheet：").grid(row=row, column=2, sticky=tk.E, pady=3)
        sheet_combo = ttk.Combobox(editor, textvariable=sheet_var, values=[], width=22, state="normal")
        sheet_combo.grid(row=row, column=3, sticky="ew", pady=3)
        row += 1
        ttk.Label(editor, text="行偏移：").grid(row=row, column=0, sticky=tk.W, pady=3)
        row_offset_entry = ttk.Entry(editor, textvariable=row_offset_var, width=10)
        row_offset_entry.grid(row=row, column=1, sticky=tk.W, pady=3)
        ttk.Label(editor, text="列偏移：").grid(row=row, column=2, sticky=tk.E, pady=3)
        col_offset_entry = ttk.Entry(editor, textvariable=col_offset_var, width=10)
        col_offset_entry.grid(row=row, column=3, sticky=tk.W, pady=3)
        row += 1
        ttk.Label(editor, text="指定行：").grid(row=row, column=0, sticky=tk.W, pady=3)
        row_index_entry = ttk.Entry(editor, textvariable=row_index_var, width=10)
        row_index_entry.grid(row=row, column=1, sticky=tk.W, pady=3)
        ttk.Label(editor, text="指定列：").grid(row=row, column=2, sticky=tk.E, pady=3)
        col_index_entry = ttk.Entry(editor, textvariable=col_index_var, width=10)
        col_index_entry.grid(row=row, column=3, sticky=tk.W, pady=3)
        row += 1
        target_match_check = ttk.Checkbutton(editor, text="启用目标格匹配", variable=target_match_enabled_var)
        target_match_check.grid(row=row, column=0, sticky=tk.W, pady=3)
        target_match_combo = ttk.Combobox(editor, textvariable=target_match_mode_var, values=["包含", "等于", "不等于", "正则匹配", "正则不匹配", "为空", "非空"], width=16, state="readonly")
        target_match_combo.grid(row=row, column=1, sticky=tk.W, pady=3)
        target_match_entry = ttk.Entry(editor, textvariable=target_match_value_var, width=24)
        target_match_entry.grid(row=row, column=2, columnspan=2, sticky="ew", pady=3)
        row += 1
        ttk.Label(editor, text="锚点：").grid(row=row, column=0, sticky=tk.W, pady=3)
        anchor_enabled_check = ttk.Checkbutton(editor, text="启用", variable=anchor_enabled_var)
        anchor_enabled_check.grid(row=row, column=1, sticky=tk.W, pady=3)
        anchor_axis_combo = ttk.Combobox(editor, textvariable=anchor_axis_var, values=["列", "行"], width=8, state="readonly")
        anchor_axis_combo.grid(row=row, column=2, sticky=tk.E, pady=3)
        anchor_index_entry = ttk.Entry(editor, textvariable=anchor_index_var, width=10)
        anchor_index_entry.grid(row=row, column=3, sticky=tk.W, pady=3)
        row += 1
        ttk.Label(editor, text="锚点匹配：").grid(row=row, column=0, sticky=tk.W, pady=3)
        anchor_match_combo = ttk.Combobox(editor, textvariable=anchor_match_mode_var, values=["包含", "等于", "不等于", "正则匹配", "正则不匹配", "为空", "非空"], width=16, state="readonly")
        anchor_match_combo.grid(row=row, column=1, sticky=tk.W, pady=3)
        anchor_value_entry = ttk.Entry(editor, textvariable=anchor_value_var, width=24)
        anchor_value_entry.grid(row=row, column=2, columnspan=2, sticky="ew", pady=3)
        row += 1
        ttk.Separator(editor).grid(row=row, column=0, columnspan=4, sticky="ew", pady=8)
        row += 1
        ttk.Label(editor, text="3. 写入什么", foreground="#0f172a").grid(row=row, column=0, columnspan=4, sticky=tk.W, pady=(0, 3))
        row += 1
        ttk.Label(editor, text="写入来源：").grid(row=row, column=0, sticky=tk.W, pady=3)
        value_source_combo = ttk.Combobox(editor, textvariable=value_source_var, values=LINK_VALUE_SOURCES, width=18, state="readonly")
        value_source_combo.grid(row=row, column=1, sticky=tk.W, pady=3)
        ttk.Label(editor, text="新内容字段：").grid(row=row, column=2, sticky=tk.E, pady=3)
        value_field_combo = ttk.Combobox(editor, textvariable=value_field_var, values=[], width=22, state="normal")
        value_field_combo.grid(row=row, column=3, sticky="ew", pady=3)
        row += 1
        ttk.Label(editor, text="固定值：").grid(row=row, column=0, sticky=tk.W, pady=3)
        fixed_value_entry = ttk.Entry(editor, textvariable=fixed_value_var, width=24)
        fixed_value_entry.grid(row=row, column=1, sticky="ew", pady=3)
        ttk.Label(editor, text="空值策略：").grid(row=row, column=2, sticky=tk.E, pady=3)
        empty_policy_combo = ttk.Combobox(editor, textvariable=empty_policy_var, values=["允许", "跳过"], width=12, state="readonly")
        empty_policy_combo.grid(row=row, column=3, sticky=tk.W, pady=3)
        row += 1
        ttk.Label(editor, text="模板：").grid(row=row, column=0, sticky=tk.W, pady=3)
        value_template_entry = ttk.Entry(editor, textvariable=value_template_var, width=42)
        value_template_entry.grid(row=row, column=1, columnspan=3, sticky="ew", pady=3)
        row += 1
        template_button_frame = ttk.Frame(editor)
        template_button_frame.grid(row=row, column=1, columnspan=3, sticky=tk.W, pady=(0, 4))
        row += 1
        ttk.Separator(editor).grid(row=row, column=0, columnspan=4, sticky="ew", pady=8)
        row += 1
        ttk.Label(editor, text="4. 怎么写入", foreground="#0f172a").grid(row=row, column=0, columnspan=4, sticky=tk.W, pady=(0, 3))
        row += 1
        ttk.Label(editor, text="写入方式：").grid(row=row, column=0, sticky=tk.W, pady=3)
        write_mode_combo = ttk.Combobox(editor, textvariable=write_mode_var, values=LINK_WRITE_MODES, width=18, state="readonly")
        write_mode_combo.grid(row=row, column=1, sticky=tk.W, pady=3)
        row += 1
        ttk.Label(editor, textvariable=value_hint_var, foreground="gray").grid(row=row, column=0, columnspan=4, sticky=tk.W, pady=(0, 3))
        row += 1
        ttk.Label(editor, text="追加分隔：").grid(row=row, column=0, sticky=tk.W, pady=3)
        append_separator_entry = ttk.Entry(editor, textvariable=append_separator_var, width=10)
        append_separator_entry.grid(row=row, column=1, sticky=tk.W, pady=3)
        ttk.Label(editor, text="仅值追加/值前置时生效", foreground="gray").grid(row=row, column=2, columnspan=2, sticky=tk.W, pady=3)
        row += 1
        ttk.Label(editor, text="正则模式：").grid(row=row, column=0, sticky=tk.W, pady=3)
        regex_pattern_entry = ttk.Entry(editor, textvariable=regex_pattern_var, width=24)
        regex_pattern_entry.grid(row=row, column=1, sticky="ew", pady=3)
        ttk.Label(editor, text="替换次数(0=全部)：").grid(row=row, column=2, sticky=tk.E, pady=3)
        replace_count_entry = ttk.Entry(editor, textvariable=replace_count_var, width=10)
        replace_count_entry.grid(row=row, column=3, sticky=tk.W, pady=3)
        row += 1
        case_sensitive_check = ttk.Checkbutton(editor, text="正则区分大小写", variable=case_sensitive_var)
        case_sensitive_check.grid(row=row, column=1, columnspan=3, sticky=tk.W, pady=3)
        row += 1
        ttk.Label(
            editor,
            text="模板可用：触发值、统一序号、变更摘要、操作者和执行日期等；可用下方按钮插入。",
            foreground="gray",
        ).grid(row=row, column=0, columnspan=4, sticky=tk.W, pady=(0, 6))
        row += 1
        ttk.Separator(editor).grid(row=row, column=0, columnspan=4, sticky="ew", pady=8)
        row += 1
        ttk.Label(editor, text="5. 高级：区域槽位", foreground="#0f172a").grid(row=row, column=0, columnspan=4, sticky=tk.W, pady=(0, 3))
        row += 1
        area_enabled_check = ttk.Checkbutton(editor, text="启用区域槽位", variable=area_enabled_var)
        area_enabled_check.grid(row=row, column=0, sticky=tk.W, pady=3)
        ttk.Label(editor, text="满区策略：").grid(row=row, column=2, sticky=tk.E, pady=3)
        overflow_frame = ttk.Frame(editor)
        overflow_frame.grid(row=row, column=3, sticky="ew", pady=3)
        overflow_combo = ttk.Combobox(overflow_frame, textvariable=overflow_var, values=LINK_OVERFLOW_POLICIES, width=18, state="readonly")
        overflow_combo.pack(side=tk.LEFT)

        def open_overflow_target_dlg():
            dlg2 = _make_floating_child(dlg, "满区目标行设置")
            body = ttk.Frame(dlg2, padding=12)
            body.pack(fill=tk.BOTH, expand=True)
            mode_var = tk.StringVar(value=overflow_target_mode_var.get())
            row_var = tk.StringVar(value=overflow_fixed_row_var.get())
            ttk.Label(body, text="目标行模式：").grid(row=0, column=0, sticky=tk.W, pady=4)
            mode_combo = ttk.Combobox(body, textvariable=mode_var, values=["自动", "固定行号"], width=14, state="readonly")
            mode_combo.grid(row=0, column=1, sticky=tk.W, pady=4)
            ttk.Label(body, text="固定行号：").grid(row=1, column=0, sticky=tk.W, pady=4)
            row_entry = ttk.Entry(body, textvariable=row_var, width=10)
            row_entry.grid(row=1, column=1, sticky=tk.W, pady=4)

            def _sync_row_entry(*_):
                row_entry.configure(state="normal" if mode_var.get() == "固定行号" else "disabled")
            mode_var.trace_add("write", _sync_row_entry)
            _sync_row_entry()

            def on_ok():
                overflow_target_mode_var.set(mode_var.get())
                overflow_fixed_row_var.set(row_var.get())
                dlg2.destroy()

            btn_row = ttk.Frame(body)
            btn_row.grid(row=2, column=0, columnspan=2, pady=(10, 0))
            ttk.Button(btn_row, text="确定", command=on_ok).pack(side=tk.LEFT, padx=4)
            ttk.Button(btn_row, text="取消", command=dlg2.destroy).pack(side=tk.LEFT, padx=4)
            _show_centered_window(dlg2, dlg, 300, 160)

        ttk.Button(overflow_frame, text="目标行...", command=open_overflow_target_dlg).pack(side=tk.LEFT, padx=(4, 0))
        row += 1
        ttk.Label(editor, text="槽位判定：").grid(row=row, column=0, sticky=tk.W, pady=3)
        slot_mode_combo = ttk.Combobox(
            editor,
            textvariable=slot_mode_var,
            values=SLOT_JUDGEMENT_MODES,
            width=28,
            state="readonly",
        )
        slot_mode_combo.grid(row=row, column=1, columnspan=2, sticky="ew", pady=3)
        slot_rule_button = ttk.Button(
            editor,
            text="槽位判定规则...",
            command=lambda: open_slot_judgement_editor(),
        )
        slot_rule_button.grid(row=row, column=3, sticky=tk.W, pady=3)
        row += 1
        ttk.Label(editor, textvariable=area_hint_var, foreground="gray").grid(row=row, column=0, columnspan=4, sticky=tk.W, pady=(0, 3))
        row += 1
        ttk.Label(editor, text="区域起始/结束行偏移：").grid(row=row, column=0, sticky=tk.W, pady=3)
        area_row_start_entry = ttk.Entry(editor, textvariable=area_row_start_var, width=6)
        area_row_start_entry.grid(row=row, column=1, sticky=tk.W, pady=3)
        area_row_end_entry = ttk.Entry(editor, textvariable=area_row_end_var, width=6)
        area_row_end_entry.grid(row=row, column=1, sticky=tk.E, pady=3)
        ttk.Label(editor, text="区域起始/结束列偏移：").grid(row=row, column=2, sticky=tk.E, pady=3)
        area_col_start_entry = ttk.Entry(editor, textvariable=area_col_start_var, width=6)
        area_col_start_entry.grid(row=row, column=3, sticky=tk.W, pady=3)
        area_col_end_entry = ttk.Entry(editor, textvariable=area_col_end_var, width=6)
        area_col_end_entry.grid(row=row, column=3, sticky=tk.E, pady=3)
        row += 1
        ttk.Label(editor, text="写入列偏移：").grid(row=row, column=0, sticky=tk.W, pady=3)
        area_write_col_entry = ttk.Entry(editor, textvariable=area_write_col_var, width=10)
        area_write_col_entry.grid(row=row, column=1, sticky=tk.W, pady=3)
        ttk.Label(editor, text="圈号列偏移：").grid(row=row, column=2, sticky=tk.E, pady=3)
        marker_col_entry = ttk.Entry(editor, textvariable=marker_col_var, width=10)
        marker_col_entry.grid(row=row, column=3, sticky=tk.W, pady=3)
        row += 1
        ttk.Separator(editor).grid(row=row, column=0, columnspan=4, sticky="ew", pady=8)
        row += 1
        ttk.Label(editor, text="6. 方案动作", foreground="#0f172a").grid(row=row, column=0, columnspan=4, sticky=tk.W, pady=(0, 3))
        row += 1
        action_tree = ttk.Treeview(
            editor,
            columns=("name", "target", "offset", "value"),
            show="headings",
            height=6,
        )
        for col, label, width in (
            ("name", "动作", 120),
            ("target", "目标", 110),
            ("offset", "偏移", 80),
            ("value", "写入内容", 260),
        ):
            action_tree.heading(col, text=label)
            action_tree.column(col, width=width, anchor=tk.W)
        action_tree.grid(row=row, column=0, columnspan=4, sticky="nsew", pady=3)
        row += 1
        action_buttons = ttk.Frame(editor)
        action_buttons.grid(row=row, column=0, columnspan=4, sticky=tk.E, pady=(0, 4))
        ttk.Button(action_buttons, text="增加动作", command=lambda: open_action_editor()).pack(side=tk.LEFT, padx=2)
        ttk.Button(action_buttons, text="编辑动作", command=lambda: edit_selected_action()).pack(side=tk.LEFT, padx=2)
        ttk.Button(action_buttons, text="删除动作", command=lambda: delete_selected_action()).pack(side=tk.LEFT, padx=2)
        ttk.Button(action_buttons, text="上移", command=lambda: move_selected_action(-1)).pack(side=tk.LEFT, padx=2)
        ttk.Button(action_buttons, text="下移", command=lambda: move_selected_action(1)).pack(side=tk.LEFT, padx=2)

        def open_slot_judgement_editor():
            slot_cfg = _ensure_slot_judgement(slot_judgement_state.get("value"))
            dlg2 = _make_floating_child(dlg, "槽位判定规则")
            body2 = ttk.Frame(dlg2, padding=10)
            body2.pack(fill=tk.BOTH, expand=True)
            body2.columnconfigure(0, weight=1)
            body2.rowconfigure(1, weight=1)

            general = ttk.Frame(body2)
            general.grid(row=0, column=0, sticky="ew", pady=(0, 8))
            mode_var = tk.StringVar(value=slot_mode_var.get() or slot_cfg.get("mode", SLOT_MODE_SEQUENCE_DATE))
            sequence_start_var = tk.StringVar(value=_as_text(slot_cfg.get("sequence_start", 1)))
            sequence_col_var = tk.StringVar(value=_as_text(slot_cfg.get("sequence_col_offset", 0)))
            date_col_var = tk.StringVar(value=_as_text(slot_cfg.get("date_col_offset", 0)))
            group_var = tk.StringVar(value=_as_text(slot_cfg.get("sequence_group") or "文档统一序号"))
            invalid_var = tk.StringVar(value=_as_text(slot_cfg.get("invalid_policy") or SLOT_INVALID_SKIP))
            ttk.Label(general, text="判定方式：").grid(row=0, column=0, sticky=tk.W, padx=3, pady=3)
            ttk.Combobox(general, textvariable=mode_var, values=SLOT_JUDGEMENT_MODES, width=30, state="readonly").grid(row=0, column=1, sticky=tk.W, padx=3)
            ttk.Label(general, text="无有效值：").grid(row=0, column=2, sticky=tk.E, padx=3)
            ttk.Combobox(general, textvariable=invalid_var, values=SLOT_INVALID_POLICIES, width=14, state="readonly").grid(row=0, column=3, sticky=tk.W, padx=3)
            ttk.Label(general, text="首个分配序号：").grid(row=1, column=0, sticky=tk.W, padx=3, pady=3)
            ttk.Entry(general, textvariable=sequence_start_var, width=8).grid(row=1, column=1, sticky=tk.W, padx=3)
            ttk.Label(general, text="序号列偏移：").grid(row=1, column=2, sticky=tk.E, padx=3)
            ttk.Entry(general, textvariable=sequence_col_var, width=8).grid(row=1, column=3, sticky=tk.W, padx=3)
            ttk.Label(general, text="序号分组：").grid(row=2, column=0, sticky=tk.W, padx=3, pady=3)
            ttk.Entry(general, textvariable=group_var, width=24).grid(row=2, column=1, sticky="ew", padx=3)
            ttk.Label(general, text="日期列偏移：").grid(row=2, column=2, sticky=tk.E, padx=3)
            ttk.Entry(general, textvariable=date_col_var, width=8).grid(row=2, column=3, sticky=tk.W, padx=3)
            general.columnconfigure(1, weight=1)

            notebook = ttk.Notebook(body2)
            notebook.grid(row=1, column=0, sticky="nsew")
            sequence_page = ttk.Frame(notebook, padding=8)
            date_page = ttk.Frame(notebook, padding=8)
            notebook.add(sequence_page, text="序号规则")
            notebook.add(date_page, text="日期规则")

            sequence_page.rowconfigure(0, weight=1)
            sequence_page.columnconfigure(0, weight=1)
            sequence_tree = ttk.Treeview(
                sequence_page,
                columns=("index", "symbol"),
                show="headings",
                height=18,
            )
            sequence_tree.heading("index", text="自然序号")
            sequence_tree.heading("symbol", text="特殊字符")
            sequence_tree.column("index", width=100, anchor=tk.CENTER, stretch=False)
            sequence_tree.column("symbol", width=180, anchor=tk.CENTER)
            sequence_tree.grid(row=0, column=0, sticky="nsew")
            seq_scroll = ttk.Scrollbar(sequence_page, orient=tk.VERTICAL, command=sequence_tree.yview)
            seq_scroll.grid(row=0, column=1, sticky="ns")
            sequence_tree.configure(yscrollcommand=seq_scroll.set)
            symbol_var = tk.StringVar(value="")
            seq_buttons = ttk.Frame(sequence_page)
            seq_buttons.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(6, 0))
            ttk.Label(seq_buttons, text="特殊字符：").pack(side=tk.LEFT)
            ttk.Entry(seq_buttons, textvariable=symbol_var, width=12).pack(side=tk.LEFT, padx=4)

            def reload_sequence_tree():
                sequence_tree.delete(*sequence_tree.get_children())
                for item in sorted(slot_cfg.get("sequence_symbols") or [], key=lambda value: _to_int(value.get("index"), 0)):
                    sequence_tree.insert("", tk.END, values=(_to_int(item.get("index"), 0), _cell_text(item.get("symbol", ""))))

            def select_sequence(_event=None):
                selected = sequence_tree.selection()
                if selected:
                    symbol_var.set(_cell_text(sequence_tree.item(selected[0], "values")[1]))

            def update_sequence():
                selected = sequence_tree.selection()
                if not selected:
                    return
                index = _to_int(sequence_tree.item(selected[0], "values")[0], 0)
                symbol = symbol_var.get()
                for item in slot_cfg.get("sequence_symbols") or []:
                    if _to_int(item.get("index"), -1) == index:
                        item["symbol"] = symbol
                        break
                reload_sequence_tree()

            def restore_sequence():
                slot_cfg["sequence_symbols"] = _default_sequence_symbols()
                reload_sequence_tree()

            ttk.Button(seq_buttons, text="更新字符", command=update_sequence).pack(side=tk.LEFT, padx=3)
            ttk.Button(seq_buttons, text="恢复默认圈号", command=restore_sequence).pack(side=tk.LEFT, padx=3)
            sequence_tree.bind("<<TreeviewSelect>>", select_sequence)
            reload_sequence_tree()

            date_page.columnconfigure(1, weight=1)
            date_page.rowconfigure(0, weight=1)
            preset_frame, preset_list = _make_scrollable_listbox(date_page, height=16, width=22, exportselection=False)
            preset_frame.grid(row=0, column=0, rowspan=12, sticky="nsew", padx=(0, 8))
            date_editor = ttk.Frame(date_page)
            date_editor.grid(row=0, column=1, sticky="nsew")
            date_editor.columnconfigure(1, weight=1)
            preset_name_var = tk.StringVar(value="")
            structure_var = tk.StringVar(value="自动识别常见格式")
            delimiter_var = tk.StringVar(value="自动识别")
            custom_delimiter_var = tk.StringVar(value="-")
            order_var = tk.StringVar(value="年-月-日")
            year_rule_var = tk.StringVar(value="20xx")
            pivot_var = tk.StringVar(value="80")
            position_base_var = tk.StringVar(value="从1开始")
            year_start_var = tk.StringVar(value="1")
            year_len_var = tk.StringVar(value="2")
            month_start_var = tk.StringVar(value="3")
            month_len_var = tk.StringVar(value="2")
            day_start_var = tk.StringVar(value="5")
            day_len_var = tk.StringVar(value="2")
            test_text_var = tk.StringVar(value="2026-06-13")
            test_result_var = tk.StringVar(value="")

            date_fields = [
                ("预设名称：", preset_name_var, None),
                ("输入结构：", structure_var, DATE_INPUT_STRUCTURES),
                ("日期分隔符：", delimiter_var, ["自动识别", "-", "/", ".", "年/月/日", "自定义"]),
                ("自定义分隔符：", custom_delimiter_var, None),
                ("日期顺序：", order_var, DATE_ORDERS),
                ("两位年份：", year_rule_var, DATE_YEAR_RULES),
                ("自动窗口分界：", pivot_var, None),
                ("位置规则：", position_base_var, ["从1开始", "从0开始"]),
            ]
            for field_row, (label, variable, choices) in enumerate(date_fields):
                ttk.Label(date_editor, text=label).grid(row=field_row, column=0, sticky=tk.W, pady=3)
                if choices:
                    ttk.Combobox(date_editor, textvariable=variable, values=choices, state="readonly", width=22).grid(row=field_row, column=1, sticky="ew", pady=3)
                else:
                    ttk.Entry(date_editor, textvariable=variable, width=24).grid(row=field_row, column=1, sticky="ew", pady=3)
            position_frame = ttk.Frame(date_editor)
            position_frame.grid(row=8, column=0, columnspan=2, sticky="ew", pady=4)
            for index, (label, variable) in enumerate((
                ("年起始", year_start_var), ("年长度", year_len_var),
                ("月起始", month_start_var), ("月长度", month_len_var),
                ("日起始", day_start_var), ("日长度", day_len_var),
            )):
                ttk.Label(position_frame, text=label).grid(row=index // 3 * 2, column=index % 3, sticky=tk.W, padx=3)
                ttk.Entry(position_frame, textvariable=variable, width=7).grid(row=index // 3 * 2 + 1, column=index % 3, sticky=tk.W, padx=3)
            ttk.Label(date_editor, text="测试文本：").grid(row=9, column=0, sticky=tk.W, pady=3)
            ttk.Entry(date_editor, textvariable=test_text_var).grid(row=9, column=1, sticky="ew", pady=3)
            ttk.Label(date_editor, textvariable=test_result_var, foreground="gray").grid(row=10, column=0, columnspan=2, sticky=tk.W, pady=3)
            selected_preset = {"index": None}

            def date_config_from_editor():
                config = default_date_parser_config()
                config.update({
                    "input_structure": structure_var.get(),
                    "date_delimiter": delimiter_var.get(),
                    "custom_date_delimiter": custom_delimiter_var.get(),
                    "date_order": order_var.get(),
                    "year_rule": year_rule_var.get(),
                    "auto_window_pivot": pivot_var.get(),
                    "position_base": position_base_var.get(),
                    "year_start": year_start_var.get(),
                    "year_len": year_len_var.get(),
                    "month_start": month_start_var.get(),
                    "month_len": month_len_var.get(),
                    "day_start": day_start_var.get(),
                    "day_len": day_len_var.get(),
                })
                return config

            def load_date_config(config):
                config = dict(default_date_parser_config(), **(config or {}))
                structure_var.set(config["input_structure"])
                delimiter_var.set(config["date_delimiter"])
                custom_delimiter_var.set(config["custom_date_delimiter"])
                order_var.set(config["date_order"])
                year_rule_var.set(config["year_rule"])
                pivot_var.set(_as_text(config["auto_window_pivot"]))
                position_base_var.set(config["position_base"])
                year_start_var.set(_as_text(config["year_start"]))
                year_len_var.set(_as_text(config["year_len"]))
                month_start_var.set(_as_text(config["month_start"]))
                month_len_var.set(_as_text(config["month_len"]))
                day_start_var.set(_as_text(config["day_start"]))
                day_len_var.set(_as_text(config["day_len"]))

            def reload_presets(select_index=None):
                preset_list.delete(0, tk.END)
                presets = slot_cfg.get("date_presets") or []
                for preset in presets:
                    preset_list.insert(tk.END, _as_text(preset.get("name")) or "未命名")
                if presets:
                    index = 0 if select_index is None else max(0, min(select_index, len(presets) - 1))
                    preset_list.selection_set(index)
                    selected_preset["index"] = index
                    preset_name_var.set(_as_text(presets[index].get("name")))
                    load_date_config(presets[index].get("config"))

            def on_preset_select(_event=None):
                selected = preset_list.curselection()
                if not selected:
                    return
                index = int(selected[0])
                selected_preset["index"] = index
                preset = slot_cfg["date_presets"][index]
                preset_name_var.set(_as_text(preset.get("name")))
                load_date_config(preset.get("config"))

            def save_preset():
                index = selected_preset.get("index")
                if index is None:
                    return
                slot_cfg["date_presets"][index] = {
                    "name": _as_text(preset_name_var.get()) or "未命名",
                    "config": date_config_from_editor(),
                }
                slot_cfg["active_date_preset"] = slot_cfg["date_presets"][index]["name"]
                slot_cfg["date_parser"] = copy.deepcopy(slot_cfg["date_presets"][index]["config"])
                reload_presets(index)

            def add_preset():
                slot_cfg.setdefault("date_presets", []).append({
                    "name": "新日期预设",
                    "config": default_date_parser_config(),
                })
                reload_presets(len(slot_cfg["date_presets"]) - 1)

            def delete_preset():
                index = selected_preset.get("index")
                if index is None or len(slot_cfg.get("date_presets") or []) <= 1:
                    return
                slot_cfg["date_presets"].pop(index)
                reload_presets(max(0, index - 1))

            def test_date_parser():
                try:
                    result = parse_date_value(test_text_var.get(), date_config_from_editor())
                    test_result_var.set(f"解析结果：{result[0]:04d}-{result[1]:02d}-{result[2]:02d}")
                except Exception as exc:
                    test_result_var.set(f"解析失败：{exc}")

            preset_list.bind("<<ListboxSelect>>", on_preset_select)
            preset_buttons = ttk.Frame(date_page)
            preset_buttons.grid(row=12, column=0, sticky="ew", pady=(6, 0))
            ttk.Button(preset_buttons, text="增加", command=add_preset).pack(side=tk.LEFT, padx=2)
            ttk.Button(preset_buttons, text="删除", command=delete_preset).pack(side=tk.LEFT, padx=2)
            editor_buttons = ttk.Frame(date_editor)
            editor_buttons.grid(row=11, column=0, columnspan=2, sticky=tk.E, pady=(6, 0))
            ttk.Button(editor_buttons, text="测试解析", command=test_date_parser).pack(side=tk.LEFT, padx=2)
            ttk.Button(editor_buttons, text="保存预设", command=save_preset).pack(side=tk.LEFT, padx=2)
            reload_presets()

            def save_slot_rules():
                preset_index = selected_preset.get("index")
                presets = slot_cfg.get("date_presets") or []
                if preset_index is not None and 0 <= preset_index < len(presets):
                    presets[preset_index] = {
                        "name": _as_text(preset_name_var.get()) or "未命名",
                        "config": date_config_from_editor(),
                    }
                    slot_cfg["active_date_preset"] = presets[preset_index]["name"]
                    slot_cfg["date_parser"] = copy.deepcopy(presets[preset_index]["config"])
                slot_cfg["mode"] = mode_var.get() or SLOT_MODE_SEQUENCE_DATE
                slot_cfg["sequence_start"] = max(0, _to_int(sequence_start_var.get(), 1))
                slot_cfg["sequence_col_offset"] = _to_int(sequence_col_var.get(), 0)
                slot_cfg["date_col_offset"] = _to_int(date_col_var.get(), 0)
                slot_cfg["sequence_group"] = _as_text(group_var.get()) or "文档统一序号"
                slot_cfg["invalid_policy"] = invalid_var.get() or SLOT_INVALID_SKIP
                slot_mode_var.set(slot_cfg["mode"])
                slot_judgement_state["value"] = _ensure_slot_judgement(slot_cfg)
                dlg2.destroy()

            bottom2 = ttk.Frame(body2)
            bottom2.grid(row=2, column=0, sticky=tk.E, pady=(8, 0))
            ttk.Button(bottom2, text="确定", command=save_slot_rules).pack(side=tk.LEFT, padx=3)
            ttk.Button(bottom2, text="取消", command=dlg2.destroy).pack(side=tk.LEFT, padx=3)
            dlg2.after_idle(lambda: _show_centered_window(dlg2, dlg, 900, 680))

        def action_value_label(action):
            source = _as_text(action.get("value_source") or LINK_VALUE_TEMPLATE)
            if source == LINK_VALUE_TEMPLATE:
                return _cell_text(action.get("value_template", ""))
            if source == LINK_VALUE_CONTENT_FIELD:
                return f"字段:{_as_text(action.get('value_field'))}"
            if source == LINK_VALUE_FIXED:
                return _cell_text(action.get("fixed_value", ""))
            return source

        def refresh_action_tree(select_index=None):
            action_tree.delete(*action_tree.get_children())
            for index, action in enumerate(actions_state.get("items") or []):
                action_tree.insert("", tk.END, iid=str(index), values=(
                    _as_text(action.get("name")) or f"动作{index + 1}",
                    _as_text(action.get("target_mode") or LINK_ACTION_SHARED_SLOT),
                    f"R{_to_int(action.get('row_offset'), 0):+d} C{_to_int(action.get('col_offset'), 0):+d}",
                    action_value_label(action),
                ))
            if select_index is not None and str(select_index) in action_tree.get_children():
                action_tree.selection_set(str(select_index))
                action_tree.see(str(select_index))

        def selected_action_index():
            selected = action_tree.selection()
            return _to_int(selected[0], -1) if selected else -1

        def open_action_editor(index=None):
            current = {}
            if index is not None and 0 <= index < len(actions_state.get("items") or []):
                current = copy.deepcopy(actions_state["items"][index])
            dlg2 = _make_floating_child(dlg, "编辑联动动作")
            form = ttk.Frame(dlg2, padding=12)
            form.pack(fill=tk.BOTH, expand=True)
            form.columnconfigure(1, weight=1)
            name = tk.StringVar(value=_as_text(current.get("name")) or "新动作")
            enabled = tk.BooleanVar(value=bool(current.get("enabled", True)))
            target_mode = tk.StringVar(value=_as_text(current.get("target_mode") or LINK_ACTION_SHARED_SLOT))
            row_offset = tk.StringVar(value=_as_text(current.get("row_offset") or "0"))
            col_offset = tk.StringVar(value=_as_text(current.get("col_offset") or "0"))
            value_source = tk.StringVar(value=_as_text(current.get("value_source") or LINK_VALUE_TEMPLATE))
            fixed_value = tk.StringVar(value=_cell_text(current.get("fixed_value", "")))
            value_field = tk.StringVar(value=_as_text(current.get("value_field")))
            value_template = tk.StringVar(value=_cell_text(current.get("value_template", "{触发新值}")))
            write_mode = tk.StringVar(value=_as_text(current.get("write_mode") or LINK_WRITE_REPLACE))
            empty_policy = tk.StringVar(value=_as_text(current.get("empty_policy") or "允许"))
            fields = [
                ("动作名称：", ttk.Entry(form, textvariable=name)),
                ("目标方式：", ttk.Combobox(form, textvariable=target_mode, values=LINK_ACTION_TARGET_MODES, state="readonly")),
                ("行偏移：", ttk.Entry(form, textvariable=row_offset)),
                ("列偏移：", ttk.Entry(form, textvariable=col_offset)),
                ("写入来源：", ttk.Combobox(form, textvariable=value_source, values=LINK_VALUE_SOURCES, state="readonly")),
                ("固定值：", ttk.Entry(form, textvariable=fixed_value)),
                ("新内容字段：", ttk.Combobox(form, textvariable=value_field, values=current_content_fields(), state="normal")),
                ("模板：", ttk.Entry(form, textvariable=value_template)),
                ("写入方式：", ttk.Combobox(form, textvariable=write_mode, values=LINK_WRITE_MODES, state="readonly")),
                ("空值策略：", ttk.Combobox(form, textvariable=empty_policy, values=["允许", "跳过"], state="readonly")),
            ]
            for field_row, (label, widget) in enumerate(fields):
                ttk.Label(form, text=label).grid(row=field_row, column=0, sticky=tk.W, pady=3)
                widget.grid(row=field_row, column=1, sticky="ew", pady=3)
            ttk.Checkbutton(form, text="启用动作", variable=enabled).grid(row=len(fields), column=1, sticky=tk.W, pady=3)
            ttk.Label(
                form,
                text="模板可用：{统一序号} {旧值} {新值} {变更字段} {变更摘要} {操作者} {执行日期}",
                foreground="gray",
            ).grid(row=len(fields) + 1, column=0, columnspan=2, sticky=tk.W, pady=3)

            def save_action():
                payload = {
                    "name": _as_text(name.get()) or "未命名动作",
                    "enabled": bool(enabled.get()),
                    "target_mode": target_mode.get() or LINK_ACTION_SHARED_SLOT,
                    "row_offset": _as_text(row_offset.get()) or "0",
                    "col_offset": _as_text(col_offset.get()) or "0",
                    "value_source": value_source.get() or LINK_VALUE_TEMPLATE,
                    "fixed_value": fixed_value.get(),
                    "value_field": _as_text(value_field.get()),
                    "value_template": value_template.get(),
                    "write_mode": write_mode.get() or LINK_WRITE_REPLACE,
                    "empty_policy": empty_policy.get() or "允许",
                }
                if index is None:
                    actions_state.setdefault("items", []).append(payload)
                    selected = len(actions_state["items"]) - 1
                else:
                    actions_state["items"][index] = payload
                    selected = index
                refresh_action_tree(selected)
                dlg2.destroy()

            buttons = ttk.Frame(form)
            buttons.grid(row=len(fields) + 2, column=0, columnspan=2, sticky=tk.E, pady=(8, 0))
            ttk.Button(buttons, text="确定", command=save_action).pack(side=tk.LEFT, padx=3)
            ttk.Button(buttons, text="取消", command=dlg2.destroy).pack(side=tk.LEFT, padx=3)
            dlg2.after_idle(lambda: _show_centered_window(dlg2, dlg, 620, 520))

        def edit_selected_action():
            index = selected_action_index()
            if index >= 0:
                open_action_editor(index)

        def delete_selected_action():
            index = selected_action_index()
            if index < 0:
                return
            actions_state["items"].pop(index)
            refresh_action_tree(max(0, index - 1) if actions_state["items"] else None)

        def move_selected_action(delta):
            index = selected_action_index()
            target = index + delta
            if index < 0 or target < 0 or target >= len(actions_state.get("items") or []):
                return
            items = actions_state["items"]
            items[index], items[target] = items[target], items[index]
            refresh_action_tree(target)

        def set_control_enabled(widget, enabled=True, readonly=False):
            try:
                if isinstance(widget, ttk.Combobox):
                    widget.configure(state="readonly" if enabled and readonly else ("normal" if enabled else "disabled"))
                else:
                    widget.configure(state="normal" if enabled else "disabled")
            except Exception:
                pass

        def set_controls_enabled(widgets, enabled=True, readonly=False):
            for widget in widgets:
                set_control_enabled(widget, enabled, readonly=readonly)

        def insert_template_token(token):
            try:
                value_template_entry.insert(value_template_entry.index(tk.INSERT), token)
                value_template_var.set(value_template_entry.get())
                value_template_entry.focus_set()
            except Exception:
                value_template_var.set(_cell_text(value_template_var.get()) + token)

        template_buttons = []
        for token_index, token in enumerate([
            "{触发新值}",
            "{原文}",
            "{统一序号}",
            "{变更摘要}",
            "{操作者}",
            "{执行日期}",
            "{圈号}",
        ]):
            btn = ttk.Button(template_button_frame, text=token, width=max(8, len(token) + 2), command=lambda t=token: insert_template_token(t))
            btn.grid(row=token_index // 4, column=token_index % 4, sticky=tk.W, padx=(0, 4), pady=1)
            template_buttons.append(btn)

        def update_linked_field_states(*_args):
            target_mode = _as_text(target_mode_var.get()) or LINK_TARGET_TRIGGER_OFFSET
            value_source = _as_text(value_source_var.get()) or LINK_VALUE_FIXED
            write_mode = _as_text(write_mode_var.get()) or LINK_WRITE_REPLACE
            area_enabled = bool(area_enabled_var.get())
            use_target_match = bool(target_match_enabled_var.get())
            overflow_policy = _as_text(overflow_var.get())
            use_legacy_marker = area_enabled and overflow_policy in (
                LINK_OVERFLOW_MIN_MARKER_ROW,
                LINK_OVERFLOW_MIN_DATE_ROW,
            )
            use_slot_rule = area_enabled and overflow_policy == LINK_OVERFLOW_SLOT_RULE

            is_fixed_target = target_mode == LINK_TARGET_FIXED_CELL
            is_anchor_target = target_mode == LINK_TARGET_ANCHOR_OFFSET
            set_controls_enabled([row_offset_entry, col_offset_entry], not is_fixed_target)
            set_controls_enabled([row_index_entry, col_index_entry], is_fixed_target)
            set_controls_enabled([anchor_enabled_check, anchor_axis_combo, anchor_index_entry, anchor_match_combo, anchor_value_entry], is_anchor_target, readonly=True)

            set_controls_enabled([target_match_combo, target_match_entry], use_target_match, readonly=True)

            set_control_enabled(fixed_value_entry, value_source == LINK_VALUE_FIXED)
            set_control_enabled(value_field_combo, value_source == LINK_VALUE_CONTENT_FIELD)
            set_control_enabled(value_template_entry, value_source == LINK_VALUE_TEMPLATE)
            set_controls_enabled(template_buttons, value_source == LINK_VALUE_TEMPLATE)

            set_control_enabled(append_separator_entry, write_mode in (LINK_WRITE_APPEND, LINK_WRITE_PREPEND))
            set_controls_enabled([regex_pattern_entry, replace_count_entry, case_sensitive_check], write_mode == LINK_WRITE_REGEX)

            set_control_enabled(overflow_combo, area_enabled, readonly=True)
            set_control_enabled(slot_mode_combo, use_slot_rule, readonly=True)
            set_control_enabled(slot_rule_button, use_slot_rule)
            set_controls_enabled(
                [area_row_start_entry, area_row_end_entry, area_col_start_entry, area_col_end_entry],
                area_enabled,
            )
            set_control_enabled(area_write_col_entry, area_enabled)
            set_control_enabled(marker_col_entry, use_legacy_marker)

            inactive = []
            if write_mode not in (LINK_WRITE_APPEND, LINK_WRITE_PREPEND):
                inactive.append("追加分隔不生效")
            if write_mode != LINK_WRITE_REGEX:
                inactive.append("正则参数不生效")
            value_hint_var.set(f"当前生效：{value_source} + {write_mode}" + (f"；{'; '.join(inactive)}" if inactive else ""))
            if area_enabled:
                if use_slot_rule:
                    area_hint_var.set("区域启用：先预留第一个空行；满区时按槽位判定规则选择替换行。")
                elif use_legacy_marker:
                    area_hint_var.set("区域启用：使用兼容满区策略；圈号/日期读取列由“圈号列偏移”指定。")
                else:
                    area_hint_var.set("区域启用：本次计划共享槽位状态，已分配行不会被后续事件重复占用。")
            else:
                area_hint_var.set("区域槽位未启用：下方区域参数不会参与计算。")

        for watched_var in (
            target_mode_var,
            target_match_enabled_var,
            value_source_var,
            write_mode_var,
            area_enabled_var,
            overflow_var,
            slot_mode_var,
        ):
            try:
                watched_var.trace_add("write", update_linked_field_states)
            except Exception:
                pass

        ttk.Label(preview_panel, text="联动预览").grid(row=0, column=0, sticky=tk.W, pady=(0, 4))
        preview_text = tk.Text(preview_panel, height=30, width=42, wrap=tk.WORD)
        preview_text.grid(row=1, column=0, sticky="nsew")
        preview_scroll = ttk.Scrollbar(preview_panel, orient=tk.VERTICAL, command=preview_text.yview)
        preview_scroll.grid(row=1, column=1, sticky="ns")
        preview_text.configure(yscrollcommand=preview_scroll.set)
        preview_status_var = tk.StringVar(value="未刷新")
        ttk.Label(preview_panel, textvariable=preview_status_var, foreground="gray").grid(row=2, column=0, columnspan=2, sticky=tk.W, pady=(4, 0))

        def linked_label(rule):
            prefix = "" if rule.get("enabled", True) else "[停用] "
            return f"{prefix}{_as_text(rule.get('name')) or '未命名'} <= {_as_text(rule.get('trigger_rule') or LINKED_RULE_ANY)}"

        def build_rule_from_editor():
            return {
                "name": _as_text(name_var.get()) or "未命名联动规则",
                "enabled": bool(enabled_var.get()),
                "trigger_rule": _as_text(trigger_var.get()) or LINKED_RULE_ANY,
                "trigger_tags": _normalize_event_tags(trigger_tags_var.get()),
                "target_mode": _as_text(target_mode_var.get()) or LINK_TARGET_TRIGGER_OFFSET,
                "sheet_name": _cfg_sheet_name(sheet_var.get()),
                "row_offset": _as_text(row_offset_var.get()) or "0",
                "col_offset": _as_text(col_offset_var.get()) or "0",
                "row_index": _as_text(row_index_var.get()),
                "col_index": _as_text(col_index_var.get()),
                "target_match": {
                    "enabled": bool(target_match_enabled_var.get()),
                    "mode": _as_text(target_match_mode_var.get()) or "包含",
                    "value": _as_text(target_match_value_var.get()),
                },
                "anchor": {
                    "enabled": bool(anchor_enabled_var.get()),
                    "axis": _as_text(anchor_axis_var.get()) or "列",
                    "index": _as_text(anchor_index_var.get()) or "1",
                    "match_mode": _as_text(anchor_match_mode_var.get()) or "等于",
                    "value": _as_text(anchor_value_var.get()),
                },
                "value_source": _as_text(value_source_var.get()) or LINK_VALUE_FIXED,
                "fixed_value": fixed_value_var.get(),
                "value_field": _as_text(value_field_var.get()),
                "value_template": value_template_var.get(),
                "write_mode": _as_text(write_mode_var.get()) or LINK_WRITE_REPLACE,
                "append_separator": append_separator_var.get(),
                "regex_pattern": regex_pattern_var.get(),
                "replace_count": _as_text(replace_count_var.get()) or "0",
                "case_sensitive": bool(case_sensitive_var.get()),
                "empty_policy": _as_text(empty_policy_var.get()) or "允许",
                "area_enabled": bool(area_enabled_var.get()),
                "area_row_start_offset": _as_text(area_row_start_var.get()) or "0",
                "area_row_end_offset": _as_text(area_row_end_var.get()) or "0",
                "area_col_start_offset": _as_text(area_col_start_var.get()) or "0",
                "area_col_end_offset": _as_text(area_col_end_var.get()) or "0",
                "area_write_col_offset": _as_text(area_write_col_var.get()) or "0",
                "marker_col_offset": _as_text(marker_col_var.get()) or "0",
                "overflow_policy": _as_text(overflow_var.get()) or LINK_OVERFLOW_SKIP,
                "overflow_target_mode": _as_text(overflow_target_mode_var.get()) or "自动",
                "overflow_fixed_row": _as_text(overflow_fixed_row_var.get()) or "",
                "slot_judgement": dict(
                    _ensure_slot_judgement(slot_judgement_state.get("value")),
                    mode=_as_text(slot_mode_var.get()) or SLOT_MODE_SEQUENCE_DATE,
                ),
                "actions": copy.deepcopy(actions_state.get("items") or []),
            }

        def load_rule(index):
            if index is None or index < 0 or index >= len(cfg.get("linked_rules", [])):
                selected_idx["value"] = None
                return
            selected_idx["value"] = index
            rule = cfg["linked_rules"][index]
            name_var.set(_as_text(rule.get("name")))
            enabled_var.set(bool(rule.get("enabled", True)))
            trigger_var.set(_as_text(rule.get("trigger_rule") or LINKED_RULE_ANY))
            trigger_tags_var.set("，".join(_normalize_event_tags(rule.get("trigger_tags"))))
            target_mode_var.set(_as_text(rule.get("target_mode") or LINK_TARGET_TRIGGER_OFFSET))
            sheet_var.set(_ui_sheet_name(rule.get("sheet_name", "")))
            row_offset_var.set(_as_text(rule.get("row_offset") or "0"))
            col_offset_var.set(_as_text(rule.get("col_offset") or "0"))
            row_index_var.set(_as_text(rule.get("row_index")))
            col_index_var.set(_as_text(rule.get("col_index")))
            target_match = rule.get("target_match") or {}
            target_match_enabled_var.set(bool(target_match.get("enabled", False)))
            target_match_mode_var.set(_as_text(target_match.get("mode") or "包含"))
            target_match_value_var.set(_as_text(target_match.get("value")))
            anchor = rule.get("anchor") or {}
            anchor_enabled_var.set(bool(anchor.get("enabled", False)))
            anchor_axis_var.set(_as_text(anchor.get("axis") or "列"))
            anchor_index_var.set(_as_text(anchor.get("index") or "1"))
            anchor_match_mode_var.set(_as_text(anchor.get("match_mode") or "等于"))
            anchor_value_var.set(_as_text(anchor.get("value")))
            value_source_var.set(_as_text(rule.get("value_source") or LINK_VALUE_FIXED))
            fixed_value_var.set(_cell_text(rule.get("fixed_value", "")))
            value_field_var.set(_as_text(rule.get("value_field")))
            value_template_var.set(_cell_text(rule.get("value_template", "{触发新值}")))
            write_mode_var.set(_as_text(rule.get("write_mode") or LINK_WRITE_REPLACE))
            append_separator_var.set(_cell_text(rule.get("append_separator", "")))
            regex_pattern_var.set(_cell_text(rule.get("regex_pattern", "")))
            replace_count_var.set(_as_text(rule.get("replace_count") or "0"))
            case_sensitive_var.set(bool(rule.get("case_sensitive", True)))
            empty_policy_var.set(_as_text(rule.get("empty_policy") or "允许"))
            area_enabled_var.set(bool(rule.get("area_enabled", False)))
            area_row_start_var.set(_as_text(rule.get("area_row_start_offset") or "0"))
            area_row_end_var.set(_as_text(rule.get("area_row_end_offset") or "0"))
            area_col_start_var.set(_as_text(rule.get("area_col_start_offset") or "0"))
            area_col_end_var.set(_as_text(rule.get("area_col_end_offset") or "0"))
            area_write_col_var.set(_as_text(rule.get("area_write_col_offset") or "0"))
            marker_col_var.set(_as_text(rule.get("marker_col_offset") or "0"))
            overflow_var.set(_as_text(rule.get("overflow_policy") or LINK_OVERFLOW_SKIP))
            overflow_target_mode_var.set(_as_text(rule.get("overflow_target_mode") or "自动"))
            overflow_fixed_row_var.set(_as_text(rule.get("overflow_fixed_row") or ""))
            slot_config = _ensure_slot_judgement(rule.get("slot_judgement"))
            slot_judgement_state["value"] = copy.deepcopy(slot_config)
            slot_mode_var.set(_as_text(slot_config.get("mode") or SLOT_MODE_SEQUENCE_DATE))
            actions_state["items"] = copy.deepcopy(rule.get("actions") or [])
            refresh_action_tree()
            update_linked_field_states()

        def refresh_linked_list(select_index=None):
            rule_list.delete(0, tk.END)
            for rule in cfg.get("linked_rules", []) or []:
                rule_list.insert(tk.END, linked_label(rule))
            trigger_combo.configure(values=_linked_trigger_options(cfg))
            sheet_combo.configure(values=current_sheet_names(True))
            value_field_combo.configure(values=current_content_fields())
            if cfg.get("linked_rules"):
                idx = 0 if select_index is None else max(0, min(int(select_index), len(cfg["linked_rules"]) - 1))
                rule_list.selection_clear(0, tk.END)
                rule_list.selection_set(idx)
                rule_list.see(idx)
                load_rule(idx)
            else:
                update_linked_field_states()

        def collect_preview_events():
            if not state.get("records"):
                reload_data()
            records = list(state.get("records", []) or [])
            contents = current_content_rows()
            by_file = {}
            for item in records:
                by_file.setdefault(item.get("source_file", ""), []).append(item)
            source_files = _source_files(records, params)
            aux_rows = current_aux_rows()
            table_context = current_table_context()
            events = []
            plan_states = {}
            plan_order = []
            empty_policy = _as_text(params.get("empty_policy", "跳过")) or "跳过"
            for content_index, content in enumerate(contents):
                source_file, source_note = _source_file_for_content(content, source_files, content_index, len(contents), params)
                if not source_file and source_files != [""]:
                    continue
                target_file = _target_file_for_content(content, params, source_file)
                if not target_file:
                    continue
                source_records = by_file.get(source_file, [])
                for rule in [r for r in cfg.get("rules", []) if isinstance(r, dict) and r.get("enabled", True)]:
                    locator = rule.get("source_locator", {}) or {}
                    feature_ok, _feature_detail = _feature_pass(rule.get("feature_name", ""), cfg.get("features", []), source_records, source_file, _as_text(locator.get("sheet_name")))
                    if not feature_ok:
                        continue
                    rec, _anchor_detail = _locate_target_record(rule, source_records, source_file, content=content, table_context=table_context)
                    if rec is None:
                        continue
                    ok, _match_detail = _match_text_with_sources(
                        rec.get("text", ""),
                        rule.get("source_match", {}),
                        content=content,
                        table_context=table_context,
                        doc_record=rec,
                        source_records=source_records,
                    )
                    if not ok:
                        continue
                    field = _as_text((rule.get("mapping") or {}).get("content_field") or (rule.get("mapping") or {}).get("field"))
                    if not field:
                        continue
                    value = _cell_text(content.get(field))
                    if value == "" and empty_policy in ("跳过", "报错"):
                        continue
                    plan_state = _plan_state_for(plan_states, plan_order, source_file, target_file, rec, content)
                    before_text, after_text = _update_plan_state(
                        plan_state,
                        value,
                        rule_name=rule.get("name", ""),
                        mapping_field=field,
                        content_row=content.get("__content_row__", ""),
                        write_note=f"普通映射；源文件选择={source_note}",
                    )
                    if after_text != before_text:
                        events.append({
                            "kind": "普通映射",
                            "rule_name": rule.get("name", ""),
                            "match_rule": rule.get("name", ""),
                            "event_tags": _rule_event_tags(rule, rule.get("name", "")),
                            "source_file": source_file,
                            "target_file": target_file,
                            "rec": rec,
                            "sheet_name": rec.get("sheet_name", ""),
                            "row_index": rec.get("row_index", ""),
                            "col_index": rec.get("col_index", ""),
                            "old_text": before_text,
                            "new_text": after_text,
                            "mapping_field": field,
                            "content": content,
                            "content_row": content.get("__content_row__", ""),
                            "source_note": source_note,
                        })
                for global_rule in [r for r in cfg.get("global_rules", []) if isinstance(r, dict) and r.get("enabled", True)]:
                    for rec in _global_rule_records(global_rule, source_records):
                        feature_ok, _feature_detail = _feature_pass(global_rule.get("feature_name", ""), cfg.get("features", []), source_records, source_file, rec.get("sheet_name", ""))
                        if not feature_ok:
                            continue
                        plan_state = _plan_state_for(plan_states, plan_order, source_file, target_file, rec, content)
                        current_rec = _plan_state_record(plan_state)
                        current_text = current_rec.get("text", "")
                        cond_ok, _cond_detail, condition_items = _condition_extract_items(current_text, global_rule.get("conditions", []), global_rule.get("condition_logic", "AND"))
                        if not cond_ok:
                            continue
                        value, _replace_detail, replace_error = _apply_replace_steps(current_text, global_rule, content, aux_rows, condition_items, table_context, params)
                        if replace_error or value == current_text:
                            continue
                        before_text, after_text = _update_plan_state(
                            plan_state,
                            value,
                            rule_name=f"全局:{global_rule.get('name', '')}",
                            mapping_field=_global_rule_fields(global_rule),
                            content_row=content.get("__content_row__", ""),
                            write_note=f"全局搜索替换；源文件选择={source_note}",
                        )
                        events.append({
                            "kind": "全局替换",
                            "rule_name": global_rule.get("name", ""),
                            "match_rule": f"全局:{global_rule.get('name', '')}",
                            "event_tags": _rule_event_tags(global_rule, global_rule.get("name", "")),
                            "source_file": source_file,
                            "target_file": target_file,
                            "rec": rec,
                            "sheet_name": rec.get("sheet_name", ""),
                            "row_index": rec.get("row_index", ""),
                            "col_index": rec.get("col_index", ""),
                            "old_text": before_text,
                            "new_text": after_text,
                            "mapping_field": _global_rule_fields(global_rule),
                            "content": content,
                            "content_row": content.get("__content_row__", ""),
                            "source_note": source_note,
                        })
            _assign_link_event_counts(events)
            return events, by_file

        def preview_current_rule():
            rule = build_rule_from_editor()
            events, by_file = collect_preview_events()
            rows, matched_count, skipped_count, reasons = _build_linked_plan_rows(
                [rule],
                events,
                by_file,
                params,
                table_context=current_table_context(),
            )
            preview_text.configure(state="normal")
            preview_text.delete("1.0", tk.END)
            preview_status_var.set(f"触发事件 {len(events)} 条；联动生成 {matched_count} 条；跳过 {skipped_count} 条")
            for row_values in rows[:300]:
                preview_text.insert(
                    tk.END,
                    f"[联动] {row_values[3]} R{row_values[4]}C{row_values[5]}\n"
                    f"原文：{row_values[8]}\n"
                    f"写入：{row_values[7]}\n"
                    f"规则：{row_values[12]}\n"
                    f"明细：{row_values[16]}\n\n"
                )
            if len(rows) > 300:
                preview_text.insert(tk.END, f"... 还有 {len(rows) - 300} 条未显示。\n")
            if not rows:
                preview_text.insert(tk.END, "当前联动规则没有生成写入计划。\n")
            if reasons:
                preview_text.insert(tk.END, "\n跳过原因：\n")
                for reason, count in sorted(reasons.items(), key=lambda item: item[1], reverse=True)[:10]:
                    preview_text.insert(tk.END, f"- {reason} x {count}\n")
            preview_text.configure(state="disabled")

        def save_rule(show_msg=False):
            idx = selected_idx.get("value")
            if idx is None:
                return
            rule = build_rule_from_editor()
            cfg["linked_rules"][idx] = rule
            _save_config(params, context, cfg)
            refresh_linked_list(idx)
            refresh_rules()
            status_var.set(f"已保存联动写入规则：{rule.get('name')}")
            if show_msg:
                messagebox.showinfo("保存完成", "联动写入规则已保存。", parent=dlg)

        def add_rule():
            cfg.setdefault("linked_rules", []).append(_default_linked_rule(len(cfg.get("linked_rules", [])) + 1))
            refresh_linked_list(len(cfg["linked_rules"]) - 1)

        def delete_rule():
            idx = selected_idx.get("value")
            if idx is None:
                return
            if not messagebox.askyesno("确认删除", "删除当前联动写入规则？", parent=dlg):
                return
            cfg["linked_rules"].pop(idx)
            _save_config(params, context, cfg)
            selected_idx["value"] = None
            refresh_linked_list(0)
            refresh_rules()

        def add_scheme_preset(preset_name):
            preset = _linked_scheme_presets().get(preset_name)
            if not isinstance(preset, dict):
                return
            rule = _ensure_linked_rule(copy.deepcopy(preset))
            cfg.setdefault("linked_rules", []).append(rule)
            _save_config(params, context, cfg)
            refresh_linked_list(len(cfg["linked_rules"]) - 1)
            refresh_rules()
            status_var.set(f"已增加联动方案预设：{preset_name}")

        def export_current_scheme():
            if filedialog is None:
                return
            rule = build_rule_from_editor()
            safe_name = re.sub(r'[\\/:*?"<>|]+', "_", _as_text(rule.get("name")) or "联动写入方案")
            path = filedialog.asksaveasfilename(
                parent=dlg,
                title="导出联动写入方案",
                initialdir=str(_plugin_data_dir(context)),
                initialfile=f"{safe_name}.json",
                defaultextension=".json",
                filetypes=[("JSON 文件", "*.json"), ("所有文件", "*.*")],
            )
            if not path:
                return
            payload = {
                "schema": "DataFlowKit.visual_mapping.linked_rules",
                "version": 1,
                "linked_rules": [rule],
            }
            Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            status_var.set(f"已导出联动方案：{path}")

        def import_linked_schemes():
            if filedialog is None:
                return
            path = filedialog.askopenfilename(
                parent=dlg,
                title="导入联动写入方案",
                initialdir=str(_plugin_data_dir(context)),
                filetypes=[("JSON 文件", "*.json"), ("所有文件", "*.*")],
            )
            if not path:
                return
            try:
                payload = json.loads(Path(path).read_text(encoding="utf-8"))
                if isinstance(payload, list):
                    imported = payload
                elif isinstance(payload, dict) and isinstance(payload.get("linked_rules"), list):
                    imported = payload["linked_rules"]
                elif isinstance(payload, dict):
                    imported = [payload]
                else:
                    imported = []
                rules = [
                    _ensure_linked_rule(copy.deepcopy(item))
                    for item in imported
                    if isinstance(item, dict)
                ]
                if not rules:
                    raise ValueError("文件中没有有效的联动写入规则")
                start_index = len(cfg.setdefault("linked_rules", []))
                cfg["linked_rules"].extend(rules)
                _save_config(params, context, cfg)
                refresh_linked_list(start_index)
                refresh_rules()
                status_var.set(f"已导入 {len(rules)} 条联动写入规则")
            except Exception as exc:
                messagebox.showerror("导入失败", str(exc), parent=dlg)

        def on_rule_select(_event=None):
            sel = rule_list.curselection()
            if sel:
                load_rule(int(sel[0]))

        rule_list.bind("<<ListboxSelect>>", on_rule_select)

        left_buttons = ttk.Frame(left_panel)
        left_buttons.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(left_buttons, text="增加", command=add_rule).pack(side=tk.LEFT, padx=2)
        ttk.Button(left_buttons, text="删除", command=delete_rule).pack(side=tk.LEFT, padx=2)
        ttk.Button(left_buttons, text="保存修改", command=lambda: save_rule(True)).pack(side=tk.LEFT, padx=2)
        scheme_buttons = ttk.Frame(left_panel)
        scheme_buttons.pack(fill=tk.X, pady=(4, 0))
        preset_button = ttk.Menubutton(scheme_buttons, text="方案预设")
        preset_menu = tk.Menu(preset_button, tearoff=False)
        for preset_name in _linked_scheme_presets():
            preset_menu.add_command(
                label=preset_name,
                command=lambda name=preset_name: add_scheme_preset(name),
            )
        preset_button.configure(menu=preset_menu)
        preset_button.pack(side=tk.LEFT, padx=2)
        ttk.Button(scheme_buttons, text="导入", command=import_linked_schemes).pack(side=tk.LEFT, padx=2)
        ttk.Button(scheme_buttons, text="导出当前", command=export_current_scheme).pack(side=tk.LEFT, padx=2)

        preview_buttons = ttk.Frame(preview_panel)
        preview_buttons.grid(row=3, column=0, columnspan=2, sticky=tk.E, pady=(8, 0))
        ttk.Button(preview_buttons, text="刷新预览", command=preview_current_rule).pack(side=tk.LEFT, padx=4)
        ttk.Button(preview_buttons, text="关闭", command=dlg.destroy).pack(side=tk.LEFT, padx=4)

        update_linked_field_states()
        refresh_linked_list(initial_index)
        dlg.after_idle(lambda: _show_centered_window(dlg, win, 1480, 760))

    def current_content_fields():
        table = tables.get(content_alias_var.get(), {})
        fields, _ = _content_rows(table)
        return fields

    def current_content_rows():
        table = tables.get(content_alias_var.get(), {})
        _fields, rows = _content_rows(table)
        return rows

    def current_aux_fields():
        table = tables.get(aux_alias_var.get(), {})
        fields, _ = _content_rows(table)
        return fields

    def current_aux_rows():
        table = tables.get(aux_alias_var.get(), {})
        _fields, rows = _content_rows(table)
        return rows

    def current_table_context():
        return _table_row_context(tables, content_alias_var.get(), aux_alias_var.get())

    def _put_visual_change(changes, rec, new_text, kind, rule_name="", content_row="", detail="", force=False):
        if not isinstance(rec, dict):
            return False
        old_text = _cell_text(rec.get("text", rec.get("old_text", "")))
        new_text = _cell_text(new_text)
        key = _cell_key(rec)
        previous = changes.get(key)
        if new_text == old_text and not force and previous is None:
            return False
        change = {
            "kind": kind,
            "rule_name": _as_text(rule_name),
            "content_row": content_row,
            "old_text": old_text,
            "new_text": new_text,
            "detail": _as_text(detail),
            "record": dict(rec),
        }
        if previous:
            history = list(previous.get("history", []))
            history.append({k: v for k, v in previous.items() if k not in ("record", "history")})
            change["history"] = history
        changes[key] = change
        return True

    def build_visual_preview_changes():
        sync_params_from_ui()
        if not state.get("records"):
            reload_data()
        records = list(state.get("records", []) or [])
        contents = current_content_rows()
        changes = {}
        normal_changed = 0
        global_changed = 0
        linked_changed = 0
        skipped = 0
        if not records:
            return changes, normal_changed, global_changed, linked_changed, skipped

        by_file = {}
        for item in records:
            by_file.setdefault(item.get("source_file", ""), []).append(item)
        source_files = _source_files(records, params)
        empty_policy = _as_text(params.get("empty_policy", "跳过")) or "跳过"
        plan_states = {}
        plan_order = []
        trigger_events = []
        normal_rules = [r for r in cfg.get("rules", []) if isinstance(r, dict) and r.get("enabled", True)]
        if contents and normal_rules:
            for content_index, content in enumerate(contents):
                source_file, source_note = _source_file_for_content(content, source_files, content_index, len(contents), params)
                if not source_file and source_files != [""]:
                    skipped += len(normal_rules)
                    continue
                target_file = _target_file_for_content(content, params, source_file)
                if not target_file:
                    skipped += len(normal_rules)
                    continue
                source_records = by_file.get(source_file, [])
                for rule in normal_rules:
                    locator = rule.get("source_locator", {}) or {}
                    feature_ok, feature_detail = _feature_pass(rule.get("feature_name", ""), cfg.get("features", []), source_records, source_file, _as_text(locator.get("sheet_name")))
                    if not feature_ok:
                        skipped += 1
                        continue
                    rec, anchor_detail = _locate_target_record(rule, source_records, source_file, content=content, table_context=current_table_context())
                    if rec is None:
                        skipped += 1
                        continue
                    ok, match_detail = _match_text_with_sources(
                        rec.get("text", ""),
                        rule.get("source_match", {}),
                        content=content,
                        table_context=current_table_context(),
                        doc_record=rec,
                        source_records=source_records,
                    )
                    if not ok:
                        skipped += 1
                        continue
                    mapping = rule.get("mapping", {}) or {}
                    field = _as_text(mapping.get("content_field") or mapping.get("field"))
                    if not field:
                        skipped += 1
                        continue
                    value = _cell_text(content.get(field))
                    if value == "" and empty_policy in ("跳过", "报错"):
                        skipped += 1
                        continue
                    plan_state = _plan_state_for(plan_states, plan_order, source_file, target_file, rec, content)
                    before_text, after_text = _update_plan_state(
                        plan_state,
                        value,
                        rule_name=rule.get("name", ""),
                        mapping_field=field,
                        content_row=content.get("__content_row__", ""),
                        source_detail=f"{feature_detail}；{match_detail}",
                        anchor_detail=anchor_detail,
                        write_note=f"普通映射；源文件选择={source_note}",
                        anchor_rule=json.dumps(rule.get("anchor", {}), ensure_ascii=False),
                    )
                    if after_text != before_text:
                        normal_changed += 1
                        trigger_events.append({
                            "kind": "普通映射",
                            "rule_name": rule.get("name", ""),
                            "match_rule": rule.get("name", ""),
                            "event_tags": _rule_event_tags(rule, rule.get("name", "")),
                            "source_file": source_file,
                            "target_file": target_file,
                            "rec": rec,
                            "sheet_name": rec.get("sheet_name", ""),
                            "row_index": rec.get("row_index", ""),
                            "col_index": rec.get("col_index", ""),
                            "old_text": before_text,
                            "new_text": after_text,
                            "mapping_field": field,
                            "content": content,
                            "content_row": content.get("__content_row__", ""),
                            "source_note": source_note,
                        })

        global_rules = [r for r in cfg.get("global_rules", []) if isinstance(r, dict) and r.get("enabled", True)]
        if global_rules:
            aux_rows = current_aux_rows()
            table_context = current_table_context()
            for content_index, content in enumerate(contents):
                source_file, source_note = _source_file_for_content(content, source_files, content_index, len(contents), params)
                if not source_file and source_files != [""]:
                    skipped += len(global_rules)
                    continue
                target_file = _target_file_for_content(content, params, source_file)
                if not target_file:
                    skipped += len(global_rules)
                    continue
                source_records = by_file.get(source_file, [])
                for global_rule in global_rules:
                    candidates = _global_rule_records(global_rule, source_records)
                    if not candidates:
                        skipped += 1
                        continue
                    rule_hit = 0
                    for rec in candidates:
                        feature_ok, feature_detail = _feature_pass(global_rule.get("feature_name", ""), cfg.get("features", []), source_records, source_file, rec.get("sheet_name", ""))
                        if not feature_ok:
                            continue
                        plan_state = _plan_state_for(plan_states, plan_order, source_file, target_file, rec, content)
                        current_rec = _plan_state_record(plan_state)
                        current_text = current_rec.get("text", "")
                        cond_ok, cond_detail, condition_items = _condition_extract_items(current_text, global_rule.get("conditions", []), global_rule.get("condition_logic", "AND"))
                        if not cond_ok:
                            continue
                        value, replace_detail, replace_error = _apply_replace_steps(current_text, global_rule, content, aux_rows, condition_items, table_context, params)
                        if replace_error or value == current_text:
                            if replace_error:
                                skipped += 1
                            continue
                        if value == "" and empty_policy in ("跳过", "报错"):
                            skipped += 1
                            continue
                        before_text, after_text = _update_plan_state(
                            plan_state,
                            value,
                            rule_name=f"全局:{global_rule.get('name', '')}",
                            mapping_field=_global_rule_fields(global_rule),
                            content_row=content.get("__content_row__", ""),
                            source_detail=f"{feature_detail}；{cond_detail}",
                            write_note=f"全局搜索替换；{replace_detail}；源文件选择={source_note}",
                        )
                        rule_hit += 1
                        if after_text != before_text:
                            global_changed += 1
                            trigger_events.append({
                                "kind": "全局替换",
                                "rule_name": global_rule.get("name", ""),
                                "match_rule": f"全局:{global_rule.get('name', '')}",
                                "event_tags": _rule_event_tags(global_rule, global_rule.get("name", "")),
                                "source_file": source_file,
                                "target_file": target_file,
                                "rec": rec,
                                "sheet_name": rec.get("sheet_name", ""),
                                "row_index": rec.get("row_index", ""),
                                "col_index": rec.get("col_index", ""),
                                "old_text": before_text,
                                "new_text": after_text,
                                "mapping_field": _global_rule_fields(global_rule),
                                "content": content,
                                "content_row": content.get("__content_row__", ""),
                                "source_note": source_note,
                            })
                    if rule_hit == 0:
                        skipped += 1

        linked_rules = [r for r in cfg.get("linked_rules", []) if isinstance(r, dict) and r.get("enabled", True)]
        if linked_rules and trigger_events:
            _assign_link_event_counts(trigger_events)
            linked_changed, linked_skipped, _linked_reasons = _apply_linked_rules_to_plan_states(
                linked_rules,
                trigger_events,
                by_file,
                params,
                plan_states,
                plan_order,
                table_context=current_table_context(),
            )
            skipped += linked_skipped
        for key in plan_order:
            plan_state = plan_states.get(key)
            if not plan_state or not plan_state.get("touched"):
                continue
            rec = _plan_state_record(plan_state)
            kind = "流程预览"
            rules_text = " -> ".join(plan_state.get("match_rules", []) or [])
            if rules_text.startswith("联动:") or " -> 联动:" in rules_text:
                kind = "联动写入"
            elif "全局:" in rules_text:
                kind = "全局替换"
            elif rules_text:
                kind = "普通映射"
            _put_visual_change(
                changes,
                rec,
                plan_state.get("current_text", ""),
                kind,
                rules_text,
                ",".join(plan_state.get("content_rows", []) or []),
                "；".join(plan_state.get("write_notes", []) or []),
                force=True,
            )
        return changes, normal_changed, global_changed, linked_changed, skipped

    def apply_visual_preview_highlight():
        changes, normal_changed, global_changed, linked_changed, skipped = build_visual_preview_changes()
        state["preview_changes"] = changes
        if state.get("selected_group"):
            render_group(state["selected_group"])
        status_var.set(
            f"替换预览高亮 {len(changes)} 格；普通映射变化 {normal_changed} 条；全局替换变化 {global_changed} 条；联动写入 {linked_changed} 条；跳过/错误 {skipped} 条"
        )

    def clear_visual_preview_highlight():
        state["preview_changes"] = {}
        if state.get("selected_group"):
            render_group(state["selected_group"])
        status_var.set("已清除替换预览高亮")

    def show_global_replace_preview():
        sync_params_from_ui()
        if not state.get("records"):
            reload_data()
        dlg = _make_floating_child(win, "全局替换预览")
        body = ttk.Frame(dlg, padding=10)
        body.pack(fill=tk.BOTH, expand=True)
        body.rowconfigure(1, weight=1)
        body.columnconfigure(0, weight=1)

        header_var = tk.StringVar(value="")
        ttk.Label(body, textvariable=header_var, foreground="gray").grid(row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 6))
        preview_text = tk.Text(body, height=32, width=120, wrap=tk.WORD)
        preview_text.grid(row=1, column=0, sticky="nsew")
        preview_scroll = ttk.Scrollbar(body, orient=tk.VERTICAL, command=preview_text.yview)
        preview_scroll.grid(row=1, column=1, sticky="ns")
        preview_text.configure(yscrollcommand=preview_scroll.set)

        def render_preview():
            sync_params_from_ui()
            records = list(state.get("records", []) or [])
            preview_text.configure(state="normal")
            preview_text.delete("1.0", tk.END)
            if not records:
                header_var.set("可替换 0 条；文档读取表没有可预览记录")
                preview_text.insert(tk.END, "当前文档读取表没有可预览记录，请先刷新可视化。")
                preview_text.configure(state="disabled")
                return
            global_rules = cfg.get("global_rules", []) or []
            if not any(isinstance(rule, dict) and rule.get("enabled", True) for rule in global_rules):
                header_var.set("可替换 0 条；没有启用的全局搜索替换规则")
                preview_text.insert(tk.END, "当前配置没有启用的全局搜索替换规则。")
                preview_text.configure(state="disabled")
                return
            contents = current_content_rows()
            preview_rows, total_changed, total_errors = _preview_global_replace_rows(
                global_rules,
                records,
                cfg.get("features", []),
                contents,
                current_aux_rows(),
                params,
                limit=800,
                include_unchanged=True,
                table_context=current_table_context(),
            )
            header_var.set(f"可替换 {total_changed} 条；错误/跳过 {total_errors} 条；显示 {len(preview_rows)} 条")
            for item in preview_rows:
                preview_text.insert(
                    tk.END,
                    f"[{item.get('status')}] 规则：{item.get('rule_name')}  {item.get('source_file')} {item.get('location')} 新内容行{item.get('content_row')}\n"
                    f"原文：{item.get('old_text')}\n"
                    f"替换：{item.get('new_text')}\n"
                    f"明细：{item.get('detail')}\n\n"
                )
            if total_changed > len([r for r in preview_rows if r.get("status") == "替换"]):
                preview_text.insert(tk.END, "... 还有更多替换结果未显示，请缩小规则范围或增加预览上限。\n")
            if not preview_rows:
                preview_text.insert(tk.END, "当前全局规则未产生可替换结果。")
            preview_text.configure(state="disabled")

        button_row = ttk.Frame(body)
        button_row.grid(row=2, column=0, columnspan=2, sticky=tk.E, pady=(8, 0))
        ttk.Button(button_row, text="刷新预览", command=render_preview).pack(side=tk.LEFT, padx=4)
        ttk.Button(button_row, text="关闭", command=dlg.destroy).pack(side=tk.LEFT, padx=4)
        render_preview()
        dlg.after_idle(lambda: _show_centered_window(dlg, win, 1120, 720))

    def current_doc_fields():
        table = tables.get(doc_alias_var.get(), {})
        return list(table.get("headers", []) or [])

    def refresh_field_combos():
        doc_fields = current_doc_fields()
        content_fields = current_content_fields()
        source_file_field_combo.configure(values=doc_fields)
        planned_file_field_combo.configure(values=content_fields)
        if not source_file_field_var.get() and doc_fields:
            source_file_field_var.set("source_file" if "source_file" in doc_fields else doc_fields[0])
        if not planned_file_field_var.get() and content_fields:
            planned_file_field_var.set("target_file" if "target_file" in content_fields else content_fields[0])

    def rule_id_for_rec(rec):
        return f"{rec.get('sheet_name','')}:R{rec.get('row_index')}C{rec.get('col_index')}"

    def find_rule(rec):
        rid = rule_id_for_rec(rec)
        for rule in cfg.setdefault("rules", []):
            if rule.get("id") == rid:
                return rule
        rule = _default_rule_for_cell(rec)
        cfg["rules"].append(rule)
        return rule

    def refresh_rules():
        rule_lb.delete(0, tk.END)
        for rule in cfg.get("rules", []):
            if not rule.get("enabled", True):
                prefix = "[停用] "
            else:
                prefix = ""
            field = (rule.get("mapping") or {}).get("content_field", "")
            feature_name = _cfg_feature_name(rule.get("feature_name"))
            feature_note = f" [特征:{feature_name}]" if feature_name else ""
            rule_lb.insert(tk.END, f"{prefix}{rule.get('name','')} -> {field}{feature_note}")
        for rule in cfg.get("global_rules", []) or []:
            prefix = "" if rule.get("enabled", True) else "[停用] "
            feature_name = _cfg_feature_name(rule.get("feature_name"))
            feature_note = f" [特征:{feature_name}]" if feature_name else ""
            rule_lb.insert(tk.END, f"{prefix}[全局] {rule.get('name','')}{feature_note}")
        for rule in cfg.get("linked_rules", []) or []:
            prefix = "" if rule.get("enabled", True) else "[停用] "
            trigger = _as_text(rule.get("trigger_rule") or LINKED_RULE_ANY)
            rule_lb.insert(tk.END, f"{prefix}[联动] {rule.get('name','')} <= {trigger}")

    def select_rule_list_index(index):
        total = rule_lb.size()
        if total <= 0:
            return
        index = max(0, min(int(index), total - 1))
        rule_lb.selection_clear(0, tk.END)
        rule_lb.selection_set(index)
        rule_lb.see(index)

    def selected_rule_ref(show_warning=True):
        sel = rule_lb.curselection()
        if not sel:
            if show_warning:
                messagebox.showwarning("未选择规则", "请先在“已配置规则”列表里选中一条规则。", parent=win)
            return None
        list_index = int(sel[0])
        normal_rules = cfg.setdefault("rules", [])
        if list_index < len(normal_rules):
            return {
                "kind": "rules",
                "label": "普通映射规则",
                "rules": normal_rules,
                "index": list_index,
                "list_index": list_index,
                "rule": normal_rules[list_index],
            }
        global_rules = cfg.setdefault("global_rules", [])
        global_index = list_index - len(normal_rules)
        if 0 <= global_index < len(global_rules):
            return {
                "kind": "global_rules",
                "label": "全局替换规则",
                "rules": global_rules,
                "index": global_index,
                "list_index": list_index,
                "rule": global_rules[global_index],
            }
        linked_rules = cfg.setdefault("linked_rules", [])
        linked_index = list_index - len(normal_rules) - len(global_rules)
        if 0 <= linked_index < len(linked_rules):
            return {
                "kind": "linked_rules",
                "label": "联动写入规则",
                "rules": linked_rules,
                "index": linked_index,
                "list_index": list_index,
                "rule": linked_rules[linked_index],
            }
        if show_warning:
            messagebox.showwarning("规则不存在", "当前选中的规则已经不存在，请刷新列表后重试。", parent=win)
        return None

    def rule_list_index(kind, index):
        if kind == "global_rules":
            return len(cfg.get("rules", []) or []) + int(index)
        if kind == "linked_rules":
            return len(cfg.get("rules", []) or []) + len(cfg.get("global_rules", []) or []) + int(index)
        return int(index)

    def after_rule_manage(kind, index, message):
        state["preview_changes"] = {}
        state["focused_cell_key"] = ""
        refresh_rules()
        select_rule_list_index(rule_list_index(kind, index))
        if state.get("selected_group"):
            render_group(state["selected_group"])
        status_var.set(f"{message}；请点击“保存配置”写入当前配置")

    def delete_selected_rule():
        ref = selected_rule_ref()
        if not ref:
            return
        rule = ref["rule"]
        name = _as_text(rule.get("name")) or _as_text(rule.get("id")) or "未命名规则"
        if not messagebox.askyesno("删除规则", f"确定删除这条{ref['label']}吗？\n\n{name}", parent=win):
            return
        ref["rules"].pop(ref["index"])
        next_index = min(ref["index"], max(0, len(ref["rules"]) - 1))
        after_rule_manage(ref["kind"], next_index, f"已删除规则：{name}")

    def toggle_selected_rule():
        ref = selected_rule_ref()
        if not ref:
            return
        rule = ref["rule"]
        enabled = not bool(rule.get("enabled", True))
        rule["enabled"] = enabled
        name = _as_text(rule.get("name")) or _as_text(rule.get("id")) or "未命名规则"
        state_text = "启用" if enabled else "停用"
        after_rule_manage(ref["kind"], ref["index"], f"已{state_text}规则：{name}")

    def move_selected_rule(delta):
        ref = selected_rule_ref()
        if not ref:
            return
        rules = ref["rules"]
        old_index = ref["index"]
        new_index = old_index + int(delta)
        if new_index < 0 or new_index >= len(rules):
            status_var.set("规则已经在当前分组的边界位置")
            return
        rules[old_index], rules[new_index] = rules[new_index], rules[old_index]
        direction = "上移" if delta < 0 else "下移"
        name = _as_text(rules[new_index].get("name")) or _as_text(rules[new_index].get("id")) or "未命名规则"
        after_rule_manage(ref["kind"], new_index, f"已{direction}规则：{name}")

    def show_info(rec):
        state["selected_rec"] = rec
        info_text.delete("1.0", tk.END)
        payload = dict(rec)
        preview_change = state.get("preview_changes", {}).get(_cell_key(rec))
        if preview_change:
            payload["preview_change"] = preview_change
        info_text.insert(tk.END, json.dumps(payload, ensure_ascii=False, indent=2))

    def edit_source(rec):
        dlg = _make_floating_child(win, "输入源信息")
        body = ttk.Frame(dlg, padding=10)
        body.pack(fill=tk.BOTH, expand=True)
        txt = tk.Text(body, height=18, width=70, wrap=tk.WORD)
        txt.pack(fill=tk.BOTH, expand=True)
        txt.insert(tk.END, json.dumps(rec, ensure_ascii=False, indent=2))
        txt.configure(state="disabled")
        ttk.Button(body, text="关闭", command=dlg.destroy).pack(anchor=tk.E, pady=(8, 0))
        dlg.after_idle(lambda: _show_centered_window(dlg, win))

    def edit_rule(rec, rule_override=None):
        rule = rule_override or find_rule(rec)
        dlg = _make_floating_child(win, "输入源匹配 / 锚点定位规则")
        body = ttk.Frame(dlg, padding=10)
        body.pack(fill=tk.BOTH, expand=True)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(1, weight=1)
        body.rowconfigure(2, weight=1)
        source_match = rule.setdefault("source_match", {})
        anchor = rule.setdefault("anchor", {})
        sm_enabled = tk.BooleanVar(value=bool(source_match.get("enabled", False)))
        sm_logic = tk.StringVar(value=_as_text(source_match.get("logic") or "AND") or "AND")
        feature_var = tk.StringVar(value=_ui_feature_name(rule.get("feature_name", "")))
        anchor_enabled = tk.BooleanVar(value=bool(anchor.get("enabled", False)))
        anchor_axis = tk.StringVar(value=anchor.get("axis", "列"))
        anchor_index = tk.StringVar(value=str(anchor.get("index", rec.get("col_index", 1))))
        anchor_logic = tk.StringVar(value=_as_text(anchor.get("logic") or "AND") or "AND")
        row_offset = tk.StringVar(value=str(anchor.get("row_offset", 0)))
        col_offset = tk.StringVar(value=str(anchor.get("col_offset", 0)))

        top = ttk.Frame(body)
        top.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        top.columnconfigure(3, weight=1)
        ttk.Label(top, text=f"当前格：{rec.get('sheet_name','')} R{rec.get('row_index')}C{rec.get('col_index')}").grid(row=0, column=0, sticky=tk.W, padx=4)
        ttk.Label(top, text="表特征：").grid(row=0, column=1, sticky=tk.E, padx=4)
        ttk.Combobox(top, textvariable=feature_var, values=current_feature_names(True), width=20, state="normal").grid(row=0, column=2, sticky=tk.W, padx=4)
        ttk.Label(top, text=f"原文：{_short_preview_text(rec.get('text',''), 80)}", foreground="gray").grid(row=0, column=3, sticky=tk.W, padx=8)

        def match_source_choices():
            choices = ["手动输入", "文档读取表字段"]
            for alias in table_aliases:
                alias = _as_text(alias)
                if alias and alias not in choices:
                    choices.append(alias)
            return choices

        def doc_match_fields():
            fields = ["text", "source_file", "block_type", "sheet_name", "row_index", "col_index", "cell_address"]
            for field in current_doc_fields():
                field = _as_text(field)
                if field and field not in fields:
                    fields.append(field)
            return fields

        def source_fields(source):
            source = _normalize_batch_table_source(source)
            if _is_manual_batch_source(source):
                return []
            if source in ("文档读取表字段", "当前格字段", "doc_field"):
                return doc_match_fields()
            return (current_table_context().get("fields_by_alias") or {}).get(source, [])

        def preview_content_row():
            rows = current_content_rows()
            return rows[0] if rows else {}

        def same_scope_records():
            sheet = rec.get("sheet_name", "")
            source = rec.get("source_file", "")
            result = []
            for item in state.get("records", []):
                if sheet and item.get("sheet_name", "") != sheet:
                    continue
                if source and item.get("source_file", "") != source:
                    continue
                result.append(item)
            return result

        def make_condition_section(parent, title, conditions, default_logic):
            frame = ttk.LabelFrame(parent, text=title, padding=8)
            frame.columnconfigure(0, weight=1)
            frame.rowconfigure(1, weight=1)
            logic_var = tk.StringVar(value=_as_text(default_logic or "AND") or "AND")
            head = ttk.Frame(frame)
            head.grid(row=0, column=0, sticky="ew")
            ttk.Label(head, text="默认连接：").pack(side=tk.LEFT)
            ttk.Combobox(head, textvariable=logic_var, values=["AND", "OR"], width=8, state="readonly").pack(side=tk.LEFT, padx=4)

            columns = ("join", "mode", "source", "value", "field", "row_policy", "row_index")
            tree_frame = ttk.Frame(frame)
            tree_frame.grid(row=1, column=0, sticky="nsew", pady=4)
            tree_frame.rowconfigure(0, weight=1)
            tree_frame.columnconfigure(0, weight=1)
            tree = ttk.Treeview(tree_frame, columns=columns, show="headings", height=5)
            specs = [
                ("join", "连接", 70),
                ("mode", "匹配", 110),
                ("source", "值来源", 140),
                ("value", "手动值", 190),
                ("field", "字段", 150),
                ("row_policy", "行策略", 120),
                ("row_index", "固定行", 70),
            ]
            for col, text, width in specs:
                tree.heading(col, text=text)
                tree.column(col, width=width, anchor=tk.W, stretch=False)
            tree.grid(row=0, column=0, sticky="nsew")
            yscroll = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=tree.yview)
            yscroll.grid(row=0, column=1, sticky="ns")
            xscroll = ttk.Scrollbar(tree_frame, orient=tk.HORIZONTAL, command=tree.xview)
            xscroll.grid(row=1, column=0, sticky="ew")
            tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)

            editor = ttk.Frame(frame)
            editor.grid(row=2, column=0, sticky="ew", pady=(4, 0))
            join_var = tk.StringVar(value="AND")
            mode_var = tk.StringVar(value="包含")
            source_var = tk.StringVar(value="手动输入")
            value_var = tk.StringVar(value="")
            field_var = tk.StringVar(value="")
            row_policy_var = tk.StringVar(value=REPLACE_ROW_CONTENT_ROW)
            row_index_var = tk.StringVar(value="1")
            ttk.Combobox(editor, textvariable=join_var, values=["AND", "OR"], width=7, state="readonly").pack(side=tk.LEFT, padx=2)
            ttk.Combobox(editor, textvariable=mode_var, values=["包含", "等于", "不等于", "正则匹配", "正则不匹配", "为空", "非空"], width=12, state="readonly").pack(side=tk.LEFT, padx=2)
            source_combo = ttk.Combobox(editor, textvariable=source_var, values=match_source_choices(), width=16, state="readonly")
            source_combo.pack(side=tk.LEFT, padx=2)
            value_entry = ttk.Entry(editor, textvariable=value_var, width=22)
            value_entry.pack(side=tk.LEFT, padx=2, fill=tk.X, expand=True)
            field_combo = ttk.Combobox(editor, textvariable=field_var, values=[], width=18, state="normal")
            field_combo.pack(side=tk.LEFT, padx=2)
            ttk.Combobox(editor, textvariable=row_policy_var, values=REPLACE_ROW_POLICY_CHOICES, width=13, state="readonly").pack(side=tk.LEFT, padx=2)
            ttk.Entry(editor, textvariable=row_index_var, width=7).pack(side=tk.LEFT, padx=2)

            def refresh_source_fields(_event=None):
                field_combo.configure(values=source_fields(source_var.get()))
                if _is_manual_batch_source(source_var.get()):
                    value_entry.configure(state="normal")
                else:
                    value_entry.configure(state="disabled")

            def values_from_editor():
                return (
                    join_var.get() or "AND",
                    mode_var.get() or "包含",
                    source_var.get() or "手动输入",
                    value_var.get(),
                    field_var.get(),
                    row_policy_var.get() or REPLACE_ROW_CONTENT_ROW,
                    row_index_var.get() or "1",
                )

            def load_to_editor(values):
                values = list(values or [])
                while len(values) < 7:
                    values.append("")
                join, mode, source, value, field, row_policy, row_index = values[:7]
                join_var.set(join or "AND")
                mode_var.set(mode or "包含")
                source_var.set(source or "手动输入")
                value_var.set(value)
                field_var.set(field)
                row_policy_var.set(row_policy or REPLACE_ROW_CONTENT_ROW)
                row_index_var.set(row_index or "1")
                refresh_source_fields()

            def insert_condition(cond):
                source = _normalize_batch_table_source(cond.get("value_source") or cond.get("match_value_source") or "手动输入")
                tree.insert("", tk.END, values=(
                    _as_text(cond.get("join") or "AND"),
                    _as_text(cond.get("mode") or "包含"),
                    source,
                    _as_text(cond.get("value") or cond.get("match_value")),
                    _as_text(cond.get("value_field") or cond.get("match_value_field") or cond.get("field")),
                    _normalize_replace_row_policy(cond.get("row_policy") or cond.get("match_row_policy") or cond.get("match_value_row_policy")),
                    _as_text(cond.get("row_index") or cond.get("match_row_index") or "1"),
                ))

            def get_conditions():
                rows = []
                for item_id in tree.get_children():
                    join, mode, source, value, field, row_policy, row_index = tree.item(item_id, "values")
                    rows.append({
                        "join": _as_text(join) or "AND",
                        "mode": _as_text(mode) or "包含",
                        "value_source": _normalize_batch_table_source(source),
                        "value": value,
                        "value_field": _as_text(field),
                        "row_policy": _normalize_replace_row_policy(row_policy),
                        "row_index": _as_text(row_index) or "1",
                    })
                return rows

            def add_condition():
                tree.insert("", tk.END, values=values_from_editor())

            def update_condition():
                sel = tree.selection()
                if sel:
                    tree.item(sel[0], values=values_from_editor())

            def delete_condition():
                for item_id in tree.selection():
                    tree.delete(item_id)

            def on_select(_event=None):
                sel = tree.selection()
                if sel:
                    load_to_editor(tree.item(sel[0], "values"))

            buttons = ttk.Frame(frame)
            buttons.grid(row=3, column=0, sticky=tk.E, pady=(4, 0))
            ttk.Button(buttons, text="增加条件", command=add_condition).pack(side=tk.LEFT, padx=2)
            ttk.Button(buttons, text="更新条件", command=update_condition).pack(side=tk.LEFT, padx=2)
            ttk.Button(buttons, text="删除条件", command=delete_condition).pack(side=tk.LEFT, padx=2)
            tree.bind("<<TreeviewSelect>>", on_select)
            source_combo.bind("<<ComboboxSelected>>", refresh_source_fields)
            for cond in conditions:
                insert_condition(cond)
            if not tree.get_children():
                insert_condition({"join": "AND", "mode": "包含", "value_source": "手动输入", "value": ""})
            first = tree.get_children()
            if first:
                tree.selection_set(first[0])
                load_to_editor(tree.item(first[0], "values"))
            return {
                "frame": frame,
                "logic_var": logic_var,
                "tree": tree,
                "get_conditions": get_conditions,
            }

        source_frame = ttk.Frame(body)
        source_frame.grid(row=1, column=0, sticky="nsew", pady=(0, 8))
        source_frame.columnconfigure(0, weight=1)
        source_frame.rowconfigure(1, weight=1)
        source_controls = ttk.Frame(source_frame)
        source_controls.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        ttk.Checkbutton(source_controls, text="启用输入源匹配", variable=sm_enabled).pack(side=tk.LEFT, padx=4)
        source_section = make_condition_section(
            source_frame,
            "输入源匹配规则设置",
            _legacy_conditions_from_match_cfg(source_match, "mode", "value"),
            source_match.get("logic", "AND"),
        )
        source_section["frame"].grid(row=1, column=0, sticky="nsew")

        anchor_frame = ttk.Frame(body)
        anchor_frame.grid(row=2, column=0, sticky="nsew", pady=(0, 8))
        anchor_frame.columnconfigure(0, weight=1)
        anchor_frame.rowconfigure(1, weight=1)
        anchor_controls = ttk.Frame(anchor_frame)
        anchor_controls.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        ttk.Checkbutton(anchor_controls, text="启用锚点", variable=anchor_enabled).pack(side=tk.LEFT, padx=4)
        ttk.Label(anchor_controls, text="方向：").pack(side=tk.LEFT, padx=(12, 2))
        ttk.Combobox(anchor_controls, textvariable=anchor_axis, values=["行", "列"], width=8, state="readonly").pack(side=tk.LEFT, padx=2)
        ttk.Label(anchor_controls, text="行/列序号：").pack(side=tk.LEFT, padx=(12, 2))
        ttk.Entry(anchor_controls, textvariable=anchor_index, width=8).pack(side=tk.LEFT, padx=2)
        ttk.Label(anchor_controls, text="偏移行：").pack(side=tk.LEFT, padx=(12, 2))
        ttk.Entry(anchor_controls, textvariable=row_offset, width=8).pack(side=tk.LEFT, padx=2)
        ttk.Label(anchor_controls, text="偏移列：").pack(side=tk.LEFT, padx=(12, 2))
        ttk.Entry(anchor_controls, textvariable=col_offset, width=8).pack(side=tk.LEFT, padx=2)
        anchor_section = make_condition_section(
            anchor_frame,
            "锚点候选匹配规则设置",
            _legacy_conditions_from_match_cfg(anchor, "match_mode", "value"),
            anchor.get("logic", "AND"),
        )
        anchor_section["frame"].grid(row=1, column=0, sticky="nsew")

        def current_source_match_cfg():
            conditions = source_section["get_conditions"]()
            first = conditions[0] if conditions else {}
            return {
                "enabled": bool(sm_enabled.get()),
                "logic": source_section["logic_var"].get(),
                "conditions": conditions,
                "mode": first.get("mode", "包含"),
                "value": first.get("value", ""),
            }

        def current_anchor_cfg():
            conditions = anchor_section["get_conditions"]()
            first = conditions[0] if conditions else {}
            return {
                "enabled": bool(anchor_enabled.get()),
                "axis": anchor_axis.get(),
                "index": anchor_index.get(),
                "logic": anchor_section["logic_var"].get(),
                "conditions": conditions,
                "match_mode": first.get("mode", "等于"),
                "value": first.get("value", ""),
                "row_offset": row_offset.get(),
                "col_offset": col_offset.get(),
            }

        def evaluate_record(item, match_cfg, match_index=1):
            return _match_text_with_sources(
                item.get("text", ""),
                match_cfg,
                content=preview_content_row(),
                table_context=current_table_context(),
                doc_record=item,
                source_records=same_scope_records(),
                match_index=match_index,
            )

        def preview_match(title, match_cfg, axis_filter=False):
            records = same_scope_records()
            matched_records = []
            failed_records = []
            seen = 0
            for item in records:
                if axis_filter:
                    axis = anchor_axis.get()
                    index = _to_int(anchor_index.get(), 0)
                    if index <= 0:
                        continue
                    if axis in ("列", "column") and int(item.get("col_index") or 0) != index:
                        continue
                    if axis in ("行", "row") and int(item.get("row_index") or 0) != index:
                        continue
                seen += 1
                ok, detail = evaluate_record(item, match_cfg, seen)
                row = (item, detail)
                if ok:
                    matched_records.append(row)
                else:
                    failed_records.append(row)
            current_ok, current_detail = evaluate_record(rec, match_cfg, 1)
            preview = _make_floating_child(dlg, title)
            preview_body = ttk.Frame(preview, padding=10)
            preview_body.pack(fill=tk.BOTH, expand=True)
            preview_body.rowconfigure(1, weight=1)
            preview_body.columnconfigure(0, weight=1)
            header = f"当前格：{'通过' if current_ok else '不通过'}；命中 {len(matched_records)} / {seen or len(records)} 条"
            if not match_cfg.get("enabled"):
                header += "；注意：未启用，正式执行会按通过处理"
            ttk.Label(preview_body, text=header, foreground="gray").grid(row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 6))
            txt = tk.Text(preview_body, height=28, width=112, wrap=tk.WORD)
            txt.grid(row=1, column=0, sticky="nsew")
            scroll = ttk.Scrollbar(preview_body, orient=tk.VERTICAL, command=txt.yview)
            scroll.grid(row=1, column=1, sticky="ns")
            txt.configure(yscrollcommand=scroll.set)
            txt.insert(tk.END, f"当前格 R{rec.get('row_index')}C{rec.get('col_index')}：{current_detail}\n")
            txt.insert(tk.END, f"当前文本：{rec.get('text', '')}\n\n")
            if matched_records:
                txt.insert(tk.END, "命中记录：\n")
                for item, detail in matched_records[:300]:
                    txt.insert(tk.END, f"- {item.get('sheet_name','')} R{item.get('row_index')}C{item.get('col_index')}：{item.get('text','')}\n  明细：{detail}\n")
                if len(matched_records) > 300:
                    txt.insert(tk.END, f"... 还有 {len(matched_records) - 300} 条命中未显示。\n")
            else:
                txt.insert(tk.END, "没有任何命中记录。\n")
                if failed_records:
                    txt.insert(tk.END, "\n未命中示例：\n")
                    for item, detail in failed_records[:20]:
                        txt.insert(tk.END, f"- {item.get('sheet_name','')} R{item.get('row_index')}C{item.get('col_index')}：{item.get('text','')}\n  明细：{detail}\n")
            txt.configure(state="disabled")
            button_row = ttk.Frame(preview_body)
            button_row.grid(row=2, column=0, columnspan=2, sticky=tk.E, pady=(8, 0))
            ttk.Button(button_row, text="关闭", command=preview.destroy).pack(side=tk.RIGHT, padx=4)
            preview.after_idle(lambda: _show_centered_window(preview, dlg, 1000, 640))

        def anchor_candidates_from_ui():
            axis = anchor_axis.get()
            index = _to_int(anchor_index.get(), 0)
            if index <= 0:
                messagebox.showwarning("无法反推", "请先设置锚点行/列序号。", parent=dlg)
                return []
            match_cfg = current_anchor_cfg()
            candidates = []
            seen = 0
            for item in same_scope_records():
                if axis in ("列", "column") and int(item.get("col_index") or 0) != index:
                    continue
                if axis in ("行", "row") and int(item.get("row_index") or 0) != index:
                    continue
                seen += 1
                ok, _detail = evaluate_record(item, match_cfg, seen)
                if ok:
                    candidates.append(item)
            return candidates

        def apply_anchor_candidate(anchor_rec):
            target_row = int(rec.get("row_index") or 0)
            target_col = int(rec.get("col_index") or 0)
            anchor_row = int(anchor_rec.get("row_index") or 0)
            anchor_col = int(anchor_rec.get("col_index") or 0)
            row_offset.set(str(target_row - anchor_row))
            col_offset.set(str(target_col - anchor_col))
            anchor_enabled.set(True)

        def choose_anchor_candidate(candidates):
            chooser = _make_floating_child(dlg, "选择锚点候选")
            body2 = ttk.Frame(chooser, padding=10)
            body2.pack(fill=tk.BOTH, expand=True)
            ttk.Label(body2, text="命中多个锚点，请选择用于反推偏移的单元格：").pack(anchor=tk.W, pady=(0, 6))
            lb_frame, lb = _make_scrollable_listbox(body2, height=min(12, max(4, len(candidates))), width=72, exportselection=False)
            lb_frame.pack(fill=tk.BOTH, expand=True)
            for item in candidates:
                lb.insert(tk.END, f"R{item.get('row_index')}C{item.get('col_index')}  {item.get('text', '')}"[:180])
            if candidates:
                lb.selection_set(0)

            def use_selected():
                sel = lb.curselection()
                if not sel:
                    return
                apply_anchor_candidate(candidates[int(sel[0])])
                chooser.destroy()

            btn_row = ttk.Frame(body2)
            btn_row.pack(fill=tk.X, pady=(8, 0))
            ttk.Button(btn_row, text="使用选中", command=use_selected).pack(side=tk.RIGHT, padx=4)
            ttk.Button(btn_row, text="取消", command=chooser.destroy).pack(side=tk.RIGHT, padx=4)
            lb.bind("<Double-1>", lambda _e=None: use_selected())
            chooser.after_idle(lambda: _show_centered_window(chooser, dlg))

        def auto_infer_offset():
            candidates = anchor_candidates_from_ui()
            if not candidates:
                messagebox.showwarning("无法反推", "未找到匹配的锚点单元格。请检查行/列序号和匹配条件。", parent=dlg)
                return
            if len(candidates) == 1:
                apply_anchor_candidate(candidates[0])
                messagebox.showinfo("反推完成", f"已自动写入偏移：行 {row_offset.get()}，列 {col_offset.get()}", parent=dlg)
                return
            choose_anchor_candidate(candidates)

        def on_ok():
            rule["feature_name"] = _cfg_feature_name(feature_var.get())
            source_match.clear()
            source_match.update(current_source_match_cfg())
            anchor.clear()
            anchor.update(current_anchor_cfg())
            state["preview_changes"] = {}
            refresh_rules()
            dlg.destroy()

        btns = ttk.Frame(body)
        btns.grid(row=3, column=0, sticky=tk.E, pady=(0, 2))
        ttk.Button(btns, text="输入源匹配预览", command=lambda: preview_match("输入源匹配预览", current_source_match_cfg(), False)).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="锚点候选预览", command=lambda: preview_match("锚点候选预览", current_anchor_cfg(), True)).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="自动反推偏移", command=auto_infer_offset).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="确定", command=on_ok).pack(side=tk.RIGHT, padx=4)
        ttk.Button(btns, text="取消", command=dlg.destroy).pack(side=tk.RIGHT, padx=4)
        dlg.after_idle(lambda: _show_centered_window(dlg, win, 1120, 760))

    def edit_mapping(rec):
        rule = find_rule(rec)
        fields = current_content_fields()
        dlg = _make_floating_child(win, "映射字段设置")
        body = ttk.Frame(dlg, padding=10)
        body.pack(fill=tk.BOTH, expand=True)
        mapping = rule.setdefault("mapping", {})
        field_var = tk.StringVar(value=mapping.get("content_field", fields[0] if fields else ""))
        ttk.Label(body, text=f"当前格：{rule.get('name')}").grid(row=0, column=0, columnspan=2, sticky=tk.W, padx=4, pady=4)
        ttk.Label(body, text=f"原值：{rec.get('text','')}").grid(row=1, column=0, columnspan=2, sticky=tk.W, padx=4, pady=4)
        ttk.Label(body, text="替换字段：").grid(row=2, column=0, sticky=tk.W, padx=4, pady=4)
        ttk.Combobox(body, textvariable=field_var, values=fields, width=36, state="normal").grid(row=2, column=1, sticky=tk.W, padx=4, pady=4)

        def on_ok():
            mapping["content_field"] = field_var.get().strip()
            state["preview_changes"] = {}
            refresh_rules()
            dlg.destroy()

        btns = ttk.Frame(body)
        btns.grid(row=3, column=0, columnspan=2, sticky=tk.E, pady=8)
        ttk.Button(btns, text="确定", command=on_ok).pack(side=tk.RIGHT, padx=4)
        ttk.Button(btns, text="取消", command=dlg.destroy).pack(side=tk.RIGHT, padx=4)
        dlg.after_idle(lambda: _show_centered_window(dlg, win))

    def _record_span(rec):
        return max(1, int(rec.get("row_span") or 1)), max(1, int(rec.get("col_span") or 1))

    def _add_region(kind, bbox, rec):
        state["cell_regions"].append((kind, bbox, rec))

    def render_group(group_name):
        canvas.delete("all")
        corner_canvas.delete("all")
        col_header_canvas.delete("all")
        row_header_canvas.delete("all")
        state["cell_regions"] = []
        group = state["groups"].get(group_name, {})
        records = [r for r in group.values() if r.get("is_merge_origin", True)]
        occupied_positions = {
            (_to_int(rec.get("row_index"), 0), _to_int(rec.get("col_index"), 0))
            for rec in records
        }
        for preview_change in state.get("preview_changes", {}).values():
            rec = preview_change.get("record") or {}
            position = (_to_int(rec.get("row_index"), 0), _to_int(rec.get("col_index"), 0))
            if (
                (rec.get("sheet_name") or "table_1") == group_name
                and position[0] > 0
                and position[1] > 0
                and position not in occupied_positions
            ):
                records.append(rec)
                occupied_positions.add(position)
        col_w = grid_col_w
        row_h = grid_row_h
        head_w = grid_head_w
        head_h = grid_head_h
        max_row = 0
        max_col = 0
        occupied = set()
        for rec in records:
            r = int(rec.get("row_index") or 0)
            c = int(rec.get("col_index") or 0)
            rs, cs = _record_span(rec)
            max_row = max(max_row, r + rs - 1)
            max_col = max(max_col, c + cs - 1)
            for rr in range(r, r + rs):
                for cc in range(c, c + cs):
                    occupied.add((rr, cc))
        max_row = max(max_row, max([r for r, _c in group.keys()] or [0]))
        max_col = max(max_col, max([c for _r, c in group.keys()] or [0]))

        corner_canvas.create_rectangle(0, 0, head_w, head_h, fill="#dfe7f1", outline="#c7ced8")
        for c in range(1, max_col + 1):
            x1 = (c - 1) * col_w
            x2 = x1 + col_w
            col_header_canvas.create_rectangle(x1, 0, x2, head_h, fill="#e8edf3", outline="#c7ced8")
            col_header_canvas.create_text((x1 + x2) / 2, head_h / 2, text=str(c), fill="#334155")
        for r in range(1, max_row + 1):
            y1 = (r - 1) * row_h
            y2 = y1 + row_h
            row_header_canvas.create_rectangle(0, y1, head_w, y2, fill="#e8edf3", outline="#c7ced8")
            row_header_canvas.create_text(head_w / 2, (y1 + y2) / 2, text=str(r), fill="#334155")
            for c in range(1, max_col + 1):
                if (r, c) in occupied:
                    continue
                x1 = (c - 1) * col_w
                x2 = x1 + col_w
                canvas.create_rectangle(x1, y1, x2, y2, fill="#ffffff", outline="#e3e8ef")

        for rec in records:
            r = int(rec.get("row_index") or 0)
            c = int(rec.get("col_index") or 0)
            if r <= 0 or c <= 0:
                continue
            rs, cs = _record_span(rec)
            x1 = (c - 1) * col_w
            y1 = (r - 1) * row_h
            x2 = (c - 1 + cs) * col_w
            y2 = (r - 1 + rs) * row_h
            is_merged = bool(rec.get("is_merged", False)) or rs > 1 or cs > 1
            preview_change = state.get("preview_changes", {}).get(_cell_key(rec))
            if preview_change:
                if preview_change.get("kind") == "联动写入":
                    fill = "#e0f2fe"
                    outline = "#0284c7"
                else:
                    fill = "#dcfce7"
                    outline = "#16a34a"
                border_width = 3
            else:
                fill = "#fff7df" if is_merged else "#ffffff"
                outline = "#f59e0b" if is_merged else "#cbd5e1"
                border_width = 2 if is_merged else 1
            canvas.create_rectangle(x1, y1, x2, y2, fill=fill, outline=outline, width=border_width)
            btn_y1 = y1 + 4
            btn_y2 = y1 + 24
            buttons = [("source", "源"), ("rule", "规则"), ("mapping", "字段")]
            bx = x1 + 5
            for kind, text in buttons:
                bw = 38 if kind == "source" else 48
                canvas.create_rectangle(bx, btn_y1, bx + bw, btn_y2, fill="#f1f5f9", outline="#94a3b8")
                canvas.create_text(bx + bw / 2, (btn_y1 + btn_y2) / 2, text=text, fill="#0f172a", font=("TkDefaultFont", 9))
                _add_region(kind, (bx, btn_y1, bx + bw, btn_y2), rec)
                bx += bw + 4
            display_text = _cell_text(rec.get("text", ""))
            if preview_change:
                label = _as_text(preview_change.get("kind")) or "替换预览"
                display_text = f"[{label}]\n{_canvas_preview_text(preview_change.get('new_text', ''))}"
            if is_merged:
                merge_note = rec.get("merged_range") or f"{rs}行x{cs}列"
                display_text = f"[合并 {merge_note}]\n{display_text}"
            canvas.create_text(x1 + 8, y1 + 32, anchor=tk.NW, text=display_text[:120], width=max(80, (x2 - x1) - 16), fill="#111827")
            if state.get("focused_cell_key") == _cell_key(rec):
                canvas.create_rectangle(x1 + 3, y1 + 3, x2 - 3, y2 - 3, outline="#2563eb", width=3)
            _add_region("cell", (x1, y1, x2, y2), rec)

        body_w = max_col * col_w + 20
        body_h = max_row * row_h + 20
        canvas.configure(scrollregion=(0, 0, body_w, body_h))
        col_header_canvas.configure(scrollregion=(0, 0, body_w, head_h))
        row_header_canvas.configure(scrollregion=(0, 0, head_w, body_h))
        canvas.update_idletasks()
        col_header_canvas.update_idletasks()
        row_header_canvas.update_idletasks()
        col_header_canvas.xview_moveto(canvas.xview()[0])
        row_header_canvas.yview_moveto(canvas.yview()[0])
        state["selected_group"] = group_name

    def _scroll_canvas_to_record(rec):
        try:
            r = int(rec.get("row_index") or 0)
            c = int(rec.get("col_index") or 0)
            rs, cs = _record_span(rec)
            canvas.update_idletasks()
            region = [float(v) for v in str(canvas.cget("scrollregion")).split()]
            if len(region) != 4:
                return
            _x0, _y0, body_w, body_h = region
            view_w = max(1, canvas.winfo_width())
            view_h = max(1, canvas.winfo_height())
            x_center = (c - 1 + cs / 2) * grid_col_w
            y_center = (r - 1 + rs / 2) * grid_row_h
            if body_w > view_w:
                x_frac = (x_center - view_w / 2) / max(1, body_w - view_w)
                x_frac = max(0.0, min(1.0, x_frac))
                canvas.xview_moveto(x_frac)
                col_header_canvas.xview_moveto(x_frac)
            if body_h > view_h:
                y_frac = (y_center - view_h / 2) / max(1, body_h - view_h)
                y_frac = max(0.0, min(1.0, y_frac))
                canvas.yview_moveto(y_frac)
                row_header_canvas.yview_moveto(y_frac)
        except Exception:
            pass

    def _select_group_in_list(group_name):
        for index in range(group_lb.size()):
            if group_lb.get(index) == group_name:
                group_lb.selection_clear(0, tk.END)
                group_lb.selection_set(index)
                group_lb.see(index)
                return True
        return False

    def _locate_rule_record_for_edit(rule):
        if not state.get("records"):
            reload_data()
        records = list(state.get("records", []) or [])
        if not records:
            return None, "当前文档读取表没有可定位记录"
        locator = rule.get("source_locator", {}) or {}
        source_file = _as_text(locator.get("source_file"))
        source_files = _source_files(records, params)
        if not source_file and len(source_files) == 1:
            source_file = source_files[0]
        by_file = {}
        for item in records:
            by_file.setdefault(item.get("source_file", ""), []).append(item)
        source_records = by_file.get(source_file, records if not source_file else [])
        rec, detail = _locate_target_record(rule, source_records, source_file)
        if rec is not None:
            return rec, detail
        sheet_name = _as_text(locator.get("sheet_name"))
        row_index = _to_int(locator.get("row_index"), 0)
        col_index = _to_int(locator.get("col_index"), 0)
        for item in records:
            if source_file and item.get("source_file", "") != source_file:
                continue
            if sheet_name and item.get("sheet_name", "") != sheet_name:
                continue
            if row_index > 0 and int(item.get("row_index") or 0) != row_index:
                continue
            if col_index > 0 and int(item.get("col_index") or 0) != col_index:
                continue
            return item, f"{detail}；已按原始坐标回退定位"
        return None, detail

    def _focus_record_in_canvas(rec):
        group_name = rec.get("sheet_name") or "table_1"
        if group_name not in state.get("groups", {}):
            return False, f"目标表格/Sheet 不存在：{group_name}"
        state["focused_cell_key"] = _cell_key(rec)
        _select_group_in_list(group_name)
        render_group(group_name)
        _scroll_canvas_to_record(rec)
        show_info(rec)
        return True, ""

    def edit_selected_rule():
        ref = selected_rule_ref()
        if not ref:
            return
        if ref["kind"] == "global_rules":
            manage_global_rules(ref["index"])
            return
        if ref["kind"] == "linked_rules":
            manage_linked_rules(ref["index"])
            return
        rule = ref["rule"]
        rec, detail = _locate_rule_record_for_edit(rule)
        if rec is None:
            name = _as_text(rule.get("name")) or _as_text(rule.get("id")) or "未命名规则"
            status_var.set(f"规则定位失败：{name}；{detail}")
            messagebox.showwarning("定位失败", f"无法定位这条普通映射规则对应的格子。\n\n{name}\n{detail}", parent=win)
            return
        ok, focus_msg = _focus_record_in_canvas(rec)
        if not ok:
            status_var.set(f"规则定位失败：{focus_msg}")
            messagebox.showwarning("定位失败", focus_msg, parent=win)
            return
        name = _as_text(rule.get("name")) or _as_text(rule.get("id")) or "未命名规则"
        status_var.set(f"已跳转并打开规则：{name}；{detail}")
        win.after_idle(lambda rec=rec, rule=rule: edit_rule(rec, rule))

    def on_canvas_click(event):
        x = canvas.canvasx(event.x)
        y = canvas.canvasy(event.y)
        # 优先命中按钮热区；整格热区覆盖范围更大，不能先抢走点击事件。
        for kind, bbox, rec in reversed(state.get("cell_regions", [])):
            if kind == "cell":
                continue
            x1, y1, x2, y2 = bbox
            if x1 <= x <= x2 and y1 <= y <= y2:
                show_info(rec)
                if kind == "source":
                    edit_source(rec)
                elif kind == "rule":
                    edit_rule(rec)
                    render_group(state.get("selected_group", ""))
                elif kind == "mapping":
                    edit_mapping(rec)
                    render_group(state.get("selected_group", ""))
                return
        for kind, bbox, rec in reversed(state.get("cell_regions", [])):
            if kind != "cell":
                continue
            x1, y1, x2, y2 = bbox
            if x1 <= x <= x2 and y1 <= y <= y2:
                show_info(rec)
                return

    def on_canvas_motion(event):
        x = canvas.canvasx(event.x)
        y = canvas.canvasy(event.y)
        cursor = ""
        for kind, bbox, _rec in reversed(state.get("cell_regions", [])):
            if kind == "cell":
                continue
            x1, y1, x2, y2 = bbox
            if x1 <= x <= x2 and y1 <= y <= y2:
                cursor = "hand2"
                break
        canvas.configure(cursor=cursor)

    def on_canvas_wheel(event):
        canvas.yview_scroll(-1 * int(event.delta / 120), "units")
        row_header_canvas.yview_moveto(canvas.yview()[0])
        return "break"

    def on_canvas_shift_wheel(event):
        canvas.xview_scroll(-1 * int(event.delta / 120), "units")
        col_header_canvas.xview_moveto(canvas.xview()[0])
        return "break"

    canvas.bind("<Button-1>", on_canvas_click)
    canvas.bind("<Motion>", on_canvas_motion)
    for wheel_widget in (canvas, row_header_canvas, col_header_canvas, corner_canvas):
        wheel_widget.bind("<MouseWheel>", on_canvas_wheel)
        wheel_widget.bind("<Shift-MouseWheel>", on_canvas_shift_wheel)

    def reload_data():
        params["doc_table_alias"] = doc_alias_var.get().strip() or "当前表"
        params["content_table_alias"] = content_alias_var.get().strip() or "新内容表"
        params["replace_aux_table_alias"] = aux_alias_var.get().strip() or "替换辅助表"
        params["config_name"] = config_name_var.get().strip() or "default"
        params["source_file_field"] = source_file_field_var.get().strip() or "source_file"
        params["planned_file_field"] = planned_file_field_var.get().strip() or "target_file"
        refresh_field_combos()
        doc_table = tables.get(params["doc_table_alias"], {})
        state["preview_changes"] = {}
        state["focused_cell_key"] = ""
        state["records"] = _doc_records(doc_table, params)
        state["groups"] = _group_doc_grid(state["records"])
        group_lb.delete(0, tk.END)
        for group_name in sorted(state["groups"].keys()):
            group_lb.insert(tk.END, group_name)
        if group_lb.size():
            group_lb.selection_set(0)
            render_group(group_lb.get(0))
        refresh_rules()
        status_var.set(f"读取 {len(state['records'])} 个单元格；规则 {len(cfg.get('rules', []))} 条；全局 {len(cfg.get('global_rules', []))} 条；联动 {len(cfg.get('linked_rules', []))} 条")

    def on_group_select(_event=None):
        sel = group_lb.curselection()
        if sel:
            render_group(group_lb.get(sel[0]))

    group_lb.bind("<<ListboxSelect>>", on_group_select)
    config_name_combo.bind("<<ComboboxSelected>>", lambda _e=None: load_config_by_name(config_name_var.get()))
    doc_alias_combo.bind("<<ComboboxSelected>>", lambda _e=None: (refresh_field_combos(), reload_data()))
    content_alias_combo.bind("<<ComboboxSelected>>", lambda _e=None: (refresh_field_combos(), reload_data()))
    aux_alias_combo.bind("<<ComboboxSelected>>", lambda _e=None: refresh_field_combos())

    bottom = ttk.Frame(win, padding=8)
    bottom.pack(fill=tk.X)

    result = {"ok": False, "params": params}

    def sync_params_from_ui():
        params["doc_table_alias"] = doc_alias_var.get().strip() or "当前表"
        params["content_table_alias"] = content_alias_var.get().strip() or "新内容表"
        params["replace_aux_table_alias"] = aux_alias_var.get().strip() or "替换辅助表"
        params["config_name"] = config_name_var.get().strip() or "default"
        params["source_file_field"] = source_file_field_var.get().strip() or "source_file"
        params["planned_file_field"] = planned_file_field_var.get().strip() or "target_file"

    def show_rule_replace_preview():
        sync_params_from_ui()
        if not state.get("records"):
            reload_data()
        records = list(state.get("records", []) or [])
        enabled_rules = [r for r in cfg.get("rules", []) if isinstance(r, dict) and r.get("enabled", True)]
        selected = rule_lb.curselection()
        selected_note = "全部普通映射规则"
        if selected and int(selected[0]) < len(enabled_rules):
            enabled_rules = [enabled_rules[int(selected[0])]]
            selected_note = f"选中规则：{enabled_rules[0].get('name', '')}"
        contents = current_content_rows()
        by_file = {}
        for item in records:
            by_file.setdefault(item.get("source_file", ""), []).append(item)
        source_files = _source_files(records, params)
        empty_policy = _as_text(params.get("empty_policy", "跳过")) or "跳过"

        dlg = _make_floating_child(win, "规则替换预览")
        body = ttk.Frame(dlg, padding=10)
        body.pack(fill=tk.BOTH, expand=True)
        body.rowconfigure(1, weight=1)
        body.columnconfigure(0, weight=1)
        header_var = tk.StringVar(value="")
        ttk.Label(body, textvariable=header_var, foreground="gray").grid(row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 6))
        txt = tk.Text(body, height=32, width=128, wrap=tk.WORD)
        txt.grid(row=1, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(body, orient=tk.VERTICAL, command=txt.yview)
        scroll.grid(row=1, column=1, sticky="ns")
        txt.configure(yscrollcommand=scroll.set)

        generated = []
        skipped_items = []

        def add_skip(rule, content, note, source_file="", rec=None):
            skipped_items.append({
                "rule": rule,
                "content": content,
                "note": note,
                "source_file": source_file,
                "rec": rec,
            })

        if not records:
            header_var.set("可生成 0 条；文档读取表没有记录")
            txt.insert(tk.END, "当前文档读取表没有可预览记录，请先刷新可视化。\n")
        elif not enabled_rules:
            header_var.set("可生成 0 条；没有启用的普通映射规则")
            txt.insert(tk.END, "已配置规则中没有启用的普通映射规则。若只配置了全局规则，请使用“全局替换预览”。\n")
        elif not contents:
            header_var.set("可生成 0 条；新内容表没有记录")
            txt.insert(tk.END, "当前新内容表没有可用于替换的行。\n")
        else:
            for content_index, content in enumerate(contents):
                source_file, source_note = _source_file_for_content(content, source_files, content_index, len(contents), params)
                if not source_file and source_files != [""]:
                    for rule in enabled_rules:
                        add_skip(rule, content, source_note)
                    continue
                target_file = _target_file_for_content(content, params, source_file)
                if not target_file:
                    for rule in enabled_rules:
                        add_skip(rule, content, f"拟定新文件字段为空：{_planned_file_field(params)}；源文件选择={source_note}", source_file)
                    continue
                source_records = by_file.get(source_file, [])
                for rule in enabled_rules:
                    locator = rule.get("source_locator", {}) or {}
                    feature_ok, feature_detail = _feature_pass(rule.get("feature_name", ""), cfg.get("features", []), source_records, source_file, _as_text(locator.get("sheet_name")))
                    if not feature_ok:
                        add_skip(rule, content, feature_detail, source_file)
                        continue
                    rec, anchor_detail = _locate_target_record(rule, source_records, source_file, content=content, table_context=current_table_context())
                    if rec is None:
                        add_skip(rule, content, anchor_detail, source_file)
                        continue
                    ok, match_detail = _match_text_with_sources(
                        rec.get("text", ""),
                        rule.get("source_match", {}),
                        content=content,
                        table_context=current_table_context(),
                        doc_record=rec,
                        source_records=source_records,
                    )
                    if not ok:
                        add_skip(rule, content, f"输入源内容匹配未通过：{match_detail}", source_file, rec)
                        continue
                    mapping = rule.get("mapping", {}) or {}
                    field = _as_text(mapping.get("content_field") or mapping.get("field"))
                    if not field:
                        add_skip(rule, content, "未选择映射字段", source_file, rec)
                        continue
                    field_exists = field in content
                    value = _cell_text(content.get(field))
                    if value == "" and empty_policy == "跳过":
                        note = "映射字段为空，按策略跳过"
                        if not field_exists:
                            note = f"映射字段不存在：{field}，按空值跳过"
                        add_skip(rule, content, note, source_file, rec)
                        continue
                    if value == "" and empty_policy == "报错":
                        note = f"映射字段为空会报错：{field}"
                        if not field_exists:
                            note = f"映射字段不存在会报错：{field}"
                        add_skip(rule, content, note, source_file, rec)
                        continue
                    generated.append({
                        "rule": rule,
                        "content": content,
                        "source_file": source_file,
                        "target_file": target_file,
                        "rec": rec,
                        "field": field,
                        "field_exists": field_exists,
                        "value": value,
                        "source_note": source_note,
                        "feature_detail": feature_detail,
                        "match_detail": match_detail,
                        "anchor_detail": anchor_detail,
                    })

            header_var.set(f"{selected_note}；可生成 {len(generated)} 条；跳过 {len(skipped_items)} 条；新内容行 {len(contents)}；源文件 {len(source_files)}")
            if generated:
                txt.insert(tk.END, "可生成写入计划：\n")
                for item in generated[:300]:
                    rec = item["rec"]
                    rule = item["rule"]
                    same_note = "；注意：新值与原文相同" if item["value"] == rec.get("text", "") else ""
                    field_note = "" if item["field_exists"] else "；注意：字段不存在，当前按空字符串处理"
                    txt.insert(
                        tk.END,
                        f"[生成] {rule.get('name','')}  {rec.get('sheet_name','')} R{rec.get('row_index')}C{rec.get('col_index')}  新内容行{item['content'].get('__content_row__','')}\n"
                        f"源文件：{item['source_file']}\n"
                        f"目标文件：{item['target_file']}\n"
                        f"原文：{rec.get('text','')}\n"
                        f"替换：{item['value']}\n"
                        f"字段：{item['field']}{field_note}{same_note}\n"
                        f"明细：源文件选择={item['source_note']}；{item['feature_detail']}；{item['match_detail']}；{item['anchor_detail']}\n\n"
                    )
                if len(generated) > 300:
                    txt.insert(tk.END, f"... 还有 {len(generated) - 300} 条生成结果未显示。\n\n")
            else:
                txt.insert(tk.END, "没有生成任何写入计划。\n\n")
            if skipped_items:
                txt.insert(tk.END, "跳过明细：\n")
                for item in skipped_items[:300]:
                    rec = item.get("rec")
                    location = f"{rec.get('sheet_name','')} R{rec.get('row_index')}C{rec.get('col_index')}" if rec else ""
                    txt.insert(
                        tk.END,
                        f"[跳过] {item['rule'].get('name','')} {location} 新内容行{item['content'].get('__content_row__','')}\n"
                        f"原因：{item['note']}\n"
                        f"源文件：{item.get('source_file','')}\n\n"
                    )
                if len(skipped_items) > 300:
                    txt.insert(tk.END, f"... 还有 {len(skipped_items) - 300} 条跳过明细未显示。\n")

        txt.configure(state="disabled")
        buttons = ttk.Frame(body)
        buttons.grid(row=2, column=0, columnspan=2, sticky=tk.E, pady=(8, 0))
        ttk.Button(buttons, text="关闭", command=dlg.destroy).pack(side=tk.RIGHT, padx=4)
        dlg.after_idle(lambda: _show_centered_window(dlg, win, 1120, 720))

    def save_current_config():
        sync_params_from_ui()
        _save_config(params, context, cfg)
        refresh_config_combo()
        refresh_rules()
        messagebox.showinfo("保存完成", "映射配置已保存", parent=win)

    def save_and_close():
        sync_params_from_ui()
        _save_config(params, context, cfg)
        refresh_config_combo()
        result["ok"] = True
        result["params"] = params
        win.destroy()

    ttk.Button(bottom, text="刷新可视化", command=reload_data).pack(side=tk.LEFT, padx=4)
    ttk.Button(bottom, text="保存配置", command=save_current_config).pack(side=tk.LEFT, padx=4)
    ttk.Button(bottom, text="确定", command=save_and_close).pack(side=tk.RIGHT, padx=4)
    ttk.Button(bottom, text="取消", command=win.destroy).pack(side=tk.RIGHT, padx=4)
    ttk.Button(bottom, text="规则替换预览", command=show_rule_replace_preview).pack(side=tk.RIGHT, padx=4)
    ttk.Button(bottom, text="高亮替换预览", command=apply_visual_preview_highlight).pack(side=tk.RIGHT, padx=4)
    ttk.Button(bottom, text="清除高亮", command=clear_visual_preview_highlight).pack(side=tk.RIGHT, padx=4)

    reload_data()
    _show_centered_window(win, parent, CONFIG_WINDOW_WIDTH, CONFIG_WINDOW_HEIGHT)
    win.grab_set()
    win.wait_window()
    return result["params"] if result.get("ok") else current_params


def _external_progress_callback(msg):
    try:
        text = json.dumps(msg, ensure_ascii=False) + "\n"
        sys.stdout.buffer.write(text.encode("utf-8"))
        sys.stdout.buffer.flush()
    except Exception:
        pass


def _run_external_entry(input_path, output_path):
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        payload = json.loads(Path(input_path).read_text(encoding="utf-8"))
        input_data = payload.get("input_data") or {}
        params = payload.get("params") or {}
        context = payload.get("context") or {}
        context.setdefault("plugin_id", PLUGIN_INFO["id"])
        context["progress_callback"] = _external_progress_callback
        context["report_progress"] = lambda current=0, total=0, message="", **extra: _external_progress_callback({
            "type": "progress",
            "current": current,
            "total": total,
            "message": message,
            **extra,
        })
        result = run(input_data, params, context)
    except Exception as exc:
        result = {
            "ok": False,
            "message": str(exc),
            "output": {"type": "table", "headers": ["错误"], "rows": [[str(exc)]], "meta": {"plugin": PLUGIN_INFO["id"]}},
            "logs": [{"level": "ERROR", "message": str(exc)}, {"level": "ERROR", "message": traceback.format_exc()}],
            "summary": {"success": 0, "failed": 1},
        }
    output_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if result.get("ok", False) else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=PLUGIN_INFO["name"])
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_path")
    args = parser.parse_args(argv)
    if args.input_path and args.output_path:
        return _run_external_entry(args.input_path, args.output_path)
    print("这是 DataFlowKit 插件，请在主程序插件节点中调用。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
