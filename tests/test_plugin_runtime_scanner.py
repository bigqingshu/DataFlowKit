# -*- coding: utf-8 -*-
import json
import os
import tempfile
import unittest
from pathlib import Path

from plugin_runtime.scanner import scan_plugins


class PluginRuntimeScannerTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(dir=os.getcwd())
        self.root = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_scans_importable_single_file_plugin(self):
        plugin = self.root / "demo_plugin.py"
        plugin.write_text(
            "\n".join([
                "PLUGIN_INFO = {'id': 'demo', 'name': 'Demo', 'api_version': '1.0'}",
                "PARAMETER_SCHEMA = [{'name': 'field'}]",
                "def run(input_data, params, context):",
                "    return {'ok': True, 'output': input_data}",
            ]),
            encoding="utf-8",
        )

        registry, errors = scan_plugins(str(self.root))

        self.assertEqual(errors, [])
        self.assertIn("demo", registry)
        self.assertTrue(registry["demo"]["import_ok"])
        self.assertEqual(registry["demo"]["metadata_source"], "import_py")
        self.assertEqual(registry["demo"]["schema"], [{"name": "field"}])

    def test_scans_manifest_plugin_without_importing_entry_by_default(self):
        plugin_dir = self.root / "manifest_demo"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.py").write_text("raise RuntimeError('should not import')\n", encoding="utf-8")
        (plugin_dir / "plugin.json").write_text(
            json.dumps({
                "plugin_info": {
                    "id": "manifest_demo",
                    "name": "Manifest Demo",
                    "api_version": "1.0",
                    "run_mode": "external_python",
                },
                "entry": "plugin.py",
                "schema": [{"name": "path"}],
            }, ensure_ascii=False),
            encoding="utf-8",
        )

        registry, errors = scan_plugins(str(self.root))

        self.assertEqual(errors, [])
        self.assertIn("manifest_demo", registry)
        item = registry["manifest_demo"]
        self.assertFalse(item["import_ok"])
        self.assertEqual(item["run_mode_default"], "插件独立环境")
        self.assertEqual(item["metadata_source"], "plugin_json")

    def test_duplicate_plugin_id_is_reported_as_error(self):
        for name in ("a.py", "b.py"):
            (self.root / name).write_text(
                "\n".join([
                    "PLUGIN_INFO = {'id': 'same', 'name': 'Same', 'api_version': '1.0'}",
                    "def run(input_data, params, context):",
                    "    return {'ok': True, 'output': input_data}",
                ]),
                encoding="utf-8",
            )

        registry, errors = scan_plugins(str(self.root))

        self.assertIn("same", registry)
        self.assertEqual(len(errors), 1)
        self.assertIn("插件 id 重复", errors[0]["error"])


if __name__ == "__main__":
    unittest.main()

