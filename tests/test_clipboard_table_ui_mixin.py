# -*- coding: utf-8 -*-
import unittest
from unittest import mock

from workflow.clipboard_table_ui_mixin import ClipboardTableUiMixin


class FakeVar:
    def __init__(self, value=None):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class FakeWidget:
    created = []

    def __init__(self, parent=None, **kwargs):
        self.parent = parent
        self.kwargs = kwargs
        self.pack_calls = []
        self.grid_calls = []
        self.bindings = {}
        self.configures = []
        FakeWidget.created.append(self)

    def pack(self, **kwargs):
        self.pack_calls.append(kwargs)
        return None

    def grid(self, **kwargs):
        self.grid_calls.append(kwargs)
        return None

    def bind(self, event, callback):
        self.bindings[event] = callback

    def configure(self, **kwargs):
        self.configures.append(kwargs)

    def rowconfigure(self, row, weight=0):
        self.row_config = (row, weight)

    def columnconfigure(self, column, weight=0):
        self.column_config = (column, weight)

    def yview(self, *args):
        return None

    def xview(self, *args):
        return None

    def set(self, *args):
        return None


class FakeFrame(FakeWidget):
    pass


class FakeButton(FakeWidget):
    pass


class FakeLabel(FakeWidget):
    pass


class FakeSeparator(FakeWidget):
    pass


class FakeEntry(FakeWidget):
    pass


class FakeCheckbutton(FakeWidget):
    pass


class FakeCombobox(FakeWidget):
    pass


class FakeScrollbar(FakeWidget):
    pass


class FakeTreeview(FakeWidget):
    pass


class FakeTtk:
    Frame = FakeFrame
    Button = FakeButton
    Label = FakeLabel
    Separator = FakeSeparator
    Entry = FakeEntry
    Checkbutton = FakeCheckbutton
    Combobox = FakeCombobox
    Scrollbar = FakeScrollbar
    Treeview = FakeTreeview


class FakeTkModule:
    X = "x"
    BOTH = "both"
    LEFT = "left"
    W = "w"
    VERTICAL = "vertical"
    HORIZONTAL = "horizontal"

    class StringVar(FakeVar):
        pass


class ClipboardTableUiFakeApp(ClipboardTableUiMixin):
    def __init__(self):
        self.root = object()
        self.db_path_var = FakeVar("db.sqlite")
        self.table_name_var = FakeVar("paste_table")
        self.first_row_header_var = FakeVar(True)
        self.recreate_table_var = FakeVar(True)
        self.search_var = FakeVar("")
        self.edit_btn_text = FakeVar("修改模式:关")
        self.refresh_count = 0

    def refresh_table_list(self):
        self.refresh_count += 1

    def load_clipboard(self):
        pass

    def clear_preview(self):
        pass

    def delete_header_and_promote_next_row(self):
        pass

    def toggle_edit_mode(self):
        pass

    def open_plan_workflow(self):
        pass

    def open_batch_replace(self):
        pass

    def open_data_extract(self):
        pass

    def open_merge_columns(self):
        pass

    def open_advanced_filter(self):
        pass

    def export_current_preview_to_xlsx(self):
        pass

    def save_to_sqlite(self):
        pass

    def delete_current_sqlite_table(self):
        pass

    def choose_db(self):
        pass

    def on_table_selected(self, event=None):
        pass

    def reparse_current_raw(self):
        pass

    def search_main_preview(self, reset=True):
        self.last_search_reset = reset

    def search_main_prev(self):
        pass

    def search_main_next(self):
        pass

    def on_tree_double_click(self, event):
        pass


class ClipboardTableUiMixinTests(unittest.TestCase):
    def setUp(self):
        FakeWidget.created = []

    def test_build_ui_creates_main_sections_and_binds_events(self):
        app = ClipboardTableUiFakeApp()
        with mock.patch("workflow.clipboard_table_ui_mixin.ttk", FakeTtk), \
                mock.patch("workflow.clipboard_table_ui_mixin.tk", FakeTkModule):
            top_frame = app.build_ui()

        self.assertIsInstance(top_frame, FakeFrame)
        self.assertEqual(app.refresh_count, 1)
        self.assertIsInstance(app.table_combo, FakeCombobox)
        self.assertIn("<<ComboboxSelected>>", app.table_combo.bindings)
        self.assertIsInstance(app.tree, FakeTreeview)
        self.assertIn("<Double-1>", app.tree.bindings)
        self.assertEqual(app.info_var.get(), "等待读取剪贴板数据。")

        button_texts = [w.kwargs.get("text") for w in FakeWidget.created if isinstance(w, FakeButton)]
        self.assertIn("读取剪贴板并解析", button_texts)
        self.assertIn("搜索", button_texts)
        self.assertIn("删除当前表", button_texts)

        search_entries = [
            w for w in FakeWidget.created
            if isinstance(w, FakeEntry) and w.kwargs.get("textvariable") is app.search_var
        ]
        self.assertEqual(len(search_entries), 1)
        self.assertIn("<Return>", search_entries[0].bindings)
        search_entries[0].bindings["<Return>"](None)
        self.assertTrue(app.last_search_reset)

    def test_build_top_button_bar_uses_edit_textvariable(self):
        app = ClipboardTableUiFakeApp()
        with mock.patch("workflow.clipboard_table_ui_mixin.ttk", FakeTtk), \
                mock.patch("workflow.clipboard_table_ui_mixin.tk", FakeTkModule):
            app.build_top_button_bar()

        edit_buttons = [
            w for w in FakeWidget.created
            if isinstance(w, FakeButton) and w.kwargs.get("textvariable") is app.edit_btn_text
        ]
        self.assertEqual(len(edit_buttons), 1)


if __name__ == "__main__":
    unittest.main()
