# -*- coding: utf-8 -*-
import unittest

from DataFlowKit import PlanWorkflowWindow
from workflow import table_access_window_ui
from workflow import table_access_window_actions
from workflow.table_access_window_callbacks import create_table_access_window_callbacks
from workflow.table_access_window_ui import (
    add_table_access_entry,
    apply_auto_field_mapping_by_name,
    apply_auto_field_mapping_by_order,
    build_table_access_impact_preview,
    build_table_access_permission_check,
    clear_field_mapping,
    delete_table_access_entry,
    delete_field_mapping_entry,
    field_mapping_item,
    field_mapping_mode_display,
    field_mapping_mode_value,
    load_field_form,
    make_table_access_field_key,
    rebuild_table_access,
    render_field_mapping_tree,
    render_table_access_tree,
    reset_field_form,
    save_table_access_entry,
    selected_field_key,
    table_access_field_mapping_mode_choices,
    table_access_field_tree_columns,
    table_access_node_tree_columns,
    table_access_preset_config,
    table_access_preset_choices,
    table_access_role_choices,
    table_access_source_type_choices,
    table_access_table_tree_columns,
    upsert_field_mapping_entry,
)


class DummyTree:
    def __init__(self):
        self.rows = {}
        self.selected = None
        self.focused = None

    def delete(self, *items):
        if not items:
            return
        for item in items:
            self.rows.pop(item, None)

    def get_children(self):
        return list(self.rows)

    def insert(self, parent, index, iid=None, values=()):
        self.rows[str(iid)] = tuple(values)

    def selection(self):
        return [self.selected] if self.selected is not None else []

    def selection_set(self, iid):
        self.selected = str(iid)

    def selection_remove(self, selection):
        selected = set(str(item) for item in (selection or []))
        if self.selected in selected:
            self.selected = None

    def focus(self, iid):
        self.focused = str(iid)


class DummyWidget:
    def __init__(self):
        self.configured = {}

    def configure(self, **kwargs):
        self.configured.update(kwargs)


class DummyVar:
    def __init__(self, value=None):
        self.value = value

    def set(self, value):
        self.value = value

    def get(self):
        return self.value


class DummyWindow:
    def __init__(self):
        self.calls = []

    def current_table_access_window_node(self, state):
        return {"type": "读取", "name": "节点"}

    def current_table_access_window_table_entry(self, state):
        return {"role": "target"}

    def refresh_table_access_window_field_tree(self, state, field_section, field_tree):
        self.calls.append(("refresh_field_tree", state.get("node_index")))

    def refresh_table_access_node_tree(self, node_tree, state):
        self.calls.append(("refresh_node_tree", state.get("node_index")))

    def refresh_table_access_window_table_tree(self, state, table_section, field_section, node_tree, table_tree, field_tree, select_index=None):
        self.calls.append(("refresh_table_tree", select_index))

    def on_table_access_window_node_selected(self, *args, **kwargs):
        self.calls.append(("on_node_selected", kwargs.get("force", False)))

    def on_table_access_window_table_selected(self, *args, **kwargs):
        self.calls.append(("on_table_selected", True))

    def on_table_access_window_field_selected(self, *args, **kwargs):
        self.calls.append(("on_field_selected", True))

    def save_table_access_window_table_entry(self, *args, **kwargs):
        self.calls.append(("save_table_entry", True))

    def add_table_access_window_table_entry(self, *args, **kwargs):
        self.calls.append(("add_table_entry", True))

    def delete_table_access_window_table_entry(self, *args, **kwargs):
        self.calls.append(("delete_table_entry", True))

    def rebuild_table_access_window_default_access(self, *args, **kwargs):
        self.calls.append(("rebuild_default_access", True))

    def check_table_access_window_permissions(self, *args, **kwargs):
        self.calls.append(("check_all_permissions", True))

    def preview_table_access_window_impact(self, *args, **kwargs):
        self.calls.append(("preview_impact", True))

    def apply_table_access_window_table_preset(self, *args, **kwargs):
        self.calls.append(("apply_table_preset", True))

    def save_table_access_window_field_entry(self, *args, **kwargs):
        self.calls.append(("save_field_entry", True))

    def add_table_access_window_field_entry(self, *args, **kwargs):
        self.calls.append(("add_field_entry", True))

    def delete_table_access_window_field_entry(self, *args, **kwargs):
        self.calls.append(("delete_field_entry", True))

    def auto_match_table_access_window_fields(self, *args, **kwargs):
        self.calls.append(("auto_match_fields", True))

    def auto_match_table_access_window_fields_by_order(self, *args, **kwargs):
        self.calls.append(("auto_match_fields_by_order", True))

    def clear_table_access_window_fields(self, *args, **kwargs):
        self.calls.append(("clear_fields", True))


class TableAccessWindowUiTests(unittest.TestCase):
    def make_window_action_fixture(self):
        window = PlanWorkflowWindow.__new__(PlanWorkflowWindow)
        first_entry = {
            "role": "target",
            "source_type": "SQLite表",
            "table": "orders",
            "write_mode": "append",
            "permissions": {"read_table": True, "write_table": True},
            "field_mapping": {
                "amount": {
                    "source_field": "Amount",
                    "target_field": "AmountOut",
                    "permissions": {"read_field": True, "write_field": True},
                }
            },
        }
        second_entry = {
            "role": "output",
            "source_type": "SQLite表",
            "table": "archive",
            "write_mode": "replace_table",
            "permissions": {"write_table": True},
            "field_mapping": {
                "archived": {
                    "source_field": "ArchiveAmount",
                    "target_field": "ArchiveAmountOut",
                    "permissions": {"read_field": True, "write_field": True},
                }
            },
        }
        window.nodes = [
            {"type": "读取", "name": "源", "enabled": True, "table_access": {"tables": []}},
            {"type": "写入", "name": "保存", "enabled": True, "table_access": {"tables": [first_entry, second_entry]}},
        ]
        window.get_node_table_access = lambda node: node.get("table_access", {"tables": []})
        window.mark_node_table_access_manual = lambda node: node.setdefault("table_access", {"tables": []})
        window.table_access_node_status = lambda node: "启用"
        window.table_access_entry_table_label = lambda entry: entry.get("table", "")
        window.table_access_operation_summary = lambda entry: "操作"
        window.table_permission_summary = lambda entry: "权限"
        window.write_mode_display_text = lambda mode: {"append": "追加行", "replace_table": "覆盖表"}.get(mode, mode)
        window.table_access_entry_status = lambda entry: "已授权"
        window.normalize_table_access_write_mode = lambda mode: str(mode or "")
        window.table_access_table_choices = lambda node=None: ["orders", "archive"] if node else []
        window.get_table_access_field_choices = lambda node_index, entry: ["Amount", "AmountOut", "ArchiveAmount", "ArchiveAmountOut", "SavedAmount"]
        window.field_bool_text = lambda value: "是" if value else "否"
        window.field_permission_status = lambda item: "字段已授权"
        window.make_table_access_field_key = lambda mapping, source, target: make_table_access_field_key(mapping, source, target)
        window.table_permission_set = lambda **kwargs: {
            "read_table": bool(kwargs.get("read")),
            "write_table": bool(kwargs.get("write")),
        }
        window.make_table_access_entry = lambda role, table, **kwargs: {
            "role": role,
            "source_type": kwargs.get("source_type", "SQLite表"),
            "table": table,
            "write_mode": kwargs.get("write_mode", ""),
            "permissions": kwargs.get("permissions", {"read_table": True}),
            "field_mapping": kwargs.get("field_mapping", {}),
            "field_mapping_mode": "by_name",
            "log_only": bool(kwargs.get("log_only", False)),
        }

        table_section = {
            "role_var": DummyVar("target"),
            "source_type_var": DummyVar("SQLite表"),
            "table_var": DummyVar("orders"),
            "write_mode_var": DummyVar("append"),
            "field_mapping_mode_var": DummyVar("按字段名"),
            "is_current_var": DummyVar(False),
            "log_only_var": DummyVar(False),
            "permission_vars": {"read_table": DummyVar(True), "write_table": DummyVar(True)},
            "preset_var": DummyVar("自定义"),
            "table_combo": DummyWidget(),
        }
        field_section = {
            "source_field_var": DummyVar(),
            "target_field_var": DummyVar(),
            "source_index_var": DummyVar(),
            "target_index_var": DummyVar(),
            "field_permission_vars": {
                "read_field": DummyVar(),
                "write_field": DummyVar(),
                "create_field": DummyVar(),
                "protect_field": DummyVar(),
            },
            "source_field_combo": DummyWidget(),
            "target_field_combo": DummyWidget(),
        }
        return {
            "window": window,
            "table_section": table_section,
            "field_section": field_section,
            "node_tree": DummyTree(),
            "table_tree": DummyTree(),
            "field_tree": DummyTree(),
            "status_var": DummyVar(),
            "state": {"node_index": 1, "table_index": 0, "field_keys": [], "refreshing_node_tree": False},
        }

    def test_window_column_and_choice_specs(self):
        self.assertEqual(table_access_node_tree_columns()[0], ("index", "#", 44))
        self.assertEqual(table_access_table_tree_columns()[0], ("role", "表角色", 80))
        self.assertEqual(table_access_field_tree_columns()[0], ("source_index", "源序", 48))
        self.assertIn("target", table_access_role_choices())
        self.assertIn("SQLite表", table_access_source_type_choices())
        self.assertIn("追加或更新", table_access_preset_choices())
        self.assertEqual(table_access_field_mapping_mode_choices(), ["按字段名", "按列顺序", "手动"])

    def test_mode_display_and_value(self):
        self.assertEqual(field_mapping_mode_display({"field_mapping_mode": "by_order"}), "按列顺序")
        self.assertEqual(field_mapping_mode_display({"field_mapping_mode": "manual"}), "手动")
        self.assertEqual(field_mapping_mode_display({"field_mapping_mode": "by_name"}), "按字段名")
        self.assertEqual(field_mapping_mode_value("按列顺序"), "by_order")
        self.assertEqual(field_mapping_mode_value("手动"), "manual")
        self.assertEqual(field_mapping_mode_value("按字段名"), "by_name")

    def test_render_table_and_field_trees(self):
        table_tree = DummyTree()
        entries = [{
            "role": "target",
            "table": "src",
            "permissions": {"read_table": True},
            "write_mode": "append",
        }]
        selected = render_table_access_tree(
            table_tree,
            entries,
            table_label=lambda entry: entry["table"],
            operation_summary=lambda entry: "读表",
            permission_summary=lambda entry: "读表",
            write_mode_text=lambda mode: "追加行",
            entry_status=lambda entry: "只读",
            select_index=0,
        )
        self.assertEqual(selected, 0)
        self.assertEqual(table_tree.rows["0"], ("target", "src", "读表", "否", "读表", "追加行", "只读"))
        self.assertEqual(table_tree.selected, "0")

        field_tree = DummyTree()
        entry = {
            "field_mapping": {
                "a": {
                    "source_index": 1,
                    "source_field": "A",
                    "target_index": 2,
                    "target_field": "B",
                    "permissions": {"read_field": True, "write_field": False},
                }
            }
        }
        keys = render_field_mapping_tree(
            field_tree,
            entry,
            bool_text=lambda value: "是" if value else "否",
            permission_status=lambda item: "只读",
        )
        self.assertEqual(keys, ["a"])
        self.assertEqual(field_tree.rows["0"], (1, "A", 2, "B", "是", "否", "否", "否", "只读"))

    def test_field_form_and_mapping_operations(self):
        vars_ = {
            "source": DummyVar(),
            "target": DummyVar(),
            "source_index": DummyVar(),
            "target_index": DummyVar(),
            "perms": {
                "read_field": DummyVar(False),
                "write_field": DummyVar(False),
                "create_field": DummyVar(False),
                "protect_field": DummyVar(False),
            },
        }
        item = {
            "source_field": "A",
            "target_field": "B",
            "source_index": "1",
            "target_index": "2",
            "permissions": {"read_field": True, "protect_field": True},
        }
        load_field_form(
            item,
            vars_["source"],
            vars_["target"],
            vars_["source_index"],
            vars_["target_index"],
            vars_["perms"],
        )
        self.assertEqual(vars_["source"].get(), "A")
        self.assertTrue(vars_["perms"]["read_field"].get())
        self.assertTrue(vars_["perms"]["protect_field"].get())

        reset_field_form(
            vars_["source"],
            vars_["target"],
            vars_["source_index"],
            vars_["target_index"],
            vars_["perms"],
            write_enabled=True,
        )
        self.assertEqual(vars_["source"].get(), "")
        self.assertTrue(vars_["perms"]["read_field"].get())
        self.assertTrue(vars_["perms"]["write_field"].get())
        self.assertFalse(vars_["perms"]["protect_field"].get())

        entry = {}
        key = upsert_field_mapping_entry(
            entry,
            None,
            " A ",
            " B ",
            "1",
            "2",
            "by_name",
            {"read_field": True},
            lambda mapping, source, target: "generated",
        )
        self.assertEqual(key, "generated")
        self.assertEqual(field_mapping_item(entry, "generated")["source_field"], "A")
        self.assertEqual(selected_field_key(["0"], ["generated"]), "generated")
        self.assertTrue(delete_field_mapping_entry(entry, "generated"))
        self.assertEqual(entry["field_mapping"], {})

        entry["field_mapping"] = {"x": {"target_field": "X"}}
        clear_field_mapping(entry)
        self.assertEqual(entry["field_mapping"], {})

    def test_table_entry_operations(self):
        access = {"tables": []}
        result = add_table_access_entry(access, {"role": "source", "table": "src"})
        self.assertEqual(result["table_index"], 0)
        self.assertEqual(access["tables"][0]["role"], "source")

        result = save_table_access_entry(
            access,
            0,
            {
                "role": " target ",
                "source_type": "",
                "table": "",
                "is_current_table": True,
                "log_only": True,
                "write_mode": " append ",
                "field_mapping_mode": "by_order",
                "permissions": {"read_table": 1, "write_table": 0},
            },
            lambda: {"role": "default", "field_mapping": {}},
        )
        entry = result["entry"]
        self.assertEqual(result["table_index"], 0)
        self.assertEqual(entry["role"], "target")
        self.assertEqual(entry["source_type"], "SQLite表")
        self.assertEqual(entry["table"], "__CURRENT_TABLE__")
        self.assertTrue(entry["is_current_table"])
        self.assertTrue(entry["log_only"])
        self.assertEqual(entry["write_mode"], "append")
        self.assertEqual(entry["field_mapping_mode"], "by_order")
        self.assertEqual(entry["permissions"], {"read_table": True, "write_table": False})

        result = save_table_access_entry(
            access,
            None,
            {"table": "out", "permissions": {"read_table": True}},
            lambda: {"field_mapping": {"kept": {}}},
        )
        self.assertEqual(result["table_index"], 1)
        self.assertEqual(access["tables"][1]["table"], "out")
        self.assertEqual(access["tables"][1]["field_mapping"], {"kept": {}})

        result = delete_table_access_entry(access, 0)
        self.assertTrue(result["deleted"])
        self.assertEqual(result["table_index"], 0)
        self.assertEqual(access["tables"][0]["table"], "out")

        node = {"table_access": access}
        default_access = {"version": 1, "tables": [{"role": "current"}]}
        self.assertIs(rebuild_table_access(node, default_access), default_access)
        self.assertIs(node["table_access"], default_access)

    def test_permission_check_and_impact_preview_messages(self):
        nodes = [
            {"type": "读取", "table_access": {"tables": [{"role": "source", "table": "", "permissions": {}}]}},
            {
                "type": "写入",
                "table_access": {
                    "tables": [{
                        "role": "target",
                        "table": "danger",
                        "permissions": {"read_table": True, "replace_table": True},
                    }]
                },
            },
        ]

        def get_access(node):
            return node["table_access"]

        def status(entry):
            if not entry.get("table"):
                return "未绑定"
            if (entry.get("permissions") or {}).get("replace_table"):
                return "危险写入"
            return "只读"

        result = build_table_access_permission_check(nodes, get_access, status)
        self.assertEqual(result["total_nodes"], 2)
        self.assertEqual(result["total_entries"], 2)
        self.assertEqual(result["need_config"], ["1.读取 / source / "])
        self.assertEqual(result["risky"], ["2.写入 / target / danger"])
        self.assertIn("待配置：1 项", result["message"])
        self.assertIn("危险写入：1 项", result["message"])

        preview = build_table_access_impact_preview(
            1,
            {"type": "写入", "name": "保存"},
            {"role": "target", "table": "danger", "write_mode": "append"},
            [("a", {})],
            table_label=lambda entry: entry["table"],
            operation_summary=lambda entry: "写表",
            entry_status=lambda entry: "已授权",
            permission_summary=lambda entry: "读表/写表",
            write_mode_text=lambda mode: "追加行",
        )
        self.assertIn("节点：2.写入 / 保存", preview)
        self.assertIn("实际表：danger", preview)
        self.assertIn("字段映射：1 个", preview)
        self.assertIsNone(build_table_access_impact_preview(0, None, {}, [], None, None, None, None, None))

    def test_auto_field_mapping_helpers(self):
        entry = {"permissions": {"write_table": True, "alter_schema": True}}
        count = apply_auto_field_mapping_by_name(
            entry,
            ["订单 编号", "金额"],
            ["订单_编号", "缺失"],
            lambda value: str(value or "").replace(" ", "_"),
        )
        self.assertEqual(count, 1)
        self.assertEqual(entry["field_mapping_mode"], "by_name")
        item = entry["field_mapping"]["订单_编号"]
        self.assertEqual(item["source_field"], "订单 编号")
        self.assertEqual(item["target_field"], "订单_编号")
        self.assertTrue(item["permissions"]["write_field"])
        self.assertTrue(item["permissions"]["create_field"])

        count = apply_auto_field_mapping_by_order(
            entry,
            ["A", "B"],
            ["X"],
        )
        self.assertEqual(count, 2)
        self.assertEqual(entry["field_mapping_mode"], "by_order")
        self.assertEqual(entry["field_mapping"]["col_1"]["source_field"], "A")
        self.assertEqual(entry["field_mapping"]["col_1"]["target_field"], "X")
        self.assertEqual(entry["field_mapping"]["col_2"]["source_field"], "B")
        self.assertEqual(entry["field_mapping"]["col_2"]["target_field"], "B")

        self.assertEqual(make_table_access_field_key({"字段": {}}, "字段", ""), "字段_2")

    def test_table_access_preset_config(self):
        keys = [
            "read_table",
            "write_table",
            "create_table",
            "append_rows",
            "update_rows",
            "clear_table",
            "replace_table",
            "alter_schema",
        ]
        append_config = table_access_preset_config("追加写入", keys)
        self.assertEqual(append_config["write_mode"], "append")
        self.assertTrue(append_config["permissions"]["append_rows"])
        self.assertTrue(append_config["permissions"]["alter_schema"])
        self.assertFalse(append_config["log_only"])

        log_config = table_access_preset_config("默认读写只记录", keys)
        self.assertTrue(log_config["log_only"])
        self.assertTrue(log_config["permissions"]["update_rows"])
        self.assertIsNone(log_config["write_mode"])

        danger_config = table_access_preset_config("危险全开", keys)
        self.assertTrue(all(danger_config["permissions"].values()))
        self.assertEqual(danger_config["write_mode"], "replace_table")
        self.assertIsNone(table_access_preset_config("不存在", keys))

    def test_window_selection_instance_methods_refresh_forms(self):
        fixture = self.make_window_action_fixture()
        window = fixture["window"]
        table_section = fixture["table_section"]
        field_section = fixture["field_section"]
        node_tree = fixture["node_tree"]
        table_tree = fixture["table_tree"]
        field_tree = fixture["field_tree"]
        status_var = fixture["status_var"]
        state = fixture["state"]
        state["node_index"] = 0
        state["table_index"] = None

        node_tree.selection_set("1")
        window.on_table_access_window_node_selected(
            state,
            table_section,
            field_section,
            node_tree,
            table_tree,
            field_tree,
            status_var,
        )
        self.assertEqual(state["node_index"], 1)
        self.assertEqual(state["table_index"], 0)
        self.assertEqual(table_section["table_var"].get(), "orders")
        self.assertEqual(table_section["write_mode_var"].get(), "append")
        self.assertEqual(table_section["table_combo"].configured["values"], ["orders", "archive"])
        self.assertEqual(field_section["source_field_combo"].configured["values"], ["Amount", "AmountOut", "ArchiveAmount", "ArchiveAmountOut", "SavedAmount"])
        self.assertEqual(state["field_keys"], ["amount"])
        self.assertIn("2.写入 / 保存", status_var.get())

        table_tree.selection_set("1")
        window.on_table_access_window_table_selected(
            state,
            table_section,
            field_section,
            table_tree,
            field_tree,
        )
        self.assertEqual(state["table_index"], 1)
        self.assertEqual(table_section["table_var"].get(), "archive")
        self.assertEqual(table_section["write_mode_var"].get(), "replace_table")
        self.assertEqual(state["field_keys"], ["archived"])

        field_tree.selection_set("0")
        window.on_table_access_window_field_selected(state, field_section, field_tree)
        self.assertEqual(field_section["source_field_var"].get(), "ArchiveAmount")
        self.assertEqual(field_section["target_field_var"].get(), "ArchiveAmountOut")
        self.assertTrue(field_section["field_permission_vars"]["read_field"].get())
        self.assertTrue(field_section["field_permission_vars"]["write_field"].get())

    def test_window_table_and_field_action_instance_methods(self):
        fixture = self.make_window_action_fixture()
        window = fixture["window"]
        table_section = fixture["table_section"]
        field_section = fixture["field_section"]
        node_tree = fixture["node_tree"]
        table_tree = fixture["table_tree"]
        field_tree = fixture["field_tree"]
        status_var = fixture["status_var"]
        state = fixture["state"]
        entry = window.nodes[1]["table_access"]["tables"][0]

        table_section["table_var"].set("orders_saved")
        table_section["write_mode_var"].set("replace_table")
        table_section["field_mapping_mode_var"].set("按列顺序")
        table_section["permission_vars"]["read_table"].set(True)
        table_section["permission_vars"]["write_table"].set(False)
        window.save_table_access_window_table_entry(
            state,
            table_section,
            field_section,
            node_tree,
            table_tree,
            field_tree,
            status_var,
        )
        self.assertEqual(entry["table"], "orders_saved")
        self.assertEqual(entry["write_mode"], "replace_table")
        self.assertEqual(entry["field_mapping_mode"], "by_order")
        self.assertFalse(entry["permissions"]["write_table"])
        self.assertEqual(status_var.get(), "表角色设置已保存。")

        table_section["permission_vars"]["write_table"].set(True)
        field_section["source_field_var"].set("SavedAmount")
        field_section["target_field_var"].set("SavedAmountOut")
        field_section["source_index_var"].set("3")
        field_section["target_index_var"].set("4")
        field_section["field_permission_vars"]["read_field"].set(True)
        field_section["field_permission_vars"]["write_field"].set(True)
        field_section["field_permission_vars"]["create_field"].set(False)
        field_section["field_permission_vars"]["protect_field"].set(False)
        field_tree.selection_set("0")
        state["field_keys"] = ["amount"]
        window.save_table_access_window_field_entry(state, table_section, field_section, field_tree, status_var)
        item = entry["field_mapping"]["amount"]
        self.assertEqual(item["source_field"], "SavedAmount")
        self.assertEqual(item["target_field"], "SavedAmountOut")
        self.assertEqual(item["match_mode"], "by_order")
        self.assertEqual(status_var.get(), "字段映射已保存。")

        window.add_table_access_window_field_entry(table_section, field_section, field_tree)
        self.assertIsNone(field_tree.selected)
        self.assertEqual(field_section["source_field_var"].get(), "")
        self.assertTrue(field_section["field_permission_vars"]["write_field"].get())

        field_tree.selection_set("0")
        state["field_keys"] = ["amount"]
        window.delete_table_access_window_field_entry(state, field_section, field_tree, status_var)
        self.assertNotIn("amount", entry["field_mapping"])
        self.assertEqual(status_var.get(), "字段映射已删除。")

        entry["field_mapping"] = {"a": {}, "b": {}}
        window.clear_table_access_window_fields(state, field_section, field_tree, status_var)
        self.assertEqual(entry["field_mapping"], {})
        self.assertEqual(status_var.get(), "字段映射已清空。")

    def test_ui_action_wrapper_delegates_to_action_module(self):
        calls = []
        sentinel = object()
        original = table_access_window_actions.save_table_access_window_table_entry

        def fake_action(*args):
            calls.append(args)
            return sentinel

        try:
            table_access_window_actions.save_table_access_window_table_entry = fake_action
            result = table_access_window_ui.save_table_access_window_table_entry(
                "window",
                "state",
                "table_section",
                "field_section",
                "node_tree",
                "table_tree",
                "field_tree",
                "status_var",
            )
        finally:
            table_access_window_actions.save_table_access_window_table_entry = original

        self.assertIs(result, sentinel)
        self.assertEqual(
            calls,
            [
                (
                    "window",
                    "state",
                    "table_section",
                    "field_section",
                    "node_tree",
                    "table_tree",
                    "field_tree",
                    "status_var",
                )
            ],
        )

    def test_callback_factories_delegate_to_window_methods(self):
        self.assertIs(
            table_access_window_ui.create_table_access_window_callbacks,
            create_table_access_window_callbacks,
        )
        window = DummyWindow()
        state = {"node_index": 0, "table_index": 0, "field_keys": []}
        table_section = {}
        field_section = {}
        node_tree = DummyTree()
        table_tree = DummyTree()
        field_tree = DummyTree()
        status_var = DummyVar("status")

        callbacks = create_table_access_window_callbacks(
            window,
            object(),
            state,
            table_section,
            field_section,
            node_tree,
            table_tree,
            field_tree,
            status_var,
        )

        callbacks["refresh_node_tree"]()
        callbacks["refresh_table_tree"](2)
        callbacks["on_node_selected"](force=True)
        callbacks["on_table_selected"]()
        callbacks["on_field_selected"]()
        callbacks["add_table_entry"]()
        callbacks["save_table_entry"]()
        callbacks["delete_table_entry"]()
        callbacks["rebuild_default_access"]()
        callbacks["check_all_permissions"]()
        callbacks["preview_impact"]()
        callbacks["apply_table_preset"]()
        callbacks["save_field_entry"]()
        callbacks["add_field_entry"]()
        callbacks["delete_field_entry"]()
        callbacks["auto_match_fields"]()
        callbacks["auto_match_fields_by_order"]()
        callbacks["clear_fields"]()

        self.assertIn(("refresh_node_tree", 0), window.calls)
        self.assertIn(("refresh_table_tree", 2), window.calls)
        self.assertIn(("on_node_selected", True), window.calls)
        self.assertIn(("apply_table_preset", True), window.calls)
        self.assertIn(("clear_fields", True), window.calls)


if __name__ == "__main__":
    unittest.main()
