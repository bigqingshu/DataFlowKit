# -*- coding: utf-8 -*-
import tempfile
import unittest
from pathlib import Path

from engine.plugin_service import PluginService


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PLUGINS_DIR = PROJECT_ROOT / "plugins"
FIELD_SELECT_EMPTY_TEXT = "当前输入表没有可选字段"
FIELD_SELECT_INVALID_TEXT = "当前字段不在输入表字段中，仍会保留原值"


class PluginParameterMetadataTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(dir=PROJECT_ROOT)
        self.service = PluginService(plugins_dir=str(PLUGINS_DIR), app_dir=self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def _schema(self, plugin_id):
        result = self.service.get_plugin_schema(plugin_id)
        self.assertTrue(result["ok"], result)
        return result["schema"]

    def _fields(self, schema):
        return {
            field["key"]: field
            for group in schema["form"]["groups"]
            for field in group.get("fields", [])
        }

    def _group_titles(self, schema):
        return [group["title"] for group in schema["form"]["groups"]]

    def _assert_parameter_metadata_quality_gate(self, plugin_id):
        schema = self._schema(plugin_id)
        all_fields = self._fields(schema)
        metadata = schema["parameter_metadata"]
        metadata_fields = {
            field["key"]: field
            for field in metadata.get("fields", [])
        }
        fields = {
            key: field
            for key, field in all_fields.items()
            if key in metadata_fields
        }

        self.assertEqual(metadata["schema_version"], "plugin_parameters.v1")
        self.assertEqual(metadata["field_count"], len(fields))
        self.assertEqual(set(metadata["field_index"].keys()), set(fields.keys()))
        self.assertEqual(set(metadata_fields.keys()), set(fields.keys()))
        self.assertEqual(metadata["layout_index"]["schema_version"], "plugin_parameter_layout.v1")
        self.assertEqual(metadata["ui_hints"]["schema_version"], "plugin_parameter_ui_hints.v1")
        self.assertEqual(set(metadata["layout_index"]["field_order"]), set(fields.keys()))
        self.assertEqual(
            metadata["layout_index"]["group_order"],
            [group["group_key"] for group in metadata["layout_index"]["groups"]],
        )

        for key, field in fields.items():
            field_type = str(field.get("type") or "")
            if field_type in {"field_select", "table_select", "dynamic_select"}:
                self.assertIn("options_source", field, key)
                self.assertIn("empty_text", field, key)
                self.assertTrue(str(field["empty_text"]).strip(), key)
            if field_type == "field_select":
                self.assertIn("invalid_value_text", field, key)
                self.assertTrue(str(field["invalid_value_text"]).strip(), key)

            for meta_key in ("depends_on", "refresh_on_change"):
                for dependency in field.get(meta_key) or []:
                    self.assertTrue(str(dependency).startswith("params."), (key, meta_key, dependency))

            for meta_key in ("visible_when", "enabled_when"):
                self._assert_condition_uses_parameter_keys(field.get(meta_key), field_key=key)

        for source_type, detail in (metadata.get("options_source_details") or {}).items():
            self.assertTrue(detail.get("field_keys"), source_type)
            self.assertGreaterEqual(detail.get("field_count", 0), len(detail.get("field_keys") or []))
            for field_key in detail.get("field_keys") or []:
                self.assertIn(field_key, fields)

        for source_type, entries in (metadata.get("options_source_index") or {}).items():
            self.assertTrue(entries, source_type)
            for entry in entries:
                self.assertIn(entry.get("field_key"), fields)

    def _assert_condition_uses_parameter_keys(self, condition, *, field_key):
        if not condition:
            return
        if isinstance(condition, dict):
            if "field" in condition:
                self.assertTrue(
                    str(condition.get("field") or "").startswith("params."),
                    (field_key, condition),
                )
            for item in condition.get("all") or []:
                self._assert_condition_uses_parameter_keys(item, field_key=field_key)
            for item in condition.get("any") or []:
                self._assert_condition_uses_parameter_keys(item, field_key=field_key)

    def test_parameter_metadata_quality_gate_for_multi_ui_clients(self):
        for plugin_id in (
            "plugin.example_cached_plugin",
            "plugin.word_excel_read_to_db_v1",
            "plugin.word_excel_write_from_table_v2",
            "plugin.visual_mapping_write_plan_v1",
        ):
            with self.subTest(plugin_id=plugin_id):
                self._assert_parameter_metadata_quality_gate(plugin_id)

    def test_word_excel_reader_parameter_metadata_is_ui_ready(self):
        schema = self._schema("plugin.word_excel_read_to_db_v1")
        fields = self._fields(schema)
        group_titles = self._group_titles(schema)

        self.assertIn("插件参数 / 读取设置", group_titles)
        self.assertIn("插件参数 / 文件来源", group_titles)
        self.assertIn("插件参数 / 写库设置", group_titles)
        self.assertIn("插件参数 / 缓存与失败处理", group_titles)
        self.assertIn("高级参数 / 读取设置", group_titles)
        self.assertLess(group_titles.index("插件参数 / 文件来源"), group_titles.index("插件参数 / 写库设置"))
        self.assertLess(group_titles.index("插件参数 / 写库设置"), group_titles.index("插件参数 / 缓存与失败处理"))

        self.assertEqual(fields["params.read_engine"]["refresh_on_change"], ["params.read_engine"])
        self.assertEqual(fields["params.word_merge_mode"]["visible_when"]["field"], "params.read_engine")
        self.assertEqual(fields["params.word_merge_mode"]["visible_when"]["equals"], "win32")
        self.assertEqual(fields["params.doc_read_strategy"]["visible_when"]["field"], "params.read_engine")
        self.assertEqual(fields["params.doc_read_strategy"]["depends_on"], ["params.read_engine"])
        self.assertEqual(fields["params.path_source"]["refresh_on_change"], ["params.path_source"])
        self.assertEqual(fields["params.path_field"]["options_source"], {"type": "preview_headers"})
        self.assertEqual(fields["params.path_field"]["visible_when"]["field"], "params.path_source")
        self.assertEqual(fields["params.path_field"]["depends_on"], ["params.path_source"])
        self.assertEqual(fields["params.path_field"]["empty_text"], FIELD_SELECT_EMPTY_TEXT)
        self.assertEqual(fields["params.path_field"]["invalid_value_text"], FIELD_SELECT_INVALID_TEXT)
        metadata = schema["parameter_metadata"]
        self.assertIn("preview_headers", metadata["options_source_index"])
        self.assertIn("params.path_field", metadata["options_source_details"]["preview_headers"]["field_keys"])
        self.assertEqual(metadata["options_source_details"]["preview_headers"]["label"], "当前输入表字段")
        layout_groups = {group["title"]: group for group in metadata["layout_index"]["groups"]}
        self.assertEqual(layout_groups["插件参数 / 文件来源"]["field_keys"][0], "params.path_source")
        self.assertTrue(layout_groups["高级参数 / 读取设置"]["advanced"])
        ui_hints = {field["field_key"]: field for field in metadata["ui_hints"]["fields"]}
        self.assertIn("params.directory_path", metadata["ui_hints"]["placeholder_fields"])
        self.assertEqual(ui_hints["params.directory_path"]["placeholder"], "选择或输入固定目录路径")
        self.assertIn("params.preview_write_db", metadata["ui_hints"]["warning_fields"])
        self.assertIn("预览也会写入数据库", ui_hints["params.preview_write_db"]["warning"])
        self.assertEqual(fields["params.directory_path"]["type"], "directory")
        self.assertEqual(fields["params.directory_path"]["depends_on"], ["params.path_source"])
        self.assertEqual(fields["params.force_refresh"]["enabled_when"]["field"], "params.enable_cache")
        self.assertEqual(fields["params.force_refresh"]["depends_on"], ["params.enable_cache"])

    def test_word_excel_writer_parameter_metadata_is_ui_ready(self):
        schema = self._schema("plugin.word_excel_write_from_table_v2")
        fields = self._fields(schema)
        group_titles = self._group_titles(schema)

        self.assertIn("插件参数 / 写入引擎", group_titles)
        self.assertIn("插件参数 / 写入策略", group_titles)
        self.assertIn("插件参数 / 路径字段", group_titles)
        self.assertIn("插件参数 / 目标文件策略", group_titles)
        self.assertIn("插件参数 / 写入数据字段", group_titles)
        self.assertIn("高级参数 / win32高级设置", group_titles)
        self.assertLess(group_titles.index("插件参数 / 写入引擎"), group_titles.index("插件参数 / 写入策略"))
        self.assertLess(group_titles.index("插件参数 / 路径字段"), group_titles.index("插件参数 / 目标文件策略"))

        self.assertEqual(fields["params.write_engine"]["refresh_on_change"], ["params.write_engine"])
        self.assertEqual(fields["params.win32_open_retries"]["depends_on"], ["params.write_engine"])
        self.assertEqual(fields["params.win32_open_retries"]["visible_when"]["field"], "params.write_engine")
        self.assertEqual(fields["params.win32_open_retries"]["min"], 0)
        self.assertEqual(fields["params.win32_open_retries"]["step"], 1)
        self.assertEqual(fields["params.win32_open_retries"]["unit"], "次")
        metadata = schema["parameter_metadata"]
        layout_groups = {group["title"]: group for group in metadata["layout_index"]["groups"]}
        self.assertTrue(layout_groups["高级参数 / win32高级设置"]["advanced"])
        self.assertIn("params.win32_open_retries", layout_groups["高级参数 / win32高级设置"]["field_keys"])
        ui_hints = {field["field_key"]: field for field in metadata["ui_hints"]["fields"]}
        self.assertIn("params.win32_open_retries", metadata["ui_hints"]["advanced_fields"])
        self.assertIn("params.win32_open_retries", metadata["ui_hints"]["numeric_fields"])
        self.assertEqual(ui_hints["params.win32_open_retries"]["min"], 0)
        self.assertEqual(ui_hints["params.win32_open_retries"]["step"], 1)
        self.assertEqual(ui_hints["params.win32_open_retries"]["unit"], "次")
        self.assertIn("params.preview_write_files", metadata["ui_hints"]["warning_fields"])
        self.assertEqual(fields["params.verify_after_write"]["visible_when"]["field"], "params.write_engine")
        self.assertEqual(fields["params.verify_after_write"]["depends_on"], ["params.write_engine"])
        self.assertIn("win32 Word", fields["params.verify_after_write"]["help"])
        self.assertEqual(fields["params.word_text_write_mode"]["depends_on"], ["params.write_engine"])
        self.assertEqual(fields["params.word_text_write_mode"]["refresh_on_change"], ["params.word_text_write_mode"])
        self.assertEqual(
            fields["params.scoped_replace_default"]["visible_when"],
            {
                "all": [
                    {"field": "params.write_engine", "equals": "win32"},
                    {"field": "params.word_text_write_mode", "equals": "按old_text查找替换"},
                ],
            },
        )
        self.assertEqual(
            fields["params.scoped_replace_default"]["depends_on"],
            ["params.write_engine", "params.word_text_write_mode"],
        )
        self.assertEqual(
            fields["params.old_text_field"]["depends_on"],
            ["params.write_engine", "params.word_text_write_mode", "params.write_strategy_field"],
        )
        self.assertIn("word_global_replace", fields["params.old_text_field"]["help"])
        self.assertIn("params.old_text_field", metadata["ui_hints"]["warning_fields"])
        self.assertIn("params.write_strategy_field", metadata["options_source_details"]["preview_headers"]["depends_on"])
        preview_header_entries = {
            item["field_key"]: item
            for item in metadata["options_source_index"]["preview_headers"]
        }
        self.assertEqual(
            preview_header_entries["params.old_text_field"]["depends_on"],
            ["params.write_engine", "params.word_text_write_mode", "params.write_strategy_field"],
        )
        self.assertEqual(
            fields["params.replace_scope_field"]["depends_on"],
            ["params.write_engine", "params.word_text_write_mode", "params.write_strategy_field"],
        )
        self.assertIn("节点级默认替换次数", fields["params.replace_scope_field"]["help"])
        self.assertIn("params.replace_scope_field", metadata["ui_hints"]["warning_fields"])
        self.assertIn("params.rule_old_text_field", metadata["ui_hints"]["warning_fields"])
        self.assertIn("params.rule_new_text_field", metadata["ui_hints"]["warning_fields"])
        self.assertEqual(fields["params.rule_old_text_field"]["depends_on"], ["params.write_engine", "params.word_text_write_mode"])
        self.assertEqual(fields["params.rule_new_text_field"]["depends_on"], ["params.write_engine", "params.word_text_write_mode"])
        self.assertIn("255 字符限制", fields["params.rule_old_text_field"]["help"])
        self.assertIn("配套使用", fields["params.rule_new_text_field"]["help"])
        self.assertIn("行级策略", fields["params.write_strategy_field"]["help"])

        for key in (
            "params.path_field",
            "params.target_path_field",
            "params.block_type_field",
            "params.value_field",
            "params.meta_json_field",
        ):
            self.assertEqual(fields[key]["options_source"], {"type": "preview_headers"})
            self.assertEqual(fields[key]["empty_text"], FIELD_SELECT_EMPTY_TEXT)
            self.assertEqual(fields[key]["invalid_value_text"], FIELD_SELECT_INVALID_TEXT)

    def test_template_plugin_parameter_metadata_is_ui_ready(self):
        schema = self._schema("plugin.example_cached_plugin")
        fields = self._fields(schema)
        group_titles = self._group_titles(schema)

        self.assertIn("插件参数 / 输入", group_titles)
        self.assertIn("插件参数 / 输出", group_titles)
        self.assertIn("插件参数 / 缓存", group_titles)
        self.assertLess(group_titles.index("插件参数 / 输入"), group_titles.index("插件参数 / 输出"))
        self.assertLess(group_titles.index("插件参数 / 输出"), group_titles.index("插件参数 / 缓存"))

        self.assertEqual(fields["params.path_field"]["options_source"], {"type": "preview_headers"})
        self.assertEqual(fields["params.path_field"]["empty_text"], FIELD_SELECT_EMPTY_TEXT)
        self.assertEqual(fields["params.path_field"]["invalid_value_text"], FIELD_SELECT_INVALID_TEXT)
        self.assertEqual(fields["params.sample_table"]["options_source"], {"type": "table_names"})
        self.assertEqual(fields["params.sample_table"]["empty_text"], "当前没有可选数据库表")
        self.assertEqual(fields["params.enable_cache"]["refresh_on_change"], ["params.enable_cache"])
        self.assertEqual(fields["params.cache_key_mode"]["enabled_when"]["field"], "params.enable_cache")
        self.assertEqual(fields["params.cache_key_mode"]["depends_on"], ["params.enable_cache"])
        self.assertEqual(fields["params.cache_namespace"]["visible_when"]["field"], "params.enable_cache")
        self.assertEqual(fields["params.cache_namespace"]["depends_on"], ["params.enable_cache"])
        self.assertEqual(fields["params.cache_namespace"]["width_hint"], "wide")
        self.assertIn("项目/批次", fields["params.cache_namespace"]["help"])
        metadata = schema["parameter_metadata"]
        self.assertIn("params.cache_namespace", metadata["ui_hints"]["placeholder_fields"])
        self.assertIn("params.cache_namespace", metadata["ui_hints"]["width_hint_fields"])
        self.assertIn("params.enable_cache", metadata["dependency_index"])
        self.assertIn("params.cache_namespace", metadata["dependency_index"]["params.enable_cache"])

    def test_visual_mapping_plugin_is_complex_config_protocol_sample(self):
        described = self.service.describe_plugin_config(
            "plugin.visual_mapping_write_plan_v1",
            input_table={
                "headers": ["source_file", "sheet_name", "cell", "content"],
                "rows": [],
            },
        )

        self.assertTrue(described["ok"], described)
        self.assertEqual(described["config_schema_version"], "DataFlowKit.visual_mapping.config.v1")
        self.assertEqual(described["protocol_family"], "plugin_complex_config")
        view_ids = [view["view_id"] for view in described["views"]]
        self.assertIn("visual_mapping.rules", view_ids)
        self.assertIn("visual_mapping.linked_rules", view_ids)
        view_by_id = {view["view_id"]: view for view in described["views"]}
        rules_action_state = view_by_id["visual_mapping.rules"]["action_state"]
        self.assertEqual(rules_action_state["schema_version"], "plugin_config_action_state.v1")
        self.assertEqual(rules_action_state["action_id"], "visual_mapping.edit.rules")
        self.assertIn("replace_item", rules_action_state["supported_operations"])
        self.assertTrue(rules_action_state["buttons"]["append_item"]["enabled"])
        self.assertFalse(rules_action_state["buttons"]["update_item"]["enabled"])
        self.assertFalse(rules_action_state["buttons"]["delete_item"]["enabled"])
        action_ids = [action["action_id"] for action in described["actions"]]
        self.assertIn("visual_mapping.edit.rules", action_ids)
        self.assertIn("visual_mapping.edit.linked_rules", action_ids)
        compatibility = described["config_compatibility"]
        self.assertEqual(compatibility["compatibility_tier"], "A_SCHEMA_PATCH")
        self.assertEqual(compatibility["primary_config_path"], "schema_patch")
        self.assertTrue(compatibility["config_patch"])
        self.assertTrue(compatibility["legacy_fallback_available"])
        self.assertFalse(compatibility["legacy_ui_required"])
        self.assertEqual(compatibility["ui_support"]["recommended_entry"], "standard_protocol")
        self.assertTrue(compatibility["ui_support"]["direct_ui"]["qt"])
        self.assertTrue(compatibility["ui_support"]["direct_ui"]["dotnet"])
        self.assertTrue(compatibility["ui_support"]["direct_ui"]["web"])

        config_sections = {section["section_id"]: section for section in described["config_sections"]}
        self.assertIn("plugin.config_protocol", config_sections)
        self.assertIn("plugin.parameter_metadata", config_sections)
        self.assertIn("plugin.config_compatibility", config_sections)
        protocol_text = "\n".join(config_sections["plugin.config_protocol"]["lines"])
        self.assertIn("DataFlowKit.visual_mapping.protocol_manifest.v1", protocol_text)
        self.assertIn("接口 describe_config、validate_config_patch、apply_config_patch、preview_config_effect", protocol_text)
        self.assertIn("Patch协议：config_patch", protocol_text)
        self.assertIn("警告协议：config_warning", protocol_text)
        self.assertIn("配置动作：编辑单元格映射规则", protocol_text)
        compatibility_text = "\n".join(config_sections["plugin.config_compatibility"]["lines"])
        self.assertIn("兼容等级 A_SCHEMA_PATCH", compatibility_text)
        self.assertIn("可直接支持UI：Tk、Qt、.NET、Web、Electron", compatibility_text)
        metadata_text = "\n".join(config_sections["plugin.parameter_metadata"]["lines"])
        self.assertIn("参数字段：8 个", metadata_text)
        self.assertIn("参数能力：动态候选、字段动作", metadata_text)


if __name__ == "__main__":
    unittest.main()
