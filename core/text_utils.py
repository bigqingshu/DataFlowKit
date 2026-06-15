# -*- coding: utf-8 -*-
"""Pure text and SQL-name helpers."""

import re


def sanitize_sql_name(name, default_name):
    name = str(name).strip()

    if not name:
        name = default_name

    name = re.sub(r"\W+", "_", name, flags=re.UNICODE)

    if re.match(r"^\d", name):
        name = "t_" + name

    if not name:
        name = default_name

    return name


def make_sql_columns(headers):
    result = []
    used = {}

    for index, header in enumerate(headers, start=1):
        col = sanitize_sql_name(header, f"col_{index}")

        if col in used:
            used[col] += 1
            col = f"{col}_{used[col]}"
        else:
            used[col] = 1

        result.append(col)

    return result


def quote_ident(name):
    return '"' + str(name).replace('"', '""') + '"'

