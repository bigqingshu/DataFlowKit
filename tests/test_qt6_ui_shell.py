# -*- coding: utf-8 -*-
import copy
import os
import unittest
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from db.table_manager import TableAccessManager
from engine.plugin_service import PluginService
from ui_qt import app as qt_app
from ui_qt.config_form import NodeConfigForm, coerce_form_value, format_form_value, value_kind
from ui_qt.engine_client import QtHeadlessEngineClient, SAMPLE_HEADERS, SAMPLE_PLAN
from ui_qt.main_window import QtWorkflowMainWindow, build_main_window
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
from ui_qt.qt_compat import QtBindingUnavailable, qt_enum
from workflow.node_ui_schema import build_node_detail_payload, get_node_ui_schema
from workflow.node_config_context_cache import build_preview_context_cache


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
        self.assertEqual(preview_loaded["view_state"]["table_kind"], "preview")
        self.assertEqual(preview_loaded["view_state"]["table_title"], "Headless 预览结果")
        self.assertEqual(preview_loaded["message_panel"]["title"], "预览来源")

        preview_panel = client.build_preview_panel_state(
            current_source={"type": "memory", "table_role": "preview"},
            current_headers=["A"],
            current_rows=[["a"]],
            preview_headers=["A", "B"],
            preview_rows=[["a", "b"]],
        )
        self.assertEqual(preview_panel["selected_key"], "memory:preview:")
        self.assertEqual(preview_panel["title"], "Headless 预览结果")

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

        output_panel = client.build_output_panel_state({"output_mode": "导出为xlsx"})
        output_panel_fields = {field["key"]: field for field in output_panel["fields"]}
        self.assertTrue(output_panel_fields["path"]["visible"])
        self.assertFalse(output_panel_fields["db_path"]["visible"])
        self.assertEqual(output_panel_fields["path"]["action"]["key"], "browse_output_path")
        self.assertFalse(output_panel["view_state"]["refresh_preview_sources"])

        sqlite_output_panel = client.build_output_panel_state({"output_mode": "保存为SQLite新表"})
        self.assertTrue(sqlite_output_panel["view_state"]["refresh_preview_sources"])
        self.assertIn("db_path", sqlite_output_panel["view_state"]["visible_field_keys"])

        node_detail = client.describe_node_detail("core.new_columns", preview_headers=["A"])
        self.assertTrue(node_detail["ok"])
        self.assertEqual(node_detail["detail"]["node_type_id"], "core.new_columns")
        self.assertTrue(node_detail["detail"]["sections"])

    def test_engine_client_exposes_plugin_config_options(self):
        class FakeEngine:
            def __init__(self):
                self.calls = []

            def resolve_plugin_config_options(self, plugin_id, **kwargs):
                self.calls.append({"plugin_id": plugin_id, **copy.deepcopy(kwargs)})
                return {
                    "ok": True,
                    "schema_version": "DataFlowKit.plugin_config_options.v1",
                    "choices": ["A"],
                }

        fake = FakeEngine()
        client = QtHeadlessEngineClient(engine=fake)

        result = client.resolve_plugin_config_options(
            "plugin.demo",
            field_key="mapping.content_field",
            current_values={"row": 1},
            view_id="visual_mapping.rules",
            section="rules",
            config={"params": {"config_name": "default"}},
            input_table={"headers": ["A"], "rows": []},
            context={"input_tables": {}},
        )

        self.assertTrue(result["ok"])
        self.assertEqual(fake.calls[0]["plugin_id"], "plugin.demo")
        self.assertEqual(fake.calls[0]["field_key"], "mapping.content_field")
        self.assertEqual(fake.calls[0]["current_values"], {"row": 1})
        self.assertEqual(fake.calls[0]["view_id"], "visual_mapping.rules")
        self.assertEqual(fake.calls[0]["section"], "rules")

    def test_qt_shell_lists_and_configures_plugin_nodes(self):
        try:
            qt = qt_app.load_qt6()
        except QtBindingUnavailable as exc:
            self.skipTest(str(exc))

        with TemporaryDirectory(dir=os.getcwd()) as temp_dir:
            plugin = Path(temp_dir) / "demo_plugin.py"
            plugin.write_text(
                "\n".join([
                    "PLUGIN_INFO = {'id': 'demo', 'name': 'Demo', 'api_version': '1.0', 'version': '0.1', 'description': 'Demo plugin'}",
                    "PARAMETER_SCHEMA = [",
                    "    {'name': 'field', 'label': '字段', 'type': 'field_select', 'default': 'A', 'required': True},",
                    "    {'name': 'limit', 'label': '数量', 'type': 'int', 'default': 3},",
                    "    {'name': 'mode', 'label': '模式', 'type': 'dynamic_select', 'default': 'fast'},",
                    "]",
                    "def get_dynamic_parameter_options(param_name, params, context):",
                    "    return ['fast', 'safe'] if param_name == 'mode' else []",
                    "def open_config_window(parent, current_params, context):",
                    "    params = dict(current_params)",
                    "    params['limit'] = 11",
                    "    return params",
                    "def describe_config(params, context):",
                    "    items = list(params.get('items') or [{'name': 'alpha', 'enabled': True}, {'name': 'beta', 'enabled': False}])",
                    "    return {",
                    "        'schema_version': 'demo.config.v1',",
                    "        'views': [",
                    "            {'view_id': 'demo.overview', 'title': 'Demo Overview', 'kind': 'summary', 'summary': {'items': len(items), 'mode': params.get('mode', 'fast')}},",
                    "            {'view_id': 'demo.details', 'title': 'Demo Details', 'kind': 'form', 'values': {'mode': params.get('mode', 'fast'), 'limit': params.get('limit', 3)}, 'form': {'groups': [{'title': '基本', 'fields': [{'key': 'mode', 'label': '模式', 'help': '运行模式'}, {'key': 'limit', 'label': '数量', 'help': '处理数量'}]}]}},",
                    "            {'view_id': 'demo.preview', 'title': 'Demo Preview', 'kind': 'text_preview', 'text': 'mode=' + str(params.get('mode', 'fast'))},",
                    "            {'view_id': 'demo.items', 'title': 'Demo Items', 'kind': 'structured_list', 'editor_kind': 'demo.items', 'config_path': ['items'], 'item_count': len(items), 'columns': [{'key': 'name', 'label': '名称'}, {'key': 'enabled', 'label': '启用'}], 'items': items, 'append_value': {'name': 'from_view', 'enabled': True}, 'patch_operations': ['append_item', 'delete_item', 'set_enabled', 'move_item']},",
                    "        ],",
                    "        'actions': [{'action_id': 'demo.edit_items', 'label': '编辑 Demo Items', 'kind': 'config_editor', 'editor_kind': 'demo.items'}],",
                    "        'warnings': [{'code': 'demo_items_warning', 'level': 'warning', 'message': 'Demo Items 需要确认', 'view_id': 'demo.items', 'field': 'items.enabled', 'path': '/views/demo.items/fields/items.enabled', 'config_path': ['items', 'enabled']}],",
                    "        'patch_schema': {'kind': 'config_patch', 'operations': [{'operation': 'append_item'}, {'operation': 'delete_item'}, {'operation': 'set_enabled'}, {'operation': 'move_item'}], 'fields': [{'key': 'operation'}, {'key': 'path'}, {'key': 'target_index'}, {'key': 'payload'}], 'sections': {'items': {'path': ['items'], 'model_key': 'demo_item'}}},",
                    "        'warning_schema': {'kind': 'config_warning', 'fields': [{'key': 'code'}, {'key': 'message'}, {'key': 'view_id'}, {'key': 'field'}, {'key': 'path'}]},",
                    "        'protocol_manifest': {'schema_version': 'demo.protocol_manifest.v1', 'interfaces': {'describe_config': True, 'apply_config_patch': True, 'preview_config_effect': True}, 'views': [{'view_id': 'demo.items', 'kind': 'structured_list'}], 'models': ['demo_item'], 'patch': {'sections': ['items']}, 'config_effect': {'provider': 'preview_config_effect'}},",
                    "    }",
                    "def preview_config_effect(params, context):",
                    "    return {'schema_version': 'demo.effect.v1', 'summary': {'items': len(params.get('items') or [])}, 'expected_output_fields': ['A', 'Demo'], 'side_effects': [{'kind': 'read_input_tables', 'label': '读取输入表'}]}",
                    "def validate_config_patch(params, context, patch):",
                    "    return True, ''",
                    "def apply_config_patch(params, context, patch):",
                    "    params = dict(params)",
                    "    items = [dict(item) for item in (params.get('items') or [{'name': 'alpha', 'enabled': True}, {'name': 'beta', 'enabled': False}])]",
                    "    op = patch.get('operation')",
                    "    if op == 'append_item':",
                    "        value = dict(patch.get('payload') or patch.get('value') or {})",
                    "        items.append(value or {'name': 'item_' + str(len(items) + 1), 'enabled': True})",
                    "    elif op == 'delete_item':",
                    "        items.pop(int(patch.get('target_index', patch.get('index'))))",
                    "    elif op == 'set_enabled':",
                    "        idx = int(patch.get('target_index', patch.get('index')))",
                    "        payload = patch.get('payload') if isinstance(patch.get('payload'), dict) else {}",
                    "        items[idx]['enabled'] = bool(payload.get('enabled', patch.get('enabled')))",
                    "    elif op == 'move_item':",
                    "        item = items.pop(int(patch.get('target_index', patch.get('index'))))",
                    "        items.insert(int(patch.get('to_index')), item)",
                    "    else:",
                    "        return {'ok': False, 'message': 'unsupported'}",
                    "    params['items'] = items",
                    "    params['last_patch'] = dict(patch)",
                    "    return {'ok': True, 'params': params, 'changed': True, 'message': 'patched'}",
                    "def run(input_data, params, context):",
                    "    return {'ok': True, 'output': input_data}",
                ]),
                encoding="utf-8",
            )
            (Path(temp_dir) / "bad_plugin.py").write_text("raise RuntimeError('broken scan')", encoding="utf-8")

            client = QtHeadlessEngineClient()
            client.engine.plugins = PluginService(plugins_dir=temp_dir, app_dir=temp_dir)
            catalog = client.list_node_ui_catalog(preview_headers=["A"])
            detail = client.describe_node_detail("plugin.demo", preview_headers=["A"])

            app = qt.QtWidgets.QApplication.instance() or qt.QtWidgets.QApplication([])
            window = build_main_window(qt, engine_client=client)
            controller = window.qt_workflow_controller
            controller.add_node_by_type("plugin.demo")

            plugin_node = controller.current_plan["nodes"][-1]
            controller.show_node_config(len(controller.current_plan["nodes"]) - 1)

            plugin_group = next(group for group in catalog["catalog"]["groups"] if group["group"] == "插件")
            plugin_item = next(item for item in plugin_group["items"] if item["node_type_id"] == "plugin.demo")

            self.assertEqual(plugin_item["display_name"], "插件 / Demo")
            self.assertTrue(plugin_item["supported_headless"])
            self.assertEqual(plugin_node["node_type_id"], "plugin.demo")
            self.assertEqual(plugin_node["config"]["plugin_id"], "demo")
            self.assertEqual(plugin_node["config"]["params"]["limit"], 3)
            self.assertIn("plugin_id", controller.config_form.config_fields)
            self.assertIn("params", controller.config_form.config_fields)
            self.assertIn("params.field", controller.config_form.config_fields)
            self.assertIn("params.limit", controller.config_form.config_fields)
            self.assertIn("params.mode", controller.config_form.config_fields)
            self.assertFalse(controller.legacy_plugin_config_button.isHidden())
            field_editor = controller.config_form.config_fields["params.field"]["editor"]
            field_choices = [field_editor.itemText(index) for index in range(field_editor.count())]
            self.assertEqual(field_editor.currentText(), "A")
            self.assertIn("source_file", field_choices)
            mode_editor = controller.config_form.config_fields["params.mode"]["editor"]
            mode_choices = [mode_editor.itemText(index) for index in range(mode_editor.count())]
            self.assertEqual(mode_choices, ["fast", "safe"])
            limit_editor = controller.config_form.config_fields["params.limit"]["editor"]
            self.assertEqual(limit_editor.text(), "3")
            limit_editor.setText("5")
            converted_node = controller.config_form.to_node()
            self.assertEqual(converted_node["config"]["params"]["field"], "A")
            self.assertEqual(converted_node["config"]["params"]["limit"], 5)
            self.assertNotIn("params.limit", converted_node["config"])
            self.assertEqual(controller.node_detail_title_label.text(), "插件 / Demo")
            self.assertIn("插件 ID：demo", controller.node_detail_sections.toPlainText())
            self.assertIn("旧版设置窗口", controller.node_detail_sections.toPlainText())
            self.assertIn("配置能力：schema配置、动态候选、配置描述、结构化patch、配置效果预览、旧版窗口fallback", controller.node_detail_sections.toPlainText())
            self.assertIn("配置协议", controller.node_detail_sections.toPlainText())
            self.assertIn("协议清单：demo.protocol_manifest.v1", controller.node_detail_sections.toPlainText())
            self.assertIn("接口 describe_config、apply_config_patch、preview_config_effect", controller.node_detail_sections.toPlainText())
            self.assertIn("模型 demo_item", controller.node_detail_sections.toPlainText())
            self.assertIn("效果预览 preview_config_effect", controller.node_detail_sections.toPlainText())
            self.assertIn("Patch协议：config_patch", controller.node_detail_sections.toPlainText())
            self.assertIn("操作 append_item、delete_item、set_enabled、move_item", controller.node_detail_sections.toPlainText())
            self.assertIn("字段 operation、path、target_index、payload", controller.node_detail_sections.toPlainText())
            self.assertIn("警告协议：config_warning", controller.node_detail_sections.toPlainText())
            self.assertIn("字段 code、message、view_id、field、path", controller.node_detail_sections.toPlainText())
            self.assertIn("Demo Items 需要确认（视图 demo.items；字段 items.enabled；路径 /views/demo.items/fields/items.enabled；配置 items.enabled；代码 demo_items_warning）", controller.node_detail_sections.toPlainText())
            self.assertIn("兼容动作：兼容旧版设置", controller.node_detail_sections.toPlainText())
            self.assertIn("兼容状态：生命周期 legacy_fallback", controller.node_detail_sections.toPlainText())
            self.assertIn("迁移目标 describe_config + parameter_metadata + config_patch", controller.node_detail_sections.toPlainText())
            self.assertIn("退场条件 插件已提供等价 schema/patch 配置能力且目标 UI 已完成承接", controller.node_detail_sections.toPlainText())
            self.assertIn("兼容提示：旧版 Tk 设置窗口仅作为兼容 fallback", controller.node_detail_sections.toPlainText())
            self.assertIn("参数元数据", controller.node_detail_sections.toPlainText())
            self.assertIn("参数能力：动态候选", controller.node_detail_sections.toPlainText())
            self.assertIn("参数布局：", controller.node_detail_sections.toPlainText())
            self.assertIn("参数UI提示：", controller.node_detail_sections.toPlainText())
            self.assertIn("兼容等级 A_SCHEMA_PATCH", controller.node_detail_sections.toPlainText())
            self.assertIn("可直接支持UI：Tk、Qt、.NET、Web、Electron", controller.node_detail_sections.toPlainText())
            self.assertIn("schema/patch", controller.legacy_plugin_config_button.toolTip())
            self.assertIn("模式：legacy_fallback", controller.legacy_plugin_config_button.toolTip())
            self.assertIn("生命周期：legacy_fallback", controller.legacy_plugin_config_button.toolTip())
            self.assertIn("兼容等级：A_SCHEMA_PATCH", controller.legacy_plugin_config_button.toolTip())
            self.assertIn("标准协议支持UI：Tk、Qt、.NET、Web、Electron", controller.legacy_plugin_config_button.toolTip())
            self.assertIn("建议位置：compatibility_menu", controller.legacy_plugin_config_button.toolTip())
            self.assertIn("显示优先级：low", controller.legacy_plugin_config_button.toolTip())
            self.assertIn("推荐主入口：否", controller.legacy_plugin_config_button.toolTip())
            self.assertIn("打开前建议提示兼容风险", controller.legacy_plugin_config_button.toolTip())
            self.assertIn("迁移目标：describe_config + parameter_metadata + config_patch", controller.legacy_plugin_config_button.toolTip())
            self.assertIn("来源：plugin_config_description.actions", controller.legacy_plugin_config_button.toolTip())
            self.assertIn("配置动作：编辑 Demo Items", controller.node_detail_sections.toPlainText())
            self.assertFalse(controller.plugin_config_view_tabs.isHidden())
            self.assertLess(controller.plugin_config_view_tabs.minimumHeight(), 170)
            self.assertEqual(
                controller.plugin_config_view_tabs.sizePolicy().verticalPolicy(),
                qt.QtWidgets.QSizePolicy.Policy.Ignored,
            )
            protocol_tab_titles = [
                controller.plugin_config_view_tabs.tabText(index)
                for index in range(controller.plugin_config_view_tabs.count())
            ]
            self.assertIn("Demo Overview", protocol_tab_titles)
            self.assertIn("Demo Details", protocol_tab_titles)
            self.assertIn("Demo Preview", protocol_tab_titles)
            self.assertIn("Demo Items", protocol_tab_titles)
            self.assertIn("参数元数据", protocol_tab_titles)
            self.assertIn("配置效果", protocol_tab_titles)
            metadata_page = controller.plugin_config_view_tabs.widget(protocol_tab_titles.index("参数元数据"))
            metadata_table = metadata_page if isinstance(metadata_page, qt.QtWidgets.QTableWidget) else metadata_page.findChild(qt.QtWidgets.QTableWidget)
            self.assertIsNotNone(metadata_table)
            self.assertEqual(metadata_table.item(2, 0).text(), "field_count")
            self.assertEqual(metadata_table.item(2, 1).text(), "3")
            items_tab_index = protocol_tab_titles.index("Demo Items")
            self.assertIn("Demo Items 需要确认", controller.plugin_config_view_tabs.tabToolTip(items_tab_index))
            self.assertIn("字段 items.enabled", controller.plugin_config_view_tabs.tabToolTip(items_tab_index))
            details_page = controller.plugin_config_view_tabs.widget(protocol_tab_titles.index("Demo Details"))
            details_table = details_page if isinstance(details_page, qt.QtWidgets.QTableWidget) else details_page.findChild(qt.QtWidgets.QTableWidget)
            self.assertIsNotNone(details_table)
            self.assertEqual(details_table.item(0, 0).text(), "基本")
            self.assertEqual(details_table.item(0, 1).text(), "模式")
            self.assertEqual(details_table.item(0, 2).text(), "fast")
            preview_page = controller.plugin_config_view_tabs.widget(protocol_tab_titles.index("Demo Preview"))
            preview_editor = preview_page if isinstance(preview_page, qt.QtWidgets.QPlainTextEdit) else preview_page.findChild(qt.QtWidgets.QPlainTextEdit)
            self.assertIsNotNone(preview_editor)
            self.assertEqual(preview_editor.toPlainText(), "mode=fast")
            effect_page = controller.plugin_config_view_tabs.widget(protocol_tab_titles.index("配置效果"))
            effect_table = effect_page if isinstance(effect_page, qt.QtWidgets.QTableWidget) else effect_page.findChild(qt.QtWidgets.QTableWidget)
            self.assertIsNotNone(effect_table)
            self.assertEqual(effect_table.item(0, 0).text(), "items")
            effect_rows = {
                effect_table.item(row, 0).text(): effect_table.item(row, 1).text()
                for row in range(effect_table.rowCount())
                if effect_table.item(row, 0) is not None and effect_table.item(row, 1) is not None
            }
            self.assertIn("配置效果预览：", effect_rows["状态"])
            items_page = controller.plugin_config_view_tabs.widget(items_tab_index)
            items_table = items_page.findChild(qt.QtWidgets.QTableWidget)
            self.assertIsNotNone(items_table)
            self.assertEqual(items_table.rowCount(), 2)
            self.assertEqual(items_table.horizontalHeaderItem(0).text(), "名称")
            self.assertEqual(items_table.item(0, 0).text(), "alpha")
            self.assertEqual(items_table.item(1, 1).text(), "否")
            items_page.plugin_config_buttons["append_item"].click()
            app.processEvents()

            def current_items_table():
                titles = [
                    controller.plugin_config_view_tabs.tabText(index)
                    for index in range(controller.plugin_config_view_tabs.count())
                ]
                page = controller.plugin_config_view_tabs.widget(titles.index("Demo Items"))
                return page, page.findChild(qt.QtWidgets.QTableWidget)

            items_page, items_table = current_items_table()
            self.assertEqual(items_table.rowCount(), 3)
            self.assertEqual(controller.current_plan["nodes"][-1]["config"]["params"]["items"][-1]["name"], "from_view")
            append_patch = controller.current_plan["nodes"][-1]["config"]["params"]["last_patch"]
            self.assertEqual(append_patch["schema_version"], "demo.config.v1")
            self.assertEqual(append_patch["view_id"], "demo.items")
            self.assertEqual(append_patch["editor_kind"], "demo.items")
            self.assertEqual(append_patch["action_id"], "demo.edit_items")
            self.assertEqual(append_patch["path"], ["items"])
            self.assertEqual(append_patch["payload"], {"name": "from_view", "enabled": True})
            self.assertEqual(append_patch["value"], {"name": "from_view", "enabled": True})
            items_table.selectRow(0)
            items_page.plugin_config_buttons["set_enabled"].click()
            app.processEvents()
            items_page, items_table = current_items_table()
            self.assertEqual(items_table.item(0, 1).text(), "否")
            enabled_patch = controller.current_plan["nodes"][-1]["config"]["params"]["last_patch"]
            self.assertEqual(enabled_patch["target_index"], 0)
            self.assertEqual(enabled_patch["payload"], {"enabled": False})
            items_table.selectRow(0)
            items_page.plugin_config_buttons["move_item_1"].click()
            app.processEvents()
            items_page, items_table = current_items_table()
            self.assertEqual(items_table.item(0, 0).text(), "beta")
            items_table.selectRow(2)
            items_page.plugin_config_buttons["delete_item"].click()
            app.processEvents()
            _items_page, items_table = current_items_table()
            self.assertEqual(items_table.rowCount(), 2)
            self.assertIn("Demo plugin", detail["detail"]["description"])
            with patch("ui_qt.main_window.QtWorkflowMainWindow._confirm_prompt", return_value=True) as mock_confirm:
                controller.open_legacy_plugin_config()
            self.assertTrue(mock_confirm.called)
            prompt = mock_confirm.call_args.args[0]["prompt"]
            self.assertEqual(prompt["code"], "confirm_legacy_plugin_config")
            self.assertIn("兼容 fallback", prompt["message"])
            self.assertEqual(controller.current_plan["nodes"][-1]["config"]["params"]["limit"], 11)
            self.assertIn("旧版插件设置已写回当前节点配置", controller.info_text.toPlainText())
            controller.refresh_plugins()
            self.assertIn("已注册插件：1 个", controller.info_text.toPlainText())
            self.assertIn("bad_plugin.py", controller.issue_text.toPlainText())
            self.assertEqual(controller.message_tabs.tabText(controller.message_tabs.currentIndex()), "问题")
            window.close()
            app.processEvents()

    def test_plugin_structured_list_uses_item_schema_display_columns(self):
        try:
            qt = qt_app.load_qt6()
        except QtBindingUnavailable as exc:
            self.skipTest(str(exc))
        app = qt.QtWidgets.QApplication.instance() or qt.QtWidgets.QApplication([])
        window = build_main_window(qt)
        controller = window.qt_workflow_controller

        widget = controller._make_plugin_structured_list_widget(
            {
                "view_id": "demo.items",
                "kind": "structured_list",
                "config_path": ["items"],
                "items": [{"name": "alpha", "enabled": True}],
                "item_model_key": "demo_default",
                "item_schema": {
                    "display_columns": [
                        {"key": "name", "label": "名称"},
                        {"key": "enabled", "label": "启用"},
                    ],
                    "columns": [
                        {"key": "name", "label": "名称", "type": "text"},
                        {"key": "enabled", "label": "启用", "type": "bool"},
                    ],
                },
            },
            {
                "config_schema_version": "demo.config.v1",
                "models": {"demo_default": {"name": "new_item", "enabled": True}},
            },
        )

        table = widget.findChild(qt.QtWidgets.QTableWidget)
        self.assertIsNotNone(table)
        self.assertEqual(table.horizontalHeaderItem(0).text(), "名称")
        self.assertEqual(table.horizontalHeaderItem(1).text(), "启用")
        self.assertEqual(table.item(0, 0).text(), "alpha")
        self.assertEqual(table.item(0, 1).text(), "是")
        self.assertEqual(widget.plugin_config_schema_version, "demo.config.v1")
        self.assertEqual(widget.plugin_config_append_value, {"name": "new_item", "enabled": True})
        window.close()
        app.processEvents()

    def test_plugin_structured_list_reads_nested_item_schema_values(self):
        try:
            qt = qt_app.load_qt6()
        except QtBindingUnavailable as exc:
            self.skipTest(str(exc))
        app = qt.QtWidgets.QApplication.instance() or qt.QtWidgets.QApplication([])
        window = build_main_window(qt)
        controller = window.qt_workflow_controller

        widget = controller._make_plugin_structured_list_widget(
            {
                "view_id": "demo.rules",
                "kind": "structured_list",
                "items": [{"name": "rule_1", "mapping": {"content_field": "write_value"}}],
                "item_schema": {
                    "columns": [
                        {"key": "name", "label": "规则", "type": "text"},
                        {
                            "key": "mapping.content_field",
                            "label": "写入字段",
                            "type": "select",
                            "config_path": ["mapping", "content_field"],
                        },
                    ],
                },
            },
            {"config_schema_version": "demo.config.v1"},
        )

        table = widget.findChild(qt.QtWidgets.QTableWidget)
        self.assertIsNotNone(table)
        self.assertEqual(table.horizontalHeaderItem(1).text(), "写入字段")
        self.assertEqual(table.item(0, 1).text(), "write_value")
        window.close()
        app.processEvents()

    def test_plugin_structured_list_buttons_follow_action_state(self):
        try:
            qt = qt_app.load_qt6()
        except QtBindingUnavailable as exc:
            self.skipTest(str(exc))
        app = qt.QtWidgets.QApplication.instance() or qt.QtWidgets.QApplication([])
        window = build_main_window(qt)
        controller = window.qt_workflow_controller

        widget = controller._make_plugin_structured_list_widget(
            {
                "view_id": "demo.items",
                "kind": "structured_list",
                "config_path": ["items"],
                "patch_operations": ["append_item", "update_item", "delete_item", "move_item"],
                "items": [
                    {"name": "alpha", "enabled": True},
                    {"name": "beta", "enabled": True},
                ],
                "columns": [
                    {"key": "name", "label": "名称"},
                    {"key": "enabled", "label": "启用"},
                ],
                "action_state": {
                    "schema_version": "plugin_config_action_state.v1",
                    "buttons": {
                        "append_item": {"label": "新增", "operation": "append_item", "visible": True, "enabled": True},
                        "update_item": {"label": "应用修改", "operation": "update_item", "visible": True, "enabled": True, "requires_selection": True},
                        "delete_item": {"label": "删除", "operation": "delete_item", "visible": True, "enabled": True, "requires_selection": True},
                        "set_enabled": {"label": "启停", "operation": "set_enabled", "visible": False, "enabled": False},
                        "move_item_-1": {"label": "上移", "operation": "move_item", "target_offset": -1, "visible": True, "enabled": False, "requires_selection": True},
                        "move_item_1": {"label": "下移", "operation": "move_item", "target_offset": 1, "visible": True, "enabled": True, "requires_selection": True},
                    },
                },
            },
            {"config_schema_version": "demo.config.v1"},
        )

        table = widget.findChild(qt.QtWidgets.QTableWidget)
        self.assertIsNotNone(table)
        self.assertFalse(widget.plugin_config_buttons["move_item_-1"].isEnabled())
        self.assertTrue(widget.plugin_config_buttons["move_item_1"].isEnabled())
        self.assertFalse(widget.plugin_config_buttons["set_enabled"].isVisible())
        table.selectRow(1)
        app.processEvents()
        self.assertTrue(widget.plugin_config_buttons["move_item_-1"].isEnabled())
        self.assertFalse(widget.plugin_config_buttons["move_item_1"].isEnabled())
        window.close()
        app.processEvents()

    def test_plugin_config_patch_status_uses_patch_result(self):
        try:
            qt = qt_app.load_qt6()
        except QtBindingUnavailable as exc:
            self.skipTest(str(exc))
        app = qt.QtWidgets.QApplication.instance() or qt.QtWidgets.QApplication([])
        window = build_main_window(qt)
        controller = window.qt_workflow_controller
        captured = []

        def apply_patch(plugin_id, *, patch=None, config=None, input_table=None, context=None):
            captured.append({
                "plugin_id": plugin_id,
                "patch": copy.deepcopy(patch or {}),
                "config": copy.deepcopy(config or {}),
            })
            return {
                "ok": True,
                "message": "旧消息",
                "patch_result": {
                    "schema_version": "plugin_config_patch_result.v1",
                    "status_message": "协议状态消息",
                },
                "config": {"plugin_id": "demo", "params": {"mode": "new"}},
            }

        controller.engine_client.apply_plugin_config_patch = apply_patch
        controller.current_plan = {
            "plan_name": "demo",
            "nodes": [{
                "node_type_id": "plugin.demo",
                "config": {"plugin_id": "demo", "params": {"mode": "old"}},
            }],
        }
        controller.node_list.clear()
        controller.node_list.addItem("插件 / Demo")
        controller.node_list.setCurrentRow(0)
        controller.config_form.to_node = lambda: copy.deepcopy(controller.current_plan["nodes"][0])
        controller.refresh_node_list = lambda: None
        controller.show_node_config = lambda index: None

        controller._apply_plugin_config_patch({"operation": "set_param", "key": "mode", "value": "new"})

        self.assertEqual(captured[0]["plugin_id"], "demo")
        self.assertEqual(controller.current_plan["nodes"][0]["config"]["params"]["mode"], "new")
        self.assertEqual(controller.status_bar.currentMessage(), "协议状态消息")
        window.close()
        app.processEvents()

    def test_plugin_config_patch_target_focuses_protocol_view_item(self):
        try:
            qt = qt_app.load_qt6()
        except QtBindingUnavailable as exc:
            self.skipTest(str(exc))
        app = qt.QtWidgets.QApplication.instance() or qt.QtWidgets.QApplication([])
        window = build_main_window(qt)
        controller = window.qt_workflow_controller

        controller._render_plugin_config_views({
            "ok": True,
            "views": [
                {
                    "view_id": "demo.summary",
                    "kind": "summary",
                    "title": "概览",
                    "summary": {"状态": "ok"},
                },
                {
                    "view_id": "demo.rules",
                    "kind": "structured_list",
                    "title": "规则",
                    "section": "rules",
                    "patch_target": {"target_id_fields": ["id"]},
                    "items": [
                        {"id": "rule_1", "name": "第一条"},
                        {"id": "rule_2", "name": "第二条"},
                    ],
                    "columns": [
                        {"key": "name", "label": "名称"},
                    ],
                },
            ],
        })

        focused = controller._focus_plugin_config_target({
            "schema_version": "plugin_config_patch_target.v1",
            "view_id": "demo.rules",
            "target_id": "rule_2",
            "can_focus_view": True,
            "can_focus_item": True,
        })

        self.assertTrue(focused)
        self.assertEqual(controller.node_tabs.currentIndex(), 1)
        self.assertEqual(controller.plugin_config_view_tabs.currentIndex(), 1)
        table = controller.plugin_config_view_tabs.currentWidget().plugin_config_table
        self.assertEqual(table.currentRow(), 1)
        window.close()
        app.processEvents()

    def test_plugin_config_views_use_protocol_layout_and_ui_hints(self):
        try:
            qt = qt_app.load_qt6()
        except QtBindingUnavailable as exc:
            self.skipTest(str(exc))
        app = qt.QtWidgets.QApplication.instance() or qt.QtWidgets.QApplication([])
        window = build_main_window(qt)
        controller = window.qt_workflow_controller

        described = {
            "ok": True,
            "layout": {
                "schema_version": "DataFlowKit.visual_mapping.layout.v1",
                "default_view_id": "demo.rules",
                "view_order": ["demo.overview", "demo.rules", "demo.advanced"],
                "primary_views": ["demo.overview", "demo.rules"],
                "advanced_views": ["demo.advanced"],
                "preferred_navigation": "tabs",
            },
            "ui_hints": {
                "schema_version": "DataFlowKit.visual_mapping.ui_hints.v1",
                "navigation": "tabs",
                "density": "compact",
                "display_mode": "workflow_panel",
                "view_hints": {
                    "demo.rules": {
                        "title": "协议规则",
                        "description": "按协议默认打开规则。",
                        "empty_text": "暂无规则。",
                        "primary_action": "demo.edit.rules",
                        "role": "primary_editor",
                    },
                    "demo.advanced": {
                        "description": "高级设置。",
                    },
                },
            },
            "views": [
                {"view_id": "demo.advanced", "kind": "summary", "title": "高级", "summary": {"状态": "advanced"}},
                {
                    "view_id": "demo.rules",
                    "kind": "structured_list",
                    "title": "规则",
                    "items": [{"id": "rule_1", "name": "第一条"}],
                    "columns": [{"key": "name", "label": "名称"}],
                },
                {"view_id": "demo.overview", "kind": "summary", "title": "概览", "summary": {"状态": "ok"}},
            ],
        }

        controller._render_plugin_config_views(described)
        titles = [
            controller.plugin_config_view_tabs.tabText(index)
            for index in range(controller.plugin_config_view_tabs.count())
        ]

        self.assertEqual(titles, ["概览", "协议规则", "高级"])
        self.assertEqual(controller.plugin_config_view_tabs.currentIndex(), 1)
        tooltip = controller.plugin_config_view_tabs.tabToolTip(1)
        self.assertIn("按协议默认打开规则", tooltip)
        self.assertIn("空状态：暂无规则。", tooltip)
        self.assertIn("主动作：demo.edit.rules", tooltip)

        controller._append_plugin_config_detail(described)
        detail_text = controller.node_detail_sections.toPlainText()
        self.assertIn("插件配置布局：默认视图 demo.rules", detail_text)
        self.assertIn("插件UI提示：导航 tabs", detail_text)
        window.close()
        app.processEvents()

    def test_plugin_parameter_form_consumes_config_ui_hints(self):
        try:
            qt = qt_app.load_qt6()
        except QtBindingUnavailable as exc:
            self.skipTest(str(exc))
        app = qt.QtWidgets.QApplication.instance() or qt.QtWidgets.QApplication([])
        window = build_main_window(qt)
        controller = window.qt_workflow_controller

        schema = {
            "node_type_id": "plugin.demo",
            "display_name": "插件 / Demo",
            "form": {
                "groups": [{
                    "title": "插件参数",
                    "fields": [
                        {"key": "params.path", "label": "路径字段", "type": "field_select", "config_path": ["params", "path"]},
                        {"key": "params.limit", "label": "数量", "type": "number", "config_path": ["params", "limit"]},
                    ],
                }],
            },
        }
        described = {
            "ok": True,
            "ui_hints": {
                "schema_version": "plugin_config_ui_hints.v1",
                "parameter_field_hints": {
                    "schema_version": "plugin_parameter_ui_hints.v1",
                    "fields": [
                        {
                            "field_key": "params.path",
                            "placeholder": "选择路径字段",
                            "warning": "路径字段为空时无法读取文件。",
                            "empty_text": "当前输入表没有可选字段",
                            "invalid_value_text": "字段不在当前输入表中",
                            "advanced": True,
                        },
                        {
                            "field_key": "params.limit",
                            "min": 0,
                            "step": 1,
                            "unit": "行",
                        },
                    ],
                },
            },
        }

        merged = controller._schema_with_plugin_config_hints(schema, described)
        fields = {
            field["key"]: field
            for group in merged["form"]["groups"]
            for field in group["fields"]
        }
        self.assertTrue(fields["params.path"]["advanced"])
        self.assertEqual(fields["params.path"]["placeholder"], "选择路径字段")
        self.assertEqual(fields["params.path"]["protocol_hints"]["plugin_config_ui_hints"]["field_key"], "params.path")
        self.assertEqual(fields["params.limit"]["unit"], "行")

        controller.config_form.set_node(
            {"node_type_id": "plugin.demo", "config": {"params": {"path": "", "limit": 3}}},
            headers=[],
            schema=merged,
        )
        path_tooltip = controller.config_form.config_fields["params.path"]["editor"].toolTip()
        limit_tooltip = controller.config_form.config_fields["params.limit"]["editor"].toolTip()
        self.assertIn("路径字段为空时无法读取文件", path_tooltip)
        self.assertIn("占位提示：选择路径字段", path_tooltip)
        self.assertIn("无候选时提示：当前输入表没有可选字段", path_tooltip)
        self.assertIn("高级参数", path_tooltip)
        self.assertIn("单位：行", limit_tooltip)
        window.close()
        app.processEvents()

    def test_plugin_warning_target_link_focuses_protocol_view(self):
        try:
            qt = qt_app.load_qt6()
        except QtBindingUnavailable as exc:
            self.skipTest(str(exc))
        app = qt.QtWidgets.QApplication.instance() or qt.QtWidgets.QApplication([])
        window = build_main_window(qt)
        controller = window.qt_workflow_controller

        controller._render_plugin_config_views({
            "ok": True,
            "views": [
                {"view_id": "demo.summary", "kind": "summary", "title": "概览", "summary": {"状态": "ok"}},
                {
                    "view_id": "demo.items",
                    "kind": "structured_list",
                    "title": "条目",
                    "items": [{"id": "item_1", "name": "第一条"}],
                    "columns": [{"key": "name", "label": "名称"}],
                },
            ],
        })
        controller._append_plugin_warning_target_links([
            {
                "code": "demo_warning",
                "message": "需要检查条目",
                "target": {
                    "schema_version": "plugin_config_warning_target.v1",
                    "view_id": "demo.items",
                    "field": "items.enabled",
                    "focus_path": "/views/demo.items/fields/items.enabled",
                    "can_focus_view": True,
                },
            },
        ])

        self.assertIn("配置警告定位", controller.node_detail_sections.toPlainText())
        self.assertIn("定位", controller.node_detail_sections.toPlainText())
        controller.node_tabs.setCurrentIndex(0)
        controller.plugin_config_view_tabs.setCurrentIndex(0)
        controller._handle_node_detail_link(qt.QtCore.QUrl("dfk-plugin-warning:plugin_warning_0"))

        self.assertEqual(controller.node_tabs.currentIndex(), 1)
        self.assertEqual(controller.plugin_config_view_tabs.currentIndex(), 1)
        self.assertEqual(controller.status_bar.currentMessage(), "已定位到插件配置警告。")
        window.close()
        app.processEvents()

    def test_plugin_warning_formatter_uses_target_payload(self):
        try:
            qt = qt_app.load_qt6()
        except QtBindingUnavailable as exc:
            self.skipTest(str(exc))
        app = qt.QtWidgets.QApplication.instance() or qt.QtWidgets.QApplication([])
        window = build_main_window(qt)
        controller = window.qt_workflow_controller

        line = controller._format_plugin_warning_item({
            "code": "demo_warning",
            "message": "需要检查配置",
            "target": {
                "schema_version": "plugin_config_warning_target.v1",
                "view_id": "demo.items",
                "field": "items.enabled",
                "focus_path": "/views/demo.items/fields/items.enabled",
                "config_path": ["items", "enabled"],
            },
        })

        self.assertIn("需要检查配置", line)
        self.assertIn("视图 demo.items", line)
        self.assertIn("字段 items.enabled", line)
        self.assertIn("路径 /views/demo.items/fields/items.enabled", line)
        self.assertIn("配置 items.enabled", line)
        window.close()
        app.processEvents()

    def test_plugin_structured_list_edits_item_schema_columns_as_update_patch(self):
        try:
            qt = qt_app.load_qt6()
        except QtBindingUnavailable as exc:
            self.skipTest(str(exc))
        app = qt.QtWidgets.QApplication.instance() or qt.QtWidgets.QApplication([])
        window = build_main_window(qt)
        controller = window.qt_workflow_controller
        captured = []
        controller._apply_plugin_config_patch = lambda patch: captured.append(copy.deepcopy(patch))

        widget = controller._make_plugin_structured_list_widget(
            {
                "view_id": "demo.rules",
                "kind": "structured_list",
                "editor_kind": "demo.rules",
                "config_path": ["items"],
                "section": "items",
                "patch_target": {"target_id_fields": ["id", "name"]},
                "patch_operations": ["update_item"],
                "items": [{
                    "id": "rule_1",
                    "name": "rule",
                    "enabled": True,
                    "mapping": {"content_field": "old", "empty_policy": "keep"},
                    "source_locator": {"row_index": 1, "col_index": 2},
                }],
                "item_schema": {
                    "columns": [
                        {"key": "name", "label": "规则", "type": "text"},
                        {
                            "key": "mapping.content_field",
                            "label": "写入字段",
                            "type": "select",
                            "choices": ["old", "new"],
                            "config_path": ["mapping", "content_field"],
                        },
                        {
                            "key": "source_locator.row_index",
                            "label": "行",
                            "type": "number",
                            "config_path": ["source_locator", "row_index"],
                        },
                        {"key": "enabled", "label": "启用", "type": "bool"},
                    ],
                },
            },
            {
                "config_schema_version": "demo.config.v1",
                "protocol_family": "plugin_complex_config",
                "plugin_id": "demo.plugin",
                "config_key": "main",
                "actions": [{"action_id": "demo.edit_rules", "editor_kind": "demo.rules"}],
            },
        )

        table = widget.findChild(qt.QtWidgets.QTableWidget)
        self.assertIsNotNone(table)
        self.assertEqual(table.horizontalHeaderItem(1).text(), "写入字段")
        table.selectRow(0)
        table.cellWidget(0, 0).setText("renamed")
        table.cellWidget(0, 1).setCurrentText("new")
        table.cellWidget(0, 2).setText("7")
        table.cellWidget(0, 3).setChecked(False)
        widget.plugin_config_buttons["update_item"].click()

        self.assertEqual(len(captured), 1)
        patch = captured[0]
        self.assertEqual(patch["schema_version"], "demo.config.v1")
        self.assertEqual(patch["protocol_family"], "plugin_complex_config")
        self.assertEqual(patch["plugin_id"], "demo.plugin")
        self.assertEqual(patch["config_key"], "main")
        self.assertEqual(patch["config_name"], "main")
        self.assertEqual(patch["view_id"], "demo.rules")
        self.assertEqual(patch["editor_kind"], "demo.rules")
        self.assertEqual(patch["action_id"], "demo.edit_rules")
        self.assertEqual(patch["section"], "items")
        self.assertEqual(patch["operation"], "update_item")
        self.assertEqual(patch["path"], ["items"])
        self.assertEqual(patch["target_index"], 0)
        self.assertEqual(patch["index"], 0)
        self.assertEqual(patch["target_id"], "rule_1")
        self.assertEqual(patch["payload"]["id"], "rule_1")
        self.assertEqual(patch["payload"]["name"], "renamed")
        self.assertFalse(patch["payload"]["enabled"])
        self.assertEqual(patch["payload"]["mapping"]["content_field"], "new")
        self.assertEqual(patch["payload"]["mapping"]["empty_policy"], "keep")
        self.assertEqual(patch["payload"]["source_locator"]["row_index"], 7)
        self.assertEqual(patch["payload"]["source_locator"]["col_index"], 2)
        self.assertEqual(patch["value"], patch["payload"])
        window.close()
        app.processEvents()

    def test_plugin_structured_list_select_uses_plugin_config_options(self):
        try:
            qt = qt_app.load_qt6()
        except QtBindingUnavailable as exc:
            self.skipTest(str(exc))
        app = qt.QtWidgets.QApplication.instance() or qt.QtWidgets.QApplication([])
        window = build_main_window(qt)
        controller = window.qt_workflow_controller
        calls = []

        def resolve_options(plugin_id, **kwargs):
            calls.append({"plugin_id": plugin_id, **copy.deepcopy(kwargs)})
            return {
                "ok": True,
                "schema_version": "DataFlowKit.plugin_config_options.v1",
                "source": "content_fields",
                "choices": ["from_protocol", "other"],
            }

        controller.engine_client.resolve_plugin_config_options = resolve_options
        controller.current_headers = ["source_file", "A"]
        controller.current_rows = [["demo.xlsx", "1"]]
        controller.set_current_input_db_path("input.sqlite", refresh=False)
        controller.output_db_path_edit.setText("output.sqlite")

        widget = controller._make_plugin_structured_list_widget(
            {
                "view_id": "visual_mapping.rules",
                "kind": "structured_list",
                "editor_kind": "visual_mapping.rules",
                "section": "rules",
                "config_path": ["plugin_settings", "configs", "default", "rules"],
                "patch_operations": ["update_item"],
                "items": [{"mapping": {"content_field": "old"}}],
                "item_schema": {
                    "columns": [
                        {
                            "key": "mapping.content_field",
                            "label": "写入字段",
                            "type": "select",
                            "config_path": ["mapping", "content_field"],
                            "choices": ["old_static"],
                            "options_source": {
                                "type": "visual_mapping_context",
                                "key": "content_fields",
                            },
                        },
                    ],
                },
            },
            {
                "config_schema_version": "DataFlowKit.visual_mapping.config.v1",
                "protocol_family": "plugin_complex_config",
                "plugin_id": "visual_mapping_write_plan_v1",
                "config_key": "default",
                "config": {
                    "plugin_id": "visual_mapping_write_plan_v1",
                    "params": {"config_name": "default"},
                },
            },
        )

        table = widget.findChild(qt.QtWidgets.QTableWidget)
        self.assertIsNotNone(table)
        editor = table.cellWidget(0, 0)
        self.assertIsInstance(editor, qt.QtWidgets.QComboBox)
        choices = [editor.itemText(index) for index in range(editor.count())]
        self.assertEqual(choices, ["old", "from_protocol", "other"])
        self.assertEqual(editor.currentText(), "old")

        self.assertEqual(len(calls), 1)
        call = calls[0]
        self.assertEqual(call["plugin_id"], "visual_mapping_write_plan_v1")
        self.assertEqual(call["field_key"], "mapping.content_field")
        self.assertEqual(call["view_id"], "visual_mapping.rules")
        self.assertEqual(call["section"], "rules")
        self.assertEqual(call["current_values"]["mapping"]["content_field"], "old")
        self.assertEqual(call["config"]["params"]["config_name"], "default")
        self.assertEqual(call["input_table"]["headers"], ["source_file", "A"])
        self.assertEqual(call["context"]["db_path"], "input.sqlite")
        self.assertEqual(call["context"]["input_db_path"], "input.sqlite")
        self.assertEqual(call["context"]["output_db_path"], "output.sqlite")
        window.close()
        app.processEvents()

    def test_plugin_structured_detail_form_select_uses_plugin_config_options(self):
        try:
            qt = qt_app.load_qt6()
        except QtBindingUnavailable as exc:
            self.skipTest(str(exc))
        app = qt.QtWidgets.QApplication.instance() or qt.QtWidgets.QApplication([])
        window = build_main_window(qt)
        controller = window.qt_workflow_controller
        calls = []

        def resolve_options(plugin_id, **kwargs):
            calls.append({"plugin_id": plugin_id, **copy.deepcopy(kwargs)})
            return {
                "ok": True,
                "schema_version": "DataFlowKit.plugin_config_options.v1",
                "source": "anchor_modes",
                "choices": ["protocol_mode", "fallback_mode"],
            }

        controller.engine_client.resolve_plugin_config_options = resolve_options
        widget = controller._make_plugin_structured_list_widget(
            {
                "view_id": "demo.rules",
                "kind": "structured_list",
                "section": "rules",
                "patch_operations": ["update_item"],
                "items": [{
                    "name": "rule",
                    "anchor": {"anchor_mode": "old"},
                }],
                "item_schema": {
                    "columns": [
                        {"key": "name", "label": "规则", "type": "text"},
                    ],
                    "detail_sections": [
                        {
                            "key": "anchor",
                            "title": "锚点定位",
                            "kind": "form",
                            "config_path": ["anchor"],
                            "fields": [
                                {
                                    "key": "anchor_mode",
                                    "label": "锚点模式",
                                    "type": "select",
                                    "config_path": ["anchor_mode"],
                                    "choices": ["static_mode"],
                                    "options_source": {
                                        "type": "plugin_config_context",
                                        "key": "anchor_modes",
                                    },
                                },
                            ],
                        },
                    ],
                },
            },
            {
                "config_schema_version": "demo.config.v1",
                "protocol_family": "plugin_complex_config",
                "plugin_id": "demo.plugin",
                "config": {"plugin_id": "demo.plugin", "params": {"mode": "demo"}},
            },
        )

        detail_tabs = widget.findChild(qt.QtWidgets.QTabWidget, "pluginConfigDetailTabs")
        self.assertIsNotNone(detail_tabs)
        anchor_page = detail_tabs.widget(0)
        anchor_fields = {
            ".".join(column["config_path"]): editor
            for column, editor in anchor_page.plugin_detail_form_fields
        }
        editor = anchor_fields["anchor.anchor_mode"]
        self.assertIsInstance(editor, qt.QtWidgets.QComboBox)
        choices = [editor.itemText(index) for index in range(editor.count())]
        self.assertEqual(choices, ["old", "protocol_mode", "fallback_mode"])
        self.assertEqual(editor.currentText(), "old")

        self.assertEqual(len(calls), 1)
        call = calls[0]
        self.assertEqual(call["plugin_id"], "demo.plugin")
        self.assertEqual(call["field_key"], "anchor_mode")
        self.assertEqual(call["view_id"], "demo.rules")
        self.assertEqual(call["section"], "rules")
        self.assertEqual(call["current_values"]["anchor"]["anchor_mode"], "old")
        window.close()
        app.processEvents()

    def test_plugin_structured_list_renders_detail_sections_as_update_patch(self):
        try:
            qt = qt_app.load_qt6()
        except QtBindingUnavailable as exc:
            self.skipTest(str(exc))
        app = qt.QtWidgets.QApplication.instance() or qt.QtWidgets.QApplication([])
        window = build_main_window(qt)
        controller = window.qt_workflow_controller
        captured = []
        controller._apply_plugin_config_patch = lambda patch: captured.append(copy.deepcopy(patch))

        widget = controller._make_plugin_structured_list_widget(
            {
                "view_id": "demo.rules",
                "kind": "structured_list",
                "config_path": ["rules"],
                "patch_operations": ["update_item"],
                "items": [{
                    "id": "rule_1",
                    "name": "rule",
                    "anchor": {"enabled": True, "row_offset": 0},
                    "conditions": [
                        {"mode": "包含", "value": "old", "meta": "keep_1"},
                        {"mode": "包含", "value": "second", "meta": "keep_2"},
                    ],
                }],
                "item_schema": {
                    "columns": [
                        {"key": "name", "label": "规则", "type": "text"},
                    ],
                    "detail_sections": [
                        {
                            "key": "anchor",
                            "title": "锚点定位",
                            "kind": "form",
                            "config_path": ["anchor"],
                            "fields": [
                                {"key": "enabled", "label": "启用", "type": "bool"},
                                {"key": "row_offset", "label": "行偏移", "type": "number"},
                            ],
                        },
                        {
                            "key": "conditions",
                            "title": "内容条件",
                            "kind": "structured_list",
                            "config_path": ["conditions"],
                            "item_default": {"mode": "包含", "value": ""},
                            "item_schema": {
                                "columns": [
                                    {
                                        "key": "mode",
                                        "label": "方式",
                                        "type": "select",
                                        "choices": ["包含", "等于"],
                                        "allow_custom": False,
                                    },
                                    {"key": "value", "label": "值", "type": "text"},
                                ],
                            },
                        },
                    ],
                },
            },
            {"config_schema_version": "demo.config.v1"},
        )

        table = widget.findChild(qt.QtWidgets.QTableWidget)
        self.assertIsNotNone(table)
        table.selectRow(0)
        detail_tabs = widget.findChild(qt.QtWidgets.QTabWidget, "pluginConfigDetailTabs")
        self.assertIsNotNone(detail_tabs)
        self.assertEqual(
            [detail_tabs.tabText(index) for index in range(detail_tabs.count())],
            ["锚点定位", "内容条件"],
        )

        anchor_page = detail_tabs.widget(0)
        anchor_fields = {
            ".".join(column["config_path"]): editor
            for column, editor in anchor_page.plugin_detail_form_fields
        }
        anchor_fields["anchor.enabled"].setChecked(False)
        anchor_fields["anchor.row_offset"].setText("2")

        conditions_page = detail_tabs.widget(1)
        conditions_table = conditions_page.plugin_detail_table
        self.assertEqual(conditions_table.rowCount(), 2)
        conditions_table.selectRow(0)
        conditions_page.plugin_detail_buttons["delete_item"].click()
        self.assertEqual(conditions_table.rowCount(), 1)
        conditions_table.cellWidget(0, 1).setText("remaining")
        conditions_page.plugin_detail_buttons["append_item"].click()
        new_row = conditions_table.rowCount() - 1
        conditions_table.cellWidget(new_row, 0).setCurrentText("等于")
        conditions_table.cellWidget(new_row, 1).setText("new")

        widget.plugin_config_buttons["update_item"].click()

        self.assertEqual(len(captured), 1)
        patch = captured[0]
        self.assertEqual(patch["schema_version"], "demo.config.v1")
        self.assertEqual(patch["operation"], "update_item")
        self.assertEqual(patch["path"], ["rules"])
        self.assertEqual(patch["target_index"], 0)
        self.assertFalse(patch["payload"]["anchor"]["enabled"])
        self.assertEqual(patch["payload"]["anchor"]["row_offset"], 2)
        self.assertEqual(patch["payload"]["conditions"][0]["value"], "remaining")
        self.assertEqual(patch["payload"]["conditions"][0]["meta"], "keep_2")
        self.assertEqual(patch["payload"]["conditions"][1], {"mode": "等于", "value": "new"})
        self.assertEqual(patch["value"], patch["payload"])
        window.close()
        app.processEvents()

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
        self.assertTrue(idle_actions["actions"]["refresh_plugins"]["enabled"])
        self.assertFalse(idle_actions["actions"]["legacy_plugin_config"]["enabled"])
        self.assertTrue(idle_actions["actions"]["legacy_plugin_config"]["fallback"])
        self.assertFalse(idle_actions["actions"]["legacy_plugin_config"]["preferred"])
        self.assertEqual(idle_actions["actions"]["legacy_plugin_config"]["ui_placement"], "compatibility_menu")
        self.assertFalse(idle_actions["actions"]["cancel_job"]["enabled"])

        plugin_actions = client.describe_workflow_actions(
            plan={"nodes": [{"node_type_id": "plugin.demo", "config": {"plugin_id": "demo"}}]},
            selected_indexes=[0],
            is_running=False,
        )
        self.assertTrue(plugin_actions["actions"]["legacy_plugin_config"]["enabled"])
        self.assertEqual(plugin_actions["actions"]["legacy_plugin_config"]["ui_prominence"], "low")

        running_actions = client.describe_workflow_actions(
            plan=SAMPLE_PLAN,
            selected_indexes=[0],
            is_running=True,
        )
        self.assertFalse(running_actions["actions"]["delete_nodes"]["enabled"])
        self.assertFalse(running_actions["actions"]["execute_plan"]["enabled"])
        self.assertFalse(running_actions["actions"]["refresh_plugins"]["enabled"])
        self.assertFalse(running_actions["actions"]["legacy_plugin_config"]["enabled"])
        self.assertTrue(running_actions["actions"]["cancel_job"]["enabled"])

        plugin_inputs = client.describe_picker_context(
            options_source={"type": "plugin_input_tables"},
            current_values={"input_tables": [{"alias": "明细"}, {"name": "归档"}]},
        )
        self.assertEqual(
            plugin_inputs["picker_context"]["candidates"],
            ["当前表", "workflow_current", "primary", "明细", "归档"],
        )

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

    def test_finalize_job_result_includes_message_panel(self):
        client = QtHeadlessEngineClient()

        final = client.finalize_job_result({
            "status": "completed",
            "message": "任务完成",
            "result": {
                "table": {"headers": ["A"], "rows": [["a"]]},
                "logs": ["done"],
                "steps": 1,
            },
        }, job_action="preview_plan")

        self.assertEqual(final["message_panel"]["title"], "任务结果")
        self.assertIn("任务完成", final["message_panel"]["body"])
        self.assertEqual(final["view_state"]["table_title"], "执行结果")
        self.assertTrue(final["view_state"]["should_refresh_preview_sources"])

        final_with_ui_logs = client.finalize_job_result({
            "status": "completed",
            "message": "任务完成",
            "result": {
                "table": {"headers": ["A"], "rows": [["a"]]},
                "logs": ["raw engine log"],
                "steps": 1,
            },
        }, job_action="preview_plan", logs=["[2026-06-23 14:32:18.237] [INFO] formatted ui log"])
        self.assertEqual(
            final_with_ui_logs["logs"],
            ["[2026-06-23 14:32:18.237] [INFO] formatted ui log"],
        )

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

        started = client.describe_job_started(status_prefix="预览")
        self.assertEqual(started["status_message"], "预览已启动")
        self.assertEqual(started["message_panel"]["title"], "预览")

        cancel_failure = client.describe_job_cancel_failure(error="stop failed")
        self.assertEqual(cancel_failure["status_message"], "取消任务失败")
        self.assertIn("stop failed", cancel_failure["message_panel"]["body"])

        poll_failure = client.describe_job_poll_failure(error="poll failed")
        self.assertEqual(poll_failure["status_message"], "后台任务状态读取失败")
        self.assertIn("poll failed", poll_failure["message_panel"]["body"])
        self.assertIn("demo", client.format_issues_text([{"severity": "warning", "code": "demo", "message": "hello"}]))

        validation = client.validate_workflow_request(SAMPLE_PLAN, execute_actions=True)
        validation_feedback = client.describe_validation_feedback(validation)
        self.assertEqual(validation_feedback["feedback"]["status_message"], "校验通过")
        self.assertIn("OK: true", validation_feedback["feedback"]["issue_message"])
        self.assertEqual(validation_feedback["feedback"]["sections"][0]["title"], "基础校验")
        self.assertIn("校验通过", validation_feedback["feedback"]["summary_lines"])
        self.assertEqual(validation_feedback["feedback"]["message_panel"]["preferred_tab"], "info")
        self.assertIn("基础校验", validation_feedback["feedback"]["message_panel"]["info_body"])

        message_panel = client.build_message_panel_state(
            mode="warning",
            title="测试",
            issues=[{"severity": "warning", "code": "demo", "message": "hello"}],
            logs=["log-1"],
        )
        self.assertEqual(message_panel["panel"]["mode"], "warning")
        self.assertIn("hello", message_panel["panel"]["body"])
        self.assertEqual(message_panel["panel"]["preferred_tab"], "issues")
        self.assertIn("hello", message_panel["panel"]["issue_body"])

        picker_feedback = client.describe_picker_feedback(
            action_key="pick_table_field",
            field_key="lookup_field",
            table_field="lookup_table",
            table_name="",
            candidates=[],
        )
        self.assertEqual(picker_feedback["feedback"]["status_message"], "请先选择关联数据表。")
        self.assertIn("lookup_table", picker_feedback["feedback"]["issue_message"])
        self.assertEqual(picker_feedback["feedback"]["issues"][0]["code"], "table_context_required")

        plan_ref_feedback = client.describe_picker_feedback(
            action_key="pick_plan_ref",
            field_key="loop_id",
            ref_kind="loop_id",
            candidates=[],
        )
        self.assertEqual(plan_ref_feedback["feedback"]["status_message"], "当前计划没有可用循环。")
        self.assertIn("请先添加对应节点或填写自定义值", plan_ref_feedback["feedback"]["issue_message"])
        self.assertEqual(plan_ref_feedback["feedback"]["issues"][0]["code"], "plan_refs_missing")

        runtime_ref_feedback = client.describe_picker_feedback(
            action_key="pick_runtime_ref",
            field_key="transit_table",
            ref_kind="transit_table",
            candidates=[],
        )
        self.assertEqual(runtime_ref_feedback["feedback"]["status_message"], "当前计划没有可用中转表。")
        self.assertIn("请先配置相关节点或填写自定义值", runtime_ref_feedback["feedback"]["issue_message"])
        self.assertEqual(runtime_ref_feedback["feedback"]["issues"][0]["code"], "runtime_refs_missing")

    def test_facade_applies_node_config_state(self):
        client = QtHeadlessEngineClient()

        invalid_node = copy.deepcopy(SAMPLE_PLAN["nodes"][0])
        invalid_node["config"] = dict(invalid_node.get("config") or {})
        invalid_node["config"]["columns_text"] = "status=ready\n=broken"
        invalid_result = client.apply_node_config_state(
            SAMPLE_PLAN,
            index=0,
            node=invalid_node,
            preview_headers=SAMPLE_HEADERS,
        )
        self.assertFalse(invalid_result["ok"])
        self.assertEqual(invalid_result["feedback"]["title"], "节点配置校验失败")

        valid_node = copy.deepcopy(SAMPLE_PLAN["nodes"][0])
        valid_node["config"] = dict(valid_node.get("config") or {})
        valid_node["config"]["columns_text"] = "status=updated"
        valid_result = client.apply_node_config_state(
            SAMPLE_PLAN,
            index=0,
            node=valid_node,
            preview_headers=SAMPLE_HEADERS,
        )
        self.assertTrue(valid_result["ok"])
        self.assertEqual(valid_result["feedback"]["status_message"], "节点配置已应用。")
        applied_plan = valid_result["apply_result"]["plan"]
        self.assertEqual(applied_plan["nodes"][0]["config"]["columns_text"], "status=updated")
        context_payload = valid_result["node_config_context"]
        self.assertTrue(context_payload["ok"])
        context_fields = {
            field["key"]: field
            for field in context_payload["fields"]
        }
        self.assertIn("columns_text", context_fields)
        self.assertEqual(context_fields["columns_text"]["help_payload"]["key"], "columns_text")
        self.assertTrue(context_fields["columns_text"]["help_payload"]["sections"])

    def test_facade_describes_shared_node_config_context(self):
        client = QtHeadlessEngineClient()

        described = client.describe_node_config_context(
            "字段映射写入表",
            preview_headers=["源字段"],
            table_names=["orders", "result"],
            table_columns={"orders": ["id", "name"], "result": ["row_id", "status"]},
        )

        self.assertTrue(described["ok"])
        self.assertIsInstance(described["warning_items"], list)
        self.assertTrue(described["help_sections"])
        fields = {field["key"]: field for field in described["fields"]}
        self.assertIn("field_mappings", fields)
        columns = {
            column["key"]: column
            for column in fields["field_mappings"]["item_schema"]["columns"]
        }
        self.assertEqual(columns["source_field"]["context_requirements"][0]["kind"], "table_columns")
        self.assertEqual(columns["target_field"]["action"]["key"], "pick_table_field")
        self.assertEqual(described["help_sections"][0]["sections"][0]["title"], "字段说明")

        filter_context = client.describe_node_config_context(
            "core.filter",
            config={
                "extra_tables": ["people"],
                "output_fields": ["当前表.Code", "people.Name"],
            },
            preview_headers=["Code"],
            table_names=["people"],
            table_columns={"people": ["Code", "Name"]},
        )
        self.assertEqual(filter_context["shared_config_context"]["schema_version"], "filter_config_context.v1")
        self.assertEqual(filter_context["shared_config_context"]["field_state"]["first_current"], "当前表.Code")
        self.assertEqual(filter_context["shared_config_context"]["selected_tables"], ["当前表", "people"])
        self.assertEqual(
            filter_context["shared_config_context"]["available_fields"],
            ["当前表.Code", "people.Code", "people.Name"],
        )
        self.assertIn("实际输出字段", filter_context["shared_config_context"]["output_text"])
        shared_section = filter_context["shared_config_sections"][0]
        self.assertEqual(shared_section["title"], "共享配置状态")
        self.assertIn("可用字段：3 个", shared_section["lines"])

        command_result = client.apply_node_config_command(
            "core.filter",
            config={"extra_tables": ["people"], "output_fields": []},
            command={"type": "add_all_output_fields"},
            preview_headers=["Code"],
            table_names=["people"],
            table_columns={"people": ["Code", "Name"]},
        )
        self.assertTrue(command_result["ok"])
        self.assertEqual(command_result["config"]["output_fields"], ["当前表.Code", "people.Code", "people.Name"])
        self.assertEqual(command_result["node_config_context"]["shared_config_context"]["selected_tables"], ["当前表", "people"])

        option_result = client.resolve_node_config_options(
            "core.filter",
            config={"extra_tables": ["people"]},
            field_key="conditions.value",
            current_values={"value_source": "字段值"},
            preview_headers=["Code"],
            table_names=["people"],
            table_columns={"people": ["Code", "Name"]},
        )
        self.assertTrue(option_result["ok"])
        self.assertEqual(option_result["schema_version"], "filter_config_options.v1")
        self.assertEqual(option_result["choices"], ["当前表.Code", "people.Code", "people.Name"])

        advanced_service = client.describe_advanced_filter_service()
        advanced_state = client.describe_advanced_filter_state(
            selected_tables=["people"],
            columns_by_table={"people": ["Code", "Name"]},
        )
        advanced_command = client.apply_advanced_filter_command(
            advanced_state["state"],
            {"type": "add_all_output_fields"},
        )
        self.assertTrue(advanced_service["ok"])
        self.assertIn("save_preview_to_table", advanced_service["commands"])
        self.assertTrue(advanced_state["ok"])
        self.assertEqual(advanced_state["state"]["field_display_cache"], ["people.Code", "people.Name"])
        self.assertTrue(advanced_command["ok"])
        self.assertEqual(advanced_command["state"]["output_fields"], ["people.Code", "people.Name"])

    def test_facade_describes_confirmation_prompts(self):
        client = QtHeadlessEngineClient()

        clear_prompt = client.describe_confirmation_prompt(action="clear_nodes", plan=SAMPLE_PLAN)
        self.assertTrue(clear_prompt["prompt"]["required"])
        self.assertEqual(clear_prompt["prompt"]["code"], "confirm_clear_nodes")

        legacy_prompt = client.describe_confirmation_prompt(
            action="legacy_plugin_config",
            compatibility_action={
                "label": "兼容旧版设置",
                "requires_confirmation": True,
                "mode": "legacy_fallback",
                "lifecycle": "legacy_fallback",
                "migration_target": "describe_config + parameter_metadata + config_patch",
                "warning": "旧版 Tk 设置窗口仅作为兼容 fallback。",
            },
        )
        self.assertTrue(legacy_prompt["prompt"]["required"])
        self.assertEqual(legacy_prompt["prompt"]["code"], "confirm_legacy_plugin_config")
        self.assertEqual(legacy_prompt["prompt"]["confirm_label"], "兼容旧版设置")
        self.assertIn("兼容 fallback", legacy_prompt["prompt"]["message"])
        self.assertIn("模式：legacy_fallback", legacy_prompt["prompt"]["details"])

        run_prompt = client.describe_confirmation_prompt(
            action="run_plan",
            plan=SAMPLE_PLAN,
            output_settings={
                "mode": "覆盖当前表",
                "backup_before_overwrite": True,
            },
            access_precheck={"issues": [], "summary": "将写回数据库"},
        )
        self.assertTrue(run_prompt["prompt"]["required"])
        self.assertEqual(run_prompt["prompt"]["code"], "confirm_run_plan")
        self.assertIn("将写回数据库", "\n".join(run_prompt["prompt"]["details"]))
        self.assertIn("自动备份", "\n".join(run_prompt["prompt"]["details"]))

    def test_facade_describes_plan_command_and_file_failures(self):
        client = QtHeadlessEngineClient()

        plan_command_feedback = client.describe_plan_command_feedback({
            "ok": False,
            "issues": [{"severity": "warning", "code": "demo", "message": "不能删除最后一个节点"}],
        })
        self.assertEqual(plan_command_feedback["feedback"]["status_message"], "计划编辑失败")
        self.assertIn("不能删除最后一个节点", plan_command_feedback["feedback"]["message_panel"]["issue_body"])

        file_failure = client.describe_plan_file_failure(
            action="打开计划",
            issues=[{"severity": "error", "code": "schema", "message": "计划格式无效"}],
        )
        self.assertEqual(file_failure["feedback"]["status_message"], "打开计划失败：计划模板校验未通过")
        self.assertIn("计划格式无效", file_failure["feedback"]["message_panel"]["issue_body"])

    def test_facade_describes_file_actions_and_state_payloads(self):
        client = QtHeadlessEngineClient()

        open_action = client.describe_file_action("open_plan", plan_dir="plan")
        self.assertEqual(open_action["file_dialog"]["dialog"], "open_file")
        self.assertEqual(open_action["file_dialog"]["title"], "打开 workflow_plan")

        save_action = client.describe_file_action("save_plan", plan_dir="plan", current_plan_path="")
        self.assertEqual(save_action["file_dialog"]["dialog"], "save_file")
        self.assertIn("工作流计划.json", save_action["file_dialog"]["initial_path"])

        imported_state = client.build_import_table_state({
            "path": "demo.csv",
            "table": {"headers": ["A"], "rows": [["a"]]},
        })
        self.assertEqual(imported_state["state"]["table_title"], "输入表格")
        self.assertIn("demo.csv", imported_state["state"]["status_message"])
        self.assertEqual(imported_state["state"]["message_panel"]["title"], "导入输入表格")

        plan_with_input_source = copy.deepcopy(SAMPLE_PLAN)
        plan_with_input_source["input_source"] = {"type": "sqlite", "db_path": "input.db", "table_name": "orders"}
        plan_with_input_source["input_db_path"] = "input.db"
        loaded_state = client.build_loaded_plan_state({
            "path": "plan\\demo.json",
            "plan": plan_with_input_source,
            "warning": "已迁移旧字段",
        })
        self.assertEqual(loaded_state["state"]["plan_path"], "plan\\demo.json")
        self.assertEqual(loaded_state["state"]["input_source"]["table_name"], "orders")
        self.assertEqual(loaded_state["state"]["input_db_path"], "input.db")
        self.assertEqual(loaded_state["state"]["issue_message"], "已迁移旧字段")
        self.assertEqual(loaded_state["state"]["message_panel"]["mode"], "warning")

        saved_state = client.build_saved_plan_state({
            "path": "plan\\saved.json",
            "plan": SAMPLE_PLAN,
        }, SAMPLE_PLAN)
        self.assertEqual(saved_state["state"]["plan_path"], "plan\\saved.json")
        self.assertIn("已保存", saved_state["state"]["status_message"])
        self.assertEqual(saved_state["state"]["message_panel"]["title"], "保存计划")

        template_state = client.build_template_list_state({
            "templates": [
                {"name": "示例模板A", "path": "plan\\a.json"},
                {"name": "示例模板B", "path": "plan\\b.json"},
            ]
        }, show_status=True)
        self.assertEqual(template_state["state"]["template_count"], 2)
        self.assertEqual(template_state["state"]["status_message"], "模板刷新完成：2 个。")
        self.assertEqual(template_state["state"]["message_panel"]["title"], "计划模板")
        self.assertIn("示例模板A", template_state["state"]["message_panel"]["info_body"])

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
        first_combo = table.cellWidget(0, 0).findChild(qt.QtWidgets.QComboBox)
        second_widget = table.cellWidget(0, 1)
        second_line = second_widget if hasattr(second_widget, "text") else second_widget.findChild(qt.QtWidgets.QLineEdit)
        self.assertEqual(first_combo.currentText(), "A")
        self.assertEqual(second_line.text(), "AA")
        form._structured_list_add_row(editor)
        table.setCurrentCell(1, 0)
        table.cellWidget(1, 0).findChild(qt.QtWidgets.QComboBox).setCurrentText("B")
        second_widget = table.cellWidget(1, 1)
        second_line = second_widget if hasattr(second_widget, "text") else second_widget.findChild(qt.QtWidgets.QLineEdit)
        second_line.setText("BB")
        converted = form.to_node()
        self.assertEqual(converted["config"]["mappings"], [{"old": "A", "new": "AA"}, {"old": "B", "new": "BB"}])
        app.processEvents()

    def test_config_form_refreshes_dynamic_options_and_validation_state(self):
        try:
            qt = qt_app.load_qt6()
        except QtBindingUnavailable as exc:
            self.skipTest(str(exc))
        app = qt.QtWidgets.QApplication.instance() or qt.QtWidgets.QApplication([])
        schema = get_node_ui_schema("core.replace", preview_headers=["A", "B"])
        node = {
            "node_type_id": "core.replace",
            "node_id": "n1",
            "name": "批量替换",
            "enabled": True,
            "node_version": "1.0.0",
            "config": {
                "target_field": "A",
                "match_mode": "包含",
                "match_value": "x",
                "replace_mode": "整格替换为新值",
                "replace_value": "y",
                "match_value_source": "手动输入",
                "replace_value_source": "手动输入",
            },
        }
        form = NodeConfigForm(qt, headers=["A", "B"])
        form.set_node(node, headers=["A", "B"], schema=schema)
        form.set_headers(["C", "D"])
        target_editor = form.config_fields["target_field"]["editor"]
        self.assertIn("C", [target_editor.itemText(i) for i in range(target_editor.count())])
        form.set_validation_issues([{"path": "config.target_field", "message": "目标字段不存在"}])
        state = form.describe_state()
        self.assertIn("目标字段不存在", form.config_fields["target_field"]["editor"].toolTip())
        self.assertEqual(state["fields"]["target_field"]["issues"][0]["message"], "目标字段不存在")
        app.processEvents()

    def test_config_form_consumes_plugin_ui_metadata(self):
        try:
            qt = qt_app.load_qt6()
        except QtBindingUnavailable as exc:
            self.skipTest(str(exc))
        app = qt.QtWidgets.QApplication.instance() or qt.QtWidgets.QApplication([])
        schema = {
            "form": {
                "groups": [
                    {
                        "title": "插件参数",
                        "fields": [
                            {
                                "key": "params.mode",
                                "config_path": ["params", "mode"],
                                "label": "模式",
                                "type": "select",
                                "choices": [],
                                "placeholder": "选择模式",
                                "empty_text": "暂无模式",
                                "warning": "模式会影响运行耗时",
                                "invalid_value_text": "请选择有效模式",
                                "advanced": True,
                            },
                            {
                                "key": "params.path",
                                "config_path": ["params", "path"],
                                "label": "目录",
                                "type": "text",
                                "placeholder": "选择插件目录",
                                "width_hint": "wide",
                            },
                        ],
                    }
                ]
            },
            "parameter_metadata": {
                "schema_version": "plugin_parameters.v1",
                "plugin_id": "demo",
                "field_count": 2,
                "field_index": {
                    "params.mode": {"param_key": "mode", "config_path": ["params", "mode"]},
                    "params.path": {"param_key": "path", "config_path": ["params", "path"]},
                },
                "group_index": {
                    "plugin.parameters": {"title": "插件参数", "field_keys": ["params.mode", "params.path"]},
                },
                "layout_index": {
                    "schema_version": "plugin_parameter_layout.v1",
                    "field_order": ["params.mode", "params.path"],
                    "group_order": ["plugin.parameters"],
                    "groups": [
                        {"group_key": "plugin.parameters", "title": "插件参数", "advanced": False, "field_keys": ["params.mode", "params.path"], "field_count": 2},
                    ],
                },
                "ui_hints": {
                    "schema_version": "plugin_parameter_ui_hints.v1",
                    "field_count": 2,
                    "fields": [
                        {
                            "field_key": "params.mode",
                            "param_key": "mode",
                            "label": "模式",
                            "type": "select",
                            "placeholder": "选择模式",
                            "warning": "模式会影响运行耗时",
                            "advanced": True,
                        },
                        {
                            "field_key": "params.path",
                            "param_key": "path",
                            "label": "目录",
                            "type": "text",
                            "placeholder": "选择插件目录",
                            "width_hint": "wide",
                        },
                    ],
                    "advanced_fields": ["params.mode"],
                    "warning_fields": ["params.mode"],
                    "placeholder_fields": ["params.mode", "params.path"],
                    "numeric_fields": [],
                    "width_hint_fields": ["params.path"],
                },
                "dependency_index": {"params.mode": ["params.path"]},
                "capabilities": {"dynamic_options": True, "field_dependencies": True},
                "context_requirements": {"needs_dynamic_options": True},
            },
        }
        node = {
            "node_type_id": "plugin.demo",
            "node_id": "n1",
            "name": "Demo",
            "enabled": True,
            "node_version": "1.0.0",
            "config": {"params": {"mode": "", "path": ""}},
        }
        form = NodeConfigForm(qt)
        form.set_node(node, schema=schema)

        state = form.describe_state()
        self.assertEqual(state["parameter_metadata"]["schema_version"], "plugin_parameters.v1")
        self.assertEqual(state["parameter_metadata"]["plugin_id"], "demo")
        self.assertEqual(state["parameter_metadata"]["field_count"], 2)
        self.assertEqual(state["parameter_metadata"]["field_index_keys"], ["params.mode", "params.path"])
        self.assertEqual(state["parameter_metadata"]["group_index_keys"], ["plugin.parameters"])
        self.assertEqual(state["parameter_metadata"]["dependency_index"]["params.mode"], ["params.path"])
        self.assertEqual(state["parameter_metadata"]["layout_index"]["schema_version"], "plugin_parameter_layout.v1")
        self.assertEqual(state["parameter_metadata"]["ui_hints"]["schema_version"], "plugin_parameter_ui_hints.v1")
        self.assertIn("params.mode", state["parameter_metadata"]["layout_index"]["field_order"])
        self.assertIn("params.mode", state["parameter_metadata"]["ui_hints"]["advanced_fields"])
        self.assertIn("params.mode", state["parameter_metadata"]["ui_hints"]["warning_fields"])
        self.assertIn("params.path", state["parameter_metadata"]["ui_hints"]["placeholder_fields"])
        self.assertIn("params.path", state["parameter_metadata"]["ui_hints"]["width_hint_fields"])
        self.assertTrue(state["parameter_metadata"]["capabilities"]["dynamic_options"])
        self.assertTrue(state["parameter_metadata"]["context_requirements"]["needs_dynamic_options"])
        mode_state = state["fields"]["params.mode"]
        self.assertEqual(mode_state["placeholder"], "选择模式")
        self.assertIn("警告：模式会影响运行耗时", mode_state["tooltip"])
        self.assertIn("无效值提示：请选择有效模式", mode_state["tooltip"])
        self.assertIn("高级参数", mode_state["tooltip"])
        self.assertEqual(state["fields"]["params.path"]["placeholder"], "选择插件目录")
        self.assertGreaterEqual(form.config_fields["params.path"]["editor"].minimumWidth(), 260)
        app.processEvents()

    def test_config_form_uses_parameter_metadata_as_fallback_groups(self):
        try:
            qt = qt_app.load_qt6()
        except QtBindingUnavailable as exc:
            self.skipTest(str(exc))
        app = qt.QtWidgets.QApplication.instance() or qt.QtWidgets.QApplication([])
        schema = {
            "parameter_metadata": {
                "schema_version": "plugin_parameters.v1",
                "plugin_id": "demo",
                "field_count": 2,
                "fields": [
                    {
                        "key": "params.mode",
                        "config_path": ["params", "mode"],
                        "label": "模式",
                        "type": "select",
                        "choices": ["快", "稳"],
                        "default": "快",
                    },
                    {
                        "key": "params.path",
                        "config_path": ["params", "path"],
                        "label": "目录",
                        "type": "text",
                        "placeholder": "选择插件目录",
                        "default": "data",
                    },
                ],
                "group_index": {
                    "plugin.parameters": {
                        "title": "插件参数",
                        "advanced": False,
                        "field_keys": ["params.mode", "params.path"],
                    },
                },
                "layout_index": {
                    "schema_version": "plugin_parameter_layout.v1",
                    "field_order": ["params.mode", "params.path"],
                    "group_order": ["plugin.parameters"],
                    "groups": [
                        {
                            "group_key": "plugin.parameters",
                            "title": "插件参数",
                            "advanced": False,
                            "field_keys": ["params.mode", "params.path"],
                            "field_count": 2,
                        },
                    ],
                },
            },
        }
        node = {
            "node_type_id": "plugin.demo",
            "node_id": "n1",
            "name": "Demo",
            "enabled": True,
            "node_version": "1.0.0",
            "config": {},
        }
        form = NodeConfigForm(qt)
        form.set_node(node, schema=schema)

        self.assertIn("params.mode", form.config_fields)
        self.assertIn("params.path", form.config_fields)
        self.assertEqual(form.config_fields["params.mode"]["kind"], "choice")
        self.assertEqual(form.config_fields["params.path"]["kind"], "text")
        self.assertEqual(form.config_fields["params.mode"]["editor"].currentText(), "快")
        self.assertEqual(form.config_fields["params.path"]["editor"].text(), "data")
        self.assertEqual(form.config_fields["params.path"]["editor"].placeholderText(), "选择插件目录")
        self.assertEqual(form.to_node()["config"]["params"]["path"], "data")
        app.processEvents()

    def test_config_form_exposes_schema_action_buttons(self):
        try:
            qt = qt_app.load_qt6()
        except QtBindingUnavailable as exc:
            self.skipTest(str(exc))
        app = qt.QtWidgets.QApplication.instance() or qt.QtWidgets.QApplication([])
        schema = get_node_ui_schema("core.replace", preview_headers=["A", "B"])
        node = {
            "node_type_id": "core.replace",
            "node_id": "n1",
            "name": "批量替换",
            "enabled": True,
            "node_version": "1.0.0",
            "config": {
                "target_field": "A",
                "match_mode": "包含",
                "match_value": "x",
                "replace_mode": "整格替换为新值",
                "replace_value": "y",
                "match_value_source": "手动输入",
                "replace_value_source": "手动输入",
            },
        }
        calls = []

        def action_handler(payload):
            calls.append(payload)
            return {"value": "B"}

        form = NodeConfigForm(qt, headers=["A", "B"], action_handler=action_handler)
        form.set_node(node, headers=["A", "B"], schema=schema)
        form.widget.show()
        app.processEvents()
        state = form.describe_state()
        self.assertEqual(state["fields"]["target_field"]["action"]["key"], "pick_preview_header")
        self.assertTrue(state["fields"]["target_field"]["action_visible"])
        form.config_fields["target_field"]["action_button"].click()
        self.assertEqual(calls[0]["field_key"], "target_field")
        self.assertEqual(form.config_fields["target_field"]["editor"].currentText(), "B")
        app.processEvents()

    def test_config_form_supports_multi_select_field_values(self):
        try:
            qt = qt_app.load_qt6()
        except QtBindingUnavailable as exc:
            self.skipTest(str(exc))
        app = qt.QtWidgets.QApplication.instance() or qt.QtWidgets.QApplication([])
        schema = get_node_ui_schema("core.merge_columns", preview_headers=["A", "B", "C"])
        node = {
            "node_type_id": "core.merge_columns",
            "node_id": "n1",
            "name": "合并列",
            "enabled": True,
            "node_version": "1.0.0",
            "config": {
                "fields": ["A", "B"],
                "separators": ["-"],
                "output_field": "合并结果",
                "skip_empty": True,
                "trim_value": True,
                "empty_placeholder": "",
            },
        }
        form = NodeConfigForm(qt, headers=["A", "B", "C"])
        form.set_node(node, headers=["A", "B", "C"], schema=schema)
        editor = form.config_fields["fields"]["editor"]
        self.assertEqual(editor.text(), "A、B")
        self.assertEqual(form.to_node()["config"]["fields"], ["A", "B"])
        form._set_field_value(form.config_fields["fields"], ["B", "C"])
        self.assertEqual(editor.text(), "B、C")
        self.assertEqual(form.to_node()["config"]["fields"], ["B", "C"])
        app.processEvents()

    def test_config_form_exposes_shared_filter_service_commands(self):
        try:
            qt = qt_app.load_qt6()
        except QtBindingUnavailable as exc:
            self.skipTest(str(exc))
        app = qt.QtWidgets.QApplication.instance() or qt.QtWidgets.QApplication([])

        schema = get_node_ui_schema(
            "core.filter",
            table_names=["people"],
            table_columns={"people": ["Code", "Name"]},
        )
        form = NodeConfigForm(qt)
        form.set_node(
            {
                "node_type_id": "core.filter",
                "node_id": "n1",
                "name": "高级筛选",
                "enabled": True,
                "node_version": "1.0.0",
                "config": {
                    "source_table": "当前表",
                    "extra_tables": ["people"],
                    "conditions": [],
                    "join_rules": [],
                    "output_fields": [],
                    "logic": "AND",
                    "join_logic": "AND",
                    "result_limit": "5000",
                    "max_intermediate": "200000",
                },
            },
            headers=["Code"],
            table_names=["people"],
            table_columns={"people": ["Code", "Name"]},
            schema=schema,
        )
        form.widget.show()
        app.processEvents()

        panel = form.widget.findChild(qt.QtWidgets.QGroupBox, "sharedConfigServicePanel")
        add_all = form.widget.findChild(qt.QtWidgets.QPushButton, "sharedConfigCommand_add_all_output_fields")
        clear_output = form.widget.findChild(qt.QtWidgets.QPushButton, "sharedConfigCommand_clear_output_fields")
        build_preview = form.widget.findChild(qt.QtWidgets.QPushButton, "sharedConfigCommand_build_preview")
        state = form.describe_state()["shared_config_service"]

        self.assertIsNotNone(panel)
        self.assertIsNotNone(add_all)
        self.assertIsNotNone(clear_output)
        self.assertIsNotNone(build_preview)
        self.assertEqual(state["protocol_family"], "advanced_filter_service")
        self.assertIn("output_fields", state["section_ids"])
        self.assertIn("add_all_output_fields", state["visible_command_ids"])
        self.assertFalse(build_preview.isEnabled())
        self.assertIn("需要参数", build_preview.toolTip())

        add_all.click()
        app.processEvents()

        self.assertEqual(form.to_node()["config"]["output_fields"], ["当前表.Code", "people.Code", "people.Name"])
        self.assertIn("添加全部输出字段", form.describe_state()["shared_config_service"]["status_text"])
        self.assertIn("已应用", form.describe_state()["shared_config_service"]["status_text"])

        clear_output = form.widget.findChild(qt.QtWidgets.QPushButton, "sharedConfigCommand_clear_output_fields")
        self.assertIsNotNone(clear_output)
        clear_output.click()
        app.processEvents()

        self.assertEqual(form.to_node()["config"]["output_fields"], [])
        self.assertIn("清空输出字段", form.describe_state()["shared_config_service"]["status_text"])

    def test_config_form_supports_table_name_multi_select_actions(self):
        try:
            qt = qt_app.load_qt6()
        except QtBindingUnavailable as exc:
            self.skipTest(str(exc))
        app = qt.QtWidgets.QApplication.instance() or qt.QtWidgets.QApplication([])
        calls = []

        def action_handler(payload):
            calls.append(payload)
            return {"value": ["orders", "logs"]}

        form = NodeConfigForm(qt, table_names=["orders", "logs", "archive"], action_handler=action_handler)
        form.set_node(
            {
                "node_type_id": "demo.multi_table",
                "node_id": "n1",
                "name": "多表",
                "enabled": True,
                "node_version": "1.0.0",
                "config": {"extra_tables": ["orders"]},
            },
            table_names=["orders", "logs", "archive"],
            schema={
                "form": {
                    "groups": [
                        {
                            "title": "参数",
                            "fields": [
                                {
                                    "key": "extra_tables",
                                    "type": "field_multi_select",
                                    "options_source": {"type": "table_names"},
                                    "action": {"key": "pick_table_names", "label": "选择表", "multiple": True},
                                }
                            ],
                        }
                    ]
                }
            },
        )

        form._trigger_field_action("extra_tables")

        self.assertEqual(calls[0]["action"]["key"], "pick_table_names")
        self.assertEqual(calls[0]["table_names"], ["orders", "logs", "archive"])
        self.assertEqual(form.to_node()["config"]["extra_tables"], ["orders", "logs"])
        app.processEvents()

    def test_config_form_refreshes_table_column_choices_from_selected_table(self):
        try:
            qt = qt_app.load_qt6()
        except QtBindingUnavailable as exc:
            self.skipTest(str(exc))
        app = qt.QtWidgets.QApplication.instance() or qt.QtWidgets.QApplication([])
        schema = {
            "form": {
                "groups": [
                    {
                        "title": "参数",
                        "fields": [
                            {
                                "key": "lookup_table",
                                "type": "table_select",
                                "options_source": {"type": "table_names"},
                            },
                            {
                                "key": "lookup_field",
                                "type": "field_select",
                                "options_source": {"type": "table_columns", "table_field": "lookup_table"},
                            },
                        ],
                    }
                ]
            }
        }
        node = {
            "node_type_id": "demo.lookup_field",
            "node_id": "n1",
            "name": "表字段选择",
            "enabled": True,
            "node_version": "1.0.0",
            "config": {
                "lookup_table": "orders",
                "lookup_field": "id",
            },
        }
        form = NodeConfigForm(
            qt,
            table_names=["orders", "logs"],
            table_columns={"orders": ["id", "name"], "logs": ["row_id"]},
        )
        form.set_node(
            node,
            table_names=["orders", "logs"],
            table_columns={"orders": ["id", "name"], "logs": ["row_id"]},
            schema=schema,
        )
        table_editor = form.config_fields["lookup_table"]["editor"]
        field_editor = form.config_fields["lookup_field"]["editor"]
        self.assertIn("name", [field_editor.itemText(i) for i in range(field_editor.count())])
        table_editor.setCurrentText("logs")
        app.processEvents()
        self.assertIn("row_id", [field_editor.itemText(i) for i in range(field_editor.count())])
        app.processEvents()

    def test_structured_list_cells_support_schema_actions(self):
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
        calls = []

        def action_handler(payload):
            calls.append(payload)
            return {"value": "B"}

        form = NodeConfigForm(qt, headers=["A", "B"], action_handler=action_handler)
        form.set_node(node, headers=["A", "B"], schema=schema)
        editor = form.config_fields["mappings"]["editor"]
        table = editor.structured_state["table"]
        cell_container = table.cellWidget(0, 0)
        button = cell_container.findChild(qt.QtWidgets.QPushButton)
        combo = cell_container.findChild(qt.QtWidgets.QComboBox)
        self.assertIsNotNone(button)
        self.assertIsNotNone(combo)
        button.click()
        self.assertEqual(calls[0]["context"]["kind"], "structured_cell")
        self.assertEqual(combo.currentText(), "B")
        app.processEvents()

    def test_structured_list_cells_support_table_picker_actions(self):
        try:
            qt = qt_app.load_qt6()
        except QtBindingUnavailable as exc:
            self.skipTest(str(exc))
        app = qt.QtWidgets.QApplication.instance() or qt.QtWidgets.QApplication([])
        schema = {
            "form": {
                "groups": [
                    {
                        "title": "参数",
                        "fields": [
                            {
                                "key": "rules",
                                "type": "structured_list",
                                "item_schema": {
                                    "columns": [
                                        {
                                            "key": "table_name",
                                            "label": "目标表",
                                            "type": "table_select",
                                            "options_source": {"type": "table_names"},
                                        }
                                    ]
                                },
                            }
                        ],
                    }
                ]
            }
        }
        node = {
            "node_type_id": "demo.table_picker",
            "node_id": "n1",
            "name": "表格选择",
            "enabled": True,
            "node_version": "1.0.0",
            "config": {
                "rules": [{"table_name": "源表"}],
            },
        }
        calls = []

        def action_handler(payload):
            calls.append(payload)
            return {"value": "结果表"}

        form = NodeConfigForm(qt, table_names=["源表", "结果表"], action_handler=action_handler)
        form.set_node(node, table_names=["源表", "结果表"], schema=schema)
        editor = form.config_fields["rules"]["editor"]
        table = editor.structured_state["table"]
        cell_container = table.cellWidget(0, 0)
        button = cell_container.findChild(qt.QtWidgets.QPushButton)
        combo = cell_container.findChild(qt.QtWidgets.QComboBox)
        self.assertIsNotNone(button)
        self.assertIsNotNone(combo)
        button.click()
        self.assertEqual(calls[0]["action"]["key"], "pick_table_name")
        self.assertEqual(calls[0]["table_names"], ["源表", "结果表"])
        self.assertEqual(combo.currentText(), "结果表")
        app.processEvents()

    def test_structured_list_cells_support_multi_select_picker_actions(self):
        try:
            qt = qt_app.load_qt6()
        except QtBindingUnavailable as exc:
            self.skipTest(str(exc))
        app = qt.QtWidgets.QApplication.instance() or qt.QtWidgets.QApplication([])
        schema = {
            "form": {
                "groups": [
                    {
                        "title": "参数",
                        "fields": [
                            {
                                "key": "rules",
                                "type": "structured_list",
                                "item_schema": {
                                    "columns": [
                                        {
                                            "key": "fields",
                                            "label": "字段列表",
                                            "type": "field_multi_select",
                                            "options_source": {"type": "preview_headers"},
                                        }
                                    ]
                                },
                            }
                        ],
                    }
                ]
            }
        }
        node = {
            "node_type_id": "demo.multi_field_picker",
            "node_id": "n1",
            "name": "多字段选择",
            "enabled": True,
            "node_version": "1.0.0",
            "config": {
                "rules": [{"fields": ["A"]}],
            },
        }
        calls = []

        def action_handler(payload):
            calls.append(payload)
            return {"value": ["B", "C"]}

        form = NodeConfigForm(qt, headers=["A", "B", "C"], action_handler=action_handler)
        form.set_node(node, headers=["A", "B", "C"], schema=schema)
        editor = form.config_fields["rules"]["editor"]
        table = editor.structured_state["table"]
        cell_container = table.cellWidget(0, 0)
        button = cell_container.findChild(qt.QtWidgets.QPushButton)
        line_edit = cell_container.findChild(qt.QtWidgets.QLineEdit)
        self.assertIsNotNone(button)
        self.assertIsNotNone(line_edit)
        button.click()
        self.assertEqual(calls[0]["action"]["key"], "pick_preview_headers")
        self.assertEqual(calls[0]["headers"], ["A", "B", "C"])
        self.assertEqual(line_edit.text(), "B、C")
        self.assertEqual(form.to_node()["config"]["rules"], [{"fields": ["B", "C"]}])
        app.processEvents()

    def test_structured_list_refreshes_table_column_choices_per_row(self):
        try:
            qt = qt_app.load_qt6()
        except QtBindingUnavailable as exc:
            self.skipTest(str(exc))
        app = qt.QtWidgets.QApplication.instance() or qt.QtWidgets.QApplication([])
        schema = {
            "form": {
                "groups": [
                    {
                        "title": "参数",
                        "fields": [
                            {
                                "key": "rules",
                                "type": "structured_list",
                                "item_schema": {
                                    "columns": [
                                        {
                                            "key": "table_name",
                                            "label": "目标表",
                                            "type": "table_select",
                                            "options_source": {"type": "table_names"},
                                        },
                                        {
                                            "key": "field_name",
                                            "label": "目标字段",
                                            "type": "field_select",
                                            "options_source": {"type": "table_columns", "table_field": "table_name"},
                                        },
                                    ]
                                },
                            }
                        ],
                    }
                ]
            }
        }
        node = {
            "node_type_id": "demo.structured_table_field",
            "node_id": "n1",
            "name": "结构化表字段",
            "enabled": True,
            "node_version": "1.0.0",
            "config": {
                "rules": [{"table_name": "orders", "field_name": "id"}],
            },
        }
        form = NodeConfigForm(
            qt,
            table_names=["orders", "logs"],
            table_columns={"orders": ["id", "name"], "logs": ["row_id"]},
        )
        form.set_node(
            node,
            table_names=["orders", "logs"],
            table_columns={"orders": ["id", "name"], "logs": ["row_id"]},
            schema=schema,
        )
        editor = form.config_fields["rules"]["editor"]
        table = editor.structured_state["table"]
        table_name_editor = table.cellWidget(0, 0).findChild(qt.QtWidgets.QComboBox)
        field_editor = table.cellWidget(0, 1).findChild(qt.QtWidgets.QComboBox)
        self.assertIn("name", [field_editor.itemText(i) for i in range(field_editor.count())])
        table_name_editor.setCurrentText("logs")
        app.processEvents()
        self.assertIn("row_id", [field_editor.itemText(i) for i in range(field_editor.count())])
        app.processEvents()

    def test_structured_list_refreshes_table_name_choices_from_multi_select_field(self):
        try:
            qt = qt_app.load_qt6()
        except QtBindingUnavailable as exc:
            self.skipTest(str(exc))
        app = qt.QtWidgets.QApplication.instance() or qt.QtWidgets.QApplication([])
        schema = {
            "form": {
                "groups": [
                    {
                        "title": "参数",
                        "fields": [
                            {
                                "key": "extra_tables",
                                "type": "field_multi_select",
                                "options_source": {"type": "table_names"},
                            },
                            {
                                "key": "rules",
                                "type": "structured_list",
                                "item_schema": {
                                    "columns": [
                                        {
                                            "key": "table_name",
                                            "label": "目标表",
                                            "type": "table_select",
                                            "options_source": {"type": "field_values", "field": "extra_tables", "value_kind": "table_names"},
                                        }
                                    ]
                                },
                            }
                        ],
                    }
                ]
            }
        }
        node = {
            "node_type_id": "demo.contextual_table_picker",
            "node_id": "n1",
            "name": "上下文表选择",
            "enabled": True,
            "node_version": "1.0.0",
            "config": {
                "extra_tables": ["logs"],
                "rules": [{"table_name": "logs"}],
            },
        }
        form = NodeConfigForm(qt, table_names=["orders", "logs", "archive"])
        form.set_node(node, table_names=["orders", "logs", "archive"], schema=schema)
        editor = form.config_fields["rules"]["editor"]
        table_widget = editor.structured_state["table"]
        column_schema = editor.structured_state["columns"][0]
        table_name_editor = form._structured_cell_widget(table_widget.cellWidget(0, 0), column_schema)

        self.assertEqual([table_name_editor.itemText(i) for i in range(table_name_editor.count())], ["logs"])

        form.config_fields["extra_tables"]["editor"].multi_select_value = ["orders", "archive"]
        form.config_fields["extra_tables"]["editor"].setText("2 项")
        form._apply_dynamic_state()
        app.processEvents()

        self.assertEqual([table_name_editor.itemText(i) for i in range(table_name_editor.count())], ["logs", "orders", "archive"])

    def test_structured_list_cells_support_single_table_field_picker_actions(self):
        try:
            qt = qt_app.load_qt6()
        except QtBindingUnavailable as exc:
            self.skipTest(str(exc))
        app = qt.QtWidgets.QApplication.instance() or qt.QtWidgets.QApplication([])
        schema = {
            "form": {
                "groups": [
                    {
                        "title": "参数",
                        "fields": [
                            {
                                "key": "rules",
                                "type": "structured_list",
                                "item_schema": {
                                    "columns": [
                                        {
                                            "key": "table_name",
                                            "label": "目标表",
                                            "type": "table_select",
                                            "options_source": {"type": "table_names"},
                                        },
                                        {
                                            "key": "field_name",
                                            "label": "目标字段",
                                            "type": "field_select",
                                            "options_source": {"type": "table_columns", "table_field": "table_name"},
                                        },
                                    ]
                                },
                            }
                        ],
                    }
                ]
            }
        }
        node = {
            "node_type_id": "demo.structured_table_field",
            "node_id": "n1",
            "name": "结构化表字段",
            "enabled": True,
            "node_version": "1.0.0",
            "config": {
                "rules": [{"table_name": "orders", "field_name": "id"}],
            },
        }
        calls = []

        def action_handler(payload):
            calls.append(payload)
            return {"value": "name"}

        form = NodeConfigForm(
            qt,
            table_names=["orders", "logs"],
            table_columns={"orders": ["id", "name"], "logs": ["row_id"]},
            action_handler=action_handler,
        )
        form.set_node(
            node,
            table_names=["orders", "logs"],
            table_columns={"orders": ["id", "name"], "logs": ["row_id"]},
            schema=schema,
        )
        editor = form.config_fields["rules"]["editor"]
        table = editor.structured_state["table"]
        cell_container = table.cellWidget(0, 1)
        button = cell_container.findChild(qt.QtWidgets.QPushButton)
        combo = cell_container.findChild(qt.QtWidgets.QComboBox)
        self.assertIsNotNone(button)
        self.assertIsNotNone(combo)
        button.click()
        self.assertEqual(calls[0]["action"]["key"], "pick_table_field")
        self.assertEqual(calls[0]["table_columns"], {"orders": ["id", "name"], "logs": ["row_id"]})
        self.assertEqual(combo.currentText(), "name")
        self.assertEqual(form.to_node()["config"]["rules"], [{"table_name": "orders", "field_name": "name"}])
        app.processEvents()

    def test_structured_list_cells_expose_shared_tooltips(self):
        try:
            qt = qt_app.load_qt6()
        except QtBindingUnavailable as exc:
            self.skipTest(str(exc))
        app = qt.QtWidgets.QApplication.instance() or qt.QtWidgets.QApplication([])

        schema = get_node_ui_schema(
            "字段映射写入表",
            preview_headers=["源字段"],
            table_names=["orders", "result"],
            table_columns={"orders": ["id", "name"], "result": ["row_id", "status"]},
        )
        form = NodeConfigForm(
            qt,
            table_names=["orders", "result"],
            table_columns={"orders": ["id", "name"], "result": ["row_id", "status"]},
        )
        form.set_node(
            {
                "node_type_id": "字段映射写入表",
                "node_id": "n1",
                "name": "写回",
                "enabled": True,
                "node_version": "1.0.0",
                "config": {
                    "writeback_direction": "当前表写入SQLite目标表",
                    "source_table": "orders",
                    "target_table": "result",
                    "use_match_rules": True,
                    "match_rules": [{"source_field": "id", "target_field": "row_id"}],
                    "field_mappings": [{"source_field": "name", "target_field": "status"}],
                    "overwrite_policy": "目标已有值且不同才覆盖",
                    "source_empty_policy": "跳过",
                    "source_empty_fixed": "",
                    "no_match_policy": "跳过并记录",
                    "multi_match_policy": "跳过并记录",
                    "duplicate_target_policy": "跳过重复并记录异常",
                    "enable_write": False,
                    "backup_before_write": True,
                    "output_preview_table": True,
                    "sequential_insert_missing_rows": True,
                },
            },
            table_names=["orders", "result"],
            table_columns={"orders": ["id", "name"], "result": ["row_id", "status"]},
            schema=schema,
        )

        frame = form.config_fields["field_mappings"]["editor"]
        table = frame.structured_state["table"]
        cell = table.cellWidget(0, 1)
        button = cell.findChild(qt.QtWidgets.QPushButton)
        combo = cell.findChild(qt.QtWidgets.QComboBox)

        self.assertIsNotNone(button)
        self.assertIsNotNone(combo)
        self.assertIn("字段说明", combo.toolTip())
        self.assertIn("字段说明", button.toolTip())
        app.processEvents()

    def test_controller_handles_single_table_field_picker_actions(self):
        try:
            qt = qt_app.load_qt6()
        except QtBindingUnavailable as exc:
            self.skipTest(str(exc))
        app = qt.QtWidgets.QApplication.instance() or qt.QtWidgets.QApplication([])
        window = build_main_window(qt)
        controller = window.qt_workflow_controller

        controller.config_form.set_node(
            {
                "node_type_id": "demo.lookup_field_picker",
                "node_id": "n1",
                "name": "表字段选择",
                "enabled": True,
                "node_version": "1.0.0",
                "config": {
                    "lookup_table": "orders",
                    "lookup_field": "id",
                },
            },
            table_names=["orders"],
            table_columns={"orders": ["id", "name"]},
            schema={
                "form": {
                    "groups": [
                        {
                            "title": "参数",
                            "fields": [
                                {
                                    "key": "lookup_table",
                                    "type": "table_select",
                                    "options_source": {"type": "table_names"},
                                },
                                {
                                    "key": "lookup_field",
                                    "type": "field_select",
                                    "options_source": {"type": "table_columns", "table_field": "lookup_table"},
                                    "action": {"key": "pick_table_field", "table_field": "lookup_table"},
                                },
                            ],
                        }
                    ]
                }
            },
        )

        with patch.object(controller.qt.QtWidgets.QInputDialog, "getItem", return_value=("name", True)):
            result = controller._pick_single_table_field_for_field(
                "lookup_field",
                {
                    "action": {"key": "pick_table_field", "table_field": "lookup_table"},
                    "schema": {"options_source": {"type": "table_columns", "table_field": "lookup_table"}},
                    "table_columns": {"orders": ["id", "name"]},
                    "value": "id",
                },
            )

        self.assertEqual(result["value"], "name")
        window.close()
        app.processEvents()

    def test_controller_uses_shared_picker_feedback_for_missing_candidates(self):
        try:
            qt = qt_app.load_qt6()
        except QtBindingUnavailable as exc:
            self.skipTest(str(exc))
        app = qt.QtWidgets.QApplication.instance() or qt.QtWidgets.QApplication([])
        window = build_main_window(qt)
        controller = window.qt_workflow_controller

        result = controller._pick_single_value_for_field("target_field", {"headers": [], "value": ""})
        self.assertEqual(result, {})
        self.assertEqual(controller.status_bar.currentMessage(), "当前没有可选字段。")
        self.assertEqual(controller.current_message_panel.get("title"), "字段选择")
        self.assertIn("当前没有可选字段", controller.issue_text.toPlainText())

        controller.config_form.set_node(
            {
                "node_type_id": "demo.lookup_field_picker",
                "node_id": "n1",
                "name": "表字段选择",
                "enabled": True,
                "node_version": "1.0.0",
                "config": {
                    "lookup_table": "",
                    "lookup_field": "",
                },
            },
            table_names=["orders"],
            table_columns={"orders": ["id", "name"]},
            schema={
                "form": {
                    "groups": [
                        {
                            "title": "参数",
                            "fields": [
                                {"key": "lookup_table", "type": "table_select", "options_source": {"type": "table_names"}},
                                {"key": "lookup_field", "type": "field_select", "options_source": {"type": "table_columns", "table_field": "lookup_table"}},
                            ],
                        }
                    ]
                }
            },
        )
        result = controller._pick_single_table_field_for_field(
            "lookup_field",
            {
                "action": {"key": "pick_table_field", "table_field": "lookup_table"},
                "schema": {"options_source": {"type": "table_columns", "table_field": "lookup_table"}},
                "table_columns": {"orders": ["id", "name"]},
                "value": "",
            },
        )
        self.assertEqual(result, {})
        self.assertEqual(controller.status_bar.currentMessage(), "请先选择关联数据表。")
        self.assertIn("lookup_table", controller.issue_text.toPlainText())

        window.close()
        app.processEvents()

    def test_node_ui_metadata_maps_protocol_to_chinese_ui(self):
        self.assertEqual(node_display_label("core.new_columns"), "新建列")
        self.assertEqual(category_label("数据处理"), "数据处理")
        self.assertEqual(node_field_label("enabled"), "启用")
        self.assertEqual(config_field_label("columns_text"), "新字段列表")
        self.assertEqual(choices_for_field("target_field", headers=["A", "B"]), ["A", "B"])
        self.assertIn("按列配置值", choices_for_field("value_mode"))
        self.assertEqual(config_layout_for_node("core.new_columns")[0]["title"], "字段定义")

    def test_config_form_splits_legacy_join_rule_and_preserves_runtime_shape(self):
        try:
            qt = qt_app.load_qt6()
        except QtBindingUnavailable as exc:
            self.skipTest(str(exc))
        app = qt.QtWidgets.QApplication.instance() or qt.QtWidgets.QApplication([])

        schema = get_node_ui_schema(
            "core.filter",
            table_names=["orders", "people"],
            table_columns={"orders": ["id", "name"], "people": ["code", "title"]},
        )
        form = NodeConfigForm(qt)
        form.set_node(
            {
                "node_type_id": "core.filter",
                "node_id": "n1",
                "name": "高级筛选",
                "enabled": True,
                "node_version": "1.0.0",
                "config": {
                    "source_table": "orders",
                    "extra_tables": ["people"],
                    "join_rules": [{"left": "id", "op": "等于", "right": "people.code"}],
                },
            },
            table_names=["orders", "people"],
            table_columns={"orders": ["id", "name"], "people": ["code", "title"]},
            schema=schema,
        )

        frame = form.config_fields["join_rules"]["editor"]
        table = frame.structured_state["table"]
        right_table_column = next(i for i, col in enumerate(frame.structured_state["columns"]) if col.get("key") == "right_table")
        right_column = next(i for i, col in enumerate(frame.structured_state["columns"]) if col.get("key") == "right")
        right_table_combo = form._structured_cell_widget(table.cellWidget(0, right_table_column), frame.structured_state["columns"][right_table_column])
        right_combo = form._structured_cell_widget(table.cellWidget(0, right_column), frame.structured_state["columns"][right_column])

        self.assertEqual(right_table_combo.currentText(), "people")
        self.assertEqual(right_combo.currentText(), "people.code")
        self.assertEqual([right_table_combo.itemText(i) for i in range(right_table_combo.count())], ["people"])
        shared_context = form.describe_state()["shared_config_context"]
        self.assertEqual(shared_context["schema_version"], "filter_config_context.v1")
        self.assertEqual(shared_context["available_fields"], ["people.code", "people.title"])
        self.assertEqual(shared_context["selected_tables"], ["当前表", "people"])

        right_table_combo.setCurrentText("people")
        app.processEvents()
        self.assertEqual([right_combo.itemText(i) for i in range(right_combo.count())], ["people.code", "people.title"])

        right_combo.setCurrentText("people.title")
        node = form.to_node()
        self.assertEqual(node["config"]["join_rules"], [{"left": "id", "op": "等于", "right_table": "people", "right": "people.title"}])
        self.assertEqual(config_layout_for_node("批量替换")[0]["title"], "目标与匹配")
        self.assertIn("每行一个新字段", field_help_text("columns_text"))
        self.assertIn("添加字段", node_summary("core.new_columns"))
        self.assertIn("可预览", node_badges("core.replace", supported_headless=True))
        self.assertTrue(node_warnings("core.delete_columns"))
        self.assertIn("暂不支持", format_node_detail("core.filter", supported_headless=False))
        detail_payload = build_node_detail_payload("core.filter", supported_headless=False)
        self.assertEqual(detail_payload["category"], "数据处理")
        self.assertIn("兼容性", [section["title"] for section in detail_payload["sections"]])
        self.assertTrue(detail_payload["config_summary"])
        self.assertTrue(detail_payload["compatibility"]["legacy_ui_required"])
        self.assertEqual(detail_payload["meta_items"][0]["label"], "分类")
        self.assertIn("执行层：仅旧执行链", detail_payload["meta_text"])
        detail_payload_supported = build_node_detail_payload("core.replace", supported_headless=True)
        self.assertIn("必填", "\n".join(detail_payload_supported["config_summary"]))
        self.assertIn("动态显示", "\n".join(detail_payload_supported["config_summary"]))
        self.assertIn("目标字段", detail_payload_supported["config_capabilities"]["required_fields"])
        self.assertIn("匹配值字段", detail_payload_supported["config_capabilities"]["dynamic_fields"])
        self.assertIn("目标字段", detail_payload_supported["config_capabilities"]["action_fields"])
        self.assertTrue(detail_payload_supported["compatibility"]["headless_preview"])
        self.assertIn("表单能力", [section["title"] for section in detail_payload_supported["sections"]])
        self.assertIn("兼容性：可直接预览/执行", detail_payload_supported["meta_text"])
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
        writeback_schema = get_node_ui_schema(
            "字段映射写入表",
            table_names=["orders", "result"],
            table_columns={"orders": ["id", "name"], "result": ["row_id", "status"]},
        )
        writeback_fields = {
            field["key"]: field
            for group in writeback_schema["form"]["groups"]
            for field in group["fields"]
        }
        mapping_columns = {
            item["key"]: item
            for item in writeback_fields["field_mappings"]["item_schema"]["columns"]
        }
        self.assertEqual(mapping_columns["source_field"]["options_source"], {"type": "table_columns", "table_field": "source_table"})
        self.assertEqual(mapping_columns["target_field"]["action"]["key"], "pick_table_field")

    def test_config_form_uses_shared_filter_option_resolver_for_join_rules(self):
        try:
            qt = qt_app.load_qt6()
        except QtBindingUnavailable as exc:
            self.skipTest(str(exc))
        qt.QtWidgets.QApplication.instance() or qt.QtWidgets.QApplication([])

        class SpyClient(QtHeadlessEngineClient):
            def __init__(self):
                super().__init__()
                self.option_calls = []

            def resolve_node_config_options(self, node_type_id="", **kwargs):
                self.option_calls.append({"node_type_id": node_type_id, **copy.deepcopy(kwargs)})
                return super().resolve_node_config_options(node_type_id, **kwargs)

        client = SpyClient()
        schema = get_node_ui_schema(
            "core.filter",
            table_names=["people"],
            table_columns={"people": ["code", "title"]},
        )
        form = NodeConfigForm(qt, headers=["id"], table_names=["people"], table_columns={"people": ["code", "title"]}, engine_client=client)
        form.set_node(
            {
                "node_type_id": "core.filter",
                "node_id": "n1",
                "name": "高级筛选",
                "enabled": True,
                "node_version": "1.0.0",
                "config": {
                    "source_table": "",
                    "extra_tables": ["people"],
                    "join_rules": [
                        {
                            "left": "当前表.id",
                            "op": "等于",
                            "right_table": "people",
                            "right": "people.code",
                        }
                    ],
                },
            },
            headers=["id"],
            table_names=["people"],
            table_columns={"people": ["code", "title"]},
            schema=schema,
        )

        frame = form.config_fields["join_rules"]["editor"]
        table = frame.structured_state["table"]
        right_column = next(i for i, col in enumerate(frame.structured_state["columns"]) if col.get("key") == "right")
        right_combo = form._structured_cell_widget(table.cellWidget(0, right_column), frame.structured_state["columns"][right_column])

        self.assertEqual([right_combo.itemText(i) for i in range(right_combo.count())], ["people.code", "people.title"])
        self.assertTrue(any(call.get("field_key") == "join_rules.right" for call in client.option_calls))
        right_call = next(call for call in client.option_calls if call.get("field_key") == "join_rules.right")
        self.assertEqual(right_call["current_values"]["right_table"], "people")
        self.assertEqual(right_call["preview_headers"], ["id"])
        self.assertEqual(right_call["table_columns"], {"people": ["code", "title"]})

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

    def test_controller_loads_sqlite_input_table_from_source_panel(self):
        try:
            qt = qt_app.load_qt6()
        except QtBindingUnavailable as exc:
            self.skipTest(str(exc))
        app = qt.QtWidgets.QApplication.instance() or qt.QtWidgets.QApplication([])
        with TemporaryDirectory() as temp_dir:
            db_path = str(Path(temp_dir) / "input.db")
            TableAccessManager(db_path).write_table(
                "orders",
                ["id", "name"],
                [["1", "Alice"], ["2", "Bob"]],
                mode="replace",
            )
            window = build_main_window(qt)
            controller = window.qt_workflow_controller

            controller.output_db_path_edit.setText(db_path)
            controller.refresh_input_table_combo()
            self.assertEqual(controller.input_table_combo.count(), 0)
            self.assertFalse(controller.load_input_table_button.isEnabled())

            controller.input_db_path_edit.setText(db_path)
            controller.apply_input_db_path_from_edit()
            controller.last_preview_headers = ["old"]
            controller.last_preview_rows = [["preview"]]
            controller.node_config_preview_cache = {"node_1": {"headers": ["old"]}}
            controller.refresh_input_table_combo()
            controller.load_selected_input_table()
            app.processEvents()

            self.assertEqual(controller.current_input_db_path, db_path)
            self.assertEqual(controller.input_db_path_edit.text(), db_path)
            self.assertEqual(controller.input_table_combo.currentText(), "orders")
            self.assertEqual(controller.current_headers, ["id", "name"])
            self.assertEqual(controller.current_rows, [["1", "Alice"], ["2", "Bob"]])
            self.assertEqual(controller.current_input_source["table_name"], "orders")
            self.assertEqual(controller.last_preview_headers, [])
            self.assertEqual(controller.last_preview_rows, [])
            self.assertEqual(controller.node_config_preview_cache, {})
            self.assertEqual(controller.input_summary_label.text(), "当前输入：2 行 x 2 列")
            self.assertIn("旧预览结果已清空", controller.current_message_panel.get("body", ""))
            self.assertIn("已载入输入表", controller.status_bar.currentMessage())
            self.assertIn("服务动作：load_table", controller.load_input_table_button.toolTip())
            window.close()
            app.processEvents()

    def test_controller_input_table_actions_follow_data_source_service(self):
        try:
            qt = qt_app.load_qt6()
        except QtBindingUnavailable as exc:
            self.skipTest(str(exc))
        app = qt.QtWidgets.QApplication.instance() or qt.QtWidgets.QApplication([])
        with TemporaryDirectory() as temp_dir:
            db_path = str(Path(temp_dir) / "input.db")
            TableAccessManager(db_path).write_table("orders", ["id"], [["1"]], mode="replace")
            window = build_main_window(qt)
            controller = window.qt_workflow_controller
            controller.input_db_path_edit.setText(db_path)
            controller.apply_input_db_path_from_edit(show_status=False)

            self.assertTrue(controller.load_input_table_button.isEnabled())
            self.assertIn("服务动作：load_table", controller.load_input_table_button.toolTip())
            controller.data_source_service_description = {"table_actions": {}}
            controller.refresh_input_table_combo()
            self.assertFalse(controller.load_input_table_button.isEnabled())
            self.assertIn("未声明 list_tables", controller.input_table_combo.toolTip())
            controller.load_selected_input_table()
            self.assertIn("不支持载入输入表", controller.status_bar.currentMessage())
            window.close()
            app.processEvents()

    def test_data_source_manager_loads_table_and_applies_workflow_input(self):
        try:
            qt = qt_app.load_qt6()
        except QtBindingUnavailable as exc:
            self.skipTest(str(exc))
        app = qt.QtWidgets.QApplication.instance() or qt.QtWidgets.QApplication([])
        with TemporaryDirectory() as temp_dir:
            db_path = str(Path(temp_dir) / "input.db")
            TableAccessManager(db_path).write_table(
                "orders",
                ["id", "name"],
                [["1", "Alice"], ["2", "Bob"], ["3", "Bob Jr"]],
                mode="replace",
            )
            window = build_main_window(qt)
            controller = window.qt_workflow_controller

            controller.input_db_path_edit.setText(db_path)
            controller.apply_input_db_path_from_edit(show_status=False)
            controller.open_data_source_manager()
            manager = controller.data_source_manager_controller
            manager.refresh_table_combo()
            manager.table_combo.setCurrentText("orders")
            manager.load_selected_table()
            manager.search_edit.setText("Bob")
            manager.search_current_table(reset=True)
            first_index = manager.table_view.currentIndex()
            manager.goto_search_match(1)
            manager_state = manager.describe_state()
            manager.apply_to_workflow()
            app.processEvents()

            background_role = qt_enum(qt, "ItemDataRole", "BackgroundRole")
            current_index = manager.table_view.currentIndex()
            self.assertEqual(manager.current_table()["headers"], ["id", "name"])
            self.assertEqual(manager_state["schema_version"], "data_source_manager_state.v1")
            self.assertEqual(manager_state["panel_state"]["schema_version"], "data_source_panel_state.v1")
            self.assertEqual(manager_state["panel_state"]["shape"], {"rows": 3, "columns": 2})
            self.assertEqual(manager_state["panel_state"]["view_state"]["shape_text"], "3 行 x 2 列")
            self.assertEqual(manager_state["panel_state"]["view_state"]["search"]["current_cell"], {"row": 2, "column": 1})
            self.assertTrue(manager_state["panel_state"]["view_state"]["action_enabled"]["save_sqlite"])
            self.assertEqual(manager_state["service"]["schema_version"], "data_source_service.v1")
            self.assertEqual(manager_state["service"]["protocol_family"], "data_source_service")
            self.assertTrue(manager_state["service"]["capabilities"]["table_handles"])
            self.assertTrue(manager_state["service"]["capabilities"]["panel_state"])
            self.assertIn("build_data_source_panel_state", manager_state["service"]["action_ids"])
            self.assertIn("build_data_source_manager_state", manager_state["service"]["action_ids"])
            self.assertIn("describe_data_source_actions", manager_state["service"]["action_ids"])
            self.assertIn("save_sqlite", manager_state["service"]["data_action_ids"])
            self.assertIn("load_table", manager_state["service"]["table_action_ids"])
            self.assertIn("get_table_handle_page", manager_state["service"]["table_action_ids"])
            self.assertEqual(
                manager_state["service"]["result_schemas"]["table_page"]["schema_version"],
                "table_page.v1",
            )
            self.assertEqual(
                manager_state["service"]["client_profiles"]["schema_version"],
                "data_source_client_profiles.v1",
            )
            self.assertEqual(
                manager_state["service"]["transport_hints"]["table_transfer"]["preferred_action"],
                "create_table_handle",
            )
            self.assertEqual(
                manager_state["service"]["result_schemas"]["data_source_manager_state"]["schema_version"],
                "data_source_manager_state.v1",
            )
            self.assertEqual(manager_state["action_schema"]["schema_version"], "data_source_action_schema.v1")
            self.assertIn("patch_cell", manager_state["action_schema"]["action_ids"])
            self.assertEqual(
                manager_state["action_schema"]["result_schemas"]["data_source_state"]["schema_version"],
                "data_source_state.v1",
            )
            self.assertEqual(manager_state["save_modes"]["schema_version"], "table_save_modes.v1")
            self.assertEqual(manager_state["save_modes"]["mode_field"]["choices_source"], "modes")
            self.assertEqual(manager_state["layout"]["schema_version"], "data_source_manager_layout.v1")
            self.assertEqual(manager_state["ui_hints"]["schema_version"], "data_source_manager_ui_hints.v1")
            self.assertEqual(manager.window.property("data_source_manager_layout_schema"), "data_source_manager_layout.v1")
            self.assertEqual(manager.window.property("data_source_manager_ui_hints_schema"), "data_source_manager_ui_hints.v1")
            self.assertEqual(manager.window.property("data_source_manager_default_section"), "table")
            self.assertEqual(manager.window.property("data_source_client_profiles_schema"), "data_source_client_profiles.v1")
            self.assertEqual(manager.window.property("data_source_transport_hints_schema"), "data_source_transport_hints.v1")
            self.assertEqual(manager.window.property("data_source_default_client_profile"), "stdio_desktop")
            self.assertEqual(manager.window.property("data_source_table_transfer_action"), "create_table_handle")
            self.assertEqual(manager.window.property("data_source_table_page_action"), "get_table_handle_page")
            self.assertEqual(manager.window.property("data_source_table_release_action"), "release_table_handle")
            self.assertEqual(manager.window.property("data_source_page_size_default"), 200)
            self.assertEqual(manager.page_size_spin.value(), 200)
            self.assertEqual(manager.save_button.property("data_source_action_id"), "save_sqlite")
            self.assertEqual(manager.save_button.property("data_source_section_id"), "save")
            self.assertEqual(manager.save_button.property("data_source_prominence"), "primary")
            self.assertEqual(manager.delete_table_button.property("data_source_prominence"), "danger")
            self.assertIn("协议动作：save_sqlite", manager.save_button.toolTip())
            self.assertIn("区域：保存", manager.save_button.toolTip())
            self.assertIn("服务动作：save_table", manager.save_button.toolTip())
            self.assertIn("警告：删除 SQLite 表需要确认", manager.delete_table_button.toolTip())
            self.assertIn("区域：表格", manager.table_view.toolTip())
            self.assertEqual(manager_state["source_controls"]["db_path"], db_path)
            self.assertIn("orders", manager_state["source_controls"]["table_names"])
            self.assertEqual(manager_state["source_controls"]["selected_table"], "orders")
            self.assertTrue(manager.clear_button.isEnabled())
            self.assertTrue(manager.promote_header_button.isEnabled())
            self.assertTrue(manager.search_button.isEnabled())
            self.assertTrue(manager.save_button.isEnabled())
            self.assertTrue(manager.delete_table_button.isEnabled())
            self.assertTrue(manager.apply_input_button.isEnabled())
            self.assertTrue(manager.edit_mode_checkbox.isEnabled())
            self.assertEqual((first_index.row(), first_index.column()), (1, 1))
            self.assertEqual((current_index.row(), current_index.column()), (2, 1))
            self.assertEqual(manager.search_status_label.text(), "2/2")
            self.assertIsNotNone(manager.table_model.data(manager.table_model.index(2, 1), background_role))
            self.assertEqual(controller.current_headers, ["id", "name"])
            self.assertEqual(controller.current_rows, [["1", "Alice"], ["2", "Bob"], ["3", "Bob Jr"]])
            self.assertEqual(controller.current_input_source["table_name"], "orders")
            self.assertEqual(controller.input_summary_label.text(), "当前输入：3 行 x 2 列")
            self.assertIn("数据源管理窗口", controller.status_bar.currentMessage())
            manager.window.close()
            window.close()
            app.processEvents()

    def test_data_source_manager_button_state_follows_panel_state(self):
        try:
            qt = qt_app.load_qt6()
        except QtBindingUnavailable as exc:
            self.skipTest(str(exc))
        app = qt.QtWidgets.QApplication.instance() or qt.QtWidgets.QApplication([])
        window = build_main_window(qt)
        controller = window.qt_workflow_controller
        controller.open_data_source_manager()
        manager = controller.data_source_manager_controller

        controller.engine_client.build_data_source_panel_state = lambda *args, **kwargs: {
            "ok": True,
            "panel_state": {
                "schema_version": "data_source_panel_state.v1",
                "view_state": {
                    "title": "后端状态",
                    "status_text": "后端状态：1 行 x 1 列，未保存",
                    "page_status_text": "后端分页文本",
                    "page_controls": {
                        "page_size_enabled": False,
                        "prev_enabled": True,
                        "next_enabled": False,
                        "load_full_enabled": True,
                    },
                    "action_enabled": {
                        "clear_table": False,
                        "promote_first_row": False,
                        "search_table": True,
                        "save_sqlite": True,
                        "apply_to_workflow": True,
                        "patch_cell": False,
                        "delete_sqlite": True,
                    },
                },
                "service": {"schema_version": "data_source_service.v1", "capabilities": {"panel_state": True}},
                "action_schema": {"schema_version": "data_source_action_schema.v1"},
                "save_modes": {"schema_version": "table_save_modes.v1", "mode_ids": ["replace"]},
            },
        }
        controller.engine_client.describe_data_source_actions = lambda *args, **kwargs: {
            "ok": True,
            "action_state": {
                "actions": {
                    "clear_table": {"enabled": True},
                    "promote_first_row": {"enabled": True},
                    "search_table": {"enabled": False},
                    "save_sqlite": {"enabled": False},
                    "apply_to_workflow": {"enabled": False},
                    "patch_cell": {"enabled": True},
                    "delete_sqlite": {"enabled": False},
                },
            },
            "action_schema": {},
        }
        manager.set_table(["A"], [["1"]], source={"type": "sqlite", "db_path": "demo.db", "table_name": "demo"}, dirty=True)
        manager._refresh_table_shape_status()
        manager._refresh_page_controls()
        manager._refresh_data_action_controls()

        self.assertEqual(manager.status_label.text(), "后端状态：1 行 x 1 列，未保存")
        self.assertEqual(manager.page_status_label.text(), "后端分页文本")
        self.assertFalse(manager.page_size_spin.isEnabled())
        self.assertTrue(manager.prev_page_button.isEnabled())
        self.assertFalse(manager.next_page_button.isEnabled())
        self.assertTrue(manager.load_full_table_button.isEnabled())
        self.assertFalse(manager.clear_button.isEnabled())
        self.assertFalse(manager.promote_header_button.isEnabled())
        self.assertTrue(manager.search_button.isEnabled())
        self.assertTrue(manager.save_button.isEnabled())
        self.assertTrue(manager.apply_input_button.isEnabled())
        self.assertFalse(manager.edit_mode_checkbox.isEnabled())
        self.assertTrue(manager.delete_table_button.isEnabled())
        self.assertEqual(manager.describe_state()["panel_state"]["view_state"]["action_enabled"]["save_sqlite"], True)
        window.close()
        app.processEvents()

    def test_data_source_manager_pages_sqlite_preview_and_applies_full_table(self):
        try:
            qt = qt_app.load_qt6()
        except QtBindingUnavailable as exc:
            self.skipTest(str(exc))
        app = qt.QtWidgets.QApplication.instance() or qt.QtWidgets.QApplication([])
        with TemporaryDirectory() as temp_dir:
            db_path = str(Path(temp_dir) / "input.db")
            rows = [[str(index), f"Item {index}"] for index in range(1, 6)]
            TableAccessManager(db_path).write_table(
                "orders",
                ["id", "name"],
                rows,
                mode="replace",
            )
            window = build_main_window(qt)
            controller = window.qt_workflow_controller

            controller.input_db_path_edit.setText(db_path)
            controller.apply_input_db_path_from_edit(show_status=False)
            controller.open_data_source_manager()
            manager = controller.data_source_manager_controller
            manager.refresh_table_combo()
            manager.table_combo.setCurrentText("orders")
            manager.page_size_spin.setValue(2)
            handle_calls = []
            original_create_handle = controller.engine_client.create_table_handle
            original_get_handle_page = controller.engine_client.get_table_handle_page
            original_release_handle = controller.engine_client.release_table_handle

            def record_create_handle(*args, **kwargs):
                handle_calls.append(("create", copy.deepcopy(kwargs)))
                return original_create_handle(*args, **kwargs)

            def record_get_handle_page(handle, *args, **kwargs):
                handle_calls.append(("page", handle, copy.deepcopy(kwargs)))
                return original_get_handle_page(handle, *args, **kwargs)

            def record_release_handle(handle):
                handle_calls.append(("release", handle))
                return original_release_handle(handle)

            controller.engine_client.create_table_handle = record_create_handle
            controller.engine_client.get_table_handle_page = record_get_handle_page
            controller.engine_client.release_table_handle = record_release_handle

            manager.load_selected_table()
            app.processEvents()

            self.assertTrue(manager.current_table_is_partial)
            self.assertEqual(handle_calls[0][0], "create")
            self.assertEqual(handle_calls[0][1]["source"]["type"], "sqlite")
            self.assertEqual(handle_calls[0][1]["limit"], 3)
            self.assertTrue(manager.current_table_handle)
            self.assertEqual(manager.current_table()["rows"], rows[:2])
            self.assertEqual(manager.current_source["type"], "sqlite")
            self.assertIn("第 1-2 行", manager.page_status_label.text())
            self.assertFalse(manager.save_button.isEnabled())
            self.assertFalse(manager.edit_mode_checkbox.isEnabled())
            self.assertFalse(manager.promote_header_button.isEnabled())
            self.assertTrue(manager.clear_button.isEnabled())
            self.assertTrue(manager.apply_input_button.isEnabled())
            self.assertTrue(manager.delete_table_button.isEnabled())
            self.assertTrue(manager.next_page_button.isEnabled())
            first_handle = manager.current_table_handle

            manager.goto_next_page()
            app.processEvents()

            self.assertEqual(handle_calls[1][0], "page")
            self.assertEqual(handle_calls[1][1], first_handle)
            self.assertEqual(handle_calls[1][2]["offset"], 2)
            self.assertEqual(manager.current_table_handle, first_handle)
            self.assertEqual(manager.page_offset, 2)
            self.assertEqual(manager.current_table()["rows"], rows[2:4])
            self.assertIn("第 3-4 行", manager.page_status_label.text())

            manager.apply_to_workflow()
            app.processEvents()

            self.assertIn(("release", first_handle), handle_calls)
            self.assertFalse(controller.engine_client.list_table_handles()["handles"])
            self.assertEqual(manager.current_table_handle, "")
            self.assertFalse(manager.current_table_is_partial)
            self.assertEqual(manager.current_table()["rows"], rows)
            self.assertEqual(controller.current_rows, rows)
            self.assertEqual(controller.input_summary_label.text(), "当前输入：5 行 x 2 列")
            self.assertIn("完整表", manager.status_label.text())
            manager.window.close()
            window.close()
            app.processEvents()

    def test_data_source_manager_remembers_database_and_syncs_input_combo(self):
        try:
            qt = qt_app.load_qt6()
        except QtBindingUnavailable as exc:
            self.skipTest(str(exc))
        app = qt.QtWidgets.QApplication.instance() or qt.QtWidgets.QApplication([])
        with TemporaryDirectory() as temp_dir:
            db_path = str(Path(temp_dir) / "input.db")
            TableAccessManager(db_path).write_table(
                "orders",
                ["id", "name"],
                [["1", "Alice"]],
                mode="replace",
            )
            window = build_main_window(qt)
            controller = window.qt_workflow_controller

            controller.open_data_source_manager()
            manager = controller.data_source_manager_controller
            manager.db_path_edit.setText(db_path)
            manager.refresh_table_combo()
            app.processEvents()

            self.assertEqual(controller.current_input_db_path, db_path)
            self.assertEqual(controller.input_db_path_edit.text(), db_path)
            self.assertEqual(controller.input_table_combo.currentText(), "orders")
            manager.window.close()

            controller.open_data_source_manager()
            reopened = controller.data_source_manager_controller
            app.processEvents()

            self.assertEqual(reopened.db_path_edit.text(), db_path)
            self.assertEqual(reopened.table_combo.currentText(), "orders")
            reopened.window.close()
            window.close()
            app.processEvents()

    def test_controller_job_context_and_logs_include_db_path_timestamp_and_elapsed(self):
        try:
            qt = qt_app.load_qt6()
        except QtBindingUnavailable as exc:
            self.skipTest(str(exc))
        app = qt.QtWidgets.QApplication.instance() or qt.QtWidgets.QApplication([])
        with TemporaryDirectory() as temp_dir:
            db_path = str(Path(temp_dir) / "input.db")
            window = build_main_window(qt)
            controller = window.qt_workflow_controller
            controller.current_input_db_path = db_path
            captured = {}

            def fake_start_job(job_action, plan, input_table=None, **options):
                captured["job_action"] = job_action
                captured["plan"] = copy.deepcopy(plan)
                captured["input_table"] = copy.deepcopy(input_table)
                captured["options"] = copy.deepcopy(options)
                return {"ok": True, "job_id": "job-test", "done": False, "status": "running"}

            def fake_get_job_events(job_id, since=0):
                return {
                    "ok": True,
                    "job_id": job_id,
                    "next_sequence": 2,
                    "events": [
                        {
                            "type": "node_done",
                            "message": "完成节点 1.新建列：1 行 × 2 列",
                            "elapsed_seconds": 2.36,
                            "timestamp": 1782196338.237,
                        },
                        {
                            "type": "workflow_done",
                            "rows": 1,
                            "cols": 2,
                            "elapsed_seconds": 3.5,
                            "timestamp": 1782196340.0,
                        },
                    ],
                }

            def fake_get_job_status(job_id, include_result=True):
                return {
                    "ok": True,
                    "job_id": job_id,
                    "done": True,
                    "status": "succeeded",
                    "message": "任务完成。",
                    "result": {
                        "table": {"headers": ["A", "B"], "rows": [["a", "b"]]},
                        "logs": [],
                        "steps": 1,
                    },
                }

            controller.engine_client.start_job = fake_start_job
            controller.engine_client.get_job_events = fake_get_job_events
            controller.engine_client.get_job_status = fake_get_job_status

            controller.start_workflow_job(
                "preview_plan",
                {"nodes": []},
                input_table={"headers": ["A"], "rows": [["a"]]},
                title="预览结果",
                status_prefix="预览",
            )
            app.processEvents()

            context = captured["options"]["context"]
            self.assertEqual(context["db_path"], db_path)
            self.assertEqual(context["workflow_snapshot"]["db_path"], db_path)
            logs = controller.log_text.toPlainText()
            self.assertRegex(logs, r"\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}\] \[INFO\]")
            self.assertIn("完成节点 1.新建列：1 行 × 2 列，耗时 2.36 秒", logs)
            self.assertIn("工作流完成：1 行 × 2 列，总耗时 3.50 秒", logs)
            window.close()
            app.processEvents()

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
        self.assertTrue(controller.node_type_combo.isHidden())
        self.assertTrue(controller.add_node_button.isHidden())
        self.assertGreater(controller.catalog_tree.topLevelItemCount(), 0)
        self.assertEqual(controller.node_list.count(), 1)
        self.assertIn("未保存", controller.status_bar.currentMessage())
        self.assertEqual(controller.output_mode_combo.itemText(0), "输出到主界面预览区")
        self.assertEqual(controller.output_mode_combo.currentText(), "输出到主界面预览区")
        self.assertEqual(controller.output_db_path_edit.text(), "")
        self.assertEqual(controller.output_path_edit.text(), "")
        self.assertEqual(controller.input_table_combo.count(), 0)
        self.assertFalse(controller.load_input_table_button.isEnabled())
        self.assertTrue(controller.data_source_manager_button.isEnabled())
        self.assertEqual(controller.node_tabs.count(), 2)
        self.assertEqual(controller.node_tabs.tabText(0), "节点配置")
        self.assertEqual(controller.node_tabs.tabText(1), "节点说明")
        self.assertEqual(controller.node_tabs.currentIndex(), 0)
        self.assertEqual(controller.result_tabs.count(), 3)
        self.assertEqual(controller.result_tabs.tabText(0), "预览")
        self.assertEqual(controller.result_tabs.tabText(1), "输出")
        self.assertEqual(controller.result_tabs.tabText(2), "消息")
        self.assertEqual(controller.result_tabs.currentIndex(), 0)
        self.assertEqual(controller.node_detail_title_label.text(), "新建列")
        self.assertIn("说明", controller.node_detail_sections.toPlainText())
        self.assertFalse(controller.output_form_fields["backup_before_overwrite"]["editor"].isVisible())
        self.assertTrue(controller.refresh_schema_button.isEnabled())
        self.assertTrue(controller.refresh_plugin_button.isEnabled())
        self.assertTrue(controller.apply_config_button.isEnabled())
        self.assertFalse(controller.cancel_job_button.isEnabled())

        with patch("ui_qt.main_window.QtWorkflowMainWindow._confirm_prompt", return_value=True):
            controller.show_input_table()
            self.assertEqual(controller.current_table_kind, "input")
            controller.add_node_by_type("core.replace")
            self.assertEqual(len(controller.current_plan["nodes"]), 2)
            self.assertTrue(controller.node_action_buttons["上移"].isEnabled())
            self.assertFalse(controller.node_action_buttons["下移"].isEnabled())
            controller.node_list.setCurrentRow(0)
            app.processEvents()
            self.assertFalse(controller.node_action_buttons["上移"].isEnabled())
            self.assertTrue(controller.node_action_buttons["下移"].isEnabled())
            controller.node_list.setCurrentRow(1)
            app.processEvents()
            self.assertTrue(controller.node_action_buttons["上移"].isEnabled())
            self.assertFalse(controller.node_action_buttons["下移"].isEnabled())
            self.assertEqual(controller.config_form.config_fields["target_field"]["action_button"].text(), "选择字段")
            self.assertTrue(controller.config_form.config_fields["match_value_field"]["label"].isHidden())
            controller.config_form.config_fields["match_value_source"]["editor"].setCurrentText("列字段")
            app.processEvents()
            self.assertFalse(controller.config_form.config_fields["match_value_field"]["label"].isHidden())
            controller.node_tabs.setCurrentIndex(1)
            controller.show_node_detail("core.replace")
            self.assertEqual(controller.node_tabs.currentIndex(), 1)
            self.assertEqual(controller.node_detail_title_label.text(), "批量替换")
            self.assertIn("注意", controller.node_detail_sections.toPlainText())
            self.assertIn("结构化警告", controller.node_detail_sections.toPlainText())
            self.assertIn("配置项", controller.node_detail_sections.toPlainText())
            self.assertIn("配置提示", controller.node_detail_sections.toPlainText())
            self.assertIn("动态显示", controller.node_detail_sections.toPlainText())
            controller._apply_node_detail_panel(
                {"title": "高级筛选"},
                schema={"node_type_id": "core.filter", "display_name": "高级筛选"},
                context={
                    "shared_config_sections": [{
                        "title": "共享配置状态",
                        "lines": ["可用字段：2 个", "实际输出字段：A、B", "状态：当前多表筛选未发现明显全组合风险。"],
                    }]
                },
            )
            self.assertIn("共享配置状态", controller.node_detail_sections.toPlainText())
            self.assertIn("实际输出字段：A、B", controller.node_detail_sections.toPlainText())
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
            self.assertEqual(controller.result_tabs.tabText(controller.result_tabs.currentIndex()), "消息")
            self.assertEqual(controller.message_tabs.tabText(controller.message_tabs.currentIndex()), "问题")
            self.assertIn("节点配置校验失败", controller.info_text.toPlainText())
            self.assertIn("√", controller.node_action_buttons["启用/禁用"].accessibleName())
            controller.toggle_selected_node_enabled()
            self.assertFalse(controller.current_plan["nodes"][controller.selected_node_index()].get("enabled", True))
            self.assertIn("×", controller.node_action_buttons["启用/禁用"].accessibleName())
            controller.toggle_selected_node_enabled()
            self.assertIn("√", controller.node_action_buttons["启用/禁用"].accessibleName())
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
            self.assertEqual(controller.result_tabs.tabText(controller.result_tabs.currentIndex()), "消息")
            controller.node_list.setCurrentRow(0)
            controller.preview_to_selected_node()
            self.wait_for_controller_job(app, controller)
            self.assertEqual(controller.result_tabs.tabText(controller.result_tabs.currentIndex()), "预览")
            self.assertEqual(controller.current_table_kind, "preview")
            self.assertIn("status", controller.last_preview_headers)
            self.assertEqual(controller.workflow_progress.value(), 100)
            self.assertFalse(controller.cancel_job_button.isEnabled())
            controller.execute_plan()
            self.wait_for_controller_job(app, controller)
            self.assertEqual(controller.result_tabs.tabText(controller.result_tabs.currentIndex()), "预览")
            self.assertEqual(controller.current_table_kind, "preview")
            self.assertIn("status", controller.last_preview_headers)
            self.assertTrue(controller.table_title.text().startswith("执行结果"))
            controller.show_preview_table()
            self.assertEqual(controller.current_table_kind, "preview")
            controller.output_mode_combo.setCurrentText("保存为SQLite新表")
            app.processEvents()
            window.show()
            app.processEvents()
            controller.result_tabs.setCurrentIndex(1)
            app.processEvents()
            self.assertTrue(controller.output_form_fields["target"]["editor"].isVisible())
            self.assertTrue(controller.output_form_fields["db_path"]["editor"].isVisible())
            self.assertTrue(controller.output_form_fields["db_path"]["action_button"].isVisible())
            controller.execute_plan()
            self.wait_for_controller_job(app, controller)
            self.assertTrue(controller.table_title.text().startswith("执行结果（输出未落地）"))
            self.assertIn("missing_db_path", controller.issue_text.toPlainText())
            self.assertEqual(controller.result_tabs.tabText(controller.result_tabs.currentIndex()), "预览")
            controller.show_log_text()
            self.assertEqual(controller.result_tabs.tabText(controller.result_tabs.currentIndex()), "消息")
            self.assertEqual(controller.message_tabs.tabText(controller.message_tabs.currentIndex()), "日志")
            self.assertIn("输出设置校验失败", controller.status_bar.currentMessage())
            settings = controller.current_output_settings()
            self.assertEqual(settings["mode"], "保存为SQLite新表")

    def test_controller_uses_preview_cache_for_next_node_config_fields(self):
        try:
            qt = qt_app.load_qt6()
        except QtBindingUnavailable as exc:
            self.skipTest(str(exc))
        app = qt.QtWidgets.QApplication.instance() or qt.QtWidgets.QApplication([])
        controller = QtWorkflowMainWindow(qt)
        plan = {
            "headers": ["A"],
            "rows": [["a"]],
            "nodes": [
                {
                    "node_type_id": "core.new_columns",
                    "name": "生成字段",
                    "enabled": True,
                    "config": {"columns_text": "Generated=1", "conflict_mode": "自动改名"},
                },
                {
                    "node_type_id": "core.replace",
                    "name": "使用生成字段",
                    "enabled": True,
                    "config": {
                        "target_field": "A",
                        "match_mode": "包含",
                        "replace_mode": "局部替换匹配字符串",
                        "match_value_source": "手动输入",
                        "match_value": "a",
                        "replace_value_source": "手动输入",
                        "replace_value": "b",
                    },
                },
            ],
        }
        controller.current_plan = copy.deepcopy(plan)
        controller.current_headers = ["A"]
        controller.current_rows = [["a"]]
        controller.node_config_preview_cache = build_preview_context_cache(
            plan=plan,
            stop_index=0,
            headers=["A", "Generated"],
            rows=[["a", "g"]],
        )
        captured_headers = []
        original_schema = controller.engine_client.get_node_ui_schema

        def fake_get_node_ui_schema(node_type_id, **kwargs):
            if node_type_id == "core.replace":
                captured_headers.append(list(kwargs.get("preview_headers") or []))
            return original_schema(node_type_id, **kwargs)

        def fail_start_job(*args, **kwargs):
            raise AssertionError("opening node config must not start a workflow job")

        controller.engine_client.get_node_ui_schema = fake_get_node_ui_schema
        controller.engine_client.start_job = fail_start_job

        controller.refresh_all(selected_index=1)
        app.processEvents()

        target_editor = controller.config_form.config_fields["target_field"]["editor"]
        choices = [target_editor.itemText(i) for i in range(target_editor.count())]
        self.assertIn(["A", "Generated"], captured_headers)
        self.assertIn("Generated", choices)
        self.assertFalse(controller.current_job_id)

    def test_controller_feedback_uses_structured_validation_sections(self):
        try:
            qt = qt_app.load_qt6()
        except QtBindingUnavailable as exc:
            self.skipTest(str(exc))
        app = qt.QtWidgets.QApplication.instance() or qt.QtWidgets.QApplication([])
        controller = QtWorkflowMainWindow(qt)

        feedback = controller.engine_client.describe_validation_feedback({
            "ok": True,
            "validation": {"ok": True, "node_count": 1, "issues": []},
            "jump_validation": {"issues": [], "summary": "跳转链路正常"},
            "access_precheck": {
                "issues": [{"severity": "warning", "code": "demo", "message": "将写回数据库"}],
                "summary": "存在写回风险，请确认目标表",
            },
        })

        controller._apply_feedback(feedback)

        self.assertIn("校验发现提示", controller.info_text.toPlainText())
        self.assertIn("基础校验", controller.info_text.toPlainText())
        self.assertIn("存在写回风险，请确认目标表", controller.info_text.toPlainText())
        self.assertIn("将写回数据库", controller.issue_text.toPlainText())
        self.assertEqual(controller.result_tabs.tabText(controller.result_tabs.currentIndex()), "消息")
        self.assertEqual(controller.message_tabs.tabText(controller.message_tabs.currentIndex()), "问题")

    def test_controller_uses_confirmation_prompts_for_clear_and_run(self):
        try:
            qt = qt_app.load_qt6()
        except QtBindingUnavailable as exc:
            self.skipTest(str(exc))
        app = qt.QtWidgets.QApplication.instance() or qt.QtWidgets.QApplication([])
        window = build_main_window(qt)
        controller = window.qt_workflow_controller
        window.show()
        app.processEvents()

        with patch("ui_qt.main_window.QtWorkflowMainWindow._confirm_prompt", return_value=False) as mock_confirm:
            controller.clear_nodes()
            self.assertEqual(len(controller.current_plan["nodes"]), 1)
            self.assertTrue(mock_confirm.called)

        with patch("ui_qt.main_window.QtWorkflowMainWindow._confirm_prompt", return_value=False) as mock_confirm:
            controller.output_mode_combo.setCurrentText("覆盖当前表")
            app.processEvents()
            controller.execute_plan()
            self.assertTrue(mock_confirm.called)
            self.assertEqual(controller.status_bar.currentMessage(), "已取消执行")

        with patch.object(controller, "refresh_preview_table_combo") as mock_refresh:
            controller.output_mode_combo.setCurrentText("保存为SQLite新表")
            app.processEvents()
            self.assertTrue(mock_refresh.called)

        window.close()
        app.processEvents()

    def test_controller_passes_table_context_to_forms_and_detail(self):
        try:
            qt = qt_app.load_qt6()
        except QtBindingUnavailable as exc:
            self.skipTest(str(exc))
        app = qt.QtWidgets.QApplication.instance() or qt.QtWidgets.QApplication([])
        window = build_main_window(qt)
        controller = window.qt_workflow_controller
        controller.output_db_path_edit.setText("demo.db")

        with patch.object(controller.engine_client, "list_tables", return_value={
            "tables": [
                {"name": "orders", "headers": ["id", "name"]},
                {"name": "logs", "headers": ["row_id"]},
            ]
        }) as mock_list_tables, patch.object(controller.engine_client, "describe_node_detail", wraps=controller.engine_client.describe_node_detail) as mock_describe_detail:
            controller.refresh_catalog()
            controller.show_node_detail("core.replace")
            controller.show_node_config(0)

        self.assertTrue(mock_list_tables.called)
        self.assertEqual(controller.config_form.table_names, ["orders", "logs"])
        self.assertEqual(controller.config_form.plan.get("nodes"), controller.current_plan.get("nodes"))
        self.assertEqual(mock_describe_detail.call_args.kwargs["table_names"], ["orders", "logs"])
        self.assertEqual(mock_describe_detail.call_args.kwargs["table_columns"], {"orders": ["id", "name"], "logs": ["row_id"]})
        window.close()
        app.processEvents()

    def test_controller_handles_table_field_picker_actions(self):
        try:
            qt = qt_app.load_qt6()
        except QtBindingUnavailable as exc:
            self.skipTest(str(exc))
        app = qt.QtWidgets.QApplication.instance() or qt.QtWidgets.QApplication([])
        window = build_main_window(qt)
        controller = window.qt_workflow_controller

        controller.config_form.set_node(
            {
                "node_type_id": "demo.lookup_field_picker",
                "node_id": "n1",
                "name": "表字段选择",
                "enabled": True,
                "node_version": "1.0.0",
                "config": {
                    "lookup_table": "orders",
                    "lookup_fields": ["id"],
                },
            },
            table_names=["orders"],
            table_columns={"orders": ["id", "name"]},
            schema={
                "form": {
                    "groups": [
                        {
                            "title": "参数",
                            "fields": [
                                {
                                    "key": "lookup_table",
                                    "type": "table_select",
                                    "options_source": {"type": "table_names"},
                                },
                                {
                                    "key": "lookup_fields",
                                    "type": "field_multi_select",
                                    "options_source": {"type": "table_columns", "table_field": "lookup_table"},
                                },
                            ],
                        }
                    ]
                }
            },
        )

        with patch.object(controller.qt.QtWidgets.QDialog, "exec", return_value=int(controller.qt.QtWidgets.QDialog.DialogCode.Accepted)):
            result = controller._pick_multi_table_fields_for_field(
                "lookup_fields",
                {
                    "action": {"key": "pick_table_fields", "table_field": "lookup_table"},
                    "schema": {"options_source": {"type": "table_columns", "table_field": "lookup_table"}},
                    "table_columns": {"orders": ["id", "name"]},
                    "value": ["id"],
                },
            )

        self.assertEqual(result["value"], ["id"])
        window.close()
        app.processEvents()

    def test_controller_picks_multi_table_names(self):
        try:
            qt = qt_app.load_qt6()
        except QtBindingUnavailable as exc:
            self.skipTest(str(exc))
        app = qt.QtWidgets.QApplication.instance() or qt.QtWidgets.QApplication([])

        window = build_main_window(qt)
        controller = window.qt_workflow_controller

        with patch.object(controller.qt.QtWidgets.QDialog, "exec", return_value=int(controller.qt.QtWidgets.QDialog.DialogCode.Accepted)):
            result = controller._pick_multi_tables_for_field(
                "extra_tables",
                {
                    "action": {"key": "pick_table_names"},
                    "table_names": ["orders", "logs"],
                    "value": ["orders"],
                },
            )

        self.assertEqual(result["value"], ["orders"])
        window.close()
        app.processEvents()

    def test_controller_uses_shared_table_picker_context(self):
        try:
            qt = qt_app.load_qt6()
        except QtBindingUnavailable as exc:
            self.skipTest(str(exc))
        app = qt.QtWidgets.QApplication.instance() or qt.QtWidgets.QApplication([])

        window = build_main_window(qt)
        controller = window.qt_workflow_controller

        with patch.object(controller.qt.QtWidgets.QInputDialog, "getItem", return_value=("logs", True)):
            result = controller._pick_single_table_for_field(
                "lookup_table",
                {
                    "action": {"key": "pick_table_name"},
                    "table_names": ["orders", "logs"],
                    "value": "orders",
                },
            )

        self.assertEqual(result["value"], "logs")

        controller.config_form.set_node(
            {
                "node_type_id": "demo.lookup_field_picker",
                "node_id": "n1",
                "name": "表字段选择",
                "enabled": True,
                "node_version": "1.0.0",
                "config": {
                    "lookup_table": "orders",
                    "lookup_field": "id",
                },
            },
            table_names=["orders", "logs"],
            table_columns={"orders": ["id", "name"], "logs": ["row_id"]},
            schema={
                "form": {
                    "groups": [
                        {
                            "title": "参数",
                            "fields": [
                                {"key": "lookup_table", "type": "table_select", "options_source": {"type": "table_names"}},
                                {"key": "lookup_field", "type": "field_select", "options_source": {"type": "table_columns", "table_field": "lookup_table"}},
                            ],
                        }
                    ]
                }
            },
        )

        with patch.object(controller.qt.QtWidgets.QInputDialog, "getItem", return_value=("name", True)):
            result = controller._pick_single_table_field_for_field(
                "lookup_field",
                {
                    "action": {"key": "pick_table_field", "table_field": "lookup_table"},
                    "schema": {"options_source": {"type": "table_columns", "table_field": "lookup_table"}},
                    "table_columns": {"orders": ["id", "name"], "logs": ["row_id"]},
                    "value": "id",
                },
            )

        self.assertEqual(result["value"], "name")
        window.close()
        app.processEvents()

    def test_config_form_uses_plan_reference_choices(self):
        try:
            qt = qt_app.load_qt6()
        except QtBindingUnavailable as exc:
            self.skipTest(str(exc))
        app = qt.QtWidgets.QApplication.instance() or qt.QtWidgets.QApplication([])

        form = NodeConfigForm(qt, plan={
            "nodes": [
                {"node_type_id": "core.loop_start", "config": {"loop_id": "Loop_A"}},
                {"node_type_id": "core.jump_anchor", "config": {"anchor_id": "ANCHOR_END"}},
            ]
        })
        schema = {
            "form": {
                "groups": [
                    {
                        "title": "参数",
                        "fields": [
                            {
                                "key": "loop_id",
                                "label": "循环 ID",
                                "type": "select",
                                "options_source": {"type": "plan_refs", "ref_kind": "loop_id"},
                                "action": {"key": "pick_plan_ref", "label": "选择循环", "ref_kind": "loop_id"},
                            },
                            {
                                "key": "jump_rules",
                                "label": "跳转规则",
                                "type": "structured_list",
                                "item_schema": {
                                    "type": "object",
                                    "columns": [
                                        {"key": "value", "label": "值", "type": "text"},
                                        {
                                            "key": "target_anchor_id",
                                            "label": "目标锚点",
                                            "type": "select",
                                            "options_source": {"type": "plan_refs", "ref_kind": "anchor_id"},
                                            "action": {"key": "pick_plan_ref", "label": "选择锚点", "ref_kind": "anchor_id"},
                                        },
                                    ],
                                },
                            },
                        ],
                    }
                ]
            }
        }
        form.set_node(
            {
                "node_type_id": "core.loop_judge",
                "node_id": "n1",
                "name": "循环判断",
                "enabled": True,
                "node_version": "1.0.0",
                "config": {
                    "loop_id": "",
                    "jump_rules": [{"value": "TRUE", "target_anchor_id": ""}],
                },
            },
            schema=schema,
        )

        loop_editor = form.config_fields["loop_id"]["editor"]
        loop_values = [loop_editor.itemText(i) for i in range(loop_editor.count())]
        self.assertIn("Loop_A", loop_values)

        jump_editor = form.config_fields["jump_rules"]["editor"]
        table = jump_editor.structured_state["table"]
        cell_widget = form._structured_cell_widget(
            table.cellWidget(0, 1),
            {"key": "target_anchor_id", "type": "select"},
        )
        anchor_values = [cell_widget.itemText(i) for i in range(cell_widget.count())]
        self.assertIn("ANCHOR_END", anchor_values)
        app.processEvents()

    def test_config_form_uses_runtime_reference_choices(self):
        try:
            qt = qt_app.load_qt6()
        except QtBindingUnavailable as exc:
            self.skipTest(str(exc))
        app = qt.QtWidgets.QApplication.instance() or qt.QtWidgets.QApplication([])

        form = NodeConfigForm(qt, plan={
            "nodes": [
                {"node_type_id": "core.save_transit", "config": {"transit_name": "中转A"}},
                {"node_type_id": "core.group", "config": {"save_to_transit": True, "output_transit_name": "组输出B"}},
            ]
        })
        schema = {
            "form": {
                "groups": [
                    {
                        "title": "参数",
                        "fields": [
                            {
                                "key": "transit_table",
                                "label": "中转表",
                                "type": "select",
                                "options_source": {"type": "runtime_refs", "ref_kind": "transit_table"},
                                "action": {"key": "pick_runtime_ref", "label": "选择中转表", "ref_kind": "transit_table"},
                            },
                            {
                                "key": "links",
                                "label": "关联",
                                "type": "structured_list",
                                "item_schema": {
                                    "type": "object",
                                    "columns": [
                                        {
                                            "key": "target_transit_table",
                                            "label": "目标中转表",
                                            "type": "select",
                                            "options_source": {"type": "runtime_refs", "ref_kind": "transit_table"},
                                            "action": {"key": "pick_runtime_ref", "label": "选择中转表", "ref_kind": "transit_table"},
                                        }
                                    ],
                                },
                            },
                        ],
                    }
                ]
            }
        }
        form.set_node(
            {
                "node_type_id": "core.loop_start",
                "node_id": "n1",
                "name": "循环起点",
                "enabled": True,
                "node_version": "1.0.0",
                "config": {
                    "transit_table": "",
                    "links": [{"target_transit_table": ""}],
                },
            },
            schema=schema,
        )

        transit_editor = form.config_fields["transit_table"]["editor"]
        transit_values = [transit_editor.itemText(i) for i in range(transit_editor.count())]
        self.assertIn("中转A", transit_values)
        self.assertIn("组输出B", transit_values)

        links_editor = form.config_fields["links"]["editor"]
        table = links_editor.structured_state["table"]
        cell_widget = form._structured_cell_widget(
            table.cellWidget(0, 0),
            {"key": "target_transit_table", "type": "select"},
        )
        link_values = [cell_widget.itemText(i) for i in range(cell_widget.count())]
        self.assertIn("中转A", link_values)
        self.assertIn("组输出B", link_values)
        app.processEvents()

    def test_config_form_uses_shared_picker_context_for_table_and_field_values(self):
        try:
            qt = qt_app.load_qt6()
        except QtBindingUnavailable as exc:
            self.skipTest(str(exc))
        app = qt.QtWidgets.QApplication.instance() or qt.QtWidgets.QApplication([])

        schema = {
            "form": {
                "groups": [
                    {
                        "title": "参数",
                        "fields": [
                            {
                                "key": "lookup_table",
                                "label": "查找表",
                                "type": "select",
                                "options_source": {"type": "table_names"},
                            },
                            {
                                "key": "lookup_field",
                                "label": "查找字段",
                                "type": "select",
                                "options_source": {"type": "table_columns", "table_field": "lookup_table"},
                            },
                            {
                                "key": "extra_tables",
                                "label": "附加表",
                                "type": "field_multi_select",
                                "options_source": {"type": "table_names"},
                            },
                            {
                                "key": "right_table",
                                "label": "右表",
                                "type": "select",
                                "options_source": {"type": "field_values", "field": "extra_tables", "value_kind": "table_names"},
                            },
                        ],
                    }
                ]
            }
        }

        form = NodeConfigForm(qt)
        form.set_node(
            {
                "node_type_id": "demo.shared_context",
                "node_id": "n1",
                "name": "共享候选",
                "enabled": True,
                "node_version": "1.0.0",
                "config": {
                    "lookup_table": "orders",
                    "lookup_field": "id",
                    "extra_tables": ["logs", "archive"],
                    "right_table": "logs",
                },
            },
            table_names=["orders", "logs", "archive"],
            table_columns={"orders": ["id", "name"], "logs": ["row_id"], "archive": ["archived_at"]},
            schema=schema,
        )

        lookup_table = form.config_fields["lookup_table"]["editor"]
        lookup_field = form.config_fields["lookup_field"]["editor"]
        right_table = form.config_fields["right_table"]["editor"]

        self.assertIn("orders", [lookup_table.itemText(i) for i in range(lookup_table.count())])
        self.assertEqual([lookup_field.itemText(i) for i in range(lookup_field.count())], ["id", "name"])
        self.assertEqual([right_table.itemText(i) for i in range(right_table.count())], ["logs", "archive"])
        app.processEvents()

    def test_controller_handles_plan_reference_picker_actions(self):
        try:
            qt = qt_app.load_qt6()
        except QtBindingUnavailable as exc:
            self.skipTest(str(exc))
        app = qt.QtWidgets.QApplication.instance() or qt.QtWidgets.QApplication([])
        window = build_main_window(qt)
        controller = window.qt_workflow_controller
        controller.plan = {
            "nodes": [
                {"node_type_id": "core.loop_start", "config": {"loop_id": "Loop_A"}},
                {"node_type_id": "core.loop_start", "config": {"loop_id": "Loop_B"}},
                {"node_type_id": "core.jump_anchor", "config": {"anchor_id": "ANCHOR_X"}},
            ]
        }

        with patch.object(controller.qt.QtWidgets.QInputDialog, "getItem", return_value=("Loop_A", True)):
            result = controller._pick_plan_reference_for_field(
                "loop_id",
                {
                    "action": {"key": "pick_plan_ref", "ref_kind": "loop_id"},
                    "plan_refs": [],
                    "value": "Loop_B",
                },
            )
        self.assertEqual(result["value"], "Loop_A")

        no_result = controller._pick_plan_reference_for_field(
            "default_anchor_id",
            {
                "action": {"key": "pick_plan_ref", "ref_kind": "anchor_id"},
                "plan_refs": [],
                "value": "",
            },
        )
        self.assertEqual(no_result["value"], "ANCHOR_X")

        controller.plan = {"nodes": []}
        no_result = controller._pick_plan_reference_for_field(
            "default_anchor_id",
            {
                "action": {"key": "pick_plan_ref", "ref_kind": "anchor_id"},
                "plan_refs": [],
                "value": "",
            },
        )
        self.assertEqual(no_result, {})
        self.assertIn("计划引用选择", controller.info_text.toPlainText())
        self.assertIn("请先添加对应节点或填写自定义值", controller.issue_text.toPlainText())
        window.close()
        app.processEvents()

    def test_controller_handles_runtime_reference_picker_actions(self):
        try:
            qt = qt_app.load_qt6()
        except QtBindingUnavailable as exc:
            self.skipTest(str(exc))
        app = qt.QtWidgets.QApplication.instance() or qt.QtWidgets.QApplication([])
        window = build_main_window(qt)
        controller = window.qt_workflow_controller
        controller.plan = {
            "nodes": [
                {"node_type_id": "core.save_transit", "config": {"transit_name": "中转A"}},
                {"node_type_id": "core.group", "config": {"save_to_transit": True, "output_transit_name": "组输出B"}},
            ]
        }

        with patch.object(controller.qt.QtWidgets.QInputDialog, "getItem", return_value=("中转A", True)):
            result = controller._pick_runtime_reference_for_field(
                "transit_table",
                {
                    "action": {"key": "pick_runtime_ref", "ref_kind": "transit_table"},
                    "runtime_refs": [],
                    "value": "组输出B",
                },
            )
        self.assertEqual(result["value"], "中转A")

        with patch.object(controller.qt.QtWidgets.QInputDialog, "getItem", return_value=("中转A", True)):
            no_result = controller._pick_runtime_reference_for_field(
                "transit_table",
                {
                    "action": {"key": "pick_runtime_ref", "ref_kind": "transit_table"},
                    "runtime_refs": [],
                    "value": "",
                },
            )
        self.assertEqual(no_result["value"], "中转A")

        controller.plan = {"nodes": []}
        no_result = controller._pick_runtime_reference_for_field(
            "transit_table",
            {
                "action": {"key": "pick_runtime_ref", "ref_kind": "transit_table"},
                "runtime_refs": [],
                "value": "",
            },
        )
        self.assertEqual(no_result, {})
        self.assertIn("运行时引用选择", controller.info_text.toPlainText())
        self.assertIn("请先配置相关节点或填写自定义值", controller.issue_text.toPlainText())
        window.close()
        app.processEvents()

    def test_controller_uses_facade_file_actions_for_import_open_and_save(self):
        try:
            qt = qt_app.load_qt6()
        except QtBindingUnavailable as exc:
            self.skipTest(str(exc))
        app = qt.QtWidgets.QApplication.instance() or qt.QtWidgets.QApplication([])
        window = build_main_window(qt)
        controller = window.qt_workflow_controller
        window.show()
        app.processEvents()

        import_path = str(Path("demo.csv"))
        plan_path = str(Path("plan") / "demo.json")
        save_path = str(Path("plan") / "saved.json")

        with patch("ui_qt.main_window.QtWorkflowMainWindow._choose_file_path", side_effect=[import_path, plan_path, save_path]) as mock_choose:
            with patch.object(controller.engine_client, "import_table_file", return_value={
                "ok": True,
                "path": import_path,
                "table": {"headers": ["A"], "rows": [["a"]]},
            }):
                controller.import_table()
                self.assertEqual(controller.current_headers, ["A"])
                self.assertEqual(controller.current_rows, [["a"]])

            with patch.object(controller.engine_client, "load_plan_template", return_value={
                "ok": True,
                "path": plan_path,
                "plan": {
                    **SAMPLE_PLAN,
                    "input_source": {"type": "sqlite", "db_path": "input.db", "table_name": "orders"},
                    "input_db_path": "input.db",
                },
                "warning": "已打开测试计划",
            }):
                controller.open_plan()
                self.assertTrue(str(controller.current_plan_path).endswith("demo.json"))
                self.assertEqual(controller.current_input_db_path, "input.db")
                self.assertEqual(controller.input_db_path_edit.text(), "input.db")
                self.assertEqual(controller.current_input_source["table_name"], "orders")
                self.assertIn("打开计划", controller.info_text.toPlainText())
                self.assertIn("已打开测试计划", controller.current_message_panel.get("body", ""))

            with patch.object(controller.engine_client, "save_plan_template", return_value={
                "ok": True,
                "path": save_path,
                "plan": SAMPLE_PLAN,
            }) as mock_save:
                controller.current_plan_path = None
                controller.save_plan()
                self.assertTrue(str(controller.current_plan_path).endswith("saved.json"))
                save_kwargs = mock_save.call_args[1]
                self.assertEqual(save_kwargs["input_db_path"], "input.db")
                self.assertEqual(save_kwargs["input_source"]["table_name"], "orders")
                self.assertIn("已保存", controller.status_bar.currentMessage())

            self.assertEqual(mock_choose.call_count, 3)

        window.close()
        app.processEvents()
        window.close()
        app.processEvents()

    def test_controller_uses_shared_template_list_state(self):
        try:
            qt = qt_app.load_qt6()
        except QtBindingUnavailable as exc:
            self.skipTest(str(exc))
        app = qt.QtWidgets.QApplication.instance() or qt.QtWidgets.QApplication([])
        window = build_main_window(qt)
        controller = window.qt_workflow_controller
        window.show()
        app.processEvents()

        with patch.object(controller.engine_client, "list_plan_templates", return_value={
            "templates": [
                {"name": "Alpha", "path": "plan\\alpha.json"},
                {"name": "Beta", "path": "plan\\beta.json"},
            ]
        }):
            controller.refresh_template_list(show_status=True)

        self.assertEqual(controller.plan_template_combo.count(), 2)
        self.assertEqual(controller.plan_template_combo.itemText(0), "Alpha")
        self.assertEqual(controller.status_bar.currentMessage(), "模板刷新完成：2 个。")
        self.assertEqual(controller.current_message_panel.get("title"), "计划模板")
        self.assertIn("Alpha", controller.info_text.toPlainText())

        window.close()
        app.processEvents()


if __name__ == "__main__":
    unittest.main()
