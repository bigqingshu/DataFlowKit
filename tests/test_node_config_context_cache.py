# -*- coding: utf-8 -*-
import unittest

from workflow.node_config_context_cache import (
    build_preview_context_cache,
    normalize_current_table_field_reference,
    resolve_node_config_headers,
)


class NodeConfigContextCacheTests(unittest.TestCase):
    def make_plan(self):
        return {
            "headers": ["A"],
            "rows": [["a"]],
            "nodes": [
                {"node_type_id": "core.new_columns", "config": {"columns_text": "Generated=1"}},
                {"node_type_id": "core.replace", "config": {"target_field": "Generated"}},
            ],
        }

    def test_resolves_headers_from_explicit_previous_node_preview(self):
        plan = self.make_plan()
        cache = build_preview_context_cache(
            plan=plan,
            stop_index=0,
            headers=["A", "Generated"],
            rows=[["a", "g"]],
        )

        resolved = resolve_node_config_headers(
            selected_index=1,
            current_headers=["A"],
            preview_cache=cache,
            plan=plan,
        )

        self.assertEqual(resolved["headers"], ["A", "Generated"])
        self.assertEqual(resolved["source"], "preview_cache")
        self.assertEqual(resolved["reason"], "cache_matches_previous_node")
        self.assertEqual(cache["row_count"], 1)
        self.assertEqual(cache["column_count"], 2)

    def test_falls_back_when_cache_is_for_another_node(self):
        plan = self.make_plan()
        cache = build_preview_context_cache(
            plan=plan,
            stop_index=1,
            headers=["A", "Generated", "AfterSecond"],
            rows=[],
        )

        resolved = resolve_node_config_headers(
            selected_index=1,
            current_headers=["A"],
            preview_cache=cache,
            plan=plan,
        )

        self.assertEqual(resolved["headers"], ["A"])
        self.assertEqual(resolved["reason"], "cache_not_for_selected_node")

    def test_falls_back_when_plan_signature_changed(self):
        plan = self.make_plan()
        cache = build_preview_context_cache(
            plan=plan,
            stop_index=0,
            headers=["A", "Generated"],
            rows=[],
        )
        changed_plan = self.make_plan()
        changed_plan["nodes"].append({"node_type_id": "core.delete_columns", "config": {}})

        resolved = resolve_node_config_headers(
            selected_index=1,
            current_headers=["A"],
            preview_cache=cache,
            plan=changed_plan,
        )

        self.assertEqual(resolved["headers"], ["A"])
        self.assertEqual(resolved["reason"], "cache_stale_plan")

    def test_first_node_uses_current_input_headers(self):
        plan = self.make_plan()
        cache = build_preview_context_cache(
            plan=plan,
            stop_index=0,
            headers=["A", "Generated"],
            rows=[],
        )

        resolved = resolve_node_config_headers(
            selected_index=0,
            current_headers=["A"],
            preview_cache=cache,
            plan=plan,
        )

        self.assertEqual(resolved["headers"], ["A"])
        self.assertEqual(resolved["source"], "current_headers")

    def test_normalizes_legacy_current_table_prefix_when_header_exists(self):
        self.assertEqual(
            normalize_current_table_field_reference("当前表.Generated", ["Generated"]),
            "Generated",
        )
        self.assertEqual(
            normalize_current_table_field_reference("当前表.Missing", ["Generated"]),
            "当前表.Missing",
        )


if __name__ == "__main__":
    unittest.main()
