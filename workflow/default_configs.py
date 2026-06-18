# -*- coding: utf-8 -*-
"""Default workflow node configuration builders."""

import os
from datetime import datetime


DEFAULT_NODE_NAMES = {
    "节点组 / 子工作流": "节点组 / 子工作流",
    "循环执行起点": "循环执行起点",
    "循环判断回跳": "循环判断回跳",
    "批量替换": "批量替换",
    "数据提取": "数据提取",
    "格式规范化 / 日期时间解析": "格式规范化 / 日期时间解析",
    "新建日期时间列": "新建日期时间列",
    "新建列": "新建列",
    "合并列": "合并列",
    "批量更改列名": "批量更改列名",
    "去重 / 重复数据处理": "去重 / 重复数据处理",
    "列数字运算": "列数字运算",
    "匹配值输出列名": "匹配值输出列名",
    "复制列": "复制列",
    "复制行": "复制行",
    "删除行": "删除行",
    "填充值": "填充值",
    "序列填充": "序列填充",
    "区域填充": "区域填充",
    "行数据映射填充": "行数据映射填充",
    "保存中转数据": "保存中转数据",
    "字段映射写入表": "字段映射写入表",
    "高级筛选": "筛选数据",
    "删除列": "删除列",
    "移动列": "整理列顺序",
}


def default_name_for_node(node_type):
    return DEFAULT_NODE_NAMES.get(node_type, node_type)


def _now_hms(now_text=None):
    if now_text is None:
        return datetime.now().strftime("%H%M%S")
    if hasattr(now_text, "strftime"):
        return now_text.strftime("%H%M%S")
    return str(now_text)


def default_config_for_type(node_type, preview_headers=None, table_names=None, table_columns=None, app_dir=None, now_text=None):
    headers = list(preview_headers or [])
    tables = list(table_names or [])
    table_columns = table_columns or {}
    first = headers[0] if headers else ""
    second = headers[1] if len(headers) > 1 else first
    suffix = _now_hms(now_text)
    base_dir = app_dir or os.getcwd()

    if node_type == "节点组 / 子工作流":
        return {
            "group_name": f"节点组_{suffix}",
            "nodes": [],
            "description": "",
            "input_source_type": "当前工作表",
            "input_sqlite_table": "",
            "input_transit_table": "",
            "input_fields": [],
            "input_mapping": {},
            "input_defaults": {},
            "missing_input_policy": "缺失填空",
            "transit_scope": "组内中转私有",
            "allow_loop_nodes": False,
            "main_output_mode": "输出为当前工作表",
            "save_to_transit": False,
            "output_transit_name": "",
            "output_transit_conflict_mode": "覆盖整表",
            "save_to_sqlite": False,
            "output_sqlite_table": "",
            "output_sqlite_mode": "自动加时间戳新表",
            "sqlite_save_in_preview": False,
        }
    if node_type == "循环执行起点":
        return {
            "loop_id": f"loop_{suffix}",
            "source_type": "当前表",
            "source_table": "",
            "transit_table": "",
            "fields": list(headers[:3]),
            "flag_field": "执行标志",
            "init_flag_mode": "空值填0，非0不执行",
            "boundary_mode": "整体表格数据边界",
            "reference_field": first,
            "current_table_name": "当前循环项",
            "output_current_as_table": True,
            "running_flag_policy": "执行中1标记失败3",
            "max_loop_count": "10000",
        }
    if node_type == "循环判断回跳":
        return {
            "loop_id": "",
            "condition_source": "当前表",
            "condition_mode": "始终成功",
            "condition_field": first,
            "condition_op": "等于",
            "condition_value": "成功",
            "on_success": "标记完成2并继续循环",
            "on_fail": "标记失败3并继续下一条",
            "end_output_mode": "循环队列表",
            "result_table_name": "循环结果",
        }
    if node_type == "跳转锚点节点":
        return {
            "anchor_id": f"anchor_{suffix}",
            "anchor_name": f"锚点_{suffix}",
            "description": "",
        }
    if node_type == "无条件跳转节点":
        return {
            "target_anchor_id": "",
            "note": "",
        }
    if node_type == "条件判断节点":
        return {
            "flag_name": f"condition_{suffix}",
            "source_type": "当前表",
            "condition_type": "表行数",
            "field": first,
            "op": "大于",
            "value": "0",
            "case_sensitive": True,
            "true_value": "TRUE",
            "false_value": "FALSE",
        }
    if node_type == "条件跳转节点":
        return {
            "flag_name": "",
            "jump_rules": [
                {"value": "TRUE", "target_anchor_id": ""},
                {"value": "FALSE", "target_anchor_id": ""},
            ],
            "default_anchor_id": "",
        }
    if node_type == "批量替换":
        return {
            "target_field": first,
            "match_mode": "包含",
            "match_value": "",
            "replace_value": "",
            "replace_mode": "局部替换匹配字符串",
            "case_sensitive": True,
            "match_value_source": "手动输入",
            "replace_value_source": "手动输入",
            "match_value_field": first,
            "replace_value_field": first,
            "match_row_policy": "当前行",
            "match_row_index": "1",
            "replace_row_policy": "当前行",
            "replace_row_index": "1",
            "replace_count": "0",
            "skip_empty_match_value": True,
        }
    if node_type == "数据提取":
        return {
            "source_field": first,
            "method": "正则提取",
            "output_mode": "生成新字段",
            "new_field": "提取结果",
            "unmatched_mode": "留空",
            "unmatched_fixed": "未匹配",
            "case_sensitive": True,
            "strip_result": True,
            "regex_pattern": "",
            "regex_group": "0",
            "regex_find_all": False,
            "regex_joiner": ";",
            "start_pos": "1",
            "extract_len": "1",
            "position_base": "从1开始",
            "n_chars": "1",
            "delimiter": "-",
            "part_index": "1",
            "ignore_empty_part": False,
            "before_key": "",
            "after_key": "",
            "between_occurrence": "1",
            "marker": "-",
            "find_mode": "第一次出现",
            "prefix": "",
            "suffix": "",
        }
    if node_type == "格式规范化 / 日期时间解析":
        return {
            "source_field": first,
            "time_source_field": second,
            "use_separate_time_field": False,
            "parse_type": "日期",
            "input_structure": "固定位置",
            "position_base": "从1开始",
            "year_start": "1",
            "year_len": "2",
            "month_start": "3",
            "month_len": "2",
            "day_start": "5",
            "day_len": "2",
            "hour_start": "1",
            "hour_len": "2",
            "minute_start": "3",
            "minute_len": "2",
            "second_start": "5",
            "second_len": "0",
            "date_delimiter": "自动识别",
            "time_delimiter": "自动识别",
            "custom_date_delimiter": "-",
            "custom_time_delimiter": ":",
            "date_order": "年-月-日",
            "year_rule": "20xx",
            "auto_window_pivot": "80",
            "output_template": "{YYYY}-{MM}-{DD}",
            "time_output_template": "{HH}:{mm}",
            "datetime_output_template": "{YYYY}-{MM}-{DD} {HH}:{mm}",
            "output_mode": "生成新字段",
            "new_field": "标准日期",
            "unmatched_mode": "留空",
            "unmatched_fixed": "未匹配",
            "strip_value": True,
            "output_status": True,
            "status_field": "格式解析状态",
            "component_prefix": "解析",
        }
    if node_type == "新建日期时间列":
        return {
            "output_mode": "生成新字段",
            "new_field": "当前日期时间",
            "target_field": first,
            "time_mode": "整次运行固定同一时间",
            "format_mode": "占位符模板",
            "template": "{YYYY}-{MM}-{DD} {HH}:{mm}:{ss}",
            "strftime_template": "%Y-%m-%d %H:%M:%S",
        }
    if node_type == "新建列":
        return {
            "columns_text": "新字段1\n新字段2",
            "value_mode": "统一默认值",
            "default_value": "",
            "conflict_mode": "自动改名",
            "strip_column_name": True,
            "allow_empty_name": False,
        }
    if node_type == "合并列":
        fields = [field for field in [first, second] if field]
        return {
            "fields": fields,
            "separators": ["-"] * max(len(fields) - 1, 0),
            "output_field": "合并结果",
            "skip_empty": True,
            "trim_value": True,
            "empty_placeholder": "",
        }
    if node_type == "批量更改列名":
        return {
            "mode": "手动映射改名",
            "mappings": [],
            "prefix": "",
            "suffix": "",
            "replace_match": "",
            "replace_value": "",
            "scope": "全部字段",
            "scope_fields": [],
            "duplicate_policy": "自动追加编号",
            "missing_policy": "跳过并记录警告",
            "trim_names": True,
        }
    if node_type == "去重 / 重复数据处理":
        return {
            "dedupe_mode": "指定字段/组合字段去重",
            "key_fields": [first] if first else [],
            "trim": True,
            "ignore_case": False,
            "empty_key_policy": "空键参与去重",
            "keep_policy": "保留第一条",
            "output_mode": "输出去重后的数据",
            "add_marker_columns": True,
            "duplicate_group_field": "重复组编号",
            "duplicate_status_field": "重复状态",
            "duplicate_index_field": "组内序号",
            "duplicate_count_field": "重复次数",
            "keep_flag_field": "是否保留",
        }
    if node_type == "列数字运算":
        return {
            "target_field": first,
            "operation": "加",
            "operand_source": "固定值",
            "operand_value": "1",
            "operand_field": second,
            "row_offset": "0",
            "sequence_start": "1",
            "sequence_step": "1",
            "output_mode": "生成新字段",
            "output_field": f"{first}_计算结果" if first else "计算结果",
            "non_number_policy": "留空",
            "non_number_fixed": "",
            "divide_zero_policy": "留空",
            "divide_zero_fixed": "",
            "decimal_places": "自动",
            "range_mode": "全部行",
            "start_row": "1",
            "end_row": "1",
            "reference_field": first,
        }
    if node_type == "匹配值输出列名":
        lookup_table = tables[0] if tables else ""
        lookup_fields = list(table_columns.get(lookup_table, [])[:3]) if lookup_table else []
        return {
            "source_field": first,
            "lookup_table": lookup_table,
            "lookup_fields": lookup_fields,
            "match_mode": "完全相等",
            "output_field": "匹配字段名",
            "output_match_value": True,
            "match_value_field": "匹配值",
            "output_match_row": True,
            "match_row_field": "匹配行号",
            "output_status": True,
            "status_field": "匹配状态",
            "multi_match_policy": "合并所有字段名",
            "multi_match_separator": ";",
            "no_match_value": "未匹配",
            "skip_empty_lookup_value": True,
        }
    if node_type == "复制列":
        return {
            "source_field": first,
            "output_mode": "生成新字段",
            "new_field": f"{first}_复制" if first else "复制列",
            "target_field": first,
            "trim_value": False,
            "empty_default": "",
        }
    if node_type == "复制行":
        return {
            "source_row": "1",
            "copy_count": "1",
            "insert_mode": "表尾",
            "insert_row": "1",
        }
    if node_type == "删除行":
        return {
            "delete_mode": "按行号列表",
            "row_spec": "1",
            "start_row": "1",
            "end_row": "1",
            "condition_field": first,
            "condition_op": "包含",
            "condition_value": "",
            "case_sensitive": True,
            "empty_mode": "整行为空",
            "empty_field": first,
        }
    if node_type == "填充值":
        return {
            "target_field": first,
            "start_row": "1",
            "direction": "向下",
            "value_source": "手动输入值",
            "manual_value": "",
            "source_field": first,
            "source_end_field": second,
            "source_row": "1",
            "multi_field_fill_direction": "横向填充",
            "source_start_row": "1",
            "source_end_row": "1",
            "source_range_mode": "来源列数据边界",
            "start_row_mode": "手动指定起始行",
            "end_mode": "填充到数据边界",
            "count": "1",
            "end_row": "1",
            "end_field": first,
            "reference_field": first,
            "overwrite_rule": "只填充空单元格",
        }
    if node_type == "序列填充":
        return {
            "target_field": first,
            "start_row": "1",
            "direction": "向下",
            "start_row_mode": "手动指定起始行",
            "start_value": "1",
            "step": "1",
            "count_source_mode": "使用结束条件",
            "end_mode": "填充到数据边界",
            "count": "1",
            "end_row": "1",
            "end_field": first,
            "reference_field": first,
            "overwrite_rule": "覆盖所有目标单元格",
            "zero_pad": "0",
            "prefix": "",
            "suffix": "",
        }
    if node_type == "区域填充":
        return {
            "start_field": first,
            "end_field": second,
            "start_row": "1",
            "end_row": "1",
            "value_source": "手动输入值",
            "manual_value": "",
            "source_field": first,
            "source_end_field": second,
            "source_row": "1",
            "multi_field_fill_direction": "横向填充",
            "source_start_row": "1",
            "source_end_row": "1",
            "source_range_mode": "来源列数据边界",
            "start_row_mode": "手动指定起始行",
            "end_row_mode": "手动指定结束行",
            "reference_field": first,
            "overwrite_rule": "只填充空单元格",
        }
    if node_type == "行数据映射填充":
        return {
            "mode": "按行取值展开",
            "start_row": "1",
            "end_mode": "填充到数据边界",
            "count": "1",
            "end_row": "1",
            "value_fields": [header for header in headers[:3]],
            "keep_fields": [header for header in headers[:2]],
            "output_value_field": "输出内容",
            "output_source_field": True,
            "source_field_name": "来源字段",
            "output_original_row": True,
            "original_row_field": "原始行号",
            "output_status": True,
            "status_field": "状态",
            "empty_mode": "跳过空值",
            "empty_fixed": "未填写",
            "trim_value": True,
        }
    if node_type == "保存中转数据":
        base_name = f"中转_{suffix}"
        export_dir = os.path.join(base_dir, "export")
        return {
            "transit_name": base_name,
            "save_memory": True,
            "save_sqlite": False,
            "sqlite_table": base_name,
            "sqlite_mode": "自动加时间戳",
            "save_xlsx": False,
            "xlsx_path": os.path.join(export_dir, f"{base_name}.xlsx"),
            "stop_after_save": False,
        }
    if node_type == "选定列写入指定表":
        target_table = tables[0] if tables else "选定列结果"
        return {
            "source_type": "当前工作流表",
            "source_sqlite_table": tables[0] if tables else "",
            "source_transit_table": "",
            "selected_fields": list(headers[:3]),
            "target_type": "SQLite表",
            "target_table": target_table,
            "target_transit_table": "选定列结果",
            "write_mode": "复制列到目标表新建字段",
            "field_name_mode": "使用原字段名",
            "target_prefix": "",
            "target_suffix": "",
            "field_mappings": [],
            "overwrite_rule": "只写入空单元格",
            "enable_write": False,
            "backup_before_write": True,
        }
    if node_type == "字段映射写入表":
        target_table = tables[0] if tables else ""
        return {
            "writeback_direction": "当前表写入SQLite目标表",
            "target_table": target_table,
            "source_table": target_table,
            "use_match_rules": True,
            "match_rules": [],
            "field_mappings": [],
            "overwrite_policy": "目标已有值且不同才覆盖",
            "source_empty_policy": "跳过",
            "source_empty_fixed": "",
            "no_match_policy": "跳过并记录",
            "multi_match_policy": "跳过并记录",
            "duplicate_target_policy": "跳过重复并记录异常",
            "enable_write": False,
            "backup_before_write": True,
            "output_preview_table": True,
            "sequential_insert_missing_rows": True,
        }
    if node_type == "高级筛选":
        return {
            "logic": "AND",
            "conditions": [],
            "join_rules": [],
            "join_logic": "AND",
            "extra_tables": [],
            "output_fields": [],
            "result_limit": "5000",
            "max_intermediate": "200000",
            "remove_duplicates": False,
        }
    if node_type == "删除列":
        return {"fields": []}
    if node_type == "移动列":
        return {"order": list(headers)}
    if node_type == "获取文件列表":
        return {
            "directory": base_dir,
            "recursive": True,
            "include_files": True,
            "include_dirs": False,
            "include_hidden": False,
            "extensions": "",
            "name_contains": "",
            "glob_pattern": "*",
            "max_files": "20000",
        }
    if node_type == "批量重命名":
        return {
            "path_field": "完整路径",
            "new_name_field": "新文件名",
            "name_value_type": "仅文件名",
            "new_path_field": "新完整路径",
            "status_field": "重命名状态",
            "auto_append_ext": False,
            "allow_dirs": False,
            "create_target_dirs": False,
            "conflict_mode": "跳过目标已存在",
            "actual_rename": False,
            "write_log": True,
            "log_path": os.path.abspath("rename_log.csv"),
        }
    return {}
