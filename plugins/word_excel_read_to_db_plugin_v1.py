# -*- coding: utf-8 -*-
import hashlib
import json
import re
import shutil
import sqlite3
import tempfile
import time
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

PLUGIN_INFO = {
    "id": "word_excel_read_to_db_v1",
    "name": "Word/Excel读取入库V1",
    "version": "1.0.0",
    "api_version": "1.0",
    "category": "文件处理",
    "description": "读取Word/Excel文件并按“每文件一表”写入数据库，输出处理摘要。",
    "input_type": "table",
    "output_type": "table",
    "danger_level": "db_write",
}


def get_parameter_schema():
    return [
        {
            "name": "read_engine",
            "label": "读取引擎",
            "type": "select",
            "choices": ["win32", "zip_xml"],
            "default": "win32",
            "help": "win32：通过 Office COM 读取；zip_xml：Word/Excel 走 ZIP+XML 解析。",
        },
        {
            "name": "path_source",
            "label": "文件来源",
            "type": "select",
            "choices": [
                "当前表字段=完整文件路径",
                "当前表字段=目录路径",
                "插件参数=固定目录路径",
            ],
            "default": "当前表字段=完整文件路径",
        },
        {
            "name": "path_field",
            "label": "完整路径字段",
            "type": "field_select",
            "default": "完整路径",
        },
        {
            "name": "dir_field",
            "label": "目录字段",
            "type": "field_select",
            "default": "目录",
        },
        {
            "name": "directory_path",
            "label": "固定目录路径",
            "type": "folder_path",
            "default": "",
        },
        {
            "name": "recursive",
            "label": "目录递归扫描",
            "type": "bool",
            "default": True,
        },
        {
            "name": "file_patterns",
            "label": "文件匹配",
            "type": "text",
            "default": "*.doc;*.docx;*.docm;*.xls;*.xlsx;*.xlsm",
            "help": "多个模式用 ; 或 , 分隔。",
        },
        {
            "name": "table_name_mode",
            "label": "表名模式",
            "type": "select",
            "choices": ["文件名", "文件名+短哈希"],
            "default": "文件名+短哈希",
        },
        {
            "name": "table_prefix",
            "label": "表名前缀",
            "type": "text",
            "default": "src_",
        },
        {
            "name": "write_mode",
            "label": "写表模式",
            "type": "select",
            "choices": ["replace", "timestamp", "fail"],
            "default": "replace",
        },
        {
            "name": "preview_write_db",
            "label": "预览模式仍写库",
            "type": "bool",
            "default": False,
            "help": "默认预览模式只模拟，不实际写入数据库。",
        },
        {
            "name": "enable_cache",
            "label": "启用插件缓存",
            "type": "bool",
            "default": True,
        },
        {
            "name": "force_refresh",
            "label": "强制重新处理，不使用缓存",
            "type": "bool",
            "default": False,
        },
        {
            "name": "cache_key_mode",
            "label": "缓存校验方式",
            "type": "select",
            "choices": ["快速签名", "文件Hash"],
            "default": "快速签名",
        },
        {
            "name": "error_policy",
            "label": "失败处理",
            "type": "select",
            "choices": ["继续并记录失败", "遇错停止"],
            "default": "继续并记录失败",
        },
    ]


def _as_text(v):
    return "" if v is None else str(v).strip()


def _safe_cell(row, idx):
    return row[idx] if idx < len(row) else ""


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


def _check_cancel(context):
    ev = context.get("cancel_event")
    return bool(ev is not None and hasattr(ev, "is_set") and ev.is_set())


def _resolve_path(text, context):
    p = Path(_as_text(text))
    if p.is_absolute():
        return p
    app_dir = Path(context.get("app_dir", "."))
    return (app_dir / p).resolve()


def _split_patterns(text):
    raw = _as_text(text)
    if raw == "":
        return ["*.doc", "*.docx", "*.docm", "*.xls", "*.xlsx", "*.xlsm"]
    parts = re.split(r"[;,]", raw)
    cleaned = [p.strip() for p in parts if p.strip()]
    return cleaned or ["*.doc", "*.docx", "*.docm", "*.xls", "*.xlsx", "*.xlsm"]


def _collect_files(input_data, params, context):
    headers = list(input_data.get("headers", []))
    rows = [list(r) for r in input_data.get("rows", [])]
    source_mode = params.get("path_source", "当前表字段=完整文件路径")
    recursive = bool(params.get("recursive", True))
    patterns = _split_patterns(params.get("file_patterns", ""))

    def scan_dir(dir_path):
        files = []
        for pat in patterns:
            if recursive:
                files.extend([p for p in dir_path.rglob(pat) if p.is_file()])
            else:
                files.extend([p for p in dir_path.glob(pat) if p.is_file()])
        return files

    out = []
    if source_mode == "当前表字段=完整文件路径":
        field = _as_text(params.get("path_field", "完整路径"))
        idx = headers.index(field)
        for row_no, row in enumerate(rows, start=1):
            cell = _as_text(_safe_cell(row, idx))
            if cell:
                out.append({"path": _resolve_path(cell, context), "source_row": row_no, "source_mode": source_mode})
    elif source_mode == "当前表字段=目录路径":
        field = _as_text(params.get("dir_field", "目录"))
        idx = headers.index(field)
        for row_no, row in enumerate(rows, start=1):
            cell = _as_text(_safe_cell(row, idx))
            if not cell:
                continue
            folder = _resolve_path(cell, context)
            for p in scan_dir(folder):
                out.append({"path": p, "source_row": row_no, "source_mode": source_mode})
    else:
        folder = _resolve_path(_as_text(params.get("directory_path", "")), context)
        for p in scan_dir(folder):
            out.append({"path": p, "source_row": "", "source_mode": source_mode})

    dedup = {}
    for item in out:
        key = str(item["path"]).lower()
        if key not in dedup:
            dedup[key] = item
    return list(dedup.values())


def _sanitize_table_name(name):
    name = re.sub(r"[^0-9A-Za-z_\u4e00-\u9fff]+", "_", _as_text(name))
    name = name.strip("_")
    return name or "unnamed"


def _short_hash(path):
    h = hashlib.sha256(str(path).encode("utf-8")).hexdigest()
    return h[:8]


def _build_table_name(file_path, params):
    prefix = _as_text(params.get("table_prefix", "src_"))
    mode = _as_text(params.get("table_name_mode", "文件名+短哈希"))
    stem = _sanitize_table_name(file_path.stem)
    if mode == "文件名":
        return _sanitize_table_name(prefix + stem)
    return _sanitize_table_name(f"{prefix}{stem}_{_short_hash(file_path)}")


def _cache_db_path(context):
    data_dir = Path(context.get("plugin_data_dir", "."))
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "cache.sqlite"


def _ensure_cache_table(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS plugin_cache (
            cache_key TEXT PRIMARY KEY,
            plugin_id TEXT,
            plugin_version TEXT,
            file_path TEXT,
            file_size INTEGER,
            file_mtime_ns INTEGER,
            file_hash TEXT,
            params_hash TEXT,
            result_json TEXT,
            updated_at TEXT
        )
        """
    )
    conn.commit()


def _stable_params_hash(params):
    ignore = {"enable_cache", "force_refresh", "cache_key_mode"}
    data = {k: params[k] for k in sorted(params.keys()) if k not in ignore}
    txt = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(txt.encode("utf-8")).hexdigest()


def _file_sha256(file_path):
    h = hashlib.sha256()
    with file_path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _cache_signature(file_path, mode):
    st = file_path.stat()
    sig = {
        "file_size": int(st.st_size),
        "file_mtime_ns": int(getattr(st, "st_mtime_ns", int(st.st_mtime * 1_000_000_000))),
        "file_hash": "",
    }
    if mode == "文件Hash":
        sig["file_hash"] = _file_sha256(file_path)
    return sig


def _cache_key(file_path, mode, params_hash, sig):
    payload = {
        "plugin_id": PLUGIN_INFO["id"],
        "plugin_version": PLUGIN_INFO["version"],
        "file_path": str(file_path.resolve()).lower(),
        "file_size": sig["file_size"],
        "file_mtime_ns": sig["file_mtime_ns"],
        "file_hash": sig.get("file_hash", ""),
        "params_hash": params_hash,
        "cache_key_mode": mode,
    }
    txt = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(txt.encode("utf-8")).hexdigest()


def _cache_load(conn, key):
    cur = conn.cursor()
    cur.execute("SELECT result_json FROM plugin_cache WHERE cache_key=?", (key,))
    row = cur.fetchone()
    if not row or not row[0]:
        return None
    try:
        data = json.loads(row[0])
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _cache_save(conn, key, file_path, params_hash, sig, result_data):
    payload = json.dumps(result_data, ensure_ascii=False)
    conn.execute(
        """
        INSERT OR REPLACE INTO plugin_cache(
            cache_key, plugin_id, plugin_version, file_path, file_size, file_mtime_ns,
            file_hash, params_hash, result_json, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            key,
            PLUGIN_INFO["id"],
            PLUGIN_INFO["version"],
            str(file_path),
            int(sig.get("file_size", 0)),
            int(sig.get("file_mtime_ns", 0)),
            _as_text(sig.get("file_hash", "")),
            params_hash,
            payload,
            time.strftime("%Y-%m-%d %H:%M:%S"),
        ),
    )
    conn.commit()


def _xml_texts(node, ns):
    texts = []
    for t in node.findall(".//w:t", ns):
        if t.text:
            texts.append(t.text)
    return "".join(texts).strip()


def _clean_word_text(text):
    s = _as_text(text)
    s = s.replace("\r", "").replace("\x07", "").replace("\n", "").strip()
    return s


def _read_docx_like(file_path):
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    rows = []
    with zipfile.ZipFile(file_path, "r") as zf:
        if "word/document.xml" not in zf.namelist():
            return rows
        root = ET.fromstring(zf.read("word/document.xml"))
        body = root.find("w:body", ns)
        if body is None:
            return rows

        para_idx = 0
        table_idx = 0
        for child in list(body):
            tag = child.tag.split("}")[-1]
            if tag == "p":
                para_idx += 1
                txt = _xml_texts(child, ns)
                if txt != "":
                    rows.append(
                        {
                            "block_type": "word_paragraph",
                            "sheet_name": "",
                            "row_index": para_idx,
                            "col_index": "",
                            "cell_address": "",
                            "text": txt,
                            "meta_json": json.dumps({"paragraph_index": para_idx}, ensure_ascii=False),
                        }
                    )
            elif tag == "tbl":
                table_idx += 1
                row_idx = 0
                for tr in child.findall(".//w:tr", ns):
                    row_idx += 1
                    col_idx = 0
                    for tc in tr.findall("./w:tc", ns):
                        col_idx += 1
                        txt = _xml_texts(tc, ns)
                        if txt == "":
                            continue
                        rows.append(
                            {
                                "block_type": "word_table_cell",
                                "sheet_name": f"table_{table_idx}",
                                "row_index": row_idx,
                                "col_index": col_idx,
                                "cell_address": f"R{row_idx}C{col_idx}",
                                "text": txt,
                                "meta_json": json.dumps(
                                    {"table_index": table_idx, "row_index": row_idx, "col_index": col_idx},
                                    ensure_ascii=False,
                                ),
                            }
                        )
    return rows


def _read_doc_via_com(file_path):
    try:
        import pythoncom
        import win32com.client
    except Exception as exc:
        raise RuntimeError("读取 .doc 需要 pywin32 + Word") from exc

    temp_docx = None
    temp_dir = None
    word = None
    try:
        pythoncom.CoInitialize()
        word = win32com.client.DispatchEx("Word.Application")
        word.Visible = False
        word.DisplayAlerts = 0
        doc = word.Documents.Open(str(file_path), ReadOnly=True, AddToRecentFiles=False, ConfirmConversions=False, Visible=False)
        try:
            # 使用临时目录文件，避免 mkstemp 文件句柄在 Windows 上占用导致 WinError 32。
            temp_dir = Path(tempfile.mkdtemp(prefix="word_doc_convert_"))
            temp_docx = temp_dir / f"{file_path.stem}_converted.docx"
            # 12 = wdFormatXMLDocument
            doc.SaveAs2(str(temp_docx), FileFormat=12)
        finally:
            doc.Close(False)

        # 某些 Word 版本 SaveAs2 后会短暂占用文件，这里做轻量重试。
        last_err = None
        for _ in range(5):
            try:
                return _read_docx_like(temp_docx)
            except Exception as exc:
                last_err = exc
                time.sleep(0.15)
        raise last_err if last_err else RuntimeError("读取临时 docx 失败")
    finally:
        if word is not None:
            try:
                word.Quit()
            except Exception:
                pass
        try:
            pythoncom.CoUninitialize()
        except Exception:
            pass
        if temp_dir is not None and temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)


def _read_word_via_com(file_path):
    try:
        import pythoncom
        import win32com.client
    except Exception as exc:
        raise RuntimeError("读取 Word 需要 pywin32 + Word") from exc

    word = None
    doc = None
    rows = []
    try:
        pythoncom.CoInitialize()
        word = win32com.client.DispatchEx("Word.Application")
        word.Visible = False
        word.DisplayAlerts = 0
        doc = word.Documents.Open(str(file_path), ReadOnly=True, AddToRecentFiles=False, ConfirmConversions=False, Visible=False)

        try:
            p_count = int(doc.Paragraphs.Count)
        except Exception:
            p_count = 0
        for i in range(1, p_count + 1):
            try:
                txt = _clean_word_text(doc.Paragraphs(i).Range.Text)
            except Exception:
                txt = ""
            if txt == "":
                continue
            rows.append(
                {
                    "block_type": "word_paragraph",
                    "sheet_name": "",
                    "row_index": i,
                    "col_index": "",
                    "cell_address": "",
                    "text": txt,
                    "meta_json": json.dumps({"paragraph_index": i}, ensure_ascii=False),
                }
            )

        try:
            t_count = int(doc.Tables.Count)
        except Exception:
            t_count = 0
        for t in range(1, t_count + 1):
            table = doc.Tables(t)
            try:
                r_count = int(table.Rows.Count)
                c_count = int(table.Columns.Count)
            except Exception:
                continue
            for r in range(1, r_count + 1):
                for c in range(1, c_count + 1):
                    try:
                        txt = _clean_word_text(table.Cell(r, c).Range.Text)
                    except Exception:
                        txt = ""
                    if txt == "":
                        continue
                    rows.append(
                        {
                            "block_type": "word_table_cell",
                            "sheet_name": f"table_{t}",
                            "row_index": r,
                            "col_index": c,
                            "cell_address": f"R{r}C{c}",
                            "text": txt,
                            "meta_json": json.dumps({"table_index": t, "row_index": r, "col_index": c}, ensure_ascii=False),
                        }
                    )
        return rows
    finally:
        if doc is not None:
            try:
                doc.Close(False)
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


def _read_excel_openpyxl(file_path):
    try:
        from openpyxl import load_workbook
    except Exception as exc:
        raise RuntimeError("未安装 openpyxl") from exc

    rows = []
    wb = load_workbook(filename=str(file_path), read_only=True, data_only=False)
    try:
        for ws in wb.worksheets:
            for row in ws.iter_rows(min_row=1, max_row=ws.max_row, min_col=1, max_col=ws.max_column):
                for cell in row:
                    value = cell.value
                    if value is None or str(value) == "":
                        continue
                    rows.append(
                        {
                            "block_type": "excel_cell",
                            "sheet_name": ws.title,
                            "row_index": cell.row,
                            "col_index": cell.column,
                            "cell_address": cell.coordinate,
                            "text": str(value),
                            "meta_json": json.dumps({"data_type": cell.data_type}, ensure_ascii=False),
                        }
                    )
    finally:
        wb.close()
    return rows


def _read_excel_via_com(file_path):
    try:
        import pythoncom
        import win32com.client
    except Exception as exc:
        raise RuntimeError("读取 Excel 需要 openpyxl 或 pywin32 + Excel") from exc

    excel = None
    wb = None
    rows = []
    try:
        pythoncom.CoInitialize()
        excel = win32com.client.DispatchEx("Excel.Application")
        excel.Visible = False
        excel.DisplayAlerts = False
        wb = excel.Workbooks.Open(str(file_path), ReadOnly=True, UpdateLinks=0)
        for si in range(1, wb.Worksheets.Count + 1):
            ws = wb.Worksheets(si)
            used = ws.UsedRange
            if used is None:
                continue
            sr = int(used.Row)
            sc = int(used.Column)
            rc = int(used.Rows.Count)
            cc = int(used.Columns.Count)
            for r in range(sr, sr + rc):
                for c in range(sc, sc + cc):
                    cell = ws.Cells(r, c)
                    txt = _as_text(cell.Text)
                    if txt == "":
                        continue
                    rows.append(
                        {
                            "block_type": "excel_cell",
                            "sheet_name": _as_text(ws.Name),
                            "row_index": r,
                            "col_index": c,
                            "cell_address": _as_text(cell.Address).replace("$", ""),
                            "text": txt,
                            "meta_json": "{}",
                        }
                    )
        return rows
    finally:
        if wb is not None:
            try:
                wb.Close(False)
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


def _read_file_rows(file_path, read_engine):
    ext = file_path.suffix.lower()
    engine = _as_text(read_engine).lower() or "win32"

    if ext in (".doc", ".docx", ".docm"):
        if engine == "win32":
            return _read_word_via_com(file_path)
        if ext == ".doc":
            # doc 无法直接 ZIP+XML，降级转换后再解析
            return _read_doc_via_com(file_path)
        return _read_docx_like(file_path)

    if ext in (".xlsx", ".xlsm", ".xls"):
        if engine == "win32":
            try:
                return _read_excel_via_com(file_path)
            except Exception:
                return _read_excel_openpyxl(file_path)
        try:
            return _read_excel_openpyxl(file_path)
        except Exception:
            return _read_excel_via_com(file_path)

    raise ValueError(f"不支持的文件类型：{ext}")


def _write_table_with_db_api(db, table_name, headers, rows, mode):
    return db.write_table(table_name=table_name, headers=headers, rows=rows, mode=mode)


def _write_table_sqlite_fallback(db_path, table_name, headers, rows, mode):
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        qname = '"' + table_name.replace('"', '""') + '"'
        if mode == "replace":
            cur.execute(f"DROP TABLE IF EXISTS {qname}")
        elif mode == "fail":
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
            if cur.fetchone():
                raise RuntimeError(f"表已存在：{table_name}")
        elif mode == "timestamp":
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
            if cur.fetchone():
                table_name = f"{table_name}_{_short_hash(table_name)}"
                qname = '"' + table_name.replace('"', '""') + '"'

        col_defs = ", ".join(['"' + h.replace('"', '""') + '" TEXT' for h in headers])
        cur.execute(f"CREATE TABLE IF NOT EXISTS {qname} ({col_defs})")
        placeholders = ", ".join(["?"] * len(headers))
        cols = ", ".join(['"' + h.replace('"', '""') + '"' for h in headers])
        cur.executemany(f"INSERT INTO {qname} ({cols}) VALUES ({placeholders})", rows)
        conn.commit()
        return {"table_name": table_name, "row_count": len(rows)}
    finally:
        conn.close()


def validate_params(params, input_data, context):
    p = dict(params or {})
    headers = list(input_data.get("headers", []))
    source_mode = _as_text(p.get("path_source", "当前表字段=完整文件路径"))

    if source_mode == "当前表字段=完整文件路径":
        if _as_text(p.get("path_field", "完整路径")) not in headers:
            return False, "完整路径字段不存在"
    elif source_mode == "当前表字段=目录路径":
        if _as_text(p.get("dir_field", "目录")) not in headers:
            return False, "目录字段不存在"
    else:
        if _as_text(p.get("directory_path", "")) == "":
            return False, "固定目录路径不能为空"
    return True, ""


def run(input_data, params, context):
    p = dict(params or {})
    read_engine = _as_text(p.get("read_engine", "win32")) or "win32"
    error_policy = _as_text(p.get("error_policy", "继续并记录失败"))
    files = _collect_files(input_data, p, context)
    if not files:
        return {
            "ok": True,
            "message": "未找到待处理文件",
            "output": {"type": "table", "headers": ["提示"], "rows": [["未找到待处理文件"]], "meta": {"plugin": PLUGIN_INFO["id"]}},
            "logs": [{"level": "INFO", "message": "未找到待处理文件"}],
            "summary": {"total": 0, "success": 0, "failed": 0, "written_rows": 0, "output_rows": 0},
        }
    _progress(context, 0, len(files), f"准备读取 {len(files)} 个文件", stage="prepare")

    db = context.get("db")
    db_path = context.get("db_path", "")
    is_preview = bool(context.get("is_preview", False))
    preview_write_db = bool(p.get("preview_write_db", False))
    write_mode = _as_text(p.get("write_mode", "replace")) or "replace"
    logs = []
    enable_cache = bool(p.get("enable_cache", True))
    force_refresh = bool(p.get("force_refresh", False))
    cache_key_mode = _as_text(p.get("cache_key_mode", "快速签名")) or "快速签名"
    if cache_key_mode not in ("快速签名", "文件Hash"):
        cache_key_mode = "快速签名"
    params_hash = _stable_params_hash(p)
    cache_conn = None
    if enable_cache:
        try:
            cache_conn = sqlite3.connect(str(_cache_db_path(context)))
            _ensure_cache_table(cache_conn)
        except Exception as exc:
            cache_conn = None
            logs.append({"level": "WARNING", "message": f"CACHE_ERROR：初始化缓存失败：{exc}"})

    detail_headers = [
        "source_file",
        "source_name",
        "source_ext",
        "block_type",
        "sheet_name",
        "row_index",
        "col_index",
        "cell_address",
        "text",
        "meta_json",
    ]
    summary_headers = ["source_row", "source_mode", "file_name", "file_path", "table_name", "read_rows", "write_rows", "status", "error"]
    summary_rows = []
    output_rows = []
    cancelled = False
    cache_hit_count = 0
    cache_miss_count = 0
    cache_write_count = 0

    try:
        file_iter = enumerate(files, start=1)
    except Exception:
        file_iter = []

    for i, item in file_iter:
        if _check_cancel(context):
            cancelled = True
            logs.append({"level": "WARNING", "message": "检测到取消信号，已停止后续读取"})
            _progress(context, i - 1, len(files), "已取消，停止后续读取", stage="cancelled")
            break
        file_path = item["path"]
        table_name = _build_table_name(file_path, p)
        _progress(context, i - 1, len(files), f"读取中：{file_path.name}", stage="file_start", object=str(file_path))
        try:
            if not file_path.exists():
                raise FileNotFoundError(f"文件不存在：{file_path}")

            parsed = None
            cache_key = ""
            cache_sig = None
            if enable_cache and cache_conn is not None:
                try:
                    cache_sig = _cache_signature(file_path, cache_key_mode)
                    cache_key = _cache_key(file_path, cache_key_mode, params_hash, cache_sig)
                    if force_refresh:
                        logs.append({"level": "INFO", "object": str(file_path), "message": "CACHE_REFRESH：强制重新处理"})
                    else:
                        cached = _cache_load(cache_conn, cache_key)
                        if cached and isinstance(cached.get("parsed"), list):
                            parsed = cached["parsed"]
                            cache_hit_count += 1
                            logs.append({"level": "INFO", "object": str(file_path), "message": "CACHE_HIT：文件未变化，复用缓存读取结果"})
                        else:
                            cache_miss_count += 1
                            logs.append({"level": "INFO", "object": str(file_path), "message": "CACHE_MISS：未命中缓存，重新读取"})
                except Exception as exc:
                    logs.append({"level": "WARNING", "object": str(file_path), "message": f"CACHE_ERROR：读取缓存失败：{exc}"})

            if parsed is None:
                parsed = _read_file_rows(file_path, read_engine)
                if enable_cache and cache_conn is not None and cache_key and cache_sig is not None:
                    try:
                        _cache_save(cache_conn, cache_key, file_path, params_hash, cache_sig, {"parsed": parsed})
                        cache_write_count += 1
                        logs.append({"level": "INFO", "object": str(file_path), "message": "CACHE_WRITE：已写入缓存"})
                    except Exception as exc:
                        logs.append({"level": "WARNING", "object": str(file_path), "message": f"CACHE_ERROR：写入缓存失败：{exc}"})

            detail_rows = []
            for r in parsed:
                detail_rows.append(
                    [
                        str(file_path),
                        file_path.name,
                        file_path.suffix.lower(),
                        _as_text(r.get("block_type", "")),
                        _as_text(r.get("sheet_name", "")),
                        _as_text(r.get("row_index", "")),
                        _as_text(r.get("col_index", "")),
                        _as_text(r.get("cell_address", "")),
                        _as_text(r.get("text", "")),
                        _as_text(r.get("meta_json", "{}")),
                    ]
                )
            output_rows.extend(detail_rows)

            written_count = 0
            status = "读取成功(预览未写库)" if (is_preview and not preview_write_db) else "成功"
            if not (is_preview and not preview_write_db):
                if db is not None and hasattr(db, "write_table"):
                    result = _write_table_with_db_api(db, table_name, detail_headers, detail_rows, write_mode)
                    table_name = _as_text(result.get("table_name", table_name)) or table_name
                else:
                    if not db_path:
                        raise RuntimeError("缺少数据库连接：context['db'] 和 context['db_path'] 都不可用")
                    result = _write_table_sqlite_fallback(db_path, table_name, detail_headers, detail_rows, write_mode)
                    table_name = _as_text(result.get("table_name", table_name)) or table_name
                written_count = len(detail_rows)

            summary_rows.append(
                [
                    item["source_row"],
                    item["source_mode"],
                    file_path.name,
                    str(file_path),
                    table_name,
                    len(detail_rows),
                    written_count,
                    status,
                    "",
                ]
            )
            logs.append(
                {
                    "level": "INFO",
                    "object": str(file_path),
                    "message": f"{file_path.name} -> {table_name}，引擎={read_engine}，读取 {len(detail_rows)} 行",
                }
            )
            _progress(context, i, len(files), f"已完成：{file_path.name}", stage="file_done", object=str(file_path))
        except Exception as exc:
            err = str(exc)
            summary_rows.append(
                [
                    item["source_row"],
                    item["source_mode"],
                    file_path.name,
                    str(file_path),
                    table_name,
                    0,
                    0,
                    "失败",
                    err,
                ]
            )
            logs.append(
                {
                    "level": "ERROR",
                    "object": str(file_path),
                    "message": f"{file_path.name} 失败：{err}",
                }
            )
            _progress(context, i, len(files), f"失败：{file_path.name}", stage="file_error", object=str(file_path))
            if error_policy == "遇错停止":
                raise

    ok_count = len([r for r in summary_rows if r[7].startswith("成功") or r[7].startswith("读取成功")])
    fail_count = len(summary_rows) - ok_count
    written_rows = sum(int(r[6]) for r in summary_rows if str(r[6]).isdigit())
    summary = {
        "total": len(summary_rows),
        "planned_total": len(files),
        "success": ok_count,
        "failed": fail_count,
        "written_rows": written_rows,
        "output_rows": len(output_rows),
        "read_engine": read_engine,
        "cancelled": cancelled,
        "cache_enabled": enable_cache,
        "cache_key_mode": cache_key_mode,
        "cache_hit": cache_hit_count,
        "cache_miss": cache_miss_count,
        "cache_write": cache_write_count,
    }
    if cache_conn is not None:
        try:
            cache_conn.close()
        except Exception:
            pass
    _progress(context, len(summary_rows), len(files), "读取阶段完成", stage="done", cancelled=cancelled)
    return {
        "ok": True,
        "message": f"读取完成：成功 {ok_count}，失败 {fail_count}",
        "output": {
            "type": "table",
            "headers": detail_headers,
            "rows": output_rows,
            "meta": {
                "plugin": PLUGIN_INFO["id"],
                "success_count": ok_count,
                "fail_count": fail_count,
                "summary_headers": summary_headers,
                "summary_rows": summary_rows,
            },
        },
        "logs": logs[-200:],
        "summary": summary,
    }
