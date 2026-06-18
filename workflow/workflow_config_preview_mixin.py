# -*- coding: utf-8 -*-
"""Config-pane preview context helpers for PlanWorkflowWindow."""


class WorkflowConfigPreviewMixin:
    """Compatibility methods for computing fields/transit tables before a node."""

    def make_config_preview_context(self):
        """
        配置界面专用的预运行上下文。

        用途：刷新某个节点配置时，会临时运行它前面的节点，以便拿到“到当前节点为止”的字段列表和中转副表。
        这里允许“选定列写入指定表”在配置预运行时写入【当前工作表】和【中转副表】，
        这样后续高级筛选、匹配值输出列名、插件节点等配置界面才能看到这些临时字段。

        注意：selected_columns_config_preview_only 会在该节点内部拦截 SQLite 写入，
        防止只是切换/刷新配置界面时误改真实数据库。
        """
        return {
            "transit_tables": {},
            "loop_states": {},
            "loop_results": {},
            "is_config_probe": True,
            "allow_selected_columns_write_in_preview": True,
            "selected_columns_config_preview_only": True,
        }

    def get_headers_rows_before(self, idx):
        return self.run_plan(
            stop_index=idx - 1,
            raise_error=True,
            initial_context=self.make_config_preview_context(),
        )[:2]

    def get_transit_context_before(self, idx):
        """运行到指定节点之前，取得已经保存的内存中转副表。配置界面用于列出可引用的中转表。"""
        if idx is None or idx <= 0:
            return self.make_config_preview_context()
        try:
            _, _, _, context = self.run_plan(
                stop_index=idx - 1,
                raise_error=False,
                return_context=True,
                initial_context=self.make_config_preview_context(),
            )
            return context
        except Exception:
            return self.make_config_preview_context()
