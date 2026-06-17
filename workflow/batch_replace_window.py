# -*- coding: utf-8 -*-
"""Batch replace / data processing window."""

import re
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from shared.atomic_json_utils import atomic_write_json, load_json_with_backup


def load_json_file_with_recovery(path, parent=None):
    data, info = load_json_with_backup(path)
    warning = info.get("warning", "")
    if warning:
        messagebox.showwarning("配置已从备份恢复", warning, parent=parent)
    return data


class BatchReplaceWindow:
    # 批量替换 / 数据处理窗口

    OPERATORS = ["包含", "不包含", "完全相等", "不等于", "开头是", "结尾是", "为空", "不为空", "正则匹配"]
    REPLACE_MODES = ["局部替换匹配字符串", "整格替换为新值"]
    SCOPES = ["全部行", "当前选中行"]

    def __init__(self, app):
        self.app = app
        self.window = tk.Toplevel(app.root)
        self.window.title("批量替换 / 数据处理")
        self.window.geometry("1280x760")
        self.window.transient(app.root)

        self.rules = []
        self.preview_changes = []
        self.preview_final_rows = None
        self.last_backup = None

        self.field_var = tk.StringVar(value=app.headers[0] if app.headers else "")
        self.operator_var = tk.StringVar(value="包含")
        self.match_value_var = tk.StringVar()
        self.replace_value_var = tk.StringVar()
        self.replace_mode_var = tk.StringVar(value="局部替换匹配字符串")
        self.scope_var = tk.StringVar(value="全部行")
        self.case_sensitive_var = tk.BooleanVar(value=False)
        self.replace_first_only_var = tk.BooleanVar(value=False)
        self.result_limit_var = tk.StringVar(value="1000")

        self.build_ui()

    def build_ui(self):
        main = ttk.Frame(self.window, padding=8)
        main.pack(fill=tk.BOTH, expand=True)

        rule_frame = ttk.LabelFrame(main, text="1. 替换规则设置", padding=8)
        rule_frame.pack(fill=tk.X)

        ttk.Label(rule_frame, text="目标字段：").grid(row=0, column=0, sticky=tk.W, padx=4, pady=4)
        self.field_combo = ttk.Combobox(rule_frame, textvariable=self.field_var, values=self.app.headers, width=24, state="readonly")
        self.field_combo.grid(row=0, column=1, sticky=tk.W, padx=4, pady=4)

        ttk.Label(rule_frame, text="匹配方式：").grid(row=0, column=2, sticky=tk.W, padx=4, pady=4)
        ttk.Combobox(rule_frame, textvariable=self.operator_var, values=self.OPERATORS, width=14, state="readonly").grid(row=0, column=3, sticky=tk.W, padx=4, pady=4)

        ttk.Label(rule_frame, text="匹配值：").grid(row=0, column=4, sticky=tk.W, padx=4, pady=4)
        ttk.Entry(rule_frame, textvariable=self.match_value_var, width=28).grid(row=0, column=5, sticky=tk.W, padx=4, pady=4)

        ttk.Label(rule_frame, text="替换值：").grid(row=1, column=0, sticky=tk.W, padx=4, pady=4)
        ttk.Entry(rule_frame, textvariable=self.replace_value_var, width=28).grid(row=1, column=1, sticky=tk.W, padx=4, pady=4)

        ttk.Label(rule_frame, text="替换方式：").grid(row=1, column=2, sticky=tk.W, padx=4, pady=4)
        ttk.Combobox(rule_frame, textvariable=self.replace_mode_var, values=self.REPLACE_MODES, width=22, state="readonly").grid(row=1, column=3, sticky=tk.W, padx=4, pady=4)

        ttk.Label(rule_frame, text="作用范围：").grid(row=1, column=4, sticky=tk.W, padx=4, pady=4)
        ttk.Combobox(rule_frame, textvariable=self.scope_var, values=self.SCOPES, width=14, state="readonly").grid(row=1, column=5, sticky=tk.W, padx=4, pady=4)

        ttk.Checkbutton(rule_frame, text="区分大小写", variable=self.case_sensitive_var).grid(row=2, column=1, sticky=tk.W, padx=4, pady=4)
        ttk.Checkbutton(rule_frame, text="只替换第一次出现", variable=self.replace_first_only_var).grid(row=2, column=3, sticky=tk.W, padx=4, pady=4)

        btns = ttk.Frame(rule_frame)
        btns.grid(row=2, column=5, sticky=tk.E, padx=4, pady=4)
        ttk.Button(btns, text="添加当前规则", command=self.add_rule).pack(side=tk.LEFT, padx=3)
        ttk.Button(btns, text="删除选中规则", command=self.delete_selected_rule).pack(side=tk.LEFT, padx=3)
        ttk.Button(btns, text="清空规则", command=self.clear_rules).pack(side=tk.LEFT, padx=3)

        center = ttk.PanedWindow(main, orient=tk.HORIZONTAL)
        center.pack(fill=tk.BOTH, expand=True, pady=8)

        rules_frame = ttk.LabelFrame(center, text="2. 规则列表（为空时，预览/执行会使用上方当前输入规则）", padding=6)
        center.add(rules_frame, weight=1)

        self.rules_tree = ttk.Treeview(
            rules_frame,
            columns=("序号", "字段", "匹配方式", "匹配值", "替换值", "替换方式", "范围", "选项"),
            show="headings",
            height=12
        )
        for col, width in [
            ("序号", 50), ("字段", 120), ("匹配方式", 90), ("匹配值", 150),
            ("替换值", 150), ("替换方式", 150), ("范围", 90), ("选项", 150)
        ]:
            self.rules_tree.heading(col, text=col)
            self.rules_tree.column(col, width=width, anchor=tk.W, stretch=False)

        rules_y = ttk.Scrollbar(rules_frame, orient=tk.VERTICAL, command=self.rules_tree.yview)
        rules_x = ttk.Scrollbar(rules_frame, orient=tk.HORIZONTAL, command=self.rules_tree.xview)
        self.rules_tree.configure(yscrollcommand=rules_y.set, xscrollcommand=rules_x.set)
        self.rules_tree.grid(row=0, column=0, sticky="nsew")
        rules_y.grid(row=0, column=1, sticky="ns")
        rules_x.grid(row=1, column=0, sticky="ew")
        rules_frame.rowconfigure(0, weight=1)
        rules_frame.columnconfigure(0, weight=1)

        preview_frame = ttk.LabelFrame(center, text="3. 替换结果预览", padding=6)
        center.add(preview_frame, weight=2)

        self.preview_tree = ttk.Treeview(
            preview_frame,
            columns=("行号", "字段", "原内容", "新内容", "规则"),
            show="headings",
            height=12
        )
        for col, width in [("行号", 70), ("字段", 120), ("原内容", 260), ("新内容", 260), ("规则", 180)]:
            self.preview_tree.heading(col, text=col)
            self.preview_tree.column(col, width=width, anchor=tk.W, stretch=False)

        prev_y = ttk.Scrollbar(preview_frame, orient=tk.VERTICAL, command=self.preview_tree.yview)
        prev_x = ttk.Scrollbar(preview_frame, orient=tk.HORIZONTAL, command=self.preview_tree.xview)
        self.preview_tree.configure(yscrollcommand=prev_y.set, xscrollcommand=prev_x.set)
        self.preview_tree.grid(row=0, column=0, sticky="nsew")
        prev_y.grid(row=0, column=1, sticky="ns")
        prev_x.grid(row=1, column=0, sticky="ew")
        preview_frame.rowconfigure(0, weight=1)
        preview_frame.columnconfigure(0, weight=1)

        bottom = ttk.Frame(main)
        bottom.pack(fill=tk.X)

        ttk.Label(bottom, text="预览最大显示行数：").pack(side=tk.LEFT, padx=4)
        ttk.Entry(bottom, textvariable=self.result_limit_var, width=8).pack(side=tk.LEFT, padx=4)
        ttk.Button(bottom, text="预览替换结果", command=self.preview_replace).pack(side=tk.LEFT, padx=4)
        ttk.Button(bottom, text="执行替换", command=self.execute_replace).pack(side=tk.LEFT, padx=4)
        ttk.Button(bottom, text="撤销上一次替换", command=self.undo_last_replace).pack(side=tk.LEFT, padx=4)
        ttk.Button(bottom, text="保存规则模板", command=self.save_template).pack(side=tk.LEFT, padx=4)
        ttk.Button(bottom, text="载入规则模板", command=self.load_template).pack(side=tk.LEFT, padx=4)
        ttk.Button(bottom, text="关闭", command=self.window.destroy).pack(side=tk.RIGHT, padx=4)

        self.status_var = tk.StringVar(value="提示：局部替换会把字段内部匹配到的字符串替换掉，例如 123456 中 45 → 54，结果为 123546。")
        ttk.Label(main, textvariable=self.status_var, padding=(0, 6)).pack(fill=tk.X)

    def normalize_rule(self):
        field = self.field_var.get().strip()
        if field not in self.app.headers:
            raise ValueError("请选择有效的目标字段。")

        operator = self.operator_var.get().strip()
        match_value = self.match_value_var.get()
        replace_value = self.replace_value_var.get()
        replace_mode = self.replace_mode_var.get().strip()

        if operator not in ["为空", "不为空"] and match_value == "":
            raise ValueError("匹配值不能为空。若要判断空值，请选择“为空”或“不为空”。")

        if replace_mode == "局部替换匹配字符串" and operator in ["为空", "不为空"]:
            raise ValueError("“为空/不为空”建议使用“整格替换为新值”，局部替换没有可替换的匹配字符串。")

        return {
            "field": field,
            "operator": operator,
            "match_value": match_value,
            "replace_value": replace_value,
            "replace_mode": replace_mode,
            "scope": self.scope_var.get().strip() or "全部行",
            "case_sensitive": bool(self.case_sensitive_var.get()),
            "replace_first_only": bool(self.replace_first_only_var.get())
        }

    def add_rule(self):
        try:
            rule = self.normalize_rule()
        except Exception as e:
            messagebox.showwarning("规则无效", str(e))
            return

        self.rules.append(rule)
        self.refresh_rules_tree()
        self.status_var.set(f"已添加规则：{len(self.rules)} 条。")

    def delete_selected_rule(self):
        selected = self.rules_tree.selection()
        if not selected:
            messagebox.showwarning("提示", "请先选择要删除的规则。")
            return

        indices = sorted([self.rules_tree.index(item) for item in selected], reverse=True)
        for idx in indices:
            if 0 <= idx < len(self.rules):
                self.rules.pop(idx)
        self.refresh_rules_tree()
        self.status_var.set(f"已删除选中规则，剩余 {len(self.rules)} 条。")

    def clear_rules(self):
        self.rules.clear()
        self.refresh_rules_tree()
        self.status_var.set("已清空规则列表。")

    def refresh_rules_tree(self):
        self.rules_tree.delete(*self.rules_tree.get_children())
        for i, rule in enumerate(self.rules, start=1):
            opts = []
            opts.append("区分大小写" if rule.get("case_sensitive") else "忽略大小写")
            opts.append("只替换第一次" if rule.get("replace_first_only") else "替换所有")
            self.rules_tree.insert("", tk.END, values=(
                i,
                rule.get("field", ""),
                rule.get("operator", ""),
                rule.get("match_value", ""),
                rule.get("replace_value", ""),
                rule.get("replace_mode", ""),
                rule.get("scope", "全部行"),
                "；".join(opts)
            ))

    def get_rules_for_action(self):
        if self.rules:
            return list(self.rules)
        return [self.normalize_rule()]

    def get_target_indices(self, scope):
        if scope == "当前选中行":
            selected = self.app.tree.selection()
            if not selected:
                return []
            return sorted({self.app.tree.index(item) for item in selected})
        return list(range(len(self.app.rows)))

    def compare_text(self, text, pattern, rule):
        operator = rule.get("operator", "包含")
        case_sensitive = rule.get("case_sensitive", False)

        text = "" if text is None else str(text)
        pattern = "" if pattern is None else str(pattern)

        if operator == "为空":
            return text == ""
        if operator == "不为空":
            return text != ""

        if operator == "正则匹配":
            flags = 0 if case_sensitive else re.IGNORECASE
            try:
                return re.search(pattern, text, flags) is not None
            except re.error as e:
                raise ValueError(f"正则表达式错误：{e}")

        cmp_text = text if case_sensitive else text.lower()
        cmp_pattern = pattern if case_sensitive else pattern.lower()

        if operator == "包含":
            return cmp_pattern in cmp_text
        if operator == "不包含":
            return cmp_pattern not in cmp_text
        if operator == "完全相等":
            return cmp_text == cmp_pattern
        if operator == "不等于":
            return cmp_text != cmp_pattern
        if operator == "开头是":
            return cmp_text.startswith(cmp_pattern)
        if operator == "结尾是":
            return cmp_text.endswith(cmp_pattern)

        return False

    def build_replaced_text(self, text, rule):
        text = "" if text is None else str(text)
        match_value = str(rule.get("match_value", ""))
        replace_value = str(rule.get("replace_value", ""))
        replace_mode = rule.get("replace_mode", "局部替换匹配字符串")
        operator = rule.get("operator", "包含")
        case_sensitive = rule.get("case_sensitive", False)
        count = 1 if rule.get("replace_first_only", False) else 0

        if replace_mode == "整格替换为新值":
            return replace_value

        if operator == "正则匹配":
            flags = 0 if case_sensitive else re.IGNORECASE
            try:
                return re.sub(match_value, replace_value, text, count=count, flags=flags)
            except re.error as e:
                raise ValueError(f"正则表达式错误：{e}")

        if match_value == "":
            return text

        if case_sensitive:
            return text.replace(match_value, replace_value, count if count else -1)

        return re.sub(re.escape(match_value), replace_value, text, count=count, flags=re.IGNORECASE)

    def normalize_rows_copy(self):
        normalized = []
        col_count = len(self.app.headers)
        for row in self.app.rows:
            fixed = list(row)
            if len(fixed) < col_count:
                fixed += [""] * (col_count - len(fixed))
            if len(fixed) > col_count:
                fixed = fixed[:col_count]
            normalized.append(fixed)
        return normalized

    def compute_changes(self):
        rules = self.get_rules_for_action()
        final_rows = self.normalize_rows_copy()
        changes = []

        for rule_index, rule in enumerate(rules, start=1):
            field = rule.get("field")
            if field not in self.app.headers:
                continue

            col_idx = self.app.headers.index(field)
            target_indices = self.get_target_indices(rule.get("scope", "全部行"))

            for row_idx in target_indices:
                if row_idx < 0 or row_idx >= len(final_rows):
                    continue

                old_value = final_rows[row_idx][col_idx]
                if self.compare_text(old_value, rule.get("match_value", ""), rule):
                    new_value = self.build_replaced_text(old_value, rule)
                    if new_value != old_value:
                        changes.append({
                            "row_index": row_idx,
                            "field": field,
                            "old": old_value,
                            "new": new_value,
                            "rule_index": rule_index,
                            "rule": rule
                        })
                        final_rows[row_idx][col_idx] = new_value

        return changes, final_rows

    def get_preview_limit(self):
        try:
            value = int(self.result_limit_var.get().strip())
            return max(value, 1)
        except Exception:
            return 1000

    def preview_replace(self):
        try:
            changes, final_rows = self.compute_changes()
        except Exception as e:
            messagebox.showerror("预览失败", str(e))
            return

        self.preview_changes = changes
        self.preview_final_rows = final_rows
        self.preview_tree.delete(*self.preview_tree.get_children())

        limit = self.get_preview_limit()
        for change in changes[:limit]:
            self.preview_tree.insert("", tk.END, values=(
                change["row_index"] + 1,
                change["field"],
                change["old"],
                change["new"],
                f"规则{change['rule_index']}"
            ))

        if not changes:
            self.status_var.set("没有找到可替换的数据。")
        else:
            suffix = f"，仅显示前 {limit} 条" if len(changes) > limit else ""
            self.status_var.set(f"预览完成：共 {len(changes)} 处变更{suffix}。")

    def execute_replace(self):
        try:
            changes, final_rows = self.compute_changes()
        except Exception as e:
            messagebox.showerror("执行失败", str(e))
            return

        if not changes:
            messagebox.showinfo("提示", "没有找到可替换的数据。")
            return

        ok = messagebox.askyesno("确认替换", f"本次将修改 {len(changes)} 处内容。\n是否继续？")
        if not ok:
            return

        self.last_backup = [list(row) for row in self.app.rows]
        self.app.rows = final_rows
        self.app.refresh_tree()

        self.preview_changes = changes
        self.preview_final_rows = final_rows
        self.preview_tree.delete(*self.preview_tree.get_children())
        limit = self.get_preview_limit()
        for change in changes[:limit]:
            self.preview_tree.insert("", tk.END, values=(
                change["row_index"] + 1,
                change["field"],
                change["old"],
                change["new"],
                f"规则{change['rule_index']}"
            ))

        self.app.info_var.set(f"批量替换完成：共修改 {len(changes)} 处内容。")
        self.status_var.set(f"执行完成：共修改 {len(changes)} 处内容。可点击“撤销上一次替换”恢复。")

    def undo_last_replace(self):
        if self.last_backup is None:
            messagebox.showwarning("提示", "当前没有可撤销的替换操作。")
            return

        self.app.rows = [list(row) for row in self.last_backup]
        self.app.refresh_tree()
        self.last_backup = None
        self.preview_tree.delete(*self.preview_tree.get_children())
        self.status_var.set("已撤销上一次替换操作。")
        self.app.info_var.set("已撤销上一次批量替换。")

    def save_template(self):
        rules = self.rules
        if not rules:
            try:
                rules = [self.normalize_rule()]
            except Exception as e:
                messagebox.showwarning("规则无效", str(e))
                return

        path = filedialog.asksaveasfilename(
            title="保存替换规则模板",
            defaultextension=".json",
            filetypes=[("JSON 文件", "*.json"), ("所有文件", "*.*")]
        )
        if not path:
            return

        data = {
            "version": 1,
            "type": "batch_replace_template",
            "rules": rules
        }
        try:
            atomic_write_json(path, data)
            self.status_var.set(f"已保存替换规则模板：{path}")
        except Exception as e:
            messagebox.showerror("保存失败", str(e))

    def load_template(self):
        path = filedialog.askopenfilename(
            title="载入替换规则模板",
            filetypes=[("JSON 文件", "*.json"), ("所有文件", "*.*")]
        )
        if not path:
            return

        try:
            data = load_json_file_with_recovery(path, parent=self.window)

            rules = data.get("rules", data if isinstance(data, list) else [])
            valid_rules = []
            for rule in rules:
                if not isinstance(rule, dict):
                    continue
                if rule.get("field") in self.app.headers:
                    valid_rules.append({
                        "field": rule.get("field", ""),
                        "operator": rule.get("operator", "包含"),
                        "match_value": rule.get("match_value", ""),
                        "replace_value": rule.get("replace_value", ""),
                        "replace_mode": rule.get("replace_mode", "局部替换匹配字符串"),
                        "scope": rule.get("scope", "全部行"),
                        "case_sensitive": bool(rule.get("case_sensitive", False)),
                        "replace_first_only": bool(rule.get("replace_first_only", False))
                    })

            self.rules = valid_rules
            self.refresh_rules_tree()
            self.status_var.set(f"已载入模板：{path}，有效规则 {len(valid_rules)} 条。")
        except Exception as e:
            messagebox.showerror("载入失败", str(e))
