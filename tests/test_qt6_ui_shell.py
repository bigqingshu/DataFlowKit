# -*- coding: utf-8 -*-
import unittest
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from ui_qt import app as qt_app
from ui_qt.config_form import NodeConfigForm, coerce_form_value, format_form_value, value_kind
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
from ui_qt.qt_compat import QtBindingUnavailable
from workflow.node_ui_schema import get_node_ui_schema


class Qt6UiShellTests(unittest.TestCase):
    def wait_for_controller_job(self, app, controller, timeout=2.0):
        deadline = time.time() + timeout
        while controller.current_job_id and time.time() < deadline:
            app.processEvents()
            time.sleep(0.01)
        app.processEvents()
        self.assertFalse(controller.current_job_id)

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

    def test_facade_builds_output_settings_and_combined_validation(self):
        client = QtHeadlessEngineClient()

        settings = client.build_output_settings(
            output_mode="保存为SQLite新表",
            output_table="结果表",
            db_path="demo.db",
        )
        validation = client.validate_workflow_request(
            SAMPLE_PLAN,
            execute_actions=True,
            output_settings=settings["settings"],
        )

        self.assertTrue(settings["ok"])
        self.assertEqual(settings["settings"]["mode"], "保存为SQLite新表")
        self.assertEqual(settings["settings"]["target"], "结果表")
        self.assertIn("validation", validation)
        self.assertIn("jump_validation", validation)
        self.assertIn("access_precheck", validation)

    def test_facade_lists_node_ui_catalog_and_preview_sources(self):
        client = QtHeadlessEngineClient()

        catalog = client.list_node_ui_catalog(preview_headers=["A", "B"])
        self.assertTrue(catalog["ok"])
        self.assertEqual(catalog["catalog"]["schema_version"], "2.0")
        first_group = catalog["catalog"]["groups"][0]
        self.assertIn("group", first_group)
        self.assertTrue(first_group["items"])
        first_item = first_group["items"][0]
        self.assertIn("submenu", first_item)
        self.assertIn("supported_headless", first_item)

        preview_sources = client.list_preview_sources(
            current_headers=["A"],
            current_rows=[["a"]],
            preview_headers=["A", "B"],
            preview_rows=[["a", "b"]],
        )
        self.assertTrue(preview_sources["sources"])
        self.assertEqual(preview_sources["sources"][0]["source"]["table_role"], "input")

        preview_loaded = client.load_preview_source(
            {"type": "memory", "table_role": "preview"},
            current_headers=["A"],
            current_rows=[["a"]],
            preview_headers=["A", "B"],
            preview_rows=[["a", "b"]],
        )
        self.assertTrue(preview_loaded["ok"])
        self.assertEqual(preview_loaded["table"]["headers"], ["A", "B"])
        self.assertEqual(preview_loaded["title"], "Headless 预览结果")

        panel_state = client.build_workflow_panel_state(
            plan=SAMPLE_PLAN,
            current_headers=SAMPLE_PLAN["headers"],
            current_rows=SAMPLE_PLAN["rows"],
            selected_index=0,
        )
        self.assertTrue(panel_state["ok"])
        self.assertEqual(panel_state["input_summary"], "当前输入：3 行 x 4 列")
        self.assertEqual(panel_state["selected_node"]["node_type_id"], "core.new_columns")
        self.assertTrue(panel_state["node_items"])

        output_form = client.describe_output_form({"output_mode": "覆盖当前表"})
        self.assertTrue(output_form["ok"])
        self.assertEqual(output_form["settings"]["mode"], "覆盖当前表")
        output_fields = {field["key"]: field for field in output_form["form"]["fields"]}
        self.assertEqual(output_fields["backup_before_overwrite"]["visible_when"], {"field": "mode", "equals": "覆盖当前表"})

    def test_facade_describes_workflow_actions_and_progress(self):
        client = QtHeadlessEngineClient()

        idle_actions = client.describe_workflow_actions(
            plan=SAMPLE_PLAN,
            selected_indexes=[0],
            is_running=False,
        )
        self.assertTrue(idle_actions["ok"])
        self.assertTrue(idle_actions["actions"]["delete_nodes"]["enabled"])
        self.assertFalse(idle_actions["actions"]["move_node_up"]["enabled"])
        self.assertFalse(idle_actions["actions"]["move_node_down"]["enabled"])
        self.assertTrue(idle_actions["actions"]["apply_node_config"]["enabled"])
        self.assertFalse(idle_actions["actions"]["cancel_job"]["enabled"])

        running_actions = client.describe_workflow_actions(
            plan=SAMPLE_PLAN,
            selected_indexes=[0],
            is_running=True,
        )
        self.assertFalse(running_actions["actions"]["delete_nodes"]["enabled"])
        self.assertFalse(running_actions["actions"]["execute_plan"]["enabled"])
        self.assertTrue(running_actions["actions"]["cancel_job"]["enabled"])

        start_progress = client.build_job_progress_state(
            current_job_id="job-1",
            title="预览结果",
            running=True,
        )
        self.assertEqual(start_progress["progress"]["workflow_label"], "任务已启动：job-1")
        self.assertEqual(start_progress["progress"]["workflow_value"], 0)

        node_progress = client.build_job_progress_state(
            current_job_id="job-1",
            title="预览结果",
            event={
                "type": "node_progress",
                "message": "处理中 5/10",
                "current": 5,
                "total": 10,
            },
            running=True,
        )
        self.assertEqual(node_progress["progress"]["node_label"], "处理中 5/10")
        self.assertEqual(node_progress["progress"]["node_value"], 50)

        final_progress = client.build_job_progress_state(
            title="执行结果",
            final={
                "table": {
                    "headers": ["A", "B"],
                    "rows": [["a", "b"]],
                },
                "steps": 3,
            },
        )
        self.assertEqual(final_progress["progress"]["workflow_label"], "执行结果完成：1 行 x 2 列")
        self.assertEqual(final_progress["progress"]["node_label"], "执行步数：3")

    def test_facade_builds_standard_feedback_payloads(self):
        client = QtHeadlessEngineClient()

        selection_feedback = client.describe_selection_feedback(selected_index=None, purpose="预览")
        self.assertEqual(selection_feedback["feedback"]["status_message"], "预览前需要先选择节点")
        self.assertEqual(selection_feedback["feedback"]["issues"][0]["code"], "selection_required")

        conflict_feedback = client.describe_job_run_conflict(current_job_id="job-42")
        self.assertEqual(conflict_feedback["feedback"]["status_message"], "后台任务运行中")
        self.assertIn("job-42", conflict_feedback["feedback"]["logs"][0])

        failure_feedback = client.describe_job_start_failure(status_prefix="执行", error="boom")
        self.assertFalse(failure_feedback["ok"])
        self.assertEqual(failure_feedback["feedback"]["status_message"], "执行启动失败")
        self.assertEqual(failure_feedback["feedback"]["issue_message"], "boom")

        validation = client.validate_workflow_request(SAMPLE_PLAN, execute_actions=True)
        validation_feedback = client.describe_validation_feedback(validation)
        self.assertEqual(validation_feedback["feedback"]["status_message"], "校验通过")
        self.assertIn("OK: true", validation_feedback["feedback"]["issue_message"])

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

    def test_config_form_supports_structured_list_fields(self):
        try:
            qt = qt_app.load_qt6()
        except QtBindingUnavailable as exc:
            self.skipTest(str(exc))
        app = qt.QtWidgets.QApplication.instance() or qt.QtWidgets.QApplication([])
        schema = get_node_ui_schema("批量更改列名", preview_headers=["A", "B"])
        node = {
            "node_type_id": "core.rename_columns",
            "node_id": "n1",
            "name": "批量更改列名",
            "enabled": True,
            "node_version": "1.0.0",
            "config": {
                "mode": "手动映射改名",
                "mappings": [{"old": "A", "new": "AA"}],
            },
        }
        form = NodeConfigForm(qt, headers=["A", "B"])
        form.set_node(node, headers=["A", "B"], schema=schema)
        self.assertEqual(form.config_fields["mappings"]["kind"], "structured_list")
        editor = form.config_fields["mappings"]["editor"]
        table = editor.structured_state["table"]
        self.assertEqual(table.rowCount(), 1)
        self.assertEqual(table.columnCount(), 2)
        self.assertIsNotNone(table.cellWidget(0, 0))
        self.assertIsNotNone(table.cellWidget(0, 1))
        self.assertEqual(table.cellWidget(0, 0).currentText(), "A")
        self.assertEqual(table.cellWidget(0, 1).text(), "AA")
        form._structured_list_add_row(editor)
        table.setCurrentCell(1, 0)
        table.cellWidget(1, 0).setCurrentText("B")
        table.cellWidget(1, 1).setText("BB")
        converted = form.to_node()
        self.assertEqual(converted["config"]["mappings"], [{"old": "A", "new": "AA"}, {"old": "B", "new": "BB"}])
        app.processEvents()

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
        self.assertEqual(schema["schema_version"], "2.0")
        self.assertEqual(schema["form"]["schema_version"], "2.0")
        self.assertTrue(schema["form"]["dynamic_rules"])
        self.assertEqual(schema["menu"]["path"], ["数据处理", "新建列"])
        self.assertEqual(schema["menu"]["group"], "数据处理")
        self.assertEqual(schema["menu"]["submenu"], ["新建列"])
        self.assertEqual(schema["form"]["groups"][0]["fields"][0]["key"], "columns_text")
        new_column_fields = {
            field["key"]: field
            for group in schema["form"]["groups"]
            for field in group["fields"]
        }
        self.assertTrue(new_column_fields["columns_text"]["required"])
        self.assertEqual(
            new_column_fields["default_value"]["visible_when"],
            {"field": "value_mode", "equals": "统一默认值"},
        )
        replace_schema = get_node_ui_schema("core.replace", preview_headers=["A", "B"])
        replace_fields = {
            field["key"]: field
            for group in replace_schema["form"]["groups"]
            for field in group["fields"]
        }
        self.assertEqual(replace_fields["target_field"]["options_source"], {"type": "preview_headers"})
        self.assertEqual(
            replace_fields["match_value_field"]["visible_when"],
            {"field": "match_value_source", "equals": "列字段"},
        )
        self.assertEqual(replace_fields["replace_count"]["validation"], {"integer": True, "min": 0})

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
        client = QtHeadlessEngineClient()
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            json_path = root / "rows.json"
            csv_path = root / "rows.csv"
            json_path.write_text('[{"A": "a", "B": 1}, {"A": "b", "B": 2}]', encoding="utf-8")
            csv_path.write_text("A,B\na,1\nb,2\n", encoding="utf-8")

            imported = client.import_table_file(json_path)
            self.assertEqual(imported["table"]["headers"], ["A", "B"])
            self.assertEqual(imported["table"]["rows"], [["a", 1], ["b", 2]])

            imported = client.import_table_file(csv_path)
            self.assertEqual(imported["table"]["headers"], ["A", "B"])
            self.assertEqual(imported["table"]["rows"], [["a", "1"], ["b", "2"]])

    def test_original_style_workflow_panel_controller_operations(self):
        try:
            qt = qt_app.load_qt6()
        except QtBindingUnavailable as exc:
            self.skipTest(str(exc))
        app = qt.QtWidgets.QApplication.instance() or qt.QtWidgets.QApplication([])
        window = build_main_window(qt)
        controller = window.qt_workflow_controller
        window.show()
        app.processEvents()

        self.assertEqual(controller.input_summary_label.text(), "当前输入：3 行 x 4 列")
        self.assertEqual(controller.config_header_label.text().startswith("节点类型："), True)
        self.assertGreater(controller.node_type_combo.count(), 0)
        self.assertGreater(controller.catalog_tree.topLevelItemCount(), 0)
        self.assertEqual(controller.node_list.count(), 1)
        self.assertIn("未保存", controller.status_bar.currentMessage())
        self.assertEqual(controller.output_mode_combo.itemText(0), "输出到主界面预览区")
        self.assertEqual(controller.output_mode_combo.currentText(), "输出到主界面预览区")
        self.assertEqual(controller.output_db_path_edit.text(), "")
        self.assertEqual(controller.output_path_edit.text(), "")
        self.assertFalse(controller.output_form_fields["backup_before_overwrite"]["editor"].isVisible())
        self.assertTrue(controller.add_node_button.isEnabled())
        self.assertTrue(controller.apply_config_button.isEnabled())
        self.assertFalse(controller.cancel_job_button.isEnabled())

        controller.add_node_by_type("core.replace")
        self.assertEqual(len(controller.current_plan["nodes"]), 2)
        self.assertTrue(controller.config_form.config_fields["match_value_field"]["label"].isHidden())
        controller.config_form.config_fields["match_value_source"]["editor"].setCurrentText("列字段")
        app.processEvents()
        self.assertFalse(controller.config_form.config_fields["match_value_field"]["label"].isHidden())
        controller.copy_selected_node()
        self.assertEqual(len(controller.current_plan["nodes"]), 3)
        copied_node = controller.current_plan["nodes"][controller.selected_node_index()]
        self.assertTrue(copied_node.get("node_id"))
        self.assertTrue(copied_node.get("name", "").endswith("_复制"))
        controller.config_form.config_fields["target_field"]["editor"].setCurrentText("Missing")
        before_config = dict(controller.current_plan["nodes"][controller.selected_node_index()].get("config", {}))
        controller.apply_node_config()
        self.assertEqual(controller.current_plan["nodes"][controller.selected_node_index()].get("config", {}), before_config)
        self.assertIn("目标字段不存在", controller.issue_text.toPlainText())
        controller.toggle_selected_node_enabled()
        self.assertFalse(controller.current_plan["nodes"][controller.selected_node_index()].get("enabled", True))
        controller.toggle_selected_node_enabled()
        controller.node_list.setCurrentRow(0)
        controller.refresh_action_states(is_running=True)
        self.assertFalse(controller.add_node_button.isEnabled())
        self.assertFalse(controller.node_action_buttons["删除"].isEnabled())
        self.assertFalse(controller.run_action_buttons["执行计划"].isEnabled())
        self.assertTrue(controller.cancel_job_button.isEnabled())
        controller.refresh_action_states(is_running=False)
        controller.node_list.setCurrentRow(-1)
        controller.preview_to_selected_node()
        self.assertIn("请先选择一个节点。", controller.issue_text.toPlainText())
        self.assertEqual(controller.status_bar.currentMessage(), "预览前需要先选择节点")
        controller.node_list.setCurrentRow(0)
        controller.preview_to_selected_node()
        self.wait_for_controller_job(app, controller)
        self.assertEqual(controller.current_table_kind, "preview")
        self.assertIn("status", controller.last_preview_headers)
        self.assertEqual(controller.workflow_progress.value(), 100)
        self.assertFalse(controller.cancel_job_button.isEnabled())
        controller.execute_plan()
        self.wait_for_controller_job(app, controller)
        self.assertEqual(controller.current_table_kind, "preview")
        self.assertIn("status", controller.last_preview_headers)
        self.assertTrue(controller.table_title.text().startswith("执行结果"))
        controller.output_mode_combo.setCurrentText("保存为SQLite新表")
        app.processEvents()
        window.show()
        app.processEvents()
        self.assertTrue(controller.output_form_fields["target"]["editor"].isVisible())
        self.assertTrue(controller.output_form_fields["db_path"]["editor"].isVisible())
        controller.execute_plan()
        self.wait_for_controller_job(app, controller)
        self.assertTrue(controller.table_title.text().startswith("执行结果（输出未落地）"))
        self.assertIn("missing_db_path", controller.issue_text.toPlainText())
        self.assertIn("输出设置校验失败", controller.status_bar.currentMessage())
        settings = controller.current_output_settings()
        self.assertEqual(settings["mode"], "保存为SQLite新表")
        window.close()
        app.processEvents()


if __name__ == "__main__":
    unittest.main()
