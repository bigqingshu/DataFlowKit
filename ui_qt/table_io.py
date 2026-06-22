# -*- coding: utf-8 -*-
"""Compatibility shim for table loading helpers used by the Qt shell."""

from engine.table_io import load_delimited_table, load_json_table, load_table_file

__all__ = [
    "load_delimited_table",
    "load_json_table",
    "load_table_file",
]