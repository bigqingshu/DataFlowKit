# -*- coding: utf-8 -*-
"""Backend table listing, loading, editing, and paging service."""

from __future__ import annotations

import csv
import io
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from db.table_manager import TableAccessManager
from engine.issue_schema import has_error_issues, make_issue
from engine.models import TableData
from engine.table_io import load_table_file


@dataclass
class TableDataService:
    db_path: str = ""
    handle_id_factory: object = None
    table_handles: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.handle_id_factory is None:
            self.handle_id_factory = lambda: "table_" + uuid.uuid4().hex

    def list_tables(self, db_path=None):
        target_db = self._resolve_db_path(db_path)
        if not target_db or not Path(target_db).exists():
            return {
                "ok": True,
                "db_path": target_db,
                "tables": [],
                "issues": [],
            }
        tables = TableAccessManager(target_db, node_type="TableDataService").list_tables()
        return {
            "ok": True,
            "db_path": target_db,
            "tables": tables,
            "issues": [],
        }

    def load_table(self, source=None, *, db_path=None, table_name=None, path=None, limit=None, offset=0):
        source = dict(source or {})
        source_type = str(source.get("type") or source.get("source_type") or "").strip()
        db_path = source.get("db_path") if source.get("db_path") is not None else db_path
        table_name = source.get("table_name") or source.get("table") or table_name
        path = source.get("path") or path
        limit = source.get("limit", limit)
        offset = int(source.get("offset", offset) or 0)

        if source_type in {"table", "inline"} or ("headers" in source and "rows" in source):
            table = TableData.from_payload(source).to_dict()
            return self.get_table_page(table, limit=limit, offset=offset, source={"type": "inline"})
        if path or source_type in {"file", "path"}:
            if not path:
                return self._failure("missing_table_path", "文件表需要 path。", "/path")
            headers, rows = load_table_file(path)
            table = TableData.from_payload({"headers": headers, "rows": rows}).to_dict()
            return self.get_table_page(table, limit=limit, offset=offset, source={"type": "file", "path": str(path)})
        return self.load_sqlite_table(table_name, db_path=db_path, limit=limit, offset=offset)

    def parse_clipboard_table(self, text, *, first_row_header=True):
        try:
            table = parse_clipboard_table(text, first_row_header=first_row_header)
        except ValueError as exc:
            return self._failure("parse_clipboard_table_failed", str(exc), "/text")
        return {
            "ok": True,
            "source": {"type": "clipboard"},
            "table": table,
            "state": build_data_source_state(table, source={"type": "clipboard"}, dirty=True, display_name="剪贴板数据"),
            "issues": [],
        }

    def normalize_table_headers(self, headers):
        return {
            "ok": True,
            "headers": normalize_table_headers(headers),
            "issues": [],
        }

    def promote_first_row_to_headers(self, table):
        try:
            updated = promote_first_row_to_headers(table)
        except ValueError as exc:
            return self._failure("promote_header_failed", str(exc), "/table/rows")
        return {
            "ok": True,
            "table": updated,
            "state": build_data_source_state(updated, source=(table or {}).get("source"), dirty=True),
            "issues": [],
        }

    def patch_table_cell(self, table, *, row=None, column=None, value=""):
        try:
            updated = patch_table_cell(table, row=row, column=column, value=value)
        except ValueError as exc:
            return self._failure("patch_table_cell_failed", str(exc), "/table")
        return {
            "ok": True,
            "table": updated,
            "state": build_data_source_state(updated, source=(table or {}).get("source"), dirty=True),
            "issues": [],
        }

    def search_table(self, table, keyword):
        matches = search_table(table, keyword)
        return {
            "ok": True,
            "keyword": str(keyword or ""),
            "matches": matches,
            "count": len(matches),
            "issues": [],
        }

    def build_data_source_state(self, table=None, *, source=None, dirty=False, display_name=""):
        return {
            "ok": True,
            "state": build_data_source_state(
                table or {},
                source=source,
                dirty=dirty,
                display_name=display_name,
            ),
            "issues": [],
        }

    def save_table(self, table=None, *, db_path=None, table_name=None, mode="replace"):
        target_db = self._resolve_db_path(db_path)
        table_data = TableData.from_payload(table or {}).to_dict()
        issues = []
        if not target_db:
            issues.append(make_issue("error", "missing_db_path", "保存 SQLite 表需要数据库路径。", path="/db_path", source="TableDataService"))
        if not str(table_name or "").strip():
            issues.append(make_issue("error", "missing_table_name", "保存 SQLite 表需要表名。", path="/table_name", source="TableDataService"))
        if not table_data.get("headers"):
            issues.append(make_issue("error", "missing_table_headers", "保存 SQLite 表需要字段名。", path="/table/headers", source="TableDataService"))
        if has_error_issues(issues):
            return {
                "ok": False,
                "db_path": target_db,
                "table": table_data,
                "issues": issues,
            }
        try:
            result = TableAccessManager(target_db, node_type="TableDataService").write_table(
                table_name,
                table_data.get("headers") or [],
                table_data.get("rows") or [],
                mode=mode,
            )
        except Exception as exc:
            return self._failure("save_table_failed", str(exc), "/table")
        actual_name = result.get("table_name") or str(table_name or "").strip()
        saved_source = {"type": "sqlite", "db_path": target_db, "table_name": actual_name}
        return {
            "ok": True,
            "db_path": target_db,
            "table_name": actual_name,
            "service_result": result,
            "source": saved_source,
            "state": build_data_source_state(
                table_data,
                source=saved_source,
                dirty=False,
                display_name=actual_name,
            ),
            "issues": [],
        }

    def delete_table(self, *, db_path=None, table_name=None, backup=True, confirmed=False):
        target_db = self._resolve_db_path(db_path)
        issues = []
        if not bool(confirmed):
            issues.append(make_issue("error", "delete_not_confirmed", "删除 SQLite 表需要 confirmed=True。", path="/confirmed", source="TableDataService"))
        if not target_db:
            issues.append(make_issue("error", "missing_db_path", "删除 SQLite 表需要数据库路径。", path="/db_path", source="TableDataService"))
        if not str(table_name or "").strip():
            issues.append(make_issue("error", "missing_table_name", "删除 SQLite 表需要表名。", path="/table_name", source="TableDataService"))
        if has_error_issues(issues):
            return {
                "ok": False,
                "db_path": target_db,
                "table_name": str(table_name or ""),
                "issues": issues,
            }
        try:
            backup_name = TableAccessManager(target_db, node_type="TableDataService").drop_table(
                table_name,
                backup=bool(backup),
            )
        except Exception as exc:
            return self._failure("delete_table_failed", str(exc), "/table_name")
        return {
            "ok": True,
            "db_path": target_db,
            "table_name": str(table_name or "").strip(),
            "backup_table": backup_name,
            "deleted": True,
            "issues": [],
        }

    def load_sqlite_table(self, table_name, *, db_path=None, limit=None, offset=0):
        issues = []
        target_db = self._resolve_db_path(db_path)
        if not target_db:
            issues.append(make_issue(
                "error",
                "missing_db_path",
                "读取 SQLite 表需要数据库路径。",
                path="/db_path",
                source="TableDataService",
            ))
        if not str(table_name or "").strip():
            issues.append(make_issue(
                "error",
                "missing_table_name",
                "读取 SQLite 表需要表名。",
                path="/table_name",
                source="TableDataService",
            ))
        if has_error_issues(issues):
            return {
                "ok": False,
                "db_path": target_db,
                "table": {"type": "table", "headers": [], "rows": []},
                "issues": issues,
            }

        manager = TableAccessManager(target_db, node_type="TableDataService")
        if not manager.table_exists(table_name):
            return self._failure("table_not_found", f"SQLite 表不存在：{table_name}", "/table_name")
        table = manager.read_table(table_name, limit=limit, offset=offset)
        return {
            "ok": True,
            "source": {"type": "sqlite", "db_path": target_db, "table_name": table_name},
            "table": TableData.from_payload(table).to_dict(),
            "page": _page_info(table.get("rows", []), limit=limit, offset=offset),
            "issues": [],
        }

    def get_table_page(self, table, *, limit=None, offset=0, source=None):
        handle_id = _table_handle_id(table, source)
        if handle_id:
            return self.get_table_handle_page(handle_id, limit=limit, offset=offset)
        return _page_table_payload(table, limit=limit, offset=offset, source=source)

    def create_table_handle(self, table_or_source=None, *, source=None, limit=None, offset=0, **kwargs):
        source_payload = source if source is not None else table_or_source
        if source_payload is None:
            source_payload = {}
        loaded = self.load_table(source_payload, limit=None, offset=0, **kwargs)
        if not loaded.get("ok"):
            return {
                "ok": False,
                "handle": "",
                "issues": loaded.get("issues", []),
                "table": loaded.get("table", {"type": "table", "headers": [], "rows": []}),
            }
        table = TableData.from_payload(loaded.get("table") or {}).to_dict()
        handle_id = str(self.handle_id_factory())
        self.table_handles[handle_id] = {
            "handle": handle_id,
            "table": table,
            "source": loaded.get("source") or {},
            "created_from": source_payload,
        }
        page = self.get_table_handle_page(handle_id, limit=limit, offset=offset)
        return {
            "ok": True,
            "handle": handle_id,
            "source": {"type": "handle", "handle": handle_id},
            "schema": {
                "headers": list(table.get("headers") or []),
                "row_count": len(table.get("rows") or []),
                "column_count": len(table.get("headers") or []),
            },
            "page": page.get("page", {}),
            "table": page.get("table", {"type": "table", "headers": [], "rows": []}),
            "issues": [],
        }

    def get_table_handle_page(self, handle, *, limit=None, offset=0):
        handle_id = str(handle or "").strip()
        if handle_id not in self.table_handles:
            return self._failure("table_handle_not_found", f"表句柄不存在：{handle_id}", "/handle")
        item = self.table_handles[handle_id]
        result = _page_table_payload(
            item.get("table", {}),
            limit=limit,
            offset=offset,
            source={"type": "handle", "handle": handle_id},
        )
        result["handle"] = handle_id
        return result

    def list_table_handles(self):
        handles = []
        for handle_id, item in sorted(self.table_handles.items()):
            table = TableData.from_payload(item.get("table") or {}).to_dict()
            handles.append({
                "handle": handle_id,
                "source": item.get("source") or {},
                "headers": list(table.get("headers") or []),
                "row_count": len(table.get("rows") or []),
                "column_count": len(table.get("headers") or []),
            })
        return {
            "ok": True,
            "handles": handles,
            "count": len(handles),
            "issues": [],
        }

    def release_table_handle(self, handle):
        handle_id = str(handle or "").strip()
        existed = handle_id in self.table_handles
        if existed:
            del self.table_handles[handle_id]
        return {
            "ok": True,
            "handle": handle_id,
            "released": bool(existed),
            "remaining": len(self.table_handles),
            "issues": [],
        }

    def _resolve_db_path(self, db_path=None):
        return str(db_path or self.db_path or "").strip()

    def _failure(self, code, message, path):
        issue = make_issue("error", code, message, path=path, source="TableDataService")
        return {
            "ok": False,
            "table": {"type": "table", "headers": [], "rows": []},
            "issues": [issue],
        }


def _page_info(rows, *, limit=None, offset=0):
    row_count = len(rows or [])
    limit_value = None if limit is None or limit == "" else int(limit)
    return {
        "offset": int(offset or 0),
        "limit": limit_value,
        "row_count": row_count,
        "total_rows": None,
        "has_more": False if limit_value is None else row_count >= limit_value,
    }


def _page_table_payload(table, *, limit=None, offset=0, source=None):
    table_data = TableData.from_payload(table or {})
    offset = int(offset or 0)
    rows = [list(row) for row in table_data.rows]
    if limit is None or limit == "":
        page_rows = rows[offset:]
        limit_value = None
    else:
        limit_value = max(0, int(limit))
        page_rows = rows[offset:offset + limit_value]
    page_table = TableData.from_payload({
        "headers": table_data.headers,
        "rows": page_rows,
    }).to_dict()
    return {
        "ok": True,
        "source": source or {},
        "table": page_table,
        "page": {
            "offset": offset,
            "limit": limit_value,
            "row_count": len(page_rows),
            "total_rows": len(rows),
            "has_more": (offset + len(page_rows)) < len(rows),
        },
        "issues": [],
    }


def _table_handle_id(table, source):
    if isinstance(table, str):
        return table.strip()
    if isinstance(table, dict) and str(table.get("type") or "").strip() == "handle":
        return str(table.get("handle") or table.get("id") or "").strip()
    if isinstance(source, str):
        return source.strip()
    if isinstance(source, dict) and str(source.get("type") or "").strip() == "handle":
        return str(source.get("handle") or source.get("id") or "").strip()
    return ""


def parse_clipboard_table(text, *, first_row_header=True):
    data = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    if not data.strip():
        raise ValueError("剪贴板内容为空。")
    delimiter = "\t" if "\t" in data or "," not in data else ","
    reader = csv.reader(io.StringIO(data), delimiter=delimiter)
    parsed_rows = []
    for row in reader:
        cleaned = [str(cell).strip() for cell in row]
        if not cleaned or all(cell == "" for cell in cleaned):
            continue
        parsed_rows.append(cleaned)
    if not parsed_rows:
        raise ValueError("没有解析到有效表格数据。")

    width = max(len(row) for row in parsed_rows)
    normalized = [_normalize_row(row, width) for row in parsed_rows]
    if bool(first_row_header) and len(normalized) >= 2:
        headers = normalize_table_headers(normalized[0])
        rows = normalized[1:]
    else:
        headers = normalize_table_headers([f"列{index + 1}" for index in range(width)])
        rows = normalized
    return {
        "type": "table",
        "headers": headers,
        "rows": rows,
        "meta": {
            "delimiter": "tab" if delimiter == "\t" else "comma",
            "source": "clipboard",
        },
    }


def normalize_table_headers(headers):
    result = []
    used = {}
    for index, header in enumerate(headers or [], start=1):
        name = str(header or "").strip() or f"列{index}"
        if name in used:
            used[name] += 1
            name = f"{name}_{used[name]}"
        else:
            used[name] = 1
        result.append(name)
    return result


def promote_first_row_to_headers(table):
    table_data = TableData.from_payload(table or {})
    if not table_data.headers:
        raise ValueError("当前没有字段名，无法提升下一行为字段名。")
    if not table_data.rows:
        raise ValueError("当前没有下一行数据，无法提升为字段名。")
    return {
        "type": "table",
        "headers": normalize_table_headers(table_data.rows[0]),
        "rows": [list(row) for row in table_data.rows[1:]],
    }


def patch_table_cell(table, *, row=None, column=None, value=""):
    table_data = TableData.from_payload(table or {})
    row_index = int(row)
    col_index = int(column)
    if row_index < 0 or row_index >= len(table_data.rows):
        raise ValueError("行索引超出范围。")
    if col_index < 0 or col_index >= len(table_data.headers):
        raise ValueError("列索引超出范围。")
    rows = [list(item) for item in table_data.rows]
    while len(rows[row_index]) < len(table_data.headers):
        rows[row_index].append("")
    rows[row_index][col_index] = "" if value is None else str(value)
    return {
        "type": "table",
        "headers": list(table_data.headers),
        "rows": rows,
    }


def search_table(table, keyword):
    text = str(keyword or "").strip().lower()
    if not text:
        return []
    table_data = TableData.from_payload(table or {})
    matches = []
    for row_index, row in enumerate(table_data.rows):
        fixed = _normalize_row(row, len(table_data.headers))
        row_matches = []
        for column_index, value in enumerate(fixed):
            if text in str(value or "").lower():
                row_matches.append({
                    "row": row_index,
                    "column": column_index,
                    "header": table_data.headers[column_index] if column_index < len(table_data.headers) else "",
                    "value": "" if value is None else str(value),
                })
        if row_matches:
            matches.append({
                "row": row_index,
                "cells": row_matches,
            })
    return matches


def build_data_source_state(table=None, *, source=None, dirty=False, display_name=""):
    table_data = TableData.from_payload(table or {}).to_dict()
    headers = list(table_data.get("headers") or [])
    rows = [list(row) for row in (table_data.get("rows") or [])]
    source_payload = dict(source or {})
    title = str(display_name or source_payload.get("table_name") or source_payload.get("path") or "输入数据源")
    return {
        "source": source_payload,
        "headers": headers,
        "rows": rows,
        "dirty": bool(dirty),
        "display_name": title,
        "row_count": len(rows),
        "column_count": len(headers),
    }


def _normalize_row(row, width):
    values = ["" if value is None else str(value) for value in (row or [])]
    if len(values) < width:
        values += [""] * (width - len(values))
    if len(values) > width:
        values = values[:width]
    return values
