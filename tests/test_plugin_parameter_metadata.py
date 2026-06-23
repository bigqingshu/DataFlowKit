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
        self.assertEqual(fields["params.path_source"]["refresh_on_change"], ["params.path_source"])
        self.assertEqual(fields["params.path_field"]["options_source"], {"type": "preview_headers"})
        self.assertEqual(fields["params.path_field"]["visible_when"]["field"], "params.path_source")
        self.assertEqual(fields["params.path_field"]["depends_on"], ["params.path_source"])
        self.assertEqual(fields["params.path_field"]["empty_text"], FIELD_SELECT_EMPTY_TEXT)
        self.assertEqual(fields["params.path_field"]["invalid_value_text"], FIELD_SELECT_INVALID_TEXT)
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
        self.assertEqual(fields["params.word_text_write_mode"]["depends_on"], ["params.write_engine"])

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


if __name__ == "__main__":
    unittest.main()
