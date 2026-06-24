# -*- coding: utf-8 -*-
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from workflow.advanced_filter_command_service import (
    ADVANCED_FILTER_COMMAND_SCHEMA_VERSION,
    ADVANCED_FILTER_LAYOUT_SCHEMA_VERSION,
    ADVANCED_FILTER_SERVICE_SCHEMA_VERSION,
    ADVANCED_FILTER_UI_HINTS_SCHEMA_VERSION,
    apply_advanced_filter_command,
    describe_advanced_filter_service,
    describe_advanced_filter_state,
)


class AdvancedFilterCommandServiceTests(unittest.TestCase):
    def test_describe_service_exposes_protocol_metadata(self):
        service = describe_advanced_filter_service()

        self.assertEqual(service["schema_version"], ADVANCED_FILTER_SERVICE_SCHEMA_VERSION)
        self.assertEqual(service["protocol_family"], "advanced_filter_service")
        self.assertIn("add_condition", service["commands"])
        self.assertIn("add_output_fields", service["commands"])
        self.assertIn("build_preview", service["commands"])
        self.assertIn("apply_template", service["commands"])
        self.assertEqual(service["command_schema"], ADVANCED_FILTER_COMMAND_SCHEMA_VERSION)
        self.assertEqual(service["command_schema_detail"]["schema_version"], ADVANCED_FILTER_COMMAND_SCHEMA_VERSION)
        self.assertEqual(service["layout"]["schema_version"], ADVANCED_FILTER_LAYOUT_SCHEMA_VERSION)
        self.assertEqual(service["ui_hints"]["schema_version"], ADVANCED_FILTER_UI_HINTS_SCHEMA_VERSION)
        self.assertIn("conditions", service["layout"]["section_order"])
        self.assertEqual(service["layout"]["default_section_id"], "conditions")
        self.assertEqual(service["command_schema_detail"]["commands"]["add_condition"]["section_id"], "conditions")
        self.assertEqual(service["command_schema_detail"]["commands"]["add_join_rule"]["requires_confirmation_when"], ["same_join_field"])
        self.assertEqual(service["ui_hints"]["command_prominence"]["build_preview"], "primary")
        self.assertEqual(
            service["result_schemas"]["advanced_filter_layout"]["schema_version"],
            ADVANCED_FILTER_LAYOUT_SCHEMA_VERSION,
        )

    def test_describe_state_builds_fields_and_combo_defaults(self):
        state = describe_advanced_filter_state(
            selected_tables=["orders", "people"],
            columns_by_table={
                "orders": ["id", "person_id"],
                "people": ["id", "name"],
            },
        )

        self.assertEqual(state["field_display_cache"], ["orders.id", "orders.person_id", "people.id", "people.name"])
        self.assertEqual(state["filter_field"], "orders.id")
        self.assertEqual(state["join_left"], "orders.id")
        self.assertEqual(state["join_right"], "orders.person_id")

    def test_refresh_fields_filters_invalid_rules_and_outputs(self):
        state = {
            "conditions": [
                {"field": "orders.id", "op": "等于", "value": "1"},
                {"field": "bad", "op": "等于", "value": "2"},
            ],
            "join_rules": [
                {"left": "orders.person_id", "op": "等于", "right": "people.id"},
                {"left": "orders.id", "op": "等于", "right": "bad"},
            ],
            "output_fields": ["people.name", "bad"],
            "filter_field": "people.name",
            "join_left": "bad",
        }

        result = apply_advanced_filter_command(state, {
            "type": "refresh_fields",
            "selected_tables": ["orders", "people"],
            "columns_by_table": {
                "orders": ["id", "person_id"],
                "people": ["id", "name"],
            },
        })

        self.assertTrue(result["ok"])
        self.assertEqual(result["state"]["conditions"], [{"field": "orders.id", "op": "等于", "value": "1"}])
        self.assertEqual(result["state"]["join_rules"], [{"left": "orders.person_id", "op": "等于", "right": "people.id"}])
        self.assertEqual(result["state"]["output_fields"], ["people.name"])
        self.assertEqual(result["state"]["filter_field"], "people.name")
        self.assertEqual(result["state"]["join_left"], "orders.id")

    def test_add_condition_uses_structured_confirmation_for_empty_value(self):
        state = {
            "selected_tables": ["orders"],
            "columns_by_table": {"orders": ["id"]},
        }

        blocked = apply_advanced_filter_command(state, {
            "type": "add_condition",
            "field": "orders.id",
            "op": "包含",
            "value": "",
        })

        self.assertFalse(blocked["ok"])
        self.assertTrue(blocked["requires_confirmation"])
        self.assertEqual(blocked["issues"][0]["code"], "empty_condition_value_requires_confirmation")
        self.assertEqual(blocked["state"]["conditions"], [])

        allowed = apply_advanced_filter_command(state, {
            "type": "add_condition",
            "field": "orders.id",
            "op": "包含",
            "value": "",
            "allow_empty_value": True,
        })

        self.assertTrue(allowed["ok"])
        self.assertEqual(allowed["state"]["conditions"], [{"field": "orders.id", "op": "包含", "value": ""}])

    def test_add_join_rule_uses_structured_confirmation_for_same_field(self):
        state = {
            "selected_tables": ["orders"],
            "columns_by_table": {"orders": ["id"]},
        }

        blocked = apply_advanced_filter_command(state, {
            "type": "add_join_rule",
            "left": "orders.id",
            "op": "等于",
            "right": "orders.id",
        })

        self.assertFalse(blocked["ok"])
        self.assertTrue(blocked["requires_confirmation"])
        self.assertEqual(blocked["issues"][0]["code"], "same_join_field_requires_confirmation")

        allowed = apply_advanced_filter_command(state, {
            "type": "add_join_rule",
            "left": "orders.id",
            "op": "等于",
            "right": "orders.id",
            "allow_same_field": True,
        })

        self.assertTrue(allowed["ok"])
        self.assertEqual(allowed["state"]["join_rules"], [{"left": "orders.id", "op": "等于", "right": "orders.id"}])

    def test_output_field_commands_keep_order_and_ignore_invalid_indexes(self):
        state = {
            "selected_tables": ["orders", "people"],
            "columns_by_table": {
                "orders": ["id"],
                "people": ["name", "age"],
            },
            "output_fields": ["orders.id"],
        }

        added = apply_advanced_filter_command(state, {
            "type": "add_output_fields",
            "indexes": [1, 0, 99, -1],
        })
        self.assertEqual(added["state"]["output_fields"], ["orders.id", "people.name"])

        all_added = apply_advanced_filter_command(added["state"], {"type": "add_all_output_fields"})
        self.assertEqual(all_added["state"]["output_fields"], ["orders.id", "people.name", "people.age"])

        removed = apply_advanced_filter_command(all_added["state"], {
            "type": "remove_output_fields",
            "indexes": [1, 99],
        })
        self.assertEqual(removed["state"]["output_fields"], ["orders.id", "people.age"])

        cleared = apply_advanced_filter_command(removed["state"], {"type": "clear_output_fields"})
        self.assertEqual(cleared["state"]["output_fields"], [])

    def test_delete_and_clear_rule_commands(self):
        state = {
            "conditions": [
                {"field": "orders.id", "op": "等于", "value": "1"},
                {"field": "people.name", "op": "包含", "value": "A"},
            ],
            "join_rules": [
                {"left": "orders.id", "op": "等于", "right": "people.id"},
                {"left": "orders.code", "op": "左包含右", "right": "people.code"},
            ],
        }

        deleted = apply_advanced_filter_command(state, {
            "type": "delete_conditions",
            "indexes": [0],
        })
        self.assertEqual(deleted["state"]["conditions"], [{"field": "people.name", "op": "包含", "value": "A"}])

        join_deleted = apply_advanced_filter_command(deleted["state"], {
            "type": "delete_join_rules",
            "indexes": [1],
        })
        self.assertEqual(join_deleted["state"]["join_rules"], [{"left": "orders.id", "op": "等于", "right": "people.id"}])

        cleared_conditions = apply_advanced_filter_command(join_deleted["state"], {"type": "clear_conditions"})
        self.assertEqual(cleared_conditions["state"]["conditions"], [])

        cleared_join = apply_advanced_filter_command(cleared_conditions["state"], {"type": "clear_join_rules"})
        self.assertEqual(cleared_join["state"]["join_rules"], [])

    def test_build_preview_and_dedupe_preview(self):
        state = {
            "selected_tables": ["orders"],
            "columns_by_table": {"orders": ["id", "name"]},
            "conditions": [{"field": "orders.name", "op": "包含", "value": "A"}],
            "output_fields": ["orders.id", "orders.name"],
        }

        preview = apply_advanced_filter_command(state, {
            "type": "build_preview",
            "table_records_map": {
                "orders": [
                    {"orders.id": "1", "orders.name": "Alpha"},
                    {"orders.id": "1", "orders.name": "Alpha"},
                    {"orders.id": "2", "orders.name": "Beta"},
                ],
            },
        })

        self.assertTrue(preview["ok"])
        self.assertEqual(preview["preview"]["headers"], ["orders.id", "orders.name"])
        self.assertEqual(preview["preview"]["rows"], [["1", "Alpha"], ["1", "Alpha"]])
        self.assertEqual(preview["preview"]["row_count"], 2)

        deduped = apply_advanced_filter_command(preview["state"], {"type": "dedupe_preview"})
        self.assertTrue(deduped["ok"])
        self.assertEqual(deduped["state"]["preview_rows"], [["1", "Alpha"]])
        self.assertEqual(deduped["preview"]["row_count"], 1)

    def test_build_preview_reports_structured_issue_without_output_fields(self):
        result = apply_advanced_filter_command({}, {
            "type": "build_preview",
            "table_records_map": {},
        })

        self.assertFalse(result["ok"])
        self.assertEqual(result["issues"][0]["code"], "missing_output_fields")

    def test_main_preview_snapshot_and_template_commands(self):
        state = {
            "main_table": "orders",
            "tables_cache": ["orders", "people"],
            "selected_tables": ["orders"],
            "columns_by_table": {
                "orders": ["id", "name"],
                "people": ["id", "name"],
            },
            "conditions": [{"field": "orders.id", "op": "等于", "value": "1"}],
            "output_fields": ["orders.name"],
            "result_limit": "12",
            "max_intermediate": "34",
            "save_table": "out",
            "preview_headers": ["orders.name"],
            "preview_rows": [["Alpha"]],
        }

        snapshot = apply_advanced_filter_command(state, {"type": "build_main_preview_snapshot"})
        self.assertTrue(snapshot["ok"])
        self.assertEqual(snapshot["main_preview_snapshot"], {
            "headers": ["orders.name"],
            "rows": [["Alpha"]],
            "raw_data": "",
        })

        exported = apply_advanced_filter_command(state, {"type": "export_template"})
        self.assertTrue(exported["ok"])
        self.assertEqual(exported["template"]["main_table"], "orders")
        self.assertEqual(exported["template"]["selected_tables"], ["orders"])
        self.assertEqual(exported["template"]["save_table"], "out")

        applied = apply_advanced_filter_command(state, {
            "type": "apply_template",
            "template": {
                "main_table": "people",
                "selected_tables": ["people", "missing"],
                "conditions": [{"field": "people.name", "op": "包含", "value": "A"}],
                "join_rules": [{"left": "orders.id", "op": "等于", "right": "people.id"}],
                "output_fields": ["people.name", "missing"],
                "logic": "OR",
                "join_logic": "AND",
                "result_limit": "56",
                "max_intermediate": "78",
                "save_table": "templated",
            },
        })

        self.assertTrue(applied["ok"])
        self.assertEqual(applied["state"]["main_table"], "people")
        self.assertEqual(applied["state"]["selected_tables"], ["people"])
        self.assertEqual(applied["state"]["conditions"], [{"field": "people.name", "op": "包含", "value": "A"}])
        self.assertEqual(applied["state"]["join_rules"], [])
        self.assertEqual(applied["state"]["output_fields"], ["people.name"])
        self.assertEqual(applied["state"]["logic"], "OR")
        self.assertEqual(applied["state"]["result_limit"], "56")
        self.assertEqual(applied["state"]["save_table"], "templated")

    def test_template_file_commands_are_ui_free(self):
        state = {
            "main_table": "orders",
            "tables_cache": ["orders", "people"],
            "selected_tables": ["orders"],
            "columns_by_table": {
                "orders": ["id", "name"],
                "people": ["id", "name"],
            },
            "conditions": [{"field": "orders.id", "op": "等于", "value": "1"}],
            "output_fields": ["orders.name"],
            "save_table": "out",
        }

        with TemporaryDirectory() as temp_dir:
            path = str(Path(temp_dir) / "filter_template.json")
            saved = apply_advanced_filter_command(state, {
                "type": "save_template_file",
                "path": path,
            })
            loaded = apply_advanced_filter_command({
                "tables_cache": ["orders", "people"],
                "columns_by_table": {
                    "orders": ["id", "name"],
                    "people": ["id", "name"],
                },
            }, {
                "type": "load_template_file",
                "path": path,
            })

        self.assertTrue(saved["ok"])
        self.assertEqual(saved["template_file"]["schema_version"], "advanced_filter_template_file.v1")
        self.assertEqual(saved["template_file"]["action"], "save")
        self.assertEqual(saved["template_file"]["template"]["save_table"], "out")
        self.assertTrue(loaded["ok"])
        self.assertEqual(loaded["template_file"]["action"], "load")
        self.assertEqual(loaded["state"]["conditions"], [{"field": "orders.id", "op": "等于", "value": "1"}])
        self.assertEqual(loaded["state"]["output_fields"], ["orders.name"])


if __name__ == "__main__":
    unittest.main()
