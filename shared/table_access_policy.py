# -*- coding: utf-8 -*-
"""Pure helpers shared by table-access permission checks."""

import fnmatch
import re


_IDENTIFIER_ATOM = r'(?:`[^`]+`|"[^"]+"|\[[^\]]+\]|[A-Za-z_\u4e00-\u9fff][\w\u4e00-\u9fff$]*)'
_IDENTIFIER_PATTERN = rf'(?:{_IDENTIFIER_ATOM})(?:\s*\.\s*(?:{_IDENTIFIER_ATOM}))?'


def unquote_identifier(value):
    text = str(value or "").strip()
    if "." in text:
        text = text.rsplit(".", 1)[-1].strip()
    if len(text) >= 2:
        pairs = {('"', '"'), ("`", "`"), ("[", "]")}
        if (text[0], text[-1]) in pairs:
            text = text[1:-1]
    return text.replace('""', '"').replace("``", "`").strip()


def table_pattern_matches(table_name, pattern, match_type="glob"):
    name = str(table_name or "").strip()
    pattern = str(pattern or "").strip()
    if not name or not pattern:
        return False
    mode = str(match_type or "glob").strip().lower()
    if mode in {"prefix", "前缀"}:
        return name.startswith(pattern)
    if mode in {"regex", "正则"}:
        try:
            return re.fullmatch(pattern, name) is not None
        except re.error:
            return False
    return fnmatch.fnmatchcase(name, pattern)


def _strip_sql_literals_and_comments(sql):
    text = str(sql or "")
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    text = re.sub(r"--[^\r\n]*", " ", text)
    text = re.sub(r"'(?:''|[^'])*'", "''", text)
    return text


def extract_read_tables(sql):
    """Extract directly referenced tables from common SQLite read statements."""
    text = _strip_sql_literals_and_comments(sql)
    cte_names = set()
    for match in re.finditer(
        rf'(?:\bWITH\b|,)\s*({_IDENTIFIER_PATTERN})\s+AS\s*\(',
        text,
        flags=re.I,
    ):
        name = unquote_identifier(match.group(1))
        if name:
            cte_names.add(name.lower())

    tables = []
    for match in re.finditer(rf'\b(?:FROM|JOIN)\s+({_IDENTIFIER_PATTERN})', text, flags=re.I):
        name = unquote_identifier(match.group(1))
        if name and name.lower() not in cte_names and name not in tables:
            tables.append(name)

    pragma_match = re.search(
        rf'\bPRAGMA\s+(?:table_info|table_xinfo|foreign_key_list|index_list)\s*\(\s*({_IDENTIFIER_PATTERN})\s*\)',
        text,
        flags=re.I,
    )
    if pragma_match:
        name = unquote_identifier(pragma_match.group(1))
        if name and name not in tables:
            tables.append(name)
    return tables
