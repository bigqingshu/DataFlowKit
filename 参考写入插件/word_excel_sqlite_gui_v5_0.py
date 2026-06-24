# -*- coding: utf-8 -*-
"""
Word 批量结构化入库 / SQLite 预览 / 替换计划 / win32com 回写工具

适用环境：
    Windows + Microsoft Word + Python 3.9+ + pywin32

安装依赖：
    pip install pywin32

主要功能：
    1. 使用 Python + win32com 调用 Word
    2. 批量扫描 doc/docx/docm
    3. 抽取正文、表格、页眉页脚、文本框/艺术字文字、形状信息、内容控件、书签、域信息
    4. 对 docx/docm 或临时转换后的 docx 提取 word/media/* 并计算图片/媒体 hash
    5. 保存到 SQLite
    6. GUI 预览 documents / content_blocks / media_blocks / replace_rules / replace_plan / replace_log
    7. 基于规则生成替换计划
    8. 按“副本回写 + 旧值校验 + 日志记录”的方式回写 Word

说明：
    - 本脚本优先保证通用性和可实验性，不追求第一次就覆盖 Word 全部边缘格式。
    - 页码只作为辅助显示，不作为唯一定位。
    - 图片、复杂对象、艺术字等：文字可抽取时进入 content_blocks；媒体文件进入 media_blocks。
    - 对于艺术字/形状，Word COM 不同版本暴露接口略有差异，脚本做了安全降级。
"""

import os
import re
import json
import time
import queue
import shutil
import sqlite3
import hashlib
import zipfile
import tempfile
import threading
import traceback
import unicodedata
from pathlib import Path
from datetime import datetime

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog


APP_NAME = "Word Excel SQLite Template Generator v5.0"

# v4.7 精简版：旧新映射、替换规则、替换计划回写流程已从 GUI 屏蔽。
# 保留核心流程：Word 入库 -> 模板登记 -> template_fields/generation_data -> generation_plan -> 定位直写生成。
MAPPING_FLOW_DISABLED = True

DB_VERSION = 3


# -----------------------------
# Word 常量：避免强依赖 win32com.constants
# -----------------------------

class Wd:
    wdAlertsNone = 0
    wdDoNotSaveChanges = 0
    wdSaveChanges = -1

    wdFormatXMLDocument = 12
    wdFormatXMLDocumentMacroEnabled = 13

    wdReplaceNone = 0
    wdReplaceOne = 1
    wdReplaceAll = 2

    wdFindStop = 0

    wdStatisticPages = 2

    wdActiveEndPageNumber = 3
    wdWithInTable = 12

    # StoryType
    wdMainTextStory = 1
    wdFootnotesStory = 2
    wdEndnotesStory = 3
    wdCommentsStory = 4
    wdTextFrameStory = 5
    wdEvenPagesHeaderStory = 6
    wdPrimaryHeaderStory = 7
    wdEvenPagesFooterStory = 8
    wdPrimaryFooterStory = 9
    wdFirstPageHeaderStory = 10
    wdFirstPageFooterStory = 11


STORY_TYPE_NAMES = {
    1: "正文",
    2: "脚注",
    3: "尾注",
    4: "批注",
    5: "文本框/形状文本",
    6: "偶数页页眉",
    7: "主页眉",
    8: "偶数页页脚",
    9: "主页脚",
    10: "首页页眉",
    11: "首页页脚",
}


# -----------------------------
# GUI 空表列名配置
# 作用：
#   1. SQLite 表刚创建、还没有数据时，Treeview 也能显示列名。
#   2. 旧数据库某些表还没插入数据时，不会出现“只有表页签，没有列名”的情况。
#   3. 这些列名与 init_db() 中的建表字段保持一致。
# -----------------------------

TABLE_DISPLAY_COLUMNS = {
    "documents": [
        "doc_id", "file_path", "file_name", "file_ext", "file_hash", "file_size",
        "modified_time", "extract_time", "page_count", "status", "note"
    ],
    "content_blocks": [
        "block_id", "doc_id", "block_type", "story_seq", "story_type", "story_name", "page_no",
        "paragraph_index", "table_index", "row_index", "col_index", "cell_index",
        "shape_scope", "shape_index", "shape_name", "inline_shape_index",
        "content_control_index", "bookmark_name", "field_index",
        "range_start", "range_end",
        "raw_text", "norm_text", "text_hash",
        "context_before", "context_after", "location_json", "extra_json", "created_at"
    ],
    "media_blocks": [
        "media_id", "doc_id", "media_kind", "media_name", "media_path", "media_ext",
        "media_size", "media_hash", "source_note", "location_json", "extra_json", "created_at"
    ],
    "template_docs": [
        "template_id", "enabled", "template_name", "template_path", "template_hash",
        "template_type", "filename_template", "output_dir", "doc_id", "status",
        "remark", "created_at", "updated_at"
    ],
    "template_fields": [
        "field_id", "template_id", "field_key", "block_id", "block_type", "old_value",
        "replace_mode", "required", "default_value", "remark", "created_at", "updated_at"
    ],
    "generation_data": [
        "row_id", "enabled", "batch_name", "data_id", "template_id", "template_name",
        "output_name", "output_dir", "field_key", "field_value",
        "remark", "created_at", "updated_at"
    ],
    "generation_plan": [
        "gen_id", "batch_name", "template_id", "data_id", "output_name", "output_path",
        "template_hash_at_plan", "status", "field_count", "missing_fields", "conflict_info",
        "error", "created_at", "updated_at"
    ],
    "generation_field_plan": [
        "item_id", "gen_id", "template_id", "field_id", "field_key", "block_id", "block_type",
        "old_value", "new_value", "replace_mode", "status", "error",
        "current_text_at_write", "created_at", "updated_at"
    ],
    "generation_log": [
        "log_id", "gen_id", "item_id", "action", "status", "message", "created_at"
    ],
    "excel_template_docs": [
        "excel_template_id", "enabled", "template_name", "template_path", "file_ext", "file_hash",
        "filename_template", "output_dir", "status", "remark", "created_at", "updated_at"
    ],
    "excel_content_blocks": [
        "excel_block_id", "excel_template_id", "sheet_index", "sheet_name", "row_index", "col_index",
        "cell_address", "raw_value", "formula", "number_format", "is_merged", "merge_area", "created_at"
    ],
    "excel_template_fields": [
        "excel_field_id", "excel_template_id", "field_key", "excel_block_id", "sheet_name", "cell_address",
        "old_value", "write_mode", "required", "default_value", "remark", "created_at", "updated_at"
    ],
    "excel_generation_data": [
        "row_id", "enabled", "batch_name", "data_id", "excel_template_id", "template_name",
        "output_name", "output_dir", "field_key", "field_value", "remark", "created_at", "updated_at"
    ],
    "excel_generation_plan": [
        "excel_gen_id", "batch_name", "excel_template_id", "data_id", "output_name", "output_path",
        "template_hash_at_plan", "status", "field_count", "missing_fields", "conflict_info", "error", "created_at", "updated_at"
    ],
    "excel_generation_field_plan": [
        "excel_item_id", "excel_gen_id", "excel_template_id", "excel_field_id", "field_key", "excel_block_id",
        "sheet_name", "row_index", "col_index", "cell_address", "old_value", "new_value", "write_mode",
        "status", "error", "current_text_at_write", "created_at", "updated_at"
    ],
    "excel_generation_log": [
        "excel_log_id", "excel_gen_id", "excel_item_id", "action", "status", "message", "created_at"
    ],
    "old_new_map": [
        "map_id", "enabled", "priority", "group_name", "old_value", "new_value",
        "match_mode", "replace_mode", "scope", "file_match", "table_match",
        "row_match", "col_match", "context_required", "source_key", "remark",
        "created_at", "updated_at"
    ],
    "replace_rules": [
        "rule_id", "enabled", "priority", "scope", "file_match", "table_match",
        "row_match", "col_match", "match_mode", "old_value", "new_value",
        "context_required", "replace_mode", "remark", "created_at", "updated_at"
    ],
    "replace_plan": [
        "plan_id", "doc_id", "block_id", "rule_id", "map_id", "source_type",
        "file_path", "block_type", "old_text", "new_text",
        "rule_old_value", "rule_new_value", "rule_match_mode", "rule_replace_mode",
        "match_reason", "confidence", "status", "output_path",
        "error", "current_text_at_write", "created_at", "updated_at"
    ],
    "replace_log": [
        "log_id", "plan_id", "doc_id", "block_id", "action", "status",
        "old_text", "new_text", "message", "created_at"
    ],
}


def default_columns_for_table(table_name: str):
    return TABLE_DISPLAY_COLUMNS.get(table_name, [])


# -----------------------------
# GUI 中文列名配置
# 注意：
#   1. SQLite 真实字段仍然使用英文，程序内部查询/更新不受影响。
#   2. GUI 表头显示中文 + 英文字段，便于人工核对。
#   3. 双击编辑窗口里的 JSON 键仍然是英文，这是为了能直接保存回 SQLite。
# -----------------------------

COLUMN_CN_NAMES = {
    # 通用字段
    "enabled": "是否启用",
    "priority": "优先级",
    "created_at": "创建时间",
    "updated_at": "更新时间",
    "remark": "备注",
    "status": "状态",
    "error": "错误信息",
    "batch_name": "批次名称",
    "data_id": "数据编号",
    "output_name": "输出文件名",
    "output_path": "输出路径",
    "output_dir": "输出目录",

    # documents 文档表
    "doc_id": "文档ID",
    "file_path": "文件路径",
    "file_name": "文件名",
    "file_ext": "文件扩展名",
    "file_hash": "文件哈希",
    "file_size": "文件大小",
    "modified_time": "修改时间",
    "extract_time": "抽取时间",
    "page_count": "页数",
    "note": "说明",

    # content_blocks 内容块表
    "block_id": "内容块ID",
    "block_type": "内容块类型",
    "story_seq": "故事流序号",
    "story_type": "故事流类型",
    "story_name": "故事流名称",
    "page_no": "页码",
    "paragraph_index": "段落序号",
    "table_index": "表格编号",
    "row_index": "行号",
    "col_index": "列号",
    "cell_index": "单元格序号",
    "shape_scope": "形状范围",
    "shape_index": "形状序号",
    "shape_name": "形状名称",
    "inline_shape_index": "内嵌形状序号",
    "content_control_index": "内容控件序号",
    "bookmark_name": "书签名称",
    "field_index": "域序号",
    "range_start": "Range起点",
    "range_end": "Range终点",
    "raw_text": "原始文字",
    "norm_text": "规范化文字",
    "text_hash": "文字哈希",
    "context_before": "前文",
    "context_after": "后文",
    "location_json": "位置信息JSON",
    "extra_json": "额外信息JSON",

    # media_blocks 媒体表
    "media_id": "媒体ID",
    "media_kind": "媒体类型",
    "media_name": "媒体名称",
    "media_path": "媒体路径",
    "media_ext": "媒体扩展名",
    "media_size": "媒体大小",
    "media_hash": "媒体哈希",
    "source_note": "来源说明",

    # template_docs 模板文件表
    "template_id": "模板ID",
    "template_name": "模板名称",
    "template_path": "模板路径",
    "template_hash": "模板哈希",
    "template_type": "模板类型",
    "filename_template": "文件名模板",

    # template_fields 模板字段表
    "field_id": "字段ID",
    "field_key": "字段名称",
    "old_value": "模板旧值",
    "replace_mode": "替换方式",
    "required": "是否必填",
    "default_value": "默认值",

    # generation_data 批量生成数据表
    "row_id": "生成数据ID",
    "gen_data_id": "生成数据ID",
    "template_name": "模板名称",
    "field_value": "字段新值",

    # generation_plan 生成计划表
    "gen_id": "生成计划ID",
    "template_hash_at_plan": "计划时模板哈希",
    "field_count": "字段数量",
    "missing_fields": "缺失字段",
    "conflict_info": "冲突信息",

    # generation_field_plan 字段生成计划表
    "item_id": "字段计划ID",
    "field_id": "模板字段ID",
    "new_value": "新值",
    "current_text_at_write": "回写时实际文本",

    # generation_log 生成日志表
    "log_id": "日志ID",
    "action": "操作类型",
    "message": "日志信息",

    # old_new_map 旧新映射表
    "map_id": "映射ID",
    "group_name": "分组名称",
    "match_mode": "匹配方式",
    "scope": "作用范围",
    "file_match": "文件名匹配",
    "table_match": "表格号匹配",
    "row_match": "行号匹配",
    "col_match": "列号匹配",
    "context_required": "必须包含上下文",
    "source_key": "来源标识",

    # replace_rules 替换规则表
    "rule_id": "规则ID",

    # replace_plan 替换计划表
    "plan_id": "替换计划ID",
    "source_type": "来源类型",
    "file_path": "文件路径",
    "old_text": "原始整块文本",
    "new_text": "替换后整块文本",
    "rule_old_value": "规则旧值",
    "rule_new_value": "规则新值",
    "rule_match_mode": "规则匹配方式",
    "rule_replace_mode": "规则替换方式",
    "match_reason": "匹配原因",
    "confidence": "置信度",

    # replace_log 替换日志表
    # old_text/new_text 在上面已翻译
}


def cn_col_name(col_name: str) -> str:
    """返回中文列名。找不到翻译时返回原英文字段。"""
    return COLUMN_CN_NAMES.get(col_name, col_name)


def cn_heading_text(col_name: str, show_english: bool = True) -> str:
    """
    Treeview 表头显示文本。
    默认显示：中文名(英文字段)。
    """
    cn = cn_col_name(col_name)
    if show_english and cn != col_name:
        return f"{cn}({col_name})"
    return cn


def cn_detail_label(col_name: str) -> str:
    """详情/提示中显示：中文名（英文字段）。"""
    cn = cn_col_name(col_name)
    if cn != col_name:
        return f"{cn}（{col_name}）"
    return col_name



# -----------------------------
# 通用工具函数
# -----------------------------

def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def safe_str(value, default=""):
    try:
        if value is None:
            return default
        return str(value)
    except Exception:
        return default


def sha256_file(path, chunk_size=1024 * 1024):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            data = f.read(chunk_size)
            if not data:
                break
            h.update(data)
    return h.hexdigest()


def sha256_bytes(data: bytes):
    return hashlib.sha256(data).hexdigest()


def clean_word_text(text: str) -> str:
    """
    Word Range.Text 常见结尾：
        段落：\r
        表格单元格：\r\x07
    """
    if text is None:
        return ""
    text = str(text)
    text = text.replace("\x00", "")
    text = text.replace("\x07", "")
    text = text.replace("\r", "\n")
    text = text.replace("\v", "\n")
    return text.strip()


def normalize_text(text: str) -> str:
    """
    规范化文本：用于匹配，不用于回写。
    可后续按你的业务继续增加规则，例如：
        - 去除全角/半角差异
        - 英文大小写
        - 多空格归一
        - 特定符号替换
    """
    text = clean_word_text(text)
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\u3000", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n+", "\n", text)
    return text.strip()


def make_json(obj):
    try:
        return json.dumps(obj, ensure_ascii=False)
    except Exception:
        return "{}"


def parse_json(s, default=None):
    if default is None:
        default = {}
    try:
        if not s:
            return default
        return json.loads(s)
    except Exception:
        return default


def safe_get(obj, attr, default=None):
    try:
        return getattr(obj, attr)
    except Exception:
        return default


def safe_call(func, default=None):
    try:
        return func()
    except Exception:
        return default


def safe_com_text(obj, attr_chain, default=""):
    """
    attr_chain 示例：
        ["TextFrame", "TextRange", "Text"]
        ["TextFrame2", "TextRange", "Text"]
    """
    cur = obj
    try:
        for attr in attr_chain:
            cur = getattr(cur, attr)
        return clean_word_text(cur)
    except Exception:
        return default


def short_error(e):
    return f"{type(e).__name__}: {e}"


def ensure_parent(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)


def is_word_file(path: Path):
    if path.name.startswith("~$"):
        return False
    return path.suffix.lower() in [".doc", ".docx", ".docm"]


def is_excel_file(path: Path):
    """判断是否为可处理的 Excel 模板文件。"""
    if path.name.startswith("~$"):
        return False
    return path.suffix.lower() in [".xls", ".xlsx", ".xlsm"]


def excel_col_letter(col_index: int) -> str:
    """1-based 列号转 Excel 字母列，例如 1 -> A, 28 -> AB。"""
    col_index = int(col_index)
    result = ""
    while col_index > 0:
        col_index, rem = divmod(col_index - 1, 26)
        result = chr(65 + rem) + result
    return result or "A"


def excel_cell_address(row_index: int, col_index: int) -> str:
    return f"{excel_col_letter(col_index)}{int(row_index)}"


# -----------------------------
# SQLite 管理
# -----------------------------

class DBManager:
    def __init__(self, db_path):
        self.db_path = Path(db_path)

    def connect(self):
        ensure_parent(self.db_path)
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    def _ensure_columns(self, cur, table_name, columns):
        """为旧数据库补字段，避免重新建库。"""
        existing = {row[1] for row in cur.execute(f"PRAGMA table_info({table_name})").fetchall()}
        for col, col_type in columns.items():
            if col not in existing:
                cur.execute(f"ALTER TABLE {table_name} ADD COLUMN {col} {col_type}")

    def init_db(self):
        with self.connect() as conn:
            cur = conn.cursor()

            cur.execute("""
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT
            )
            """)

            cur.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                doc_id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT UNIQUE NOT NULL,
                file_name TEXT NOT NULL,
                file_ext TEXT,
                file_hash TEXT,
                file_size INTEGER,
                modified_time TEXT,
                extract_time TEXT,
                page_count INTEGER,
                status TEXT DEFAULT 'ok',
                note TEXT
            )
            """)

            cur.execute("""
            CREATE TABLE IF NOT EXISTS content_blocks (
                block_id INTEGER PRIMARY KEY AUTOINCREMENT,
                doc_id INTEGER NOT NULL,
                block_type TEXT NOT NULL,
                story_seq INTEGER,
                story_type INTEGER,
                story_name TEXT,
                page_no INTEGER,

                paragraph_index INTEGER,
                table_index INTEGER,
                row_index INTEGER,
                col_index INTEGER,
                cell_index INTEGER,

                shape_scope TEXT,
                shape_index INTEGER,
                shape_name TEXT,
                inline_shape_index INTEGER,

                content_control_index INTEGER,
                bookmark_name TEXT,
                field_index INTEGER,

                range_start INTEGER,
                range_end INTEGER,

                raw_text TEXT,
                norm_text TEXT,
                text_hash TEXT,

                context_before TEXT,
                context_after TEXT,
                location_json TEXT,
                extra_json TEXT,

                created_at TEXT,
                FOREIGN KEY(doc_id) REFERENCES documents(doc_id) ON DELETE CASCADE
            )
            """)

            cur.execute("""
            CREATE TABLE IF NOT EXISTS media_blocks (
                media_id INTEGER PRIMARY KEY AUTOINCREMENT,
                doc_id INTEGER NOT NULL,
                media_kind TEXT,
                media_name TEXT,
                media_path TEXT,
                media_ext TEXT,
                media_size INTEGER,
                media_hash TEXT,
                source_note TEXT,
                location_json TEXT,
                extra_json TEXT,
                created_at TEXT,
                FOREIGN KEY(doc_id) REFERENCES documents(doc_id) ON DELETE CASCADE
            )
            """)

            cur.execute("""
            CREATE TABLE IF NOT EXISTS old_new_map (
                map_id INTEGER PRIMARY KEY AUTOINCREMENT,
                enabled INTEGER DEFAULT 1,
                priority INTEGER DEFAULT 100,
                group_name TEXT DEFAULT 'default',

                -- 核心旧新映射
                old_value TEXT NOT NULL,
                new_value TEXT NOT NULL,

                -- 匹配/替换方式：contains / exact / regex / fuzzy；partial / full
                match_mode TEXT DEFAULT 'contains',
                replace_mode TEXT DEFAULT 'partial',

                -- 限制范围：any / paragraph / table_cell / shape_text / content_control / bookmark / field
                scope TEXT DEFAULT 'any',
                file_match TEXT,
                table_match TEXT,
                row_match TEXT,
                col_match TEXT,
                context_required TEXT,

                -- 可选：业务来源、批次、备注
                source_key TEXT,
                remark TEXT,
                created_at TEXT,
                updated_at TEXT
            )
            """)

            cur.execute("""
            CREATE TABLE IF NOT EXISTS replace_rules (
                rule_id INTEGER PRIMARY KEY AUTOINCREMENT,
                enabled INTEGER DEFAULT 1,
                priority INTEGER DEFAULT 100,
                scope TEXT DEFAULT 'any',
                file_match TEXT,
                table_match TEXT,
                row_match TEXT,
                col_match TEXT,
                match_mode TEXT DEFAULT 'contains',
                old_value TEXT,
                new_value TEXT,
                context_required TEXT,
                replace_mode TEXT DEFAULT 'partial',
                remark TEXT,
                created_at TEXT,
                updated_at TEXT
            )
            """)

            cur.execute("""
            CREATE TABLE IF NOT EXISTS replace_plan (
                plan_id INTEGER PRIMARY KEY AUTOINCREMENT,
                doc_id INTEGER NOT NULL,
                block_id INTEGER NOT NULL,
                rule_id INTEGER,
                map_id INTEGER,
                source_type TEXT DEFAULT 'replace_rules',
                file_path TEXT,
                block_type TEXT,

                -- 内容块级别的旧值/新值：用于整块校验和整块回写
                old_text TEXT,
                new_text TEXT,

                -- 规则级别的旧值/新值：用于优先执行局部替换
                rule_old_value TEXT,
                rule_new_value TEXT,
                rule_match_mode TEXT,
                rule_replace_mode TEXT,

                -- 方便人工核查的定位字段
                position_key TEXT,
                current_text_at_write TEXT,

                match_reason TEXT,
                confidence INTEGER,
                status TEXT DEFAULT '待确认',
                output_path TEXT,
                error TEXT,
                created_at TEXT,
                updated_at TEXT,
                FOREIGN KEY(doc_id) REFERENCES documents(doc_id) ON DELETE CASCADE,
                FOREIGN KEY(block_id) REFERENCES content_blocks(block_id) ON DELETE CASCADE,
                FOREIGN KEY(rule_id) REFERENCES replace_rules(rule_id) ON DELETE SET NULL
            )
            """)

            cur.execute("""
            CREATE TABLE IF NOT EXISTS replace_log (
                log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                plan_id INTEGER,
                doc_id INTEGER,
                block_id INTEGER,
                action TEXT,
                status TEXT,
                old_text TEXT,
                new_text TEXT,
                message TEXT,
                created_at TEXT
            )
            """)


            cur.execute("""
            CREATE TABLE IF NOT EXISTS template_docs (
                template_id INTEGER PRIMARY KEY AUTOINCREMENT,
                enabled INTEGER DEFAULT 1,
                template_name TEXT,
                template_path TEXT UNIQUE NOT NULL,
                template_hash TEXT,
                template_type TEXT,
                filename_template TEXT,
                output_dir TEXT,
                doc_id INTEGER,
                status TEXT DEFAULT 'ok',
                remark TEXT,
                created_at TEXT,
                updated_at TEXT,
                FOREIGN KEY(doc_id) REFERENCES documents(doc_id) ON DELETE SET NULL
            )
            """)

            cur.execute("""
            CREATE TABLE IF NOT EXISTS template_fields (
                field_id INTEGER PRIMARY KEY AUTOINCREMENT,
                template_id INTEGER NOT NULL,
                field_key TEXT NOT NULL,
                block_id INTEGER NOT NULL,
                block_type TEXT,
                old_value TEXT,
                replace_mode TEXT DEFAULT 'partial',
                required INTEGER DEFAULT 1,
                default_value TEXT,
                remark TEXT,
                created_at TEXT,
                updated_at TEXT,
                FOREIGN KEY(template_id) REFERENCES template_docs(template_id) ON DELETE CASCADE,
                FOREIGN KEY(block_id) REFERENCES content_blocks(block_id) ON DELETE CASCADE
            )
            """)

            cur.execute("""
            CREATE TABLE IF NOT EXISTS generation_data (
                row_id INTEGER PRIMARY KEY AUTOINCREMENT,
                enabled INTEGER DEFAULT 1,
                batch_name TEXT DEFAULT 'default',
                data_id TEXT NOT NULL,
                template_id INTEGER,
                template_name TEXT,
                output_name TEXT,
                output_dir TEXT,
                field_key TEXT NOT NULL,
                field_value TEXT,
                remark TEXT,
                created_at TEXT,
                updated_at TEXT
            )
            """)

            cur.execute("""
            CREATE TABLE IF NOT EXISTS generation_plan (
                gen_id INTEGER PRIMARY KEY AUTOINCREMENT,
                batch_name TEXT,
                template_id INTEGER,
                data_id TEXT,
                output_name TEXT,
                output_path TEXT,
                template_hash_at_plan TEXT,
                status TEXT DEFAULT '待确认',
                field_count INTEGER DEFAULT 0,
                missing_fields TEXT,
                conflict_info TEXT,
                error TEXT,
                created_at TEXT,
                updated_at TEXT,
                FOREIGN KEY(template_id) REFERENCES template_docs(template_id) ON DELETE CASCADE
            )
            """)

            cur.execute("""
            CREATE TABLE IF NOT EXISTS generation_field_plan (
                item_id INTEGER PRIMARY KEY AUTOINCREMENT,
                gen_id INTEGER NOT NULL,
                template_id INTEGER,
                field_id INTEGER,
                field_key TEXT,
                block_id INTEGER,
                block_type TEXT,
                old_value TEXT,
                new_value TEXT,
                replace_mode TEXT DEFAULT 'partial',
                status TEXT DEFAULT '待替换',
                error TEXT,
                current_text_at_write TEXT,
                created_at TEXT,
                updated_at TEXT,
                FOREIGN KEY(gen_id) REFERENCES generation_plan(gen_id) ON DELETE CASCADE,
                FOREIGN KEY(template_id) REFERENCES template_docs(template_id) ON DELETE CASCADE,
                FOREIGN KEY(field_id) REFERENCES template_fields(field_id) ON DELETE SET NULL,
                FOREIGN KEY(block_id) REFERENCES content_blocks(block_id) ON DELETE SET NULL
            )
            """)

            cur.execute("""
            CREATE TABLE IF NOT EXISTS generation_log (
                log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                gen_id INTEGER,
                item_id INTEGER,
                action TEXT,
                status TEXT,
                message TEXT,
                created_at TEXT
            )
            """)

            cur.execute("""
            CREATE TABLE IF NOT EXISTS excel_template_docs (
                excel_template_id INTEGER PRIMARY KEY AUTOINCREMENT,
                enabled INTEGER DEFAULT 1,
                template_name TEXT,
                template_path TEXT UNIQUE NOT NULL,
                file_ext TEXT,
                file_hash TEXT,
                filename_template TEXT,
                output_dir TEXT,
                status TEXT DEFAULT 'ok',
                remark TEXT,
                created_at TEXT,
                updated_at TEXT
            )
            """)

            cur.execute("""
            CREATE TABLE IF NOT EXISTS excel_content_blocks (
                excel_block_id INTEGER PRIMARY KEY AUTOINCREMENT,
                excel_template_id INTEGER NOT NULL,
                sheet_index INTEGER,
                sheet_name TEXT,
                row_index INTEGER,
                col_index INTEGER,
                cell_address TEXT,
                raw_value TEXT,
                formula TEXT,
                number_format TEXT,
                is_merged INTEGER DEFAULT 0,
                merge_area TEXT,
                created_at TEXT,
                FOREIGN KEY(excel_template_id) REFERENCES excel_template_docs(excel_template_id) ON DELETE CASCADE
            )
            """)

            cur.execute("""
            CREATE TABLE IF NOT EXISTS excel_template_fields (
                excel_field_id INTEGER PRIMARY KEY AUTOINCREMENT,
                excel_template_id INTEGER NOT NULL,
                field_key TEXT NOT NULL,
                excel_block_id INTEGER,
                sheet_name TEXT,
                cell_address TEXT,
                old_value TEXT,
                write_mode TEXT DEFAULT 'cell',
                required INTEGER DEFAULT 1,
                default_value TEXT,
                remark TEXT,
                created_at TEXT,
                updated_at TEXT,
                FOREIGN KEY(excel_template_id) REFERENCES excel_template_docs(excel_template_id) ON DELETE CASCADE,
                FOREIGN KEY(excel_block_id) REFERENCES excel_content_blocks(excel_block_id) ON DELETE SET NULL
            )
            """)

            cur.execute("""
            CREATE TABLE IF NOT EXISTS excel_generation_data (
                row_id INTEGER PRIMARY KEY AUTOINCREMENT,
                enabled INTEGER DEFAULT 1,
                batch_name TEXT DEFAULT 'default',
                data_id TEXT NOT NULL,
                excel_template_id INTEGER,
                template_name TEXT,
                output_name TEXT,
                output_dir TEXT,
                field_key TEXT NOT NULL,
                field_value TEXT,
                remark TEXT,
                created_at TEXT,
                updated_at TEXT
            )
            """)

            cur.execute("""
            CREATE TABLE IF NOT EXISTS excel_generation_plan (
                excel_gen_id INTEGER PRIMARY KEY AUTOINCREMENT,
                batch_name TEXT,
                excel_template_id INTEGER,
                data_id TEXT,
                output_name TEXT,
                output_path TEXT,
                template_hash_at_plan TEXT,
                status TEXT DEFAULT '待确认',
                field_count INTEGER DEFAULT 0,
                missing_fields TEXT,
                conflict_info TEXT,
                error TEXT,
                created_at TEXT,
                updated_at TEXT,
                FOREIGN KEY(excel_template_id) REFERENCES excel_template_docs(excel_template_id) ON DELETE CASCADE
            )
            """)

            cur.execute("""
            CREATE TABLE IF NOT EXISTS excel_generation_field_plan (
                excel_item_id INTEGER PRIMARY KEY AUTOINCREMENT,
                excel_gen_id INTEGER NOT NULL,
                excel_template_id INTEGER,
                excel_field_id INTEGER,
                field_key TEXT,
                excel_block_id INTEGER,
                sheet_name TEXT,
                row_index INTEGER,
                col_index INTEGER,
                cell_address TEXT,
                old_value TEXT,
                new_value TEXT,
                write_mode TEXT DEFAULT 'cell',
                status TEXT DEFAULT '待替换',
                error TEXT,
                current_text_at_write TEXT,
                created_at TEXT,
                updated_at TEXT,
                FOREIGN KEY(excel_gen_id) REFERENCES excel_generation_plan(excel_gen_id) ON DELETE CASCADE,
                FOREIGN KEY(excel_template_id) REFERENCES excel_template_docs(excel_template_id) ON DELETE CASCADE,
                FOREIGN KEY(excel_field_id) REFERENCES excel_template_fields(excel_field_id) ON DELETE SET NULL,
                FOREIGN KEY(excel_block_id) REFERENCES excel_content_blocks(excel_block_id) ON DELETE SET NULL
            )
            """)

            cur.execute("""
            CREATE TABLE IF NOT EXISTS excel_generation_log (
                excel_log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                excel_gen_id INTEGER,
                excel_item_id INTEGER,
                action TEXT,
                status TEXT,
                message TEXT,
                created_at TEXT
            )
            """)

            # 修复历史/手动建表导致的模板字段表结构问题：
            # 如果 template_fields.field_id 不是主键，generation_field_plan 的外键会报
            # foreign key mismatch，导致“模板数据→生成计划”失败。
            self._repair_template_generation_schema(cur)

            cur.execute("CREATE INDEX IF NOT EXISTS idx_blocks_doc ON content_blocks(doc_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_blocks_norm ON content_blocks(norm_text)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_blocks_type ON content_blocks(block_type)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_plan_status ON replace_plan(status)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_plan_doc ON replace_plan(doc_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_media_doc ON media_blocks(doc_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_map_enabled ON old_new_map(enabled)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_map_group ON old_new_map(group_name)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_plan_map ON replace_plan(map_id)")

            cur.execute("CREATE INDEX IF NOT EXISTS idx_template_docs_doc ON template_docs(doc_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_template_docs_enabled ON template_docs(enabled)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_template_fields_template ON template_fields(template_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_generation_data_batch ON generation_data(batch_name)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_generation_data_data_id ON generation_data(data_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_generation_plan_status ON generation_plan(status)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_generation_plan_template ON generation_plan(template_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_generation_field_gen ON generation_field_plan(gen_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_excel_template_docs_enabled ON excel_template_docs(enabled)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_excel_content_template ON excel_content_blocks(excel_template_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_excel_template_fields_template ON excel_template_fields(excel_template_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_excel_generation_data_batch ON excel_generation_data(batch_name)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_excel_generation_plan_status ON excel_generation_plan(status)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_excel_generation_field_gen ON excel_generation_field_plan(excel_gen_id)")

            # 兼容旧版本数据库：如果 replace_plan 已存在，补充新增字段。
            self._ensure_columns(cur, "replace_plan", {
                "rule_old_value": "TEXT",
                "rule_new_value": "TEXT",
                "rule_match_mode": "TEXT",
                "rule_replace_mode": "TEXT",
                "position_key": "TEXT",
                "current_text_at_write": "TEXT",
                "map_id": "INTEGER",
                "source_type": "TEXT DEFAULT 'replace_rules'",
            })

            # 兼容旧版本数据库：如果 old_new_map 已存在但字段不完整，补充字段。
            self._ensure_columns(cur, "old_new_map", {
                "enabled": "INTEGER DEFAULT 1",
                "priority": "INTEGER DEFAULT 100",
                "group_name": "TEXT DEFAULT 'default'",
                "old_value": "TEXT",
                "new_value": "TEXT",
                "match_mode": "TEXT DEFAULT 'contains'",
                "replace_mode": "TEXT DEFAULT 'partial'",
                "scope": "TEXT DEFAULT 'any'",
                "file_match": "TEXT",
                "table_match": "TEXT",
                "row_match": "TEXT",
                "col_match": "TEXT",
                "context_required": "TEXT",
                "source_key": "TEXT",
                "remark": "TEXT",
                "created_at": "TEXT",
                "updated_at": "TEXT",
            })


            # 兼容模板批量生成模块的旧数据库补字段。
            self._ensure_columns(cur, "template_docs", {
                "enabled": "INTEGER DEFAULT 1",
                "template_name": "TEXT",
                "template_path": "TEXT",
                "template_hash": "TEXT",
                "template_type": "TEXT",
                "filename_template": "TEXT",
                "output_dir": "TEXT",
                "doc_id": "INTEGER",
                "status": "TEXT DEFAULT 'ok'",
                "remark": "TEXT",
                "created_at": "TEXT",
                "updated_at": "TEXT",
            })
            self._ensure_columns(cur, "template_fields", {
                "template_id": "INTEGER",
                "field_key": "TEXT",
                "block_id": "INTEGER",
                "block_type": "TEXT",
                "old_value": "TEXT",
                "replace_mode": "TEXT DEFAULT 'partial'",
                "required": "INTEGER DEFAULT 1",
                "default_value": "TEXT",
                "remark": "TEXT",
                "created_at": "TEXT",
                "updated_at": "TEXT",
            })
            self._ensure_columns(cur, "generation_data", {
                "enabled": "INTEGER DEFAULT 1",
                "batch_name": "TEXT DEFAULT 'default'",
                "data_id": "TEXT",
                "template_id": "INTEGER",
                "template_name": "TEXT",
                "output_name": "TEXT",
                "output_dir": "TEXT",
                "field_key": "TEXT",
                "field_value": "TEXT",
                "remark": "TEXT",
                "created_at": "TEXT",
                "updated_at": "TEXT",
            })
            self._ensure_columns(cur, "generation_plan", {
                "batch_name": "TEXT",
                "template_id": "INTEGER",
                "data_id": "TEXT",
                "output_name": "TEXT",
                "output_path": "TEXT",
                "template_hash_at_plan": "TEXT",
                "status": "TEXT DEFAULT '待确认'",
                "field_count": "INTEGER DEFAULT 0",
                "missing_fields": "TEXT",
                "conflict_info": "TEXT",
                "error": "TEXT",
                "created_at": "TEXT",
                "updated_at": "TEXT",
            })
            self._ensure_columns(cur, "generation_field_plan", {
                "gen_id": "INTEGER",
                "template_id": "INTEGER",
                "field_id": "INTEGER",
                "field_key": "TEXT",
                "block_id": "INTEGER",
                "block_type": "TEXT",
                "old_value": "TEXT",
                "new_value": "TEXT",
                "replace_mode": "TEXT DEFAULT 'partial'",
                "status": "TEXT DEFAULT '待替换'",
                "error": "TEXT",
                "current_text_at_write": "TEXT",
                "created_at": "TEXT",
                "updated_at": "TEXT",
            })
            self._ensure_columns(cur, "generation_log", {
                "gen_id": "INTEGER",
                "item_id": "INTEGER",
                "action": "TEXT",
                "status": "TEXT",
                "message": "TEXT",
                "created_at": "TEXT",
            })

            cur.execute(
                "INSERT OR REPLACE INTO meta(key, value) VALUES(?, ?)",
                ("db_version", str(DB_VERSION))
            )
            cur.execute(
                "INSERT OR REPLACE INTO meta(key, value) VALUES(?, ?)",
                ("last_init_time", now_str())
            )
            conn.commit()

    def _repair_template_generation_schema(self, cur):
        """
        修复 template_fields / generation_field_plan 的历史结构问题。

        背景：
            如果 template_fields 是通过外部工具/Excel/旧版本脚本手动创建的，
            可能出现 field_id 只是普通 TEXT 列，而不是 INTEGER PRIMARY KEY。
            此时 generation_field_plan 的外键：
                FOREIGN KEY(field_id) REFERENCES template_fields(field_id)
            会触发 SQLite:
                foreign key mismatch - "generation_field_plan" referencing "template_fields"

        处理：
            1. 检查 template_fields.field_id 是否为主键。
            2. 如果不是，备份旧表为 template_fields_bad_backup_时间戳。
            3. 重建标准 template_fields。
            4. 尽量保留旧数据并转换数字字段类型。
            5. 重建 generation_field_plan。
               该表本质是“生成计划明细”，可由 generation_data 重新生成，因此历史明细可以安全清空。
        """
        def table_exists(name):
            return cur.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                (name,)
            ).fetchone() is not None

        if not table_exists("template_fields"):
            return

        cols = cur.execute("PRAGMA table_info(template_fields)").fetchall()
        col_info = {c[1]: c for c in cols}
        field_col = col_info.get("field_id")
        template_fields_ok = bool(field_col and int(field_col[5] or 0) == 1)

        # 检查 generation_field_plan 是否引用到了错误的旧表名，例如 template_fields_bad_backup
        gfp_bad = False
        if table_exists("generation_field_plan"):
            try:
                fks = cur.execute("PRAGMA foreign_key_list(generation_field_plan)").fetchall()
                for fk in fks:
                    # fk 字段格式：id, seq, table, from, to, on_update, on_delete, match
                    if fk[3] == "field_id" and fk[2] != "template_fields":
                        gfp_bad = True
                        break
            except Exception:
                gfp_bad = True

        if template_fields_ok and not gfp_bad:
            return

        cur.execute("PRAGMA foreign_keys=OFF")

        # generation_field_plan 是生成计划明细，遇到结构问题时直接重建，后续重新点“模板数据→生成计划”即可恢复。
        cur.execute("DROP TABLE IF EXISTS generation_field_plan")

        if not template_fields_ok:
            rows = cur.execute("SELECT * FROM template_fields").fetchall()
            old_cols = [c[1] for c in cur.execute("PRAGMA table_info(template_fields)").fetchall()]

            backup_name = "template_fields_bad_backup_" + datetime.now().strftime("%Y%m%d_%H%M%S")
            cur.execute(f"ALTER TABLE template_fields RENAME TO {backup_name}")

            cur.execute("""
                CREATE TABLE template_fields (
                    field_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    template_id INTEGER NOT NULL,
                    field_key TEXT NOT NULL,
                    block_id INTEGER,
                    block_type TEXT,
                    old_value TEXT,
                    replace_mode TEXT DEFAULT 'partial',
                    required INTEGER DEFAULT 1,
                    default_value TEXT,
                    remark TEXT,
                    created_at TEXT,
                    updated_at TEXT,
                    FOREIGN KEY(template_id) REFERENCES template_docs(template_id) ON DELETE CASCADE,
                    FOREIGN KEY(block_id) REFERENCES content_blocks(block_id) ON DELETE SET NULL
                )
            """)

            def get(row, name, default=None):
                if name not in old_cols:
                    return default
                try:
                    return row[name]
                except Exception:
                    return default

            def to_int_or_none(v):
                if v is None:
                    return None
                s = str(v).strip()
                if s == "":
                    return None
                try:
                    return int(float(s))
                except Exception:
                    return None

            def to_int_default(v, default=1):
                x = to_int_or_none(v)
                return default if x is None else x

            for row in rows:
                cur.execute("""
                    INSERT INTO template_fields(
                        field_id, template_id, field_key, block_id, block_type,
                        old_value, replace_mode, required, default_value, remark,
                        created_at, updated_at
                    )
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    to_int_or_none(get(row, "field_id")),
                    to_int_or_none(get(row, "template_id")),
                    "" if get(row, "field_key") is None else str(get(row, "field_key")),
                    to_int_or_none(get(row, "block_id")),
                    get(row, "block_type"),
                    get(row, "old_value"),
                    get(row, "replace_mode") or "partial",
                    to_int_default(get(row, "required"), 1),
                    get(row, "default_value"),
                    get(row, "remark"),
                    get(row, "created_at"),
                    get(row, "updated_at"),
                ))

        # 重建 generation_field_plan，确保外键指向新的标准 template_fields。
        cur.execute("""
            CREATE TABLE IF NOT EXISTS generation_field_plan (
                item_id INTEGER PRIMARY KEY AUTOINCREMENT,
                gen_id INTEGER NOT NULL,
                template_id INTEGER,
                field_id INTEGER,
                field_key TEXT,
                block_id INTEGER,
                block_type TEXT,
                old_value TEXT,
                new_value TEXT,
                replace_mode TEXT DEFAULT 'partial',
                status TEXT DEFAULT '待替换',
                error TEXT,
                current_text_at_write TEXT,
                created_at TEXT,
                updated_at TEXT,
                FOREIGN KEY(gen_id) REFERENCES generation_plan(gen_id) ON DELETE CASCADE,
                FOREIGN KEY(template_id) REFERENCES template_docs(template_id) ON DELETE CASCADE,
                FOREIGN KEY(field_id) REFERENCES template_fields(field_id) ON DELETE SET NULL,
                FOREIGN KEY(block_id) REFERENCES content_blocks(block_id) ON DELETE SET NULL
            )
        """)

        cur.execute("CREATE INDEX IF NOT EXISTS idx_template_fields_template ON template_fields(template_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_generation_field_gen ON generation_field_plan(gen_id)")

        cur.execute("PRAGMA foreign_keys=ON")


    def upsert_document(self, file_path: Path, status="extracting", note=""):
        file_path = Path(file_path).resolve()
        stat = file_path.stat()
        file_hash = sha256_file(file_path)
        modified_time = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")

        with self.connect() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO documents(
                    file_path, file_name, file_ext, file_hash, file_size,
                    modified_time, extract_time, status, note
                )
                VALUES(?,?,?,?,?,?,?,?,?)
                ON CONFLICT(file_path) DO UPDATE SET
                    file_name=excluded.file_name,
                    file_ext=excluded.file_ext,
                    file_hash=excluded.file_hash,
                    file_size=excluded.file_size,
                    modified_time=excluded.modified_time,
                    extract_time=excluded.extract_time,
                    status=excluded.status,
                    note=excluded.note
            """, (
                str(file_path),
                file_path.name,
                file_path.suffix.lower(),
                file_hash,
                stat.st_size,
                modified_time,
                now_str(),
                status,
                note
            ))
            conn.commit()
            cur.execute("SELECT doc_id FROM documents WHERE file_path=?", (str(file_path),))
            return cur.fetchone()["doc_id"]

    def clear_document_related(self, doc_id):
        with self.connect() as conn:
            conn.execute("DELETE FROM replace_log WHERE doc_id=?", (doc_id,))
            conn.execute("DELETE FROM replace_plan WHERE doc_id=?", (doc_id,))
            conn.execute("DELETE FROM media_blocks WHERE doc_id=?", (doc_id,))
            conn.execute("DELETE FROM content_blocks WHERE doc_id=?", (doc_id,))
            conn.commit()

    def update_document(self, doc_id, **kwargs):
        if not kwargs:
            return
        keys = list(kwargs.keys())
        sql = "UPDATE documents SET " + ",".join([f"{k}=?" for k in keys]) + " WHERE doc_id=?"
        values = [kwargs[k] for k in keys] + [doc_id]
        with self.connect() as conn:
            conn.execute(sql, values)
            conn.commit()

    def insert_block(self, conn, **kwargs):
        keys = list(kwargs.keys())
        values = [kwargs[k] for k in keys]
        sql = f"""
            INSERT INTO content_blocks({",".join(keys)})
            VALUES({",".join(["?"] * len(keys))})
        """
        conn.execute(sql, values)

    def insert_media(self, conn, **kwargs):
        keys = list(kwargs.keys())
        values = [kwargs[k] for k in keys]
        sql = f"""
            INSERT INTO media_blocks({",".join(keys)})
            VALUES({",".join(["?"] * len(keys))})
        """
        conn.execute(sql, values)

    def get_row_by_id(self, table_name, id_col, id_value):
        allowed = {
            "documents": "doc_id",
            "content_blocks": "block_id",
            "media_blocks": "media_id",
            "old_new_map": "map_id",
            "replace_rules": "rule_id",
            "replace_plan": "plan_id",
            "replace_log": "log_id",
            "template_docs": "template_id",
            "template_fields": "field_id",
            "generation_data": "row_id",
            "generation_plan": "gen_id",
            "generation_field_plan": "item_id",
            "generation_log": "log_id",
        }
        if table_name not in allowed or allowed[table_name] != id_col:
            raise ValueError("不允许的表或主键")
        with self.connect() as conn:
            row = conn.execute(
                f"SELECT * FROM {table_name} WHERE {id_col}=?",
                (id_value,)
            ).fetchone()
            return dict(row) if row else None

    def update_row_by_id(self, table_name, id_col, id_value, data):
        """
        GUI 双击详情窗口保存时使用。
        只允许更新已知表，主键列不更新。
        """
        allowed = {
            "documents": "doc_id",
            "content_blocks": "block_id",
            "media_blocks": "media_id",
            "old_new_map": "map_id",
            "replace_rules": "rule_id",
            "replace_plan": "plan_id",
            "replace_log": "log_id",
            "template_docs": "template_id",
            "template_fields": "field_id",
            "generation_data": "row_id",
            "generation_plan": "gen_id",
            "generation_field_plan": "item_id",
            "generation_log": "log_id",
        }
        if table_name not in allowed or allowed[table_name] != id_col:
            raise ValueError("不允许的表或主键")

        with self.connect() as conn:
            cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}
            update_data = {
                k: v for k, v in data.items()
                if k in cols and k != id_col
            }
            if not update_data:
                return

            if "updated_at" in cols and "updated_at" not in update_data:
                update_data["updated_at"] = now_str()

            keys = list(update_data.keys())
            sql = f"UPDATE {table_name} SET " + ",".join([f"{k}=?" for k in keys]) + f" WHERE {id_col}=?"
            conn.execute(sql, [update_data[k] for k in keys] + [id_value])
            conn.commit()

    def get_table_columns(self, table_name):
        """
        获取表字段。
        优先读取 SQLite 当前真实表结构；如果旧库/空库还没创建成功，则使用 TABLE_DISPLAY_COLUMNS 兜底。
        """
        allowed = {
            "documents",
            "content_blocks",
            "media_blocks",
            "old_new_map",
            "replace_rules",
            "replace_plan",
            "replace_log",
            "template_docs",
            "template_fields",
            "generation_data",
            "generation_plan",
            "generation_field_plan",
            "generation_log",
            "excel_template_docs",
            "excel_content_blocks",
            "excel_template_fields",
            "excel_generation_data",
            "excel_generation_plan",
            "excel_generation_field_plan",
            "excel_generation_log",
        }
        if table_name not in allowed:
            raise ValueError("不允许的表名")

        try:
            with self.connect() as conn:
                rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
                cols = [r[1] for r in rows]
                if cols:
                    return cols
        except Exception:
            pass

        return default_columns_for_table(table_name)

    def query_preview(self, table_name, limit=500):
        allowed = {
            "documents",
            "content_blocks",
            "media_blocks",
            "old_new_map",
            "replace_rules",
            "replace_plan",
            "replace_log",
            "template_docs",
            "template_fields",
            "generation_data",
            "generation_plan",
            "generation_field_plan",
            "generation_log",
            "excel_template_docs",
            "excel_content_blocks",
            "excel_template_fields",
            "excel_generation_data",
            "excel_generation_plan",
            "excel_generation_field_plan",
            "excel_generation_log",
        }
        if table_name not in allowed:
            raise ValueError("不允许的表名")
        with self.connect() as conn:
            rows = conn.execute(f"SELECT * FROM {table_name} ORDER BY 1 DESC LIMIT ?", (limit,)).fetchall()
            return [dict(r) for r in rows]

    def add_rule(self, rule):
        with self.connect() as conn:
            conn.execute("""
                INSERT INTO replace_rules(
                    enabled, priority, scope, file_match, table_match, row_match, col_match,
                    match_mode, old_value, new_value, context_required, replace_mode,
                    remark, created_at, updated_at
                )
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                int(rule.get("enabled", 1)),
                int(rule.get("priority", 100)),
                rule.get("scope", "any"),
                rule.get("file_match", ""),
                rule.get("table_match", ""),
                rule.get("row_match", ""),
                rule.get("col_match", ""),
                rule.get("match_mode", "contains"),
                rule.get("old_value", ""),
                rule.get("new_value", ""),
                rule.get("context_required", ""),
                rule.get("replace_mode", "partial"),
                rule.get("remark", ""),
                now_str(),
                now_str(),
            ))
            conn.commit()

    def add_old_new_map(self, item):
        """GUI 手动新增旧新映射；也可以直接用外部 SQL 写入 old_new_map。"""
        with self.connect() as conn:
            conn.execute("""
                INSERT INTO old_new_map(
                    enabled, priority, group_name, old_value, new_value,
                    match_mode, replace_mode, scope,
                    file_match, table_match, row_match, col_match,
                    context_required, source_key, remark, created_at, updated_at
                )
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                int(item.get("enabled", 1)),
                int(item.get("priority", 100)),
                item.get("group_name", "default"),
                item.get("old_value", ""),
                item.get("new_value", ""),
                item.get("match_mode", "contains"),
                item.get("replace_mode", "partial"),
                item.get("scope", "any"),
                item.get("file_match", ""),
                item.get("table_match", ""),
                item.get("row_match", ""),
                item.get("col_match", ""),
                item.get("context_required", ""),
                item.get("source_key", ""),
                item.get("remark", ""),
                now_str(),
                now_str(),
            ))
            conn.commit()


    def register_templates_from_folder(self, folder, recursive=True, template_type="", filename_template=""):
        """
        把目录下 Word 文件登记到 template_docs。
        注意：登记模板不等于抽取内容。建议先执行“扫描Word并入库”，再登记模板，template_docs.doc_id 会自动关联 documents。
        """
        folder = Path(folder)
        files = [p for p in (folder.rglob("*") if recursive else folder.iterdir()) if p.is_file() and is_word_file(p)]
        count = 0
        with self.connect() as conn:
            for path in files:
                full = str(path.resolve())
                file_hash = sha256_file(path)
                doc = conn.execute("SELECT doc_id FROM documents WHERE file_path=?", (full,)).fetchone()
                doc_id = doc["doc_id"] if doc else None
                conn.execute("""
                    INSERT INTO template_docs(
                        enabled, template_name, template_path, template_hash, template_type,
                        filename_template, output_dir, doc_id, status, remark, created_at, updated_at
                    )
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(template_path) DO UPDATE SET
                        template_name=excluded.template_name,
                        template_hash=excluded.template_hash,
                        template_type=COALESCE(NULLIF(excluded.template_type,''), template_docs.template_type),
                        filename_template=COALESCE(NULLIF(excluded.filename_template,''), template_docs.filename_template),
                        doc_id=excluded.doc_id,
                        status='ok',
                        updated_at=excluded.updated_at
                """, (
                    1, path.stem, full, file_hash, template_type,
                    filename_template, "", doc_id, "ok", "目录登记", now_str(), now_str()
                ))
                count += 1
            conn.commit()
        return count

    def add_template_field(self, item):
        """手动新增模板字段；也可以直接 SQL 写 template_fields。"""
        with self.connect() as conn:
            block = conn.execute("SELECT block_type, raw_text FROM content_blocks WHERE block_id=?", (item.get("block_id"),)).fetchone()
            block_type = item.get("block_type") or (block["block_type"] if block else "")
            old_value = item.get("old_value")
            if old_value in (None, "") and block:
                old_value = block["raw_text"]
            conn.execute("""
                INSERT INTO template_fields(
                    template_id, field_key, block_id, block_type, old_value, replace_mode,
                    required, default_value, remark, created_at, updated_at
                )
                VALUES(?,?,?,?,?,?,?,?,?,?,?)
            """, (
                item.get("template_id"), item.get("field_key"), item.get("block_id"), block_type,
                old_value or "", item.get("replace_mode", "partial"), int(item.get("required", 1)),
                item.get("default_value", ""), item.get("remark", ""), now_str(), now_str()
            ))
            conn.commit()

    def delete_selected_ids(self, table, id_col, ids):
        allowed = {
            "old_new_map": "map_id",
            "replace_rules": "rule_id",
            "replace_plan": "plan_id",
            "template_docs": "template_id",
            "template_fields": "field_id",
            "generation_data": "row_id",
            "generation_plan": "gen_id",
            "generation_field_plan": "item_id",
            "excel_generation_plan": "excel_gen_id",
        }
        if table not in allowed or allowed[table] != id_col:
            raise ValueError("不允许删除该表")
        if not ids:
            return
        marks = ",".join(["?"] * len(ids))
        with self.connect() as conn:
            conn.execute(f"DELETE FROM {table} WHERE {id_col} IN ({marks})", ids)
            conn.commit()

    def update_plan_status(self, ids, status):
        if not ids:
            return
        marks = ",".join(["?"] * len(ids))
        with self.connect() as conn:
            conn.execute(
                f"UPDATE replace_plan SET status=?, updated_at=? WHERE plan_id IN ({marks})",
                [status, now_str()] + list(ids)
            )
            conn.commit()


# -----------------------------
# Word 抽取器
# -----------------------------

class WordExtractor:
    def __init__(self, db: DBManager, log_func=print):
        self.db = db
        self.log = log_func

    def _create_word(self):
        try:
            import pythoncom
            import win32com.client
        except Exception as e:
            raise RuntimeError("缺少 pywin32，请先执行：pip install pywin32") from e

        pythoncom.CoInitialize()
        word = win32com.client.DispatchEx("Word.Application")
        word.Visible = False
        word.DisplayAlerts = Wd.wdAlertsNone
        return word

    def _close_word(self, word):
        try:
            word.Quit()
        except Exception:
            pass
        try:
            import pythoncom
            pythoncom.CoUninitialize()
        except Exception:
            pass

    def extract_folder(self, folder, recursive=True):
        folder = Path(folder)
        if not folder.exists():
            raise FileNotFoundError(folder)

        if recursive:
            files = [p for p in folder.rglob("*") if p.is_file() and is_word_file(p)]
        else:
            files = [p for p in folder.iterdir() if p.is_file() and is_word_file(p)]

        self.log(f"找到 Word 文件：{len(files)} 个")
        if not files:
            return

        word = self._create_word()
        try:
            for i, path in enumerate(files, 1):
                self.log(f"[{i}/{len(files)}] 抽取：{path}")
                try:
                    self.extract_one(word, path)
                    self.log(f"完成：{path.name}")
                except Exception as e:
                    self.log(f"失败：{path.name} -> {short_error(e)}")
                    try:
                        doc_id = self.db.upsert_document(path, status="error", note=short_error(e))
                        self.db.update_document(doc_id, status="error", note=traceback.format_exc()[:3000])
                    except Exception:
                        pass
        finally:
            self._close_word(word)

    def extract_one(self, word, file_path):
        file_path = Path(file_path).resolve()
        doc_id = self.db.upsert_document(file_path, status="extracting")
        self.db.clear_document_related(doc_id)

        doc = None
        try:
            doc = word.Documents.Open(
                str(file_path),
                ReadOnly=True,
                AddToRecentFiles=False,
                ConfirmConversions=False,
                Visible=False
            )

            page_count = safe_call(lambda: doc.ComputeStatistics(Wd.wdStatisticPages), None)

            with self.db.connect() as conn:
                self._extract_stories(conn, doc, doc_id)
                self._extract_document_shapes(conn, doc, doc_id)
                self._extract_inline_shapes(conn, doc, doc_id)
                self._extract_content_controls(conn, doc, doc_id)
                self._extract_bookmarks(conn, doc, doc_id)
                self._extract_fields(conn, doc, doc_id)
                self._extract_media_hashes(conn, word, doc, doc_id, file_path)
                conn.commit()

            self.db.update_document(doc_id, status="ok", note="", page_count=page_count, extract_time=now_str())

        finally:
            if doc is not None:
                try:
                    doc.Close(SaveChanges=Wd.wdDoNotSaveChanges)
                except Exception:
                    pass

    def _story_ranges(self, doc):
        result = []
        seq = 0
        try:
            story = doc.StoryRanges
            for sr in story:
                cur = sr
                while cur is not None:
                    seq += 1
                    story_type = safe_get(cur, "StoryType", None)
                    result.append((seq, cur, story_type, STORY_TYPE_NAMES.get(story_type, f"StoryType_{story_type}")))
                    cur = safe_get(cur, "NextStoryRange", None)
        except Exception:
            # 兜底正文
            try:
                seq += 1
                result.append((seq, doc.Content, Wd.wdMainTextStory, "正文"))
            except Exception:
                pass
        return result

    def _extract_stories(self, conn, doc, doc_id):
        for story_seq, story_range, story_type, story_name in self._story_ranges(doc):
            self._extract_paragraphs(conn, doc_id, story_seq, story_range, story_type, story_name)
            self._extract_tables(conn, doc_id, story_seq, story_range, story_type, story_name)

    def _extract_paragraphs(self, conn, doc_id, story_seq, story_range, story_type, story_name):
        paragraphs = safe_get(story_range, "Paragraphs", None)
        if paragraphs is None:
            return

        total = safe_call(lambda: paragraphs.Count, 0) or 0

        prev_text = ""
        for idx in range(1, total + 1):
            try:
                p = paragraphs(idx)
                rng = p.Range

                # 表格内段落由 table_cell 单独管理，避免重复。
                in_table = safe_call(lambda: rng.Information(Wd.wdWithInTable), False)
                if in_table:
                    continue

                raw = clean_word_text(rng.Text)
                if not raw:
                    continue

                page_no = safe_call(lambda: rng.Information(Wd.wdActiveEndPageNumber), None)
                style_name = safe_call(lambda: rng.Style.NameLocal, "")

                # 后文为了简单不提前访问 idx+1，避免 COM 性能损耗。
                loc = {
                    "story_seq": story_seq,
                    "story_type": story_type,
                    "story_name": story_name,
                    "paragraph_index": idx,
                    "range_start": safe_get(rng, "Start", None),
                    "range_end": safe_get(rng, "End", None),
                }

                self.db.insert_block(
                    conn,
                    doc_id=doc_id,
                    block_type="paragraph",
                    story_seq=story_seq,
                    story_type=story_type,
                    story_name=story_name,
                    page_no=page_no,
                    paragraph_index=idx,
                    table_index=None,
                    row_index=None,
                    col_index=None,
                    cell_index=None,
                    shape_scope=None,
                    shape_index=None,
                    shape_name=None,
                    inline_shape_index=None,
                    content_control_index=None,
                    bookmark_name=None,
                    field_index=None,
                    range_start=safe_get(rng, "Start", None),
                    range_end=safe_get(rng, "End", None),
                    raw_text=raw,
                    norm_text=normalize_text(raw),
                    text_hash=sha256_bytes(normalize_text(raw).encode("utf-8")),
                    context_before=prev_text,
                    context_after="",
                    location_json=make_json(loc),
                    extra_json=make_json({"style": style_name}),
                    created_at=now_str()
                )
                prev_text = raw
            except Exception:
                continue

    def _extract_tables(self, conn, doc_id, story_seq, story_range, story_type, story_name):
        tables = safe_get(story_range, "Tables", None)
        if tables is None:
            return

        table_count = safe_call(lambda: tables.Count, 0) or 0

        for table_index in range(1, table_count + 1):
            try:
                tbl = tables(table_index)
                cells = safe_get(tbl.Range, "Cells", None)
                cell_count = safe_call(lambda: cells.Count, 0) if cells is not None else 0
                if not cell_count:
                    continue

                for cell_index in range(1, cell_count + 1):
                    try:
                        cell = cells(cell_index)
                        rng = cell.Range
                        raw = clean_word_text(rng.Text)
                        if not raw:
                            continue

                        row_index = safe_get(cell, "RowIndex", None)
                        col_index = safe_get(cell, "ColumnIndex", None)
                        page_no = safe_call(lambda: rng.Information(Wd.wdActiveEndPageNumber), None)

                        loc = {
                            "story_seq": story_seq,
                            "story_type": story_type,
                            "story_name": story_name,
                            "table_index": table_index,
                            "cell_index": cell_index,
                            "row_index": row_index,
                            "col_index": col_index,
                            "range_start": safe_get(rng, "Start", None),
                            "range_end": safe_get(rng, "End", None),
                        }

                        self.db.insert_block(
                            conn,
                            doc_id=doc_id,
                            block_type="table_cell",
                            story_seq=story_seq,
                            story_type=story_type,
                            story_name=story_name,
                            page_no=page_no,
                            paragraph_index=None,
                            table_index=table_index,
                            row_index=row_index,
                            col_index=col_index,
                            cell_index=cell_index,
                            shape_scope=None,
                            shape_index=None,
                            shape_name=None,
                            inline_shape_index=None,
                            content_control_index=None,
                            bookmark_name=None,
                            field_index=None,
                            range_start=safe_get(rng, "Start", None),
                            range_end=safe_get(rng, "End", None),
                            raw_text=raw,
                            norm_text=normalize_text(raw),
                            text_hash=sha256_bytes(normalize_text(raw).encode("utf-8")),
                            context_before="",
                            context_after="",
                            location_json=make_json(loc),
                            extra_json=make_json({
                                "table_rows": safe_call(lambda: tbl.Rows.Count, None),
                                "table_cols": safe_call(lambda: tbl.Columns.Count, None),
                            }),
                            created_at=now_str()
                        )
                    except Exception:
                        continue
            except Exception:
                continue

    def _extract_document_shapes(self, conn, doc, doc_id):
        """
        抽取形状、文本框、艺术字等对象。
        注意：不同 Word 版本/对象类型暴露接口差异很大，因此尽量安全读取。
        """
        # 文档级 Shapes
        self._extract_shapes_from_collection(conn, doc_id, safe_get(doc, "Shapes", None), "document")

        # 各节的页眉页脚 Shapes
        sections = safe_get(doc, "Sections", None)
        sec_count = safe_call(lambda: sections.Count, 0) if sections is not None else 0
        for sec_i in range(1, sec_count + 1):
            try:
                sec = sections(sec_i)

                headers = safe_get(sec, "Headers", None)
                h_count = safe_call(lambda: headers.Count, 0) if headers is not None else 0
                for h_i in range(1, h_count + 1):
                    try:
                        header = headers(h_i)
                        self._extract_shapes_from_collection(
                            conn, doc_id, safe_get(header, "Shapes", None),
                            f"section_{sec_i}_header_{h_i}"
                        )
                    except Exception:
                        pass

                footers = safe_get(sec, "Footers", None)
                f_count = safe_call(lambda: footers.Count, 0) if footers is not None else 0
                for f_i in range(1, f_count + 1):
                    try:
                        footer = footers(f_i)
                        self._extract_shapes_from_collection(
                            conn, doc_id, safe_get(footer, "Shapes", None),
                            f"section_{sec_i}_footer_{f_i}"
                        )
                    except Exception:
                        pass
            except Exception:
                continue

    def _extract_shapes_from_collection(self, conn, doc_id, shapes, shape_scope):
        if shapes is None:
            return
        count = safe_call(lambda: shapes.Count, 0) or 0

        for i in range(1, count + 1):
            try:
                shp = shapes(i)
                name = safe_str(safe_get(shp, "Name", ""))
                alt = safe_str(safe_get(shp, "AlternativeText", ""))
                title = safe_str(safe_get(shp, "Title", ""))
                shape_type = safe_get(shp, "Type", None)
                left = safe_get(shp, "Left", None)
                top = safe_get(shp, "Top", None)
                width = safe_get(shp, "Width", None)
                height = safe_get(shp, "Height", None)

                text1 = safe_com_text(shp, ["TextFrame", "TextRange", "Text"])
                text2 = safe_com_text(shp, ["TextFrame2", "TextRange", "Text"])
                raw = text1 or text2 or ""

                loc = {
                    "shape_scope": shape_scope,
                    "shape_index": i,
                    "shape_name": name,
                    "shape_type": shape_type,
                    "left": safe_str(left),
                    "top": safe_str(top),
                    "width": safe_str(width),
                    "height": safe_str(height),
                }

                # 形状元数据：即使没有文字，也存到 media_blocks 作为对象索引。
                self.db.insert_media(
                    conn,
                    doc_id=doc_id,
                    media_kind="shape_object",
                    media_name=name,
                    media_path="",
                    media_ext="",
                    media_size=None,
                    media_hash="",
                    source_note=shape_scope,
                    location_json=make_json(loc),
                    extra_json=make_json({
                        "title": title,
                        "alternative_text": alt,
                        "shape_type": shape_type,
                    }),
                    created_at=now_str()
                )

                if raw:
                    self.db.insert_block(
                        conn,
                        doc_id=doc_id,
                        block_type="shape_text",
                        story_seq=None,
                        story_type=None,
                        story_name="形状/艺术字/文本框",
                        page_no=None,
                        paragraph_index=None,
                        table_index=None,
                        row_index=None,
                        col_index=None,
                        cell_index=None,
                        shape_scope=shape_scope,
                        shape_index=i,
                        shape_name=name,
                        inline_shape_index=None,
                        content_control_index=None,
                        bookmark_name=None,
                        field_index=None,
                        range_start=None,
                        range_end=None,
                        raw_text=raw,
                        norm_text=normalize_text(raw),
                        text_hash=sha256_bytes(normalize_text(raw).encode("utf-8")),
                        context_before="",
                        context_after="",
                        location_json=make_json(loc),
                        extra_json=make_json({
                            "title": title,
                            "alternative_text": alt,
                            "shape_type": shape_type,
                        }),
                        created_at=now_str()
                    )
            except Exception:
                continue

    def _extract_inline_shapes(self, conn, doc, doc_id):
        inline_shapes = safe_get(doc, "InlineShapes", None)
        count = safe_call(lambda: inline_shapes.Count, 0) if inline_shapes is not None else 0

        for i in range(1, count + 1):
            try:
                ish = inline_shapes(i)
                rng = safe_get(ish, "Range", None)
                page_no = safe_call(lambda: rng.Information(Wd.wdActiveEndPageNumber), None) if rng else None

                loc = {
                    "inline_shape_index": i,
                    "range_start": safe_get(rng, "Start", None) if rng else None,
                    "range_end": safe_get(rng, "End", None) if rng else None,
                    "page_no": page_no,
                    "type": safe_get(ish, "Type", None),
                    "width": safe_str(safe_get(ish, "Width", "")),
                    "height": safe_str(safe_get(ish, "Height", "")),
                }

                self.db.insert_media(
                    conn,
                    doc_id=doc_id,
                    media_kind="inline_shape",
                    media_name=f"InlineShape_{i}",
                    media_path="",
                    media_ext="",
                    media_size=None,
                    media_hash="",
                    source_note="InlineShapes",
                    location_json=make_json(loc),
                    extra_json=make_json({}),
                    created_at=now_str()
                )
            except Exception:
                continue

    def _extract_content_controls(self, conn, doc, doc_id):
        ccs = safe_get(doc, "ContentControls", None)
        count = safe_call(lambda: ccs.Count, 0) if ccs is not None else 0

        for i in range(1, count + 1):
            try:
                cc = ccs(i)
                rng = cc.Range
                raw = clean_word_text(rng.Text)
                if not raw:
                    continue

                loc = {
                    "content_control_index": i,
                    "title": safe_get(cc, "Title", ""),
                    "tag": safe_get(cc, "Tag", ""),
                    "type": safe_get(cc, "Type", None),
                    "range_start": safe_get(rng, "Start", None),
                    "range_end": safe_get(rng, "End", None),
                }

                self.db.insert_block(
                    conn,
                    doc_id=doc_id,
                    block_type="content_control",
                    story_seq=None,
                    story_type=None,
                    story_name="内容控件",
                    page_no=safe_call(lambda: rng.Information(Wd.wdActiveEndPageNumber), None),
                    paragraph_index=None,
                    table_index=None,
                    row_index=None,
                    col_index=None,
                    cell_index=None,
                    shape_scope=None,
                    shape_index=None,
                    shape_name=None,
                    inline_shape_index=None,
                    content_control_index=i,
                    bookmark_name=None,
                    field_index=None,
                    range_start=safe_get(rng, "Start", None),
                    range_end=safe_get(rng, "End", None),
                    raw_text=raw,
                    norm_text=normalize_text(raw),
                    text_hash=sha256_bytes(normalize_text(raw).encode("utf-8")),
                    context_before="",
                    context_after="",
                    location_json=make_json(loc),
                    extra_json=make_json({}),
                    created_at=now_str()
                )
            except Exception:
                continue

    def _extract_bookmarks(self, conn, doc, doc_id):
        bms = safe_get(doc, "Bookmarks", None)
        count = safe_call(lambda: bms.Count, 0) if bms is not None else 0

        for i in range(1, count + 1):
            try:
                bm = bms(i)
                rng = bm.Range
                raw = clean_word_text(rng.Text)
                if not raw:
                    continue

                name = safe_str(bm.Name)

                loc = {
                    "bookmark_index": i,
                    "bookmark_name": name,
                    "range_start": safe_get(rng, "Start", None),
                    "range_end": safe_get(rng, "End", None),
                }

                self.db.insert_block(
                    conn,
                    doc_id=doc_id,
                    block_type="bookmark",
                    story_seq=None,
                    story_type=None,
                    story_name="书签",
                    page_no=safe_call(lambda: rng.Information(Wd.wdActiveEndPageNumber), None),
                    paragraph_index=None,
                    table_index=None,
                    row_index=None,
                    col_index=None,
                    cell_index=None,
                    shape_scope=None,
                    shape_index=None,
                    shape_name=None,
                    inline_shape_index=None,
                    content_control_index=None,
                    bookmark_name=name,
                    field_index=None,
                    range_start=safe_get(rng, "Start", None),
                    range_end=safe_get(rng, "End", None),
                    raw_text=raw,
                    norm_text=normalize_text(raw),
                    text_hash=sha256_bytes(normalize_text(raw).encode("utf-8")),
                    context_before="",
                    context_after="",
                    location_json=make_json(loc),
                    extra_json=make_json({}),
                    created_at=now_str()
                )
            except Exception:
                continue

    def _extract_fields(self, conn, doc, doc_id):
        fields = safe_get(doc, "Fields", None)
        count = safe_call(lambda: fields.Count, 0) if fields is not None else 0

        for i in range(1, count + 1):
            try:
                fld = fields(i)
                code_text = clean_word_text(safe_get(fld.Code, "Text", ""))
                result_text = clean_word_text(safe_get(fld.Result, "Text", ""))
                raw = result_text or code_text
                if not raw:
                    continue

                rng = fld.Result if result_text else fld.Code
                loc = {
                    "field_index": i,
                    "field_type": safe_get(fld, "Type", None),
                    "range_start": safe_get(rng, "Start", None),
                    "range_end": safe_get(rng, "End", None),
                }

                self.db.insert_block(
                    conn,
                    doc_id=doc_id,
                    block_type="field",
                    story_seq=None,
                    story_type=None,
                    story_name="域",
                    page_no=safe_call(lambda: rng.Information(Wd.wdActiveEndPageNumber), None),
                    paragraph_index=None,
                    table_index=None,
                    row_index=None,
                    col_index=None,
                    cell_index=None,
                    shape_scope=None,
                    shape_index=None,
                    shape_name=None,
                    inline_shape_index=None,
                    content_control_index=None,
                    bookmark_name=None,
                    field_index=i,
                    range_start=safe_get(rng, "Start", None),
                    range_end=safe_get(rng, "End", None),
                    raw_text=raw,
                    norm_text=normalize_text(raw),
                    text_hash=sha256_bytes(normalize_text(raw).encode("utf-8")),
                    context_before="",
                    context_after="",
                    location_json=make_json(loc),
                    extra_json=make_json({"code_text": code_text, "result_text": result_text}),
                    created_at=now_str()
                )
            except Exception:
                continue

    def _extract_media_hashes(self, conn, word, doc, doc_id, file_path: Path):
        """
        对 docx/docm：直接解压 word/media/*
        对 doc：另存临时 docx 后解压 word/media/*
        """
        temp_dir = None
        zip_path = None

        try:
            suffix = file_path.suffix.lower()

            if suffix in [".docx", ".docm"]:
                zip_path = file_path
            else:
                temp_dir = Path(tempfile.mkdtemp(prefix="word_sqlite_media_"))
                zip_path = temp_dir / (file_path.stem + "_tmp.docx")
                doc.SaveAs2(str(zip_path), FileFormat=Wd.wdFormatXMLDocument)

            if not zip_path or not zip_path.exists():
                return

            if not zipfile.is_zipfile(zip_path):
                return

            with zipfile.ZipFile(zip_path, "r") as zf:
                for name in zf.namelist():
                    if not name.startswith("word/media/"):
                        continue
                    data = zf.read(name)
                    media_name = Path(name).name
                    ext = Path(name).suffix.lower()

                    self.db.insert_media(
                        conn,
                        doc_id=doc_id,
                        media_kind="docx_media",
                        media_name=media_name,
                        media_path=name,
                        media_ext=ext,
                        media_size=len(data),
                        media_hash=sha256_bytes(data),
                        source_note="docx_zip_media",
                        location_json=make_json({}),
                        extra_json=make_json({}),
                        created_at=now_str()
                    )
        except Exception as e:
            self.db.insert_media(
                conn,
                doc_id=doc_id,
                media_kind="media_extract_error",
                media_name="",
                media_path="",
                media_ext="",
                media_size=None,
                media_hash="",
                source_note=short_error(e),
                location_json=make_json({}),
                extra_json=make_json({"traceback": traceback.format_exc()[:3000]}),
                created_at=now_str()
            )
        finally:
            if temp_dir and temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)


# -----------------------------
# 替换计划生成
# -----------------------------

class ReplacePlanner:
    def __init__(self, db: DBManager, log_func=print):
        self.db = db
        self.log = log_func

    def generate(self, clear_old_pending=True):
        with self.db.connect() as conn:
            if clear_old_pending:
                conn.execute("DELETE FROM replace_plan WHERE status IN ('待确认','已确认','冲突','失败')")
                conn.commit()

            rules = conn.execute("""
                SELECT * FROM replace_rules
                WHERE enabled=1
                ORDER BY priority ASC, rule_id ASC
            """).fetchall()

            if not rules:
                self.log("没有启用的替换规则。")
                return 0

            blocks = conn.execute("""
                SELECT b.*, d.file_name, d.file_path
                FROM content_blocks b
                JOIN documents d ON b.doc_id=d.doc_id
                WHERE COALESCE(b.raw_text, '') <> ''
            """).fetchall()

            count = 0
            for rule in rules:
                for block in blocks:
                    ok, new_text, reason, confidence = self._match_rule(rule, block)
                    if not ok:
                        continue

                    if new_text == block["raw_text"]:
                        continue

                    conn.execute("""
                        INSERT INTO replace_plan(
                            doc_id, block_id, rule_id, map_id, source_type, file_path, block_type,
                            old_text, new_text,
                            rule_old_value, rule_new_value, rule_match_mode, rule_replace_mode,
                            position_key,
                            match_reason, confidence,
                            status, created_at, updated_at
                        )
                        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """, (
                        block["doc_id"],
                        block["block_id"],
                        rule["rule_id"],
                        None,
                        "replace_rules",
                        block["file_path"],
                        block["block_type"],
                        block["raw_text"],
                        new_text,
                        rule["old_value"],
                        rule["new_value"],
                        rule["match_mode"],
                        rule["replace_mode"],
                        self._make_position_key(block),
                        reason,
                        confidence,
                        "待确认",
                        now_str(),
                        now_str()
                    ))
                    count += 1

            conn.commit()
            self.log(f"生成替换计划：{count} 条")
            return count

    def _make_position_key(self, block):
        bt = block["block_type"] or ""
        if bt == "table_cell":
            return f"table[{block['table_index']}].cell[{block['row_index']}][{block['col_index']}].cell_index[{block['cell_index']}]"
        if bt == "paragraph":
            return f"story[{block['story_seq']}].paragraph[{block['paragraph_index']}]"
        if bt == "shape_text":
            return f"shape_scope[{block['shape_scope']}].shape[{block['shape_index']}].name[{block['shape_name']}]"
        if bt == "content_control":
            return f"content_control[{block['content_control_index']}]"
        return f"{bt}.block_id[{block['block_id']}]"

    def _match_rule(self, rule, block):
        scope = (rule["scope"] or "any").strip()
        block_type = block["block_type"] or ""

        if scope != "any" and scope != block_type:
            return False, "", "", 0

        file_match = (rule["file_match"] or "").strip()
        if file_match and file_match not in (block["file_name"] or "") and file_match not in (block["file_path"] or ""):
            return False, "", "", 0

        # 表格行列限制
        if (rule["table_match"] or "").strip():
            if str(block["table_index"] or "") != (rule["table_match"] or "").strip():
                return False, "", "", 0

        if (rule["row_match"] or "").strip():
            if str(block["row_index"] or "") != (rule["row_match"] or "").strip():
                return False, "", "", 0

        if (rule["col_match"] or "").strip():
            if str(block["col_index"] or "") != (rule["col_match"] or "").strip():
                return False, "", "", 0

        old_value = rule["old_value"] or ""
        new_value = rule["new_value"] or ""
        context_required = (rule["context_required"] or "").strip()
        match_mode = (rule["match_mode"] or "contains").strip().lower()
        replace_mode = (rule["replace_mode"] or "partial").strip().lower()

        raw = block["raw_text"] or ""
        norm = block["norm_text"] or normalize_text(raw)
        norm_old = normalize_text(old_value)

        if not old_value:
            return False, "", "", 0

        combined_context = "\n".join([
            block["raw_text"] or "",
            block["context_before"] or "",
            block["context_after"] or "",
            block["story_name"] or "",
            block["location_json"] or "",
            block["extra_json"] or "",
        ])
        if context_required and context_required not in combined_context:
            return False, "", "", 0

        if match_mode == "exact":
            if norm != norm_old:
                return False, "", "", 0
            if replace_mode == "full":
                return True, new_value, "exact + full", 100
            return True, raw.replace(old_value, new_value) if old_value in raw else new_value, "exact", 100

        if match_mode == "contains":
            if old_value not in raw and norm_old not in norm:
                return False, "", "", 0
            if replace_mode == "full":
                return True, new_value, "contains + full", 90
            if old_value in raw:
                return True, raw.replace(old_value, new_value), "contains raw", 90
            # 规范化命中但原文没有完全一样的旧值，保守处理为整块替换建议
            return True, new_value if replace_mode == "full" else raw, "contains norm only; no direct raw replace", 60

        if match_mode == "regex":
            try:
                if not re.search(old_value, raw):
                    return False, "", "", 0
                if replace_mode == "full":
                    return True, new_value, "regex + full", 85
                return True, re.sub(old_value, new_value, raw), "regex", 85
            except re.error:
                return False, "", "", 0

        if match_mode == "fuzzy":
            # 简易模糊：规范化后包含任一方向
            if norm_old in norm or norm in norm_old:
                if replace_mode == "full":
                    return True, new_value, "fuzzy + full", 70
                return True, raw.replace(old_value, new_value) if old_value in raw else raw, "fuzzy", 70
            return False, "", "", 0

        return False, "", "", 0



# -----------------------------
# 旧新映射计划生成
# -----------------------------

class OldNewMapPlanner:
    """
    从 old_new_map 表直接生成 replace_plan。

    设计目的：
        你可以用外部 SQL / Excel 导入工具 / 其他脚本，把旧值、新值写入 old_new_map；
        本类负责把“想改什么”转换成“具体改哪个文件哪个内容块”。
    """
    def __init__(self, db: DBManager, log_func=print):
        self.db = db
        self.log = log_func
        self.rule_matcher = ReplacePlanner(db, log_func)

    def generate(self, clear_old_pending=True, group_name=""):
        with self.db.connect() as conn:
            if clear_old_pending:
                # 只清理由 old_new_map 生成的未最终完成计划，不清理手工规则 replace_rules 生成的计划。
                conn.execute("""
                    DELETE FROM replace_plan
                    WHERE COALESCE(source_type, '')='old_new_map'
                      AND status IN ('待确认','已确认','冲突','失败')
                """)
                conn.commit()

            if group_name:
                maps = conn.execute("""
                    SELECT * FROM old_new_map
                    WHERE enabled=1 AND COALESCE(group_name, 'default')=?
                    ORDER BY priority ASC, map_id ASC
                """, (group_name,)).fetchall()
            else:
                maps = conn.execute("""
                    SELECT * FROM old_new_map
                    WHERE enabled=1
                    ORDER BY priority ASC, map_id ASC
                """).fetchall()

            if not maps:
                self.log("old_new_map 中没有启用的旧新映射。")
                return 0

            blocks = conn.execute("""
                SELECT b.*, d.file_name, d.file_path
                FROM content_blocks b
                JOIN documents d ON b.doc_id=d.doc_id
                WHERE COALESCE(b.raw_text, '') <> ''
            """).fetchall()

            count = 0
            skipped_same = 0
            for item in maps:
                for block in blocks:
                    ok, new_text, reason, confidence = self.rule_matcher._match_rule(item, block)
                    if not ok:
                        continue
                    if new_text == block["raw_text"]:
                        skipped_same += 1
                        continue

                    conn.execute("""
                        INSERT INTO replace_plan(
                            doc_id, block_id, rule_id, map_id, source_type, file_path, block_type,
                            old_text, new_text,
                            rule_old_value, rule_new_value, rule_match_mode, rule_replace_mode,
                            position_key,
                            match_reason, confidence,
                            status, created_at, updated_at
                        )
                        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """, (
                        block["doc_id"],
                        block["block_id"],
                        None,
                        item["map_id"],
                        "old_new_map",
                        block["file_path"],
                        block["block_type"],
                        block["raw_text"],
                        new_text,
                        item["old_value"],
                        item["new_value"],
                        item["match_mode"],
                        item["replace_mode"],
                        self.rule_matcher._make_position_key(block),
                        f"old_new_map[{item['map_id']}] {reason}",
                        confidence,
                        "待确认",
                        now_str(),
                        now_str()
                    ))
                    count += 1

            conn.commit()
            self.log(f"从 old_new_map 生成替换计划：{count} 条；跳过无变化命中：{skipped_same} 条。")
            return count


# -----------------------------
# Word 回写器
# -----------------------------

class WordRewriter:
    """
    回写器 v2：
    - 参考上传脚本中的 write_word_cell_stable 思路，增加表格单元格重试写入。
    - 优先使用 replace_plan 中保存的“规则旧值/规则新值”做局部替换。
    - 局部替换失败后，才使用“内容块旧值/内容块新值”做整块回写。
    - 不直接覆盖原文件，只改输出目录中的副本。
    """
    def __init__(self, db: DBManager, log_func=print):
        self.db = db
        self.log = log_func

    def _create_word(self):
        try:
            import pythoncom
            import win32com.client
        except Exception as e:
            raise RuntimeError("缺少 pywin32，请先执行：pip install pywin32") from e

        pythoncom.CoInitialize()
        word = win32com.client.DispatchEx("Word.Application")
        word.Visible = False
        word.DisplayAlerts = Wd.wdAlertsNone
        return word

    def _close_word(self, word):
        try:
            word.Quit()
        except Exception:
            pass
        try:
            import pythoncom
            pythoncom.CoUninitialize()
        except Exception:
            pass

    def rewrite_confirmed_to_copies(self, output_dir):
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        with self.db.connect() as conn:
            plans = conn.execute("""
                SELECT p.*, b.location_json, b.extra_json, b.story_seq, b.paragraph_index,
                       b.table_index, b.row_index, b.col_index, b.cell_index,
                       b.shape_scope, b.shape_index, b.shape_name, b.content_control_index,
                       b.block_type, d.file_path AS src_file_path, d.file_name
                FROM replace_plan p
                JOIN content_blocks b ON p.block_id=b.block_id
                JOIN documents d ON p.doc_id=d.doc_id
                WHERE p.status='已确认'
                ORDER BY p.doc_id, p.plan_id
            """).fetchall()

        if not plans:
            self.log("没有状态为“已确认”的替换计划。")
            return 0

        by_doc = {}
        for p in plans:
            by_doc.setdefault(p["doc_id"], []).append(p)

        word = self._create_word()
        total_done = 0

        try:
            for doc_id, doc_plans in by_doc.items():
                src = Path(doc_plans[0]["src_file_path"])
                if not src.exists():
                    self._mark_doc_plans_failed(doc_plans, f"源文件不存在：{src}")
                    continue

                out_path = self._make_output_path(output_dir, src)
                shutil.copy2(src, out_path)
                self.log(f"回写副本：{out_path}")

                doc = None
                try:
                    doc = word.Documents.Open(
                        str(out_path),
                        ReadOnly=False,
                        AddToRecentFiles=False,
                        ConfirmConversions=False,
                        Visible=False
                    )

                    for plan in doc_plans:
                        ok, msg, current_text = self._apply_one_plan(doc, plan)
                        if ok:
                            total_done += 1
                            self._mark_plan(plan["plan_id"], "已替换", str(out_path), "", current_text)
                            self._log_replace(plan, "rewrite", "已替换", msg)
                        else:
                            status = "冲突" if ("旧值校验失败" in msg or "定位失败" in msg or "未命中" in msg) else "失败"
                            self._mark_plan(plan["plan_id"], status, str(out_path), msg, current_text)
                            self._log_replace(plan, "rewrite", status, msg)

                    # 参考上传脚本：先正常 Save，失败再重试 SaveAs。
                    self._save_doc_stable(doc, out_path)
                except Exception as e:
                    err = traceback.format_exc()
                    self.log(f"文档回写失败：{src.name} -> {short_error(e)}")
                    self._mark_doc_plans_failed(doc_plans, err[:3000], output_path=str(out_path))
                finally:
                    if doc is not None:
                        try:
                            doc.Close(SaveChanges=Wd.wdSaveChanges)
                        except Exception:
                            try:
                                doc.Close(SaveChanges=False)
                            except Exception:
                                pass

        finally:
            self._close_word(word)

        self.log(f"回写完成：成功 {total_done} 条")
        return total_done

    def _save_doc_stable(self, doc, out_path):
        try:
            doc.Save()
            return
        except Exception as save_error:
            self.log(f"保存失败，准备重试：{short_error(save_error)}")

        try:
            time.sleep(0.3)
            doc.Save()
            return
        except Exception as save_error:
            self.log(f"重试保存失败，准备 SaveAs：{short_error(save_error)}")

        try:
            ext = Path(out_path).suffix.lower()
            file_format = Wd.wdFormatXMLDocument if ext == ".docx" else 0
            doc.SaveAs(str(out_path), FileFormat=file_format)
        except Exception as e:
            raise RuntimeError(f"SaveAs 也失败：{short_error(e)}") from e

    def _make_output_path(self, output_dir: Path, src: Path):
        candidate = output_dir / src.name
        if not candidate.exists():
            return candidate
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        return output_dir / f"{src.stem}_{ts}{src.suffix}"

    def _mark_plan(self, plan_id, status, output_path="", error="", current_text=""):
        with self.db.connect() as conn:
            conn.execute("""
                UPDATE replace_plan
                SET status=?, output_path=?, error=?, current_text_at_write=?, updated_at=?
                WHERE plan_id=?
            """, (status, output_path, error, current_text, now_str(), plan_id))
            conn.commit()

    def _mark_doc_plans_failed(self, plans, error, output_path=""):
        with self.db.connect() as conn:
            for p in plans:
                conn.execute("""
                    UPDATE replace_plan
                    SET status='失败', output_path=?, error=?, updated_at=?
                    WHERE plan_id=?
                """, (output_path, error, now_str(), p["plan_id"]))
            conn.commit()

    def _log_replace(self, plan, action, status, message):
        with self.db.connect() as conn:
            conn.execute("""
                INSERT INTO replace_log(
                    plan_id, doc_id, block_id, action, status,
                    old_text, new_text, message, created_at
                )
                VALUES(?,?,?,?,?,?,?,?,?)
            """, (
                plan["plan_id"], plan["doc_id"], plan["block_id"],
                action, status, plan["old_text"], plan["new_text"], message, now_str()
            ))
            conn.commit()

    def _story_ranges(self, doc):
        result = []
        seq = 0
        try:
            for sr in doc.StoryRanges:
                cur = sr
                while cur is not None:
                    seq += 1
                    result.append((seq, cur, safe_get(cur, "StoryType", None)))
                    cur = safe_get(cur, "NextStoryRange", None)
        except Exception:
            try:
                seq += 1
                result.append((seq, doc.Content, Wd.wdMainTextStory))
            except Exception:
                pass
        return result

    def _get_story_by_seq(self, doc, story_seq):
        if story_seq is None:
            return None
        try:
            story_seq = int(story_seq)
        except Exception:
            return None
        for seq, rng, stype in self._story_ranges(doc):
            if seq == story_seq:
                return rng
        return None

    def _plan_values(self, plan):
        """
        兼容旧计划：没有 rule_old_value/rule_new_value 时退回 old_text/new_text。
        """
        try:
            rule_old = plan["rule_old_value"] or ""
        except Exception:
            rule_old = ""
        try:
            rule_new = plan["rule_new_value"] or ""
        except Exception:
            rule_new = ""
        try:
            replace_mode = plan["rule_replace_mode"] or "partial"
        except Exception:
            replace_mode = "partial"

        block_old = plan["old_text"] or ""
        block_new = plan["new_text"] or ""

        if not rule_old:
            rule_old = block_old
        if not rule_new:
            rule_new = block_new

        return block_old, block_new, rule_old, rule_new, replace_mode

    def _apply_one_plan(self, doc, plan):
        block_type = plan["block_type"]

        if block_type == "paragraph":
            return self._apply_paragraph(doc, plan)

        if block_type == "table_cell":
            return self._apply_table_cell(doc, plan)

        if block_type == "shape_text":
            return self._apply_shape_text(doc, plan)

        if block_type == "content_control":
            return self._apply_content_control(doc, plan)

        return False, f"当前 block_type 暂未开放自动回写：{block_type}", ""

    def _range_body(self, rng, exclude_last_char=False):
        """
        表格单元格 Range 末尾有特殊结束符，写入时通常要排除最后一个字符。
        """
        try:
            dup = rng.Duplicate
            if exclude_last_char and dup.End > dup.Start:
                dup.End = dup.End - 1
            return dup
        except Exception:
            return rng

    def _execute_replace_on_range(self, rng, search_str, replace_str, replace_all=False):
        """
        参考上传脚本中的 execute_replace_on_range：
        使用 Range.Find 执行替换。默认只替换一次，避免误伤。
        """
        if not search_str:
            return False, "search_str 为空"

        try:
            rng.Find.ClearFormatting()
            rng.Find.Replacement.ClearFormatting()
            replace_flag = Wd.wdReplaceAll if replace_all else Wd.wdReplaceOne
            result = rng.Find.Execute(
                search_str, False, False, False, False, False,
                True, Wd.wdFindStop, False, replace_str, replace_flag
            )
            if result:
                return True, "Find.Replace 命中"
            return False, "Find 未命中"
        except Exception as e:
            return False, f"Find 替换异常：{short_error(e)}"

    def _replace_text_object_value(self, cur, block_old, block_new, rule_old, rule_new, replace_mode):
        """
        对普通字符串计算新值。用于 Range.Find 失败后的稳定整块/局部回写。
        """
        cur_clean = clean_word_text(cur)
        if replace_mode == "full":
            if normalize_text(cur_clean) == normalize_text(block_old) or normalize_text(rule_old) in normalize_text(cur_clean):
                return True, block_new if block_new else rule_new, "full"
            return False, cur_clean, "旧值校验失败"

        # partial：优先用规则旧值局部替换
        if rule_old and rule_old in cur_clean:
            return True, cur_clean.replace(rule_old, rule_new), "partial_rule_raw"

        # 规范化命中但原字符串没命中，不能安全局部替换，只在整块相等时整块替换
        if normalize_text(cur_clean) == normalize_text(block_old):
            return True, block_new, "partial_block_full_fallback"

        # 如果内容块旧值在当前文本中，做内容块级局部替换
        if block_old and block_old in cur_clean:
            return True, cur_clean.replace(block_old, block_new), "partial_block_raw"

        return False, cur_clean, "旧值校验失败或未命中"

    def _apply_paragraph(self, doc, plan):
        block_old, block_new, rule_old, rule_new, replace_mode = self._plan_values(plan)

        story_rng = self._get_story_by_seq(doc, plan["story_seq"])
        if story_rng is None:
            return False, "定位失败：story_seq 不存在", ""

        try:
            p = story_rng.Paragraphs(int(plan["paragraph_index"]))
            rng = p.Range
            cur = clean_word_text(rng.Text)
        except Exception as e:
            return False, f"定位失败：段落不存在 -> {short_error(e)}", ""

        # 第一层：优先按规则旧值局部替换
        if replace_mode != "full" and rule_old and rule_old in cur:
            ok, msg = self._execute_replace_on_range(rng, rule_old, rule_new, replace_all=False)
            if ok:
                return True, f"段落局部替换完成：{msg}", cur

        # 第二层：内容块级 Find
        if block_old and block_old in cur:
            ok, msg = self._execute_replace_on_range(rng, block_old, block_new, replace_all=False)
            if ok:
                return True, f"段落内容块替换完成：{msg}", cur

        # 第三层：整段稳定回写
        ok, new_value, reason = self._replace_text_object_value(cur, block_old, block_new, rule_old, rule_new, replace_mode)
        if not ok:
            return False, f"{reason}：当前段落=[{cur[:200]}]", cur

        try:
            rng.Text = str(new_value) + "\r"
            return True, f"段落整段回写完成：{reason}", cur
        except Exception as e:
            return False, f"段落整段回写失败：{short_error(e)}", cur

    def _get_table_cell(self, story_rng, plan):
        tbl = story_rng.Tables(int(plan["table_index"]))
        # 优先 cell_index，合并单元格时比 row/col 更稳
        if plan["cell_index"]:
            return tbl.Range.Cells(int(plan["cell_index"]))
        return tbl.Cell(int(plan["row_index"]), int(plan["col_index"]))

    def _write_cell_range_text_stable(self, cell, new_value, max_retries=3):
        """
        参考上传脚本 write_word_cell_stable 的重试思路。
        这里优先写 cell.Range.Duplicate 且 End-1，避免破坏单元格结束符。
        """
        last_error = ""
        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    time.sleep(0.2 * attempt)
                rng = cell.Range.Duplicate
                if rng.End > rng.Start:
                    rng.End = rng.End - 1
                rng.Text = str(new_value)
                return True, f"单元格 Range.Text 写入成功，尝试 {attempt + 1}"
            except Exception as e:
                last_error = short_error(e)
                self.log(f"单元格写入尝试 {attempt + 1} 失败：{last_error}")

        # 兜底：直接写 cell.Range.Text，与上传脚本一致，但可能影响单元格末尾格式。
        try:
            cell.Range.Text = str(new_value)
            return True, "兜底 cell.Range.Text 写入成功"
        except Exception as e:
            return False, f"单元格写入失败：{last_error}; fallback={short_error(e)}"

    def _apply_table_cell(self, doc, plan):
        block_old, block_new, rule_old, rule_new, replace_mode = self._plan_values(plan)

        story_rng = self._get_story_by_seq(doc, plan["story_seq"])
        if story_rng is None:
            return False, "定位失败：story_seq 不存在", ""

        try:
            cell = self._get_table_cell(story_rng, plan)
            raw_rng = cell.Range
            body_rng = self._range_body(raw_rng, exclude_last_char=True)
            cur = clean_word_text(raw_rng.Text)
        except Exception as e:
            return False, f"定位失败：表格单元格不存在 -> {short_error(e)}", ""

        # 第一层：局部替换，优先用规则旧值/新值。
        if replace_mode != "full" and rule_old and rule_old in cur:
            ok, msg = self._execute_replace_on_range(body_rng, rule_old, rule_new, replace_all=False)
            if ok:
                return True, f"表格单元格局部替换完成：{msg}", cur

            # Range.Find 可能因 run/特殊对象失败，直接计算后稳定写入。
            ok_calc, new_cell_value, reason = self._replace_text_object_value(cur, block_old, block_new, rule_old, rule_new, replace_mode)
            if ok_calc:
                ok_write, msg2 = self._write_cell_range_text_stable(cell, new_cell_value)
                if ok_write:
                    return True, f"表格单元格局部计算回写完成：{reason}; {msg2}", cur
                return False, msg2, cur

        # 第二层：内容块级替换
        if block_old and block_old in cur:
            ok, msg = self._execute_replace_on_range(body_rng, block_old, block_new, replace_all=False)
            if ok:
                return True, f"表格单元格内容块替换完成：{msg}", cur

        # 第三层：整格稳定回写
        ok_calc, new_cell_value, reason = self._replace_text_object_value(cur, block_old, block_new, rule_old, rule_new, replace_mode)
        if not ok_calc:
            return False, f"{reason}：当前单元格=[{cur[:200]}]", cur

        ok_write, msg = self._write_cell_range_text_stable(cell, new_cell_value)
        if ok_write:
            return True, f"表格单元格整格/兜底回写完成：{reason}; {msg}", cur
        return False, msg, cur

    def _get_shape_collection_by_scope(self, doc, scope):
        if not scope or scope == "document":
            return safe_get(doc, "Shapes", None)

        m = re.match(r"section_(\d+)_header_(\d+)", scope or "")
        if m:
            sec_i = int(m.group(1))
            h_i = int(m.group(2))
            return safe_get(doc.Sections(sec_i).Headers(h_i), "Shapes", None)

        m = re.match(r"section_(\d+)_footer_(\d+)", scope or "")
        if m:
            sec_i = int(m.group(1))
            f_i = int(m.group(2))
            return safe_get(doc.Sections(sec_i).Footers(f_i), "Shapes", None)

        return None

    def _replace_in_string_holder(self, getter, setter, block_old, block_new, rule_old, rule_new, replace_mode):
        try:
            cur = clean_word_text(getter())
        except Exception:
            return False, "无法读取文字", ""

        if not cur:
            return False, "无文字", ""

        ok, new_value, reason = self._replace_text_object_value(cur, block_old, block_new, rule_old, rule_new, replace_mode)
        if not ok:
            return False, reason, cur

        try:
            setter(new_value)
            return True, f"对象文字替换完成：{reason}", cur
        except Exception as e:
            return False, f"对象文字写入失败：{short_error(e)}", cur

    def _apply_shape_text(self, doc, plan):
        block_old, block_new, rule_old, rule_new, replace_mode = self._plan_values(plan)

        scope = plan["shape_scope"]
        shape_index = plan["shape_index"]
        shapes = self._get_shape_collection_by_scope(doc, scope)

        if shapes is None or shape_index is None:
            return False, "定位失败：形状集合不存在", ""

        try:
            shp = shapes(int(shape_index))
        except Exception as e:
            return False, f"定位失败：形状不存在 -> {short_error(e)}", ""

        # 1. 艺术字 TextEffect.Text，参考上传脚本 replace_parenthesized_number 的做法。
        ok, msg, cur = self._replace_in_string_holder(
            lambda: shp.TextEffect.Text,
            lambda v: setattr(shp.TextEffect, "Text", v),
            block_old, block_new, rule_old, rule_new, replace_mode
        )
        if ok:
            return True, "TextEffect." + msg, cur

        # 2. TextFrame.TextRange
        try:
            if shp.HasTextFrame and shp.TextFrame.HasText:
                cur2 = clean_word_text(shp.TextFrame.TextRange.Text)
                if replace_mode != "full" and rule_old and rule_old in cur2:
                    ok2, msg2 = self._execute_replace_on_range(shp.TextFrame.TextRange, rule_old, rule_new, replace_all=False)
                    if ok2:
                        return True, "TextFrame.Range." + msg2, cur2
                ok2, msg2, cur2 = self._replace_in_string_holder(
                    lambda: shp.TextFrame.TextRange.Text,
                    lambda v: setattr(shp.TextFrame.TextRange, "Text", v),
                    block_old, block_new, rule_old, rule_new, replace_mode
                )
                if ok2:
                    return True, "TextFrame." + msg2, cur2
        except Exception:
            pass

        # 3. TextFrame2.TextRange
        try:
            cur3 = clean_word_text(shp.TextFrame2.TextRange.Text)
            if cur3:
                ok3, msg3, cur3 = self._replace_in_string_holder(
                    lambda: shp.TextFrame2.TextRange.Text,
                    lambda v: setattr(shp.TextFrame2.TextRange, "Text", v),
                    block_old, block_new, rule_old, rule_new, replace_mode
                )
                if ok3:
                    return True, "TextFrame2." + msg3, cur3
        except Exception:
            pass

        return False, "旧值校验失败或形状无可写文字", cur or ""

    def _apply_content_control(self, doc, plan):
        block_old, block_new, rule_old, rule_new, replace_mode = self._plan_values(plan)

        idx = plan["content_control_index"]
        if idx is None:
            return False, "定位失败：content_control_index 不存在", ""

        try:
            cc = doc.ContentControls(int(idx))
            rng = cc.Range
            cur = clean_word_text(rng.Text)
        except Exception as e:
            return False, f"定位失败：内容控件不存在 -> {short_error(e)}", ""

        if replace_mode != "full" and rule_old and rule_old in cur:
            ok, msg = self._execute_replace_on_range(rng, rule_old, rule_new, replace_all=False)
            if ok:
                return True, f"内容控件局部替换完成：{msg}", cur

        ok_calc, new_value, reason = self._replace_text_object_value(cur, block_old, block_new, rule_old, rule_new, replace_mode)
        if not ok_calc:
            return False, f"{reason}：当前内容控件=[{cur[:200]}]", cur

        try:
            rng.Text = new_value
            return True, f"内容控件整块回写完成：{reason}", cur
        except Exception as e:
            return False, f"内容控件替换失败：{short_error(e)}", cur



# -----------------------------
# 模板批量生成计划与执行
# -----------------------------

class TemplateBatchPlanner:
    """
    从 template_docs + template_fields + generation_data 生成 generation_plan / generation_field_plan。

    generation_data 使用竖表结构：
        data_id + field_key + field_value 组成一个新文档的数据集。
    """
    def __init__(self, db: DBManager, log_func=print):
        self.db = db
        self.log = log_func

    def generate(self, batch_name="", default_output_dir="", clear_old_pending=True):
        with self.db.connect() as conn:
            if clear_old_pending:
                conn.execute("""
                    DELETE FROM generation_plan
                    WHERE status IN ('待确认','已确认','字段缺失','冲突','失败')
                """)
                conn.commit()

            if batch_name:
                rows = conn.execute("""
                    SELECT * FROM generation_data
                    WHERE enabled=1 AND COALESCE(batch_name,'default')=?
                    ORDER BY data_id, row_id
                """, (batch_name,)).fetchall()
            else:
                rows = conn.execute("""
                    SELECT * FROM generation_data
                    WHERE enabled=1
                    ORDER BY batch_name, data_id, row_id
                """).fetchall()

            if not rows:
                self.log("generation_data 中没有启用的生成数据。")
                return 0

            groups = {}
            for r in rows:
                key = (
                    r["batch_name"] or "default",
                    str(r["data_id"] or ""),
                    r["template_id"] or "",
                    r["template_name"] or "",
                    r["output_name"] or "",
                    r["output_dir"] or "",
                )
                groups.setdefault(key, []).append(r)

            count = 0
            for key, group_rows in groups.items():
                batch, data_id, template_id_hint, template_name_hint, output_name_hint, output_dir_hint = key
                data_map = {str(r["field_key"]): ("" if r["field_value"] is None else str(r["field_value"])) for r in group_rows}

                template, conflict = self._resolve_template(conn, template_id_hint, template_name_hint)
                if not template:
                    self._insert_conflict_plan(conn, batch, data_id, output_name_hint, conflict)
                    count += 1
                    continue

                fields = conn.execute("""
                    SELECT tf.*, cb.block_type AS cb_block_type, cb.raw_text AS cb_raw_text
                    FROM template_fields tf
                    LEFT JOIN content_blocks cb ON tf.block_id=cb.block_id
                    WHERE tf.template_id=?
                    ORDER BY tf.field_id
                """, (template["template_id"],)).fetchall()

                if not fields:
                    self._insert_conflict_plan(conn, batch, data_id, output_name_hint, "模板没有配置 template_fields")
                    count += 1
                    continue

                missing = []
                field_count = 0
                for f in fields:
                    field_key = f["field_key"]
                    if int(f["required"] or 0) == 1 and field_key not in data_map and not (f["default_value"] or ""):
                        missing.append(field_key)
                    field_count += 1

                output_dir = output_dir_hint or template["output_dir"] or default_output_dir or str(Path.cwd() / "word_generated_output")
                output_name = output_name_hint or self._render_filename(template, data_id, data_map)
                output_name = self._safe_filename(output_name)
                output_path = str(Path(output_dir) / output_name)
                status = "字段缺失" if missing else "待确认"
                conflict_info = "缺失字段：" + ", ".join(missing) if missing else ""

                cur = conn.execute("""
                    INSERT INTO generation_plan(
                        batch_name, template_id, data_id, output_name, output_path,
                        template_hash_at_plan, status, field_count, missing_fields,
                        conflict_info, created_at, updated_at
                    )
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    batch, template["template_id"], data_id, output_name, output_path,
                    template["template_hash"], status, field_count, ",".join(missing),
                    conflict_info, now_str(), now_str()
                ))
                gen_id = cur.lastrowid

                for f in fields:
                    field_key = f["field_key"]
                    new_value = data_map.get(field_key, f["default_value"] or "")
                    item_status = "缺失字段" if field_key in missing else "待替换"
                    conn.execute("""
                        INSERT INTO generation_field_plan(
                            gen_id, template_id, field_id, field_key, block_id, block_type,
                            old_value, new_value, replace_mode, status,
                            created_at, updated_at
                        )
                        VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                    """, (
                        gen_id, template["template_id"], f["field_id"], field_key, f["block_id"],
                        f["block_type"] or f["cb_block_type"], f["old_value"] or f["cb_raw_text"] or "",
                        new_value, f["replace_mode"] or "partial", item_status,
                        now_str(), now_str()
                    ))
                count += 1

            conn.commit()
            self.log(f"已生成模板批量生成计划：{count} 条。")
            return count

    def _resolve_template(self, conn, template_id_hint, template_name_hint):
        if template_id_hint:
            t = conn.execute("SELECT * FROM template_docs WHERE template_id=? AND enabled=1", (template_id_hint,)).fetchone()
            if t:
                return t, ""
            return None, f"template_id={template_id_hint} 不存在或未启用"

        if template_name_hint:
            rows = conn.execute("SELECT * FROM template_docs WHERE template_name=? AND enabled=1", (template_name_hint,)).fetchall()
            if len(rows) == 1:
                return rows[0], ""
            if len(rows) > 1:
                return None, f"template_name={template_name_hint} 匹配到多个模板，请改用 template_id"
            return None, f"template_name={template_name_hint} 不存在或未启用"

        rows = conn.execute("SELECT * FROM template_docs WHERE enabled=1").fetchall()
        if len(rows) == 1:
            return rows[0], ""
        if not rows:
            return None, "没有启用的 template_docs 模板"
        return None, "存在多个启用模板，generation_data 需要指定 template_id 或 template_name"

    def _insert_conflict_plan(self, conn, batch, data_id, output_name, conflict):
        conn.execute("""
            INSERT INTO generation_plan(
                batch_name, template_id, data_id, output_name, output_path,
                status, field_count, missing_fields, conflict_info, error,
                created_at, updated_at
            )
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            batch, None, data_id, output_name or "", "", "冲突", 0, "", conflict, conflict,
            now_str(), now_str()
        ))

    def _render_filename(self, template, data_id, data_map):
        tmpl = template["filename_template"] or ""
        if not tmpl:
            ext = Path(template["template_path"]).suffix or ".docx"
            return f"{template['template_name']}_{data_id}{ext}"

        def repl(m):
            key = m.group(1)
            return str(data_map.get(key, ""))

        name = re.sub(r"\{\{\s*([^{}]+?)\s*\}\}", repl, tmpl)
        ext = Path(name).suffix
        if not ext:
            name += Path(template["template_path"]).suffix or ".docx"
        return name

    def _safe_filename(self, name):
        name = str(name).strip() or "未命名.docx"
        name = re.sub(r'[\\/:*?"<>|]', "_", name)
        return name


class TemplateBatchGenerator(WordRewriter):
    """执行已确认的 generation_plan，复制模板并按 generation_field_plan 定位直写。"""

    def execute_confirmed(self, default_output_dir=""):
        with self.db.connect() as conn:
            plans = conn.execute("""
                SELECT gp.*, td.template_path, td.template_hash, td.template_name
                FROM generation_plan gp
                JOIN template_docs td ON gp.template_id=td.template_id
                WHERE gp.status='已确认'
                ORDER BY gp.gen_id
            """).fetchall()

        if not plans:
            self.log("没有状态为“已确认”的 generation_plan。")
            return 0

        word = self._create_word()
        success_docs = 0
        try:
            for gp in plans:
                ok_doc = self._execute_one_generation(word, gp, default_output_dir)
                if ok_doc:
                    success_docs += 1
        finally:
            self._close_word(word)

        self.log(f"模板批量生成完成：成功生成 {success_docs} 个文档。")
        return success_docs

    def _execute_one_generation(self, word, gp, default_output_dir):
        template_path = Path(gp["template_path"])
        if not template_path.exists():
            self._mark_generation_plan(gp["gen_id"], "失败", f"模板文件不存在：{template_path}")
            return False

        # 模板 hash 变化时阻止执行，避免字段定位错乱。
        try:
            cur_hash = sha256_file(template_path)
            if gp["template_hash_at_plan"] and cur_hash != gp["template_hash_at_plan"]:
                self._mark_generation_plan(gp["gen_id"], "冲突", "模板 hash 已变化，请重新扫描/重新生成计划")
                return False
        except Exception:
            pass

        out_path = Path(gp["output_path"] or "")
        if not str(out_path):
            out_dir = Path(default_output_dir or Path.cwd() / "word_generated_output")
            out_path = out_dir / (gp["output_name"] or f"生成_{gp['gen_id']}{template_path.suffix}")
        if not out_path.is_absolute():
            out_path = Path(default_output_dir or Path.cwd() / "word_generated_output") / out_path
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path = self._avoid_overwrite(out_path)

        try:
            shutil.copy2(template_path, out_path)
        except Exception as e:
            self._mark_generation_plan(gp["gen_id"], "失败", f"复制模板失败：{short_error(e)}")
            return False

        doc = None
        ok_count = 0
        fail_count = 0
        try:
            doc = word.Documents.Open(
                str(out_path), ReadOnly=False, AddToRecentFiles=False,
                ConfirmConversions=False, Visible=False
            )

            with self.db.connect() as conn:
                items = conn.execute("""
                    SELECT gfp.*, cb.story_seq, cb.paragraph_index, cb.table_index, cb.row_index,
                           cb.col_index, cb.cell_index, cb.shape_scope, cb.shape_index,
                           cb.shape_name, cb.content_control_index, cb.location_json, cb.extra_json
                    FROM generation_field_plan gfp
                    JOIN content_blocks cb ON gfp.block_id=cb.block_id
                    WHERE gfp.gen_id=? AND gfp.status IN ('待替换','失败','冲突')
                    ORDER BY gfp.item_id
                """, (gp["gen_id"],)).fetchall()

            for item in items:
                # v4.6：模板批量生成不再做 old_value/旧值匹配。
                # 直接按 template_fields.block_id 关联到 content_blocks 的定位信息写入 new_value。
                ok, msg, current_text = self._apply_generation_item_direct(doc, item)
                if ok:
                    ok_count += 1
                    self._mark_generation_item(item["item_id"], "已替换", "", current_text)
                    self._log_generation(gp["gen_id"], item["item_id"], "field_write_direct", "已替换", msg)
                else:
                    fail_count += 1
                    status = "冲突" if "定位失败" in msg else "失败"
                    self._mark_generation_item(item["item_id"], status, msg, current_text)
                    self._log_generation(gp["gen_id"], item["item_id"], "field_write_direct", status, msg)

            self._save_doc_stable(doc, out_path)
            final_status = "已生成" if fail_count == 0 else "部分失败"
            self._mark_generation_plan(gp["gen_id"], final_status, f"成功字段 {ok_count}，失败字段 {fail_count}", str(out_path))
            return fail_count == 0
        except Exception as e:
            self._mark_generation_plan(gp["gen_id"], "失败", traceback.format_exc()[:3000], str(out_path))
            return False
        finally:
            if doc is not None:
                try:
                    doc.Close(SaveChanges=Wd.wdSaveChanges)
                except Exception:
                    try:
                        doc.Close(SaveChanges=False)
                    except Exception:
                        pass

    def _avoid_overwrite(self, path: Path):
        if not path.exists():
            return path
        stem, ext = path.stem, path.suffix
        for i in range(1, 10000):
            candidate = path.with_name(f"{stem}_{i:03d}{ext}")
            if not candidate.exists():
                return candidate
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        return path.with_name(f"{stem}_{ts}{ext}")

    def _apply_generation_item_direct(self, doc, item):
        """
        v4.6 模板批量生成专用：按定位直接写入，不再匹配 old_value。

        核心逻辑：
            generation_field_plan.block_id
                -> content_blocks.story_seq/table_index/row_index/col_index/cell_index
                -> Word 目标位置
                -> 直接写入 generation_field_plan.new_value

        这样可以绕开 Word 特殊字符、隐藏换行、单元格结束符、艺术字 run 拆分等导致的旧值匹配失败。
        """
        block_type = item["block_type"]
        new_value = "" if item["new_value"] is None else str(item["new_value"])

        if block_type == "table_cell":
            story_rng = self._get_story_by_seq(doc, item["story_seq"])
            if story_rng is None:
                return False, "定位失败：story_seq 不存在", ""

            try:
                cell = self._get_table_cell(story_rng, item)
                cur = clean_word_text(cell.Range.Text)
            except Exception as e:
                return False, f"定位失败：表格单元格不存在 -> {short_error(e)}", ""

            ok, msg = self._write_cell_range_text_stable(cell, new_value)
            if ok:
                return True, f"按表格定位直接写入成功：table={item['table_index']}, row={item['row_index']}, col={item['col_index']}; {msg}", cur
            return False, msg, cur

        if block_type == "paragraph":
            story_rng = self._get_story_by_seq(doc, item["story_seq"])
            if story_rng is None:
                return False, "定位失败：story_seq 不存在", ""

            try:
                p = story_rng.Paragraphs(int(item["paragraph_index"]))
                rng = p.Range
                cur = clean_word_text(rng.Text)
                rng.Text = new_value + "\r"
                return True, f"按段落定位直接写入成功：paragraph={item['paragraph_index']}", cur
            except Exception as e:
                return False, f"定位失败或段落写入失败 -> {short_error(e)}", ""

        if block_type == "content_control":
            idx = item["content_control_index"]
            if idx is None:
                return False, "定位失败：content_control_index 不存在", ""
            try:
                cc = doc.ContentControls(int(idx))
                rng = cc.Range
                cur = clean_word_text(rng.Text)
                rng.Text = new_value
                return True, f"按内容控件定位直接写入成功：content_control={idx}", cur
            except Exception as e:
                return False, f"定位失败或内容控件写入失败 -> {short_error(e)}", ""

        if block_type == "shape_text":
            scope = item["shape_scope"]
            shape_index = item["shape_index"]
            shapes = self._get_shape_collection_by_scope(doc, scope)
            if shapes is None or shape_index is None:
                return False, "定位失败：形状集合不存在", ""

            try:
                shp = shapes(int(shape_index))
            except Exception as e:
                return False, f"定位失败：形状不存在 -> {short_error(e)}", ""

            # 1. 艺术字 TextEffect.Text
            try:
                cur = clean_word_text(shp.TextEffect.Text)
                shp.TextEffect.Text = new_value
                return True, f"按形状 TextEffect 定位直接写入成功：shape={shape_index}", cur
            except Exception:
                pass

            # 2. 文本框 TextFrame.TextRange
            try:
                if shp.HasTextFrame and shp.TextFrame.HasText:
                    cur = clean_word_text(shp.TextFrame.TextRange.Text)
                    shp.TextFrame.TextRange.Text = new_value
                    return True, f"按形状 TextFrame 定位直接写入成功：shape={shape_index}", cur
            except Exception:
                pass

            # 3. TextFrame2.TextRange
            try:
                cur = clean_word_text(shp.TextFrame2.TextRange.Text)
                shp.TextFrame2.TextRange.Text = new_value
                return True, f"按形状 TextFrame2 定位直接写入成功：shape={shape_index}", cur
            except Exception as e:
                return False, f"定位到形状，但未找到可写文字接口 -> {short_error(e)}", ""

        return False, f"当前 block_type 暂未开放定位直写：{block_type}", ""

    def _make_pseudo_plan(self, item):
        block_old = item["old_value"] or ""
        block_new = item["new_value"] or ""
        return {
            "block_type": item["block_type"],
            "old_text": block_old,
            "new_text": block_new,
            "rule_old_value": block_old,
            "rule_new_value": block_new,
            "rule_match_mode": "contains",
            "rule_replace_mode": item["replace_mode"] or "partial",
            "story_seq": item["story_seq"],
            "paragraph_index": item["paragraph_index"],
            "table_index": item["table_index"],
            "row_index": item["row_index"],
            "col_index": item["col_index"],
            "cell_index": item["cell_index"],
            "shape_scope": item["shape_scope"],
            "shape_index": item["shape_index"],
            "shape_name": item["shape_name"],
            "content_control_index": item["content_control_index"],
        }

    def _mark_generation_plan(self, gen_id, status, message="", output_path=None):
        with self.db.connect() as conn:
            if output_path is None:
                conn.execute("""
                    UPDATE generation_plan
                    SET status=?, error=?, updated_at=?
                    WHERE gen_id=?
                """, (status, message, now_str(), gen_id))
            else:
                conn.execute("""
                    UPDATE generation_plan
                    SET status=?, error=?, output_path=?, updated_at=?
                    WHERE gen_id=?
                """, (status, message, output_path, now_str(), gen_id))
            conn.commit()

    def _mark_generation_item(self, item_id, status, error="", current_text=""):
        with self.db.connect() as conn:
            conn.execute("""
                UPDATE generation_field_plan
                SET status=?, error=?, current_text_at_write=?, updated_at=?
                WHERE item_id=?
            """, (status, error, current_text, now_str(), item_id))
            conn.commit()

    def _log_generation(self, gen_id, item_id, action, status, message):
        with self.db.connect() as conn:
            conn.execute("""
                INSERT INTO generation_log(gen_id, item_id, action, status, message, created_at)
                VALUES(?,?,?,?,?,?)
            """, (gen_id, item_id, action, status, message, now_str()))
            conn.commit()


# -----------------------------
# Excel 抽取 / 模板批量生成
# -----------------------------

class ExcelExtractor:
    """使用 win32com 调用 Excel，抽取 xls/xlsx/xlsm 模板中的 UsedRange 非空单元格。"""
    def __init__(self, db: DBManager, log_func=print):
        self.db = db
        self.log = log_func

    def _create_excel(self):
        try:
            import pythoncom
            import win32com.client
        except Exception as e:
            raise RuntimeError("缺少 pywin32，请先执行：pip install pywin32") from e
        pythoncom.CoInitialize()
        excel = win32com.client.DispatchEx("Excel.Application")
        excel.Visible = False
        excel.DisplayAlerts = False
        return excel

    def _close_excel(self, excel):
        try:
            excel.Quit()
        except Exception:
            pass
        try:
            import pythoncom
            pythoncom.CoUninitialize()
        except Exception:
            pass

    def extract_folder(self, folder, recursive=True):
        folder = Path(folder)
        if not folder.exists():
            raise FileNotFoundError(folder)
        files = [p for p in (folder.rglob("*") if recursive else folder.iterdir()) if p.is_file() and is_excel_file(p)]
        self.log(f"找到 Excel 文件：{len(files)} 个")
        if not files:
            return
        excel = self._create_excel()
        try:
            for i, path in enumerate(files, 1):
                self.log(f"[{i}/{len(files)}] 抽取 Excel：{path}")
                try:
                    self.extract_one(excel, path)
                    self.log(f"完成：{path.name}")
                except Exception as e:
                    self.log(f"失败：{path.name} -> {short_error(e)}")
        finally:
            self._close_excel(excel)

    def extract_one(self, excel, file_path):
        file_path = Path(file_path).resolve()
        template_id = self.upsert_excel_template(file_path, status="extracting")
        with self.db.connect() as conn:
            conn.execute("DELETE FROM excel_content_blocks WHERE excel_template_id=?", (template_id,))
            conn.commit()
        wb = None
        try:
            wb = excel.Workbooks.Open(str(file_path), ReadOnly=True, UpdateLinks=0)
            with self.db.connect() as conn:
                for sheet_index in range(1, wb.Worksheets.Count + 1):
                    ws = wb.Worksheets(sheet_index)
                    sheet_name = safe_str(ws.Name)
                    used = ws.UsedRange
                    if used is None:
                        continue
                    start_row = int(used.Row)
                    start_col = int(used.Column)
                    row_count = int(used.Rows.Count)
                    col_count = int(used.Columns.Count)
                    for r in range(start_row, start_row + row_count):
                        for c in range(start_col, start_col + col_count):
                            try:
                                cell = ws.Cells(r, c)
                                value = safe_str(cell.Text)
                                formula = safe_str(cell.Formula)
                                if formula == value:
                                    formula = ""
                                if not value and not formula:
                                    continue
                                is_merged = 1 if bool(cell.MergeCells) else 0
                                merge_area = ""
                                if is_merged:
                                    try:
                                        merge_area = safe_str(cell.MergeArea.Address(False, False))
                                    except Exception:
                                        merge_area = ""
                                try:
                                    address = safe_str(cell.Address(False, False))
                                except Exception:
                                    address = excel_cell_address(r, c)
                                conn.execute("""
                                    INSERT INTO excel_content_blocks(
                                        excel_template_id, sheet_index, sheet_name, row_index, col_index, cell_address,
                                        raw_value, formula, number_format, is_merged, merge_area, created_at
                                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                                """, (
                                    template_id, sheet_index, sheet_name, r, c, address,
                                    value, formula, safe_str(cell.NumberFormat), is_merged, merge_area, now_str()
                                ))
                            except Exception:
                                continue
                conn.commit()
            self.update_excel_template(template_id, status="ok", updated_at=now_str())
        finally:
            if wb is not None:
                try:
                    wb.Close(False)
                except Exception:
                    pass

    def upsert_excel_template(self, file_path: Path, status="ok"):
        stat = file_path.stat()
        file_hash = sha256_file(file_path)
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO excel_template_docs(
                    template_name, template_path, file_ext, file_hash, status, created_at, updated_at
                ) VALUES(?,?,?,?,?,?,?)
                ON CONFLICT(template_path) DO UPDATE SET
                    template_name=excluded.template_name,
                    file_ext=excluded.file_ext,
                    file_hash=excluded.file_hash,
                    status=excluded.status,
                    updated_at=excluded.updated_at
            """, (file_path.name, str(file_path), file_path.suffix.lower(), file_hash, status, now_str(), now_str()))
            conn.commit()
            return cur.execute("SELECT excel_template_id FROM excel_template_docs WHERE template_path=?", (str(file_path),)).fetchone()["excel_template_id"]

    def update_excel_template(self, template_id, **kwargs):
        if not kwargs:
            return
        keys = list(kwargs.keys())
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE excel_template_docs SET " + ",".join([f"{k}=?" for k in keys]) + " WHERE excel_template_id=?",
                [kwargs[k] for k in keys] + [template_id]
            )
            conn.commit()


class ExcelTemplatePlanner:
    """从 excel_template_docs + excel_template_fields + excel_generation_data 生成 Excel 生成计划。"""
    def __init__(self, db: DBManager, log_func=print):
        self.db = db
        self.log = log_func

    def generate(self, batch_name="", default_output_dir="", clear_old_pending=True):
        with self.db.connect() as conn:
            if clear_old_pending:
                conn.execute("DELETE FROM excel_generation_plan WHERE status IN ('待确认','已确认','字段缺失','冲突','失败')")
                conn.commit()
            if batch_name:
                rows = conn.execute("""
                    SELECT * FROM excel_generation_data
                    WHERE enabled=1 AND COALESCE(batch_name,'default')=?
                    ORDER BY data_id, row_id
                """, (batch_name,)).fetchall()
            else:
                rows = conn.execute("""
                    SELECT * FROM excel_generation_data
                    WHERE enabled=1
                    ORDER BY batch_name, data_id, row_id
                """).fetchall()
            if not rows:
                self.log("excel_generation_data 中没有启用的生成数据。")
                return 0
            groups = {}
            for r in rows:
                key = (r["batch_name"] or "default", str(r["data_id"] or ""), r["excel_template_id"] or "", r["template_name"] or "", r["output_name"] or "", r["output_dir"] or "")
                groups.setdefault(key, []).append(r)
            count = 0
            for key, group_rows in groups.items():
                batch, data_id, template_id_hint, template_name_hint, output_name_hint, output_dir_hint = key
                data_map = {str(r["field_key"]): ("" if r["field_value"] is None else str(r["field_value"])) for r in group_rows}
                template, conflict = self._resolve_template(conn, template_id_hint, template_name_hint)
                if not template:
                    self._insert_conflict_plan(conn, batch, data_id, output_name_hint, conflict)
                    count += 1
                    continue
                fields = conn.execute("""
                    SELECT ef.*, eb.raw_value AS eb_raw_value, eb.sheet_name AS eb_sheet_name,
                           eb.row_index AS eb_row_index, eb.col_index AS eb_col_index, eb.cell_address AS eb_cell_address
                    FROM excel_template_fields ef
                    LEFT JOIN excel_content_blocks eb ON ef.excel_block_id=eb.excel_block_id
                    WHERE ef.excel_template_id=?
                    ORDER BY ef.excel_field_id
                """, (template["excel_template_id"],)).fetchall()
                if not fields:
                    self._insert_conflict_plan(conn, batch, data_id, output_name_hint, "Excel模板没有配置 excel_template_fields")
                    count += 1
                    continue
                missing = []
                for f in fields:
                    fk = f["field_key"]
                    if int(f["required"] or 0) == 1 and fk not in data_map and not (f["default_value"] or ""):
                        missing.append(fk)
                output_dir = output_dir_hint or template["output_dir"] or default_output_dir or str(Path.cwd() / "excel_generated_output")
                output_name = output_name_hint or self._render_filename(template, data_id, data_map)
                output_name = self._safe_filename(output_name, Path(template["template_path"]).suffix or ".xlsx")
                output_path = str(Path(output_dir) / output_name)
                status = "字段缺失" if missing else "待确认"
                cur = conn.execute("""
                    INSERT INTO excel_generation_plan(
                        batch_name, excel_template_id, data_id, output_name, output_path, template_hash_at_plan,
                        status, field_count, missing_fields, conflict_info, created_at, updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                """, (batch, template["excel_template_id"], data_id, output_name, output_path, template["file_hash"], status, len(fields), ",".join(missing), "缺失字段：" + ", ".join(missing) if missing else "", now_str(), now_str()))
                excel_gen_id = cur.lastrowid
                for f in fields:
                    fk = f["field_key"]
                    new_value = data_map.get(fk, f["default_value"] or "")
                    conn.execute("""
                        INSERT INTO excel_generation_field_plan(
                            excel_gen_id, excel_template_id, excel_field_id, field_key, excel_block_id,
                            sheet_name, row_index, col_index, cell_address, old_value, new_value, write_mode, status,
                            created_at, updated_at
                        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """, (excel_gen_id, template["excel_template_id"], f["excel_field_id"], fk, f["excel_block_id"], f["sheet_name"] or f["eb_sheet_name"], f["eb_row_index"], f["eb_col_index"], f["cell_address"] or f["eb_cell_address"], f["old_value"] or f["eb_raw_value"] or "", new_value, f["write_mode"] or "cell", "缺失字段" if fk in missing else "待替换", now_str(), now_str()))
                count += 1
            conn.commit()
            self.log(f"已生成 Excel 批量生成计划：{count} 条。")
            return count

    def _resolve_template(self, conn, template_id_hint, template_name_hint):
        if template_id_hint:
            t = conn.execute("SELECT * FROM excel_template_docs WHERE excel_template_id=? AND enabled=1", (template_id_hint,)).fetchone()
            return (t, "") if t else (None, f"excel_template_id={template_id_hint} 不存在或未启用")
        if template_name_hint:
            rows = conn.execute("SELECT * FROM excel_template_docs WHERE template_name=? AND enabled=1", (template_name_hint,)).fetchall()
            if len(rows) == 1:
                return rows[0], ""
            if len(rows) > 1:
                return None, f"template_name={template_name_hint} 匹配到多个Excel模板，请改用 excel_template_id"
            return None, f"template_name={template_name_hint} 不存在或未启用"
        rows = conn.execute("SELECT * FROM excel_template_docs WHERE enabled=1").fetchall()
        if len(rows) == 1:
            return rows[0], ""
        if not rows:
            return None, "没有启用的 excel_template_docs 模板"
        return None, "存在多个启用Excel模板，excel_generation_data 需要指定 excel_template_id 或 template_name"

    def _insert_conflict_plan(self, conn, batch, data_id, output_name, conflict):
        conn.execute("""
            INSERT INTO excel_generation_plan(batch_name, data_id, output_name, status, field_count, conflict_info, error, created_at, updated_at)
            VALUES(?,?,?,?,?,?,?,?,?)
        """, (batch, data_id, output_name or "", "冲突", 0, conflict, conflict, now_str(), now_str()))

    def _render_filename(self, template, data_id, data_map):
        tmpl = template["filename_template"] or ""
        if not tmpl:
            return f"{Path(template['template_path']).stem}_{data_id}{Path(template['template_path']).suffix or '.xlsx'}"
        def repl(m): return str(data_map.get(m.group(1), ""))
        name = re.sub(r"\{\{\s*([^{}]+?)\s*\}\}", repl, tmpl)
        if not Path(name).suffix:
            name += Path(template["template_path"]).suffix or ".xlsx"
        return name

    def _safe_filename(self, name, default_ext=".xlsx"):
        name = str(name).strip() or f"未命名{default_ext}"
        name = re.sub(r'[\\/:*?"<>|]', "_", name)
        if not Path(name).suffix:
            name += default_ext
        return name


class ExcelTemplateGenerator:
    """执行已确认的 Excel 生成计划，复制模板并按单元格定位直写。"""
    def __init__(self, db: DBManager, log_func=print):
        self.db = db
        self.log = log_func

    def _create_excel(self):
        try:
            import pythoncom
            import win32com.client
        except Exception as e:
            raise RuntimeError("缺少 pywin32，请先执行：pip install pywin32") from e
        pythoncom.CoInitialize()
        excel = win32com.client.DispatchEx("Excel.Application")
        excel.Visible = False
        excel.DisplayAlerts = False
        return excel

    def _close_excel(self, excel):
        try: excel.Quit()
        except Exception: pass
        try:
            import pythoncom
            pythoncom.CoUninitialize()
        except Exception:
            pass

    def execute_confirmed(self, default_output_dir=""):
        with self.db.connect() as conn:
            plans = conn.execute("""
                SELECT gp.*, td.template_path, td.file_hash, td.template_name
                FROM excel_generation_plan gp
                JOIN excel_template_docs td ON gp.excel_template_id=td.excel_template_id
                WHERE gp.status='已确认'
                ORDER BY gp.excel_gen_id
            """).fetchall()
        if not plans:
            self.log("没有状态为“已确认”的 excel_generation_plan。")
            return 0
        excel = self._create_excel()
        success = 0
        try:
            for gp in plans:
                if self._execute_one(excel, gp, default_output_dir):
                    success += 1
        finally:
            self._close_excel(excel)
        self.log(f"Excel模板批量生成完成：成功生成 {success} 个文件。")
        return success

    def _execute_one(self, excel, gp, default_output_dir):
        template_path = Path(gp["template_path"])
        if not template_path.exists():
            self._mark_plan(gp["excel_gen_id"], "失败", f"Excel模板不存在：{template_path}")
            return False
        try:
            cur_hash = sha256_file(template_path)
            if gp["template_hash_at_plan"] and cur_hash != gp["template_hash_at_plan"]:
                self._mark_plan(gp["excel_gen_id"], "冲突", "Excel模板 hash 已变化，请重新扫描/重新生成计划")
                return False
        except Exception:
            pass
        out_path = Path(gp["output_path"] or "")
        if not str(out_path):
            out_path = Path(default_output_dir or Path.cwd() / "excel_generated_output") / (gp["output_name"] or f"生成_{gp['excel_gen_id']}{template_path.suffix}")
        if not out_path.is_absolute():
            out_path = Path(default_output_dir or Path.cwd() / "excel_generated_output") / out_path
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path = self._avoid_overwrite(out_path)
        try:
            shutil.copy2(template_path, out_path)
        except Exception as e:
            self._mark_plan(gp["excel_gen_id"], "失败", f"复制Excel模板失败：{short_error(e)}")
            return False
        wb = None
        ok_count = fail_count = 0
        try:
            wb = excel.Workbooks.Open(str(out_path), ReadOnly=False, UpdateLinks=0)
            with self.db.connect() as conn:
                items = conn.execute("""
                    SELECT * FROM excel_generation_field_plan
                    WHERE excel_gen_id=? AND status IN ('待替换','失败','冲突')
                    ORDER BY excel_item_id
                """, (gp["excel_gen_id"],)).fetchall()
            for item in items:
                ok, msg, cur = self._write_item(wb, item)
                if ok:
                    ok_count += 1
                    self._mark_item(item["excel_item_id"], "已替换", "", cur)
                    self._log(gp["excel_gen_id"], item["excel_item_id"], "cell_write_direct", "已替换", msg)
                else:
                    fail_count += 1
                    self._mark_item(item["excel_item_id"], "冲突" if "定位失败" in msg else "失败", msg, cur)
                    self._log(gp["excel_gen_id"], item["excel_item_id"], "cell_write_direct", "失败", msg)
            wb.Save()
            self._mark_plan(gp["excel_gen_id"], "已生成" if fail_count == 0 else "部分失败", f"成功字段 {ok_count}，失败字段 {fail_count}", str(out_path))
            return fail_count == 0
        except Exception:
            self._mark_plan(gp["excel_gen_id"], "失败", traceback.format_exc()[:3000], str(out_path))
            return False
        finally:
            if wb is not None:
                try: wb.Close(SaveChanges=True)
                except Exception:
                    try: wb.Close(SaveChanges=False)
                    except Exception: pass

    def _write_item(self, wb, item):
        try:
            sheet_name = item["sheet_name"]
            if sheet_name:
                ws = wb.Worksheets(sheet_name)
            else:
                return False, "定位失败：sheet_name 为空", ""
            row = item["row_index"]
            col = item["col_index"]
            if not row or not col:
                addr = item["cell_address"]
                if not addr:
                    return False, "定位失败：缺少 row/col/cell_address", ""
                cell = ws.Range(addr)
            else:
                cell = ws.Cells(int(row), int(col))
            try:
                cur = safe_str(cell.Text)
            except Exception:
                cur = safe_str(cell.Value)
            target = cell
            try:
                if bool(cell.MergeCells):
                    target = cell.MergeArea.Cells(1, 1)
            except Exception:
                pass
            target.Value = "" if item["new_value"] is None else str(item["new_value"])
            return True, f"按Excel单元格定位直接写入成功：{sheet_name}!{item['cell_address']}", cur
        except Exception as e:
            return False, f"定位失败或写入失败：{short_error(e)}", ""

    def _avoid_overwrite(self, path: Path):
        if not path.exists(): return path
        for i in range(1, 10000):
            candidate = path.with_name(f"{path.stem}_{i:03d}{path.suffix}")
            if not candidate.exists(): return candidate
        return path.with_name(f"{path.stem}_{datetime.now().strftime('%Y%m%d_%H%M%S')}{path.suffix}")

    def _mark_plan(self, excel_gen_id, status, message="", output_path=None):
        with self.db.connect() as conn:
            if output_path is None:
                conn.execute("UPDATE excel_generation_plan SET status=?, error=?, updated_at=? WHERE excel_gen_id=?", (status, message, now_str(), excel_gen_id))
            else:
                conn.execute("UPDATE excel_generation_plan SET status=?, error=?, output_path=?, updated_at=? WHERE excel_gen_id=?", (status, message, output_path, now_str(), excel_gen_id))
            conn.commit()

    def _mark_item(self, excel_item_id, status, error="", current_text=""):
        with self.db.connect() as conn:
            conn.execute("UPDATE excel_generation_field_plan SET status=?, error=?, current_text_at_write=?, updated_at=? WHERE excel_item_id=?", (status, error, current_text, now_str(), excel_item_id))
            conn.commit()

    def _log(self, excel_gen_id, excel_item_id, action, status, message):
        with self.db.connect() as conn:
            conn.execute("INSERT INTO excel_generation_log(excel_gen_id, excel_item_id, action, status, message, created_at) VALUES(?,?,?,?,?,?)", (excel_gen_id, excel_item_id, action, status, message, now_str()))
            conn.commit()

# -----------------------------
# GUI
# -----------------------------

class App(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title(APP_NAME)
        self.geometry("1350x820")

        self.log_queue = queue.Queue()
        self.worker = None

        self.folder_var = tk.StringVar(value="")
        self.db_var = tk.StringVar(value=str(Path.cwd() / "word_sqlite_manager.db"))
        self.output_var = tk.StringVar(value=str(Path.cwd() / "word_modified_output"))
        self.recursive_var = tk.BooleanVar(value=True)
        self.limit_var = tk.IntVar(value=500)

        self.db = DBManager(self.db_var.get())
        try:
            self.db.init_db()
        except Exception:
            # 数据库路径异常时不阻止界面启动，用户可以重新选择 DB 后再初始化。
            pass

        self._build_ui()
        self._poll_log_queue()
        self.after(300, self.refresh_current_table)

    def _build_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        top = ttk.LabelFrame(self, text="路径设置")
        top.grid(row=0, column=0, sticky="ew", padx=8, pady=6)
        top.columnconfigure(1, weight=1)

        ttk.Label(top, text="Word目录：").grid(row=0, column=0, padx=4, pady=3, sticky="w")
        ttk.Entry(top, textvariable=self.folder_var).grid(row=0, column=1, padx=4, pady=3, sticky="ew")
        ttk.Button(top, text="选择目录", command=self.choose_folder).grid(row=0, column=2, padx=4, pady=3)

        ttk.Label(top, text="SQLite数据库：").grid(row=1, column=0, padx=4, pady=3, sticky="w")
        ttk.Entry(top, textvariable=self.db_var).grid(row=1, column=1, padx=4, pady=3, sticky="ew")
        ttk.Button(top, text="选择/新建DB", command=self.choose_db).grid(row=1, column=2, padx=4, pady=3)

        ttk.Label(top, text="回写副本目录：").grid(row=2, column=0, padx=4, pady=3, sticky="w")
        ttk.Entry(top, textvariable=self.output_var).grid(row=2, column=1, padx=4, pady=3, sticky="ew")
        ttk.Button(top, text="选择输出目录", command=self.choose_output).grid(row=2, column=2, padx=4, pady=3)

        opts = ttk.Frame(top)
        opts.grid(row=3, column=1, sticky="w", padx=4, pady=3)
        ttk.Checkbutton(opts, text="递归扫描子目录", variable=self.recursive_var).pack(side="left", padx=4)
        ttk.Label(opts, text="预览行数：").pack(side="left", padx=10)
        ttk.Entry(opts, textvariable=self.limit_var, width=8).pack(side="left")

        actions = ttk.LabelFrame(self, text="操作")
        actions.grid(row=1, column=0, sticky="ew", padx=8, pady=4)

        common_row = ttk.Frame(actions)
        common_row.pack(fill="x", padx=4, pady=2)
        word_row = ttk.Frame(actions)
        word_row.pack(fill="x", padx=4, pady=2)
        excel_row = ttk.Frame(actions)
        excel_row.pack(fill="x", padx=4, pady=2)

        common_buttons = [
            ("初始化数据库", self.init_db),
            ("刷新预览", self.refresh_current_table),
            ("删除选中生成计划", self.delete_selected_rows),
        ]
        word_buttons = [
            ("扫描Word并入库", self.extract_folder),
            ("当前Word目录→登记Word模板", self.register_templates_from_folder),
            ("Word数据→生成计划", self.generate_template_plans),
            ("选中Word计划→已确认", lambda: self.set_selected_generation_status("已确认")),
            ("执行已确认Word生成(定位直写)", self.execute_template_generation),
        ]
        excel_buttons = [
            ("扫描Excel并入库", self.extract_excel_folder),
            ("当前Excel目录→登记Excel模板", self.register_excel_templates_from_folder),
            ("Excel数据→生成计划", self.generate_excel_template_plans),
            ("选中Excel计划→已确认", lambda: self.set_selected_excel_generation_status("已确认")),
            ("执行已确认Excel生成(定位直写)", self.execute_excel_template_generation),
        ]

        ttk.Label(common_row, text="通用：").pack(side="left", padx=(2, 8))
        for text, cmd in common_buttons:
            ttk.Button(common_row, text=text, command=cmd).pack(side="left", padx=4, pady=3)
        ttk.Label(word_row, text="Word：").pack(side="left", padx=(2, 8))
        for text, cmd in word_buttons:
            ttk.Button(word_row, text=text, command=cmd).pack(side="left", padx=4, pady=3)
        ttk.Label(excel_row, text="Excel：").pack(side="left", padx=(2, 8))
        for text, cmd in excel_buttons:
            ttk.Button(excel_row, text=text, command=cmd).pack(side="left", padx=4, pady=3)

        main = ttk.PanedWindow(self, orient="vertical")
        main.grid(row=2, column=0, sticky="nsew", padx=8, pady=4)

        preview_frame = ttk.Frame(main)
        preview_frame.rowconfigure(0, weight=1)
        preview_frame.columnconfigure(0, weight=1)
        main.add(preview_frame, weight=4)

        self.notebook = ttk.Notebook(preview_frame)
        self.notebook.grid(row=0, column=0, sticky="nsew")
        self.notebook.bind("<<NotebookTabChanged>>", lambda e: self.refresh_current_table())

        self.tables = {}
        for table in [
            "documents", "content_blocks", "media_blocks",
            "template_docs", "template_fields", "generation_data", "generation_plan", "generation_field_plan", "generation_log",
            "excel_template_docs", "excel_content_blocks", "excel_template_fields", "excel_generation_data",
            "excel_generation_plan", "excel_generation_field_plan", "excel_generation_log"
        ]:
            frame = ttk.Frame(self.notebook)
            frame.rowconfigure(0, weight=1)
            frame.columnconfigure(0, weight=1)
            self.notebook.add(frame, text=table)

            tree = ttk.Treeview(frame, show="headings", selectmode="extended")
            vsb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
            hsb = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
            tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

            tree.grid(row=0, column=0, sticky="nsew")
            vsb.grid(row=0, column=1, sticky="ns")
            hsb.grid(row=1, column=0, sticky="ew")

            tree.bind("<Double-1>", self.show_cell_detail)
            # 支持鼠标左键拖动多选：按住左键从一行拖到另一行，会选中中间连续行。
            tree.bind("<ButtonPress-1>", self._tree_drag_start, add="+")
            tree.bind("<B1-Motion>", self._tree_drag_select, add="+")
            tree.bind("<ButtonRelease-1>", self._tree_drag_end, add="+")
            self.tables[table] = tree

        log_frame = ttk.LabelFrame(main, text="日志")
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)
        main.add(log_frame, weight=1)

        self.log_text = tk.Text(log_frame, height=10, wrap="word")
        self.log_text.grid(row=0, column=0, sticky="nsew")
        log_scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        log_scroll.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=log_scroll.set)

    def choose_folder(self):
        d = filedialog.askdirectory(title="选择包含 Word 的目录")
        if d:
            self.folder_var.set(d)

    def choose_db(self):
        p = filedialog.asksaveasfilename(
            title="选择或新建 SQLite 数据库",
            defaultextension=".db",
            filetypes=[("SQLite DB", "*.db"), ("All files", "*.*")]
        )
        if p:
            self.db_var.set(p)
            self.db = DBManager(p)

    def choose_output(self):
        d = filedialog.askdirectory(title="选择回写副本输出目录")
        if d:
            self.output_var.set(d)

    def log(self, msg):
        self.log_queue.put(f"[{now_str()}] {msg}")

    def _poll_log_queue(self):
        try:
            while True:
                msg = self.log_queue.get_nowait()
                self.log_text.insert("end", msg + "\n")
                self.log_text.see("end")
        except queue.Empty:
            pass
        self.after(200, self._poll_log_queue)

    def run_worker(self, target, after=None):
        if self.worker and self.worker.is_alive():
            messagebox.showwarning("提示", "当前已有任务正在运行。")
            return

        def wrapper():
            try:
                target()
                if after:
                    self.after(0, after)
            except Exception as e:
                err_msg = str(e)
                err_trace = traceback.format_exc()
                self.log(f"任务失败：{short_error(e)}")
                self.log(err_trace)
                # Python 3 会在 except 结束后清理异常变量 e，
                # 所以不能在 after/lambda 里直接引用 e，否则会触发：
                # NameError: free variable 'e' referenced before assignment
                self.after(0, lambda msg=err_msg: messagebox.showerror("错误", msg))

        self.worker = threading.Thread(target=wrapper, daemon=True)
        self.worker.start()

    def init_db(self):
        self.db = DBManager(self.db_var.get())
        self.db.init_db()
        self.log("数据库初始化完成。")
        self.refresh_current_table()

    def extract_folder(self):
        folder = self.folder_var.get().strip()
        if not folder:
            messagebox.showwarning("提示", "请先选择 Word 目录。")
            return

        self.db = DBManager(self.db_var.get())
        self.db.init_db()

        def task():
            extractor = WordExtractor(self.db, self.log)
            extractor.extract_folder(folder, recursive=self.recursive_var.get())

        self.run_worker(task, after=self.refresh_current_table)


    def register_templates_from_folder(self):
        folder = self.folder_var.get().strip()
        if not folder:
            messagebox.showwarning("提示", "请先选择 Word 目录。")
            return
        self.db = DBManager(self.db_var.get())
        self.db.init_db()

        template_type = simpledialog.askstring(
            "模板类型",
            "请输入模板类型/分类，可留空：",
            parent=self
        )
        if template_type is None:
            return

        filename_template = simpledialog.askstring(
            "输出文件名模板",
            "可选：输入输出文件名模板，例如 {{客户名称}}_{{板号}}_确认函.doc；留空后续可直接改数据库：",
            parent=self
        )
        if filename_template is None:
            return

        def task():
            count = self.db.register_templates_from_folder(
                folder,
                recursive=self.recursive_var.get(),
                template_type=template_type.strip(),
                filename_template=filename_template.strip()
            )
            self.log(f"已登记模板：{count} 个。建议先确保这些模板已执行过“扫描Word并入库”，再配置 template_fields。")

        self.run_worker(task, after=lambda: self.refresh_table("template_docs"))

    def generate_plan(self):
        self.db = DBManager(self.db_var.get())
        self.db.init_db()

        def task():
            planner = ReplacePlanner(self.db, self.log)
            planner.generate(clear_old_pending=True)

        self.run_worker(task, after=lambda: self.refresh_table("replace_plan"))

    def generate_plan_from_old_new_map(self):
        self.db = DBManager(self.db_var.get())
        self.db.init_db()

        group_name = simpledialog.askstring(
            "旧新映射批次",
            "请输入要生成的 group_name；留空表示全部启用映射：",
            parent=self
        )
        if group_name is None:
            return
        group_name = group_name.strip()

        def task():
            planner = OldNewMapPlanner(self.db, self.log)
            planner.generate(clear_old_pending=True, group_name=group_name)

        self.run_worker(task, after=lambda: self.refresh_table("replace_plan"))


    def generate_template_plans(self):
        self.db = DBManager(self.db_var.get())
        self.db.init_db()

        batch_name = simpledialog.askstring(
            "模板生成批次",
            "请输入 generation_data.batch_name；留空表示全部启用生成数据：",
            parent=self
        )
        if batch_name is None:
            return
        batch_name = batch_name.strip()
        default_output_dir = self.output_var.get().strip()

        def task():
            planner = TemplateBatchPlanner(self.db, self.log)
            planner.generate(batch_name=batch_name, default_output_dir=default_output_dir, clear_old_pending=True)

        self.run_worker(task, after=lambda: self.refresh_table("generation_plan"))

    def execute_template_generation(self):
        output_dir = self.output_var.get().strip()
        if not output_dir:
            messagebox.showwarning("提示", "请先选择输出目录。")
            return

        if not messagebox.askyesno(
            "确认",
            "将执行 status=已确认 的 generation_plan：复制模板并生成新 Word 文件，不覆盖模板。\n是否继续？"
        ):
            return

        self.db = DBManager(self.db_var.get())
        self.db.init_db()

        def task():
            generator = TemplateBatchGenerator(self.db, self.log)
            generator.execute_confirmed(default_output_dir=output_dir)

        self.run_worker(task, after=lambda: self.refresh_table("generation_plan"))

    def extract_excel_folder(self):
        folder = self.folder_var.get().strip()
        if not folder:
            messagebox.showwarning("提示", "请先选择 Excel 模板所在目录。")
            return
        self.db = DBManager(self.db_var.get())
        self.db.init_db()
        def task():
            extractor = ExcelExtractor(self.db, self.log)
            extractor.extract_folder(folder, recursive=self.recursive_var.get())
        self.run_worker(task, after=lambda: self.refresh_table("excel_template_docs"))

    def register_excel_templates_from_folder(self):
        folder = self.folder_var.get().strip()
        if not folder:
            messagebox.showwarning("提示", "请先选择 Excel 模板所在目录。")
            return
        template_type = simpledialog.askstring("Excel模板类型", "请输入 Excel 模板类型/备注，可留空：", parent=self)
        if template_type is None:
            return
        filename_template = simpledialog.askstring("Excel文件名模板", "请输入输出文件名模板，可留空，例如：{{客户名称}}_{{板号}}.xlsx：", parent=self)
        if filename_template is None:
            return
        self.db = DBManager(self.db_var.get())
        self.db.init_db()
        folder_path = Path(folder)
        files = [p for p in (folder_path.rglob("*") if self.recursive_var.get() else folder_path.iterdir()) if p.is_file() and is_excel_file(p)]
        count = 0
        with self.db.connect() as conn:
            for p in files:
                try:
                    conn.execute("""
                        INSERT INTO excel_template_docs(
                            enabled, template_name, template_path, file_ext, file_hash, filename_template, remark, status, created_at, updated_at
                        ) VALUES(?,?,?,?,?,?,?,?,?,?)
                        ON CONFLICT(template_path) DO UPDATE SET
                            template_name=excluded.template_name,
                            file_ext=excluded.file_ext,
                            file_hash=excluded.file_hash,
                            filename_template=excluded.filename_template,
                            remark=excluded.remark,
                            status='ok',
                            updated_at=excluded.updated_at
                    """, (1, p.name, str(p.resolve()), p.suffix.lower(), sha256_file(p), filename_template.strip(), template_type.strip(), "ok", now_str(), now_str()))
                    count += 1
                except Exception as e:
                    self.log(f"登记Excel模板失败：{p.name} -> {short_error(e)}")
            conn.commit()
        self.log(f"已登记 Excel 模板：{count} 个。")
        self.refresh_table("excel_template_docs")

    def generate_excel_template_plans(self):
        self.db = DBManager(self.db_var.get())
        self.db.init_db()
        batch_name = simpledialog.askstring("Excel生成批次", "请输入 excel_generation_data.batch_name；留空表示全部启用生成数据：", parent=self)
        if batch_name is None:
            return
        batch_name = batch_name.strip()
        default_output_dir = self.output_var.get().strip()
        def task():
            planner = ExcelTemplatePlanner(self.db, self.log)
            planner.generate(batch_name=batch_name, default_output_dir=default_output_dir, clear_old_pending=True)
        self.run_worker(task, after=lambda: self.refresh_table("excel_generation_plan"))

    def set_selected_excel_generation_status(self, status):
        table = self.current_table_name()
        if table != "excel_generation_plan":
            messagebox.showwarning("提示", "请先切换到 excel_generation_plan 表，并选择需要修改状态的 Excel 生成计划。")
            return
        ids = self._selected_ids_from_tree("excel_generation_plan")
        if not ids:
            messagebox.showwarning("提示", "没有选中任何 Excel 生成计划。")
            return
        marks = ",".join(["?"] * len(ids))
        self.db = DBManager(self.db_var.get())
        with self.db.connect() as conn:
            conn.execute(f"UPDATE excel_generation_plan SET status=?, updated_at=? WHERE excel_gen_id IN ({marks})", [status, now_str()] + list(ids))
            conn.commit()
        self.log(f"已将 {len(ids)} 条 excel_generation_plan 状态改为：{status}")
        self.refresh_table("excel_generation_plan")

    def execute_excel_template_generation(self):
        output_dir = self.output_var.get().strip()
        if not output_dir:
            messagebox.showwarning("提示", "请先选择输出目录。")
            return
        if not messagebox.askyesno("确认", "将执行 status=已确认 的 excel_generation_plan：复制Excel模板并生成新文件，不覆盖模板。\n是否继续？"):
            return
        self.db = DBManager(self.db_var.get())
        self.db.init_db()
        def task():
            generator = ExcelTemplateGenerator(self.db, self.log)
            generator.execute_confirmed(default_output_dir=output_dir)
        self.run_worker(task, after=lambda: self.refresh_table("excel_generation_plan"))

    def rewrite_confirmed(self):
        output_dir = self.output_var.get().strip()
        if not output_dir:
            messagebox.showwarning("提示", "请先选择输出目录。")
            return

        if not messagebox.askyesno(
            "确认",
            "将会把“已确认”的替换计划回写到副本目录，不直接覆盖原始文件。\n是否继续？"
        ):
            return

        self.db = DBManager(self.db_var.get())
        self.db.init_db()

        def task():
            rewriter = WordRewriter(self.db, self.log)
            rewriter.rewrite_confirmed_to_copies(output_dir)

        self.run_worker(task, after=lambda: self.refresh_table("replace_plan"))

    def current_table_name(self):
        tab_id = self.notebook.select()
        return self.notebook.tab(tab_id, "text")

    def refresh_current_table(self):
        self.refresh_table(self.current_table_name())

    def refresh_table(self, table):
        self.db = DBManager(self.db_var.get())
        try:
            limit = int(self.limit_var.get())
        except Exception:
            limit = 500

        try:
            rows = self.db.query_preview(table, limit=limit)
        except Exception as e:
            self.log(f"刷新 {table} 失败：{short_error(e)}")
            return

        tree = self.tables[table]
        tree.delete(*tree.get_children())

        # 即使表中没有数据，也要从 SQLite schema / 固定配置读取列名并显示。
        if rows:
            cols = list(rows[0].keys())
        else:
            try:
                cols = self.db.get_table_columns(table)
            except Exception:
                cols = default_columns_for_table(table)

        tree["columns"] = cols

        if not cols:
            self.log(f"表 {table} 暂无列信息，请先点击“初始化数据库”。")
            return

        for c in cols:
            # 表头显示中文 + 英文字段；真实 column id 仍然是英文，避免影响程序内部逻辑。
            tree.heading(c, text=cn_heading_text(c, show_english=True))
            width = 150
            if c in ["raw_text", "norm_text", "old_text", "new_text", "field_value", "default_value", "error", "note", "location_json", "extra_json", "conflict_info", "missing_fields"]:
                width = 260
            if c in ["file_path", "output_path", "template_path"]:
                width = 360
            tree.column(c, width=width, anchor="w")

        for r in rows:
            values = []
            for c in cols:
                v = r.get(c, "")
                if v is None:
                    v = ""
                v = str(v).replace("\n", "\\n")
                if len(v) > 300:
                    v = v[:300] + "..."
                values.append(v)
            tree.insert("", "end", values=values)

        self.log(f"已刷新表：{table}，显示 {len(rows)} 行。")

    def _id_col_for_table(self, table):
        return {
            "documents": "doc_id",
            "content_blocks": "block_id",
            "media_blocks": "media_id",
            "old_new_map": "map_id",
            "replace_rules": "rule_id",
            "replace_plan": "plan_id",
            "replace_log": "log_id",
            "template_docs": "template_id",
            "template_fields": "field_id",
            "generation_data": "row_id",
            "generation_plan": "gen_id",
            "generation_field_plan": "item_id",
            "generation_log": "log_id",
        }.get(table)

    def _tree_drag_start(self, event):
        """
        Treeview 鼠标拖动多选起点。
        不返回 "break"，保留 Treeview 原生单击/双击/焦点行为。
        """
        tree = event.widget
        try:
            item = tree.identify_row(event.y)
            if item:
                tree._drag_start_item = item
                tree._drag_last_item = item
                # 先选中起点。后续拖动时会选中连续范围。
                tree.selection_set(item)
                tree.focus(item)
        except Exception:
            pass

    def _tree_drag_select(self, event):
        """
        Treeview 鼠标拖动多选。
        选中从起点到当前鼠标所在行之间的所有可见行。
        """
        tree = event.widget
        try:
            start = getattr(tree, "_drag_start_item", None)
            cur = tree.identify_row(event.y)
            if not start or not cur:
                return

            if getattr(tree, "_drag_last_item", None) == cur:
                return
            tree._drag_last_item = cur

            children = list(tree.get_children(""))
            if start not in children or cur not in children:
                return

            i1 = children.index(start)
            i2 = children.index(cur)
            lo, hi = sorted((i1, i2))
            tree.selection_set(children[lo:hi + 1])
            tree.focus(cur)

            # 简单自动滚动：拖到表格顶部/底部附近时滚动一点。
            height = tree.winfo_height()
            if event.y < 20:
                tree.yview_scroll(-1, "units")
            elif event.y > height - 20:
                tree.yview_scroll(1, "units")
        except Exception:
            pass

    def _tree_drag_end(self, event):
        """Treeview 鼠标拖动多选结束。"""
        tree = event.widget
        try:
            tree._drag_last_item = None
        except Exception:
            pass

    def show_cell_detail(self, event=None):
        """
        双击打开完整行详情，并允许手动修改保存到 SQLite。
        使用 JSON 编辑模式，避免 Treeview 中被截断的文本参与保存。
        """
        table = self.current_table_name()
        tree = self.tables[table]
        item = tree.focus()
        if not item:
            return

        cols = list(tree["columns"])
        id_col = self._id_col_for_table(table)
        if not id_col or id_col not in cols:
            messagebox.showwarning("提示", "当前表没有可编辑主键。")
            return

        values = tree.item(item, "values")
        id_idx = cols.index(id_col)
        try:
            id_value = int(values[id_idx])
        except Exception:
            messagebox.showerror("错误", "无法读取当前行主键。")
            return

        self.db = DBManager(self.db_var.get())
        try:
            row_data = self.db.get_row_by_id(table, id_col, id_value)
        except Exception as e:
            messagebox.showerror("读取失败", str(e))
            return

        if not row_data:
            messagebox.showwarning("提示", "该行数据已不存在。")
            return

        win = tk.Toplevel(self)
        win.title(f"编辑 {table} - {cn_detail_label(id_col)}={id_value}")
        win.geometry("900x700")
        win.rowconfigure(0, weight=1)
        win.columnconfigure(0, weight=1)

        txt = tk.Text(win, wrap="none")
        txt.grid(row=0, column=0, sticky="nsew")

        yscroll = ttk.Scrollbar(win, orient="vertical", command=txt.yview)
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll = ttk.Scrollbar(win, orient="horizontal", command=txt.xview)
        xscroll.grid(row=1, column=0, sticky="ew")
        txt.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)

        txt.insert("1.0", json.dumps(row_data, ensure_ascii=False, indent=2))

        btns = ttk.Frame(win)
        btns.grid(row=2, column=0, columnspan=2, sticky="e", padx=8, pady=8)

        ttk.Label(
            btns,
            text=f"提示：表头已中文化；JSON 键仍为英文字段，可修改值后保存；主键 {cn_detail_label(id_col)} 不会被更新。",
            foreground="#555"
        ).pack(side="left", padx=8)

        def save_json():
            try:
                edited = json.loads(txt.get("1.0", "end").strip())
                if not isinstance(edited, dict):
                    raise ValueError("JSON 顶层必须是对象。")
                self.db.update_row_by_id(table, id_col, id_value, edited)
                self.log(f"已手动保存 {table}: {id_col}={id_value}")
                self.refresh_table(table)
                win.destroy()
            except Exception as e:
                messagebox.showerror("保存失败", str(e))

        def show_column_help():
            help_win = tk.Toplevel(win)
            help_win.title(f"字段中文对照 - {table}")
            help_win.geometry("650x520")
            help_txt = tk.Text(help_win, wrap="word")
            help_txt.pack(fill="both", expand=True)
            lines = []
            for col in cols:
                lines.append(f"{cn_col_name(col)}	{col}")
            help_txt.insert("1.0", "中文字段\t英文字段\n" + "-" * 60 + "\n" + "".join(lines))

        ttk.Button(btns, text="字段中文对照", command=show_column_help).pack(side="left", padx=4)
        ttk.Button(btns, text="保存到 SQLite", command=save_json).pack(side="left", padx=4)
        ttk.Button(btns, text="关闭", command=win.destroy).pack(side="left", padx=4)

    def add_rule_dialog(self):
        RuleDialog(self, self.db_var.get(), on_saved=lambda: self.refresh_table("replace_rules"))

    def add_old_new_map_dialog(self):
        OldNewMapDialog(self, self.db_var.get(), on_saved=lambda: self.refresh_table("old_new_map"))

    def _selected_ids_from_tree(self, table):
        tree = self.tables[table]
        cols = list(tree["columns"])
        if not cols:
            return []
        id_col = {
            "old_new_map": "map_id",
            "replace_rules": "rule_id",
            "replace_plan": "plan_id",
            "template_docs": "template_id",
            "template_fields": "field_id",
            "generation_data": "row_id",
            "generation_plan": "gen_id",
            "generation_field_plan": "item_id",
            "excel_generation_plan": "excel_gen_id",
        }.get(table)
        if id_col not in cols:
            return []
        id_idx = cols.index(id_col)
        ids = []
        for item in tree.selection():
            vals = tree.item(item, "values")
            try:
                ids.append(int(vals[id_idx]))
            except Exception:
                pass
        return ids


    def set_selected_generation_status(self, status):
        table = self.current_table_name()
        if table != "generation_plan":
            messagebox.showwarning("提示", "请先切换到 generation_plan 表，并选择需要修改状态的生成计划。")
            return
        ids = self._selected_ids_from_tree("generation_plan")
        if not ids:
            messagebox.showwarning("提示", "没有选中任何生成计划。")
            return
        marks = ",".join(["?"] * len(ids))
        self.db = DBManager(self.db_var.get())
        with self.db.connect() as conn:
            conn.execute(
                f"UPDATE generation_plan SET status=?, updated_at=? WHERE gen_id IN ({marks})",
                [status, now_str()] + list(ids)
            )
            conn.commit()
        self.log(f"已将 {len(ids)} 条 generation_plan 状态改为：{status}")
        self.refresh_table("generation_plan")

    def set_selected_any_plan_pending(self):
        table = self.current_table_name()
        if table == "replace_plan":
            self.set_selected_plan_status("待确认")
        elif table == "generation_plan":
            self.set_selected_generation_status("待确认")
        else:
            messagebox.showwarning("提示", "请切换到 replace_plan 或 generation_plan 后再操作。")

    def set_selected_plan_status(self, status):
        table = self.current_table_name()
        if table != "replace_plan":
            messagebox.showwarning("提示", "请先切换到 replace_plan 表，并选择需要修改状态的计划。")
            return
        ids = self._selected_ids_from_tree("replace_plan")
        if not ids:
            messagebox.showwarning("提示", "没有选中任何计划。")
            return
        self.db = DBManager(self.db_var.get())
        self.db.update_plan_status(ids, status)
        self.log(f"已将 {len(ids)} 条计划状态改为：{status}")
        self.refresh_table("replace_plan")

    def delete_selected_rows(self):
        table = self.current_table_name()
        if table not in ("generation_plan", "excel_generation_plan"):
            messagebox.showwarning("提示", "当前只允许删除 generation_plan 或 excel_generation_plan 中的生成计划。")
            return

        ids = self._selected_ids_from_tree(table)
        if not ids:
            messagebox.showwarning("提示", "没有选中任何生成计划。")
            return

        id_col = "gen_id" if table == "generation_plan" else "excel_gen_id"
        child_table = "generation_field_plan" if table == "generation_plan" else "excel_generation_field_plan"
        if not messagebox.askyesno(
            "确认删除",
            f"确定删除 {table} 中选中的 {len(ids)} 条生成计划吗？\n"
            f"对应的 {child_table} 会因外键级联一并删除。"
        ):
            return

        self.db = DBManager(self.db_var.get())
        self.db.delete_selected_ids(table, id_col, ids)
        self.log(f"已删除 {table}：{len(ids)} 行")
        self.refresh_table(table)


class OldNewMapDialog(tk.Toplevel):
    def __init__(self, master, db_path, on_saved=None):
        super().__init__(master)
        self.title("新增旧新映射")
        self.geometry("660x600")
        self.db = DBManager(db_path)
        self.on_saved = on_saved

        self.vars = {
            "enabled": tk.IntVar(value=1),
            "priority": tk.IntVar(value=100),
            "group_name": tk.StringVar(value="default"),
            "old_value": tk.StringVar(value=""),
            "new_value": tk.StringVar(value=""),
            "match_mode": tk.StringVar(value="contains"),
            "replace_mode": tk.StringVar(value="partial"),
            "scope": tk.StringVar(value="any"),
            "file_match": tk.StringVar(value=""),
            "table_match": tk.StringVar(value=""),
            "row_match": tk.StringVar(value=""),
            "col_match": tk.StringVar(value=""),
            "context_required": tk.StringVar(value=""),
            "source_key": tk.StringVar(value=""),
            "remark": tk.StringVar(value=""),
        }

        self._build()

    def _build(self):
        frm = ttk.Frame(self)
        frm.pack(fill="both", expand=True, padx=10, pady=10)
        frm.columnconfigure(1, weight=1)

        row = 0
        ttk.Checkbutton(frm, text="启用", variable=self.vars["enabled"]).grid(row=row, column=1, sticky="w")
        row += 1

        self._entry(frm, row, "优先级：", "priority"); row += 1
        self._entry(frm, row, "批次 group_name：", "group_name"); row += 1
        self._entry(frm, row, "旧值 old_value：", "old_value"); row += 1
        self._entry(frm, row, "新值 new_value：", "new_value"); row += 1

        ttk.Label(frm, text="匹配方式：").grid(row=row, column=0, sticky="w", pady=4)
        ttk.Combobox(
            frm, textvariable=self.vars["match_mode"],
            values=["contains", "exact", "regex", "fuzzy"], state="readonly"
        ).grid(row=row, column=1, sticky="ew", pady=4)
        row += 1

        ttk.Label(frm, text="替换方式：").grid(row=row, column=0, sticky="w", pady=4)
        ttk.Combobox(
            frm, textvariable=self.vars["replace_mode"],
            values=["partial", "full"], state="readonly"
        ).grid(row=row, column=1, sticky="ew", pady=4)
        row += 1

        ttk.Label(frm, text="作用范围：").grid(row=row, column=0, sticky="w", pady=4)
        ttk.Combobox(
            frm, textvariable=self.vars["scope"],
            values=["any", "paragraph", "table_cell", "shape_text", "content_control", "bookmark", "field"],
            state="readonly"
        ).grid(row=row, column=1, sticky="ew", pady=4)
        row += 1

        self._entry(frm, row, "文件名包含：", "file_match"); row += 1
        self._entry(frm, row, "表格号：", "table_match"); row += 1
        self._entry(frm, row, "行号：", "row_match"); row += 1
        self._entry(frm, row, "列号：", "col_match"); row += 1
        self._entry(frm, row, "必须包含上下文：", "context_required"); row += 1
        self._entry(frm, row, "来源标识 source_key：", "source_key"); row += 1
        self._entry(frm, row, "备注：", "remark"); row += 1

        tips = (
            "说明：\n"
            "1. 这张表适合由外部 SQL 批量写入 old_value/new_value。\n"
            "2. 点击“旧新映射→生成计划”后，会扫描 content_blocks 并生成 replace_plan。\n"
            "3. group_name 用于批次切换；留空生成全部启用映射。\n"
            "4. 优先级越小越先匹配；建议长字符串优先、短字符串靠后。"
        )
        ttk.Label(frm, text=tips, foreground="#555").grid(row=row, column=0, columnspan=2, sticky="w", pady=10)
        row += 1

        btns = ttk.Frame(frm)
        btns.grid(row=row, column=0, columnspan=2, sticky="e")
        ttk.Button(btns, text="保存", command=self.save).pack(side="left", padx=4)
        ttk.Button(btns, text="取消", command=self.destroy).pack(side="left", padx=4)

    def _entry(self, frm, row, label, key):
        ttk.Label(frm, text=label).grid(row=row, column=0, sticky="w", pady=4)
        ttk.Entry(frm, textvariable=self.vars[key]).grid(row=row, column=1, sticky="ew", pady=4)

    def save(self):
        if not self.vars["old_value"].get():
            messagebox.showwarning("提示", "old_value 不能为空。")
            return
        if not self.vars["new_value"].get():
            messagebox.showwarning("提示", "new_value 不能为空。")
            return

        item = {k: v.get() for k, v in self.vars.items()}
        try:
            self.db.init_db()
            self.db.add_old_new_map(item)
            if self.on_saved:
                self.on_saved()
            self.destroy()
        except Exception as e:
            messagebox.showerror("保存失败", str(e))


class RuleDialog(tk.Toplevel):
    def __init__(self, master, db_path, on_saved=None):
        super().__init__(master)
        self.title("新增替换规则")
        self.geometry("620x520")
        self.db = DBManager(db_path)
        self.on_saved = on_saved

        self.vars = {
            "enabled": tk.IntVar(value=1),
            "priority": tk.IntVar(value=100),
            "scope": tk.StringVar(value="any"),
            "file_match": tk.StringVar(value=""),
            "table_match": tk.StringVar(value=""),
            "row_match": tk.StringVar(value=""),
            "col_match": tk.StringVar(value=""),
            "match_mode": tk.StringVar(value="contains"),
            "old_value": tk.StringVar(value=""),
            "new_value": tk.StringVar(value=""),
            "context_required": tk.StringVar(value=""),
            "replace_mode": tk.StringVar(value="partial"),
            "remark": tk.StringVar(value=""),
        }

        self._build()

    def _build(self):
        frm = ttk.Frame(self)
        frm.pack(fill="both", expand=True, padx=10, pady=10)
        frm.columnconfigure(1, weight=1)

        row = 0
        ttk.Checkbutton(frm, text="启用", variable=self.vars["enabled"]).grid(row=row, column=1, sticky="w")
        row += 1

        self._entry(frm, row, "优先级：", "priority")
        row += 1

        ttk.Label(frm, text="作用范围：").grid(row=row, column=0, sticky="w", pady=4)
        ttk.Combobox(
            frm,
            textvariable=self.vars["scope"],
            values=["any", "paragraph", "table_cell", "shape_text", "content_control", "bookmark", "field"],
            state="readonly"
        ).grid(row=row, column=1, sticky="ew", pady=4)
        row += 1

        self._entry(frm, row, "文件名包含：", "file_match")
        row += 1
        self._entry(frm, row, "表格号：", "table_match")
        row += 1
        self._entry(frm, row, "行号：", "row_match")
        row += 1
        self._entry(frm, row, "列号：", "col_match")
        row += 1

        ttk.Label(frm, text="匹配方式：").grid(row=row, column=0, sticky="w", pady=4)
        ttk.Combobox(
            frm,
            textvariable=self.vars["match_mode"],
            values=["contains", "exact", "regex", "fuzzy"],
            state="readonly"
        ).grid(row=row, column=1, sticky="ew", pady=4)
        row += 1

        ttk.Label(frm, text="替换方式：").grid(row=row, column=0, sticky="w", pady=4)
        ttk.Combobox(
            frm,
            textvariable=self.vars["replace_mode"],
            values=["partial", "full"],
            state="readonly"
        ).grid(row=row, column=1, sticky="ew", pady=4)
        row += 1

        self._entry(frm, row, "旧值/正则：", "old_value")
        row += 1
        self._entry(frm, row, "新值：", "new_value")
        row += 1
        self._entry(frm, row, "必须包含上下文：", "context_required")
        row += 1
        self._entry(frm, row, "备注：", "remark")
        row += 1

        tips = (
            "说明：\n"
            "1. contains：旧值在原文中出现时，默认局部替换。\n"
            "2. exact：规范化后完全相等。\n"
            "3. regex：旧值作为 Python 正则表达式。\n"
            "4. full：将整个内容块替换为新值；partial：只替换命中部分。\n"
            "5. 表格号/行号/列号留空表示不限制。"
        )
        ttk.Label(frm, text=tips, foreground="#555").grid(row=row, column=0, columnspan=2, sticky="w", pady=10)
        row += 1

        btns = ttk.Frame(frm)
        btns.grid(row=row, column=0, columnspan=2, sticky="e")
        ttk.Button(btns, text="保存", command=self.save).pack(side="left", padx=4)
        ttk.Button(btns, text="取消", command=self.destroy).pack(side="left", padx=4)

    def _entry(self, frm, row, label, key):
        ttk.Label(frm, text=label).grid(row=row, column=0, sticky="w", pady=4)
        ttk.Entry(frm, textvariable=self.vars[key]).grid(row=row, column=1, sticky="ew", pady=4)

    def save(self):
        old = self.vars["old_value"].get()
        if not old:
            messagebox.showwarning("提示", "旧值/正则不能为空。")
            return

        rule = {}
        for k, v in self.vars.items():
            rule[k] = v.get()

        try:
            self.db.init_db()
            self.db.add_rule(rule)
            if self.on_saved:
                self.on_saved()
            self.destroy()
        except Exception as e:
            messagebox.showerror("保存失败", str(e))


def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
