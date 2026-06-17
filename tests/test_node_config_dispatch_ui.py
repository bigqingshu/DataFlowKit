# -*- coding: utf-8 -*-
import unittest

from workflow.node_config_dispatch_ui import dispatch_node_config_builder


class NodeConfigDispatchUiTests(unittest.TestCase):
    def make_window(self):
        class Window:
            def __init__(self):
                self.calls = []
                self.config_frame = None

            def get_transit_context_before(self, idx):
                self.calls.append(("get_transit", idx))
                return {"transit": idx}

            def build_replace_config(self, config, headers):
                self.calls.append(("replace", config, headers))
                return "replace"

            def build_group_node_config(self, config, headers, transit_context=None):
                self.calls.append(("group", config, headers, transit_context))
                return "group"

            def build_plugin_node_config(self, config, headers, transit_context=None, current_rows=None):
                self.calls.append(("plugin", config, headers, transit_context, current_rows))
                return "plugin"

            def build_selected_columns_write_config(self, config, headers, idx=None, transit_context=None):
                self.calls.append(("selected_write", config, headers, idx, transit_context))
                return "selected_write"

            def build_file_list_config(self, config):
                self.calls.append(("file_list", config))
                return "file_list"

        return Window()

    def test_dispatches_header_builder(self):
        window = self.make_window()
        config = {"a": 1}

        result = dispatch_node_config_builder(window, 2, "批量替换", config, ["A"], [["a"]])

        self.assertEqual(result, "replace")
        self.assertEqual(window.calls, [("replace", config, ["A"])])

    def test_dispatches_transit_header_builder(self):
        window = self.make_window()
        config = {}

        result = dispatch_node_config_builder(window, 3, "节点组 / 子工作流", config, ["A"], [])

        self.assertEqual(result, "group")
        self.assertEqual(window.calls, [
            ("get_transit", 3),
            ("group", config, ["A"], {"transit": 3}),
        ])

    def test_dispatches_plugin_with_current_rows(self):
        window = self.make_window()
        config = {}

        result = dispatch_node_config_builder(window, 4, "插件节点", config, ["A"], [["a"]])

        self.assertEqual(result, "plugin")
        self.assertEqual(window.calls, [
            ("get_transit", 4),
            ("plugin", config, ["A"], {"transit": 4}, [["a"]]),
        ])

    def test_dispatches_selected_columns_write_with_index(self):
        window = self.make_window()
        config = {}

        result = dispatch_node_config_builder(window, 5, "选定列写入指定表", config, ["A"], [])

        self.assertEqual(result, "selected_write")
        self.assertEqual(window.calls, [
            ("get_transit", 5),
            ("selected_write", config, ["A"], 5, {"transit": 5}),
        ])

    def test_dispatches_config_only_builder(self):
        window = self.make_window()
        config = {}

        result = dispatch_node_config_builder(window, 1, "获取文件列表", config, ["A"], [])

        self.assertEqual(result, "file_list")
        self.assertEqual(window.calls, [("file_list", config)])


if __name__ == "__main__":
    unittest.main()
