# -*- coding: utf-8 -*-
"""Text extraction workflow node."""

import re

from core.data_utils import normalize_rows, safe_cell
from workflow.nodes.data_common import field_index, get_unique_header, parse_int


def apply_unmatched_extract(text, status, config):
    mode = config.get("unmatched_mode", "留空")
    if mode == "留空":
        return "", status
    if mode == "保留原值":
        return text, status
    if mode == "填写固定值":
        return str(config.get("unmatched_fixed", "未匹配")), status
    if mode == "跳过该行":
        return "", "跳过"
    return "", status


def post_extract_result(result, config):
    result = "" if result is None else str(result)
    if config.get("strip_result", True):
        result = result.strip()
    return result


def extract_one_value(original, config):
    text = "" if original is None else str(original)
    method = config.get("method", "正则提取")
    case_sensitive = bool(config.get("case_sensitive", True))

    def norm(value):
        return value if case_sensitive else value.lower()

    try:
        if method == "正则提取":
            pattern = config.get("regex_pattern", "")
            if not pattern:
                raise ValueError("正则表达式不能为空。")
            flags = 0 if case_sensitive else re.IGNORECASE
            group_index = parse_int(config.get("regex_group", "0"), "提取分组")
            if config.get("regex_find_all", False):
                results = []
                for match in re.finditer(pattern, text, flags):
                    try:
                        results.append(match.group(group_index))
                    except IndexError:
                        return apply_unmatched_extract(text, "分组不存在", config)
                if not results:
                    return apply_unmatched_extract(text, "未匹配", config)
                return post_extract_result(str(config.get("regex_joiner", ";")).join(results), config), "成功"
            match = re.search(pattern, text, flags)
            if not match:
                return apply_unmatched_extract(text, "未匹配", config)
            try:
                return post_extract_result(match.group(group_index), config), "成功"
            except IndexError:
                return apply_unmatched_extract(text, "分组不存在", config)

        if method == "固定位置提取":
            start = parse_int(config.get("start_pos", "1"), "起始位置")
            length = parse_int(config.get("extract_len", "1"), "提取长度")
            start_idx = start - 1 if config.get("position_base", "从1开始") == "从1开始" else start
            if start_idx < 0 or start_idx >= len(text):
                return apply_unmatched_extract(text, "越界", config)
            return post_extract_result(text[start_idx:start_idx + length], config), "成功"

        if method == "从左取N位":
            n = parse_int(config.get("n_chars", "1"), "N")
            return post_extract_result(text[:max(n, 0)], config), "成功"

        if method == "从右取N位":
            n = parse_int(config.get("n_chars", "1"), "N")
            return post_extract_result(text[-n:] if n > 0 else "", config), "成功"

        if method == "按分隔符提取":
            delimiter = str(config.get("delimiter", "-"))
            if delimiter == "":
                raise ValueError("分隔符不能为空。")
            parts = text.split(delimiter)
            if config.get("ignore_empty_part", False):
                parts = [part for part in parts if part != ""]
            part_index = parse_int(config.get("part_index", "1"), "取第几段")
            if part_index == 0:
                raise ValueError("段序号不能为0。")
            idx = part_index - 1 if part_index > 0 else part_index
            if idx < -len(parts) or idx >= len(parts):
                return apply_unmatched_extract(text, "越界", config)
            return post_extract_result(parts[idx], config), "成功"

        if method == "前后关键字之间提取":
            start_key = str(config.get("before_key", ""))
            end_key = str(config.get("after_key", ""))
            if not start_key or not end_key:
                raise ValueError("开始关键字和结束关键字不能为空。")
            occurrence = parse_int(config.get("between_occurrence", "1"), "第几个匹配")
            search_text = norm(text)
            search_start = norm(start_key)
            search_end = norm(end_key)
            pos = 0
            found = None
            for _ in range(occurrence):
                start_pos = search_text.find(search_start, pos)
                if start_pos < 0:
                    return apply_unmatched_extract(text, "未匹配", config)
                content_start = start_pos + len(start_key)
                end_pos = search_text.find(search_end, content_start)
                if end_pos < 0:
                    return apply_unmatched_extract(text, "未匹配", config)
                found = text[content_start:end_pos]
                pos = end_pos + len(end_key)
            return post_extract_result(found, config), "成功"

        if method in ["指定字符前提取", "指定字符后提取"]:
            marker = str(config.get("marker", "-"))
            if marker == "":
                raise ValueError("指定字符不能为空。")
            search_text = norm(text)
            search_marker = norm(marker)
            idx = (
                search_text.rfind(search_marker)
                if config.get("find_mode", "第一次出现") == "最后一次出现"
                else search_text.find(search_marker)
            )
            if idx < 0:
                return apply_unmatched_extract(text, "未匹配", config)
            if method == "指定字符前提取":
                return post_extract_result(text[:idx], config), "成功"
            return post_extract_result(text[idx + len(marker):], config), "成功"

        if method == "删除前缀":
            prefix = str(config.get("prefix", ""))
            if prefix == "":
                raise ValueError("前缀不能为空。")
            if norm(text).startswith(norm(prefix)):
                return post_extract_result(text[len(prefix):], config), "成功"
            return apply_unmatched_extract(text, "未匹配", config)

        if method == "删除后缀":
            suffix = str(config.get("suffix", ""))
            if suffix == "":
                raise ValueError("后缀不能为空。")
            if norm(text).endswith(norm(suffix)):
                return post_extract_result(text[:-len(suffix)], config), "成功"
            return apply_unmatched_extract(text, "未匹配", config)

        raise ValueError(f"未知提取方式：{method}")
    except re.error as exc:
        raise ValueError(f"正则错误：{exc}") from exc


def apply_extract_node(headers, rows, config):
    idx = field_index(headers, config.get("source_field", ""))
    headers = list(headers)
    new_rows = normalize_rows(rows, len(headers))
    changed = 0
    skipped = 0

    if config.get("output_mode", "生成新字段") == "生成新字段":
        new_header = get_unique_header(config.get("new_field", "提取结果"), headers)
        headers.append(new_header)
        for row in new_rows:
            extracted, status = extract_one_value(safe_cell(row, idx), config)
            if status == "跳过":
                skipped += 1
                row.append("")
            else:
                row.append(extracted)
                changed += 1
    else:
        for row in new_rows:
            extracted, status = extract_one_value(safe_cell(row, idx), config)
            if status == "跳过":
                skipped += 1
                continue
            row[idx] = extracted
            changed += 1

    return headers, new_rows, f"写入 {changed} 行，跳过 {skipped} 行"
