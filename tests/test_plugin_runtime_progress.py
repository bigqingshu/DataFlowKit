# -*- coding: utf-8 -*-
import unittest

from plugin_runtime.progress import handle_plugin_stdout_line


class PluginRuntimeProgressTests(unittest.TestCase):
    def test_progress_json_updates_callback_and_logs_message(self):
        logs = []
        events = []

        handle_plugin_stdout_line(
            '{"type":"node_progress","current":1,"total":2,"message":"处理中"}',
            logs,
            progress_callback=events.append,
            node_name="节点A",
            plugin_id="plugin_a",
        )

        self.assertEqual(logs, [{"level": "INFO", "message": "处理中"}])
        self.assertEqual(events[0]["node_name"], "节点A")
        self.assertEqual(events[0]["plugin_id"], "plugin_a")
        self.assertEqual(events[0]["current"], 1)

    def test_node_log_preserves_type_for_callback(self):
        logs = []
        events = []

        handle_plugin_stdout_line(
            '{"type":"node_log","level":"WARNING","message":"提示"}',
            logs,
            progress_callback=events.append,
            node_name="插件节点",
            plugin_id="demo",
        )

        self.assertEqual(events[0]["type"], "node_log")
        self.assertEqual(logs, [{"level": "WARNING", "message": "提示"}])

    def test_plain_text_and_non_progress_json_become_info_logs(self):
        logs = []

        handle_plugin_stdout_line("普通输出", logs)
        handle_plugin_stdout_line('{"ok": true}', logs)

        self.assertEqual(logs, [
            {"level": "INFO", "message": "普通输出"},
            {"level": "INFO", "message": '{"ok": true}'},
        ])

    def test_empty_line_is_ignored(self):
        logs = []
        handle_plugin_stdout_line("\n", logs)
        self.assertEqual(logs, [])


if __name__ == "__main__":
    unittest.main()

