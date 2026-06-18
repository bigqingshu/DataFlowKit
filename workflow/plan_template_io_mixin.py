# -*- coding: utf-8 -*-
"""Plan template directory, data, and file IO helpers."""

import os
import re
import sys
from tkinter import filedialog, messagebox

from shared.atomic_json_utils import atomic_write_json, load_json_with_backup


def _default_app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_json_file_with_recovery(path, parent=None):
    data, info = load_json_with_backup(path)
    warning = info.get("warning", "")
    if warning:
        messagebox.showwarning("配置已从备份恢复", warning, parent=parent)
    return data


class PlanTemplateIoMixin:
    """Compatibility methods for workflow plan template IO."""

    def get_plan_dir(self):
        """返回程序真实目录下的 plan 模板目录，并确保目录存在。"""
        base_dir = getattr(getattr(self, "app", None), "app_dir", _default_app_dir())
        plan_dir = os.path.join(base_dir, "plan")
        os.makedirs(plan_dir, exist_ok=True)
        return plan_dir

    def sanitize_plan_file_name(self, name):
        """生成适合作为文件名的计划模板名称。"""
        name = str(name or "工作流计划").strip()
        name = re.sub(r'[\\/:*?"<>|]+', "_", name)
        name = re.sub(r"\s+", "_", name)
        return name or "工作流计划"

    def build_plan_template_data(self, plan_name=None):
        """
        收集当前计划模板数据。新版模板必须带 template_type。

        plan_name 优先由保存时选择的 JSON 文件名传入，
        这样模板下拉菜单中的计划名会和实际保存文件名保持一致。
        """
        plan_name = str(plan_name or "").strip()
        if not plan_name:
            plan_name = self.output_table_var.get().strip() or "工作流计划"

        self.refresh_node_tree_table_access(self.nodes)
        return {
            "template_type": "workflow_plan",
            "version": "1.0",
            "plan_name": plan_name,
            "nodes": self.nodes,
            "output_mode": self.output_mode_var.get(),
            "output_table": self.output_table_var.get(),
            "backup_before_overwrite": self.backup_before_overwrite_var.get(),
            "table_access_policy": self.normalize_table_access_policy(),
        }

    def validate_plan_template_data(self, data):
        """
        只识别新版计划模板：
        - 必须是 dict
        - template_type 必须等于 workflow_plan
        - nodes 必须是 list
        """
        if not isinstance(data, dict):
            return False, "模板内容不是 JSON 对象。"
        if data.get("template_type") != "workflow_plan":
            return False, "template_type 不是 workflow_plan。"
        if not isinstance(data.get("nodes"), list):
            return False, "nodes 字段不存在或不是列表。"
        return True, ""

    def apply_plan_template_data(self, data, source_path=""):
        """把已验证的计划模板应用到当前计划窗口。"""
        ok, reason = self.validate_plan_template_data(data)
        if not ok:
            raise ValueError(reason)

        self.nodes = data.get("nodes", [])
        self.ensure_node_tree_identity(self.nodes)
        self.output_mode_var.set(data.get("output_mode", "输出到主界面预览区"))
        self.output_table_var.set(data.get("output_table", self.make_default_output_table_name()))
        self.backup_before_overwrite_var.set(bool(data.get("backup_before_overwrite", True)))
        self.set_table_access_policy(data.get("table_access_policy", "audit"))
        self.refresh_node_list()
        self.rebuild_current_config()

        if source_path:
            self.status_var.set(f"计划模板已载入：{source_path}")
        else:
            self.status_var.set("计划模板已载入。")

    def open_plan_dir(self):
        """打开程序真实目录下的 plan 模板目录。"""
        os.makedirs(self.plan_dir, exist_ok=True)
        try:
            if hasattr(os, "startfile"):
                os.startfile(self.plan_dir)
            else:
                messagebox.showinfo("plan目录", self.plan_dir)
        except Exception as e:
            messagebox.showerror("打开失败", f"无法打开 plan 目录：\n{self.plan_dir}\n\n{e}")

    def save_plan_template(self):
        os.makedirs(self.plan_dir, exist_ok=True)
        default_name = self.sanitize_plan_file_name(self.output_table_var.get() or "工作流计划") + ".json"
        path = filedialog.asksaveasfilename(
            title="保存计划模板",
            initialdir=self.plan_dir,
            initialfile=default_name,
            defaultextension=".json",
            filetypes=[("JSON模板", "*.json"), ("所有文件", "*.*")],
        )
        if not path:
            return

        # 使用用户实际保存的 JSON 文件名作为 plan_name。
        # 例如保存为“PDF批量重命名.json”，则 JSON 内部写入：
        # "plan_name": "PDF批量重命名"。
        saved_file_name = os.path.basename(path)
        saved_plan_name = os.path.splitext(saved_file_name)[0].strip() or "工作流计划"

        data = self.build_plan_template_data(plan_name=saved_plan_name)
        try:
            atomic_write_json(path, data)
            self.status_var.set(f"计划模板已保存：{path}；plan_name 已同步为：{saved_plan_name}")
            self.refresh_plan_template_list(show_status=False)

            # 保存后尽量自动选中刚保存的模板，便于确认和后续快速载入。
            if hasattr(self, "plan_template_combo") and hasattr(self, "plan_template_map"):
                abs_saved_path = os.path.abspath(path)
                for display_name, template_path in self.plan_template_map.items():
                    if os.path.abspath(template_path) == abs_saved_path:
                        self.plan_template_var.set(display_name)
                        break
        except Exception as e:
            messagebox.showerror("保存失败", str(e))

    def load_plan_template_from_path(self, path):
        if not path:
            return
        if self.nodes:
            ok = messagebox.askyesno(
                "确认载入模板",
                "当前计划已有节点，载入模板会覆盖当前计划。\n是否继续？",
            )
            if not ok:
                return
        try:
            data = load_json_file_with_recovery(path, parent=self.window)
            self.apply_plan_template_data(data, source_path=path)
        except Exception as e:
            messagebox.showerror("载入失败", str(e))

    def load_plan_template(self):
        path = filedialog.askopenfilename(
            title="载入计划模板",
            initialdir=self.plan_dir,
            filetypes=[("JSON模板", "*.json"), ("所有文件", "*.*")],
        )
        if not path:
            return
        self.load_plan_template_from_path(path)

    def load_selected_plan_template(self):
        display = self.plan_template_var.get()
        if not display:
            messagebox.showwarning("提示", "请先从下拉菜单选择一个计划模板。")
            return

        path = self.plan_template_map.get(display)
        if not path:
            self.refresh_plan_template_list(show_status=False)
            path = self.plan_template_map.get(display)

        if not path:
            messagebox.showwarning("提示", "选中的计划模板不存在或已失效，请刷新模板列表。")
            return

        self.load_plan_template_from_path(path)
