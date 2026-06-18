# -*- coding: utf-8 -*-
"""Table matching helpers for table-access precheck."""

import re

from shared.table_access_policy import table_pattern_matches


def sanitize_table_name_for_match(name):
    name = str(name or "").strip()
    if not name:
        return ""
    name = re.sub(r"\W+", "_", name, flags=re.UNICODE)
    if re.match(r"^\d", name):
        name = "t_" + name
    return name


def table_access_entry_match_score(actual, expected):
    actual = actual or {}
    expected = expected or {}
    actual_table = str(actual.get("table", "") or "").strip()
    expected_table = str(expected.get("table", "") or "").strip()
    actual_pattern = str(actual.get("table_pattern", "") or "").strip()
    expected_pattern = str(expected.get("table_pattern", "") or "").strip()
    if expected_pattern:
        if actual_pattern == expected_pattern:
            score = 3
        elif actual_table and table_pattern_matches(actual_table, expected_pattern, expected.get("pattern_type", "glob")):
            score = 2
        else:
            return 0
    elif actual_pattern and expected_table:
        if table_pattern_matches(expected_table, actual_pattern, actual.get("pattern_type", "glob")):
            score = 2
        else:
            return 0
    else:
        if not expected_table:
            return 0
        actual_names = {actual_table, sanitize_table_name_for_match(actual_table)}
        expected_names = {expected_table, sanitize_table_name_for_match(expected_table)}
        actual_names.discard("")
        expected_names.discard("")
        if not actual_names.intersection(expected_names):
            return 0
        score = 1
    actual_source = str(actual.get("source_type", "") or "").strip()
    expected_source = str(expected.get("source_type", "") or "").strip()
    if expected_source and actual_source == expected_source:
        score += 2
    elif expected_source and actual_source and actual_source != expected_source:
        return 0
    if str(actual.get("role", "") or "").strip() == str(expected.get("role", "") or "").strip():
        score += 1
    return score


def find_matching_table_access_entry(actual_tables, expected):
    best = None
    best_score = 0
    for entry in actual_tables or []:
        if not isinstance(entry, dict):
            continue
        score = table_access_entry_match_score(entry, expected)
        if score > best_score:
            best = entry
            best_score = score
    return best
