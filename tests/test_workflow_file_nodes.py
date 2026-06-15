# -*- coding: utf-8 -*-
import os
import tempfile
import unittest

from workflow.nodes.file_nodes import (
    FILE_LIST_HEADERS,
    apply_batch_rename_node,
    apply_file_list_node,
    get_or_add_column_index,
    is_hidden_path,
    make_numbered_path,
    parse_extensions_filter,
    should_include_file_list_path,
)


class WorkflowFileNodesTests(unittest.TestCase):
    def test_parse_extensions_filter_normalizes_mixed_separators(self):
        self.assertEqual(parse_extensions_filter("txt;.CSV， log  .md"), {".txt", ".csv", ".log", ".md"})
        self.assertEqual(parse_extensions_filter(""), set())

    def test_get_or_add_column_index_extends_short_rows(self):
        idx, headers, rows = get_or_add_column_index(["A"], [["x"], []], "B")

        self.assertEqual(idx, 1)
        self.assertEqual(headers, ["A", "B"])
        self.assertEqual(rows, [["x", ""], [""]])

    def test_should_include_file_list_path_filters_name_glob_extension_and_hidden(self):
        with tempfile.TemporaryDirectory() as tmp:
            txt_path = os.path.join(tmp, "report.TXT")
            hidden_path = os.path.join(tmp, ".secret.txt")
            os.mkdir(os.path.join(tmp, "folder"))
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write("hello")
            with open(hidden_path, "w", encoding="utf-8") as f:
                f.write("hidden")

            options = {
                "include_files": True,
                "include_dirs": False,
                "include_hidden": False,
                "name_contains": "port",
                "glob_pattern": "*.TXT",
                "ext_filter": {".txt"},
            }

            self.assertTrue(should_include_file_list_path(txt_path, False, options))
            self.assertFalse(should_include_file_list_path(hidden_path, False, options))
            self.assertFalse(should_include_file_list_path(os.path.join(tmp, "folder"), True, options))

            options["include_dirs"] = True
            options["name_contains"] = ""
            options["glob_pattern"] = "*"
            self.assertTrue(should_include_file_list_path(os.path.join(tmp, "folder"), True, options))

    def test_apply_file_list_node_non_recursive_filters_and_limits(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = [
                os.path.join(tmp, "alpha.txt"),
                os.path.join(tmp, "beta.csv"),
                os.path.join(tmp, "nested"),
            ]
            os.mkdir(paths[2])
            for path in paths[:2]:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(os.path.basename(path))
            with open(os.path.join(paths[2], "inside.txt"), "w", encoding="utf-8") as f:
                f.write("inside")

            headers, rows, message = apply_file_list_node(
                [],
                [],
                {
                    "directory": tmp,
                    "recursive": False,
                    "include_files": True,
                    "include_dirs": False,
                    "extensions": "txt,csv",
                    "max_files": "1",
                },
            )

            self.assertEqual(headers, FILE_LIST_HEADERS)
            self.assertEqual(len(rows), 1)
            self.assertIn(rows[0][0], {"alpha.txt", "beta.csv"})
            self.assertEqual(rows[0][7], "否")
            self.assertIn("读取文件列表 1 项", message)
            self.assertNotIn("inside.txt", [row[0] for row in rows])

    def test_apply_file_list_node_recursive_includes_dirs_and_skips_hidden(self):
        with tempfile.TemporaryDirectory() as tmp:
            visible_dir = os.path.join(tmp, "visible")
            hidden_dir = os.path.join(tmp, ".hidden")
            os.mkdir(visible_dir)
            os.mkdir(hidden_dir)
            with open(os.path.join(visible_dir, "keep.txt"), "w", encoding="utf-8") as f:
                f.write("keep")
            with open(os.path.join(hidden_dir, "skip.txt"), "w", encoding="utf-8") as f:
                f.write("skip")

            headers, rows, _message = apply_file_list_node(
                [],
                [],
                {
                    "directory": tmp,
                    "recursive": True,
                    "include_files": True,
                    "include_dirs": True,
                    "include_hidden": False,
                    "extensions": "txt",
                },
            )

            names = [row[0] for row in rows]
            self.assertEqual(headers, FILE_LIST_HEADERS)
            self.assertIn("visible", names)
            self.assertIn("keep.txt", names)
            self.assertNotIn(".hidden", names)
            self.assertNotIn("skip.txt", names)
            self.assertTrue(is_hidden_path(hidden_dir))

    def test_apply_file_list_node_uses_default_directory_and_cancel_callback(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "a.txt"), "w", encoding="utf-8") as f:
                f.write("a")
            calls = []

            def cancel(_index=None):
                calls.append(_index)
                raise RuntimeError("用户取消")

            with self.assertRaisesRegex(RuntimeError, "用户取消"):
                apply_file_list_node(
                    [],
                    [],
                    {"recursive": True},
                    context={"default_directory": tmp, "check_cancelled": cancel},
                )

            self.assertEqual(calls, [None])

    def test_apply_file_list_node_reports_non_recursive_progress(self):
        with tempfile.TemporaryDirectory() as tmp:
            for i in range(200):
                with open(os.path.join(tmp, f"{i:03d}.txt"), "w", encoding="utf-8") as f:
                    f.write(str(i))
            progress = []

            headers, rows, _message = apply_file_list_node(
                [],
                [],
                {"directory": tmp, "recursive": False, "max_files": "200"},
                context={"report_progress": lambda **item: progress.append(item)},
            )

            self.assertEqual(headers, FILE_LIST_HEADERS)
            self.assertEqual(len(rows), 200)
            self.assertEqual(progress[-1]["current"], 200)
            self.assertEqual(progress[-1]["total"], 200)
            self.assertIn("正在扫描 200/200", progress[-1]["message"])

    def test_make_numbered_path_uses_first_available_suffix(self):
        existing = {os.path.abspath("name.txt"), os.path.abspath("name_1.txt")}

        result = make_numbered_path(
            os.path.abspath("name.txt"),
            path_exists=lambda path: os.path.abspath(path) in existing,
        )

        self.assertEqual(result, os.path.abspath("name_2.txt"))

    def test_apply_batch_rename_node_preview_generates_paths_and_statuses(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "old.txt")
            with open(src, "w", encoding="utf-8") as f:
                f.write("old")

            headers, rows, message = apply_batch_rename_node(
                ["完整路径", "新文件名"],
                [[src, "new"]],
                {"auto_append_ext": True, "actual_rename": True},
                execute_actions=False,
                context={"timestamp": "2026-01-01 00:00:00"},
            )

            self.assertEqual(headers, ["完整路径", "新文件名", "新完整路径", "重命名状态"])
            self.assertEqual(rows[0][2], os.path.join(tmp, "new.txt"))
            self.assertEqual(rows[0][3], "预览可重命名")
            self.assertEqual(message, "重命名预览：可处理 1 项，跳过/失败 0 项")
            self.assertTrue(os.path.exists(src))

    def test_apply_batch_rename_node_preview_handles_conflicts_and_missing_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "old.txt")
            target = os.path.join(tmp, "exists.txt")
            with open(src, "w", encoding="utf-8") as f:
                f.write("old")
            with open(target, "w", encoding="utf-8") as f:
                f.write("target")

            context = {"timestamp": "2026-01-01 00:00:00"}
            headers, rows, message = apply_batch_rename_node(
                ["完整路径", "新文件名"],
                [[src, "exists.txt"], ["", "x"], [src, ""]],
                {"conflict_mode": "自动加编号", "actual_rename": True},
                context=context,
            )

            self.assertEqual(rows[0][2], os.path.join(tmp, "exists_1.txt"))
            self.assertEqual(rows[0][3], "预览可重命名：自动加编号")
            self.assertEqual(rows[1][3], "跳过：原路径为空")
            self.assertEqual(rows[2][3], "跳过：新名称为空")
            self.assertEqual(message, "重命名预览：可处理 1 项，跳过/失败 2 项")
            self.assertEqual(context["batch_rename_preview_ok"], 1)
            self.assertEqual(context["batch_rename_skipped"], 2)
            self.assertEqual(context["batch_rename_log_rows"][0][4], "2026-01-01 00:00:00")

    def test_apply_batch_rename_node_executes_with_injected_callbacks(self):
        src = os.path.abspath("src.txt")
        dst = os.path.abspath("dst.txt")
        calls = []
        context = {
            "timestamp": "2026-01-01 00:00:00",
            "path_exists": lambda path: os.path.abspath(path) == src,
            "path_is_dir": lambda path: os.path.abspath(path) == os.getcwd(),
            "rename_file": lambda source, target: calls.append(("rename", source, target)),
        }

        headers, rows, message = apply_batch_rename_node(
            ["完整路径", "新文件名"],
            [[src, "dst.txt"]],
            {"actual_rename": True},
            execute_actions=True,
            context=context,
        )

        self.assertEqual(rows[0][2], dst)
        self.assertEqual(rows[0][3], "已重命名")
        self.assertEqual(calls, [("rename", src, dst)])
        self.assertEqual(message, "实际重命名 1 项，跳过/失败 0 项")
        self.assertTrue(context["batch_rename_do_rename"])

    def test_apply_batch_rename_node_execute_replace_and_create_target_dir(self):
        src = os.path.abspath("src.txt")
        dst = os.path.abspath(os.path.join("target", "dst.txt"))
        calls = []

        def path_exists(path):
            return os.path.abspath(path) in {src, dst}

        def path_is_dir(path):
            return os.path.abspath(path) == os.getcwd()

        context = {
            "path_exists": path_exists,
            "path_is_dir": path_is_dir,
            "make_dirs": lambda path: calls.append(("mkdir", os.path.abspath(path))),
            "replace_file": lambda source, target: calls.append(("replace", source, target)),
        }

        _headers, rows, message = apply_batch_rename_node(
            ["完整路径", "新完整路径"],
            [[src, dst]],
            {
                "new_name_field": "新完整路径",
                "name_value_type": "完整路径",
                "conflict_mode": "覆盖目标（危险）",
                "create_target_dirs": True,
                "actual_rename": True,
            },
            execute_actions=True,
            context=context,
        )

        self.assertEqual(rows[0][2], "已重命名：覆盖目标，已创建目标目录")
        self.assertEqual(calls[0], ("mkdir", os.path.dirname(dst)))
        self.assertEqual(calls[1], ("replace", src, dst))
        self.assertEqual(message, "实际重命名 1 项，跳过/失败 0 项")

    def test_apply_batch_rename_node_errors_and_progress_callbacks(self):
        progress = []

        with self.assertRaisesRegex(ValueError, "找不到原路径字段"):
            apply_batch_rename_node(["A"], [["x"]], {})

        def cancel(_index=None):
            raise RuntimeError("用户取消")

        with self.assertRaisesRegex(RuntimeError, "用户取消"):
            apply_batch_rename_node(
                ["完整路径", "新文件名"],
                [["missing", "x"]],
                {},
                context={"check_cancelled": cancel},
            )

        headers, rows, message = apply_batch_rename_node(
            ["完整路径", "新文件名"],
            [["missing", "x"]],
            {},
            context={"report_progress": lambda **item: progress.append(item)},
        )

        self.assertEqual(rows[0][3], "跳过：原路径不存在")
        self.assertEqual(message, "重命名预览：可处理 0 项，跳过/失败 1 项")
        self.assertEqual(progress[0]["node_name"], "批量重命名")
        self.assertEqual(progress[-1]["message"], "批量重命名节点处理完成")


if __name__ == "__main__":
    unittest.main()
