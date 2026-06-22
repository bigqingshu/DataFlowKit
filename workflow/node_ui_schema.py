# -*- coding: utf-8 -*-
"""Shared UI schema metadata for workflow nodes and config fields.

This module is intentionally independent from Tkinter/Qt.  Frontends can use
it to render menus, node descriptions, warnings, and config forms while the
execution layer continues to depend only on stable ``node_type_id`` values.
"""

from __future__ import annotations

from workflow.default_configs import default_config_for_type
from workflow.protocol_nodes import (
    DEFAULT_NODE_VERSION,
    display_type_for_node_type_id,
    list_node_type_definitions,
    node_type_definition_for,
    normalize_node_type_id,
)


CATEGORY_ORDER = ["文件处理", "流程控制", "数据处理", "输出", "插件", "未知"]

NODE_UI_SCHEMA_VERSION = "2.0"
FORM_SCHEMA_VERSION = "2.0"


NODE_CATEGORY_LABELS = {
    "文件处理": "文件处理",
    "流程控制": "流程控制",
    "数据处理": "数据处理",
    "输出": "输出",
    "插件": "插件",
    "未知": "其他",
}


NODE_FIELD_LABELS = {
    "node_type_id": "节点类型 ID",
    "node_id": "节点 ID",
    "name": "节点名称",
    "enabled": "启用",
    "node_version": "节点版本",
}


CONFIG_FIELD_LABELS = {
    "columns_text": "新字段列表",
    "value_mode": "填充值模式",
    "default_value": "统一默认值",
    "conflict_mode": "字段冲突处理",
    "strip_column_name": "清理字段名前后空白",
    "allow_empty_name": "允许空字段名",
    "target_field": "目标字段",
    "source_field": "源字段",
    "source_fields": "源字段列表",
    "new_field": "新字段名",
    "output_field": "输出字段",
    "output_mode": "输出方式",
    "match_mode": "匹配模式",
    "match_value": "匹配值",
    "replace_value": "替换值",
    "replace_mode": "替换方式",
    "case_sensitive": "区分大小写",
    "match_value_source": "匹配值来源",
    "replace_value_source": "替换值来源",
    "match_value_field": "匹配值字段",
    "replace_value_field": "替换值字段",
    "match_row_policy": "匹配行策略",
    "match_row_index": "匹配固定行号",
    "replace_row_policy": "替换行策略",
    "replace_row_index": "替换固定行号",
    "replace_count": "替换次数",
    "skip_empty_match_value": "跳过空匹配值",
    "method": "提取方法",
    "unmatched_mode": "未匹配处理",
    "unmatched_fixed": "未匹配固定值",
    "strip_result": "清理结果空白",
    "regex_pattern": "正则表达式",
    "regex_group": "正则分组",
    "regex_find_all": "提取所有匹配",
    "regex_joiner": "多匹配连接符",
    "start_pos": "起始位置",
    "extract_len": "提取长度",
    "position_base": "位置基准",
    "n_chars": "字符数",
    "delimiter": "分隔符",
    "part_index": "分段序号",
    "ignore_empty_part": "忽略空分段",
    "before_key": "前关键字",
    "after_key": "后关键字",
    "between_occurrence": "第几次出现",
    "marker": "标记字符",
    "find_mode": "查找方式",
    "prefix": "前缀",
    "suffix": "后缀",
    "parse_type": "解析类型",
    "input_structure": "输入结构",
    "year_start": "年份起始",
    "year_len": "年份长度",
    "month_start": "月份起始",
    "month_len": "月份长度",
    "day_start": "日期起始",
    "day_len": "日期长度",
    "hour_start": "小时起始",
    "hour_len": "小时长度",
    "minute_start": "分钟起始",
    "minute_len": "分钟长度",
    "second_start": "秒起始",
    "second_len": "秒长度",
    "date_delimiter": "日期分隔符",
    "time_delimiter": "时间分隔符",
    "custom_date_delimiter": "自定义日期分隔符",
    "custom_time_delimiter": "自定义时间分隔符",
    "date_order": "日期顺序",
    "ambiguous_date_policy": "歧义日期处理",
    "year_rule": "两位年份规则",
    "auto_window_pivot": "自动窗口分界",
    "output_template": "日期输出模板",
    "time_output_template": "时间输出模板",
    "datetime_output_template": "日期时间输出模板",
    "output_status": "输出解析状态",
    "status_field": "状态字段",
    "component_prefix": "组件字段前缀",
    "time_source_field": "时间源字段",
    "use_separate_time_field": "使用独立时间字段",
    "time_mode": "取时模式",
    "format_mode": "格式模式",
    "template": "模板",
    "strftime_template": "strftime 模板",
    "fields": "字段列表",
    "separators": "分隔符列表",
    "skip_empty": "跳过空值",
    "trim_value": "清理值空白",
    "empty_placeholder": "空值占位",
    "mode": "模式",
    "mappings": "映射规则",
    "scope": "作用范围",
    "scope_fields": "作用字段",
    "duplicate_policy": "重名处理",
    "missing_policy": "缺失字段处理",
    "trim_names": "清理字段名空白",
    "dedupe_mode": "去重模式",
    "key_fields": "关键字段",
    "trim": "清理空白",
    "ignore_case": "忽略大小写",
    "empty_key_policy": "空键处理",
    "keep_policy": "保留策略",
    "add_marker_columns": "添加标记字段",
    "duplicate_group_field": "重复组字段",
    "duplicate_status_field": "重复状态字段",
    "duplicate_index_field": "组内序号字段",
    "duplicate_count_field": "重复次数字段",
    "keep_flag_field": "保留标记字段",
    "operation": "运算",
    "operand_source": "操作数来源",
    "operand_value": "操作数固定值",
    "operand_field": "操作数字段",
    "row_offset": "行偏移",
    "sequence_start": "序列起始",
    "sequence_step": "序列步长",
    "non_number_policy": "非数字处理",
    "non_number_fixed": "非数字固定值",
    "divide_zero_policy": "除零处理",
    "divide_zero_fixed": "除零固定值",
    "decimal_places": "小数位数",
    "range_mode": "范围模式",
    "start_row": "起始行",
    "end_row": "结束行",
    "reference_field": "参考字段",
    "source_row": "源行号",
    "copy_count": "复制次数",
    "insert_mode": "插入方式",
    "insert_row": "插入行号",
    "delete_mode": "删除方式",
    "row_spec": "行号列表",
    "condition_field": "条件字段",
    "condition_op": "条件操作",
    "condition_value": "条件值",
    "empty_mode": "空行判断方式",
    "empty_field": "空值字段",
    "fill_mode": "填充方式",
    "fill_value": "填充值",
    "direction": "方向",
    "end_mode": "结束方式",
    "max_count": "最大数量",
    "area_spec": "区域范围",
    "mapping_rules": "映射规则",
    "field_order": "字段顺序",
    "anchor_id": "锚点 ID",
    "anchor_name": "锚点名称",
    "description": "说明",
    "target_anchor_id": "目标锚点",
    "note": "备注",
    "flag_name": "条件标志",
    "source_type": "数据来源",
    "condition_type": "条件类型",
    "field": "字段",
    "op": "操作",
    "value": "值",
    "true_value": "成立值",
    "false_value": "不成立值",
    "jump_rules": "跳转规则",
    "default_anchor_id": "默认锚点",
}


FIELD_CHOICES = {
    "value_mode": ["统一默认值", "按列配置值", "空值"],
    "conflict_mode": ["自动改名", "跳过已有字段", "覆盖已有字段", "存在则报错"],
    "match_mode": ["包含", "完全相等", "开头是", "结尾是", "正则匹配", "为空", "不为空"],
    "replace_mode": ["局部替换匹配字符串", "整格替换为新值"],
    "match_value_source": ["手动输入", "列字段"],
    "replace_value_source": ["手动输入", "列字段"],
    "match_row_policy": ["当前行", "第一行", "固定行号", "按匹配行号", "按命中序号"],
    "replace_row_policy": ["当前行", "第一行", "固定行号", "按匹配行号", "按命中序号"],
    "method": [
        "正则提取",
        "固定位置提取",
        "从左取N位",
        "从右取N位",
        "按分隔符提取",
        "前后关键字之间提取",
        "指定字符前提取",
        "指定字符后提取",
        "删除前缀",
        "删除后缀",
    ],
    "output_mode": ["生成新字段", "覆盖源字段", "覆盖已有字段", "生成多个字段", "输出去重后的数据"],
    "unmatched_mode": ["留空", "保留原值", "填写固定值", "跳过该行"],
    "position_base": ["从1开始", "从0开始"],
    "find_mode": ["第一次出现", "最后一次出现"],
    "parse_type": ["日期", "时间", "日期时间"],
    "input_structure": ["固定位置", "分隔符", "自动识别常见格式"],
    "date_delimiter": ["自动识别", "-", "/", ".", "无分隔符", "自定义"],
    "time_delimiter": ["自动识别", ":", "无分隔符", "自定义"],
    "date_order": ["年-月-日", "月-日-年", "日-月-年"],
    "ambiguous_date_policy": ["警告", "报错", "允许"],
    "year_rule": ["20xx", "19xx", "自动窗口", "不补全"],
    "time_mode": ["整次运行固定同一时间", "逐行实时获取"],
    "format_mode": ["占位符模板", "Python strftime"],
    "mode": ["手动映射改名", "添加前缀", "添加后缀", "查找替换"],
    "scope": ["全部字段", "指定字段"],
    "duplicate_policy": ["自动追加编号", "存在则覆盖", "存在则跳过", "存在则报错"],
    "missing_policy": ["跳过并记录警告", "缺失则报错"],
    "dedupe_mode": ["指定字段/组合字段去重", "整行完全重复"],
    "empty_key_policy": ["空键参与去重", "空键不参与去重"],
    "keep_policy": ["保留第一条", "保留最后一条", "全部标记不删除"],
    "operation": ["加", "减", "乘", "除", "序号", "取整", "四舍五入"],
    "operand_source": ["固定值", "字段值", "行号", "序列"],
    "non_number_policy": ["留空", "保留原值", "填写固定值", "报错"],
    "divide_zero_policy": ["留空", "保留原值", "填写固定值", "报错"],
    "range_mode": ["全部行", "指定行范围", "参考字段非空行"],
    "insert_mode": ["表尾", "表头", "指定行前", "指定行后"],
    "delete_mode": ["按行号列表", "按行号范围", "按条件", "空行"],
    "condition_op": ["等于", "不等于", "包含", "不包含", "开头是", "结尾是", "大于", "小于", "大于等于", "小于等于", "为空", "不为空", "正则匹配"],
    "op": ["等于", "不等于", "包含", "不包含", "大于", "小于", "大于等于", "小于等于", "为空", "不为空"],
    "empty_mode": ["整行为空", "指定字段为空"],
    "fill_mode": ["固定值", "向下填充", "向上填充"],
    "direction": ["向下", "向上", "向右", "向左"],
    "end_mode": ["直到非空", "指定数量", "到表尾"],
    "source_type": ["当前表"],
    "condition_type": ["表行数", "字段是否存在", "字段值", "字段空值数量", "字段包含值数量"],
}


FIELD_PICKER_KEYS = {
    "target_field",
    "source_field",
    "time_source_field",
    "match_value_field",
    "replace_value_field",
    "operand_field",
    "condition_field",
    "empty_field",
    "reference_field",
    "field",
}

FIELD_MULTI_PICKER_KEYS = {
    "fields",
    "source_fields",
    "scope_fields",
    "key_fields",
    "input_fields",
}

TABLE_PICKER_KEYS = {
    "source_table",
    "transit_table",
    "input_sqlite_table",
    "input_transit_table",
    "output_sqlite_table",
    "output_transit_name",
}


LONG_TEXT_KEYS = {
    "columns_text",
    "regex_pattern",
    "description",
    "note",
}


NODE_CONFIG_LAYOUTS = {
    "core.new_columns": [
        {
            "title": "字段定义",
            "fields": ["columns_text"],
        },
        {
            "title": "填充值",
            "fields": ["value_mode", "default_value"],
        },
        {
            "title": "字段冲突",
            "fields": ["conflict_mode", "strip_column_name", "allow_empty_name"],
        },
    ],
    "core.replace": [
        {
            "title": "目标与匹配",
            "fields": [
                "target_field",
                "match_mode",
                "match_value",
                "case_sensitive",
                "skip_empty_match_value",
            ],
        },
        {
            "title": "替换内容",
            "fields": [
                "replace_mode",
                "replace_value",
                "replace_count",
            ],
        },
        {
            "title": "字段来源",
            "fields": [
                "match_value_source",
                "match_value_field",
                "replace_value_source",
                "replace_value_field",
            ],
        },
        {
            "title": "跨行策略",
            "fields": [
                "match_row_policy",
                "match_row_index",
                "replace_row_policy",
                "replace_row_index",
            ],
        },
    ],
}


FIELD_HELP_TEXTS = {
    "columns_text": "每行一个新字段。使用“字段=值”可为按列配置值模式设置默认值。",
    "value_mode": "控制新字段的初始值来源。",
    "default_value": "当填充值模式为统一默认值时使用。",
    "conflict_mode": "目标字段已存在时的处理方式。",
    "target_field": "要处理的当前表字段。",
    "match_mode": "匹配单元格内容的规则。",
    "match_value": "用于匹配的文本、数字或正则表达式。",
    "replace_mode": "整格替换或只替换命中的局部文本。",
    "replace_value": "替换后的内容。",
    "replace_count": "0 表示替换全部命中。",
    "match_value_source": "匹配值可以手动输入，也可以来自字段。",
    "replace_value_source": "替换值可以手动输入，也可以来自字段。",
}

FIELD_VALIDATION_RULES = {
    "columns_text": {"required": True},
    "target_field": {"required": True},
    "source_field": {"required": True},
    "source_fields": {"required": True},
    "fields": {"required": True},
    "key_fields": {"required": True},
    "new_field": {"required": True},
    "output_field": {"required": True},
    "replace_count": {"integer": True, "min": 0},
    "match_row_index": {"integer": True, "min": 1},
    "replace_row_index": {"integer": True, "min": 1},
    "regex_group": {"integer": True, "min": 0},
    "start_pos": {"integer": True, "min": 0},
    "extract_len": {"integer": True, "min": 0},
    "n_chars": {"integer": True, "min": 0},
    "part_index": {"integer": True, "min": 1},
    "between_occurrence": {"integer": True, "min": 1},
}

FIELD_DYNAMIC_RULES = {
    "default_value": {
        "visible_when": {"field": "value_mode", "equals": "统一默认值"},
        "depends_on": ["value_mode"],
    },
    "match_value": {
        "visible_when": {
            "all": [
                {"field": "match_mode", "not_in": ["为空", "不为空"]},
                {"field": "match_value_source", "equals": "手动输入"},
            ],
        },
        "depends_on": ["match_mode", "match_value_source"],
    },
    "match_value_field": {
        "visible_when": {"field": "match_value_source", "equals": "列字段"},
        "depends_on": ["match_value_source"],
    },
    "replace_value": {
        "visible_when": {"field": "replace_value_source", "equals": "手动输入"},
        "depends_on": ["replace_value_source"],
    },
    "replace_value_field": {
        "visible_when": {"field": "replace_value_source", "equals": "列字段"},
        "depends_on": ["replace_value_source"],
    },
    "match_row_index": {
        "visible_when": {"field": "match_row_policy", "equals": "固定行号"},
        "depends_on": ["match_row_policy"],
    },
    "replace_row_index": {
        "visible_when": {"field": "replace_row_policy", "equals": "固定行号"},
        "depends_on": ["replace_row_policy"],
    },
    "regex_pattern": {
        "visible_when": {"field": "method", "equals": "正则提取"},
        "depends_on": ["method"],
    },
    "regex_group": {
        "visible_when": {"field": "method", "equals": "正则提取"},
        "depends_on": ["method"],
    },
    "regex_find_all": {
        "visible_when": {"field": "method", "equals": "正则提取"},
        "depends_on": ["method"],
    },
    "regex_joiner": {
        "visible_when": {"field": "regex_find_all", "equals": True},
        "depends_on": ["regex_find_all"],
    },
    "start_pos": {
        "visible_when": {"field": "method", "in": ["固定位置提取", "从左取N位", "从右取N位"]},
        "depends_on": ["method"],
    },
    "extract_len": {
        "visible_when": {"field": "method", "equals": "固定位置提取"},
        "depends_on": ["method"],
    },
    "n_chars": {
        "visible_when": {"field": "method", "in": ["从左取N位", "从右取N位"]},
        "depends_on": ["method"],
    },
    "delimiter": {
        "visible_when": {"field": "method", "equals": "按分隔符提取"},
        "depends_on": ["method"],
    },
    "part_index": {
        "visible_when": {"field": "method", "equals": "按分隔符提取"},
        "depends_on": ["method"],
    },
    "ignore_empty_part": {
        "visible_when": {"field": "method", "equals": "按分隔符提取"},
        "depends_on": ["method"],
    },
    "before_key": {
        "visible_when": {"field": "method", "equals": "前后关键字之间提取"},
        "depends_on": ["method"],
    },
    "after_key": {
        "visible_when": {"field": "method", "equals": "前后关键字之间提取"},
        "depends_on": ["method"],
    },
    "between_occurrence": {
        "visible_when": {"field": "method", "equals": "前后关键字之间提取"},
        "depends_on": ["method"],
    },
    "marker": {
        "visible_when": {"field": "method", "in": ["指定字符前提取", "指定字符后提取"]},
        "depends_on": ["method"],
    },
    "find_mode": {
        "visible_when": {"field": "method", "in": ["指定字符前提取", "指定字符后提取"]},
        "depends_on": ["method"],
    },
    "prefix": {
        "visible_when": {"field": "method", "equals": "删除前缀"},
        "depends_on": ["method"],
    },
    "suffix": {
        "visible_when": {"field": "method", "equals": "删除后缀"},
        "depends_on": ["method"],
    },
    "time_source_field": {
        "visible_when": {"field": "use_separate_time_field", "equals": True},
        "depends_on": ["use_separate_time_field"],
    },
    "custom_date_delimiter": {
        "visible_when": {"field": "date_delimiter", "equals": "自定义"},
        "depends_on": ["date_delimiter"],
    },
    "custom_time_delimiter": {
        "visible_when": {"field": "time_delimiter", "equals": "自定义"},
        "depends_on": ["time_delimiter"],
    },
    "strftime_template": {
        "visible_when": {"field": "format_mode", "equals": "Python strftime"},
        "depends_on": ["format_mode"],
    },
    "template": {
        "visible_when": {"field": "format_mode", "equals": "占位符模板"},
        "depends_on": ["format_mode"],
    },
}


NODE_UI_DESCRIPTIONS = {
    "core.file_list": {
        "summary": "读取目录文件清单",
        "description": "从指定目录生成文件列表，作为后续批处理节点的输入。",
        "badges": ["文件输入"],
        "warnings": [],
        "risk": "file_read",
    },
    "core.batch_rename": {
        "summary": "批量修改文件名",
        "description": "根据字段和规则批量重命名文件。",
        "badges": ["文件操作", "仅旧执行链"],
        "warnings": ["执行会修改真实文件名，建议先备份或先做小范围测试。"],
        "risk": "file_action",
    },
    "core.group": {
        "summary": "复用一组子节点",
        "description": "把多个节点组合成子工作流，便于复用复杂步骤。",
        "badges": ["流程控制", "可预览"],
        "warnings": ["Headless 第一版暂不支持节点组内部再放循环执行起点 / 循环判断回跳。"],
        "risk": "workflow_control",
    },
    "core.loop_start": {
        "summary": "循环处理起点",
        "description": "按循环队列逐条执行后续节点。",
        "badges": ["流程控制", "可预览"],
        "warnings": ["循环会多次执行后续节点，请设置合理的最大循环次数。"],
        "risk": "workflow_control",
    },
    "core.loop_judge": {
        "summary": "循环条件回跳",
        "description": "根据循环结果判断继续处理下一条或结束循环。",
        "badges": ["流程控制", "可预览"],
        "warnings": ["需要与同一 loop_id 的循环执行起点配对。"],
        "risk": "workflow_control",
    },
    "core.jump_anchor": {
        "summary": "设置跳转目标",
        "description": "在计划中放置锚点，供跳转节点定位。",
        "badges": ["可预览", "流程控制"],
        "warnings": [],
        "risk": "safe_transform",
    },
    "core.unconditional_jump": {
        "summary": "无条件跳到锚点",
        "description": "执行到该节点时直接跳转到指定锚点。",
        "badges": ["可预览", "流程控制"],
        "warnings": ["请确认目标锚点存在，避免计划执行路径不符合预期。"],
        "risk": "control_flow",
    },
    "core.condition_check": {
        "summary": "生成条件标志",
        "description": "根据表行数、字段值或字段状态生成 TRUE/FALSE 标志。",
        "badges": ["可预览", "流程控制"],
        "warnings": [],
        "risk": "safe_transform",
    },
    "core.conditional_jump": {
        "summary": "按条件跳转",
        "description": "读取条件标志，并按规则跳转到不同锚点。",
        "badges": ["可预览", "流程控制"],
        "warnings": ["条件值未映射时会走默认不跳转或默认锚点。"],
        "risk": "control_flow",
    },
    "core.new_columns": {
        "summary": "添加字段，可设置默认值",
        "description": "添加一个或多个字段，支持统一默认值、空值或“字段=值”批量配置。",
        "badges": ["可预览", "内存转换"],
        "warnings": [],
        "risk": "safe_transform",
    },
    "core.replace": {
        "summary": "按规则批量替换字段内容",
        "description": "在指定字段中按匹配模式替换文本，支持局部替换和整格替换。",
        "badges": ["可预览", "内存转换"],
        "warnings": ["正则匹配或空值匹配可能影响多处内容，请先预览。"],
        "risk": "safe_transform",
    },
    "core.extract": {
        "summary": "从字段中提取文本",
        "description": "用正则、固定位置、分隔符或关键字规则提取字段内容。",
        "badges": ["可预览", "内存转换"],
        "warnings": ["正则提取建议先用小样本预览命中结果。"],
        "risk": "safe_transform",
    },
    "core.datetime_format": {
        "summary": "规范化日期时间",
        "description": "把来源字段解析为标准日期、时间或日期时间格式。",
        "badges": ["可预览", "内存转换"],
        "warnings": ["歧义日期需要确认日期顺序，避免月日互换。"],
        "risk": "safe_transform",
    },
    "core.current_datetime_column": {
        "summary": "添加当前时间字段",
        "description": "生成或覆盖当前日期时间字段，可使用模板或 strftime 格式。",
        "badges": ["可预览", "内存转换"],
        "warnings": [],
        "risk": "safe_transform",
    },
    "core.merge_columns": {
        "summary": "合并多个字段",
        "description": "把多个字段按分隔符合并为一个输出字段。",
        "badges": ["可预览", "内存转换"],
        "warnings": [],
        "risk": "safe_transform",
    },
    "core.rename_columns": {
        "summary": "批量更改字段名",
        "description": "按映射、前缀、后缀或替换规则批量修改字段名。",
        "badges": ["可预览", "结构变更"],
        "warnings": ["字段重名处理会影响后续节点引用，请确认冲突策略。"],
        "risk": "schema_transform",
    },
    "core.dedupe": {
        "summary": "按字段或整行去重",
        "description": "根据关键字段或整行内容识别重复数据，可删除或添加标记字段。",
        "badges": ["可预览", "行变更"],
        "warnings": ["去重可能减少行数，请先确认关键字段和保留策略。"],
        "risk": "row_transform",
    },
    "core.numeric_column": {
        "summary": "字段数值运算",
        "description": "对数字字段做加减乘除、序号、取整等运算。",
        "badges": ["可预览", "内存转换"],
        "warnings": ["请确认非数字和除零处理策略。"],
        "risk": "safe_transform",
    },
    "core.copy_column": {
        "summary": "复制字段内容",
        "description": "把一个字段复制到新字段或覆盖已有字段。",
        "badges": ["可预览", "内存转换"],
        "warnings": [],
        "risk": "safe_transform",
    },
    "core.copy_row": {
        "summary": "复制指定行",
        "description": "复制某一行并插入到表头、表尾或指定位置。",
        "badges": ["可预览", "行变更"],
        "warnings": ["复制行会增加行数，请确认插入位置。"],
        "risk": "row_transform",
    },
    "core.delete_rows": {
        "summary": "删除指定行",
        "description": "按行号、范围、条件或空行规则删除行。",
        "badges": ["可预览", "行变更"],
        "warnings": ["删除行会减少数据，请先预览确认命中范围。"],
        "risk": "row_transform",
    },
    "core.delete_columns": {
        "summary": "删除字段",
        "description": "从当前表删除一个或多个字段。",
        "badges": ["可预览", "结构变更"],
        "warnings": ["删除字段会影响后续节点引用，请先确认字段列表。"],
        "risk": "schema_transform",
    },
    "core.move_columns": {
        "summary": "调整字段顺序",
        "description": "移动字段到指定位置，整理输出表结构。",
        "badges": ["可预览", "结构变更"],
        "warnings": [],
        "risk": "schema_transform",
    },
    "core.fill_value": {
        "summary": "按规则填充值",
        "description": "向目标字段填入固定值，或按上下方向补齐空值。",
        "badges": ["可预览", "内存转换"],
        "warnings": ["覆盖已有值前请确认填充范围。"],
        "risk": "safe_transform",
    },
    "core.sequence_fill": {
        "summary": "生成序列值",
        "description": "按起始值和步长向字段填入序列。",
        "badges": ["可预览", "内存转换"],
        "warnings": [],
        "risk": "safe_transform",
    },
    "core.area_fill": {
        "summary": "按区域填充",
        "description": "对指定行列区域批量填充值。",
        "badges": ["可预览", "内存转换"],
        "warnings": ["区域范围过大时可能影响大量单元格，请先预览。"],
        "risk": "safe_transform",
    },
    "core.row_data_mapping": {
        "summary": "按行映射填充",
        "description": "根据规则从同行或相邻行取值并填充目标字段。",
        "badges": ["可预览", "内存转换"],
        "warnings": ["请确认映射规则和字段来源。"],
        "risk": "safe_transform",
    },
    "core.match_value_output": {
        "summary": "匹配值并输出列名",
        "description": "在查找表中匹配值，并输出命中的字段名或行信息。",
        "badges": ["仅旧执行链", "多表查询"],
        "warnings": ["新界面第一版暂未接入多表查询服务。"],
        "risk": "unsupported_headless",
    },
    "core.filter": {
        "summary": "多条件/多表筛选",
        "description": "按条件、字段和多表匹配规则筛选数据。",
        "badges": ["仅旧执行链", "多表查询"],
        "warnings": ["新界面第一版暂未接入高级筛选窗口和多表服务。"],
        "risk": "unsupported_headless",
    },
    "core.save_transit": {
        "summary": "保存中转数据",
        "description": "把当前结果保存为中转表，供后续节点引用。",
        "badges": ["仅旧执行链", "状态写入"],
        "warnings": ["执行会写入工作流上下文或外部存储，新界面第一版暂不执行。"],
        "risk": "state_write",
    },
    "core.selected_columns_write": {
        "summary": "选定列写入目标表",
        "description": "把选定字段写入当前表、中转表或 SQLite 表。",
        "badges": ["仅旧执行链", "写表"],
        "warnings": ["执行可能写入目标表，建议先备份并确认写入模式。"],
        "risk": "database_write",
    },
    "core.writeback": {
        "summary": "字段映射写回表",
        "description": "按匹配规则和字段映射写回目标 SQLite 表。",
        "badges": ["仅旧执行链", "写表"],
        "warnings": ["执行会修改目标数据库表，请先备份并确认匹配规则。"],
        "risk": "database_write",
    },
    "core.plugin": {
        "summary": "调用插件节点",
        "description": "运行 Python 插件或外部进程插件。",
        "badges": ["插件", "仅旧执行链"],
        "warnings": ["新界面第一版暂未加载插件注册表。"],
        "risk": "plugin_external",
    },
}


def category_label(category):
    return NODE_CATEGORY_LABELS.get(category or "未知", category or "其他")


def node_display_label(node_type_id):
    return display_type_for_node_type_id(node_type_id)


def node_field_label(key):
    return NODE_FIELD_LABELS.get(key, key)


def config_field_label(key):
    return CONFIG_FIELD_LABELS.get(key, key.replace("_", " "))


def choices_for_field(key, headers=None, table_names=None, table_columns=None):
    headers = [str(item) for item in (headers or [])]
    table_names = [str(item) for item in (table_names or [])]
    if key in FIELD_PICKER_KEYS or key in FIELD_MULTI_PICKER_KEYS:
        return headers
    if key in TABLE_PICKER_KEYS:
        return table_names
    return FIELD_CHOICES.get(key, [])


def is_long_text_field(key):
    return key in LONG_TEXT_KEYS


def config_layout_for_node(node_type_id):
    return NODE_CONFIG_LAYOUTS.get(normalize_node_type_id(node_type_id), [])


def field_help_text(key):
    return FIELD_HELP_TEXTS.get(key, "")


def options_source_for_field(key):
    if key in FIELD_PICKER_KEYS or key in FIELD_MULTI_PICKER_KEYS:
        return {"type": "preview_headers"}
    if key in TABLE_PICKER_KEYS:
        return {"type": "table_names"}
    return None


def validation_for_field(key):
    return dict(FIELD_VALIDATION_RULES.get(key, {}))


def dynamic_rules_for_field(key):
    payload = dict(FIELD_DYNAMIC_RULES.get(key, {}))
    if "depends_on" in payload:
        payload["depends_on"] = list(payload["depends_on"])
    return payload


def node_menu_path(node_type_id, category=""):
    """Return the menu path a UI can use for tree/menu rendering."""

    stable_id = normalize_node_type_id(node_type_id)
    category = category or node_type_definition_for(stable_id).get("category", "未知")
    return [category_label(category), display_type_for_node_type_id(stable_id)]


def menu_group_for_node(node_type_id, category=""):
    """Return a stable top-level menu group key for UI shells."""

    stable_id = normalize_node_type_id(node_type_id)
    category = category or node_type_definition_for(stable_id).get("category", "未知")
    return category_label(category)


def submenu_path_for_node(node_type_id, category=""):
    """Return submenu-only segments under the top-level group."""

    path = node_menu_path(node_type_id, category)
    return path[1:] if len(path) > 1 else path


def node_ui_description(node_type_id, supported_headless=None):
    stable_id = normalize_node_type_id(node_type_id)
    payload = dict(NODE_UI_DESCRIPTIONS.get(stable_id, {}))
    if not payload:
        payload = {
            "summary": "暂无说明",
            "description": "该节点尚未配置中文 UI 说明。",
            "badges": [],
            "warnings": [],
            "risk": "unknown",
        }
    if supported_headless is False and "仅旧执行链" not in payload["badges"]:
        payload["badges"] = list(payload["badges"]) + ["仅旧执行链"]
    if supported_headless is True and "可预览" not in payload["badges"]:
        payload["badges"] = ["可预览"] + list(payload["badges"])
    return payload


def config_field_schema(key, value=None, *, headers=None, table_names=None, table_columns=None):
    choices = choices_for_field(
        key,
        headers=headers,
        table_names=table_names,
        table_columns=table_columns,
    )
    if key in FIELD_PICKER_KEYS:
        field_type = "field_select"
    elif key in FIELD_MULTI_PICKER_KEYS:
        field_type = "field_multi_select"
    elif key in TABLE_PICKER_KEYS:
        field_type = "table_select"
    elif key in FIELD_CHOICES:
        field_type = "select"
    elif key in LONG_TEXT_KEYS:
        field_type = "textarea"
    elif isinstance(value, bool):
        field_type = "bool"
    elif isinstance(value, int) and not isinstance(value, bool):
        field_type = "number"
    elif isinstance(value, float):
        field_type = "number"
    elif isinstance(value, (list, dict)):
        field_type = "json"
    else:
        field_type = "text"
    schema = {
        "key": key,
        "label": config_field_label(key),
        "type": field_type,
        "choices": list(choices),
        "default": value,
        "help": field_help_text(key),
    }
    options_source = options_source_for_field(key)
    if options_source:
        schema["options_source"] = options_source
    validation = validation_for_field(key)
    if validation:
        schema["validation"] = validation
        if validation.get("required"):
            schema["required"] = True
    schema.update(dynamic_rules_for_field(key))
    return schema


def config_form_groups_for_node(
    node_type_id,
    default_config=None,
    *,
    headers=None,
    table_names=None,
    table_columns=None,
):
    stable_id = normalize_node_type_id(node_type_id)
    config = dict(default_config or {})
    groups = []
    used = set()
    for spec in config_layout_for_node(stable_id):
        fields = [key for key in spec.get("fields", []) if key in config]
        if not fields:
            continue
        groups.append({
            "title": spec.get("title", "参数"),
            "fields": [
                config_field_schema(
                    key,
                    config.get(key),
                    headers=headers,
                    table_names=table_names,
                    table_columns=table_columns,
                )
                for key in fields
            ],
        })
        used.update(fields)

    remaining = [key for key in config.keys() if key not in used]
    if remaining:
        groups.append({
            "title": "其他参数",
            "fields": [
                config_field_schema(
                    key,
                    config.get(key),
                    headers=headers,
                    table_names=table_names,
                    table_columns=table_columns,
                )
                for key in remaining
            ],
        })
    return groups


def build_node_ui_schema(node_type_id, *, preview_headers=None, table_names=None, table_columns=None):
    stable_id = normalize_node_type_id(node_type_id)
    definition = node_type_definition_for(stable_id)
    display_name = definition.get("display_name") or display_type_for_node_type_id(stable_id)
    category = definition.get("category", "未知")
    supported_headless = bool(definition.get("supported_headless", False))
    meta = node_ui_description(stable_id, supported_headless=supported_headless)
    default_config = default_config_for_type(
        display_name,
        preview_headers=preview_headers,
        table_names=table_names,
        table_columns=table_columns,
    )
    category_index = CATEGORY_ORDER.index(category) if category in CATEGORY_ORDER else len(CATEGORY_ORDER)
    return {
        "schema_version": NODE_UI_SCHEMA_VERSION,
        "node_type_id": stable_id,
        "node_version": DEFAULT_NODE_VERSION,
        "display_name": display_name,
        "category": category,
        "category_label": category_label(category),
        "menu": {
            "path": node_menu_path(stable_id, category),
            "group": menu_group_for_node(stable_id, category),
            "submenu": submenu_path_for_node(stable_id, category),
            "order": category_index * 1000,
        },
        "summary": meta.get("summary", ""),
        "description": meta.get("description", ""),
        "badges": list(meta.get("badges", [])),
        "warnings": list(meta.get("warnings", [])),
        "risk": meta.get("risk", "unknown"),
        "capabilities": {
            "headless_preview": supported_headless,
            "headless_run": supported_headless,
            "execute_actions": False,
        },
        "form": {
            "schema_version": FORM_SCHEMA_VERSION,
            "dynamic_rules": True,
            "groups": config_form_groups_for_node(
                stable_id,
                default_config,
                headers=preview_headers,
                table_names=table_names,
                table_columns=table_columns,
            ),
        },
        "default_config": default_config,
    }


def list_node_ui_schemas(include_unsupported=True, *, preview_headers=None, table_names=None, table_columns=None):
    return [
        build_node_ui_schema(
            item["node_type_id"],
            preview_headers=preview_headers,
            table_names=table_names,
            table_columns=table_columns,
        )
        for item in list_node_type_definitions(include_unsupported=include_unsupported)
    ]


def build_node_ui_catalog(include_unsupported=True, *, preview_headers=None, table_names=None, table_columns=None):
    schemas = list_node_ui_schemas(
        include_unsupported=include_unsupported,
        preview_headers=preview_headers,
        table_names=table_names,
        table_columns=table_columns,
    )
    groups = []
    grouped_entries = {}
    for item in schemas:
        menu = item.get("menu") or {}
        group = str(menu.get("group") or item.get("category_label") or "其他")
        grouped_entries.setdefault(group, []).append({
            "node_type_id": item.get("node_type_id", ""),
            "display_name": item.get("display_name", ""),
            "summary": item.get("summary", ""),
            "badges": list(item.get("badges") or []),
            "warnings": list(item.get("warnings") or []),
            "submenu": list(menu.get("submenu") or []),
            "path": list(menu.get("path") or []),
            "supported_headless": bool((item.get("capabilities") or {}).get("headless_preview")),
            "risk": item.get("risk", "unknown"),
            "order": int(menu.get("order", 0) or 0),
        })

    order_lookup = {category_label(name): index for index, name in enumerate(CATEGORY_ORDER)}
    for group_name, entries in grouped_entries.items():
        entries.sort(key=lambda entry: (entry.get("order", 0), entry.get("display_name", "")))
        groups.append({
            "group": group_name,
            "order": order_lookup.get(group_name, len(order_lookup)),
            "items": entries,
        })
    groups.sort(key=lambda item: (item.get("order", 0), item.get("group", "")))
    return {
        "schema_version": NODE_UI_SCHEMA_VERSION,
        "groups": groups,
        "items": schemas,
    }


def get_node_ui_schema(node_type_id, *, preview_headers=None, table_names=None, table_columns=None):
    return build_node_ui_schema(
        node_type_id,
        preview_headers=preview_headers,
        table_names=table_names,
        table_columns=table_columns,
    )


def node_summary(node_type_id):
    return node_ui_description(node_type_id).get("summary", "")


def node_badges(node_type_id, supported_headless=None):
    return list(node_ui_description(node_type_id, supported_headless=supported_headless).get("badges", []))


def node_warnings(node_type_id, supported_headless=None):
    return list(node_ui_description(node_type_id, supported_headless=supported_headless).get("warnings", []))


def format_node_detail(node_type_id, *, display_name="", category="", supported_headless=None):
    stable_id = normalize_node_type_id(node_type_id)
    meta = node_ui_description(stable_id, supported_headless=supported_headless)
    title = display_name or display_type_for_node_type_id(stable_id)
    lines = [
        f"节点：{title}",
        f"类型：{stable_id}",
    ]
    if category:
        lines.append(f"分类：{category_label(category)}")
    badges = meta.get("badges") or []
    if badges:
        lines.append("能力：" + "、".join(badges))
    if meta.get("risk"):
        lines.append(f"风险：{meta.get('risk')}")
    lines.extend(["", meta.get("description") or meta.get("summary") or "暂无说明"])
    warnings = meta.get("warnings") or []
    if warnings:
        lines.append("")
        lines.append("注意：")
        lines.extend(f"- {item}" for item in warnings)
    if supported_headless is False:
        lines.append("")
        lines.append("当前 headless 预览暂不支持该节点，可保存计划后回到旧 UI 执行。")
    return "\n".join(lines)
