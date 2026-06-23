# -*- coding: utf-8 -*-
import tempfile
import unittest
from pathlib import Path

from engine.plugin_service import PluginService
from shared.datetime_parse_utils import parse_date_value
from plugins import visual_mapping_write_plan_plugin_v1 as visual


def make_record(row, col, text, source_file="doc.docx", sheet_name="Sheet1"):
    return {
        "source_file": source_file,
        "block_type": "word_table_cell",
        "sheet_name": sheet_name,
        "row_index": row,
        "col_index": col,
        "cell_address": f"R{row}C{col}",
        "text": text,
        "is_merge_origin": True,
        "is_merged": False,
        "row_span": 1,
        "col_span": 1,
    }


class VisualMappingWritePlanTests(unittest.TestCase):
    def linked_event(self, rec, new_text="changed", tags=None):
        return {
            "kind": "普通映射",
            "rule_name": "主规则",
            "match_rule": "主规则",
            "event_tags": tags or ["设计参数变化"],
            "source_file": rec["source_file"],
            "target_file": "out.docx",
            "rec": rec,
            "sheet_name": rec["sheet_name"],
            "row_index": rec["row_index"],
            "col_index": rec["col_index"],
            "old_text": rec["text"],
            "new_text": new_text,
            "mapping_field": "型号",
            "content": {"签名": "张三", "__content_row__": 1},
            "content_row": 1,
        }

    def area_rule(self):
        slot_rule = visual._default_slot_judgement()
        slot_rule.update({
            "sequence_col_offset": 0,
            "date_col_offset": 2,
        })
        return {
            "enabled": True,
            "name": "变更记录",
            "trigger_rule": visual.LINKED_RULE_ANY,
            "target_mode": visual.LINK_TARGET_FIXED_CELL,
            "sheet_name": "Sheet1",
            "row_index": 1,
            "col_index": 1,
            "area_enabled": True,
            "area_row_start_offset": 1,
            "area_row_end_offset": 3,
            "area_col_start_offset": 1,
            "area_col_end_offset": 1,
            "area_write_col_offset": 1,
            "overflow_policy": visual.LINK_OVERFLOW_SLOT_RULE,
            "slot_judgement": slot_rule,
            "value_source": visual.LINK_VALUE_TEMPLATE,
            "value_template": "{统一序号}:{触发新值}",
            "write_mode": visual.LINK_WRITE_REPLACE,
        }

    def global_replace_rule(self, scope="全部", condition_value="old", match_value="old", replace_value="new"):
        return {
            "enabled": True,
            "name": "全局替换",
            "feature_name": "",
            "scope": scope,
            "sheet_name": "",
            "condition_logic": "AND",
            "conditions": [{"join": "AND", "mode": "包含", "value": condition_value}],
            "batch_target_scope": visual.BATCH_TARGET_FULL_TEXT,
            "batch_rules": [{
                "enabled": True,
                "match_mode": "包含",
                "match_value_source": "手动输入",
                "match_value": match_value,
                "replace_value_source": "手动输入",
                "replace_value": replace_value,
                "replace_mode": "局部替换匹配字符串",
                "match_value_field": "",
                "replace_value_field": "",
                "case_sensitive": True,
                "skip_empty_match_value": True,
                "count": "0",
            }],
        }

    def content_context(self):
        tables = {
            "新内容": {
                "type": "table",
                "headers": ["anchor_text", "target_old", "write_value"],
                "rows": [["KEY-001", "old target", "linked value"]],
            }
        }
        context = visual._table_row_context(tables, content_alias="新内容")
        content = context["rows_by_alias"]["新内容"][0]
        return context, content

    def test_match_text_with_sources_reads_current_content_row_field(self):
        table_context, content = self.content_context()
        ok, detail = visual._match_text_with_sources(
            "KEY-001",
            {
                "enabled": True,
                "conditions": [{
                    "mode": "等于",
                    "value_source": "新内容",
                    "value_field": "anchor_text",
                    "row_policy": visual.REPLACE_ROW_CONTENT_ROW,
                }],
            },
            content=content,
            table_context=table_context,
        )
        self.assertTrue(ok, detail)
        self.assertIn("新内容.anchor_text", detail)

    def test_validate_params_rejects_doc_table_without_text_field(self):
        ok, message = visual.validate_params(
            {"doc_table_alias": "文档", "content_table_alias": "新内容"},
            {
                "tables": {
                    "文档": {"type": "table", "headers": ["source_file"], "rows": [["a.docx"]]},
                    "新内容": {"type": "table", "headers": ["value"], "rows": [["x"]]},
                }
            },
            {},
        )
        self.assertFalse(ok)
        self.assertIn("缺少文本字段", message)

    def test_run_returns_clear_error_when_content_table_has_no_fields(self):
        result = visual.run(
            {
                "tables": {
                    "文档": {"type": "table", "headers": ["source_file", "text"], "rows": [["a.docx", "old"]]},
                    "新内容": {"type": "table", "headers": [], "rows": []},
                }
            },
            {"doc_table_alias": "文档", "content_table_alias": "新内容"},
            {},
        )
        self.assertFalse(result["ok"])
        self.assertIn("新内容表没有可用字段", result["message"])

    def test_describe_config_exposes_visual_mapping_protocol(self):
        with tempfile.TemporaryDirectory(dir=".") as temp_dir:
            context = {
                "plugin_data_dir": temp_dir,
                "input_tables": {
                    "文档": {
                        "type": "table",
                        "headers": ["source_file", "block_type", "sheet_name", "row_index", "col_index", "cell_address", "text"],
                        "rows": [["doc.docx", "word_table_cell", "Sheet1", 1, 1, "A1", "old"]],
                    },
                    "新内容": {
                        "type": "table",
                        "headers": ["target_file", "write_value"],
                        "rows": [["out.docx", "new"]],
                    },
                    "辅助": {
                        "type": "table",
                        "headers": ["old", "new"],
                        "rows": [["old", "new"]],
                    },
                },
            }
            cfg = {
                "rules": [{
                    "id": "Sheet1:R1C1",
                    "name": "普通规则",
                    "enabled": True,
                    "feature_name": "主表",
                    "source_locator": {"sheet_name": "Sheet1", "row_index": 1, "col_index": 1, "cell_address": "A1"},
                    "source_match": {"enabled": True, "mode": "包含", "value": "old"},
                    "anchor": {"enabled": False},
                    "mapping": {"content_field": "write_value"},
                }],
                "features": [{
                    "name": "主表",
                    "enabled": True,
                    "logic": "AND",
                    "conditions": [{"join": "AND", "sheet_name": "Sheet1", "mode": "包含", "value": "old"}],
                }],
                "global_rules": [self.global_replace_rule()],
                "linked_rules": [self.area_rule()],
            }
            visual._save_settings(context, {"version": 1, "configs": {"default": cfg}})

            described = visual.describe_config(
                {
                    "config_name": "default",
                    "doc_table_alias": "文档",
                    "content_table_alias": "新内容",
                    "replace_aux_table_alias": "辅助",
                },
                dict(context, settings_warnings=["测试警告"]),
            )
            effect = visual.preview_config_effect(
                {
                    "config_name": "default",
                    "doc_table_alias": "文档",
                    "content_table_alias": "新内容",
                    "replace_aux_table_alias": "辅助",
                },
                dict(context, settings_warnings=["测试警告"]),
            )

        self.assertEqual(described["schema_version"], "DataFlowKit.visual_mapping.config.v1")
        self.assertEqual(described["protocol_family"], "plugin_complex_config")
        self.assertEqual(described["plugin_id"], visual.PLUGIN_INFO["id"])
        self.assertEqual(described["config_key"], "default")
        self.assertTrue(described["capabilities"]["config_patch"])
        self.assertTrue(described["capabilities"]["config_effect_preview"])
        self.assertIn("rules", described["capabilities"]["supported_sections"])
        self.assertEqual(described["warnings"][0]["message"], "测试警告")
        self.assertEqual(described["summary"]["rules"], 1)
        self.assertEqual(described["summary"]["features"], 1)
        self.assertEqual(described["summary"]["global_rules"], 1)
        self.assertEqual(described["summary"]["linked_rules"], 1)
        self.assertIn("write_value", described["context"]["content_fields"])
        self.assertIn("Sheet1", described["context"]["sheet_names"])
        self.assertIn("普通规则", described["context"]["rule_names"])
        self.assertIn("全局:全局替换", described["context"]["rule_names"])
        view_by_id = {view["view_id"]: view for view in described["views"]}
        self.assertEqual(view_by_id["visual_mapping.rules"]["items"][0]["content_field"], "write_value")
        self.assertEqual(view_by_id["visual_mapping.rules"]["items"][0]["mapping"]["content_field"], "write_value")
        self.assertEqual(view_by_id["visual_mapping.rules"]["items"][0]["source_locator"]["row_index"], 1)
        self.assertEqual(view_by_id["visual_mapping.rules"]["section"], "rules")
        self.assertEqual(view_by_id["visual_mapping.rules"]["item_model_key"], "rule_default")
        self.assertEqual(view_by_id["visual_mapping.rules"]["append_value"], {})
        self.assertEqual(view_by_id["visual_mapping.rules"]["item_schema"]["model_key"], "rule_default")
        self.assertEqual(view_by_id["visual_mapping.rules"]["item_schema"]["display_columns"][0]["key"], "enabled")
        rule_schema_columns = {
            column["key"]: column
            for column in view_by_id["visual_mapping.rules"]["item_schema"]["columns"]
        }
        self.assertEqual(rule_schema_columns["mapping.content_field"]["config_path"], ["mapping", "content_field"])
        self.assertEqual(rule_schema_columns["mapping.content_field"]["options_source"]["key"], "content_fields")
        self.assertIn("write_value", rule_schema_columns["mapping.content_field"]["choices"])
        self.assertEqual(rule_schema_columns["source_locator.sheet_name"]["config_path"], ["source_locator", "sheet_name"])
        self.assertIn("Sheet1", rule_schema_columns["source_locator.sheet_name"]["choices"])
        self.assertIn("append_item", view_by_id["visual_mapping.rules"]["patch_operations"])
        self.assertIn("set_enabled", view_by_id["visual_mapping.rules"]["patch_operations"])
        self.assertEqual(view_by_id["visual_mapping.features"]["items"][0]["condition_count"], 1)
        self.assertEqual(view_by_id["visual_mapping.features"]["items"][0]["conditions"][0]["value"], "old")
        self.assertEqual(view_by_id["visual_mapping.features"]["item_model_key"], "feature_default")
        feature_schema_columns = {
            column["key"]: column
            for column in view_by_id["visual_mapping.features"]["item_schema"]["columns"]
        }
        self.assertEqual(feature_schema_columns["logic"]["choices"], ["AND", "OR"])
        self.assertFalse(feature_schema_columns["logic"]["allow_custom"])
        self.assertEqual(view_by_id["visual_mapping.global_rules"]["items"][0]["batch_rule_count"], 1)
        self.assertEqual(view_by_id["visual_mapping.global_rules"]["item_model_key"], "global_rule_default")
        global_schema_columns = {
            column["key"]: column
            for column in view_by_id["visual_mapping.global_rules"]["item_schema"]["columns"]
        }
        self.assertIn(visual.GLOBAL_SCOPE_SPECIAL_OBJECTS, global_schema_columns["scope"]["choices"])
        self.assertIn(visual.BATCH_TARGET_FULL_TEXT, global_schema_columns["batch_target_scope"]["choices"])
        self.assertEqual(view_by_id["visual_mapping.linked_rules"]["items"][0]["target_mode"], visual.LINK_TARGET_FIXED_CELL)
        self.assertEqual(view_by_id["visual_mapping.linked_rules"]["item_model_key"], "linked_rule_default")
        linked_schema_columns = {
            column["key"]: column
            for column in view_by_id["visual_mapping.linked_rules"]["item_schema"]["columns"]
        }
        self.assertIn(visual.LINK_TARGET_FIXED_CELL, linked_schema_columns["target_mode"]["choices"])
        self.assertIn("普通规则", linked_schema_columns["trigger_rule"]["choices"])
        self.assertEqual(linked_schema_columns["value_field"]["options_source"]["key"], "content_fields")
        self.assertIn("visual_mapping.edit.rules", [action["action_id"] for action in described["actions"]])
        self.assertIn("linked_rule_default", described["models"])
        self.assertEqual(effect["schema_version"], "DataFlowKit.visual_mapping.config_effect.v1")
        self.assertEqual(effect["summary"]["配置名称"], "default")
        self.assertEqual(effect["summary"]["单元格映射规则"], 1)
        self.assertEqual(effect["required_input_tables"][0]["alias"], "文档")
        self.assertEqual(effect["required_input_tables"][0]["row_count"], 1)
        self.assertIn("source_file", effect["expected_output_fields"])
        self.assertIn("file_write", [item["kind"] for item in effect["side_effects"]])

    def test_plugin_service_applies_visual_mapping_rules_config_patch(self):
        with tempfile.TemporaryDirectory(dir=".") as temp_dir:
            app_dir = Path(temp_dir)
            plugin_data_dir = app_dir / "plugin_data" / visual.PLUGIN_INFO["id"]
            seed_context = {"plugin_data_dir": str(plugin_data_dir)}
            visual._save_settings(seed_context, {
                "version": 1,
                "configs": {
                    "default": {
                        "rules": [{
                            "id": "old_rule",
                            "name": "旧规则",
                            "enabled": True,
                            "source_locator": {"sheet_name": "Sheet1", "row_index": 1, "col_index": 1},
                            "mapping": {"content_field": "old_field"},
                        }],
                        "features": [],
                        "global_rules": [],
                        "linked_rules": [],
                    }
                },
            })
            service = PluginService(
                plugins_dir=str(Path.cwd() / "plugins"),
                app_dir=str(app_dir),
            )
            config = {"plugin_id": visual.PLUGIN_INFO["id"], "params": {"config_name": "default"}}
            replace_patch = {
                "operation": "replace_item",
                "target": ["plugin_settings", "configs", "default", "rules"],
                "index": 0,
                "value": {
                    "id": "new_rule",
                    "name": "新规则",
                    "enabled": True,
                    "source_locator": {"sheet_name": "Sheet1", "row_index": 2, "col_index": 3},
                    "mapping": {"content_field": "write_value"},
                },
            }
            append_patch = {
                "operation": "append_item",
                "target": ["plugin_settings", "configs", "default", "rules"],
                "value": {"id": "second_rule", "name": "第二规则", "mapping": {"content_field": "extra"}},
            }
            disable_patch = {
                "operation": "set_enabled",
                "target": ["plugin_settings", "configs", "default", "rules"],
                "index": 1,
                "enabled": False,
            }
            standard_update_patch = {
                "schema_version": visual.CONFIG_SCHEMA_VERSION,
                "operation": "update_item",
                "path": ["plugin_settings", "configs", "default", "rules", 0],
                "payload": {
                    "id": "standard_rule",
                    "name": "标准规则",
                    "enabled": True,
                    "source_locator": {"sheet_name": "Sheet1", "row_index": 4, "col_index": 5},
                    "mapping": {"content_field": "standard_value"},
                },
            }
            feature_patch = {
                "operation": "append_item",
                "section": "features",
                "payload": {"name": "协议特征", "conditions": []},
            }

            replaced = service.apply_plugin_config_patch(
                "plugin.visual_mapping_write_plan_v1",
                config=config,
                patch=replace_patch,
            )
            appended = service.apply_plugin_config_patch(
                "plugin.visual_mapping_write_plan_v1",
                config=config,
                patch=append_patch,
            )
            disabled = service.apply_plugin_config_patch(
                "plugin.visual_mapping_write_plan_v1",
                config=config,
                patch=disable_patch,
            )
            standard_updated = service.apply_plugin_config_patch(
                "plugin.visual_mapping_write_plan_v1",
                config=config,
                patch=standard_update_patch,
            )
            feature_added = service.apply_plugin_config_patch(
                "plugin.visual_mapping_write_plan_v1",
                config=config,
                patch=feature_patch,
            )
            visual._settings_path({"plugin_data_dir": str(plugin_data_dir)}).write_text("{broken", encoding="utf-8")
            described_with_warning = service.describe_plugin_config(
                "plugin.visual_mapping_write_plan_v1",
                config=config,
            )
            invalid = service.validate_plugin_config_patch(
                "plugin.visual_mapping_write_plan_v1",
                config=config,
                patch={"operation": "append_item", "section": "unknown", "payload": {}},
            )

        self.assertTrue(replaced["ok"])
        self.assertEqual(replaced["patch"]["schema_version"], visual.CONFIG_SCHEMA_VERSION)
        self.assertEqual(replaced["patch"]["config_name"], "default")
        self.assertEqual(replaced["patch"]["section"], "rules")
        self.assertEqual(replaced["patch"]["path"], ["plugin_settings", "configs", "default", "rules", 0])
        self.assertEqual(replaced["patch"]["payload"]["name"], "新规则")
        self.assertTrue(appended["ok"])
        self.assertTrue(disabled["ok"])
        self.assertEqual(disabled["patch"]["path"], ["plugin_settings", "configs", "default", "rules", 1])
        self.assertEqual(disabled["patch"]["payload"], {"enabled": False})
        self.assertTrue(standard_updated["ok"])
        self.assertEqual(standard_updated["patch"]["operation"], "replace_item")
        self.assertEqual(standard_updated["patch"]["target_index"], 0)
        self.assertEqual(standard_updated["patch"]["path"], ["plugin_settings", "configs", "default", "rules", 0])
        self.assertEqual(standard_updated["description"]["config_schema_version"], visual.CONFIG_SCHEMA_VERSION)
        self.assertEqual(standard_updated["description"]["protocol_family"], "plugin_complex_config")
        self.assertEqual(standard_updated["description"]["config_key"], "default")
        self.assertEqual(standard_updated["description"]["summary"]["rules"], 2)
        self.assertIn("linked_rule_default", standard_updated["description"]["models"])
        self.assertTrue(standard_updated["description"]["capabilities"]["config_patch"])
        self.assertEqual(standard_updated["description"]["plugin_extension"]["protocol_family"], "plugin_complex_config")
        self.assertTrue(feature_added["ok"])
        self.assertEqual(feature_added["patch"]["path"], ["plugin_settings", "configs", "default", "features"])
        plugin_warning_items = [
            item for item in described_with_warning["warning_items"]
            if item.get("source") == "plugin_config"
        ]
        self.assertTrue(plugin_warning_items)
        self.assertIn(plugin_warning_items[0]["message"], described_with_warning["warnings"])
        rules_view = next(
            view for view in standard_updated["description"]["views"]
            if view.get("view_id") == "visual_mapping.rules"
        )
        features_view = next(
            view for view in feature_added["description"]["views"]
            if view.get("view_id") == "visual_mapping.features"
        )
        self.assertEqual(rules_view["items"][0]["name"], "标准规则")
        self.assertEqual(rules_view["items"][0]["content_field"], "standard_value")
        self.assertEqual(rules_view["items"][1]["name"], "第二规则")
        self.assertFalse(rules_view["items"][1]["enabled"])
        self.assertEqual(features_view["items"][-1]["name"], "协议特征")
        self.assertFalse(invalid["ok"])
        self.assertEqual(invalid["issues"][0]["code"], "visual_mapping_config_patch_invalid")

    def test_anchor_match_uses_content_field_value(self):
        table_context, content = self.content_context()
        records = [
            make_record(1, 1, "not this"),
            make_record(5, 1, "KEY-001"),
        ]
        anchor_rec, detail = visual._match_anchor(
            records,
            {
                "enabled": True,
                "axis": "列",
                "index": 1,
                "conditions": [{
                    "mode": "等于",
                    "value_source": "新内容",
                    "value_field": "anchor_text",
                    "row_policy": visual.REPLACE_ROW_CONTENT_ROW,
                }],
            },
            content=content,
            table_context=table_context,
        )
        self.assertIsNotNone(anchor_rec, detail)
        self.assertEqual(anchor_rec["row_index"], 5)

    def test_linked_plan_uses_table_field_context_for_anchor_and_target_match(self):
        table_context, content = self.content_context()
        records = [
            make_record(1, 1, "trigger old"),
            make_record(5, 1, "KEY-001"),
            make_record(5, 2, "old target"),
        ]
        event = {
            "kind": "普通映射",
            "rule_name": "主规则",
            "match_rule": "主规则",
            "source_file": "doc.docx",
            "target_file": "out.docx",
            "rec": records[0],
            "sheet_name": "Sheet1",
            "row_index": 1,
            "col_index": 1,
            "old_text": "trigger old",
            "new_text": "trigger new",
            "content": content,
            "content_row": content["__content_row__"],
        }
        visual._assign_link_event_counts([event])
        linked_rule = {
            "enabled": True,
            "name": "联动字段锚点",
            "trigger_rule": visual.LINKED_RULE_ANY,
            "target_mode": visual.LINK_TARGET_ANCHOR_OFFSET,
            "sheet_name": "Sheet1",
            "row_offset": 0,
            "col_offset": 1,
            "anchor": {
                "enabled": True,
                "axis": "列",
                "index": 1,
                "conditions": [{
                    "mode": "等于",
                    "value_source": "新内容",
                    "value_field": "anchor_text",
                    "row_policy": visual.REPLACE_ROW_CONTENT_ROW,
                }],
            },
            "target_match": {
                "enabled": True,
                "conditions": [{
                    "mode": "等于",
                    "value_source": "新内容",
                    "value_field": "target_old",
                    "row_policy": visual.REPLACE_ROW_CONTENT_ROW,
                }],
            },
            "value_source": visual.LINK_VALUE_CONTENT_FIELD,
            "value_field": "write_value",
            "write_mode": visual.LINK_WRITE_REPLACE,
        }

        rows, matched, skipped, reasons = visual._build_linked_plan_rows(
            [linked_rule],
            [event],
            {"doc.docx": records},
            {},
            table_context=table_context,
        )

        self.assertEqual(matched, 1, reasons)
        self.assertEqual(skipped, 0, reasons)
        self.assertEqual(rows[0][3:8], ["Sheet1", 5, 2, "R5C2", "linked value"])
        self.assertEqual(rows[0][8], "old target")
        self.assertEqual(rows[0][17], visual.DIRECT_WRITE_STRATEGY)

    def test_shared_slot_context_reserves_different_rows_for_each_event(self):
        records = [
            make_record(1, 1, "anchor"),
            make_record(2, 1, ""),
            make_record(2, 2, ""),
            make_record(3, 1, ""),
            make_record(3, 2, ""),
            make_record(4, 1, ""),
            make_record(4, 2, ""),
        ]
        events = [
            self.linked_event(records[0], "A"),
            self.linked_event(records[0], "B"),
        ]
        visual._assign_link_event_counts(events)

        rows, matched, skipped, reasons = visual._build_linked_plan_rows(
            [self.area_rule()],
            events,
            {"doc.docx": records},
            {},
        )

        self.assertEqual((matched, skipped), (2, 0), reasons)
        self.assertEqual([(row[4], row[5]) for row in rows], [(2, 2), (3, 2)])
        self.assertEqual([row[7] for row in rows], ["①:A", "②:B"])

    def test_slot_judgement_prefers_sequence_over_older_date(self):
        records = [
            make_record(1, 1, "anchor"),
            make_record(2, 1, "②"),
            make_record(2, 2, "occupied"),
            make_record(2, 3, "2020-01-01"),
            make_record(3, 1, "①"),
            make_record(3, 2, "occupied"),
            make_record(3, 3, "2025-01-01"),
            make_record(4, 1, "③"),
            make_record(4, 2, "occupied"),
            make_record(4, 3, "2019-01-01"),
        ]
        event = self.linked_event(records[0])
        visual._assign_link_event_counts([event])

        rows, matched, skipped, reasons = visual._build_linked_plan_rows(
            [self.area_rule()],
            [event],
            {"doc.docx": records},
            {},
        )

        self.assertEqual((matched, skipped), (1, 0), reasons)
        self.assertEqual(rows[0][4:6], [3, 2])
        self.assertIn("最小统一序号", rows[0][16])

    def test_slot_judgement_uses_date_to_break_duplicate_sequence(self):
        records = [
            make_record(1, 1, "anchor"),
            make_record(2, 1, "①"),
            make_record(2, 2, "occupied"),
            make_record(2, 3, "2025-01-01"),
            make_record(3, 1, "①"),
            make_record(3, 2, "occupied"),
            make_record(3, 3, "2020-01-01"),
            make_record(4, 1, "②"),
            make_record(4, 2, "occupied"),
            make_record(4, 3, "2019-01-01"),
        ]
        event = self.linked_event(records[0])
        visual._assign_link_event_counts([event])

        rows, matched, skipped, reasons = visual._build_linked_plan_rows(
            [self.area_rule()],
            [event],
            {"doc.docx": records},
            {},
        )

        self.assertEqual((matched, skipped), (1, 0), reasons)
        self.assertEqual(rows[0][4:6], [3, 2])
        self.assertIn("同序号按最早日期", rows[0][16])

    def test_slot_judgement_falls_back_to_date_without_sequence(self):
        records = [
            make_record(1, 1, "anchor"),
            make_record(2, 1, "人工标记"),
            make_record(2, 2, "occupied"),
            make_record(2, 3, "2025/01/01"),
            make_record(3, 1, "人工标记"),
            make_record(3, 2, "occupied"),
            make_record(3, 3, "2020年1月1日"),
            make_record(4, 1, "人工标记"),
            make_record(4, 2, "occupied"),
            make_record(4, 3, "2024.01.01"),
        ]
        event = self.linked_event(records[0])
        visual._assign_link_event_counts([event])

        rows, matched, skipped, reasons = visual._build_linked_plan_rows(
            [self.area_rule()],
            [event],
            {"doc.docx": records},
            {},
        )

        self.assertEqual((matched, skipped), (1, 0), reasons)
        self.assertEqual(rows[0][4:6], [3, 2])
        self.assertIn("无有效统一序号", rows[0][16])

    def test_linked_plan_actions_share_one_allocated_row(self):
        records = [
            make_record(1, 1, "anchor"),
            make_record(2, 1, ""),
            make_record(2, 2, ""),
            make_record(2, 3, ""),
            make_record(2, 4, ""),
        ]
        event = self.linked_event(records[0], "更换型号")
        visual._assign_link_event_counts([event])
        rule = self.area_rule()
        rule["actions"] = [
            {
                "name": "序号",
                "target_mode": visual.LINK_ACTION_SHARED_SLOT,
                "col_offset": -1,
                "value_source": visual.LINK_VALUE_TEMPLATE,
                "value_template": "{统一序号}",
                "write_mode": visual.LINK_WRITE_REPLACE,
            },
            {
                "name": "说明",
                "target_mode": visual.LINK_ACTION_SHARED_SLOT,
                "col_offset": 0,
                "value_source": visual.LINK_VALUE_TEMPLATE,
                "value_template": "{变更字段}:{触发新值}",
                "write_mode": visual.LINK_WRITE_REPLACE,
            },
            {
                "name": "签名",
                "target_mode": visual.LINK_ACTION_SHARED_SLOT,
                "col_offset": 1,
                "value_source": visual.LINK_VALUE_CONTENT_FIELD,
                "value_field": "签名",
                "write_mode": visual.LINK_WRITE_REPLACE,
            },
        ]

        rows, matched, skipped, reasons = visual._build_linked_plan_rows(
            [rule],
            [event],
            {"doc.docx": records},
            {},
        )

        self.assertEqual((matched, skipped), (3, 0), reasons)
        self.assertEqual([(row[4], row[5]) for row in rows], [(2, 1), (2, 2), (2, 3)])
        self.assertEqual([row[7] for row in rows], ["①", "型号:更换型号", "张三"])

    def test_change_log_preset_aligns_sequence_content_signature_and_date_columns(self):
        records = [
            make_record(1, 1, "更改标记"),
            make_record(2, 1, ""),
            make_record(2, 3, ""),
            make_record(2, 4, ""),
            make_record(2, 5, ""),
            make_record(20, 2, "旧型号"),
        ]
        event = self.linked_event(
            records[-1],
            "新型号",
            tags=["需要生成变更记录"],
        )
        visual._assign_link_event_counts([event])
        rule = visual._linked_scheme_presets()["设计文件变更记录（序号优先）"]

        rows, matched, skipped, reasons = visual._build_linked_plan_rows(
            [rule],
            [event],
            {"doc.docx": records},
            {},
        )

        self.assertEqual((matched, skipped), (4, 0), reasons)
        self.assertEqual([(row[4], row[5]) for row in rows], [(2, 1), (2, 3), (2, 4), (2, 5)])
        self.assertEqual(rows[0][7], "①")
        self.assertEqual(rows[1][7], "型号：旧型号 → 新型号")
        self.assertEqual(rows[2][7], "张三")
        self.assertRegex(rows[3][7], r"^\d{4}-\d{2}-\d{2}$")

    def test_linked_rule_can_trigger_by_stable_event_tag(self):
        event = self.linked_event(make_record(1, 1, "old"), tags=["板型号变化"])
        self.assertTrue(visual._linked_rule_matches_event(
            {"trigger_rule": "已改名的规则", "trigger_tags": ["板型号变化"]},
            event,
        ))
        self.assertFalse(visual._linked_rule_matches_event(
            {"trigger_rule": "主规则", "trigger_tags": ["程序编码变化"]},
            event,
        ))

    def test_shared_date_parser_supports_presets_and_validates_date(self):
        self.assertEqual(parse_date_value("日期：2026年6月13日"), (2026, 6, 13))
        self.assertEqual(parse_date_value(
            "260613",
            {
                "input_structure": "固定位置",
                "position_base": "从1开始",
                "year_start": "1",
                "year_len": "2",
                "month_start": "3",
                "month_len": "2",
                "day_start": "5",
                "day_len": "2",
                "year_rule": "20xx",
            },
        ), (2026, 6, 13))
        with self.assertRaises(ValueError):
            parse_date_value("2026-06-31")
        with self.assertRaisesRegex(ValueError, "日期顺序存在歧义"):
            parse_date_value(
                "03/06/26",
                {
                    "input_structure": "分隔符",
                    "date_delimiter": "自动识别",
                    "date_order": "月-日-年",
                    "year_rule": "20xx",
                    "ambiguous_date_policy": "报错",
                },
            )
        self.assertEqual(
            parse_date_value(
                "03/06/26",
                {
                    "input_structure": "分隔符",
                    "date_delimiter": "自动识别",
                    "date_order": "月-日-年",
                    "year_rule": "20xx",
                    "ambiguous_date_policy": "允许",
                },
            ),
            (2026, 3, 6),
        )

    def test_output_row_preserves_meta_json_without_shifting_legacy_columns(self):
        rec = visual._normalize_doc_record(
            [
                "source_file",
                "block_type",
                "sheet_name",
                "row_index",
                "col_index",
                "cell_address",
                "text",
                "meta_json",
            ],
            [
                "doc.docx",
                "word_table_cell",
                "table_2",
                3,
                4,
                "R3C4",
                "old",
                '{"table_index": 2, "cell_index": 9}',
            ],
            1,
            {},
        )
        state = visual._plan_state_for({}, [], "doc.docx", "out.docx", rec)
        visual._update_plan_state(state, "new")
        row = visual._plan_state_to_output_row(state)

        self.assertEqual(row[17], "")
        self.assertEqual(row[18], rec["meta_json"])
        self.assertEqual(row[19], "替换第一次")
        self.assertEqual(row[20:22], ["old", "new"])
        self.assertEqual(
            visual.OUTPUT_HEADERS[18:],
            ["meta_json", "replace_scope", "rule_old_text", "rule_new_text"],
        )

    def test_minimal_text_change_extracts_model_difference(self):
        old_text = "产 品 说 明型号：HYBP2435TK-150RD电脑板"
        new_text = "产 品 说 明型号：HYBP2435TK-51RD电脑板"
        self.assertEqual(visual._minimal_text_change(old_text, new_text), ("150", "51"))

    def test_minimal_text_change_expands_past_duplicate_capacity(self):
        old_text = "名称：Q款变频天花机150冷暖电脑板型号：HYBP2435TK-150RD"
        new_text = "名称：Q款变频天花机150冷暖电脑板型号：HYBP2435TK-51RD"
        old_part, new_part = visual._minimal_text_change(old_text, new_text)

        self.assertEqual(old_text.count(old_part), 1)
        self.assertIn("-150R", old_part)
        self.assertEqual(old_text.replace(old_part, new_part, 1), new_text)

    def test_minimal_text_change_avoids_single_digit_model_rule(self):
        old_text = "设计文件图样HYBP2435TK-150RD电脑板"
        new_text = "设计文件图样HYBP2435TK-120RD电脑板"
        self.assertEqual(visual._minimal_text_change(old_text, new_text), ("150", "120"))

    def test_preview_global_replace_replaces_matching_record(self):
        record = make_record(1, 1, "old value")
        content = {"target_file": "out.docx", "__content_row__": 1}

        preview_rows, total_changed, total_errors = visual._preview_global_replace_rows(
            [self.global_replace_rule()],
            [record],
            [],
            [content],
            [],
            {"planned_file_field": "target_file"},
            include_unchanged=True,
        )

        self.assertEqual(total_changed, 1, preview_rows)
        self.assertEqual(total_errors, 0, preview_rows)
        self.assertEqual(preview_rows[0]["status"], "替换")
        self.assertEqual(preview_rows[0]["new_text"], "new value")

    def test_special_global_replace_rows_sort_long_old_text_first(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            params = {
                "doc_table_alias": "文档",
                "content_table_alias": "新内容",
                "planned_file_field": "target_file",
                "config_name": "special_global_order",
            }
            context = {"plugin_data_dir": temp_dir}
            visual._save_config(params, context, {
                "features": [],
                "rules": [],
                "global_rules": [
                    self.global_replace_rule(
                        scope=visual.GLOBAL_SCOPE_SPECIAL_OBJECTS,
                        condition_value="123",
                        match_value="123",
                        replace_value="B",
                    )
                ],
                "linked_rules": [],
            })
            input_data = {
                "tables": {
                    "文档": {
                        "type": "table",
                        "headers": ["source_file", "block_type", "sheet_name", "row_index", "col_index", "cell_address", "text"],
                        "rows": [
                            ["doc.docx", "word_table_cell", "Sheet1", 1, 1, "R1C1", "123"],
                            ["doc.docx", "word_table_cell", "Sheet1", 1, 2, "R1C2", "123569"],
                        ],
                    },
                    "新内容": {
                        "type": "table",
                        "headers": ["target_file"],
                        "rows": [["out.docx"]],
                    },
                }
            }

            result = visual.run(input_data, params, context)

        self.assertTrue(result["ok"], result)
        rows = result["output"]["rows"]
        self.assertEqual([row[2] for row in rows], ["word_global_replace", "word_global_replace"])
        self.assertEqual([row[8] for row in rows], ["123569", "123"])
        self.assertEqual([row[7] for row in rows], ["B569", "B"])

    def test_run_pipes_normal_mapping_into_global_replace_and_collapses_cell(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            params = {
                "doc_table_alias": "文档",
                "content_table_alias": "新内容",
                "planned_file_field": "target_file",
                "config_name": "pipeline",
            }
            context = {"plugin_data_dir": temp_dir}
            visual._save_config(params, context, {
                "features": [],
                "rules": [{
                    "enabled": True,
                    "name": "普通规则",
                    "feature_name": "",
                    "source_locator": {"sheet_name": "Sheet1", "row_index": 1, "col_index": 1},
                    "source_match": {"enabled": False},
                    "mapping": {"content_field": "write_value"},
                }],
                "global_rules": [self.global_replace_rule()],
                "linked_rules": [],
            })
            input_data = {
                "tables": {
                    "文档": {
                        "type": "table",
                        "headers": ["source_file", "block_type", "sheet_name", "row_index", "col_index", "cell_address", "text"],
                        "rows": [["doc.docx", "word_table_cell", "Sheet1", 1, 1, "R1C1", "source untouched"]],
                    },
                    "新内容": {
                        "type": "table",
                        "headers": ["target_file", "write_value"],
                        "rows": [["out.docx", "normal old value"]],
                    },
                }
            }

            result = visual.run(input_data, params, context)

        self.assertTrue(result["ok"], result)
        rows = result["output"]["rows"]
        self.assertEqual(len(rows), 1, rows)
        self.assertEqual(rows[0][11], "通过")
        self.assertEqual(rows[0][7], "normal new value")
        self.assertEqual(rows[0][8], "source untouched")
        self.assertEqual(rows[0][12], "普通规则 -> 全局:全局替换")
        self.assertIn("普通映射", rows[0][16])
        self.assertIn("全局搜索替换", rows[0][16])

    def test_run_linked_rule_reads_global_replaced_current_text(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            params = {
                "doc_table_alias": "文档",
                "content_table_alias": "新内容",
                "planned_file_field": "target_file",
                "config_name": "linked_after_global",
            }
            context = {"plugin_data_dir": temp_dir}
            visual._save_config(params, context, {
                "features": [],
                "rules": [{
                    "enabled": True,
                    "name": "普通规则",
                    "feature_name": "",
                    "source_locator": {"sheet_name": "Sheet1", "row_index": 1, "col_index": 1},
                    "source_match": {"enabled": False},
                    "mapping": {"content_field": "write_value"},
                }],
                "global_rules": [self.global_replace_rule()],
                "linked_rules": [{
                    "enabled": True,
                    "name": "联动追加",
                    "trigger_rule": "普通规则",
                    "target_mode": visual.LINK_TARGET_FIXED_CELL,
                    "sheet_name": "Sheet1",
                    "row_index": 2,
                    "col_index": 1,
                    "target_match": {
                        "enabled": True,
                        "conditions": [{"mode": "等于", "value": "base new"}],
                    },
                    "value_source": visual.LINK_VALUE_FIXED,
                    "fixed_value": "linked",
                    "write_mode": visual.LINK_WRITE_APPEND,
                    "append_separator": "|",
                }],
            })
            input_data = {
                "tables": {
                    "文档": {
                        "type": "table",
                        "headers": ["source_file", "block_type", "sheet_name", "row_index", "col_index", "cell_address", "text"],
                        "rows": [
                            ["doc.docx", "word_table_cell", "Sheet1", 1, 1, "R1C1", "trigger raw"],
                            ["doc.docx", "word_table_cell", "Sheet1", 2, 1, "R2C1", "base old"],
                        ],
                    },
                    "新内容": {
                        "type": "table",
                        "headers": ["target_file", "write_value"],
                        "rows": [["out.docx", "trigger old"]],
                    },
                }
            }

            result = visual.run(input_data, params, context)

        self.assertTrue(result["ok"], result)
        rows = result["output"]["rows"]
        by_cell = {(row[4], row[5]): row for row in rows}
        self.assertEqual(by_cell[(1, 1)][7], "trigger new")
        self.assertEqual(by_cell[(2, 1)][7], "base new|linked")
        self.assertIn("全局:全局替换", by_cell[(2, 1)][12])
        self.assertIn("联动:联动追加", by_cell[(2, 1)][12])
        self.assertEqual(by_cell[(2, 1)][17], visual.DIRECT_WRITE_STRATEGY)

    def test_expand_template_rejects_missing_field(self):
        with self.assertRaisesRegex(ValueError, "模板缺少字段：不存在"):
            visual._expand_template("{签名}-{不存在}", {"签名": "张三"})

    def test_settings_recovers_from_backup_instead_of_returning_empty_config(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            context = {"plugin_data_dir": temp_dir}
            visual._save_settings(context, {"version": 1, "configs": {"first": {"rules": []}}})
            visual._save_settings(context, {"version": 1, "configs": {"second": {"rules": []}}})
            path = visual._settings_path(context)
            path.write_text("{broken", encoding="utf-8")
            loaded = visual._load_settings(context)
        self.assertIn("first", loaded["configs"])
        self.assertTrue(context.get("settings_warnings"))

    def test_area_slot_scan_rejects_excessive_row_range(self):
        base = make_record(1, 1, "base")
        event = self.linked_event(base)
        rule = self.area_rule()
        rule["area_row_start_offset"] = 0
        rule["area_row_end_offset"] = visual.MAX_AREA_SCAN_ROWS
        target, detail, allocation = visual._linked_select_area_target(
            rule,
            base,
            event,
            [base],
        )
        self.assertIsNone(target)
        self.assertIn("超过安全上限", detail)
        self.assertEqual(allocation, {})


if __name__ == "__main__":
    unittest.main()
