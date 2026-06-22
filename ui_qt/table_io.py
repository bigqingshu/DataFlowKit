# -*- coding: utf-8 -*-
"""Small table import helpers for the Qt shell."""

from __future__ import annotations

import csv
import json
from pathlib import Path


def load_table_file(path):
    """Load a table from JSON, CSV, or TSV for Qt preview input."""

    target = Path(path)
    suffix = target.suffix.lower()
    if suffix == ".json":
        return load_json_table(target)
    if suffix in (".tsv", ".tab"):
        return load_delimited_table(target, delimiter="\t")
    return load_delimited_table(target, delimiter=",")


def load_json_table(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        if "headers" in data or "rows" in data:
            return list(data.get("headers", [])), [list(row) for row in data.get("rows", [])]
        if data.get("type") == "table":
            return list(data.get("headers", [])), [list(row) for row in data.get("rows", [])]
    if isinstance(data, list):
        return _table_from_json_list(data)
    raise ValueError("JSON 表格必须包含 headers/rows，或为对象数组。")


def _table_from_json_list(items):
    if not items:
        return [], []
    if all(isinstance(item, dict) for item in items):
        headers = []
        for item in items:
            for key in item.keys():
                if key not in headers:
                    headers.append(key)
        rows = [[item.get(header, "") for header in headers] for item in items]
        return headers, rows
    if all(isinstance(item, list) for item in items):
        headers = [str(value) for value in items[0]]
        rows = [list(row) for row in items[1:]]
        return headers, rows
    raise ValueError("JSON 数组必须是对象数组或二维数组。")


def load_delimited_table(path, delimiter=","):
    with Path(path).open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream, delimiter=delimiter)
        rows = [list(row) for row in reader]
    if not rows:
        return [], []
    return [str(item) for item in rows[0]], rows[1:]
