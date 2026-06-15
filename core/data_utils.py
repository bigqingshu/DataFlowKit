# -*- coding: utf-8 -*-
"""Pure row/header helpers used by workflow and database code."""


def make_unique_headers(headers):
    result = []
    used = {}
    for idx, header in enumerate(headers, start=1):
        name = str(header).strip() if header is not None else ""
        if not name:
            name = f"列{idx}"
        base = name
        if base in used:
            used[base] += 1
            name = f"{base}_{used[base]}"
        else:
            used[base] = 1
        while name in result:
            used[base] = used.get(base, 1) + 1
            name = f"{base}_{used[base]}"
        result.append(name)
    return result


def safe_cell(row, idx):
    if idx < 0 or idx >= len(row):
        return ""
    value = row[idx]
    return "" if value is None else str(value)


def normalize_rows(rows, col_count):
    result = []
    for row in rows:
        fixed = list(row)
        if len(fixed) < col_count:
            fixed += [""] * (col_count - len(fixed))
        if len(fixed) > col_count:
            fixed = fixed[:col_count]
        result.append(fixed)
    return result


def make_unique_headers_for_append(existing_headers, new_headers):
    result = []
    used = set(str(h) for h in existing_headers)
    for raw in new_headers:
        base = str(raw).strip() or "字段"
        name = base
        n = 2
        while name in used or name in result:
            name = f"{base}_{n}"
            n += 1
        result.append(name)
        used.add(name)
    return result

