# -*- coding: utf-8 -*-
import json
import re
import shutil
import tempfile
import time
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

PLUGIN_INFO = {
    "id": "word_excel_write_from_table_v2",
    "name": "Word/Excel按数据写入V2",
    "version": "1.0.0",
    "api_version": "1.0",
    "category": "文件处理",
    "description": "按输入表数据直接写回 Word/Excel（无确认直写，默认预览保护）。",
    "input_type": "table",
    "output_type": "table",
    "danger_level": "file_write",
}

OUTPUT_HEADERS = [
    "source_file",
    "target_file",
    "target_file_name",
    "engine",
    "op_total",
    "applied",
    "skipped",
    "copy_status",
    "write_status",
    "status",
    "error",
]


def get_parameter_schema():
    return [
        {
            "name": "write_engine",
            "label": "写入引擎",
            "type": "select",
            "choices": ["win32", "zip_xml"],
            "default": "win32",
            "help": "win32：Office COM 写入；zip_xml：docx 直接 XML 写入，xlsx/xlsm 用 openpyxl 写入。",
        },
        {
            "name": "preview_write_files",
            "label": "预览模式仍写入文件",
            "type": "bool",
            "default": False,
            "help": "默认关闭：预览只模拟，不改文件。",
        },
        {
            "name": "win32_reuse_app",
            "label": "win32复用Office进程",
            "type": "bool",
            "default": True,
            "help": "开启后，本节点一次运行内复用同一个 Word/Excel 进程处理多个文件。",
        },
        {
            "name": "win32_open_retries",
            "label": "win32打开重试次数",
            "type": "number",
            "default": 5,
        },
        {
            "name": "win32_retry_interval_ms",
            "label": "win32重试间隔(ms)",
            "type": "number",
            "default": 300,
        },
        {
            "name": "win32_close_settle_ms",
            "label": "win32关闭等待(ms)",
            "type": "number",
            "default": 200,
        },
        {
            "name": "word_text_write_mode",
            "label": "Word文字写入方式",
            "type": "select",
            "choices": ["保留原格式，仅改文字值", "整段覆盖"],
            "default": "保留原格式，仅改文字值",
            "help": "win32 写入 Word 时默认尽量保留原有字体/字号/颜色等格式；整段覆盖为旧行为。",
        },
        {
            "name": "error_policy",
            "label": "失败处理",
            "type": "select",
            "choices": ["继续并记录失败", "遇错停止"],
            "default": "继续并记录失败",
        },
        {
            "name": "allow_empty_text_write",
            "label": "允许写入空文本",
            "type": "bool",
            "default": False,
            "help": "关闭时，空文本记录会跳过，避免误清空内容。",
        },
        {"name": "path_field", "label": "文件路径字段", "type": "field_select", "default": "source_file"},
        {"name": "target_path_field", "label": "新文件路径字段", "type": "field_select", "default": "target_file"},
        {
            "name": "target_missing_policy",
            "label": "目标不存在时",
            "type": "select",
            "choices": ["从源文件复制", "报错"],
            "default": "从源文件复制",
        },
        {
            "name": "target_existing_policy",
            "label": "目标已存在时",
            "type": "select",
            "choices": ["直接写入", "覆盖为源文件后写入", "跳过", "报错"],
            "default": "直接写入",
        },
        {
            "name": "same_path_policy",
            "label": "新旧路径相同时",
            "type": "select",
            "choices": ["修改源文件", "跳过", "报错"],
            "default": "修改源文件",
        },
        {
            "name": "create_parent_dirs",
            "label": "自动创建目标目录",
            "type": "bool",
            "default": True,
        },
        {"name": "block_type_field", "label": "类型字段", "type": "field_select", "default": "block_type"},
        {"name": "sheet_name_field", "label": "sheet/表名字段", "type": "field_select", "default": "sheet_name"},
        {"name": "row_index_field", "label": "行号字段", "type": "field_select", "default": "row_index"},
        {"name": "col_index_field", "label": "列号字段", "type": "field_select", "default": "col_index"},
        {"name": "cell_address_field", "label": "地址字段", "type": "field_select", "default": "cell_address"},
        {"name": "value_field", "label": "写入值字段", "type": "field_select", "default": "text"},
        {"name": "meta_json_field", "label": "meta字段", "type": "field_select", "default": "meta_json"},
    ]


def get_output_schema(params=None, input_data=None, context=None):
    return {
        "type": "table",
        "headers": list(OUTPUT_HEADERS),
        "rows": [],
        "meta": {"plugin": PLUGIN_INFO["id"], "lazy_schema": True},
    }


def _as_text(v):
    return "" if v is None else str(v).strip()


def _safe_cell(row, idx):
    return row[idx] if idx < len(row) else ""


def _resolve_path(path_text, context):
    p = Path(path_text)
    if p.is_absolute():
        return p
    app_dir = Path(context.get("app_dir", "."))
    return (app_dir / p).resolve()


def _same_file_path(a, b):
    try:
        return str(Path(a).resolve()).lower() == str(Path(b).resolve()).lower()
    except Exception:
        return str(a).strip().lower() == str(b).strip().lower()


def _to_int_or_none(v):
    s = _as_text(v)
    if s == "":
        return None
    try:
        return int(s, 10)
    except Exception:
        try:
            return int(s, 0)
        except Exception:
            return None


def _to_int_with_default(v, default, min_value=None):
    n = _to_int_or_none(v)
    if n is None:
        n = int(default)
    if min_value is not None and n < min_value:
        n = int(min_value)
    return n


def _parse_table_index(sheet_name, meta_json_text):
    m = re.search(r"table_(\d+)", _as_text(sheet_name), flags=re.IGNORECASE)
    if m:
        return int(m.group(1))
    try:
        meta = json.loads(meta_json_text) if _as_text(meta_json_text) else {}
        v = meta.get("table_index")
        vi = _to_int_or_none(v)
        if vi and vi > 0:
            return vi
    except Exception:
        pass
    return None


def _parse_rc_from_address(addr_text):
    s = _as_text(addr_text).upper().replace("$", "")
    if not s:
        return None, None
    m = re.match(r"^R(\d+)C(\d+)$", s)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.match(r"^([A-Z]+)(\d+)$", s)
    if not m:
        return None, None
    letters = m.group(1)
    row = int(m.group(2))
    col = 0
    for ch in letters:
        col = col * 26 + (ord(ch) - ord("A") + 1)
    return row, col


def _excel_addr_from_rc(row, col):
    if not row or not col:
        return ""
    n = int(col)
    out = []
    while n > 0:
        n, rem = divmod(n - 1, 26)
        out.append(chr(ord("A") + rem))
    return "".join(reversed(out)) + str(int(row))


def _log(level, message, obj="", tb=""):
    return {"level": str(level).upper(), "object": _as_text(obj), "message": _as_text(message), "traceback": _as_text(tb)}


def _progress(context, current=None, total=None, message="", **extra):
    reporter = context.get("report_progress")
    if callable(reporter):
        try:
            reporter(current, total, message, **extra)
            return
        except Exception:
            pass
    callback = context.get("progress_callback")
    if callable(callback):
        msg = {
            "type": "node_progress",
            "node_name": context.get("node_name", "插件节点"),
            "plugin_id": context.get("plugin_id", PLUGIN_INFO["id"]),
            "current": current,
            "total": total,
            "message": message or "处理中",
        }
        msg.update(extra)
        try:
            callback(msg)
        except Exception:
            pass


def _short_detail_text(text, limit=90):
    text = re.sub(r"\s+", " ", _as_text(text))
    if len(text) > limit:
        return text[:limit] + "..."
    return text


def _op_location(op):
    sheet = _as_text(op.get("sheet_name"))
    row = _as_text(op.get("row_index"))
    col = _as_text(op.get("col_index"))
    addr = _as_text(op.get("cell_address"))
    if row and col:
        loc = f"{sheet} R{row}C{col}" if sheet else f"R{row}C{col}"
    elif addr:
        loc = f"{sheet} {addr}" if sheet else addr
    elif row:
        loc = f"{sheet} 段落{row}" if sheet else f"段落{row}"
    else:
        loc = sheet or _as_text(op.get("block_type")) or "写入位置"
    return loc.strip()


def _op_detail_message(file_path, op):
    return f"写入中：{Path(file_path).name} {_op_location(op)}：{_short_detail_text(op.get('value', ''))}"


def _op_progress(context, current, total, file_path, op, op_no):
    if not context:
        return
    if op_no != 1 and op_no % 20 != 0:
        return
    _progress(
        context,
        current,
        total,
        "写入中",
        stage="op_write",
        object=str(file_path),
        detail_message=_op_detail_message(file_path, op),
    )


def _check_cancel(context):
    ev = context.get("cancel_event")
    return bool(ev is not None and hasattr(ev, "is_set") and ev.is_set())


def validate_params(params, input_data, context):
    p = dict(params or {})
    headers = list(input_data.get("headers", []))

    path_field = _as_text(p.get("path_field", "source_file")) or "source_file"
    target_path_field = _as_text(p.get("target_path_field", "target_file")) or "target_file"
    value_field = _as_text(p.get("value_field", "text")) or "text"
    write_engine = _as_text(p.get("write_engine", "win32")).lower() or "win32"

    if path_field not in headers:
        return False, f"文件路径字段不存在：{path_field}"
    if target_path_field and target_path_field not in headers:
        # 兼容旧工作流：默认 target_file 不存在时自动回退到 source_file。
        if target_path_field != "target_file":
            return False, f"新文件路径字段不存在：{target_path_field}"
    if value_field not in headers:
        return False, f"写入值字段不存在：{value_field}"
    if write_engine not in ("win32", "zip_xml"):
        return False, f"不支持的写入引擎：{write_engine}"
    return True, ""


def _collect_ops(input_data, params, context):
    headers = list(input_data.get("headers", []))
    rows = [list(r) for r in input_data.get("rows", [])]
    idx = {name: headers.index(name) for name in headers}

    path_field = _as_text(params.get("path_field", "source_file")) or "source_file"
    target_path_field = _as_text(params.get("target_path_field", "target_file")) or "target_file"
    block_type_field = _as_text(params.get("block_type_field", "block_type")) or "block_type"
    sheet_name_field = _as_text(params.get("sheet_name_field", "sheet_name")) or "sheet_name"
    row_index_field = _as_text(params.get("row_index_field", "row_index")) or "row_index"
    col_index_field = _as_text(params.get("col_index_field", "col_index")) or "col_index"
    cell_address_field = _as_text(params.get("cell_address_field", "cell_address")) or "cell_address"
    value_field = _as_text(params.get("value_field", "text")) or "text"
    meta_json_field = _as_text(params.get("meta_json_field", "meta_json")) or "meta_json"
    allow_empty = bool(params.get("allow_empty_text_write", False))

    def cell_by_field(row, field_name):
        if field_name in idx:
            return _safe_cell(row, idx[field_name])
        return ""

    grouped = {}
    skipped_no_path = 0
    skipped_empty_value = 0

    for row_no, row in enumerate(rows, start=1):
        raw_path = _as_text(cell_by_field(row, path_field))
        if raw_path == "":
            skipped_no_path += 1
            continue
        raw_target = _as_text(cell_by_field(row, target_path_field))
        if raw_target == "":
            raw_target = raw_path
        value_text = str(cell_by_field(row, value_field) or "")
        if (not allow_empty) and (value_text == ""):
            skipped_empty_value += 1
            continue

        source_path = _resolve_path(raw_path, context)
        target_path = _resolve_path(raw_target, context)
        op = {
            "source_row": row_no,
            "source_path": source_path,
            "target_path": target_path,
            "block_type": _as_text(cell_by_field(row, block_type_field)).lower(),
            "sheet_name": _as_text(cell_by_field(row, sheet_name_field)),
            "row_index": _as_text(cell_by_field(row, row_index_field)),
            "col_index": _as_text(cell_by_field(row, col_index_field)),
            "cell_address": _as_text(cell_by_field(row, cell_address_field)),
            "value": value_text,
            "meta_json": _as_text(cell_by_field(row, meta_json_field)),
        }
        key = str(target_path).lower()
        group = grouped.setdefault(key, {"source_path": source_path, "target_path": target_path, "ops": [], "source_conflict": False})
        if not _same_file_path(group["source_path"], source_path):
            group["source_conflict"] = True
        group["ops"].append(op)

    return grouped, {
        "input_rows": len(rows),
        "skipped_no_path": skipped_no_path,
        "skipped_empty_value": skipped_empty_value,
    }


def _word_preserve_format_enabled(context):
    params = (context or {}).get("params") or {}
    mode = _as_text(params.get("word_text_write_mode", "保留原格式，仅改文字值")) or "保留原格式，仅改文字值"
    return mode != "整段覆盖"


def _word_body_range(range_obj):
    start = int(range_obj.Start)
    end = int(range_obj.End)
    if end > start:
        text = str(range_obj.Text)
        while end > start and text.endswith(("\r\x07", "\r", "\x07")):
            end -= 1
            text = text[:-1]
    return range_obj.Document.Range(start, max(start, end))


def _word_capture_font(range_obj):
    try:
        body = _word_body_range(range_obj)
        if int(body.End) > int(body.Start):
            sample = body.Document.Range(int(body.Start), int(body.Start) + 1)
        else:
            sample = body
        font = sample.Font
        return {
            "Name": font.Name,
            "NameFarEast": getattr(font, "NameFarEast", ""),
            "Size": font.Size,
            "Bold": font.Bold,
            "Italic": font.Italic,
            "Underline": font.Underline,
            "Color": font.Color,
        }
    except Exception:
        return {}


def _word_apply_font(range_obj, font_info):
    if not font_info:
        return
    try:
        font = range_obj.Font
        for key, value in font_info.items():
            if value is None or value == 9999999:
                continue
            try:
                setattr(font, key, value)
            except Exception:
                pass
    except Exception:
        pass


def _word_write_text_preserve_format(range_obj, value):
    text = str(value if value is not None else "")
    original_text = str(range_obj.Text)
    font_info = _word_capture_font(range_obj)
    is_table_cell = original_text.endswith("\r\x07")
    if is_table_cell:
        range_obj.Text = text + "\r\x07"
        new_body = _word_body_range(range_obj)
        _word_apply_font(new_body, font_info)
        return
    body = _word_body_range(range_obj)
    start = int(body.Start)
    body.Text = text
    if text:
        new_body = range_obj.Document.Range(start, start + len(text))
        _word_apply_font(new_body, font_info)


def _word_write_visible_text(range_obj, value, preserve_format=True):
    if preserve_format:
        _word_write_text_preserve_format(range_obj, value)
    else:
        body = _word_body_range(range_obj)
        body.Text = str(value if value is not None else "")


def _write_word_via_com(file_path, ops, context=None, progress_current=None, progress_total=None):
    try:
        import pythoncom
        import win32com.client
    except Exception as exc:
        raise RuntimeError("win32 写入 Word 需要 pywin32 + Word") from exc

    word = None
    doc = None
    applied = 0
    skipped = 0
    logs = []
    preserve_word_format = _word_preserve_format_enabled(context)
    try:
        pythoncom.CoInitialize()
        word = win32com.client.DispatchEx("Word.Application")
        word.Visible = False
        word.DisplayAlerts = 0
        doc = word.Documents.Open(str(file_path), ReadOnly=False, AddToRecentFiles=False, ConfirmConversions=False, Visible=False)

        for op_no, op in enumerate(ops, start=1):
            _op_progress(context, progress_current, progress_total, file_path, op, op_no)
            bt = _as_text(op.get("block_type", "")).lower()
            try:
                if bt == "word_paragraph":
                    pi = _to_int_or_none(op.get("row_index"))
                    if not pi or pi <= 0:
                        raise ValueError("缺少 paragraph 索引(row_index)")
                    para = doc.Paragraphs(int(pi))
                    _word_write_visible_text(para.Range, op.get("value", ""), preserve_word_format)
                    applied += 1
                elif bt == "word_table_cell":
                    table_idx = _parse_table_index(op.get("sheet_name", ""), op.get("meta_json", ""))
                    if not table_idx:
                        raise ValueError("无法确定表索引（sheet_name 或 meta_json.table_index）")
                    row_i = _to_int_or_none(op.get("row_index"))
                    col_i = _to_int_or_none(op.get("col_index"))
                    if not row_i or not col_i:
                        rr, cc = _parse_rc_from_address(op.get("cell_address", ""))
                        row_i = row_i or rr
                        col_i = col_i or cc
                    if not row_i or not col_i:
                        raise ValueError("缺少单元格行列索引(row_index/col_index/cell_address)")
                    cell = doc.Tables(int(table_idx)).Cell(int(row_i), int(col_i))
                    _word_write_visible_text(cell.Range, op.get("value", ""), preserve_word_format)
                    applied += 1
                else:
                    skipped += 1
                    logs.append(_log("WARNING", f"不支持的 Word block_type，已跳过：{bt}", str(file_path)))
            except Exception as exc:
                skipped += 1
                logs.append(_log("ERROR", f"写入失败(源行{op.get('source_row')})：{exc}", str(file_path)))
        doc.Save()
        return applied, skipped, logs
    finally:
        if doc is not None:
            try:
                doc.Close(True)
            except Exception:
                pass
        if word is not None:
            try:
                word.Quit()
            except Exception:
                pass
        try:
            pythoncom.CoUninitialize()
        except Exception:
            pass


def _write_excel_via_com(file_path, ops, context=None, progress_current=None, progress_total=None):
    try:
        import pythoncom
        import win32com.client
    except Exception as exc:
        raise RuntimeError("win32 写入 Excel 需要 pywin32 + Excel") from exc

    excel = None
    wb = None
    applied = 0
    skipped = 0
    logs = []
    try:
        pythoncom.CoInitialize()
        excel = win32com.client.DispatchEx("Excel.Application")
        excel.Visible = False
        excel.DisplayAlerts = False
        wb = excel.Workbooks.Open(str(file_path), ReadOnly=False, UpdateLinks=0)

        for op_no, op in enumerate(ops, start=1):
            _op_progress(context, progress_current, progress_total, file_path, op, op_no)
            try:
                sheet_name = _as_text(op.get("sheet_name", ""))
                ws = wb.Worksheets(sheet_name) if sheet_name else wb.Worksheets(1)
                row_i = _to_int_or_none(op.get("row_index"))
                col_i = _to_int_or_none(op.get("col_index"))
                addr = _as_text(op.get("cell_address", "")).replace("$", "")
                if row_i and col_i:
                    ws.Cells(int(row_i), int(col_i)).Value = op.get("value", "")
                    applied += 1
                elif addr:
                    ws.Range(addr).Value = op.get("value", "")
                    applied += 1
                else:
                    skipped += 1
                    logs.append(_log("WARNING", f"缺少 Excel 定位(row/col/cell_address)，已跳过，源行{op.get('source_row')}", str(file_path)))
            except Exception as exc:
                skipped += 1
                logs.append(_log("ERROR", f"Excel写入失败(源行{op.get('source_row')})：{exc}", str(file_path)))

        wb.Save()
        return applied, skipped, logs
    finally:
        if wb is not None:
            try:
                wb.Close(SaveChanges=True)
            except Exception:
                pass
        if excel is not None:
            try:
                excel.Quit()
            except Exception:
                pass
        try:
            pythoncom.CoUninitialize()
        except Exception:
            pass


class _Win32OfficeSession:
    def __init__(self, open_retries=5, retry_interval_ms=300, close_settle_ms=200):
        self.open_retries = max(1, int(open_retries or 1))
        self.retry_interval = max(0, int(retry_interval_ms or 0)) / 1000.0
        self.close_settle = max(0, int(close_settle_ms or 0)) / 1000.0
        self.pythoncom = None
        self.win32com_client = None
        self.com_initialized = False
        self.word = None
        self.excel = None

    def _ensure_com(self):
        if self.com_initialized:
            return
        try:
            import pythoncom
            import win32com.client
        except Exception as exc:
            raise RuntimeError("win32 写入需要 pywin32 + Office") from exc
        pythoncom.CoInitialize()
        self.pythoncom = pythoncom
        self.win32com_client = win32com.client
        self.com_initialized = True

    def _word_app(self):
        self._ensure_com()
        if self.word is None:
            self.word = self.win32com_client.DispatchEx("Word.Application")
            self.word.Visible = False
            self.word.DisplayAlerts = 0
        return self.word

    def _excel_app(self):
        self._ensure_com()
        if self.excel is None:
            self.excel = self.win32com_client.DispatchEx("Excel.Application")
            self.excel.Visible = False
            self.excel.DisplayAlerts = False
        return self.excel

    def _open_with_retry(self, opener, file_path):
        last_exc = None
        for attempt in range(1, self.open_retries + 1):
            try:
                return opener()
            except Exception as exc:
                last_exc = exc
                if attempt < self.open_retries and self.retry_interval > 0:
                    time.sleep(self.retry_interval)
        raise RuntimeError(f"打开文件失败，已重试 {self.open_retries} 次：{file_path}；{last_exc}")

    def write_word(self, file_path, ops, context=None, progress_current=None, progress_total=None):
        doc = None
        saved = False
        applied = 0
        skipped = 0
        logs = []
        preserve_word_format = _word_preserve_format_enabled(context)
        try:
            word = self._word_app()
            doc = self._open_with_retry(
                lambda: word.Documents.Open(str(file_path), ReadOnly=False, AddToRecentFiles=False, ConfirmConversions=False, Visible=False),
                file_path,
            )
            for op_no, op in enumerate(ops, start=1):
                _op_progress(context, progress_current, progress_total, file_path, op, op_no)
                bt = _as_text(op.get("block_type", "")).lower()
                try:
                    if bt == "word_paragraph":
                        pi = _to_int_or_none(op.get("row_index"))
                        if not pi or pi <= 0:
                            raise ValueError("缺少 paragraph 索引(row_index)")
                        para = doc.Paragraphs(int(pi))
                        _word_write_visible_text(para.Range, op.get("value", ""), preserve_word_format)
                        applied += 1
                    elif bt == "word_table_cell":
                        table_idx = _parse_table_index(op.get("sheet_name", ""), op.get("meta_json", ""))
                        if not table_idx:
                            raise ValueError("无法确定表索引（sheet_name 或 meta_json.table_index）")
                        row_i = _to_int_or_none(op.get("row_index"))
                        col_i = _to_int_or_none(op.get("col_index"))
                        if not row_i or not col_i:
                            rr, cc = _parse_rc_from_address(op.get("cell_address", ""))
                            row_i = row_i or rr
                            col_i = col_i or cc
                        if not row_i or not col_i:
                            raise ValueError("缺少单元格行列索引(row_index/col_index/cell_address)")
                        cell = doc.Tables(int(table_idx)).Cell(int(row_i), int(col_i))
                        _word_write_visible_text(cell.Range, op.get("value", ""), preserve_word_format)
                        applied += 1
                    else:
                        skipped += 1
                        logs.append(_log("WARNING", f"不支持的 Word block_type，已跳过：{bt}", str(file_path)))
                except Exception as exc:
                    skipped += 1
                    logs.append(_log("ERROR", f"写入失败(源行{op.get('source_row')})：{exc}", str(file_path)))
            doc.Save()
            saved = True
            return applied, skipped, logs
        finally:
            if doc is not None:
                try:
                    doc.Close(SaveChanges=False)
                except Exception:
                    try:
                        doc.Close(False)
                    except Exception:
                        pass
            if saved and self.close_settle > 0:
                time.sleep(self.close_settle)

    def write_excel(self, file_path, ops, context=None, progress_current=None, progress_total=None):
        wb = None
        saved = False
        applied = 0
        skipped = 0
        logs = []
        try:
            excel = self._excel_app()
            wb = self._open_with_retry(
                lambda: excel.Workbooks.Open(str(file_path), ReadOnly=False, UpdateLinks=0),
                file_path,
            )
            for op_no, op in enumerate(ops, start=1):
                _op_progress(context, progress_current, progress_total, file_path, op, op_no)
                try:
                    sheet_name = _as_text(op.get("sheet_name", ""))
                    ws = wb.Worksheets(sheet_name) if sheet_name else wb.Worksheets(1)
                    row_i = _to_int_or_none(op.get("row_index"))
                    col_i = _to_int_or_none(op.get("col_index"))
                    addr = _as_text(op.get("cell_address", "")).replace("$", "")
                    if row_i and col_i:
                        ws.Cells(int(row_i), int(col_i)).Value = op.get("value", "")
                        applied += 1
                    elif addr:
                        ws.Range(addr).Value = op.get("value", "")
                        applied += 1
                    else:
                        skipped += 1
                        logs.append(_log("WARNING", f"缺少 Excel 定位(row/col/cell_address)，已跳过，源行{op.get('source_row')}", str(file_path)))
                except Exception as exc:
                    skipped += 1
                    logs.append(_log("ERROR", f"Excel写入失败(源行{op.get('source_row')})：{exc}", str(file_path)))
            wb.Save()
            saved = True
            return applied, skipped, logs
        finally:
            if wb is not None:
                try:
                    wb.Close(SaveChanges=False)
                except Exception:
                    pass
            if saved and self.close_settle > 0:
                time.sleep(self.close_settle)

    def write_file(self, file_path, ops, context=None, progress_current=None, progress_total=None):
        ext = file_path.suffix.lower()
        if ext in (".doc", ".docx", ".docm"):
            return self.write_word(file_path, ops, context, progress_current, progress_total)
        if ext in (".xls", ".xlsx", ".xlsm"):
            return self.write_excel(file_path, ops, context, progress_current, progress_total)
        raise ValueError(f"win32 不支持的文件类型：{ext}")

    def close(self):
        if self.word is not None:
            try:
                self.word.Quit()
            except Exception:
                pass
            self.word = None
        if self.excel is not None:
            try:
                self.excel.Quit()
            except Exception:
                pass
            self.excel = None
        if self.com_initialized and self.pythoncom is not None:
            try:
                self.pythoncom.CoUninitialize()
            except Exception:
                pass
        self.com_initialized = False


def _set_word_paragraph_text(p_node, text, ns_w):
    for ch in list(p_node):
        p_node.remove(ch)
    r = ET.SubElement(p_node, f"{{{ns_w}}}r")
    t = ET.SubElement(r, f"{{{ns_w}}}t")
    txt = str(text or "")
    if txt.startswith(" ") or txt.endswith(" "):
        t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    t.text = txt


def _write_docx_zip_xml(file_path, ops, context=None, progress_current=None, progress_total=None):
    ns_w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    ns = {"w": ns_w}
    applied = 0
    skipped = 0
    logs = []

    with zipfile.ZipFile(file_path, "r") as zf:
        names = zf.namelist()
        if "word/document.xml" not in names:
            raise RuntimeError("docx 缺少 word/document.xml")
        payload = {name: zf.read(name) for name in names}

    root = ET.fromstring(payload["word/document.xml"])
    body = root.find("w:body", ns)
    if body is None:
        raise RuntimeError("docx 文档 body 不存在")

    body_children = list(body)
    paragraphs = [x for x in body_children if x.tag.split("}")[-1] == "p"]
    tables = [x for x in body_children if x.tag.split("}")[-1] == "tbl"]

    for op_no, op in enumerate(ops, start=1):
        _op_progress(context, progress_current, progress_total, file_path, op, op_no)
        bt = _as_text(op.get("block_type", "")).lower()
        try:
            if bt == "word_paragraph":
                pi = _to_int_or_none(op.get("row_index"))
                if not pi or pi <= 0 or pi > len(paragraphs):
                    raise ValueError(f"paragraph 索引越界：{pi}")
                _set_word_paragraph_text(paragraphs[pi - 1], op.get("value", ""), ns_w)
                applied += 1
            elif bt == "word_table_cell":
                table_idx = _parse_table_index(op.get("sheet_name", ""), op.get("meta_json", ""))
                if not table_idx or table_idx <= 0 or table_idx > len(tables):
                    raise ValueError(f"table 索引越界：{table_idx}")
                row_i = _to_int_or_none(op.get("row_index"))
                col_i = _to_int_or_none(op.get("col_index"))
                if not row_i or not col_i:
                    rr, cc = _parse_rc_from_address(op.get("cell_address", ""))
                    row_i = row_i or rr
                    col_i = col_i or cc
                if not row_i or not col_i:
                    raise ValueError("缺少单元格行列索引")

                tbl = tables[table_idx - 1]
                trs = tbl.findall("./w:tr", ns)
                if row_i <= 0 or row_i > len(trs):
                    raise ValueError(f"行索引越界：{row_i}")
                tcs = trs[row_i - 1].findall("./w:tc", ns)
                if col_i <= 0 or col_i > len(tcs):
                    raise ValueError(f"列索引越界：{col_i}")
                tc = tcs[col_i - 1]
                p = tc.find("./w:p", ns)
                if p is None:
                    p = ET.SubElement(tc, f"{{{ns_w}}}p")
                _set_word_paragraph_text(p, op.get("value", ""), ns_w)
                applied += 1
            else:
                skipped += 1
                logs.append(_log("WARNING", f"不支持的 Word block_type，已跳过：{bt}", str(file_path)))
        except Exception as exc:
            skipped += 1
            logs.append(_log("ERROR", f"写入失败(源行{op.get('source_row')})：{exc}", str(file_path)))

    if applied > 0:
        new_xml = ET.tostring(root, encoding="utf-8", xml_declaration=True)
        tmp_fd = tempfile.NamedTemporaryFile(delete=False, suffix=".docx", dir=str(file_path.parent))
        tmp_path = Path(tmp_fd.name)
        tmp_fd.close()
        try:
            with zipfile.ZipFile(tmp_path, "w", compression=zipfile.ZIP_DEFLATED) as out_zf:
                for name, data in payload.items():
                    if name == "word/document.xml":
                        out_zf.writestr(name, new_xml)
                    else:
                        out_zf.writestr(name, data)
            tmp_path.replace(file_path)
        finally:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except Exception:
                    pass

    return applied, skipped, logs


def _write_excel_openpyxl(file_path, ops, context=None, progress_current=None, progress_total=None):
    try:
        from openpyxl import load_workbook
    except Exception as exc:
        raise RuntimeError("zip_xml 写入 Excel 需要 openpyxl") from exc

    ext = file_path.suffix.lower()
    keep_vba = ext in (".xlsm", ".xltm")
    wb = load_workbook(filename=str(file_path), keep_vba=keep_vba)
    applied = 0
    skipped = 0
    logs = []
    try:
        for op_no, op in enumerate(ops, start=1):
            _op_progress(context, progress_current, progress_total, file_path, op, op_no)
            try:
                sheet_name = _as_text(op.get("sheet_name", ""))
                ws = wb[sheet_name] if sheet_name and sheet_name in wb.sheetnames else wb.worksheets[0]
                row_i = _to_int_or_none(op.get("row_index"))
                col_i = _to_int_or_none(op.get("col_index"))
                addr = _as_text(op.get("cell_address", "")).replace("$", "")
                if (not addr) and row_i and col_i:
                    addr = _excel_addr_from_rc(row_i, col_i)
                if not addr:
                    rr, cc = _parse_rc_from_address(op.get("cell_address", ""))
                    if rr and cc:
                        addr = _excel_addr_from_rc(rr, cc)
                if not addr:
                    skipped += 1
                    logs.append(_log("WARNING", f"缺少 Excel 定位(row/col/cell_address)，已跳过，源行{op.get('source_row')}", str(file_path)))
                    continue
                ws[addr] = op.get("value", "")
                applied += 1
            except Exception as exc:
                skipped += 1
                logs.append(_log("ERROR", f"Excel写入失败(源行{op.get('source_row')})：{exc}", str(file_path)))
        wb.save(str(file_path))
        return applied, skipped, logs
    finally:
        wb.close()


def _write_file(file_path, ops, engine, context=None, progress_current=None, progress_total=None):
    ext = file_path.suffix.lower()
    if engine == "win32":
        if ext in (".doc", ".docx", ".docm"):
            return _write_word_via_com(file_path, ops, context, progress_current, progress_total)
        if ext in (".xls", ".xlsx", ".xlsm"):
            return _write_excel_via_com(file_path, ops, context, progress_current, progress_total)
        raise ValueError(f"win32 不支持的文件类型：{ext}")

    # zip_xml
    if ext == ".doc":
        raise ValueError("zip_xml 不支持 .doc，请改用 win32")
    if ext in (".docx", ".docm"):
        return _write_docx_zip_xml(file_path, ops, context, progress_current, progress_total)
    if ext in (".xlsx", ".xlsm"):
        return _write_excel_openpyxl(file_path, ops, context, progress_current, progress_total)
    if ext == ".xls":
        raise ValueError("zip_xml 不支持 .xls，请改用 win32")
    raise ValueError(f"zip_xml 不支持的文件类型：{ext}")


def _prepare_target_file(source_path, target_path, params, preview_protected):
    missing_policy = _as_text(params.get("target_missing_policy", "从源文件复制")) or "从源文件复制"
    existing_policy = _as_text(params.get("target_existing_policy", "直接写入")) or "直接写入"
    same_policy = _as_text(params.get("same_path_policy", "修改源文件")) or "修改源文件"
    create_dirs = bool(params.get("create_parent_dirs", True))

    same_path = _same_file_path(source_path, target_path)
    source_exists = source_path.exists()
    target_exists = target_path.exists()

    if same_path:
        if same_policy == "跳过":
            return "skip", "新旧路径相同，按设置跳过"
        if same_policy == "报错":
            raise RuntimeError("新旧路径相同，按设置报错")
        if not source_exists:
            raise FileNotFoundError(f"文件不存在：{source_path}")
        return "原地写入", ""

    if not source_exists:
        raise FileNotFoundError(f"源文件不存在：{source_path}")

    if create_dirs and target_path.parent:
        if not preview_protected:
            target_path.parent.mkdir(parents=True, exist_ok=True)

    if target_exists:
        if existing_policy == "跳过":
            return "skip", "目标文件已存在，按设置跳过"
        if existing_policy == "报错":
            raise RuntimeError(f"目标文件已存在：{target_path}")
        if existing_policy == "覆盖为源文件后写入":
            if preview_protected:
                return "预览覆盖复制", ""
            shutil.copy2(str(source_path), str(target_path))
            return "已覆盖复制", ""
        return "目标已存在直接写入", ""

    if missing_policy == "报错":
        raise FileNotFoundError(f"目标文件不存在：{target_path}")
    if preview_protected:
        return "预览复制", ""
    shutil.copy2(str(source_path), str(target_path))
    return "已复制", ""


def run(input_data, params, context):
    p = dict(params or {})
    context = dict(context or {})
    context["params"] = p
    engine = _as_text(p.get("write_engine", "win32")).lower() or "win32"
    error_policy = _as_text(p.get("error_policy", "继续并记录失败"))
    preview_write = bool(p.get("preview_write_files", False))
    is_preview = bool(context.get("is_preview", False))
    win32_reuse_app = bool(p.get("win32_reuse_app", True))
    win32_open_retries = _to_int_with_default(p.get("win32_open_retries", 5), 5, min_value=1)
    win32_retry_interval_ms = _to_int_with_default(p.get("win32_retry_interval_ms", 300), 300, min_value=0)
    win32_close_settle_ms = _to_int_with_default(p.get("win32_close_settle_ms", 200), 200, min_value=0)

    grouped, prep = _collect_ops(input_data, p, context)
    total_files = len(grouped)
    total_ops = sum(len(item["ops"]) for item in grouped.values())
    _progress(context, 0, total_files if total_files > 0 else 1, f"准备写入：{total_files} 个文件", stage="prepare")

    logs = []
    if prep["skipped_no_path"] > 0:
        logs.append(_log("WARNING", f"有 {prep['skipped_no_path']} 行缺少路径，已跳过"))
    if prep["skipped_empty_value"] > 0:
        logs.append(_log("INFO", f"有 {prep['skipped_empty_value']} 行空文本，按配置已跳过"))

    if total_ops <= 0:
        return {
            "ok": True,
            "message": "没有可写入的数据",
            "output": {
                "type": "table",
                "headers": ["提示"],
                "rows": [["没有可写入的数据"]],
                "meta": {"plugin": PLUGIN_INFO["id"]},
            },
            "logs": logs,
            "summary": {
                "input_rows": prep["input_rows"],
                "total_files": 0,
                "total_ops": 0,
                "applied": 0,
                "skipped": prep["skipped_no_path"] + prep["skipped_empty_value"],
                "failed_files": 0,
                "preview_protected": bool(is_preview and not preview_write),
            },
        }

    out_headers = list(OUTPUT_HEADERS)
    out_rows = []
    total_applied = 0
    total_skipped = prep["skipped_no_path"] + prep["skipped_empty_value"]
    failed_files = 0
    preview_protected = bool(is_preview and not preview_write)
    processed_files = 0
    cancelled = False
    win32_session = None
    if engine == "win32" and win32_reuse_app and not preview_protected:
        win32_session = _Win32OfficeSession(
            open_retries=win32_open_retries,
            retry_interval_ms=win32_retry_interval_ms,
            close_settle_ms=win32_close_settle_ms,
        )
        logs.append(_log("INFO", "WIN32_REUSE：本节点将复用同一个 Word/Excel 进程处理多个文件"))

    for i, item in enumerate(grouped.values(), start=1):
        if _check_cancel(context):
            cancelled = True
            logs.append(_log("WARNING", "检测到取消信号，已停止后续写入"))
            _progress(context, i - 1, total_files, "已取消，停止后续写入", stage="cancelled")
            break
        source_path = item["source_path"]
        target_path = item["target_path"]
        ops = item["ops"]
        _progress(context, i - 1, total_files, f"写入中：{target_path.name}", stage="file_start", object=str(target_path))
        if item.get("source_conflict"):
            err = f"同一个目标文件对应多个源文件：{target_path}"
            failed_files += 1
            total_skipped += len(ops)
            processed_files += 1
            out_rows.append([str(source_path), str(target_path), target_path.name, engine, len(ops), 0, len(ops), "", "失败", "失败", err])
            logs.append(_log("ERROR", err, str(target_path)))
            _progress(context, i, total_files, f"失败：{target_path.name}", stage="file_error", object=str(target_path))
            if error_policy == "遇错停止":
                if win32_session is not None:
                    win32_session.close()
                    win32_session = None
                raise RuntimeError(err)
            continue

        copy_status = ""
        try:
            copy_status, prepare_msg = _prepare_target_file(source_path, target_path, p, preview_protected)
            if copy_status == "skip":
                out_rows.append([str(source_path), str(target_path), target_path.name, engine, len(ops), 0, len(ops), copy_status, "跳过", "跳过", prepare_msg])
                logs.append(_log("INFO", f"{target_path.name} 已跳过：{prepare_msg}", str(target_path)))
                total_skipped += len(ops)
                processed_files += 1
                _progress(context, i, total_files, f"跳过：{target_path.name}", stage="file_skipped", object=str(target_path))
                continue
        except Exception as exc:
            failed_files += 1
            err = str(exc)
            out_rows.append([str(source_path), str(target_path), target_path.name, engine, len(ops), 0, len(ops), copy_status, "失败", "失败", err])
            logs.append(_log("ERROR", f"{target_path.name} 准备目标文件失败：{err}", str(target_path)))
            total_skipped += len(ops)
            processed_files += 1
            _progress(context, i, total_files, f"失败：{target_path.name}", stage="file_error", object=str(target_path))
            if error_policy == "遇错停止":
                if win32_session is not None:
                    win32_session.close()
                    win32_session = None
                raise
            continue

        if preview_protected:
            out_rows.append([str(source_path), str(target_path), target_path.name, engine, len(ops), 0, len(ops), copy_status, "预览保护(未写入)", "预览保护(未写入)", ""])
            logs.append(_log("INFO", f"预览模式已保护，未写入：{target_path.name}", str(target_path)))
            total_skipped += len(ops)
            processed_files += 1
            _progress(context, i, total_files, f"预览保护：{target_path.name}", stage="file_skipped", object=str(target_path))
            continue

        try:
            if not target_path.exists():
                raise FileNotFoundError(f"目标文件不存在：{target_path}")
            if win32_session is not None:
                applied, skipped, write_logs = win32_session.write_file(target_path, ops, context, i - 1, total_files)
            else:
                applied, skipped, write_logs = _write_file(target_path, ops, engine, context, i - 1, total_files)
            total_applied += applied
            total_skipped += skipped
            out_rows.append([str(source_path), str(target_path), target_path.name, engine, len(ops), applied, skipped, copy_status, "成功", "成功", ""])
            logs.extend(write_logs)
            logs.append(_log("INFO", f"{target_path.name} 写入完成：应用 {applied}，跳过 {skipped}", str(target_path)))
            processed_files += 1
            _progress(context, i, total_files, f"已完成：{target_path.name}", stage="file_done", object=str(target_path))
        except Exception as exc:
            failed_files += 1
            err = str(exc)
            out_rows.append([str(source_path), str(target_path), target_path.name, engine, len(ops), 0, len(ops), copy_status, "失败", "失败", err])
            logs.append(_log("ERROR", f"{target_path.name} 写入失败：{err}", str(target_path)))
            total_skipped += len(ops)
            processed_files += 1
            _progress(context, i, total_files, f"失败：{target_path.name}", stage="file_error", object=str(target_path))
            if error_policy == "遇错停止":
                if win32_session is not None:
                    win32_session.close()
                    win32_session = None
                raise

    if win32_session is not None:
        win32_session.close()
        logs.append(_log("INFO", "WIN32_REUSE：Office 进程已统一退出"))

    ok_files = max(0, processed_files - failed_files)
    if cancelled:
        msg = f"写入已取消：已处理文件 {processed_files}/{total_files}；成功 {ok_files}，失败 {failed_files}；应用 {total_applied}，跳过 {total_skipped}"
    else:
        msg = f"写入完成：文件成功 {ok_files}，失败 {failed_files}；操作应用 {total_applied}，跳过 {total_skipped}"
    _progress(context, processed_files, total_files if total_files > 0 else 1, "写入阶段完成", stage="done", cancelled=cancelled)
    return {
        "ok": True,
        "message": msg,
        "output": {
            "type": "table",
            "headers": out_headers,
            "rows": out_rows,
            "meta": {"plugin": PLUGIN_INFO["id"]},
        },
        "logs": logs[-500:],
        "summary": {
            "input_rows": prep["input_rows"],
            "total_files": total_files,
            "total_ops": total_ops,
            "applied": total_applied,
            "skipped": total_skipped,
            "failed_files": failed_files,
            "processed_files": processed_files,
            "preview_protected": preview_protected,
            "engine": engine,
            "cancelled": cancelled,
            "win32_reuse_app": bool(engine == "win32" and win32_reuse_app),
            "win32_open_retries": win32_open_retries,
            "win32_retry_interval_ms": win32_retry_interval_ms,
            "win32_close_settle_ms": win32_close_settle_ms,
            "target_path_field": _as_text(p.get("target_path_field", "target_file")) or "target_file",
            "target_missing_policy": _as_text(p.get("target_missing_policy", "从源文件复制")) or "从源文件复制",
            "target_existing_policy": _as_text(p.get("target_existing_policy", "直接写入")) or "直接写入",
            "same_path_policy": _as_text(p.get("same_path_policy", "修改源文件")) or "修改源文件",
        },
    }


if __name__ == "__main__":
    print("这是工作流插件文件，请放到 plugins 目录并在主程序里通过插件节点调用。")
