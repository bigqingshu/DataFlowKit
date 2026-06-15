# -*- coding: utf-8 -*-
"""Filesystem workflow nodes."""

import fnmatch
import os
import re
from datetime import datetime


FILE_LIST_HEADERS = [
    "文件名",
    "完整路径",
    "所在目录",
    "扩展名",
    "文件大小",
    "修改时间",
    "创建时间",
    "是否文件夹",
    "新文件名",
    "新完整路径",
    "重命名状态",
]

BATCH_RENAME_LOG_HEADERS = ["行号", "原路径", "新路径", "状态", "时间"]


def parse_extensions_filter(text_value):
    parts = re.split(r"[;,，；\s]+", str(text_value or ""))
    result = set()
    for part in parts:
        part = part.strip().lower()
        if not part:
            continue
        if not part.startswith("."):
            part = "." + part
        result.add(part)
    return result


def get_positive_int(value, default_value):
    try:
        n = int(str(value).strip())
        return n if n > 0 else default_value
    except Exception:
        return default_value


def is_hidden_path(path):
    name = os.path.basename(path)
    if name.startswith("."):
        return True
    if os.name == "nt":
        try:
            import ctypes

            attrs = ctypes.windll.kernel32.GetFileAttributesW(str(path))
            if attrs == -1:
                return False
            return bool(attrs & 2)
        except Exception:
            return False
    return False


def get_or_add_column_index(headers, rows, column_name):
    column_name = str(column_name or "").strip()
    if not column_name:
        column_name = "结果"
    if column_name in headers:
        return headers.index(column_name), headers, rows
    headers = list(headers)
    rows = [list(row) for row in rows]
    headers.append(column_name)
    for row in rows:
        row.append("")
    return len(headers) - 1, headers, rows


def make_numbered_path(path, path_exists=None):
    path_exists = path_exists or os.path.exists
    folder = os.path.dirname(path)
    name = os.path.basename(path)
    stem, ext = os.path.splitext(name)
    for i in range(1, 10000):
        candidate = os.path.join(folder, f"{stem}_{i}{ext}")
        if not path_exists(candidate):
            return candidate
    raise ValueError(f"无法自动生成不冲突文件名：{path}")


def _call_check_cancelled(context, index=None):
    callback = (context or {}).get("check_cancelled")
    if not callable(callback):
        return
    if index is None:
        callback()
        return
    try:
        callback(index)
    except TypeError:
        callback()


def _report_progress(context, current, total, message, node_name="获取文件列表"):
    callback = (context or {}).get("report_progress")
    if not callable(callback):
        return
    try:
        callback(current=current, total=total, message=message, node_name=node_name)
    except TypeError:
        callback(current, total, message, node_name)


def make_file_list_row(path, is_dir):
    try:
        stat = os.stat(path)
        size = "" if is_dir else str(stat.st_size)
        mtime = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        ctime = datetime.fromtimestamp(stat.st_ctime).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        size, mtime, ctime = "", "", ""

    name = os.path.basename(path)
    abs_path = os.path.abspath(path)
    return [
        name,
        abs_path,
        os.path.dirname(path),
        os.path.splitext(name)[1],
        size,
        mtime,
        ctime,
        "是" if is_dir else "否",
        name,
        abs_path,
        "待处理",
    ]


def should_include_file_list_path(path, is_dir, options):
    name = os.path.basename(path)
    include_hidden = bool(options.get("include_hidden", False))
    include_dirs = bool(options.get("include_dirs", False))
    include_files = bool(options.get("include_files", True))
    name_contains = str(options.get("name_contains", "") or "")
    glob_pattern = str(options.get("glob_pattern", "*") or "*")
    ext_filter = options.get("ext_filter") or set()

    if not include_hidden and is_hidden_path(path):
        return False
    if is_dir and not include_dirs:
        return False
    if (not is_dir) and not include_files:
        return False
    if name_contains and name_contains.lower() not in name.lower():
        return False
    if glob_pattern and glob_pattern != "*" and not fnmatch.fnmatch(name, glob_pattern):
        return False

    ext = os.path.splitext(name)[1].lower()
    if (not is_dir) and ext_filter and ext not in ext_filter:
        return False
    return True


def apply_file_list_node(headers, rows, config, context=None):
    config = config or {}
    context = context or {}
    directory = config.get("directory") or context.get("default_directory") or "."
    directory = os.path.abspath(os.path.expanduser(str(directory)))
    if not os.path.isdir(directory):
        raise ValueError(f"目录不存在：{directory}")

    recursive = bool(config.get("recursive", True))
    max_files = get_positive_int(config.get("max_files", "20000"), 20000)
    options = {
        "include_files": bool(config.get("include_files", True)),
        "include_dirs": bool(config.get("include_dirs", False)),
        "include_hidden": bool(config.get("include_hidden", False)),
        "name_contains": str(config.get("name_contains", "") or ""),
        "glob_pattern": str(config.get("glob_pattern", "*") or "*"),
        "ext_filter": parse_extensions_filter(config.get("extensions", "")),
    }
    out_rows = []
    scanned_count = 0

    def add_path(path, is_dir):
        out_rows.append(make_file_list_row(path, is_dir))

    if recursive:
        for root_dir, dirnames, filenames in os.walk(directory):
            _call_check_cancelled(context)
            scanned_count += 1
            if scanned_count % 50 == 0:
                _report_progress(context, len(out_rows), max_files, f"正在扫描目录：{root_dir}")
            if not options["include_hidden"]:
                dirnames[:] = [d for d in dirnames if not is_hidden_path(os.path.join(root_dir, d))]
            if options["include_dirs"]:
                for dirname in dirnames:
                    path = os.path.join(root_dir, dirname)
                    if should_include_file_list_path(path, True, options):
                        add_path(path, True)
                        if len(out_rows) >= max_files:
                            break
            if len(out_rows) >= max_files:
                break
            if options["include_files"]:
                for filename in filenames:
                    path = os.path.join(root_dir, filename)
                    if should_include_file_list_path(path, False, options):
                        add_path(path, False)
                        if len(out_rows) >= max_files:
                            break
            if len(out_rows) >= max_files:
                break
    else:
        names = os.listdir(directory)
        total_names = len(names)
        for idx_name, name in enumerate(names, start=1):
            if idx_name % 200 == 0:
                _call_check_cancelled(context, idx_name)
                _report_progress(context, idx_name, total_names, f"正在扫描 {idx_name}/{total_names}")
            path = os.path.join(directory, name)
            is_dir = os.path.isdir(path)
            if should_include_file_list_path(path, is_dir, options):
                add_path(path, is_dir)
                if len(out_rows) >= max_files:
                    break

    return list(FILE_LIST_HEADERS), out_rows, f"读取文件列表 {len(out_rows)} 项，目录：{directory}"


def _get_context_func(context, name, default):
    func = (context or {}).get(name)
    return func if callable(func) else default


def _make_batch_rename_destination(src, new_value, name_value_type, auto_append_ext):
    if name_value_type == "完整路径":
        return os.path.abspath(os.path.expanduser(new_value)), ""

    safe_name = os.path.basename(new_value)
    if not safe_name:
        return "", "跳过：新文件名无效"
    if auto_append_ext and not os.path.splitext(safe_name)[1]:
        safe_name += os.path.splitext(src)[1]
    return os.path.abspath(os.path.join(os.path.dirname(src), safe_name)), ""


def apply_batch_rename_node(headers, rows, config, execute_actions=False, context=None):
    config = config or {}
    context = context if context is not None else {}
    headers = list(headers)
    rows = [list(row) for row in rows]

    path_field = config.get("path_field", "完整路径")
    new_name_field = config.get("new_name_field", "新文件名")
    if path_field not in headers:
        raise ValueError(f"找不到原路径字段：{path_field}")
    if new_name_field not in headers:
        raise ValueError(f"找不到新名称字段：{new_name_field}")

    path_idx = headers.index(path_field)
    new_idx = headers.index(new_name_field)
    new_path_idx, headers, rows = get_or_add_column_index(headers, rows, config.get("new_path_field", "新完整路径"))
    status_idx, headers, rows = get_or_add_column_index(headers, rows, config.get("status_field", "重命名状态"))

    name_value_type = config.get("name_value_type", "仅文件名")
    conflict_mode = config.get("conflict_mode", "跳过目标已存在")
    auto_append_ext = bool(config.get("auto_append_ext", False))
    allow_dirs = bool(config.get("allow_dirs", False))
    create_target_dirs = bool(config.get("create_target_dirs", False))
    actual_rename = bool(config.get("actual_rename", False))
    do_rename = bool(execute_actions and actual_rename)

    path_exists = _get_context_func(context, "path_exists", os.path.exists)
    path_is_dir = _get_context_func(context, "path_is_dir", os.path.isdir)
    make_dirs = _get_context_func(context, "make_dirs", lambda path: os.makedirs(path, exist_ok=True))
    rename_file = _get_context_func(context, "rename_file", os.rename)
    replace_file = _get_context_func(context, "replace_file", os.replace)
    make_numbered = _get_context_func(context, "make_numbered_path", lambda path: make_numbered_path(path, path_exists=path_exists))

    timestamp = str(context.get("timestamp") or datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    changed = 0
    preview_ok = 0
    skipped = 0
    log_rows = []

    total_rename_rows = len(rows)
    for row_num, row in enumerate(rows, start=1):
        if row_num == 1 or row_num % 100 == 0:
            _call_check_cancelled(context, row_num)
            _report_progress(
                context,
                row_num,
                total_rename_rows,
                f"正在处理重命名 {row_num}/{total_rename_rows}",
                node_name="批量重命名",
            )
        while len(row) < len(headers):
            row.append("")

        src = str(row[path_idx] or "").strip()
        new_value = str(row[new_idx] or "").strip()
        status = ""
        dst = ""
        try:
            if not src:
                status = "跳过：原路径为空"
                skipped += 1
            elif not new_value:
                status = "跳过：新名称为空"
                skipped += 1
            elif not path_exists(src):
                status = "跳过：原路径不存在"
                skipped += 1
            elif path_is_dir(src) and not allow_dirs:
                status = "跳过：不允许重命名文件夹"
                skipped += 1
            else:
                dst, status = _make_batch_rename_destination(src, new_value, name_value_type, auto_append_ext)
                if status:
                    skipped += 1

                target_dir_created_note = ""
                if not status:
                    target_dir = os.path.dirname(os.path.abspath(dst))
                    target_dir_missing = bool(target_dir) and not path_is_dir(target_dir)
                    if target_dir_missing:
                        if create_target_dirs:
                            if do_rename:
                                make_dirs(target_dir)
                                target_dir_created_note = "，已创建目标目录"
                            else:
                                target_dir_created_note = "，将创建目标目录"
                        else:
                            status = f"跳过：目标目录不存在：{target_dir}"
                            skipped += 1

                if not status:
                    if os.path.abspath(src) == os.path.abspath(dst):
                        status = "无需重命名：路径相同"
                        preview_ok += 1
                    elif path_exists(dst):
                        if conflict_mode == "跳过目标已存在":
                            status = "跳过：目标已存在"
                            skipped += 1
                        elif conflict_mode == "自动加编号":
                            dst = make_numbered(dst)
                            if do_rename:
                                rename_file(src, dst)
                                status = "已重命名：自动加编号" + target_dir_created_note
                                changed += 1
                            else:
                                status = "预览可重命名：自动加编号" + target_dir_created_note
                                preview_ok += 1
                        elif conflict_mode == "覆盖目标（危险）":
                            if do_rename:
                                replace_file(src, dst)
                                status = "已重命名：覆盖目标" + target_dir_created_note
                                changed += 1
                            else:
                                status = "预览可重命名：将覆盖目标" + target_dir_created_note
                                preview_ok += 1
                        else:
                            status = "跳过：未知冲突处理"
                            skipped += 1
                    else:
                        if do_rename:
                            rename_file(src, dst)
                            status = "已重命名" + target_dir_created_note
                            changed += 1
                        else:
                            status = ("预览可重命名" if actual_rename else "仅预览未执行") + target_dir_created_note
                            preview_ok += 1
        except Exception as e:
            status = f"失败：{e}"
            skipped += 1

        row[new_path_idx] = dst
        row[status_idx] = status
        log_rows.append([row_num, src, dst, status, timestamp])

    _report_progress(
        context,
        total_rename_rows,
        total_rename_rows,
        "批量重命名节点处理完成",
        node_name="批量重命名",
    )

    context["batch_rename_log_rows"] = log_rows
    context["batch_rename_changed"] = changed
    context["batch_rename_preview_ok"] = preview_ok
    context["batch_rename_skipped"] = skipped
    context["batch_rename_do_rename"] = do_rename

    if do_rename:
        return headers, rows, f"实际重命名 {changed} 项，跳过/失败 {skipped} 项"
    return headers, rows, f"重命名预览：可处理 {preview_ok} 项，跳过/失败 {skipped} 项"
