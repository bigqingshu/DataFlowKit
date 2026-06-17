# -*- coding: utf-8 -*-
"""SQLite table access and permission management for DataFlowKit."""

import re
import sqlite3
from datetime import datetime

from core.data_utils import make_unique_headers as core_make_unique_headers
from core.text_utils import quote_ident as core_quote_ident
from shared.table_access_policy import extract_read_tables, table_pattern_matches


class _ClosingConnection(sqlite3.Connection):
    """sqlite3 context managers commit/rollback but do not close the file handle."""

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


class TableAccessManager:
    """
    表访问统一管理入口。

    第一阶段先统一 SQLite 读写、日志与进度事件；权限配置由工作流节点保存，
    后续映射窗口可以直接复用这里的权限检查和执行入口。
    """
    WRITE_MODE_ALIASES = {
        "": "",
        "current_table_default": "current_table_default",
        "append": "append",
        "追加": "append",
        "追加写入": "append",
        "追加到已有表": "append",
        "overlay": "overlay_by_order",
        "overlay_by_order": "overlay_by_order",
        "局部覆盖": "overlay_by_order",
        "局部覆盖，保留目标原行数": "overlay_by_order",
        "按顺序覆盖": "overlay_by_order",
        "update_by_key": "update_by_key",
        "按键更新": "update_by_key",
        "按匹配字段更新": "update_by_key",
        "upsert_by_key": "upsert_by_key",
        "追加或更新": "upsert_by_key",
        "匹配更新或追加": "upsert_by_key",
        "replace": "replace_table",
        "overwrite": "replace_table",
        "replace_table": "replace_table",
        "覆盖": "replace_table",
        "覆盖表": "replace_table",
        "覆盖整表": "replace_table",
        "覆盖同名表": "replace_table",
        "覆盖重建目标表": "replace_table",
        "按来源完整结构覆盖": "replace_table",
        "clear_keep_schema": "clear_keep_schema",
        "清空保留结构写入": "clear_keep_schema",
        "清空目标字段后覆盖，保留目标原行数": "clear_keep_schema",
        "keep_schema_insert": "keep_schema_insert",
        "保留结构写入": "keep_schema_insert",
        "write_fields_only": "write_fields_only",
        "指定字段写入": "write_fields_only",
        "fill_blank_fields": "fill_blank_fields",
        "字段空缺补齐": "fill_blank_fields",
        "create_new": "create_new",
        "新建表写入": "create_new",
        "timestamp": "timestamp_new",
        "auto_timestamp": "timestamp_new",
        "timestamp_new": "timestamp_new",
        "自动加时间戳": "timestamp_new",
        "自动加时间戳新表": "timestamp_new",
        "fail": "fail_if_exists",
        "new": "fail_if_exists",
        "fail_if_exists": "fail_if_exists",
        "报错停止": "fail_if_exists",
        "不覆盖，存在则报错": "fail_if_exists",
        "存在则报错": "fail_if_exists",
    }
    SQLITE_BACKEND_WRITE_MODES = {
        "append": "append",
        "replace_table": "replace",
        "timestamp_new": "timestamp",
        "create_new": "fail",
        "fail_if_exists": "fail",
    }
    TABLE_ACCESS_POLICY_ALIASES = {
        "": "audit",
        "audit": "audit",
        "只审计": "audit",
        "审计": "audit",
        "默认只审计": "audit",
        "log": "audit",
        "prompt": "prompt",
        "预检确认": "prompt",
        "确认": "prompt",
        "warn": "prompt",
        "strict": "strict",
        "enforce": "strict",
        "强制": "strict",
        "强制拦截": "strict",
        "拦截": "strict",
        "off": "off",
        "disabled": "off",
        "none": "off",
        "关闭": "off",
    }

    def __init__(self, db_path, node_id="", node_name="", node_type="", context=None, progress_callback=None,
                 table_access=None, permission_policy=None):
        self.db_path = db_path or ""
        self.node_id = str(node_id or "")
        self.node_name = str(node_name or "")
        self.node_type = str(node_type or "")
        self.context = context if isinstance(context, dict) else None
        self.progress_callback = progress_callback or ((self.context or {}).get("progress_callback") if self.context else None)
        current_info = (self.context or {}).get("current_node_info", {}) if self.context else {}
        if not isinstance(table_access, dict) and isinstance(current_info, dict):
            table_access = current_info.get("table_access")
        self.table_access = table_access if isinstance(table_access, dict) else {}
        self.permission_policy = self.normalize_permission_policy(
            permission_policy
            or ((self.context or {}).get("table_access_policy") if self.context else "")
            or "audit"
        )
        self.events = []

    @classmethod
    def normalize_permission_policy(cls, value):
        text = str(value or "").strip()
        return cls.TABLE_ACCESS_POLICY_ALIASES.get(text, cls.TABLE_ACCESS_POLICY_ALIASES.get(text.lower(), "audit"))

    @classmethod
    def normalize_write_mode(cls, mode):
        text = str(mode or "").strip()
        if text in cls.WRITE_MODE_ALIASES:
            return cls.WRITE_MODE_ALIASES[text]
        lower = text.lower()
        if lower in cls.WRITE_MODE_ALIASES:
            return cls.WRITE_MODE_ALIASES[lower]
        if "追加" in text and ("更新" in text or "匹配" in text):
            return "upsert_by_key"
        if "追加" in text:
            return "append"
        if "清空" in text:
            return "clear_keep_schema"
        if "时间戳" in text or "自动加" in text:
            return "timestamp_new"
        if "报错" in text or "不覆盖" in text or "存在则报错" in text:
            return "fail_if_exists"
        if "新建" in text and "时间戳" not in text:
            return "create_new"
        if "更新" in text or "匹配" in text:
            return "update_by_key"
        if "字段" in text or "局部" in text or "顺序" in text:
            return "overlay_by_order"
        if "覆盖" in text or "重建" in text:
            return "replace_table"
        return lower

    @classmethod
    def sqlite_backend_write_mode(cls, mode):
        standard = cls.normalize_write_mode(mode)
        backend = cls.SQLITE_BACKEND_WRITE_MODES.get(standard)
        if not backend:
            raise ValueError(f"当前写入入口不支持写入模式：{mode}")
        return backend

    @classmethod
    def required_permissions_for_write_mode(cls, mode, exists=False, partial=False):
        standard = cls.normalize_write_mode(mode)
        required = ["write_table"]
        if standard == "append":
            required.append("append_rows")
            if not exists:
                required.append("create_table")
        elif standard in {"create_new", "timestamp_new", "fail_if_exists"}:
            required.append("create_table")
        elif standard == "replace_table":
            required.append("replace_table" if exists else "create_table")
        elif standard == "clear_keep_schema":
            required.extend(["clear_table", "update_rows"])
            if not exists:
                required.append("create_table")
        elif standard in {"overlay_by_order", "write_fields_only", "fill_blank_fields"} or partial:
            required.append("update_rows")
            if not exists:
                required.append("create_table")
        elif standard == "update_by_key":
            required.extend(["read_table", "update_rows"])
        elif standard == "upsert_by_key":
            required.extend(["read_table", "update_rows", "append_rows"])
            if not exists:
                required.append("create_table")
        elif standard == "keep_schema_insert":
            if not exists:
                required.append("create_table")
        else:
            required.append("replace_table" if exists else "create_table")

        result = []
        for perm in required:
            if perm not in result:
                result.append(perm)
        return result

    def _log_event(self, operation, table_name="", status="ok", **extra):
        emit_progress = bool(extra.pop("emit_progress", True))
        event = {
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "node_id": self.node_id,
            "node_name": self.node_name,
            "node_type": self.node_type,
            "operation": operation,
            "table_name": table_name,
            "status": status,
        }
        event.update(extra)
        self.events.append(event)
        if self.context is not None:
            self.context.setdefault("table_access_logs", []).append(event)
        if emit_progress and callable(self.progress_callback):
            message = extra.get("message") or f"{operation} {table_name}".strip()
            try:
                self.progress_callback({
                    "type": "node_progress",
                    "node_name": self.node_type or self.node_name or "表访问",
                    "message": message,
                    "detail_message": message,
                    "table_operation": operation,
                    "table_name": table_name,
                })
            except Exception:
                pass

    def _ensure_db_path(self):
        if not self.db_path:
            raise ValueError("当前未设置 SQLite 数据库路径")

    def _connect(self):
        self._ensure_db_path()
        return sqlite3.connect(self.db_path, factory=_ClosingConnection)

    @staticmethod
    def quote_ident(name):
        return core_quote_ident(name)

    @staticmethod
    def make_unique_headers(headers):
        return core_make_unique_headers(headers)

    @staticmethod
    def format_value(value):
        if value is None:
            return ""
        if isinstance(value, bytes):
            return f"<BLOB {len(value)} bytes>"
        return str(value)

    @staticmethod
    def _sanitize_name_for_match(name):
        name = str(name or "").strip()
        if not name:
            return ""
        name = re.sub(r"\W+", "_", name, flags=re.UNICODE)
        if re.match(r"^\d", name):
            name = "t_" + name
        return name

    def is_permission_enforced(self):
        return self.permission_policy in {"strict", "enforce"}

    def _access_tables(self):
        tables = (self.table_access or {}).get("tables", [])
        return tables if isinstance(tables, list) else []

    def _match_table_entry(self, table_name, source_type=""):
        wanted = {str(table_name or "").strip(), self._sanitize_name_for_match(table_name)}
        wanted.discard("")
        source_type = str(source_type or "").strip()
        fallback = None
        for entry in self._access_tables():
            if not isinstance(entry, dict):
                continue
            entry_names = {
                str(entry.get("table", "") or "").strip(),
                self._sanitize_name_for_match(entry.get("table", "")),
            }
            entry_names.discard("")
            pattern = str(entry.get("table_pattern", "") or "").strip()
            pattern_match = table_pattern_matches(
                table_name,
                pattern,
                entry.get("pattern_type", "glob"),
            )
            if not (wanted and wanted.intersection(entry_names)) and not pattern_match:
                continue
            entry_source = str(entry.get("source_type", "") or "").strip()
            if source_type:
                if entry_source == source_type:
                    return entry
                if not entry_source and fallback is None:
                    fallback = entry
                continue
            return entry
        return fallback

    def _field_rules(self, entry):
        mapping = (entry or {}).get("field_mapping") or {}
        if isinstance(mapping, dict):
            values = mapping.values()
        elif isinstance(mapping, list):
            values = mapping
        else:
            values = []
        return [item for item in values if isinstance(item, dict)]

    def _match_field_rule(self, entry, field_name, field_index=None):
        field_name = str(field_name or "").strip()
        mapping_mode = str((entry or {}).get("field_mapping_mode", "") or "").strip()
        by_order = mapping_mode in {"by_order", "按列顺序", "按顺序", "order"}
        if field_index is not None:
            try:
                field_pos = int(field_index) + 1
            except Exception:
                field_pos = None
        else:
            field_pos = None
        if not field_name and field_pos is None:
            return None
        for rule in self._field_rules(entry):
            rule_mode = str(rule.get("match_mode", "") or "").strip()
            if (by_order or rule_mode in {"by_order", "按列顺序", "按顺序", "order"}) and field_pos is not None:
                for key in ("target_index", "source_index", "index", "column_index"):
                    raw_index = rule.get(key)
                    if raw_index in ("", None):
                        continue
                    try:
                        if int(raw_index) == field_pos:
                            return rule
                    except Exception:
                        continue
            candidates = [
                rule.get("target_field"),
                rule.get("field"),
                rule.get("name"),
                rule.get("source_field"),
            ]
            if field_name in [str(v or "").strip() for v in candidates]:
                return rule
        return None

    def _permission_message(self, operation, table_name, status, missing_permissions, missing_fields):
        if status == "ok":
            return f"权限检查通过：{operation} {table_name}".strip()
        parts = [f"权限检查提示：{operation} {table_name}".strip()]
        if missing_permissions:
            parts.append("缺少表权限 " + ",".join(missing_permissions))
        if missing_fields:
            parts.append("字段受限 " + ",".join(missing_fields))
        return "；".join(parts)

    def check_table_permission(self, table_name, permissions, operation="table_access", fields=None,
                               field_action=None, write_mode="", source_type=""):
        """检查表和字段权限；log_only 表角色始终只记录不拦截。"""
        if self.permission_policy == "off":
            return True
        table_name = str(table_name or "").strip()
        required = [p for p in (permissions or []) if p]
        source_type = str(source_type or "").strip()
        entry = self._match_table_entry(table_name, source_type=source_type)
        missing_permissions = []
        missing_fields = []

        if entry is None:
            if self.table_access:
                missing_permissions.append("未配置表角色")
            else:
                status = "compat"
        else:
            status = "ok"
            perms = entry.get("permissions") or {}
            for perm in required:
                if not bool(perms.get(perm)):
                    missing_permissions.append(perm)

            action = str(field_action or "").strip()
            if action:
                rules = self._field_rules(entry)
                for field_index, field in enumerate(fields or []):
                    field = str(field or "").strip()
                    if not field and field_index is None:
                        continue
                    rule = self._match_field_rule(entry, field, field_index=field_index)
                    if rule is None:
                        if rules:
                            missing_fields.append(f"{field}:未配置")
                        continue
                    fperms = rule.get("permissions") or {}
                    if action in {"write", "create"} and bool(fperms.get("protect_field")):
                        missing_fields.append(f"{field}:保护字段")
                    if action == "create":
                        key = "create_field"
                    elif action == "write":
                        key = "write_field"
                    else:
                        key = "read_field"
                    if key in fperms and not bool(fperms.get(key)):
                        missing_fields.append(f"{field}:{key}")

        log_only = bool((entry or {}).get("log_only"))
        if entry is None and self.table_access:
            status = "missing"
        elif entry is None:
            status = "compat"
        elif missing_permissions or missing_fields:
            status = "warning" if log_only or not self.is_permission_enforced() else "denied"
        else:
            status = "ok"

        message = self._permission_message(operation, table_name, status, missing_permissions, missing_fields)
        self._log_event(
            "permission_check",
            table_name,
            status=status,
            operation_checked=operation,
            required_permissions=required,
            missing_permissions=missing_permissions,
            missing_fields=missing_fields,
            write_mode=write_mode,
            access_role=(entry or {}).get("role", ""),
            access_source_type=(entry or {}).get("source_type", ""),
            source_type=source_type,
            policy=self.permission_policy,
            log_only=log_only,
            message=message,
            emit_progress=False,
        )
        if status in {"denied", "missing"} and self.is_permission_enforced() and not log_only:
            raise PermissionError(message)
        return status not in {"denied", "missing"} or not self.is_permission_enforced() or log_only

    def validate_write_mode(self, table_name, mode, exists=None, fields=None, schema_fields=None):
        standard_mode = self.normalize_write_mode(mode or "replace_table")
        backend_mode = self.sqlite_backend_write_mode(standard_mode)
        if exists is None:
            exists = self.table_exists(table_name)

        required = self.required_permissions_for_write_mode(standard_mode, exists=exists)
        schema_fields = list(schema_fields or [])
        if schema_fields and "alter_schema" not in required:
            required.append("alter_schema")

        self.check_table_permission(
            table_name,
            required,
            operation="write_table",
            fields=fields,
            field_action="write",
            write_mode=standard_mode,
            source_type="SQLite表",
        )
        if schema_fields:
            self.check_table_permission(
                table_name,
                ["alter_schema"],
                operation="create_fields",
                fields=schema_fields,
                field_action="create",
                write_mode=standard_mode,
                source_type="SQLite表",
            )
        return backend_mode

    def list_tables(self):
        """返回当前数据库中的普通表名列表。"""
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name NOT LIKE 'sqlite_%'
                ORDER BY name
            """)
            return [r[0] for r in cur.fetchall()]

    def table_exists(self, table_name):
        """判断表是否存在。"""
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
            return cur.fetchone() is not None

    def get_columns(self, table_name):
        """返回指定表的字段名列表。"""
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(f"PRAGMA table_info({self.quote_ident(table_name)})")
            return [r[1] for r in cur.fetchall()]

    def read_table(self, table_name, limit=None, offset=0, include_rowid=False, fields=None):
        """
        读取 SQLite 表为工作流 table 格式：{"type":"table", "headers":[], "rows":[]}。
        include_rowid=True 时，会在第一列增加 __rowid__。
        """
        self.check_table_permission(table_name, ["read_table"], operation="read_table", fields=fields, field_action="read", source_type="SQLite表")
        all_columns = self.get_columns(table_name)
        if fields is None:
            columns = all_columns
        else:
            wanted = [str(f) for f in (fields or []) if str(f) in all_columns]
            columns = wanted
        if not columns:
            if not self.table_exists(table_name):
                return {"type": "table", "headers": [], "rows": [], "source_name": table_name, "meta": {"db_path": self.db_path}}
            with self._connect() as conn:
                cur = conn.cursor()
                cur.execute(f"SELECT 1 FROM {self.quote_ident(table_name)} ORDER BY rowid")
                rows = [[] for _ in cur.fetchall()]
            self._log_event("read_table", table_name, rows=len(rows), columns=0, message=f"读取表 {table_name}：{len(rows)} 行 × 0 列")
            return {"type": "table", "headers": [], "rows": rows, "source_name": table_name, "meta": {"db_path": self.db_path}}
        select_cols = ", ".join(self.quote_ident(c) for c in columns)
        if include_rowid:
            sql = f"SELECT rowid AS __rowid__, {select_cols} FROM {self.quote_ident(table_name)} ORDER BY rowid"
            headers = ["__rowid__"] + columns
        else:
            sql = f"SELECT {select_cols} FROM {self.quote_ident(table_name)} ORDER BY rowid"
            headers = columns
        params = []
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            params.extend([int(limit), int(offset or 0)])
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(sql, params)
            rows = [[self.format_value(v) for v in r] for r in cur.fetchall()]
        self._log_event("read_table", table_name, rows=len(rows), columns=len(headers), message=f"读取表 {table_name}：{len(rows)} 行 × {len(headers)} 列")
        return {"type": "table", "headers": headers, "rows": rows, "source_name": table_name, "meta": {"db_path": self.db_path}}

    def read_records(self, table_name, fields=None, include_rowid=False, include_row_index=False, prefix=""):
        data = self.read_table(table_name, include_rowid=include_rowid, fields=fields)
        headers = list(data.get("headers", []))
        rows = [list(r) for r in data.get("rows", [])]
        records = []
        for row_index, row in enumerate(rows, start=1):
            record = {}
            if include_row_index:
                record["__row_index__"] = row_index
            for i, header in enumerate(headers):
                value = row[i] if i < len(row) else ""
                if header == "__rowid__":
                    record["__rowid__"] = value
                else:
                    key = f"{prefix}{header}" if prefix else header
                    record[key] = value
            records.append(record)
        return [h for h in headers if h != "__rowid__"], records

    def backup_table(self, table_name, backup_name=None):
        """复制指定表为备份表，返回实际备份表名。"""
        if not self.table_exists(table_name):
            raise ValueError(f"表不存在：{table_name}")
        self.check_table_permission(table_name, ["read_table", "create_table"], operation="backup_table", source_type="SQLite表")
        if not backup_name:
            backup_name = f"{table_name}_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        actual = backup_name
        counter = 2
        while self.table_exists(actual):
            actual = f"{backup_name}_{counter}"
            counter += 1
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(f"CREATE TABLE {self.quote_ident(actual)} AS SELECT * FROM {self.quote_ident(table_name)}")
            conn.commit()
        self._log_event("backup_table", table_name, backup_name=actual, message=f"备份表 {table_name} -> {actual}")
        return actual

    def _create_table(self, cur, table_name, headers):
        headers = self.make_unique_headers(headers)
        col_defs = ", ".join(f"{self.quote_ident(h)} TEXT" for h in headers)
        cur.execute(f"CREATE TABLE {self.quote_ident(table_name)} ({col_defs})")
        return headers

    def _executemany(self, cur, sql, rows):
        """统一批量写入入口，便于事务失败测试和后续分批优化。"""
        return cur.executemany(sql, rows)

    def _execute_writeback_update(self, cur, sql, params):
        return cur.execute(sql, params)

    def _execute_writeback_insert(self, cur, sql, params):
        return cur.execute(sql, params)

    def _timestamp_table_name(self, base_name):
        suffix = datetime.now().strftime("%Y%m%d_%H%M%S")
        actual = f"{base_name}_{suffix}"
        counter = 2
        while self.table_exists(actual):
            actual = f"{base_name}_{suffix}_{counter}"
            counter += 1
        return actual

    def write_table(self, table_name, headers, rows, mode="replace"):
        """
        写入 table 数据到 SQLite。

        mode 可选：
        - replace / overwrite：删除同名表后重建。
        - fail / new：如果表已存在则报错。
        - timestamp / auto_timestamp：如果表已存在则自动加时间戳另存。
        - append：追加到已有表；不存在则新建；已有表缺少字段时自动 ADD COLUMN。
        """
        table_name = str(table_name).strip()
        if not table_name:
            raise ValueError("table_name 不能为空")
        headers = self.make_unique_headers(headers or [])
        rows = [list(r) for r in (rows or [])]
        if not headers:
            raise ValueError("headers 不能为空")
        standard_mode = self.normalize_write_mode(mode or "replace_table")

        actual_name = table_name
        exists = self.table_exists(table_name)
        existing_cols = self.get_columns(table_name) if exists else []
        schema_fields = [header for header in headers if exists and header not in existing_cols]
        mode = self.validate_write_mode(
            table_name,
            standard_mode,
            exists=exists,
            fields=headers,
            schema_fields=schema_fields if standard_mode == "append" else None,
        )
        if mode == "timestamp" and exists:
            actual_name = self._timestamp_table_name(table_name)
            exists = False

        fixed_rows = []
        for row in rows:
            r = list(row)
            if len(r) < len(headers):
                r += [""] * (len(headers) - len(r))
            elif len(r) > len(headers):
                r = r[:len(headers)]
            fixed_rows.append(["" if v is None else str(v) for v in r])

        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            cur = conn.cursor()
            if mode == "replace":
                cur.execute(f"DROP TABLE IF EXISTS {self.quote_ident(actual_name)}")
                self._create_table(cur, actual_name, headers)
            elif mode == "timestamp":
                self._create_table(cur, actual_name, headers)
            elif mode == "fail":
                if exists:
                    raise ValueError(f"表已存在：{actual_name}")
                self._create_table(cur, actual_name, headers)
            elif mode == "append":
                if not exists:
                    self._create_table(cur, actual_name, headers)
                else:
                    for h in headers:
                        if h not in existing_cols:
                            cur.execute(f"ALTER TABLE {self.quote_ident(actual_name)} ADD COLUMN {self.quote_ident(h)} TEXT")
            else:
                raise ValueError(f"未知写入模式：{mode}")

            col_names = ", ".join(self.quote_ident(h) for h in headers)
            placeholders = ", ".join(["?"] * len(headers))
            insert_sql = f"INSERT INTO {self.quote_ident(actual_name)} ({col_names}) VALUES ({placeholders})"
            if fixed_rows:
                self._executemany(cur, insert_sql, fixed_rows)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        self._log_event("write_table", actual_name, mode=mode, write_mode=standard_mode, rows=len(rows), columns=len(headers), message=f"写入表 {actual_name}：{len(rows)} 行 × {len(headers)} 列，模式 {standard_mode}")
        return {"table_name": actual_name, "rows": len(rows), "columns": len(headers), "mode": mode, "write_mode": standard_mode}

    def clear_fields(self, table_name, fields):
        result = self.apply_writeback_transaction(
            table_name,
            actions=[],
            clear_fields=fields,
        )
        return result["cleared_fields"]

    def apply_cell_actions(self, table_name, actions, cancel_event=None):
        result = self.apply_writeback_transaction(
            table_name,
            actions=actions,
            clear_fields=[],
            cancel_event=cancel_event,
        )
        return result["cells"]

    def apply_writeback_transaction(self, table_name, actions, clear_fields=None, cancel_event=None):
        """在同一事务中完成字段清空、已有行更新和新行追加。"""
        table_name = str(table_name or "").strip()
        if not table_name:
            raise ValueError("table_name 不能为空")
        target_columns = self.get_columns(table_name)
        if not target_columns and not self.table_exists(table_name):
            raise ValueError(f"表不存在：{table_name}")

        clean_fields = []
        existing = set(target_columns)
        for field in clear_fields or []:
            field = str(field or "").strip()
            if field and field in existing and field not in clean_fields:
                clean_fields.append(field)
        if clean_fields:
            self.check_table_permission(
                table_name,
                ["write_table", "clear_table"],
                operation="clear_fields",
                fields=clean_fields,
                field_action="write",
                source_type="SQLite表",
            )

        write_actions = [a for a in (actions or []) if a.get("write")]
        target_fields = []
        has_new_rows = False
        for action in write_actions:
            field = str(action.get("target_field", "") or "").strip()
            if field and field not in target_fields:
                target_fields.append(field)
            if action.get("is_new_row"):
                has_new_rows = True
        if write_actions:
            required = ["write_table", "update_rows"]
            if has_new_rows:
                required.append("append_rows")
            self.check_table_permission(
                table_name,
                required,
                operation="update_cells",
                fields=target_fields,
                field_action="write",
                source_type="SQLite表",
            )

        def check_cancel():
            if cancel_event is not None and cancel_event.is_set():
                raise RuntimeError("用户取消后台执行")

        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            cur = conn.cursor()
            check_cancel()
            if clean_fields:
                set_sql = ", ".join(f"{self.quote_ident(field)}=''" for field in clean_fields)
                cur.execute(f"UPDATE {self.quote_ident(table_name)} SET {set_sql}")

            actual = 0
            for index, action in enumerate(write_actions, start=1):
                if index == 1 or index % 100 == 0:
                    check_cancel()
                if action.get("is_new_row"):
                    continue
                target_field = action.get("target_field")
                if target_field not in target_columns:
                    continue
                sql = f"UPDATE {self.quote_ident(table_name)} SET {self.quote_ident(target_field)}=? WHERE rowid=?"
                self._execute_writeback_update(
                    cur,
                    sql,
                    (action.get("new_value", ""), action.get("target_rowid")),
                )
                actual += 1

            insert_groups = {}
            for index, action in enumerate(write_actions, start=1):
                if index == 1 or index % 100 == 0:
                    check_cancel()
                if not action.get("is_new_row"):
                    continue
                key = action.get("new_row_key") or f"source_{action.get('source_row', '')}"
                insert_groups.setdefault(key, {})[action.get("target_field", "")] = action.get("new_value", "")

            for index, values_by_field in enumerate(insert_groups.values(), start=1):
                if index == 1 or index % 100 == 0:
                    check_cancel()
                insert_cols = [col for col in target_columns if col in values_by_field]
                if not insert_cols:
                    continue
                placeholders = ", ".join(["?"] * len(insert_cols))
                col_sql = ", ".join(self.quote_ident(col) for col in insert_cols)
                sql = f"INSERT INTO {self.quote_ident(table_name)} ({col_sql}) VALUES ({placeholders})"
                self._execute_writeback_insert(
                    cur,
                    sql,
                    [values_by_field.get(col, "") for col in insert_cols],
                )
                actual += len(insert_cols)

            check_cancel()
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

        if clean_fields:
            self._log_event(
                "clear_fields",
                table_name,
                fields=clean_fields,
                message=f"清空表 {table_name} 字段：{len(clean_fields)} 个",
            )
        if write_actions:
            self._log_event("update_cells", table_name, cells=actual, message=f"更新表 {table_name}：{actual} 处")
        return {"cells": actual, "cleared_fields": len(clean_fields)}

    def execute_select(self, sql, params=None, tables=None):
        """执行只读 SELECT 查询，返回 table 格式。"""
        sql_text = str(sql or "").strip()
        if not sql_text.lower().startswith(("select", "with", "pragma")):
            raise ValueError("execute_select 只允许 SELECT / WITH / PRAGMA 查询")
        referenced_tables = list(tables or extract_read_tables(sql_text))
        checked_tables = set()

        def check_read_access(table_name):
            table_name = str(table_name or "").strip()
            if not table_name or table_name in checked_tables:
                return
            self.check_table_permission(
                table_name,
                ["read_table"],
                operation="execute_select",
                source_type="SQLite表",
            )
            checked_tables.add(table_name)
            if table_name not in referenced_tables:
                referenced_tables.append(table_name)

        for table_name in referenced_tables:
            check_read_access(table_name)
        with self._connect() as conn:
            denied = []

            def authorizer(action_code, arg1, arg2, database_name, trigger_name):
                if action_code == sqlite3.SQLITE_READ:
                    try:
                        check_read_access(arg1)
                    except PermissionError as exc:
                        denied.append(exc)
                        return sqlite3.SQLITE_DENY
                return sqlite3.SQLITE_OK

            conn.set_authorizer(authorizer)
            cur = conn.cursor()
            try:
                cur.execute(sql_text, params or [])
            except sqlite3.DatabaseError:
                if denied:
                    raise denied[0]
                raise
            finally:
                conn.set_authorizer(None)
            headers = [d[0] for d in (cur.description or [])]
            rows = [[self.format_value(v) for v in r] for r in cur.fetchall()]
        self._log_event(
            "execute_select",
            ",".join(referenced_tables) or "execute_select",
            rows=len(rows),
            columns=len(headers),
            referenced_tables=referenced_tables,
            message=f"执行只读查询：{len(rows)} 行 × {len(headers)} 列",
        )
        return {"type": "table", "headers": headers, "rows": rows, "source_name": "execute_select", "meta": {"db_path": self.db_path}}

    def drop_table(self, table_name, backup=False):
        """删除表；主页/管理窗口这类高风险操作也统一进入 manager。"""
        table_name = str(table_name or "").strip()
        if not table_name:
            raise ValueError("table_name 不能为空")
        if not self.table_exists(table_name):
            raise ValueError(f"表不存在：{table_name}")
        self.check_table_permission(table_name, ["drop_table"], operation="drop_table", source_type="SQLite表")
        backup_name = self.backup_table(table_name) if backup else None
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(f"DROP TABLE {self.quote_ident(table_name)}")
            conn.commit()
        self._log_event("drop_table", table_name, backup_name=backup_name, message=f"删除表 {table_name}")
        return backup_name

    def write_plugin_logs(self, log_items):
        """插件日志表属于系统日志写入，保留专门入口但不再散落 sqlite3.connect。"""
        if not log_items:
            return 0
        table_name = "_plugin_log"
        self.check_table_permission(
            table_name,
            ["write_table", "append_rows", "create_table"],
            operation="write_plugin_logs",
            source_type="SQLite表",
        )
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS _plugin_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    time TEXT,
                    level TEXT,
                    plugin_id TEXT,
                    node_name TEXT,
                    object TEXT,
                    message TEXT,
                    traceback TEXT
                )
            """)
            data = [(
                it.get("time", ""), it.get("level", "INFO"), it.get("plugin_id", ""),
                it.get("node_name", ""), it.get("object", ""), it.get("message", ""), it.get("traceback", "")
            ) for it in log_items]
            cur.executemany("""
                INSERT INTO _plugin_log(time, level, plugin_id, node_name, object, message, traceback)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, data)
            conn.commit()
        self._log_event("write_plugin_logs", table_name, rows=len(log_items), message=f"写入插件日志：{len(log_items)} 条")
        return len(log_items)


class PluginDatabaseAPI(TableAccessManager):
    """
    插件兼容别名。

    插件继续使用 context["db"] / PluginDatabaseAPI，不需要立刻改调用方式。
    """
    pass
