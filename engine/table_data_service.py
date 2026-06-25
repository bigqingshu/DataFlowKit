# -*- coding: utf-8 -*-
"""Backend table listing, loading, editing, and paging service."""

from __future__ import annotations

import csv
import copy
import io
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from db.table_manager import TableAccessManager
from engine.issue_schema import has_error_issues, make_issue
from engine.models import TableData
from engine.table_io import load_table_file


TABLE_SAVE_MODES = [
    {
        "id": "replace",
        "label": "覆盖同名表",
        "description": "同名表存在时删除后重建；不存在时新建。",
    },
    {
        "id": "timestamp",
        "label": "自动加时间戳",
        "description": "同名表存在时另存为带时间戳的新表。",
    },
    {
        "id": "fail",
        "label": "存在则报错",
        "description": "同名表存在时停止保存并返回错误。",
    },
    {
        "id": "append",
        "label": "追加",
        "description": "追加到已有表；不存在时新建。",
    },
]
DATA_SOURCE_STATE_SCHEMA_VERSION = "data_source_state.v1"
DATA_SOURCE_ACTIONS_SCHEMA_VERSION = "data_source_actions.v1"
DATA_SOURCE_ACTION_SCHEMA_VERSION = "data_source_action_schema.v1"
DATA_SOURCE_SERVICE_SCHEMA_VERSION = "data_source_service.v1"
DATA_SOURCE_PANEL_STATE_SCHEMA_VERSION = "data_source_panel_state.v1"
DATA_SOURCE_MANAGER_STATE_SCHEMA_VERSION = "data_source_manager_state.v1"
DATA_SOURCE_MANAGER_LAYOUT_SCHEMA_VERSION = "data_source_manager_layout.v1"
DATA_SOURCE_MANAGER_UI_HINTS_SCHEMA_VERSION = "data_source_manager_ui_hints.v1"
DATA_SOURCE_CLIENT_PROFILES_SCHEMA_VERSION = "data_source_client_profiles.v1"
DATA_SOURCE_TRANSPORT_HINTS_SCHEMA_VERSION = "data_source_transport_hints.v1"
DATA_SOURCE_PROTOCOL_FAMILY = "data_source_service"
TABLE_SAVE_MODES_SCHEMA_VERSION = "table_save_modes.v1"

_SAVE_MODE_ALIASES = {}
for _mode in TABLE_SAVE_MODES:
    _SAVE_MODE_ALIASES[_mode["id"]] = _mode["id"]
    _SAVE_MODE_ALIASES[_mode["label"]] = _mode["id"]
_SAVE_MODE_ALIASES.update({
    "": "replace",
    "overwrite": "replace",
    "replace_table": "replace",
    "覆盖": "replace",
    "覆盖表": "replace",
    "覆盖整表": "replace",
    "auto_timestamp": "timestamp",
    "timestamp_new": "timestamp",
    "自动加时间戳新表": "timestamp",
    "new": "fail",
    "create_new": "fail",
    "fail_if_exists": "fail",
    "报错停止": "fail",
    "不覆盖，存在则报错": "fail",
    "追加写入": "append",
    "追加到已有表": "append",
})


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

    def search_table(self, table, keyword, *, current_index=-1, offset=0, reset=True):
        matches = search_table(table, keyword)
        navigation = build_search_navigation(
            matches,
            current_index=current_index,
            offset=offset,
            reset=reset,
        )
        return {
            "ok": True,
            "keyword": str(keyword or ""),
            "matches": matches,
            "count": len(matches),
            "cell_count": navigation["count"],
            "navigation": navigation,
            "issues": [],
        }

    def build_table_search_navigation(self, matches, *, current_index=-1, offset=0, reset=False):
        return {
            "ok": True,
            "navigation": build_search_navigation(
                matches,
                current_index=current_index,
                offset=offset,
                reset=reset,
            ),
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

    def describe_data_source_actions(self, table=None, *, source=None, dirty=False):
        action_state = build_data_source_action_state(
            table or {},
            source=source,
            dirty=dirty,
        )
        return {
            "ok": True,
            "action_state": action_state,
            "actions": dict(action_state.get("actions") or {}),
            "action_schema": describe_data_source_action_schema(),
            "issues": [],
        }

    def build_data_source_panel_state(
        self,
        table=None,
        *,
        source=None,
        dirty=False,
        display_name="",
        partial=False,
        page_info=None,
        search_navigation=None,
    ):
        return {
            "ok": True,
            "panel_state": build_data_source_panel_state(
                table or {},
                source=source,
                dirty=dirty,
                display_name=display_name,
                partial=partial,
                page_info=page_info,
                search_navigation=search_navigation,
            ),
            "issues": [],
        }

    def build_data_source_manager_state(
        self,
        table=None,
        *,
        source=None,
        dirty=False,
        display_name="",
        partial=False,
        page_info=None,
        search_navigation=None,
        db_path="",
        table_names=None,
        selected_table="",
    ):
        state = self.build_data_source_panel_state(
            table,
            source=source,
            dirty=dirty,
            display_name=display_name,
            partial=partial,
            page_info=page_info,
            search_navigation=search_navigation,
        ).get("panel_state") or {}
        service = describe_data_source_service()
        action_schema = service.get("action_schema") if isinstance(service.get("action_schema"), dict) else describe_data_source_action_schema()
        table_save_modes = self.describe_table_save_modes()
        db_path_text = str(db_path or "").strip()
        table_names_list = [str(item).strip() for item in (table_names or []) if str(item).strip()]
        selected_table_name = str(selected_table or "").strip()
        if not selected_table_name:
            source_payload = state.get("source") if isinstance(state.get("source"), dict) else {}
            selected_table_name = str(source_payload.get("table_name") or source_payload.get("table") or "").strip()
        layout = describe_data_source_manager_layout()
        ui_hints = describe_data_source_manager_ui_hints()
        manager_state = {
            "schema_version": DATA_SOURCE_MANAGER_STATE_SCHEMA_VERSION,
            "protocol_family": DATA_SOURCE_PROTOCOL_FAMILY,
            "panel_state": copy.deepcopy(state),
            "layout": layout,
            "ui_hints": ui_hints,
            "service": {
                "schema_version": service.get("schema_version"),
                "protocol_family": service.get("protocol_family"),
                "service_id": service.get("service_id"),
                "capabilities": copy.deepcopy(service.get("capabilities") or {}),
                "action_ids": sorted(str(key) for key in (service.get("actions") or {}).keys()),
                "data_action_ids": sorted(str(key) for key in (service.get("data_actions") or {}).keys()),
                "table_action_ids": sorted(str(key) for key in (service.get("table_actions") or {}).keys()),
                "client_profiles": copy.deepcopy(service.get("client_profiles") or {}),
                "transport_hints": copy.deepcopy(service.get("transport_hints") or {}),
                "result_schemas": copy.deepcopy(service.get("result_schemas") or {}),
            },
            "action_schema": {
                "schema_version": action_schema.get("schema_version"),
                "action_ids": sorted(str(key) for key in (action_schema.get("actions") or {}).keys()),
                "result_schemas": copy.deepcopy(action_schema.get("result_schemas") or {}),
            },
            "save_modes": {
                "schema_version": str(table_save_modes.get("schema_version") or ""),
                "default_mode": str(table_save_modes.get("default_mode") or "replace"),
                "modes": copy.deepcopy(table_save_modes.get("modes") or []),
                "mode_field": copy.deepcopy(table_save_modes.get("mode_field") or {}),
            },
            "source_controls": {
                "db_path": db_path_text,
                "table_names": table_names_list,
                "selected_table": selected_table_name,
                "has_database": bool(db_path_text),
                "has_tables": bool(table_names_list),
                "load_enabled": bool(db_path_text and selected_table_name),
            },
        }
        return {
            "ok": True,
            "manager_state": manager_state,
            "issues": [],
        }

    def describe_data_source_service(self):
        described = describe_data_source_service()
        described["ok"] = True
        described["issues"] = []
        return described

    def describe_table_save_modes(self):
        return {
            "ok": True,
            "schema_version": TABLE_SAVE_MODES_SCHEMA_VERSION,
            "default_mode": "replace",
            "modes": describe_save_modes(),
            "mode_field": {
                "key": "mode",
                "label": "保存模式",
                "type": "select",
                "choices_source": "modes",
                "default": "replace",
            },
            "issues": [],
        }

    def normalize_table_save_mode(self, mode):
        try:
            normalized = normalize_save_mode(mode)
        except ValueError as exc:
            return self._failure("invalid_save_mode", str(exc), "/mode")
        return {
            "ok": True,
            "mode": normalized,
            "issues": [],
        }

    def save_table(self, table=None, *, db_path=None, table_name=None, mode="replace"):
        target_db = self._resolve_db_path(db_path)
        table_data = TableData.from_payload(table or {}).to_dict()
        issues = []
        try:
            save_mode = normalize_save_mode(mode)
        except ValueError as exc:
            issues.append(make_issue("error", "invalid_save_mode", str(exc), path="/mode", source="TableDataService"))
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
                mode=save_mode,
            )
        except Exception as exc:
            return self._failure("save_table_failed", str(exc), "/table")
        actual_name = result.get("table_name") or str(table_name or "").strip()
        saved_source = {"type": "sqlite", "db_path": target_db, "table_name": actual_name}
        return {
            "ok": True,
            "db_path": target_db,
            "table_name": actual_name,
            "mode": save_mode,
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


def flatten_search_matches(matches):
    flattened = []
    for item in matches or []:
        if not isinstance(item, dict):
            continue
        try:
            row = int(item.get("row", 0) or 0)
        except (TypeError, ValueError):
            continue
        cells = [cell for cell in (item.get("cells") or []) if isinstance(cell, dict)]
        if not cells:
            try:
                column = int(item.get("column", 0) or 0)
            except (TypeError, ValueError):
                column = 0
            flattened.append({
                "row": row,
                "column": column,
                "header": str(item.get("header", "") or ""),
                "value": "" if item.get("value") is None else str(item.get("value")),
            })
            continue
        for cell in cells:
            try:
                column = int(cell.get("column", 0) or 0)
            except (TypeError, ValueError):
                column = 0
            flattened.append({
                "row": row,
                "column": column,
                "header": str(cell.get("header", "") or ""),
                "value": "" if cell.get("value") is None else str(cell.get("value")),
            })
    return flattened


def build_search_navigation(matches, *, current_index=-1, offset=0, reset=False):
    flattened = flatten_search_matches(matches)
    count = len(flattened)
    if not count:
        return {
            "matches": [],
            "count": 0,
            "row_count": 0,
            "current_index": -1,
            "current_match": None,
            "current_cell": None,
            "highlighted_rows": [],
            "found": False,
            "status_text": "未找到",
        }

    try:
        base_index = int(current_index)
    except (TypeError, ValueError):
        base_index = -1
    try:
        step = int(offset)
    except (TypeError, ValueError):
        step = 0

    if bool(reset) or base_index < 0:
        index = 0
    else:
        index = base_index + step
    index = index % count
    current = flattened[index]
    row = int(current.get("row", 0) or 0)
    column = int(current.get("column", 0) or 0)
    highlighted_rows = sorted({int(item.get("row", 0) or 0) for item in flattened})
    return {
        "matches": flattened,
        "count": count,
        "row_count": len(highlighted_rows),
        "current_index": index,
        "current_match": dict(current),
        "current_cell": {"row": row, "column": column},
        "highlighted_rows": highlighted_rows,
        "found": True,
        "status_text": f"{index + 1}/{count}",
    }


def describe_save_modes():
    return [dict(mode) for mode in TABLE_SAVE_MODES]


def normalize_save_mode(mode):
    text = str(mode or "").strip()
    if text in _SAVE_MODE_ALIASES:
        return _SAVE_MODE_ALIASES[text]
    lower = text.lower()
    if lower in _SAVE_MODE_ALIASES:
        return _SAVE_MODE_ALIASES[lower]
    try:
        backend = TableAccessManager.sqlite_backend_write_mode(text)
    except ValueError:
        backend = ""
    if backend in {"replace", "timestamp", "fail", "append"}:
        return backend
    raise ValueError(f"不支持的 SQLite 保存模式：{mode}")


def build_data_source_state(table=None, *, source=None, dirty=False, display_name=""):
    table_data = TableData.from_payload(table or {}).to_dict()
    headers = list(table_data.get("headers") or [])
    rows = [list(row) for row in (table_data.get("rows") or [])]
    source_payload = dict(source or {})
    title = str(display_name or source_payload.get("table_name") or source_payload.get("path") or "输入数据源")
    action_state = build_data_source_action_state(
        {"type": "table", "headers": headers, "rows": rows},
        source=source_payload,
        dirty=dirty,
    )
    return {
        "schema_version": DATA_SOURCE_STATE_SCHEMA_VERSION,
        "source": source_payload,
        "source_type": str(source_payload.get("type") or "memory"),
        "headers": headers,
        "rows": rows,
        "table": {"type": "table", "headers": headers, "rows": rows},
        "shape": {"rows": len(rows), "columns": len(headers)},
        "dirty": bool(dirty),
        "display_name": title,
        "row_count": len(rows),
        "column_count": len(headers),
        "action_state": action_state,
    }


def build_data_source_panel_state(
    table=None,
    *,
    source=None,
    dirty=False,
    display_name="",
    partial=False,
    page_info=None,
    search_navigation=None,
):
    state = build_data_source_state(
        table or {},
        source=source,
        dirty=dirty,
        display_name=display_name,
    )
    action_state = state.get("action_state") or {}
    service = describe_data_source_service()
    action_schema = service.get("action_schema") if isinstance(service.get("action_schema"), dict) else describe_data_source_action_schema()
    save_modes = {
        "schema_version": TABLE_SAVE_MODES_SCHEMA_VERSION,
        "default_mode": "replace",
        "modes": describe_save_modes(),
        "mode_field": {
            "key": "mode",
            "label": "保存模式",
            "type": "select",
            "choices_source": "modes",
            "default": "replace",
        },
    }
    page = page_info if isinstance(page_info, dict) else {}
    search = search_navigation if isinstance(search_navigation, dict) else {}
    source_payload = state.get("source") if isinstance(state.get("source"), dict) else {}
    table_name = str(source_payload.get("table_name") or source_payload.get("table") or "").strip()
    db_path = str(source_payload.get("db_path") or "").strip()
    display_name_text = str(state.get("display_name") or display_name or table_name or "输入数据源").strip()
    rows = int(state.get("row_count") or 0)
    columns = int(state.get("column_count") or 0)
    dirty_note = "，未保存" if dirty else ""
    partial_note = "，分页预览" if partial else ""
    page_state = copy_page_info(page)
    source_type = str(state.get("source_type") or source_payload.get("type") or "memory")
    view_state = {
        "title": display_name_text,
        "source_type": source_type,
        "table_name": table_name,
        "db_path": db_path,
        "shape_text": f"{rows} 行 x {columns} 列",
        "status_text": f"{display_name_text}：{rows} 行 x {columns} 列{partial_note}{dirty_note}",
        "dirty_text": "未保存" if dirty else "",
        "partial": bool(partial),
        "page": page_state,
        "page_status_text": build_data_source_page_status_text(
            rows=rows,
            source_type=source_type,
            partial=partial,
            page=page_state,
        ),
        "page_controls": build_data_source_page_controls(
            source_type=source_type,
            table_name=table_name,
            db_path=db_path,
            partial=partial,
            page=page_state,
        ),
        "search": copy_search_navigation(search),
        "action_enabled": {
            key: bool((value or {}).get("enabled"))
            for key, value in (action_state.get("actions") or {}).items()
            if isinstance(value, dict)
        },
    }
    return {
        "schema_version": DATA_SOURCE_PANEL_STATE_SCHEMA_VERSION,
        "protocol_family": DATA_SOURCE_PROTOCOL_FAMILY,
        "state": state,
        "source": source_payload,
        "dirty": bool(dirty),
        "partial": bool(partial),
        "shape": copy.deepcopy(state.get("shape") or {}),
        "action_state": copy.deepcopy(action_state),
        "service": {
            "schema_version": service.get("schema_version"),
            "protocol_family": service.get("protocol_family"),
            "service_id": service.get("service_id"),
            "capabilities": copy.deepcopy(service.get("capabilities") or {}),
            "action_ids": sorted(str(key) for key in (service.get("actions") or {}).keys()),
            "data_action_ids": sorted(str(key) for key in (service.get("data_actions") or {}).keys()),
            "table_action_ids": sorted(str(key) for key in (service.get("table_actions") or {}).keys()),
            "client_profiles": copy.deepcopy(service.get("client_profiles") or {}),
            "transport_hints": copy.deepcopy(service.get("transport_hints") or {}),
            "result_schemas": copy.deepcopy(service.get("result_schemas") or {}),
        },
        "action_schema": {
            "schema_version": action_schema.get("schema_version"),
            "action_ids": sorted(str(key) for key in (action_schema.get("actions") or {}).keys()),
            "result_schemas": copy.deepcopy(action_schema.get("result_schemas") or {}),
        },
        "save_modes": {
            "schema_version": save_modes.get("schema_version"),
            "mode_ids": [str(item.get("id") or "") for item in save_modes.get("modes") or [] if str(item.get("id") or "")],
            "mode_field": copy.deepcopy(save_modes.get("mode_field") or {}),
        },
        "view_state": view_state,
    }


def copy_page_info(page):
    return {
        "offset": int(page.get("offset") or 0) if isinstance(page, dict) else 0,
        "limit": page.get("limit") if isinstance(page, dict) else None,
        "has_more": bool(page.get("has_more")) if isinstance(page, dict) else False,
        "total_rows": page.get("total_rows") if isinstance(page, dict) else None,
    }


def build_data_source_page_status_text(*, rows=0, source_type="", partial=False, page=None):
    page = copy_page_info(page or {})
    if partial:
        limit_text = page["limit"] if page["limit"] is not None else "未指定"
        if rows:
            start = page["offset"] + 1
            end = page["offset"] + int(rows or 0)
            text = f"分页预览：第 {start}-{end} 行，每页 {limit_text}"
        else:
            text = f"分页预览：偏移 {page['offset']} 无数据，每页 {limit_text}"
        return text + ("，还有下一页" if page["has_more"] else "，已到末页")
    if str(source_type or "") == "sqlite":
        return "分页预览：当前为完整表"
    return "分页预览：未载入"


def build_data_source_page_controls(*, source_type="", table_name="", db_path="", partial=False, page=None):
    page = copy_page_info(page or {})
    can_page = str(source_type or "") == "sqlite" and bool(str(db_path or "").strip()) and bool(str(table_name or "").strip())
    return {
        "can_page": can_page,
        "page_size_enabled": can_page,
        "prev_enabled": bool(partial and page["offset"] > 0),
        "next_enabled": bool(partial and page["has_more"]),
        "load_full_enabled": can_page,
    }


def copy_search_navigation(search):
    if not isinstance(search, dict):
        return {}
    return {
        "keyword": str(search.get("keyword") or ""),
        "status_text": str(search.get("status_text") or ""),
        "current_index": search.get("current_index", -1),
        "count": search.get("count", 0),
        "current_cell": copy.deepcopy(search.get("current_cell") or {}),
        "highlighted_rows": list(search.get("highlighted_rows") or []),
    }


def build_data_source_action_state(table=None, *, source=None, dirty=False):
    table_data = TableData.from_payload(table or {}).to_dict()
    headers = list(table_data.get("headers") or [])
    rows = [list(row) for row in (table_data.get("rows") or [])]
    source_payload = dict(source or {})
    source_type = str(source_payload.get("type") or "memory")
    has_headers = bool(headers)
    has_rows = bool(rows)
    has_table = has_headers or has_rows
    is_sqlite_source = bool(
        source_type == "sqlite"
        and str(source_payload.get("db_path") or "").strip()
        and str(source_payload.get("table_name") or "").strip()
    )

    def action(label, enabled=True, **extra):
        payload = {"label": label, "enabled": bool(enabled)}
        payload.update(extra)
        return payload

    actions = {
        "load_clipboard": action("读取剪贴板"),
        "import_file": action("导入文件"),
        "clear_table": action("清空", enabled=has_table),
        "promote_first_row": action("首行作字段名", enabled=has_rows),
        "search_table": action("搜索", enabled=has_table),
        "patch_cell": action("编辑单元格", enabled=has_headers and has_rows),
        "save_sqlite": action(
            "保存到 SQLite",
            enabled=has_headers,
            requires=["db_path", "table_name"],
            mode_source="describe_table_save_modes",
        ),
        "delete_sqlite": action(
            "删除 SQLite 表",
            enabled=is_sqlite_source,
            requires=["db_path", "table_name", "confirmed"],
            requires_confirmation=True,
        ),
        "apply_to_workflow": action("设置为工作流输入", enabled=has_headers),
    }
    return {
        "schema_version": DATA_SOURCE_ACTIONS_SCHEMA_VERSION,
        "source": source_payload,
        "source_type": source_type,
        "dirty": bool(dirty),
        "has_table": has_table,
        "has_headers": has_headers,
        "has_rows": has_rows,
        "is_sqlite_source": is_sqlite_source,
        "actions": actions,
    }


def describe_data_source_action_schema():
    data_actions = _describe_data_source_data_actions()
    return {
        "schema_version": DATA_SOURCE_ACTION_SCHEMA_VERSION,
        "protocol_family": DATA_SOURCE_PROTOCOL_FAMILY,
        "actions": {
            "load_clipboard": {
                "engine_action": "parse_clipboard_table",
                "inputs": [
                    {"key": "text", "type": "text", "required": True, "source": "clipboard"},
                    {"key": "first_row_header", "type": "bool", "default": True},
                ],
                "result": "data_source_state",
            },
            "import_file": {
                "engine_action": "import_table_file",
                "inputs": [
                    {"key": "path", "type": "path", "required": True},
                ],
                "result": "table_page",
            },
            "clear_table": {
                "engine_action": "build_data_source_state",
                "inputs": [],
                "result": "data_source_state",
            },
            "promote_first_row": {
                "engine_action": "promote_first_row_to_headers",
                "inputs": [
                    {"key": "table", "type": "table", "required": True},
                ],
                "result": "data_source_state",
            },
            "search_table": {
                "engine_action": "search_table",
                "inputs": [
                    {"key": "table", "type": "table", "required": True},
                    {"key": "keyword", "type": "text", "required": True},
                    {"key": "current_index", "type": "number", "default": -1},
                    {"key": "offset", "type": "number", "default": 0},
                    {"key": "reset", "type": "bool", "default": True},
                ],
                "result": "search_navigation",
            },
            "patch_cell": {
                "engine_action": "patch_table_cell",
                "inputs": [
                    {"key": "table", "type": "table", "required": True},
                    {"key": "row", "type": "number", "required": True},
                    {"key": "column", "type": "number", "required": True},
                    {"key": "value", "type": "text", "default": ""},
                ],
                "result": "data_source_state",
            },
            "save_sqlite": {
                "engine_action": "save_table",
                "inputs": [
                    {"key": "table", "type": "table", "required": True},
                    {"key": "db_path", "type": "path", "required": True},
                    {"key": "table_name", "type": "text", "required": True},
                    {"key": "mode", "type": "select", "default": "replace", "options_source": "describe_table_save_modes"},
                ],
                "result": "data_source_state",
            },
            "delete_sqlite": {
                "engine_action": "delete_table",
                "inputs": [
                    {"key": "db_path", "type": "path", "required": True},
                    {"key": "table_name", "type": "text", "required": True},
                    {"key": "backup", "type": "bool", "default": True},
                    {"key": "confirmed", "type": "bool", "required": True},
                ],
                "requires_confirmation": True,
                "result": "delete_result",
            },
            "apply_to_workflow": {
                "engine_action": "build_data_source_state",
                "inputs": [
                    {"key": "table", "type": "table", "required": True},
                    {"key": "source", "type": "object"},
                    {"key": "dirty", "type": "bool", "default": False},
                    {"key": "display_name", "type": "text", "default": ""},
                ],
                "result": "data_source_state",
            },
            **data_actions,
        },
        "result_schemas": {
            "data_source_state": {"schema_version": DATA_SOURCE_STATE_SCHEMA_VERSION},
            "data_source_actions": {"schema_version": DATA_SOURCE_ACTIONS_SCHEMA_VERSION},
            "data_source_manager_state": {"schema_version": DATA_SOURCE_MANAGER_STATE_SCHEMA_VERSION},
            "table_save_modes": {"schema_version": TABLE_SAVE_MODES_SCHEMA_VERSION},
            "table_page": {"schema_version": "table_page.v1"},
            "table_handle": {"schema_version": "table_handle.v1"},
            "table_handle_list": {"schema_version": "table_handle_list.v1"},
            "table_handle_release": {"schema_version": "table_handle_release.v1"},
        },
    }


def _describe_data_source_data_actions():
    return {
        "list_tables": {
            "engine_action": "list_tables",
            "inputs": [
                {"key": "db_path", "type": "path"},
            ],
            "result": "table_list",
        },
        "load_table": {
            "engine_action": "load_table",
            "inputs": [
                {"key": "source", "type": "object"},
                {"key": "db_path", "type": "path"},
                {"key": "table_name", "type": "text"},
                {"key": "path", "type": "path"},
                {"key": "limit", "type": "number"},
                {"key": "offset", "type": "number", "default": 0},
            ],
            "result": "table_page",
        },
        "get_table_page": {
            "engine_action": "get_table_page",
            "inputs": [
                {"key": "table", "type": "table_or_handle", "required": True},
                {"key": "source", "type": "object"},
                {"key": "limit", "type": "number"},
                {"key": "offset", "type": "number", "default": 0},
            ],
            "result": "table_page",
        },
        "create_table_handle": {
            "engine_action": "create_table_handle",
            "inputs": [
                {"key": "table", "type": "table"},
                {"key": "source", "type": "object"},
                {"key": "db_path", "type": "path"},
                {"key": "table_name", "type": "text"},
                {"key": "path", "type": "path"},
                {"key": "limit", "type": "number"},
                {"key": "offset", "type": "number", "default": 0},
            ],
            "result": "table_handle",
        },
        "get_table_handle_page": {
            "engine_action": "get_table_handle_page",
            "inputs": [
                {"key": "handle", "type": "text", "required": True},
                {"key": "limit", "type": "number"},
                {"key": "offset", "type": "number", "default": 0},
            ],
            "result": "table_page",
        },
        "list_table_handles": {
            "engine_action": "list_table_handles",
            "inputs": [],
            "result": "table_handle_list",
        },
        "release_table_handle": {
            "engine_action": "release_table_handle",
            "inputs": [
                {"key": "handle", "type": "text", "required": True},
            ],
            "result": "table_handle_release",
        },
    }


def describe_data_source_manager_layout():
    sections = [
        {
            "section_id": "toolbar",
            "title": "数据操作",
            "role": "primary_actions",
            "action_ids": ["load_clipboard", "import_file", "clear_table", "promote_first_row", "apply_to_workflow"],
        },
        {
            "section_id": "database",
            "title": "数据库",
            "role": "source_selector",
            "fields": ["db_path"],
            "action_ids": ["list_tables"],
        },
        {
            "section_id": "table_loader",
            "title": "载入表",
            "role": "table_selector",
            "fields": ["selected_table"],
            "action_ids": ["load_table", "create_table_handle"],
        },
        {
            "section_id": "paging",
            "title": "分页",
            "role": "table_paging",
            "fields": ["page_size"],
            "action_ids": ["get_table_handle_page", "get_table_page"],
        },
        {
            "section_id": "save",
            "title": "保存",
            "role": "sqlite_write",
            "fields": ["table_name", "mode"],
            "action_ids": ["save_sqlite", "delete_sqlite"],
        },
        {
            "section_id": "search",
            "title": "搜索",
            "role": "table_search",
            "fields": ["keyword"],
            "action_ids": ["search_table", "build_table_search_navigation"],
        },
        {
            "section_id": "table",
            "title": "表格",
            "role": "table_editor",
            "action_ids": ["patch_cell"],
        },
        {
            "section_id": "status",
            "title": "状态",
            "role": "feedback",
            "fields": ["status_text", "page_status_text", "search_status_text"],
        },
    ]
    return {
        "schema_version": DATA_SOURCE_MANAGER_LAYOUT_SCHEMA_VERSION,
        "protocol_family": DATA_SOURCE_PROTOCOL_FAMILY,
        "default_section_id": "table",
        "section_order": [section["section_id"] for section in sections],
        "sections": sections,
        "preferred_navigation": "stacked_rows",
    }


def describe_data_source_manager_ui_hints():
    return {
        "schema_version": DATA_SOURCE_MANAGER_UI_HINTS_SCHEMA_VERSION,
        "protocol_family": DATA_SOURCE_PROTOCOL_FAMILY,
        "display_mode": "tool_window",
        "density": "compact",
        "default_focus": "table",
        "section_hints": {
            "toolbar": {
                "description": "放置剪贴板、导入、清空、字段提升和设置为工作流输入等主操作。",
                "placement": "top",
            },
            "database": {
                "description": "选择或输入 SQLite 数据库路径，并触发表列表刷新。",
                "placement": "top",
            },
            "table_loader": {
                "description": "从当前数据库选择并载入 SQLite 表。",
                "placement": "top",
                "empty_text": "当前数据库没有可选表。",
            },
            "paging": {
                "description": "对大型 SQLite 表使用分页预览，必要时载入完整表。",
                "placement": "top",
            },
            "save": {
                "description": "将当前表保存到 SQLite，或删除已选择的 SQLite 表。",
                "placement": "top",
                "warning": "删除 SQLite 表需要确认；保存模式由 table_save_modes.v1 描述。",
            },
            "search": {
                "description": "搜索当前表，并通过 search_navigation.v1 定位单元格和高亮行。",
                "placement": "top",
            },
            "table": {
                "description": "显示和编辑当前表格；分页预览状态下默认禁止直接编辑。",
                "placement": "center",
            },
            "status": {
                "description": "显示载入、保存、分页、搜索和编辑状态。",
                "placement": "bottom",
            },
        },
        "action_prominence": {
            "apply_to_workflow": "primary",
            "save_sqlite": "primary",
            "delete_sqlite": "danger",
            "load_clipboard": "secondary",
            "import_file": "secondary",
            "search_table": "secondary",
        },
    }


def describe_data_source_client_profiles():
    profiles = {
        "qt_embedded": {
            "label": "Qt 直连客户端",
            "transport": "in_process",
            "recommended_actions": [
                "describe_data_source_service",
                "build_data_source_manager_state",
                "list_tables",
                "create_table_handle",
                "get_table_handle_page",
                "release_table_handle",
                "save_table",
                "delete_table",
            ],
            "table_strategy": "use_handle_for_sqlite_pages",
            "state_strategy": "consume_manager_state",
            "release_required": True,
        },
        "stdio_desktop": {
            "label": "stdio 桌面客户端",
            "transport": "json_stdio",
            "recommended_actions": [
                "describe_data_source_service",
                "build_data_source_manager_state",
                "list_tables",
                "create_table_handle",
                "get_table_handle_page",
                "release_table_handle",
            ],
            "table_strategy": "avoid_full_table_payloads",
            "state_strategy": "consume_manager_state",
            "release_required": True,
        },
        "dotnet_desktop": {
            "label": ".NET 桌面客户端",
            "transport": "json_stdio_or_local_bridge",
            "recommended_actions": [
                "describe_data_source_service",
                "describe_data_source_actions",
                "build_data_source_manager_state",
                "create_table_handle",
                "get_table_handle_page",
                "release_table_handle",
            ],
            "table_strategy": "page_with_handle_then_apply_to_workflow",
            "state_strategy": "render_from_layout_and_ui_hints",
            "release_required": True,
        },
        "web_remote": {
            "label": "Web/远程客户端",
            "transport": "json_rpc",
            "recommended_actions": [
                "describe_data_source_service",
                "build_data_source_manager_state",
                "create_table_handle",
                "get_table_handle_page",
                "release_table_handle",
            ],
            "table_strategy": "handle_pages_only",
            "state_strategy": "render_from_layout_and_ui_hints",
            "release_required": True,
        },
    }
    return {
        "schema_version": DATA_SOURCE_CLIENT_PROFILES_SCHEMA_VERSION,
        "protocol_family": DATA_SOURCE_PROTOCOL_FAMILY,
        "default_profile": "stdio_desktop",
        "profiles": profiles,
    }


def describe_data_source_transport_hints():
    return {
        "schema_version": DATA_SOURCE_TRANSPORT_HINTS_SCHEMA_VERSION,
        "protocol_family": DATA_SOURCE_PROTOCOL_FAMILY,
        "table_transfer": {
            "preferred_action": "create_table_handle",
            "page_action": "get_table_handle_page",
            "release_action": "release_table_handle",
            "inline_action": "get_table_page",
            "prefer_handle_when": ["sqlite_source", "unknown_row_count", "remote_or_stdio_client"],
            "page_size_default": 200,
            "page_size_max_hint": 2000,
        },
        "lifecycle": {
            "release_required": True,
            "release_when": ["manager_closed", "source_changed", "full_table_loaded", "workflow_input_applied"],
            "list_action": "list_table_handles",
        },
        "editing": {
            "cell_patch_action": "patch_cell",
            "paged_table_editing": "readonly_until_full_table_loaded",
            "save_action": "save_sqlite",
            "apply_action": "apply_to_workflow",
        },
        "confirmation": {
            "delete_sqlite": {
                "requires_confirmation": True,
                "confirmation_field": "confirmed",
                "danger": True,
            },
        },
        "state_payloads": {
            "manager_state_action": "build_data_source_manager_state",
            "panel_state_action": "build_data_source_panel_state",
            "layout_schema": DATA_SOURCE_MANAGER_LAYOUT_SCHEMA_VERSION,
            "ui_hints_schema": DATA_SOURCE_MANAGER_UI_HINTS_SCHEMA_VERSION,
        },
    }


def describe_data_source_service():
    action_schema = describe_data_source_action_schema()
    actions = action_schema.get("actions") or {}
    table_actions = _describe_data_source_data_actions()
    client_profiles = describe_data_source_client_profiles()
    transport_hints = describe_data_source_transport_hints()
    data_actions = {
        key: value
        for key, value in actions.items()
        if key not in table_actions
    }
    return {
        "schema_version": DATA_SOURCE_SERVICE_SCHEMA_VERSION,
        "protocol_family": DATA_SOURCE_PROTOCOL_FAMILY,
        "service_id": "table_data_service",
        "title": "输入数据源共享服务",
        "summary": "UI 无关的数据源解析、编辑、搜索、分页和 SQLite 保存/删除协议。",
        "capabilities": {
            "clipboard_parse": True,
            "file_import": True,
            "table_paging": True,
            "table_handles": True,
            "cell_edit": True,
            "search_navigation": True,
            "sqlite_save": True,
            "sqlite_delete": True,
            "action_state": True,
            "panel_state": True,
            "manager_layout": True,
            "manager_ui_hints": True,
            "client_profiles": True,
            "transport_hints": True,
        },
        "actions": {
            "describe_data_source_service": {
                "engine_action": "describe_data_source_service",
                "inputs": [],
                "result": "data_source_service",
            },
            "describe_data_source_actions": {
                "engine_action": "describe_data_source_actions",
                "inputs": [
                    {"key": "table", "type": "table"},
                    {"key": "source", "type": "object"},
                    {"key": "dirty", "type": "bool", "default": False},
                ],
                "result": "data_source_actions",
            },
            "build_data_source_panel_state": {
                "engine_action": "build_data_source_panel_state",
                "inputs": [
                    {"key": "table", "type": "table"},
                    {"key": "source", "type": "object"},
                    {"key": "dirty", "type": "bool", "default": False},
                    {"key": "display_name", "type": "text", "default": ""},
                    {"key": "partial", "type": "bool", "default": False},
                    {"key": "page_info", "type": "object"},
                    {"key": "search_navigation", "type": "object"},
                ],
                "result": "data_source_panel_state",
            },
            "build_data_source_manager_state": {
                "engine_action": "build_data_source_manager_state",
                "inputs": [
                    {"key": "table", "type": "table"},
                    {"key": "source", "type": "object"},
                    {"key": "dirty", "type": "bool", "default": False},
                    {"key": "display_name", "type": "text", "default": ""},
                    {"key": "partial", "type": "bool", "default": False},
                    {"key": "page_info", "type": "object"},
                    {"key": "search_navigation", "type": "object"},
                    {"key": "db_path", "type": "path"},
                    {"key": "table_names", "type": "list"},
                    {"key": "selected_table", "type": "text", "default": ""},
                ],
                "result": "data_source_manager_state",
            },
            "describe_table_save_modes": {
                "engine_action": "describe_table_save_modes",
                "inputs": [],
                "result": "table_save_modes",
            },
            "normalize_table_save_mode": {
                "engine_action": "normalize_table_save_mode",
                "inputs": [
                    {"key": "mode", "type": "text", "default": "replace"},
                ],
                "result": "table_save_mode",
            },
        },
        "data_actions": data_actions,
        "table_actions": table_actions,
        "client_profiles": client_profiles,
        "transport_hints": transport_hints,
        "action_schema": action_schema,
        "save_modes": {
            "schema_version": TABLE_SAVE_MODES_SCHEMA_VERSION,
            "default_mode": "replace",
            "modes": describe_save_modes(),
        },
        "result_schemas": {
            "data_source_service": {"schema_version": DATA_SOURCE_SERVICE_SCHEMA_VERSION},
            "data_source_panel_state": {"schema_version": DATA_SOURCE_PANEL_STATE_SCHEMA_VERSION},
            "data_source_manager_state": {"schema_version": DATA_SOURCE_MANAGER_STATE_SCHEMA_VERSION},
            "data_source_manager_layout": {"schema_version": DATA_SOURCE_MANAGER_LAYOUT_SCHEMA_VERSION},
            "data_source_manager_ui_hints": {"schema_version": DATA_SOURCE_MANAGER_UI_HINTS_SCHEMA_VERSION},
            "data_source_client_profiles": {"schema_version": DATA_SOURCE_CLIENT_PROFILES_SCHEMA_VERSION},
            "data_source_transport_hints": {"schema_version": DATA_SOURCE_TRANSPORT_HINTS_SCHEMA_VERSION},
            "data_source_state": {"schema_version": DATA_SOURCE_STATE_SCHEMA_VERSION},
            "data_source_actions": {"schema_version": DATA_SOURCE_ACTIONS_SCHEMA_VERSION},
            "data_source_action_schema": {"schema_version": DATA_SOURCE_ACTION_SCHEMA_VERSION},
            "table_save_modes": {"schema_version": TABLE_SAVE_MODES_SCHEMA_VERSION},
            "table_page": {"schema_version": "table_page.v1"},
            "table_list": {"schema_version": "table_list.v1"},
            "table_handle": {"schema_version": "table_handle.v1"},
            "table_handle_list": {"schema_version": "table_handle_list.v1"},
            "table_handle_release": {"schema_version": "table_handle_release.v1"},
            "search_navigation": {"schema_version": "search_navigation.v1"},
            "delete_result": {"schema_version": "delete_result.v1"},
        },
    }


def _normalize_row(row, width):
    values = ["" if value is None else str(value) for value in (row or [])]
    if len(values) < width:
        values += [""] * (width - len(values))
    if len(values) > width:
        values = values[:width]
    return values
