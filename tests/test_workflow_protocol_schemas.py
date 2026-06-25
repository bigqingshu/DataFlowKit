# -*- coding: utf-8 -*-
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "schemas"


def load_schema(name):
    with (SCHEMA_DIR / name).open("r", encoding="utf-8") as stream:
        return json.load(stream)


class WorkflowProtocolSchemaTests(unittest.TestCase):
    def test_all_protocol_schema_files_are_valid_json_objects(self):
        expected = [
            "workflow_plan.schema.json",
            "workflow_node.schema.json",
            "table_data.schema.json",
            "runtime_message.schema.json",
            "plugin_manifest.schema.json",
        ]

        for name in expected:
            with self.subTest(name=name):
                schema = load_schema(name)
                self.assertIsInstance(schema, dict)
                self.assertEqual(schema.get("$schema"), "http://json-schema.org/draft-07/schema#")
                self.assertIn("$id", schema)
                self.assertIn("title", schema)

    def test_workflow_plan_schema_keeps_existing_templates_valid(self):
        schema = load_schema("workflow_plan.schema.json")

        self.assertEqual(
            schema["required"],
            ["template_type", "version", "plan_name", "nodes"],
        )
        self.assertEqual(schema["properties"]["template_type"]["const"], "workflow_plan")
        self.assertTrue(schema.get("additionalProperties"))
        self.assertIn("workflow_node.schema.json", schema["properties"]["nodes"]["items"]["$ref"])
        self.assertEqual(schema["properties"]["db_path"]["type"], "string")
        self.assertEqual(schema["properties"]["output_path"]["type"], "string")

        sample = {
            "template_type": "workflow_plan",
            "version": "1.0",
            "plan_name": "demo",
            "nodes": [],
            "db_path": "",
            "output_path": "",
            "legacy_field": "preserved",
        }
        for field in schema["required"]:
            self.assertIn(field, sample)

    def test_workflow_node_schema_accepts_old_type_or_new_node_type_id(self):
        schema = load_schema("workflow_node.schema.json")

        self.assertEqual(schema["required"], ["enabled", "config"])
        self.assertTrue(schema.get("additionalProperties"))
        self.assertEqual(schema["properties"]["node_type_id"]["pattern"], "^[A-Za-z0-9_.:-]+$")
        self.assertEqual(schema["anyOf"], [{"required": ["type"]}, {"required": ["node_type_id"]}])

        old_style = {
            "type": "新建列",
            "enabled": True,
            "config": {},
        }
        new_style = {
            "node_type_id": "core.new_columns",
            "enabled": True,
            "config": {},
        }
        for sample in (old_style, new_style):
            self.assertIn("enabled", sample)
            self.assertIn("config", sample)
            self.assertTrue("type" in sample or "node_type_id" in sample)

    def test_table_data_schema_allows_json_scalar_cells_and_extensions(self):
        schema = load_schema("table_data.schema.json")
        row_item_type = schema["properties"]["rows"]["items"]["items"]["type"]

        self.assertEqual(schema["required"], ["type", "headers", "rows"])
        self.assertEqual(schema["properties"]["type"]["const"], "table")
        self.assertEqual(row_item_type, ["string", "number", "integer", "boolean", "null"])
        self.assertTrue(schema.get("additionalProperties"))

        sample = {
            "type": "table",
            "headers": ["A", "B"],
            "rows": [["x", 1], [None, True]],
            "metadata": {},
            "extensions": {"client": "test"},
        }
        self.assertEqual(sample["type"], "table")
        self.assertEqual(len(sample["headers"]), 2)

    def test_runtime_message_schema_matches_planned_worker_actions_and_events(self):
        schema = load_schema("runtime_message.schema.json")
        defs = schema["definitions"]
        actions = defs["request"]["properties"]["action"]["enum"]
        event_types = defs["event"]["properties"]["type"]["enum"]

        for action in [
            "list_node_types",
            "get_node_type",
            "list_node_ui_schemas",
            "get_node_ui_schema",
            "describe_node_config_context",
            "apply_node_config_command",
            "resolve_node_config_options",
            "migrate_plan",
            "list_plan_templates",
            "load_plan_template",
            "save_plan_template",
            "validate_plan_template",
            "apply_plan_command",
            "import_table_file",
            "parse_clipboard_table",
            "normalize_table_headers",
            "promote_first_row_to_headers",
            "patch_table_cell",
            "search_table",
            "build_data_source_state",
            "describe_data_source_actions",
            "build_data_source_panel_state",
            "build_data_source_manager_state",
            "describe_data_source_service",
            "save_table",
            "delete_table",
            "describe_advanced_filter_service",
            "describe_advanced_filter_state",
            "apply_advanced_filter_command",
            "validate_config",
            "validate_plan_configs",
            "make_default_node",
            "validate_plan",
            "preview_plan",
            "start_job",
            "run_plan",
            "cancel_job",
            "get_job_status",
            "get_job_events",
            "list_output_modes",
            "apply_output",
            "list_tables",
            "load_table",
            "get_table_page",
            "create_table_handle",
            "get_table_handle_page",
            "list_table_handles",
            "release_table_handle",
            "build_table_access",
            "precheck_access",
            "format_access_issue",
            "record_access_audit",
            "list_access_audit_logs",
            "format_access_audit_event",
            "analyze_jumps",
            "validate_jumps",
            "format_jump_issue",
            "get_plugin_schema",
            "describe_plugin_config",
            "resolve_plugin_parameter_options",
            "resolve_plugin_config_options",
            "preview_plugin_config_effect",
            "validate_plugin_config_patch",
            "apply_plugin_config_patch",
            "make_plugin_default_config",
            "list_plugins",
            "validate_plugin_config",
            "run_plugin",
        ]:
            self.assertIn(action, actions)

        for event_type in [
            "workflow_start",
            "workflow_done",
            "workflow_cancelled",
            "job_started",
            "job_done",
            "job_failed",
            "job_cancel_requested",
            "node_start",
            "node_done",
            "node_error",
        ]:
            self.assertIn(event_type, event_types)

        self.assertEqual(defs["request"]["required"], ["request_id", "api_version", "action", "payload"])
        self.assertEqual(defs["response"]["required"], ["request_id", "ok"])

    def test_node_ui_schema_metadata_supports_group_and_submenu_rendering(self):
        from workflow.node_ui_schema import build_node_ui_catalog, get_node_ui_schema

        schema = get_node_ui_schema("core.new_columns", preview_headers=["A"])
        self.assertEqual(schema["menu"]["group"], "数据处理")
        self.assertEqual(schema["menu"]["submenu"], ["新建列"])

        catalog = build_node_ui_catalog(preview_headers=["A"])
        self.assertEqual(catalog["schema_version"], "2.0")
        self.assertTrue(catalog["groups"])
        first_group = catalog["groups"][0]
        self.assertIn("group", first_group)
        self.assertTrue(first_group["items"])
        first_item = first_group["items"][0]
        self.assertIn("submenu", first_item)
        self.assertIn("path", first_item)

    def test_node_ui_schema_marks_structured_list_fields(self):
        from workflow.node_ui_schema import get_node_ui_schema

        schema = get_node_ui_schema("批量更改列名", preview_headers=["A", "B"])
        fields = {
            field["key"]: field
            for group in schema["form"]["groups"]
            for field in group["fields"]
        }
        self.assertEqual(fields["mappings"]["type"], "structured_list")
        self.assertEqual(fields["mappings"]["item_schema"]["columns"][0]["key"], "old")

    def test_node_ui_schema_enriches_table_driven_structured_columns(self):
        from workflow.node_ui_schema import get_node_ui_schema

        schema = get_node_ui_schema(
            "字段映射写入表",
            preview_headers=["源字段"],
            table_names=["orders", "result"],
            table_columns={"orders": ["id", "name"], "result": ["row_id", "status"]},
        )
        fields = {
            field["key"]: field
            for group in schema["form"]["groups"]
            for field in group["fields"]
        }
        mapping_columns = {
            item["key"]: item
            for item in fields["field_mappings"]["item_schema"]["columns"]
        }
        self.assertEqual(mapping_columns["source_field"]["type"], "field_select")
        self.assertEqual(mapping_columns["source_field"]["options_source"], {"type": "table_columns", "table_field": "source_table"})
        self.assertEqual(mapping_columns["source_field"]["action"]["key"], "pick_table_field")
        self.assertEqual(mapping_columns["target_field"]["options_source"], {"type": "table_columns", "table_field": "target_table"})

        filter_schema = get_node_ui_schema(
            "高级筛选",
            table_names=["orders"],
            table_columns={"orders": ["id", "status"]},
        )
        filter_fields = {
            field["key"]: field
            for group in filter_schema["form"]["groups"]
            for field in group["fields"]
        }
        condition_columns = {
            item["key"]: item
            for item in filter_fields["conditions"]["item_schema"]["columns"]
        }
        join_columns = {
            item["key"]: item
            for item in filter_fields["join_rules"]["item_schema"]["columns"]
        }
        self.assertEqual(condition_columns["field"]["options_source"], {"type": "table_columns", "table_field": "source_table"})
        self.assertEqual(join_columns["left"]["action"]["key"], "pick_table_field")
        self.assertEqual(join_columns["right_table"]["type"], "table_select")
        self.assertEqual(join_columns["right_table"]["options_source"], {"type": "field_values", "field": "extra_tables", "value_kind": "table_names"})
        self.assertEqual(join_columns["right"]["options_source"], {"type": "table_columns", "table_field": "right_table"})
        self.assertTrue(join_columns["left"]["ui_capabilities"]["supports_picker"])
        self.assertEqual(join_columns["left"]["help_sections"][0]["title"], "字段说明")

        filter_group_titles = [group["title"] for group in filter_schema["form"]["groups"]]
        self.assertEqual(filter_group_titles, ["筛选条件", "关联表", "输出控制"])
        self.assertEqual(filter_fields["extra_tables"]["type"], "field_multi_select")
        self.assertEqual(filter_fields["extra_tables"]["options_source"], {"type": "table_names"})
        self.assertEqual(filter_fields["extra_tables"]["action"]["key"], "pick_table_names")
        self.assertEqual(filter_fields["output_fields"]["type"], "field_multi_select")
        self.assertEqual(filter_fields["output_fields"]["options_source"], {"type": "table_columns", "table_field": "source_table"})
        self.assertEqual(filter_fields["output_fields"]["action"]["key"], "pick_table_fields")
        self.assertEqual(filter_fields["join_rules"]["visible_when"], {"field": "extra_tables", "truthy": True})

        writeback_group_titles = [group["title"] for group in schema["form"]["groups"]]
        self.assertEqual(writeback_group_titles, ["写回目标", "匹配规则", "写回策略", "执行控制"])
        self.assertEqual(fields["match_rules"]["type"], "structured_list")
        self.assertEqual(fields["match_rules"]["visible_when"], {"field": "use_match_rules", "equals": True})
        match_columns = {
            item["key"]: item
            for item in fields["match_rules"]["item_schema"]["columns"]
        }
        self.assertEqual(match_columns["source_field"]["options_source"], {"type": "table_columns", "table_field": "source_table"})
        self.assertEqual(match_columns["target_field"]["action"]["key"], "pick_table_field")
        self.assertTrue(match_columns["target_field"]["ui_capabilities"]["supports_picker"])
        self.assertEqual(fields["source_empty_fixed"]["visible_when"], {"field": "source_empty_policy", "equals": "填写固定值"})
        self.assertEqual(fields["target_table"]["type"], "table_select")
        self.assertEqual(fields["target_table"]["options_source"], {"type": "table_names"})

        selected_write_schema = get_node_ui_schema(
            "选定列写入指定表",
            preview_headers=["编码", "名称", "数量"],
            table_names=["orders", "result"],
            table_columns={"orders": ["id", "name"], "result": ["row_id", "status"]},
        )
        selected_write_fields = {
            field["key"]: field
            for group in selected_write_schema["form"]["groups"]
            for field in group["fields"]
        }
        self.assertEqual(selected_write_fields["source_sqlite_table"]["options_source"], {"type": "table_names"})
        self.assertEqual(selected_write_fields["selected_fields"]["type"], "field_multi_select")
        self.assertEqual(selected_write_fields["selected_fields"]["options_source"], {"type": "preview_headers"})
        self.assertEqual(selected_write_fields["selected_fields"]["action"]["key"], "pick_preview_headers")
        self.assertEqual(selected_write_fields["target_table"]["action"]["key"], "pick_table_name")

    def test_node_ui_schema_marks_table_driven_field_actions(self):
        from workflow.node_ui_schema import get_node_ui_schema

        schema = get_node_ui_schema(
            "匹配值输出列名",
            preview_headers=["源字段"],
            table_names=["lookup"],
            table_columns={"lookup": ["编码", "名称"]},
        )
        fields = {
            field["key"]: field
            for group in schema["form"]["groups"]
            for field in group["fields"]
        }
        self.assertEqual(fields["lookup_table"]["options_source"], {"type": "table_names"})
        self.assertEqual(fields["lookup_fields"]["type"], "field_multi_select")
        self.assertEqual(fields["lookup_fields"]["options_source"], {"type": "table_columns", "table_field": "lookup_table"})
        self.assertEqual(fields["lookup_fields"]["action"]["key"], "pick_table_fields")
        self.assertEqual(fields["lookup_fields"]["action"]["table_field"], "lookup_table")

    def test_node_ui_schema_exposes_plan_reference_metadata(self):
        from workflow.node_ui_schema import get_node_ui_schema, plan_reference_choices

        plan = {
            "nodes": [
                {"node_type_id": "core.loop_start", "config": {"loop_id": "Loop_A"}},
                {"node_type_id": "core.loop_start", "config": {"loop_id": "Loop_A"}},
                {"node_type_id": "core.jump_anchor", "config": {"anchor_id": "ANCHOR_END"}},
                {"node_type_id": "core.jump_anchor", "config": {"anchor_id": "ANCHOR_NEXT"}},
            ]
        }

        self.assertEqual(plan_reference_choices(plan, "loop_id"), ["Loop_A"])
        self.assertEqual(plan_reference_choices(plan, "anchor_id"), ["ANCHOR_END", "ANCHOR_NEXT"])

        loop_schema = get_node_ui_schema("core.loop_judge", preview_headers=["A"])
        loop_fields = {
            field["key"]: field
            for group in loop_schema["form"]["groups"]
            for field in group["fields"]
        }
        self.assertEqual(loop_fields["loop_id"]["options_source"], {"type": "plan_refs", "ref_kind": "loop_id"})
        self.assertEqual(loop_fields["loop_id"]["action"]["key"], "pick_plan_ref")

        jump_schema = get_node_ui_schema("core.conditional_jump", preview_headers=["A"])
        jump_fields = {
            field["key"]: field
            for group in jump_schema["form"]["groups"]
            for field in group["fields"]
        }
        self.assertEqual(jump_fields["default_anchor_id"]["options_source"], {"type": "plan_refs", "ref_kind": "anchor_id"})
        jump_columns = {
            item["key"]: item
            for item in jump_fields["jump_rules"]["item_schema"]["columns"]
        }
        self.assertEqual(jump_columns["target_anchor_id"]["type"], "select")
        self.assertEqual(jump_columns["target_anchor_id"]["options_source"], {"type": "plan_refs", "ref_kind": "anchor_id"})
        self.assertEqual(jump_columns["target_anchor_id"]["action"]["key"], "pick_plan_ref")

    def test_node_ui_schema_exposes_runtime_reference_metadata_and_capabilities(self):
        from workflow.node_ui_schema import get_node_ui_schema, runtime_reference_choices

        plan = {
            "nodes": [
                {"node_type_id": "core.save_transit", "config": {"transit_name": "中转A"}},
                {"node_type_id": "core.group", "config": {"save_to_transit": True, "output_transit_name": "组输出B"}},
            ]
        }

        self.assertEqual(runtime_reference_choices(plan, "transit_name"), ["中转A", "组输出B"])
        self.assertEqual(runtime_reference_choices(plan, "transit_table"), ["中转A", "组输出B"])

        loop_schema = get_node_ui_schema("core.loop_start", preview_headers=["A"])
        loop_fields = {
            field["key"]: field
            for group in loop_schema["form"]["groups"]
            for field in group["fields"]
        }
        self.assertEqual(loop_fields["transit_table"]["options_source"], {"type": "runtime_refs", "ref_kind": "transit_table"})
        self.assertEqual(loop_fields["transit_table"]["action"]["key"], "pick_runtime_ref")
        self.assertTrue(loop_fields["transit_table"]["ui_capabilities"]["supports_picker"])
        self.assertTrue(loop_fields["transit_table"]["ui_capabilities"]["depends_on_runtime"])
        self.assertTrue(loop_fields["transit_table"]["ui_capabilities"]["allows_manual_input"])

        group_schema = get_node_ui_schema("core.group", preview_headers=["A"])
        group_fields = {
            field["key"]: field
            for group in group_schema["form"]["groups"]
            for field in group["fields"]
        }
        self.assertEqual(group_fields["input_transit_table"]["options_source"], {"type": "runtime_refs", "ref_kind": "transit_table"})
        self.assertEqual(group_fields["output_transit_name"]["options_source"], {"type": "runtime_refs", "ref_kind": "transit_name"})

        write_schema = get_node_ui_schema("选定列写入指定表", preview_headers=["A"])
        write_fields = {
            field["key"]: field
            for group in write_schema["form"]["groups"]
            for field in group["fields"]
        }
        self.assertEqual(write_fields["source_transit_table"]["action"]["key"], "pick_runtime_ref")
        self.assertEqual(write_fields["target_transit_table"]["options_source"], {"type": "runtime_refs", "ref_kind": "transit_table"})

    def test_workflow_facade_describes_shared_picker_context(self):
        from engine.workflow_facade import WorkflowFacade
        from workflow.node_ui_schema import get_node_ui_schema

        plan = {
            "nodes": [
                {"node_type_id": "core.loop_start", "config": {"loop_id": "Loop_A"}},
                {"node_type_id": "core.jump_anchor", "config": {"anchor_id": "ANCHOR_END"}},
                {"node_type_id": "core.save_transit", "config": {"transit_name": "中转A"}},
                {"node_type_id": "core.group", "config": {"save_to_transit": True, "output_transit_name": "组输出B"}},
            ]
        }

        facade = WorkflowFacade()
        loop_context = facade.describe_picker_context(
            plan=plan,
            field_key="loop_id",
            action_key="pick_plan_ref",
            ref_kind="loop_id",
        )["picker_context"]
        self.assertEqual(loop_context["source"], "plan_refs")
        self.assertEqual(loop_context["label"], "循环")
        self.assertEqual(loop_context["candidates"], ["Loop_A"])

        anchor_context = facade.describe_picker_context(
            plan=plan,
            field_key="default_anchor_id",
            action_key="pick_plan_ref",
            ref_kind="anchor_id",
        )["picker_context"]
        self.assertEqual(anchor_context["candidates"], ["ANCHOR_END"])

        transit_context = facade.describe_picker_context(
            plan=plan,
            field_key="transit_table",
            action_key="pick_runtime_ref",
            ref_kind="transit_table",
        )["picker_context"]
        self.assertEqual(transit_context["source"], "runtime_refs")
        self.assertEqual(transit_context["label"], "中转表")
        self.assertEqual(transit_context["candidates"], ["中转A", "组输出B"])

        table_context = facade.describe_picker_context(
            field_key="lookup_table",
            action_key="pick_table_name",
            table_names=["orders", "logs"],
        )["picker_context"]
        self.assertEqual(table_context["source"], "table_names")
        self.assertEqual(table_context["candidates"], ["orders", "logs"])

        table_field_context = facade.describe_picker_context(
            field_key="lookup_field",
            action_key="pick_table_field",
            options_source={"type": "table_columns", "table_field": "lookup_table"},
            table_columns={"orders": ["id", "name"], "logs": ["row_id"]},
            current_values={"lookup_table": "orders"},
        )["picker_context"]
        self.assertEqual(table_field_context["source"], "table_columns")
        self.assertEqual(table_field_context["table_field"], "lookup_table")
        self.assertEqual(table_field_context["table_name"], "orders")
        self.assertEqual(table_field_context["candidates"], ["id", "name"])

        field_values_context = facade.describe_picker_context(
            field_key="right_table",
            options_source={"type": "field_values", "field": "extra_tables", "value_kind": "table_names"},
            table_names=["orders", "logs", "archive"],
            current_values={"extra_tables": ["orders", "archive", "missing"]},
        )["picker_context"]
        self.assertEqual(field_values_context["source"], "field_values")
        self.assertEqual(field_values_context["candidates"], ["orders", "archive"])

        jump_schema = get_node_ui_schema("core.loop_judge", preview_headers=["A"])
        jump_fields = {
            field["key"]: field
            for group in jump_schema["form"]["groups"]
            for field in group["fields"]
        }
        self.assertTrue(jump_fields["loop_id"]["ui_capabilities"]["depends_on_plan"])

    def test_workflow_facade_resolves_generic_node_config_options(self):
        from engine.workflow_facade import WorkflowFacade

        plan = {
            "nodes": [
                {"node_type_id": "core.loop_start", "config": {"loop_id": "Loop_A"}},
                {"node_type_id": "core.jump_anchor", "config": {"anchor_id": "ANCHOR_END"}},
                {"node_type_id": "core.save_transit", "config": {"transit_name": "中转A"}},
            ]
        }
        facade = WorkflowFacade()

        loop_options = facade.resolve_node_config_options(
            "core.loop_judge",
            plan=plan,
            field_key="loop_id",
        )
        self.assertTrue(loop_options["ok"])
        self.assertEqual(loop_options["schema_version"], "node_config_options.v1")
        self.assertEqual(loop_options["source"], "plan_refs")
        self.assertEqual(loop_options["choices"], ["Loop_A"])
        self.assertEqual(loop_options["picker_context"]["ref_kind"], "loop_id")

        jump_options = facade.resolve_node_config_options(
            "core.conditional_jump",
            plan=plan,
            field_key="jump_rules.target_anchor_id",
        )
        self.assertTrue(jump_options["ok"])
        self.assertEqual(jump_options["source"], "plan_refs")
        self.assertEqual(jump_options["choices"], ["ANCHOR_END"])

        table_field_options = facade.resolve_node_config_options(
            "core.match_value_output",
            field_key="lookup_fields",
            current_values={"lookup_table": "orders"},
            table_columns={"orders": ["id", "name"]},
        )
        self.assertTrue(table_field_options["ok"])
        self.assertEqual(table_field_options["source"], "table_columns")
        self.assertEqual(table_field_options["choices"], ["id", "name"])
        self.assertEqual(table_field_options["picker_context"]["table_name"], "orders")

    def test_node_ui_schema_exposes_structured_warning_items(self):
        from workflow.node_ui_schema import get_node_ui_schema

        schema = get_node_ui_schema("core.loop_judge", preview_headers=["A"])
        self.assertTrue(schema["warnings"])
        self.assertTrue(schema["warning_items"])
        self.assertEqual(schema["warning_items"][0]["level"], "warning")
        self.assertEqual(schema["warning_items"][0]["message"], schema["warnings"][0])

    def test_field_help_payload_exposes_shared_context_requirements(self):
        from workflow.node_ui_schema import build_field_help_payload, get_node_ui_schema

        schema = get_node_ui_schema(
            "字段映射写入表",
            preview_headers=["源字段"],
            table_names=["orders", "result"],
            table_columns={"orders": ["id", "name"], "result": ["row_id", "status"]},
        )
        fields = {
            field["key"]: field
            for group in schema["form"]["groups"]
            for field in group["fields"]
        }
        mapping_columns = {
            item["key"]: item
            for item in fields["field_mappings"]["item_schema"]["columns"]
        }

        target_payload = build_field_help_payload("target_table", fields["target_table"])
        self.assertEqual(target_payload["context_requirements"][0]["kind"], "table_names")

        source_payload = build_field_help_payload("source_field", mapping_columns["source_field"])
        source_requirements = source_payload["context_requirements"]
        self.assertEqual(source_requirements[0]["kind"], "table_columns")
        self.assertEqual(source_requirements[0]["table_field"], "source_table")
        self.assertEqual(source_requirements[1]["kind"], "config_field")
        self.assertEqual(source_requirements[1]["field"], "source_table")

        loop_schema = get_node_ui_schema("core.loop_judge", preview_headers=["A"])
        loop_fields = {
            field["key"]: field
            for group in loop_schema["form"]["groups"]
            for field in group["fields"]
        }
        loop_payload = build_field_help_payload("loop_id", loop_fields["loop_id"])
        self.assertEqual(loop_payload["context_requirements"][0]["kind"], "plan_refs")
        self.assertEqual(loop_payload["context_requirements"][0]["ref_kind"], "loop_id")

    def test_field_help_payload_exposes_shared_help_sections(self):
        from workflow.node_ui_schema import build_field_help_payload, get_node_ui_schema

        schema = get_node_ui_schema("core.replace", preview_headers=["A", "B"])
        fields = {
            field["key"]: field
            for group in schema["form"]["groups"]
            for field in group["fields"]
        }
        payload = build_field_help_payload("target_field", fields["target_field"])
        section = payload["sections"][0]

        self.assertEqual(payload["label"], "目标字段")
        self.assertTrue(payload["required"])
        self.assertEqual(payload["action"]["key"], "pick_preview_header")
        self.assertEqual(section["title"], "字段说明")
        joined = "\n".join(section["lines"])
        self.assertIn("必填", joined)
        self.assertIn("支持动作：选择字段", joined)
        self.assertEqual(fields["target_field"]["help_sections"][0]["title"], "字段说明")

        match_payload = build_field_help_payload("match_value_field", fields["match_value_field"])
        match_joined = "\n".join(match_payload["sections"][0]["lines"])
        self.assertIn("动态显示", match_joined)

    def test_field_help_payload_exposes_plugin_ui_metadata(self):
        from workflow.node_ui_schema import build_field_help_payload

        payload = build_field_help_payload("params.limit", {
            "label": "数量",
            "help": "限制处理条数。",
            "warning": "数量过大时可能耗时较久",
            "placeholder": "默认不限制",
            "empty_text": "暂无候选",
            "invalid_value_text": "请输入有效数字",
            "advanced": True,
            "min": 1,
            "max": 99,
            "step": 2,
            "unit": "行",
        })

        joined = "\n".join(payload["sections"][0]["lines"])
        self.assertIn("警告：数量过大时可能耗时较久", joined)
        self.assertIn("占位提示：默认不限制", joined)
        self.assertIn("无候选时提示：暂无候选", joined)
        self.assertIn("无效值提示：请输入有效数字", joined)
        self.assertIn("最小值：1", joined)
        self.assertIn("单位：行", joined)
        self.assertTrue(payload["ui"]["advanced"])
        self.assertEqual(payload["ui"]["placeholder"], "默认不限制")
        self.assertEqual(payload["ui"]["empty_text"], "暂无候选")
        self.assertEqual(payload["ui"]["unit"], "行")

    def test_plan_reference_fields_expose_shared_help_guidance(self):
        from workflow.node_ui_schema import build_field_help_payload, get_node_ui_schema

        schema = get_node_ui_schema("core.loop_judge", preview_headers=["A"])
        fields = {
            field["key"]: field
            for group in schema["form"]["groups"]
            for field in group["fields"]
        }
        loop_payload = build_field_help_payload("loop_id", fields["loop_id"])
        loop_lines = "\n".join(loop_payload["sections"][0]["lines"])
        self.assertIn("候选来源：当前计划中的循环执行起点", loop_lines)
        self.assertIn("请先添加循环执行起点", loop_lines)

        jump_schema = get_node_ui_schema("core.conditional_jump", preview_headers=["A"])
        jump_fields = {
            field["key"]: field
            for group in jump_schema["form"]["groups"]
            for field in group["fields"]
        }
        anchor_payload = build_field_help_payload("default_anchor_id", jump_fields["default_anchor_id"])
        anchor_lines = "\n".join(anchor_payload["sections"][0]["lines"])
        self.assertIn("候选来源：当前计划中的跳转锚点", anchor_lines)
        self.assertIn("请先添加跳转锚点节点", anchor_lines)

    def test_plugin_manifest_schema_keeps_current_manifest_shapes(self):
        schema = load_schema("plugin_manifest.schema.json")
        defs = schema["definitions"]
        parameter_schema = defs["parameterSchema"]

        self.assertTrue(schema.get("additionalProperties"))
        self.assertIn("^(plugin_info|PLUGIN_INFO|info)$", schema["patternProperties"])
        self.assertEqual(
            schema["patternProperties"]["^(plugin_info|PLUGIN_INFO|info)$"]["$ref"],
            "#/definitions/pluginInfo",
        )
        self.assertEqual(defs["pluginInfo"]["required"], ["id", "api_version"])
        self.assertEqual(parameter_schema["type"], "array")
        self.assertEqual(parameter_schema["items"]["required"], ["name", "type"])


if __name__ == "__main__":
    unittest.main()
