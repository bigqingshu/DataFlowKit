# -*- coding: utf-8 -*-
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from ui_qt import app as qt_app
from ui_qt.config_form import coerce_form_value, format_form_value, value_kind
from ui_qt.engine_client import QtHeadlessEngineClient, SAMPLE_PLAN
from ui_qt.main_window import build_main_window
from ui_qt.node_ui_metadata import (
    category_label,
    choices_for_field,
    config_layout_for_node,
    config_field_label,
    field_help_text,
    format_node_detail,
    node_badges,
    node_display_label,
    node_field_label,
    node_summary,
    node_warnings,
)
from ui_qt.table_io import load_table_file
from ui_qt.qt_compat import QtBindingUnavailable
from workflow.node_ui_schema import get_node_ui_schema


class Qt6UiShellTests(unittest.TestCase):
    def test_engine_client_previews_sample_plan_by_node_type_id(self):
        client = QtHeadlessEngineClient()

        validation, result = client.validate_and_preview(SAMPLE_PLAN, input_table={
            "type": "table",
            "headers": SAMPLE_PLAN["headers"],
            "rows": SAMPLE_PLAN["rows"],
        })

        self.assertTrue(validation["ok"])
        self.assertIsNotNone(result)
        self.assertEqual(result.headers[-1], "status")
        self.assertEqual(result.rows[0][-1], "ready")

    def test_make_default_node_can_omit_legacy_type(self):
        client = QtHeadlessEngineClient()

        node = client.make_default_node("core.new_columns", preview_headers=["A"])

        self.assertEqual(node["node_type_id"], "core.new_columns")
        self.assertNotIn("type", node)
        self.assertIn("columns_text", node["config"])

    def test_config_form_value_helpers_preserve_types(self):
        self.assertEqual(value_kind(True), "bool")
        self.assertEqual(value_kind(3), "int")
        self.assertEqual(value_kind(1.5), "float")
        self.assertEqual(value_kind(["A"]), "json")
        self.assertEqual(value_kind({"A": 1}), "json")
        self.assertEqual(value_kind("3"), "text")

        self.assertEqual(format_form_value({"A": 1}), '{\n  "A": 1\n}')
        self.assertEqual(coerce_form_value("int", "7"), 7)
        self.assertEqual(coerce_form_value("float", "1.25"), 1.25)
        self.assertEqual(coerce_form_value("json", '["A", "B"]'), ["A", "B"])
        self.assertEqual(coerce_form_value("text", "7"), "7")

    def test_node_ui_metadata_maps_protocol_to_chinese_ui(self):
        self.assertEqual(node_display_label("core.new_columns"), "新建列")
        self.assertEqual(category_label("数据处理"), "数据处理")
        self.assertEqual(node_field_label("enabled"), "启用")
        self.assertEqual(config_field_label("columns_text"), "新字段列表")
        self.assertEqual(choices_for_field("target_field", headers=["A", "B"]), ["A", "B"])
        self.assertIn("按列配置值", choices_for_field("value_mode"))
        self.assertEqual(config_layout_for_node("core.new_columns")[0]["title"], "字段定义")
        self.assertEqual(config_layout_for_node("批量替换")[0]["title"], "目标与匹配")
        self.assertIn("每行一个新字段", field_help_text("columns_text"))
        self.assertIn("添加字段", node_summary("core.new_columns"))
        self.assertIn("可预览", node_badges("core.replace", supported_headless=True))
        self.assertTrue(node_warnings("core.delete_columns"))
        self.assertIn("暂不支持", format_node_detail("core.filter", supported_headless=False))
        schema = get_node_ui_schema("core.new_columns", preview_headers=["A"])
        self.assertEqual(schema["menu"]["path"], ["数据处理", "新建列"])
        self.assertEqual(schema["form"]["groups"][0]["fields"][0]["key"], "columns_text")

    def test_qt6_loader_rejects_qt5_binding(self):
        with self.assertRaises(QtBindingUnavailable):
            qt_app.load_qt6("PyQt5")

    def test_parse_args_supports_smoke_and_offscreen(self):
        args = qt_app.parse_args(["--smoke", "--offscreen", "--binding", "PySide6"])

        self.assertTrue(args.smoke)
        self.assertTrue(args.offscreen)
        self.assertEqual(args.binding, "PySide6")

    def test_qt6_loader_tries_pyside6_then_pyqt6(self):
        calls = []

        def fake_get_qt(binding):
            calls.append(binding)
            if binding == "PySide6":
                raise QtBindingUnavailable("missing")
            return object()

        with patch("ui_qt.app.get_qt", side_effect=fake_get_qt):
            result = qt_app.load_qt6()

        self.assertIsNotNone(result)
        self.assertEqual(calls, ["PySide6", "PyQt6"])

    def test_table_io_loads_json_rows_and_csv(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            json_path = root / "rows.json"
            csv_path = root / "rows.csv"
            json_path.write_text('[{"A": "a", "B": 1}, {"A": "b", "B": 2}]', encoding="utf-8")
            csv_path.write_text("A,B\na,1\nb,2\n", encoding="utf-8")

            headers, rows = load_table_file(json_path)
            self.assertEqual(headers, ["A", "B"])
            self.assertEqual(rows, [["a", 1], ["b", 2]])

            headers, rows = load_table_file(csv_path)
            self.assertEqual(headers, ["A", "B"])
            self.assertEqual(rows, [["a", "1"], ["b", "2"]])

    def test_original_style_workflow_panel_controller_operations(self):
        try:
            qt = qt_app.load_qt6()
        except QtBindingUnavailable as exc:
            self.skipTest(str(exc))
        app = qt.QtWidgets.QApplication.instance() or qt.QtWidgets.QApplication([])
        window = build_main_window(qt)
        controller = window.qt_workflow_controller

        self.assertEqual(controller.input_summary_label.text(), "当前输入：3 行 x 4 列")
        self.assertEqual(controller.config_header_label.text().startswith("节点类型："), True)
        self.assertGreater(controller.node_type_combo.count(), 0)
        self.assertGreater(controller.catalog_tree.topLevelItemCount(), 0)
        self.assertEqual(controller.node_list.count(), 1)

        controller.add_node_by_type("core.replace")
        self.assertEqual(len(controller.current_plan["nodes"]), 2)
        controller.copy_selected_node()
        self.assertEqual(len(controller.current_plan["nodes"]), 3)
        controller.toggle_selected_node_enabled()
        self.assertFalse(controller.current_plan["nodes"][controller.selected_node_index()].get("enabled", True))
        controller.toggle_selected_node_enabled()
        controller.node_list.setCurrentRow(0)
        controller.preview_to_selected_node()
        self.assertEqual(controller.current_table_kind, "preview")
        self.assertIn("status", controller.last_preview_headers)
        window.close()
        app.processEvents()


if __name__ == "__main__":
    unittest.main()
