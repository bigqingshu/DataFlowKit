# -*- coding: utf-8 -*-
import unittest

from workflow.advanced_filter_command_service import (
    ADVANCED_FILTER_SERVICE_SCHEMA_VERSION,
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


if __name__ == "__main__":
    unittest.main()
