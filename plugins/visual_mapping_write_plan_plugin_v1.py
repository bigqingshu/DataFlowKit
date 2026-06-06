# -*- coding: utf-8 -*-
import argparse
import copy
import json
import re
import sys
import traceback
from pathlib import Path

try:
    import tkinter as tk
    from tkinter import messagebox, simpledialog, ttk
except Exception:  # pragma: no cover
    tk = None
    ttk = None
    messagebox = None
    simpledialog = None


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
FEATURE_ANY_LABEL = "不限制"
SHEET_ALL_LABEL = "所有表"


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


def _as_text(value):
    return "" if value is None else str(value).strip()


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
    return dlg


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
    return {"rules": [], "features": [], "global_rules": []}


def _ensure_config(cfg):
    if not isinstance(cfg, dict):
        cfg = {}
    cfg.setdefault("rules", [])
    cfg.setdefault("features", [])
    cfg.setdefault("global_rules", [])
    return cfg


def _load_settings(context):
    path = _settings_path(context)
    if not path.exists():
        return {"version": 1, "configs": {"default": _empty_config()}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("settings root must be object")
        data.setdefault("version", 1)
        data.setdefault("configs", {})
        data["configs"].setdefault("default", _empty_config())
        for name, cfg in list(data["configs"].items()):
            data["configs"][name] = _ensure_config(cfg)
        return data
    except Exception:
        return {"version": 1, "configs": {"default": _empty_config()}}


def _save_settings(context, data):
    path = _settings_path(context)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
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
    text = _as_text(d.get("text") if "text" in d else d.get("内容"))
    meta = _parse_meta_json(d.get("meta_json"))
    is_merged = _truthy(d.get("is_merged", meta.get("is_merged", False)))
    is_merge_origin = not is_merged or _truthy(d.get("is_merge_origin", meta.get("is_merge_origin", True)))
    row_span = max(1, _to_int(d.get("row_span", meta.get("row_span", 1)), 1))
    col_span = max(1, _to_int(d.get("col_span", meta.get("col_span", 1)), 1))
    merge_origin_row = _to_int(d.get("merge_origin_row", meta.get("merge_origin_row", row_index)), row_index)
    merge_origin_col = _to_int(d.get("merge_origin_col", meta.get("merge_origin_col", col_index)), col_index)
    merged_range = _as_text(d.get("merged_range") or meta.get("merged_range", ""))
    if not sheet_name:
        sheet_name = "table_1" if block_type.startswith("word_table") else "Sheet1"
    return {
        "raw": d,
        "meta": meta,
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


def _match_text(text, match_cfg):
    cfg = match_cfg or {}
    if not cfg.get("enabled", False):
        return True, "未启用输入源匹配"
    mode = _as_text(cfg.get("mode") or cfg.get("operator") or "包含") or "包含"
    value = _as_text(cfg.get("value"))
    text = _as_text(text)
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


def _cell_key(record):
    return f"{record.get('source_file','')}|{record.get('sheet_name','')}|{record.get('row_index','')}|{record.get('col_index','')}"


def _build_doc_index(records):
    index = {}
    by_file_sheet = {}
    for rec in records:
        index[_cell_key(rec)] = rec
        fs = (rec.get("source_file", ""), rec.get("sheet_name", ""))
        by_file_sheet.setdefault(fs, []).append(rec)
    return index, by_file_sheet


def _match_anchor(records, anchor_cfg):
    cfg = anchor_cfg or {}
    if not cfg.get("enabled", False):
        return None, "未启用锚点"
    axis = _as_text(cfg.get("axis", "列")) or "列"
    index = _to_int(cfg.get("index"), 0)
    if index <= 0:
        return None, "锚点行/列未设置"
    candidates = []
    for rec in records:
        if axis in ("列", "column") and int(rec.get("col_index") or 0) != index:
            continue
        if axis in ("行", "row") and int(rec.get("row_index") or 0) != index:
            continue
        ok, detail = _match_text(rec.get("text", ""), {
            "enabled": True,
            "mode": cfg.get("match_mode", "等于"),
            "value": cfg.get("value", ""),
        })
        if ok:
            candidates.append(rec)
    if not candidates:
        return None, "锚点未命中"
    return candidates[0], f"锚点命中 {len(candidates)} 个，使用第一个"


def _locate_target_record(rule, source_records, source_file):
    locator = rule.get("source_locator", {}) or {}
    sheet_name = _as_text(locator.get("sheet_name"))
    base_row = _to_int(locator.get("row_index"), 0)
    base_col = _to_int(locator.get("col_index"), 0)
    records = [r for r in source_records if (not sheet_name or r.get("sheet_name") == sheet_name)]
    anchor_cfg = rule.get("anchor", {}) or {}
    anchor_detail = "未启用锚点"
    if anchor_cfg.get("enabled", False):
        anchor_rec, anchor_detail = _match_anchor(records, anchor_cfg)
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
        return match.span(0), _as_text(match.group(0)), "0"
    try:
        if match.lastindex and group_index <= match.lastindex and match.start(group_index) >= 0:
            return match.span(group_index), _as_text(match.group(group_index)), str(group_index)
    except Exception:
        pass
    try:
        if match.lastindex:
            for index in range(1, match.lastindex + 1):
                if match.start(index) >= 0:
                    return match.span(index), _as_text(match.group(index)), str(index)
    except Exception:
        pass
    return match.span(0), _as_text(match.group(0)), "0"


def _condition_extract_items(text, conditions, default_logic="AND"):
    ok, detail = _match_condition_chain(text, conditions, default_logic)
    text = _as_text(text)
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
                    "full_match": _as_text(match.group(0)),
                    "group": used_group,
                })
        except Exception as exc:
            return False, f"{detail}；条件提取异常：{exc}", []
        if regex_items:
            return True, detail, regex_items
    return True, detail, [{"span": (0, len(text)), "value": text, "note": "条件命中，使用全文"}]


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
    template = _as_text(text)

    def replace_match(match):
        key = _as_text(match.group(1))
        return _as_text(content.get(key, match.group(0)))

    return re.sub(r"\{([^{}]+)\}", replace_match, template)


def _normalize_batch_value_source(value):
    text = _as_text(value) or "手动输入"
    if text in ("辅助表字段", "辅助表", "aux_field", "列字段"):
        return "辅助表字段"
    if text in ("辅助表固定值", "aux_fixed"):
        return "辅助表固定值"
    if text in ("新内容字段", "内容字段", "content_field"):
        return "新内容字段"
    return "手动输入"


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


def _batch_template_context(content, aux_row=None, extract=None):
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
    return data


def _iter_batch_rule_pairs(rule, content, aux_rows, extract):
    source = _normalize_batch_value_source(rule.get("value_source"))
    if source in ("辅助表字段", "辅助表固定值"):
        match_field = _as_text(rule.get("match_value_field"))
        replace_field = _as_text(rule.get("replace_value_field"))
        if not match_field:
            raise ValueError("未设置辅助表匹配值字段")
        if source == "辅助表字段" and not replace_field:
            raise ValueError("未设置辅助表替换值字段")
        skipped = 0
        for aux_row in aux_rows or []:
            match_value = _as_text((aux_row or {}).get(match_field))
            if not match_value and bool(rule.get("skip_empty_match_value", True)):
                skipped += 1
                continue
            if source == "辅助表字段":
                replace_value = _as_text((aux_row or {}).get(replace_field))
            else:
                replace_value = _expand_template(rule.get("replace_value", ""), _batch_template_context(content, aux_row, extract))
            yield match_value, replace_value, f"辅助表 {match_field}->{replace_field or '固定值'}", skipped
        return
    if source == "新内容字段":
        match_field = _as_text(rule.get("match_value_field"))
        replace_field = _as_text(rule.get("replace_value_field"))
        match_value = _as_text((content or {}).get(match_field))
        if not match_value and bool(rule.get("skip_empty_match_value", True)):
            return
        replace_value = _as_text((content or {}).get(replace_field))
        yield match_value, replace_value, f"新内容字段 {match_field}->{replace_field}", 0
        return
    yield _as_text(rule.get("match_value")), _expand_template(rule.get("replace_value", ""), _batch_template_context(content, None, extract)), "手动输入", 0


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
            "match_value": _as_text(step.get("pattern") or step.get("regex")),
            "replace_value": replace_value,
            "replace_mode": "局部替换匹配字符串",
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


def _apply_batch_rules_to_value(value, rules, content, aux_rows, extract):
    text = _as_text(value)
    valid_rules = [r for r in (rules or []) if isinstance(r, dict) and r.get("enabled", True)]
    if not valid_rules:
        return text, "未设置批量替换规则", None
    details = []
    for index, rule in enumerate(valid_rules, start=1):
        match_mode = _as_text(rule.get("match_mode")) or "包含"
        replace_mode = _as_text(rule.get("replace_mode")) or "局部替换匹配字符串"
        case_sensitive = bool(rule.get("case_sensitive", True))
        count = _to_int(rule.get("count"), 0)
        rule_changed = 0
        pair_count = 0
        skipped_empty = 0
        try:
            pairs = list(_iter_batch_rule_pairs(rule, content, aux_rows, extract))
        except Exception as exc:
            return text, "；".join(details), f"批量替换规则{index}异常：{exc}"
        source_note = _normalize_batch_value_source(rule.get("value_source"))
        for match_value, replace_value, current_source_note, skipped in pairs:
            pair_count += 1
            source_note = current_source_note
            skipped_empty = max(skipped_empty, skipped)
            try:
                if not _compare_batch_text(text, match_value, match_mode, case_sensitive):
                    continue
                text, replaced = _replace_batch_text(text, match_value, replace_value, match_mode, replace_mode, case_sensitive, count)
            except Exception as exc:
                return text, "；".join(details), f"批量替换规则{index}异常：{exc}"
            rule_changed += replaced
        detail = f"批量规则{index} {match_mode}/{replace_mode}，来源{source_note}，替换{rule_changed}次"
        if skipped_empty:
            detail += f"，跳过空匹配值{skipped_empty}行"
        if pair_count == 0:
            detail += "，无可用匹配值"
        details.append(detail)
    return text, "；".join(details), None


def _apply_replace_steps(old_text, rule, content, aux_rows=None, condition_items=None):
    text = _as_text(old_text)
    rule = rule or {}
    batch_rules = _batch_rules_for_rule(rule)
    if condition_items is None:
        cond_ok, cond_detail, condition_items = _condition_extract_items(text, rule.get("conditions", []), rule.get("condition_logic", "AND"))
        if not cond_ok:
            return text, cond_detail, None
    condition_items = [item for item in (condition_items or []) if isinstance(item, dict)]
    if not condition_items:
        return text, "匹配条件未提取到可替换值", None
    parts = []
    last_pos = 0
    extracted = 0
    changed = 0
    detail_items = []
    for item in condition_items:
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
        value = _as_text(item.get("value"))
        extract = {
            "提取内容": value,
            "匹配值": value,
            "完整匹配": _as_text(item.get("full_match", value)),
            "原文": text,
            "序号": extracted,
            "group": _as_text(item.get("group", "")),
            "组": _as_text(item.get("group", "")),
        }
        new_value, batch_detail, batch_error = _apply_batch_rules_to_value(value, batch_rules, content, aux_rows or [], extract)
        if batch_error:
            return old_text, "；".join(detail_items), batch_error
        parts.append(text[last_pos:start])
        parts.append(new_value)
        last_pos = end
        if new_value != value:
            changed += 1
        detail_items.append(f"{item.get('note', '条件命中值')}：{value} -> {new_value}；{batch_detail}")
    parts.append(text[last_pos:])
    return "".join(parts), f"条件提取 {extracted} 条，回填变化 {changed} 条；" + "；".join(detail_items[:10]), None


def _global_rule_fields(rule):
    fields = []
    for item in _batch_rules_for_rule(rule):
        if not isinstance(item, dict):
            continue
        value_source = _normalize_batch_value_source(item.get("value_source"))
        match_field = _as_text(item.get("match_value_field"))
        replace_field = _as_text(item.get("replace_value_field"))
        if value_source == "新内容字段":
            label = f"新内容:{match_field}->{replace_field}"
        elif value_source in ("辅助表字段", "辅助表固定值"):
            label = f"辅助表:{match_field}->{replace_field or '固定值'}"
        else:
            label = f"固定规则:{_as_text(item.get('match_value'))}"
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
                    values = "；".join([_as_text(item.get("value")) for item in condition_items[:8]]) or rec.get("text", "")
                    preview_rows.append({
                        "rule_name": _as_text(rule.get("name")),
                        "source_file": source_file,
                        "location": f"{rec.get('sheet_name','')} R{rec.get('row_index')}C{rec.get('col_index')}",
                        "old_text": rec.get("text", ""),
                        "new_text": values,
                        "content_row": "",
                        "detail": f"{feature_detail}；{cond_detail}；命中值={values}",
                        "status": "条件命中",
                    })
    return preview_rows, total_matched, 0


def _preview_global_replace_rows(global_rules, records, features, contents, aux_rows, params, limit=500, include_unchanged=True):
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
    for rule in rules:
        for content_index, content in enumerate(contents):
            source_file, source_note = _source_file_for_content(content, source_files, content_index, len(contents), params)
            if not source_file and source_files != [""]:
                total_errors += 1
                if len(preview_rows) < limit:
                    preview_rows.append({
                        "rule_name": _as_text(rule.get("name")),
                        "source_file": "",
                        "location": "",
                        "old_text": "",
                        "new_text": "",
                        "content_row": content.get("__content_row__", ""),
                        "detail": source_note,
                        "status": "跳过",
                    })
                continue
            target_file = _target_file_for_content(content, params, source_file)
            source_records = by_file.get(source_file, [])
            for rec in _global_rule_records(rule, source_records):
                feature_ok, feature_detail = _feature_pass(rule.get("feature_name", ""), features, source_records, source_file, rec.get("sheet_name", ""))
                if not feature_ok:
                    continue
                cond_ok, cond_detail, condition_items = _condition_extract_items(rec.get("text", ""), rule.get("conditions", []), rule.get("condition_logic", "AND"))
                if not cond_ok:
                    continue
                new_text, replace_detail, replace_error = _apply_replace_steps(rec.get("text", ""), rule, content, aux_rows, condition_items)
                if replace_error:
                    total_errors += 1
                    if len(preview_rows) < limit:
                        preview_rows.append({
                            "rule_name": _as_text(rule.get("name")),
                            "source_file": source_file,
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
                        "location": f"{rec.get('sheet_name','')} R{rec.get('row_index')}C{rec.get('col_index')}",
                        "old_text": rec.get("text", ""),
                        "new_text": new_text,
                        "content_row": content.get("__content_row__", ""),
                        "detail": f"{feature_detail}；{cond_detail}；{replace_detail}；目标文件={target_file}；源文件选择={source_note}",
                        "status": "替换",
                    })
    return preview_rows, total_changed, total_errors


def validate_params(params, input_data, context):
    doc_alias = _as_text((params or {}).get("doc_table_alias", "当前表")) or "当前表"
    content_alias = _as_text((params or {}).get("content_table_alias", "新内容表")) or "新内容表"
    tables = _all_tables(input_data, context)
    if doc_alias not in tables:
        return False, f"未找到文档读取表别名：{doc_alias}"
    if content_alias not in tables:
        return False, f"未找到新内容表别名：{content_alias}"
    return True, ""


def run(input_data, params, context):
    params = dict(params or {})
    doc_table, doc_alias = _pick_table(input_data, context, params.get("doc_table_alias", "当前表"), "当前表")
    content_table, content_alias = _pick_table(input_data, context, params.get("content_table_alias", "新内容表"), "")
    aux_table, aux_alias = _pick_optional_table(input_data, context, params.get("replace_aux_table_alias", "替换辅助表"))
    config_name, cfg, settings = _get_config(params, context)
    rules = [r for r in cfg.get("rules", []) if isinstance(r, dict) and r.get("enabled", True)]
    features = [f for f in cfg.get("features", []) if isinstance(f, dict)]
    global_rules = [r for r in cfg.get("global_rules", []) if isinstance(r, dict) and r.get("enabled", True)]
    debug_output = bool(params.get("debug_output", False))
    empty_policy = _as_text(params.get("empty_policy", "跳过")) or "跳过"
    content_fields, contents = _content_rows(content_table)
    aux_fields, aux_rows = _content_rows(aux_table)
    records = _doc_records(doc_table, params)
    by_file = {}
    for rec in records:
        by_file.setdefault(rec.get("source_file", ""), []).append(rec)
    source_files = _source_files(records, params)

    out_headers = [
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
    ]
    out_rows = []
    logs = []
    skipped = 0
    matched = 0

    if not rules and not global_rules:
        return {
            "ok": True,
            "message": "未配置映射规则或全局搜索替换规则，未生成写入计划",
            "output": {"type": "table", "headers": out_headers, "rows": [], "meta": {"plugin": PLUGIN_INFO["id"]}},
            "logs": [{"level": "WARNING", "message": "请先打开插件自带设置窗口配置单元格映射规则或全局搜索替换规则"}],
            "summary": {"rules": 0, "global_rules": 0, "output_rows": 0, "doc_table": doc_alias, "content_table": content_alias},
        }

    total = max(1, len(contents) * max(1, len(rules) + len(global_rules)))
    current = 0
    progress = (context or {}).get("report_progress")

    def add_debug_row(note, rule, content, source_file="", rec=None, status="跳过"):
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
        ])

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
            rec, anchor_detail = _locate_target_record(rule, source_records, source_file)
            if rec is None:
                skipped += 1
                add_debug_row(anchor_detail, rule, content, source_file)
                continue
            ok, match_detail = _match_text(rec.get("text", ""), rule.get("source_match", {}))
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
            value = _as_text(content.get(field))
            if value == "" and empty_policy == "跳过":
                skipped += 1
                add_debug_row("映射字段为空，按策略跳过", rule, content, source_file, rec)
                continue
            if value == "" and empty_policy == "报错":
                raise ValueError(f"映射字段为空：{field}，新内容行 {content.get('__content_row__')}")
            matched += 1
            out_rows.append([
                source_file,
                target_file,
                rec.get("block_type", ""),
                rec.get("sheet_name", ""),
                rec.get("row_index", ""),
                rec.get("col_index", ""),
                rec.get("cell_address", ""),
                value,
                rec.get("text", ""),
                field,
                content.get("__content_row__", ""),
                "通过",
                rule.get("name", ""),
                json.dumps(rule.get("anchor", {}), ensure_ascii=False),
                f"{feature_detail}；{match_detail}",
                anchor_detail,
                f"已生成写入计划；源文件选择={source_note}",
            ])

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
                cond_ok, cond_detail, condition_items = _condition_extract_items(rec.get("text", ""), global_rule.get("conditions", []), global_rule.get("condition_logic", "AND"))
                if not cond_ok:
                    continue
                value, replace_detail, replace_error = _apply_replace_steps(rec.get("text", ""), global_rule, content, aux_rows, condition_items)
                if replace_error:
                    skipped += 1
                    add_debug_row(replace_error, global_rule, content, source_file, rec)
                    continue
                if value == rec.get("text", ""):
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
                out_rows.append([
                    source_file,
                    target_file,
                    rec.get("block_type", ""),
                    rec.get("sheet_name", ""),
                    rec.get("row_index", ""),
                    rec.get("col_index", ""),
                    rec.get("cell_address", ""),
                    value,
                    rec.get("text", ""),
                    _global_rule_fields(global_rule),
                    content.get("__content_row__", ""),
                    "通过",
                    f"全局:{global_rule.get('name', '')}",
                    "",
                    f"{feature_detail}；{cond_detail}",
                    "",
                    f"全局搜索替换；{replace_detail}；源文件选择={source_note}",
                ])
            if rule_hit == 0:
                skipped += 1
                add_debug_row("全局规则未命中任何可替换记录", global_rule, content, source_file, status="跳过")

    logs.append({"level": "INFO", "message": f"配置={config_name}，单元格规则 {len(rules)} 条，全局规则 {len(global_rules)} 条，生成 {matched} 条，跳过 {skipped} 条"})
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
            "content_rows": len(contents),
            "replace_aux_rows": len(aux_rows),
            "source_files": len(source_files),
            "output_rows": len(out_rows),
            "matched": matched,
            "skipped": skipped,
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
    win.transient(parent)
    maximize_text = tk.StringVar(value="最大化")
    maximize_state = {"geometry": ""}

    def toggle_maximize():
        try:
            if win.state() == "zoomed":
                win.state("normal")
                if maximize_state.get("geometry"):
                    win.geometry(maximize_state["geometry"])
                maximize_text.set("最大化")
            else:
                maximize_state["geometry"] = win.geometry()
                win.state("zoomed")
                maximize_text.set("还原")
        except Exception:
            try:
                if not maximize_state.get("geometry"):
                    maximize_state["geometry"] = win.geometry()
                sw = win.winfo_screenwidth()
                sh = win.winfo_screenheight()
                if maximize_text.get() == "最大化":
                    win.geometry(f"{sw}x{sh}+0+0")
                    maximize_text.set("还原")
                else:
                    win.geometry(maximize_state.get("geometry", "1180x760"))
                    maximize_text.set("最大化")
            except Exception:
                pass

    top = ttk.Frame(win, padding=8)
    top.pack(fill=tk.X)
    ttk.Button(top, textvariable=maximize_text, command=toggle_maximize).pack(side=tk.RIGHT, padx=4)
    ttk.Label(top, text="文档读取表：").pack(side=tk.LEFT)
    doc_alias_var = tk.StringVar(value=params.get("doc_table_alias", "当前表"))
    doc_alias_combo = ttk.Combobox(top, textvariable=doc_alias_var, values=table_aliases, width=18, state="readonly")
    doc_alias_combo.pack(side=tk.LEFT, padx=4)
    ttk.Label(top, text="新内容表：").pack(side=tk.LEFT, padx=(12, 0))
    content_alias_var = tk.StringVar(value=params.get("content_table_alias", "新内容表"))
    content_alias_combo = ttk.Combobox(top, textvariable=content_alias_var, values=table_aliases, width=18, state="readonly")
    content_alias_combo.pack(side=tk.LEFT, padx=4)
    ttk.Label(top, text="替换辅助表：").pack(side=tk.LEFT, padx=(12, 0))
    aux_alias_var = tk.StringVar(value=params.get("replace_aux_table_alias", "替换辅助表"))
    aux_alias_combo = ttk.Combobox(top, textvariable=aux_alias_var, values=table_aliases, width=18, state="readonly")
    aux_alias_combo.pack(side=tk.LEFT, padx=4)
    ttk.Label(top, text="配置名：").pack(side=tk.LEFT, padx=(12, 0))
    config_name_var = tk.StringVar(value=params.get("config_name", config_name))
    config_name_combo = ttk.Combobox(top, textvariable=config_name_var, values=sorted((settings.get("configs") or {}).keys()), width=18, state="normal")
    config_name_combo.pack(side=tk.LEFT, padx=4)
    ttk.Button(top, text="管理配置", command=lambda: manage_configs()).pack(side=tk.LEFT, padx=4)
    ttk.Button(top, text="管理表特征", command=lambda: manage_features()).pack(side=tk.LEFT, padx=4)
    ttk.Button(top, text="全局搜索替换规则窗口", command=lambda: manage_global_rules()).pack(side=tk.LEFT, padx=4)

    status_var = tk.StringVar(value="")
    ttk.Label(top, textvariable=status_var, foreground="gray").pack(side=tk.LEFT, padx=10)

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
    group_lb = tk.Listbox(left, height=18, exportselection=False)
    group_lb.pack(fill=tk.BOTH, expand=True)

    ttk.Label(right, text="当前格信息").pack(anchor=tk.W)
    info_text = tk.Text(right, height=14, width=36)
    info_text.pack(fill=tk.X, pady=4)
    ttk.Label(right, text="已配置规则").pack(anchor=tk.W, pady=(8, 0))
    rule_lb = tk.Listbox(right, height=15, exportselection=False)
    rule_lb.pack(fill=tk.BOTH, expand=True)

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

    state = {"records": [], "groups": {}, "selected_group": "", "selected_rec": None, "cell_regions": []}

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
        lb = tk.Listbox(body, height=12, width=36, exportselection=False)
        lb.grid(row=0, column=0, rowspan=6, sticky="nsew", padx=4, pady=4)
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

        feature_lb = tk.Listbox(left_panel, height=18, width=28, exportselection=False)
        feature_lb.pack(fill=tk.BOTH, expand=True)
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
        cond_tree = ttk.Treeview(right_panel, columns=columns, show="headings", height=8)
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
        cond_tree.grid(row=5, column=0, columnspan=3, sticky="nsew", pady=(6, 4))
        cond_scroll = ttk.Scrollbar(right_panel, orient=tk.VERTICAL, command=cond_tree.yview)
        cond_scroll.grid(row=5, column=3, sticky="ns", pady=(6, 4))
        cond_tree.configure(yscrollcommand=cond_scroll.set)

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

    def manage_global_rules():
        cfg.setdefault("global_rules", [])
        dlg = _make_floating_child(win, "全局搜索替换规则窗口")
        body = ttk.Frame(dlg, padding=10)
        body.pack(fill=tk.BOTH, expand=True)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        left_panel = ttk.Frame(body)
        left_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        right_panel = ttk.Frame(body)
        right_panel.grid(row=0, column=1, sticky="nsew")
        right_panel.columnconfigure(1, weight=1)
        right_panel.rowconfigure(7, weight=1)
        right_panel.rowconfigure(11, weight=1)
        preview_panel = ttk.Frame(body)
        preview_panel.grid(row=0, column=2, sticky="nsew", padx=(8, 0))
        preview_panel.columnconfigure(0, weight=1)
        preview_panel.rowconfigure(1, weight=1)

        rule_list = tk.Listbox(left_panel, height=22, width=32, exportselection=False)
        rule_list.pack(fill=tk.BOTH, expand=True)
        selected_idx = {"value": None}

        name_var = tk.StringVar(value="")
        enabled_var = tk.BooleanVar(value=True)
        feature_var = tk.StringVar(value=FEATURE_ANY_LABEL)
        scope_var = tk.StringVar(value="全部")
        sheet_var = tk.StringVar(value=SHEET_ALL_LABEL)
        logic_var = tk.StringVar(value="AND")

        ttk.Label(right_panel, text="规则名称：").grid(row=0, column=0, sticky=tk.W, pady=3)
        ttk.Entry(right_panel, textvariable=name_var, width=30).grid(row=0, column=1, sticky="ew", pady=3)
        ttk.Checkbutton(right_panel, text="启用", variable=enabled_var).grid(row=0, column=2, sticky=tk.W, padx=6)
        ttk.Label(right_panel, text="表特征：").grid(row=1, column=0, sticky=tk.W, pady=3)
        feature_combo = ttk.Combobox(right_panel, textvariable=feature_var, values=current_feature_names(True), width=24, state="normal")
        feature_combo.grid(row=1, column=1, sticky=tk.W, pady=3)
        ttk.Label(right_panel, text="范围：").grid(row=2, column=0, sticky=tk.W, pady=3)
        ttk.Combobox(right_panel, textvariable=scope_var, values=["全部", "段落", "表格单元格"], width=14, state="readonly").grid(row=2, column=1, sticky=tk.W, pady=3)
        ttk.Label(right_panel, text="表格/Sheet：").grid(row=2, column=2, sticky=tk.E, pady=3)
        sheet_combo = ttk.Combobox(right_panel, textvariable=sheet_var, values=current_sheet_names(True), width=18, state="normal")
        sheet_combo.grid(row=2, column=3, sticky=tk.W, pady=3)
        ttk.Label(right_panel, text="条件默认连接：").grid(row=3, column=0, sticky=tk.W, pady=3)
        ttk.Combobox(right_panel, textvariable=logic_var, values=["AND", "OR"], width=8, state="readonly").grid(row=3, column=1, sticky=tk.W, pady=3)

        ttk.Label(preview_panel, text="匹配/替换预览").grid(row=0, column=0, sticky=tk.W, pady=(0, 4))
        preview_text = tk.Text(preview_panel, height=28, width=34, wrap=tk.WORD)
        preview_text.grid(row=1, column=0, sticky="nsew")
        preview_scroll = ttk.Scrollbar(preview_panel, orient=tk.VERTICAL, command=preview_text.yview)
        preview_scroll.grid(row=1, column=1, sticky="ns")
        preview_text.configure(yscrollcommand=preview_scroll.set)
        preview_status_var = tk.StringVar(value="未刷新")
        ttk.Label(preview_panel, textvariable=preview_status_var, foreground="gray").grid(row=2, column=0, columnspan=2, sticky=tk.W, pady=(4, 0))

        cond_columns = ("join", "mode", "value")
        cond_tree = ttk.Treeview(right_panel, columns=cond_columns, show="headings", height=6)
        for col, text, width in [("join", "连接", 70), ("mode", "匹配", 120), ("value", "值/正则", 360)]:
            cond_tree.heading(col, text=text)
            cond_tree.column(col, width=width, anchor=tk.W)
        ttk.Label(right_panel, text="匹配条件").grid(row=6, column=0, columnspan=4, sticky=tk.W, pady=(8, 0))
        cond_tree.grid(row=7, column=0, columnspan=4, sticky="nsew", pady=4)

        cond_input = ttk.Frame(right_panel)
        cond_input.grid(row=8, column=0, columnspan=4, sticky="ew", pady=2)
        cond_join_var = tk.StringVar(value="AND")
        cond_mode_var = tk.StringVar(value="正则匹配")
        cond_value_var = tk.StringVar(value="")
        ttk.Combobox(cond_input, textvariable=cond_join_var, values=["AND", "OR"], width=7, state="readonly").pack(side=tk.LEFT, padx=2)
        ttk.Combobox(cond_input, textvariable=cond_mode_var, values=["包含", "等于", "不等于", "正则匹配", "正则不匹配", "为空", "非空"], width=14, state="readonly").pack(side=tk.LEFT, padx=2)
        ttk.Entry(cond_input, textvariable=cond_value_var, width=48).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)

        batch_columns = ("match_mode", "match_value", "replace_value", "replace_mode", "value_source", "match_field", "replace_field", "case", "skip", "count")
        batch_tree = ttk.Treeview(right_panel, columns=batch_columns, show="headings", height=6)
        for col, text, width in [
            ("match_mode", "匹配方式", 90),
            ("match_value", "匹配值", 130),
            ("replace_value", "替换值/模板", 150),
            ("replace_mode", "替换方式", 150),
            ("value_source", "替换值来源", 100),
            ("match_field", "匹配值字段", 130),
            ("replace_field", "替换值字段", 130),
            ("case", "大小写", 70),
            ("skip", "空值跳过", 80),
            ("count", "次数", 60),
        ]:
            batch_tree.heading(col, text=text)
            batch_tree.column(col, width=width, anchor=tk.W, stretch=False)
        ttk.Label(right_panel, text="批量替换规则列表（按顺序作用于匹配条件命中值）").grid(row=10, column=0, columnspan=4, sticky=tk.W, pady=(8, 0))
        batch_tree.grid(row=11, column=0, columnspan=4, sticky="nsew", pady=4)

        batch_input = ttk.LabelFrame(right_panel, text="批量替换规则设置", padding=6)
        batch_input.grid(row=12, column=0, columnspan=4, sticky="ew", pady=2)
        batch_match_mode_var = tk.StringVar(value="包含")
        batch_match_value_var = tk.StringVar(value="")
        batch_replace_value_var = tk.StringVar(value="")
        batch_replace_mode_var = tk.StringVar(value="局部替换匹配字符串")
        batch_value_source_var = tk.StringVar(value="手动输入")
        batch_match_field_var = tk.StringVar(value="")
        batch_replace_field_var = tk.StringVar(value="")
        batch_case_var = tk.BooleanVar(value=True)
        batch_skip_empty_var = tk.BooleanVar(value=True)
        batch_count_var = tk.StringVar(value="0")
        ttk.Label(batch_input, text="匹配方式：").grid(row=0, column=0, sticky=tk.W, padx=4, pady=3)
        ttk.Combobox(batch_input, textvariable=batch_match_mode_var, values=["包含", "完全相等", "不等于", "开头是", "结尾是", "正则匹配", "为空", "不为空"], width=14, state="readonly").grid(row=0, column=1, sticky=tk.W, padx=4, pady=3)
        ttk.Label(batch_input, text="匹配值：").grid(row=0, column=2, sticky=tk.W, padx=4, pady=3)
        ttk.Entry(batch_input, textvariable=batch_match_value_var, width=22).grid(row=0, column=3, sticky="ew", padx=4, pady=3)
        ttk.Label(batch_input, text="替换值：").grid(row=0, column=4, sticky=tk.W, padx=4, pady=3)
        ttk.Entry(batch_input, textvariable=batch_replace_value_var, width=24).grid(row=0, column=5, sticky="ew", padx=4, pady=3)
        ttk.Label(batch_input, text="替换方式：").grid(row=1, column=0, sticky=tk.W, padx=4, pady=3)
        ttk.Combobox(batch_input, textvariable=batch_replace_mode_var, values=["局部替换匹配字符串", "整格替换为新值"], width=20, state="readonly").grid(row=1, column=1, sticky=tk.W, padx=4, pady=3)
        ttk.Checkbutton(batch_input, text="区分大小写", variable=batch_case_var).grid(row=1, column=2, sticky=tk.W, padx=4, pady=3)
        ttk.Label(batch_input, text="替换值来源：").grid(row=1, column=3, sticky=tk.W, padx=4, pady=3)
        ttk.Combobox(batch_input, textvariable=batch_value_source_var, values=["手动输入", "辅助表字段", "辅助表固定值", "新内容字段"], width=14, state="readonly").grid(row=1, column=4, sticky=tk.W, padx=4, pady=3)
        ttk.Label(batch_input, text="匹配值字段：").grid(row=2, column=0, sticky=tk.W, padx=4, pady=3)
        batch_match_field_combo = ttk.Combobox(batch_input, textvariable=batch_match_field_var, values=current_aux_fields(), width=20, state="normal")
        batch_match_field_combo.grid(row=2, column=1, sticky=tk.W, padx=4, pady=3)
        ttk.Label(batch_input, text="替换值字段：").grid(row=2, column=2, sticky=tk.W, padx=4, pady=3)
        batch_replace_field_combo = ttk.Combobox(batch_input, textvariable=batch_replace_field_var, values=current_aux_fields(), width=20, state="normal")
        batch_replace_field_combo.grid(row=2, column=3, sticky=tk.W, padx=4, pady=3)
        ttk.Checkbutton(batch_input, text="列匹配值为空时跳过", variable=batch_skip_empty_var).grid(row=2, column=4, sticky=tk.W, padx=4, pady=3)
        ttk.Label(batch_input, text="次数：").grid(row=3, column=0, sticky=tk.W, padx=4, pady=3)
        ttk.Entry(batch_input, textvariable=batch_count_var, width=8).grid(row=3, column=1, sticky=tk.W, padx=4, pady=3)
        ttk.Label(batch_input, text="规则作用于匹配条件命中值；辅助表字段模式逐行使用辅助表的匹配值字段/替换值字段。", foreground="gray").grid(row=4, column=0, columnspan=6, sticky=tk.W, padx=4, pady=(2, 0))
        batch_input.columnconfigure(3, weight=1)
        batch_input.columnconfigure(5, weight=1)

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
                while len(values) < 10:
                    values.append("")
                match_mode, match_value, replace_value, replace_mode, value_source, match_field, replace_field, case_text, skip_text, count = values[:10]
                rows.append({
                    "enabled": True,
                    "match_mode": _as_text(match_mode) or "包含",
                    "match_value": _as_text(match_value),
                    "replace_value": _as_text(replace_value),
                    "replace_mode": _as_text(replace_mode) or "局部替换匹配字符串",
                    "value_source": _normalize_batch_value_source(value_source),
                    "match_value_field": _as_text(match_field),
                    "replace_value_field": _as_text(replace_field),
                    "case_sensitive": _as_text(case_text) not in ("否", "False", "false", "0"),
                    "skip_empty_match_value": _as_text(skip_text) not in ("否", "False", "false", "0"),
                    "count": _as_text(count) or "0",
                })
            return rows

        def current_batch_values():
            return (
                batch_match_mode_var.get(),
                batch_match_value_var.get(),
                batch_replace_value_var.get(),
                batch_replace_mode_var.get(),
                batch_value_source_var.get(),
                batch_match_field_var.get(),
                batch_replace_field_var.get(),
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
                "condition_logic": logic_var.get() or "AND",
                "conditions": serialize_conditions(),
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
            preview_rows, total_changed, total_errors = _preview_global_replace_rows(
                [rule],
                records,
                cfg.get("features", []),
                current_content_rows(),
                current_aux_rows(),
                params,
                limit=500,
                include_unchanged=True,
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
            logic_var.set(_as_text(rule.get("condition_logic", "AND")) or "AND")
            cond_tree.delete(*cond_tree.get_children())
            for cond in rule.get("conditions", []) or []:
                cond_tree.insert("", tk.END, values=(_as_text(cond.get("join") or "AND"), _as_text(cond.get("mode") or "包含"), _as_text(cond.get("value"))))
            batch_tree.delete(*batch_tree.get_children())
            for item in _batch_rules_for_rule(rule):
                batch_tree.insert("", tk.END, values=(
                    _as_text(item.get("match_mode") or "包含"),
                    _as_text(item.get("match_value")),
                    _as_text(item.get("replace_value")),
                    _as_text(item.get("replace_mode") or "局部替换匹配字符串"),
                    _normalize_batch_value_source(item.get("value_source")),
                    _as_text(item.get("match_value_field")),
                    _as_text(item.get("replace_value_field")),
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
            field_values = []
            for field in list(current_aux_fields()) + list(current_content_fields()):
                if field not in field_values:
                    field_values.append(field)
            batch_match_field_combo.configure(values=field_values)
            batch_replace_field_combo.configure(values=field_values)
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
                "batch_rules": [{
                    "enabled": True,
                    "match_mode": "包含",
                    "match_value": "",
                    "replace_value": "",
                    "replace_mode": "局部替换匹配字符串",
                    "value_source": "手动输入",
                    "match_value_field": "",
                    "replace_value_field": "",
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
            while len(values) < 10:
                values.append("")
            match_mode, match_value, replace_value, replace_mode, value_source, match_field, replace_field, case_text, skip_text, count = values[:10]
            batch_match_mode_var.set(match_mode or "包含")
            batch_match_value_var.set(match_value)
            batch_replace_value_var.set(replace_value)
            batch_replace_mode_var.set(replace_mode or "局部替换匹配字符串")
            batch_value_source_var.set(_normalize_batch_value_source(value_source))
            batch_match_field_var.set(match_field)
            batch_replace_field_var.set(replace_field)
            batch_case_var.set(_as_text(case_text) not in ("否", "False", "false", "0"))
            batch_skip_empty_var.set(_as_text(skip_text) not in ("否", "False", "false", "0"))
            batch_count_var.set(count or "0")

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

        refresh_global_list(0)
        dlg.after_idle(lambda: _show_centered_window(dlg, win, 1280, 680))

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

    def show_info(rec):
        state["selected_rec"] = rec
        info_text.delete("1.0", tk.END)
        info_text.insert(tk.END, json.dumps(rec, ensure_ascii=False, indent=2))

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

    def edit_rule(rec):
        rule = find_rule(rec)
        dlg = _make_floating_child(win, "输入源匹配 / 锚点设置")
        body = ttk.Frame(dlg, padding=10)
        body.pack(fill=tk.BOTH, expand=True)
        source_match = rule.setdefault("source_match", {})
        anchor = rule.setdefault("anchor", {})
        sm_enabled = tk.BooleanVar(value=bool(source_match.get("enabled", False)))
        sm_mode = tk.StringVar(value=source_match.get("mode", "包含"))
        sm_value = tk.StringVar(value=source_match.get("value", rec.get("text", "")))
        feature_var = tk.StringVar(value=_ui_feature_name(rule.get("feature_name", "")))
        anchor_enabled = tk.BooleanVar(value=bool(anchor.get("enabled", False)))
        anchor_axis = tk.StringVar(value=anchor.get("axis", "列"))
        anchor_index = tk.StringVar(value=str(anchor.get("index", rec.get("col_index", 1))))
        anchor_match_mode = tk.StringVar(value=anchor.get("match_mode", "等于"))
        anchor_value = tk.StringVar(value=anchor.get("value", ""))
        row_offset = tk.StringVar(value=str(anchor.get("row_offset", 0)))
        col_offset = tk.StringVar(value=str(anchor.get("col_offset", 0)))

        ttk.Label(body, text="输入源内容匹配", font=("TkDefaultFont", 10, "bold")).grid(row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 4))
        ttk.Label(body, text="表特征：").grid(row=0, column=2, sticky=tk.E, padx=4)
        ttk.Combobox(body, textvariable=feature_var, values=current_feature_names(True), width=18, state="normal").grid(row=0, column=3, sticky=tk.W, padx=4)
        ttk.Checkbutton(body, text="启用", variable=sm_enabled).grid(row=1, column=0, sticky=tk.W)
        ttk.Combobox(body, textvariable=sm_mode, values=["包含", "等于", "不等于", "正则匹配", "正则不匹配", "为空", "非空"], width=16, state="readonly").grid(row=1, column=1, padx=4, pady=4)
        ttk.Entry(body, textvariable=sm_value, width=36).grid(row=1, column=2, columnspan=2, sticky=tk.W, padx=4, pady=4)

        ttk.Separator(body).grid(row=2, column=0, columnspan=4, sticky="ew", pady=8)
        ttk.Label(body, text="锚点功能", font=("TkDefaultFont", 10, "bold")).grid(row=3, column=0, columnspan=4, sticky=tk.W, pady=(0, 4))
        ttk.Checkbutton(body, text="启用锚点", variable=anchor_enabled).grid(row=4, column=0, sticky=tk.W)
        ttk.Label(body, text="方向：").grid(row=4, column=1, sticky=tk.E)
        ttk.Combobox(body, textvariable=anchor_axis, values=["行", "列"], width=8, state="readonly").grid(row=4, column=2, sticky=tk.W, padx=4)
        ttk.Label(body, text="行/列序号：").grid(row=5, column=0, sticky=tk.W)
        ttk.Entry(body, textvariable=anchor_index, width=10).grid(row=5, column=1, sticky=tk.W, padx=4)
        ttk.Combobox(body, textvariable=anchor_match_mode, values=["包含", "等于", "不等于", "正则匹配"], width=16, state="readonly").grid(row=5, column=2, sticky=tk.W, padx=4)
        ttk.Entry(body, textvariable=anchor_value, width=28).grid(row=5, column=3, sticky=tk.W, padx=4)
        ttk.Label(body, text="偏移行：").grid(row=6, column=0, sticky=tk.W)
        ttk.Entry(body, textvariable=row_offset, width=10).grid(row=6, column=1, sticky=tk.W, padx=4)
        ttk.Label(body, text="偏移列：").grid(row=6, column=2, sticky=tk.E)
        ttk.Entry(body, textvariable=col_offset, width=10).grid(row=6, column=3, sticky=tk.W, padx=4)

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

        def anchor_candidates_from_ui():
            axis = anchor_axis.get()
            index = _to_int(anchor_index.get(), 0)
            if index <= 0:
                messagebox.showwarning("无法反推", "请先设置锚点行/列序号。", parent=dlg)
                return []
            match_cfg = {"enabled": True, "mode": anchor_match_mode.get(), "value": anchor_value.get()}
            candidates = []
            for item in same_scope_records():
                if axis in ("列", "column") and int(item.get("col_index") or 0) != index:
                    continue
                if axis in ("行", "row") and int(item.get("row_index") or 0) != index:
                    continue
                ok, _detail = _match_text(item.get("text", ""), match_cfg)
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
            lb = tk.Listbox(body2, height=min(12, max(4, len(candidates))), width=72, exportselection=False)
            lb.pack(fill=tk.BOTH, expand=True)
            for item in candidates:
                label = f"R{item.get('row_index')}C{item.get('col_index')}  {item.get('text', '')}"
                lb.insert(tk.END, label[:180])
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
                messagebox.showwarning("无法反推", "未找到匹配的锚点单元格。请检查行/列序号、匹配方式和匹配内容。", parent=dlg)
                return
            if len(candidates) == 1:
                apply_anchor_candidate(candidates[0])
                messagebox.showinfo("反推完成", f"已自动写入偏移：行 {row_offset.get()}，列 {col_offset.get()}", parent=dlg)
                return
            choose_anchor_candidate(candidates)

        def on_ok():
            rule["feature_name"] = _cfg_feature_name(feature_var.get())
            source_match.update({"enabled": bool(sm_enabled.get()), "mode": sm_mode.get(), "value": sm_value.get()})
            anchor.update({
                "enabled": bool(anchor_enabled.get()),
                "axis": anchor_axis.get(),
                "index": anchor_index.get(),
                "match_mode": anchor_match_mode.get(),
                "value": anchor_value.get(),
                "row_offset": row_offset.get(),
                "col_offset": col_offset.get(),
            })
            refresh_rules()
            dlg.destroy()

        btns = ttk.Frame(body)
        btns.grid(row=7, column=0, columnspan=4, sticky=tk.E, pady=8)
        ttk.Button(btns, text="自动反推偏移", command=auto_infer_offset).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="确定", command=on_ok).pack(side=tk.RIGHT, padx=4)
        ttk.Button(btns, text="取消", command=dlg.destroy).pack(side=tk.RIGHT, padx=4)
        dlg.after_idle(lambda: _show_centered_window(dlg, win))

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
            fill = "#fff7df" if is_merged else "#ffffff"
            outline = "#f59e0b" if is_merged else "#cbd5e1"
            canvas.create_rectangle(x1, y1, x2, y2, fill=fill, outline=outline, width=2 if is_merged else 1)
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
            display_text = _as_text(rec.get("text", ""))
            if is_merged:
                merge_note = rec.get("merged_range") or f"{rs}行x{cs}列"
                display_text = f"[合并 {merge_note}]\n{display_text}"
            canvas.create_text(x1 + 8, y1 + 32, anchor=tk.NW, text=display_text[:120], width=max(80, (x2 - x1) - 16), fill="#111827")
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
        state["records"] = _doc_records(doc_table, params)
        state["groups"] = _group_doc_grid(state["records"])
        group_lb.delete(0, tk.END)
        for group_name in sorted(state["groups"].keys()):
            group_lb.insert(tk.END, group_name)
        if group_lb.size():
            group_lb.selection_set(0)
            render_group(group_lb.get(0))
        refresh_rules()
        status_var.set(f"读取 {len(state['records'])} 个单元格；规则 {len(cfg.get('rules', []))} 条")

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

    reload_data()
    _show_centered_window(win, parent, 1180, 760)
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
