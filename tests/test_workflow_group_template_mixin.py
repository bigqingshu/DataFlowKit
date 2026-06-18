# -*- coding: utf-8 -*-
import unittest
from unittest.mock import patch

from workflow.workflow_group_template_mixin import WorkflowGroupTemplateMixin


class FakeWindow(WorkflowGroupTemplateMixin):
    pass


class WorkflowGroupTemplateMixinTests(unittest.TestCase):
    def test_group_list_actions_delegate_to_group_template_ui(self):
        window = FakeWindow()

        with patch("workflow.workflow_group_template_mixin.group_template_ui.merge_selected_nodes_to_group", return_value=True) as merge:
            self.assertTrue(window.merge_selected_nodes_to_group())
        merge.assert_called_once()
        self.assertIs(merge.call_args.args[0], window)
        self.assertIn("messagebox_module", merge.call_args.kwargs)
        self.assertIn("simpledialog_module", merge.call_args.kwargs)

        with patch("workflow.workflow_group_template_mixin.group_template_ui.expand_selected_group", return_value=True) as expand:
            self.assertTrue(window.expand_selected_group())
        expand.assert_called_once()
        self.assertIs(expand.call_args.args[0], window)
        self.assertIn("messagebox_module", expand.call_args.kwargs)

    def test_group_template_pure_wrappers_delegate(self):
        window = FakeWindow()
        config = {"group_name": "G"}
        data = {"template_type": "workflow_group", "nodes": []}

        with patch("workflow.workflow_group_template_mixin.group_template_ui.validate_group_template_data", return_value=(True, "")) as validate:
            self.assertEqual(window.validate_group_template_data(data), (True, ""))
        validate.assert_called_once_with(data)

        with patch("workflow.workflow_group_template_mixin.group_template_ui.build_group_template_data", return_value=data) as build:
            self.assertEqual(window.build_group_template_data(config, group_name="G2"), data)
        build.assert_called_once_with(config, group_name="G2")

        with patch("workflow.workflow_group_template_mixin.group_template_ui.group_config_from_template_data", return_value=config) as restore:
            self.assertEqual(window.group_config_from_template_data(data), config)
        restore.assert_called_once_with(data)

    def test_group_dir_and_file_actions_delegate_with_local_helpers(self):
        window = FakeWindow()
        config = {"group_name": "G"}

        with patch("workflow.workflow_group_template_mixin.group_template_ui.get_group_dir", return_value="groups") as get_dir:
            self.assertEqual(window.get_group_dir(), "groups")
        get_dir.assert_called_once()
        self.assertIs(get_dir.call_args.args[0], window)
        self.assertTrue(callable(get_dir.call_args.args[1]))

        with patch("workflow.workflow_group_template_mixin.group_template_ui.save_group_template_from_config", return_value=True) as save:
            self.assertTrue(window.save_group_template_from_config(config))
        save.assert_called_once()
        self.assertIs(save.call_args.args[0], window)
        self.assertIs(save.call_args.args[1], config)
        self.assertTrue(callable(save.call_args.args[2]))
        self.assertIn("messagebox_module", save.call_args.kwargs)
        self.assertIn("filedialog_module", save.call_args.kwargs)

        with patch("workflow.workflow_group_template_mixin.group_template_ui.load_group_template_dialog", return_value={"ok": True}) as load:
            self.assertEqual(window.load_group_template_dialog(), {"ok": True})
        load.assert_called_once()
        self.assertIs(load.call_args.args[0], window)
        self.assertTrue(callable(load.call_args.args[1]))
        self.assertIn("messagebox_module", load.call_args.kwargs)
        self.assertIn("filedialog_module", load.call_args.kwargs)

        with patch("workflow.workflow_group_template_mixin.group_template_ui.open_group_dir", return_value=True) as open_dir:
            self.assertTrue(window.open_group_dir())
        open_dir.assert_called_once()
        self.assertIs(open_dir.call_args.args[0], window)
        self.assertIn("messagebox_module", open_dir.call_args.kwargs)


if __name__ == "__main__":
    unittest.main()
