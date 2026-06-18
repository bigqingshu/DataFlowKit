# -*- coding: utf-8 -*-
import json
import os
import tempfile
import unittest
from pathlib import Path

from shared.atomic_json_utils import (
    atomic_write_json,
    json_backup_path,
    load_json_with_backup,
)


class AtomicJsonUtilsTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(dir=os.getcwd())
        self.path = Path(self.temp_dir.name) / "settings.json"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_atomic_write_creates_backup_on_overwrite(self):
        atomic_write_json(self.path, {"version": 1})
        atomic_write_json(self.path, {"version": 2})
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8")), {"version": 2})
        self.assertEqual(
            json.loads(json_backup_path(self.path).read_text(encoding="utf-8")),
            {"version": 1},
        )

    def test_serialization_failure_preserves_existing_file(self):
        atomic_write_json(self.path, {"version": 1})
        with self.assertRaises(TypeError):
            atomic_write_json(self.path, {"invalid": object()})
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8")), {"version": 1})
        self.assertEqual(list(self.path.parent.glob(f".{self.path.name}.*.tmp")), [])

    def test_load_uses_backup_when_primary_is_corrupt(self):
        atomic_write_json(self.path, {"version": 1})
        atomic_write_json(self.path, {"version": 2})
        self.path.write_text("{broken", encoding="utf-8")
        data, info = load_json_with_backup(self.path)
        self.assertEqual(data, {"version": 1})
        self.assertEqual(info["source"], "backup")
        self.assertIn("已从备份恢复", info["warning"])

    def test_load_raises_when_primary_and_backup_are_corrupt(self):
        self.path.write_text("{broken", encoding="utf-8")
        json_backup_path(self.path).write_text("{also-broken", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "主文件和备份均无法读取"):
            load_json_with_backup(self.path)


if __name__ == "__main__":
    unittest.main()
