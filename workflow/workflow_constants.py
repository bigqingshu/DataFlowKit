# -*- coding: utf-8 -*-
"""Class-level constants for PlanWorkflowWindow."""


class WorkflowConstantsMixin:
    NODE_TYPES = ["获取文件列表", "节点组 / 子工作流", "循环执行起点", "跳转锚点节点", "无条件跳转节点", "条件判断节点", "条件跳转节点", "批量替换", "数据提取", "格式规范化 / 日期时间解析", "新建日期时间列", "新建列", "合并列", "批量更改列名", "去重 / 重复数据处理", "列数字运算", "匹配值输出列名", "复制列", "复制行", "删除行", "填充值", "序列填充", "区域填充", "行数据映射填充", "保存中转数据", "选定列写入指定表", "字段映射写入表", "高级筛选", "删除列", "移动列", "批量重命名", "循环判断回跳"]
    TABLE_ACCESS_POLICY_CHOICES = ["只审计", "预检确认", "强制拦截"]
    MAX_EXPANDED_ROWS = 200000
    MAX_TARGET_CELLS = 1000000
    TABLE_ACCESS_POLICY_DISPLAY = {
        "audit": "只审计",
        "prompt": "预检确认",
        "strict": "强制拦截",
        "off": "关闭",
    }
    STANDARD_WRITE_MODE_CHOICES = [
        "",
        "current_table_default",
        "create_new",
        "append",
        "overlay_by_order",
        "update_by_key",
        "upsert_by_key",
        "clear_keep_schema",
        "keep_schema_insert",
        "replace_table",
        "timestamp_new",
        "fail_if_exists",
        "write_fields_only",
        "fill_blank_fields",
    ]
    LOGIC_TYPES = ["AND", "OR"]
    FILTER_OPS = ["等于", "不等于", "包含", "不包含", "开头是", "结尾是", "大于", "小于", "大于等于", "小于等于", "为空", "不为空", "正则匹配"]
    FILTER_VALUE_SOURCES = ["固定值", "字段值"]
    REPLACE_MATCH_MODES = ["包含", "完全相等", "开头是", "结尾是", "正则匹配", "为空", "不为空"]
    REPLACE_MODES = ["局部替换匹配字符串", "整格替换为新值"]
    REPLACE_VALUE_SOURCES = ["手动输入", "列字段"]
    REPLACE_ROW_POLICIES = ["当前行", "第一行", "固定行号", "按匹配行号", "按命中序号"]
    EXTRACT_METHODS = [
        "正则提取", "固定位置提取", "从左取N位", "从右取N位", "按分隔符提取",
        "前后关键字之间提取", "指定字符前提取", "指定字符后提取", "删除前缀", "删除后缀"
    ]
    OUTPUT_MODES = ["生成新字段", "覆盖源字段"]
    UNMATCHED_MODES = ["留空", "保留原值", "填写固定值", "跳过该行"]
    FORMAT_PARSE_TYPES = ["日期", "时间", "日期时间"]
    FORMAT_INPUT_STRUCTURES = ["固定位置", "分隔符", "自动识别常见格式"]
    FORMAT_YEAR_RULES = ["20xx", "19xx", "自动窗口", "不补全"]
    FORMAT_DATE_ORDERS = ["年-月-日", "月-日-年", "日-月-年"]
    DATE_AMBIGUOUS_POLICIES = ["警告", "报错", "允许"]
    FORMAT_OUTPUT_MODES = ["生成新字段", "覆盖源字段", "生成多个字段"]
    CURRENT_DATETIME_OUTPUT_MODES = ["生成新字段", "覆盖已有字段"]
    CURRENT_DATETIME_TIME_MODES = ["整次运行固定同一时间", "逐行实时获取"]
    CURRENT_DATETIME_FORMAT_MODES = ["占位符模板", "Python strftime"]
    NEW_COLUMNS_CONFLICT_MODES = ["自动改名", "跳过已有字段", "覆盖已有字段", "存在则报错"]
    NEW_COLUMNS_VALUE_MODES = ["统一默认值", "按列配置值", "空值"]
    SEPARATOR_OPTIONS = ["空字符", "空格", "换行", "Windows换行", "制表符", "-", "_", "/", "\\", "|", ",", ";", ":", ".", "+", "自定义"]
