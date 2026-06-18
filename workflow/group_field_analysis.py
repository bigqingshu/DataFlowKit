# -*- coding: utf-8 -*-
"""Field IO analysis helpers for group/subworkflow configuration."""

import re

from workflow.nodes.filter_plan_nodes import normalize_filter_condition_value_source
from workflow.nodes.group_nodes import unique_keep_order


def parse_new_column_names_for_group_analysis(text, strip_name=True, allow_empty=False):
    """Parse new-column config text and return only column names."""
    result = []
    for part in re.split(r"[\n,，;；]+", str(text or "")):
        item = part.strip() if strip_name else str(part)
        if not item and not allow_empty:
            continue
        if "=" in item:
            name = item.split("=", 1)[0]
        else:
            name = item
        name = name.strip() if strip_name else name
        if name or allow_empty:
            result.append(name)
    return unique_keep_order(result)


def add_group_field_ref(target, value):
    """Safely append a field name or a nested field list into target."""
    if value is None:
        return
    if isinstance(value, str):
        text = value.strip()
        if text:
            target.append(text)
        return
    if isinstance(value, (list, tuple, set)):
        for item in value:
            add_group_field_ref(target, item)


def add_group_field_refs_from_dict_list(target, items, keys):
    """Collect field names from a list of dict rules by possible key names."""
    if not isinstance(items, list):
        return
    for item in items:
        if not isinstance(item, dict):
            continue
        for key in keys:
            add_group_field_ref(target, item.get(key))


def classify_group_filter_field_reference(field, extra_tables=None):
    """
    Convert advanced-filter field references for group static analysis.

    Current-table qualified names drop one "当前表." prefix. Side-table fields
    keep their qualified name and are marked external.
    """
    text = str(field or "").strip()
    if not text:
        return "", ""
    for table in extra_tables or []:
        table_name = str(table or "").strip()
        if table_name and text.startswith(f"{table_name}."):
            return "external", text
    if text.startswith("当前表."):
        return "current", text[len("当前表."):]
    return "current", text


def get_group_filter_external_output_fields(window, config, context=None):
    """Read side-table fields emitted by advanced filter when projection is implicit."""
    fields = []
    unresolved = []
    transit_tables = (context or {}).get("transit_tables", {})
    for table in list((config or {}).get("extra_tables", []) or []):
        table_name = str(table or "").strip()
        if not table_name:
            continue
        try:
            if table_name.startswith("中转:"):
                transit_name = table_name.split(":", 1)[1]
                item = transit_tables.get(transit_name)
                if not isinstance(item, dict):
                    raise ValueError("中转副表尚未生成")
                columns = list(item.get("headers", []) or [])
            else:
                columns = list(window.get_workflow_sqlite_columns(table_name, context))
            fields.extend(f"{table_name}.{column}" for column in columns)
        except Exception as exc:
            unresolved.append(f"{table_name}（{exc}）")
    return unique_keep_order(fields), unresolved


def analyze_group_filter_field_io(window, config, context=None):
    """Analyze advanced-filter conditions, join rules and projection fields inside a group."""
    cfg = config or {}
    extra_tables = list(cfg.get("extra_tables", []) or [])
    reads = []
    writes = []
    write_prefixes = []

    def add_current_read(field):
        owner, name = classify_group_filter_field_reference(field, extra_tables)
        if owner == "current":
            add_group_field_ref(reads, name)

    def add_output(field):
        owner, name = classify_group_filter_field_reference(field, extra_tables)
        if not name:
            return
        if owner == "current":
            add_group_field_ref(reads, name)
        add_group_field_ref(writes, name)

    for cond in cfg.get("conditions", []) or []:
        if not isinstance(cond, dict):
            continue
        add_current_read(cond.get("field"))
        if normalize_filter_condition_value_source(cond) == "字段值":
            add_current_read(cond.get("value"))

    for rule in cfg.get("join_rules", []) or []:
        if not isinstance(rule, dict):
            continue
        add_current_read(rule.get("left"))
        add_current_read(rule.get("right"))

    for field in cfg.get("output_fields", []) or []:
        add_output(field)

    note = "当前表字段作为组内输入；副表字段由高级筛选自行读取"
    if cfg.get("output_fields"):
        note += "；显式输出字段参与后续节点推导"
    else:
        external_fields, unresolved = get_group_filter_external_output_fields(
            window,
            cfg,
            context=context,
        )
        writes.extend(external_fields)
        write_prefixes.extend(
            f"{str(table).strip()}."
            for table in extra_tables
            if str(table).strip()
        )
        note += f"；未指定输出字段，已推导副表输出 {len(external_fields)} 个字段"
        if unresolved:
            note += "；结构未解析：" + "、".join(unresolved)
    return {
        "read_fields": unique_keep_order(reads),
        "write_fields": unique_keep_order(writes),
        "write_field_prefixes": unique_keep_order(write_prefixes),
        "note": note,
    }


def collect_group_fields_from_nested_config(target, value, field_keys=None):
    """Scan nested config and collect values whose key matches field_keys."""
    field_keys = set(field_keys or [])
    if isinstance(value, dict):
        for key, nested_value in value.items():
            if key in field_keys:
                add_group_field_ref(target, nested_value)
            elif isinstance(nested_value, (dict, list, tuple)):
                collect_group_fields_from_nested_config(target, nested_value, field_keys=field_keys)
    elif isinstance(value, (list, tuple)):
        for item in value:
            collect_group_fields_from_nested_config(target, item, field_keys=field_keys)


def analyze_group_inner_node_field_io(window, node, context=None):
    """
    Analyze the fields read and written by one node inside a group.

    The goal is conservative static analysis for common workflow nodes, so that
    group input fields can be inferred without executing the inner workflow.
    """
    node_type = node.get("type", "")
    cfg = node.get("config", {}) or {}
    reads = []
    writes = []
    note = ""

    if node_type == "批量替换":
        add_group_field_ref(reads, cfg.get("target_field"))
        legacy_source = cfg.get("value_source", "手动输入")
        match_source = cfg.get("match_value_source") or legacy_source
        replace_source = cfg.get("replace_value_source") or legacy_source
        if match_source == "列字段":
            add_group_field_ref(reads, cfg.get("match_value_field"))
        if replace_source == "列字段":
            add_group_field_ref(reads, cfg.get("replace_value_field"))
        add_group_field_ref(writes, cfg.get("target_field"))
        note = "读取目标字段及匹配/替换来源字段，覆盖目标字段"

    elif node_type == "数据提取":
        src = cfg.get("source_field")
        add_group_field_ref(reads, src)
        if cfg.get("output_mode") == "覆盖源字段":
            add_group_field_ref(writes, src)
        else:
            add_group_field_ref(writes, cfg.get("new_field"))
        note = "source_field 为输入；新字段/覆盖字段为输出"

    elif node_type == "格式规范化 / 日期时间解析":
        add_group_field_ref(reads, cfg.get("source_field"))
        if cfg.get("use_separate_time_field"):
            add_group_field_ref(reads, cfg.get("time_source_field"))
        mode = cfg.get("output_mode", "生成新字段")
        parse_type = cfg.get("parse_type", "日期")
        if mode == "覆盖源字段":
            add_group_field_ref(writes, cfg.get("source_field"))
        elif mode == "生成多个字段":
            prefix = str(cfg.get("component_prefix") or "解析").strip() or "解析"
            if parse_type in ("日期", "日期时间"):
                writes.extend([f"{prefix}年", f"{prefix}月", f"{prefix}日"])
            if parse_type in ("时间", "日期时间"):
                writes.extend([f"{prefix}时", f"{prefix}分", f"{prefix}秒"])
            add_group_field_ref(writes, cfg.get("new_field"))
        else:
            add_group_field_ref(writes, cfg.get("new_field"))
        if cfg.get("output_status"):
            add_group_field_ref(writes, cfg.get("status_field"))
        note = "日期/时间源字段为输入；标准字段/组件/状态为输出"

    elif node_type == "新建日期时间列":
        if cfg.get("output_mode") == "覆盖已有字段":
            add_group_field_ref(writes, cfg.get("target_field"))
        else:
            add_group_field_ref(writes, cfg.get("new_field"))
        note = "不读取外部字段，只生成日期时间字段"

    elif node_type == "新建列":
        writes.extend(parse_new_column_names_for_group_analysis(
            cfg.get("columns_text", ""),
            strip_name=bool(cfg.get("strip_column_name", True)),
            allow_empty=bool(cfg.get("allow_empty_name", False)),
        ))
        note = "不读取外部字段，只新建字段"

    elif node_type == "合并列":
        add_group_field_ref(reads, cfg.get("fields"))
        add_group_field_ref(writes, cfg.get("output_field"))
        note = "合并字段为输入；合并结果为输出"

    elif node_type == "批量更改列名":
        add_group_field_refs_from_dict_list(reads, cfg.get("mappings"), ["old", "old_field", "source", "source_field", "from"])
        add_group_field_refs_from_dict_list(writes, cfg.get("mappings"), ["new", "new_field", "target", "target_field", "to"])
        add_group_field_ref(reads, cfg.get("scope_fields"))
        note = "按映射读取旧字段并输出新字段"

    elif node_type == "去重 / 重复数据处理":
        add_group_field_ref(reads, cfg.get("key_fields"))
        if cfg.get("add_marker_columns"):
            for key in ["duplicate_group_field", "duplicate_status_field", "duplicate_index_field", "duplicate_count_field", "keep_flag_field"]:
                add_group_field_ref(writes, cfg.get(key))
        note = "去重键字段为输入；标记列为输出"

    elif node_type == "列数字运算":
        add_group_field_ref(reads, cfg.get("target_field"))
        if cfg.get("operand_source") == "另一列字段":
            add_group_field_ref(reads, cfg.get("operand_field"))
        add_group_field_ref(reads, cfg.get("reference_field"))
        if cfg.get("output_mode") == "覆盖原列":
            add_group_field_ref(writes, cfg.get("target_field"))
        else:
            add_group_field_ref(writes, cfg.get("output_field"))
        note = "目标字段/操作数字段为输入；计算结果为输出"

    elif node_type == "匹配值输出列名":
        add_group_field_ref(reads, cfg.get("source_field"))
        for key in ["output_field", "match_value_field", "match_row_field", "status_field"]:
            add_group_field_ref(writes, cfg.get(key))
        note = "source_field 为输入；匹配结果字段为输出"

    elif node_type == "复制列":
        src = cfg.get("source_field")
        add_group_field_ref(reads, src)
        if cfg.get("output_mode") == "覆盖已有字段":
            add_group_field_ref(writes, cfg.get("target_field"))
        else:
            add_group_field_ref(writes, cfg.get("new_field"))
        note = "源字段为输入；复制目标为输出"

    elif node_type == "删除行":
        if str(cfg.get("delete_mode", "")).startswith("按条件") or cfg.get("condition_field"):
            add_group_field_ref(reads, cfg.get("condition_field"))
        add_group_field_ref(reads, cfg.get("empty_field"))
        note = "条件/空值判断字段为输入"

    elif node_type == "填充值":
        add_group_field_ref(writes, cfg.get("target_field"))
        if cfg.get("value_source") != "手动输入值":
            for key in ["source_field", "source_end_field"]:
                add_group_field_ref(reads, cfg.get(key))
        for key in ["end_field", "reference_field"]:
            add_group_field_ref(reads, cfg.get(key))
        note = "来源字段/边界字段为输入；目标字段为输出"

    elif node_type == "序列填充":
        add_group_field_ref(writes, cfg.get("target_field"))
        for key in ["end_field", "reference_field"]:
            add_group_field_ref(reads, cfg.get(key))
        note = "边界字段为输入；目标字段为输出"

    elif node_type == "区域填充":
        for key in ["start_field", "end_field"]:
            add_group_field_ref(writes, cfg.get(key))
        if cfg.get("value_source") != "手动输入值":
            for key in ["source_field", "source_end_field"]:
                add_group_field_ref(reads, cfg.get(key))
        add_group_field_ref(reads, cfg.get("reference_field"))
        note = "来源/边界字段为输入；区域字段为输出"

    elif node_type == "行数据映射填充":
        add_group_field_ref(reads, cfg.get("value_fields"))
        add_group_field_ref(reads, cfg.get("keep_fields"))
        for key in ["output_value_field", "source_field_name", "original_row_field", "status_field"]:
            add_group_field_ref(writes, cfg.get(key))
        note = "展开取值字段/保留字段为输入；输出字段为输出"

    elif node_type == "保存中转数据":
        note = "保存当前组内表，不新增入口字段"

    elif node_type == "选定列写入指定表":
        add_group_field_ref(reads, cfg.get("selected_fields"))
        add_group_field_refs_from_dict_list(reads, cfg.get("field_mappings"), ["source", "source_field", "源字段", "from"])
        add_group_field_refs_from_dict_list(writes, cfg.get("field_mappings"), ["target", "target_field", "目标字段", "to"])
        note = "选定来源字段为输入；写入目标字段为副作用输出"

    elif node_type == "字段映射写入表":
        add_group_field_refs_from_dict_list(reads, cfg.get("match_rules"), ["source_field", "left_field", "field", "当前表字段"])
        add_group_field_refs_from_dict_list(reads, cfg.get("field_mappings"), ["source_field", "source", "当前表字段", "from"])
        note = "匹配规则/字段映射中的当前表字段为输入"

    elif node_type == "高级筛选":
        return analyze_group_filter_field_io(window, cfg, context=context)

    elif node_type == "删除列":
        add_group_field_ref(reads, cfg.get("fields"))
        note = "待删除字段为输入"

    elif node_type == "移动列":
        add_group_field_ref(reads, cfg.get("order"))
        note = "列顺序字段为输入"

    elif node_type == "批量重命名":
        for key in ["path_field", "new_name_field", "new_path_field", "status_field"]:
            if key in ("status_field", "new_path_field"):
                add_group_field_ref(writes, cfg.get(key))
            else:
                add_group_field_ref(reads, cfg.get(key))
        note = "路径字段/新文件名字段为输入；状态字段为输出"

    elif node_type == "插件节点":
        collect_group_fields_from_nested_config(
            reads,
            cfg,
            field_keys={"source_field", "target_field", "field", "path_field", "file_field", "input_field"},
        )
        collect_group_fields_from_nested_config(
            writes,
            cfg,
            field_keys={"output_field", "new_field", "status_field", "result_field"},
        )
        note = "插件节点按常见字段参数保守推导"

    else:
        collect_group_fields_from_nested_config(
            reads,
            cfg,
            field_keys={"source_field", "target_field", "field", "fields", "key_fields", "reference_field"},
        )
        collect_group_fields_from_nested_config(
            writes,
            cfg,
            field_keys={"new_field", "output_field", "status_field", "target_field"},
        )
        note = "未知节点，按常见字段键保守推导"

    return {
        "read_fields": unique_keep_order(reads),
        "write_fields": unique_keep_order(writes),
        "note": note,
    }


def infer_group_input_fields_from_nodes(window, nodes, context=None):
    """
    Infer the real group input fields needed by inner nodes in execution order.

    A read field is required only if no previous node produced it.
    """
    required = []
    produced = set()
    produced_prefixes = []
    details = []
    for idx, node in enumerate(nodes or [], start=1):
        if not node.get("enabled", True):
            details.append({
                "index": idx,
                "type": node.get("type", ""),
                "reads": [],
                "writes": [],
                "write_prefixes": [],
                "required": [],
                "note": "节点已禁用，跳过推导",
            })
            continue
        info = analyze_group_inner_node_field_io(window, node, context=context)
        reads = info.get("read_fields", [])
        writes = info.get("write_fields", [])
        write_prefixes = info.get("write_field_prefixes", [])
        req_this = []
        for field in reads:
            if field not in produced and not any(str(field).startswith(prefix) for prefix in produced_prefixes):
                req_this.append(field)
                required.append(field)
        for field in writes:
            produced.add(field)
        produced_prefixes.extend(
            prefix
            for prefix in write_prefixes
            if prefix and prefix not in produced_prefixes
        )
        details.append({
            "index": idx,
            "type": node.get("type", ""),
            "reads": reads,
            "writes": writes,
            "write_prefixes": write_prefixes,
            "required": unique_keep_order(req_this),
            "note": info.get("note", ""),
        })
    return unique_keep_order(required), details


def format_group_input_infer_details(inferred, details, limit=20):
    """Format group input inference details for display."""
    lines = [f"推导入口字段：{', '.join(inferred) if inferred else '无'}", ""]
    for item in details[:limit]:
        lines.append(f"{item.get('index')}. {item.get('type')}")
        lines.append(f"  读取：{', '.join(item.get('reads') or []) or '-'}")
        lines.append(f"  输出：{', '.join(item.get('writes') or []) or '-'}")
        if item.get("write_prefixes"):
            lines.append(f"  动态输出前缀：{', '.join(item.get('write_prefixes') or [])}")
        lines.append(f"  需要入口：{', '.join(item.get('required') or []) or '-'}")
        if item.get("note"):
            lines.append(f"  说明：{item.get('note')}")
    if len(details) > limit:
        lines.append(f"... 仅显示前 {limit} 个节点，共 {len(details)} 个节点。")
    return "\n".join(lines)
