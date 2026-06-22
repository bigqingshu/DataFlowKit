# -*- coding: utf-8 -*-
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from engine.table_io import load_table_file
from ui_qt.table_io import load_table_file as load_table_file_from_qt_shim


class EngineTableIoTests(unittest.TestCase):
    def test_loads_json_objects_and_delimited_files_from_engine_module(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            json_path = root / "rows.json"
            tsv_path = root / "rows.tsv"
            json_path.write_text('[{"A": "a", "B": 1}, {"A": "b", "B": 2}]', encoding="utf-8")
            tsv_path.write_text("A\tB\na\t1\nb\t2\n", encoding="utf-8")

            self.assertEqual(load_table_file(json_path), (["A", "B"], [["a", 1], ["b", 2]]))
            self.assertEqual(load_table_file(tsv_path), (["A", "B"], [["a", "1"], ["b", "2"]]))
            self.assertEqual(load_table_file_from_qt_shim(json_path), load_table_file(json_path))


if __name__ == "__main__":
    unittest.main()
