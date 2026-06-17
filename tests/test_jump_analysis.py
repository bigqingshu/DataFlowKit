# -*- coding: utf-8 -*-
import unittest

from workflow.jump_analysis import (
    collect_condition_flag_producers,
    collect_jump_anchors,
    collect_jump_relations,
    jump_issue_detail_text,
    jump_validation_summary_text,
    resolve_jump_anchor_index,
    validate_jump_relations,
)


class JumpAnalysisTests(unittest.TestCase):
    def test_collects_anchors_relations_and_flag_producers(self):
        nodes = [
            {"type": "条件判断节点", "name": "判断", "config": {"flag_name": "ok"}},
            {"type": "条件跳转节点", "name": "按结果跳", "config": {
                "flag_name": "ok",
                "jump_rules": [{"value": "Y", "target_anchor_id": "A1"}],
                "default_anchor_id": "END",
            }},
            {"type": "跳转锚点节点", "name": "开始", "config": {"anchor_id": "A1", "anchor_name": "入口"}},
            {"type": "无条件跳转节点", "name": "回跳", "config": {"target_anchor_id": "A1"}},
            {"type": "跳转锚点节点", "name": "结束", "config": {"anchor_id": "END"}},
        ]

        anchors = collect_jump_anchors(nodes)
        relations = collect_jump_relations(nodes, anchors_info=anchors)
        flags = collect_condition_flag_producers(nodes)

        self.assertEqual([item["anchor_id"] for item in anchors["all"]], ["A1", "END"])
        self.assertEqual(flags["ok"][0]["label"], "1.条件判断节点 / 判断")
        self.assertEqual([rel["kind"] for rel in relations], ["条件", "默认", "无条件"])
        self.assertEqual(relations[0]["status"], "有效 -> 节点 3")
        self.assertEqual(resolve_jump_anchor_index("A1", anchors_info=anchors), (2, "有效：节点 3"))

    def test_validate_jump_relations_reports_duplicate_missing_and_back_jump(self):
        nodes = [
            {"type": "跳转锚点节点", "config": {"anchor_id": "A1"}},
            {"type": "条件跳转节点", "config": {"flag_name": "missing", "jump_rules": [{"value": "", "target_anchor_id": "A1"}]}},
            {"type": "跳转锚点节点", "enabled": False, "config": {"anchor_id": "DUP"}},
            {"type": "跳转锚点节点", "enabled": False, "config": {"anchor_id": "DUP"}},
            {"type": "无条件跳转节点", "config": {"target_anchor_id": "NONE"}},
        ]

        issues = validate_jump_relations(nodes)
        messages = [issue["message"] for issue in issues]

        self.assertIn("锚点ID重复：2 个节点使用同一个ID。", messages)
        self.assertIn("未找到条件标志来源：missing", messages)
        self.assertIn("条件规则的条件值为空。", messages)
        self.assertIn("目标锚点在当前节点之前：节点 1", messages)
        self.assertIn("目标锚点不存在：NONE", messages)
        self.assertTrue(jump_validation_summary_text(issues).startswith("跳转校验完成："))

        detail = jump_issue_detail_text(next(issue for issue in issues if issue.get("relation")))
        self.assertIn("关系：", detail)
        self.assertIn("来源：", detail)


if __name__ == "__main__":
    unittest.main()
