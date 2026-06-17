# -*- coding: utf-8 -*-
import unittest

from workflow.clipboard_table_preview_mixin import ClipboardTablePreviewMixin


class FakeVar:
    def __init__(self, value=None):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class FakeTree:
    def __init__(self):
        self.columns = []
        self.items = {}
        self.order = []
        self.tags = {}
        self.selected = None
        self.focused = None
        self.seen = None
        self.next_id = 1

    def __setitem__(self, key, value):
        if key == "columns":
            self.columns = list(value)
            return
        raise KeyError(key)

    def __getitem__(self, key):
        if key == "columns":
            return self.columns
        raise KeyError(key)

    def get_children(self):
        return list(self.order)

    def delete(self, *items):
        if not items:
            return
        for item in items:
            self.items.pop(item, None)
            if item in self.order:
                self.order.remove(item)

    def heading(self, col, text=""):
        pass

    def column(self, col, **kwargs):
        pass

    def tag_configure(self, tag, **kwargs):
        self.tags.setdefault(tag, kwargs)

    def insert(self, parent, index, values=None):
        iid = f"I{self.next_id}"
        self.next_id += 1
        self.items[iid] = {"values": list(values or []), "tags": ()}
        self.order.append(iid)
        return iid

    def item(self, iid, option=None, **kwargs):
        if kwargs:
            self.items[iid].update(kwargs)
        if option is None:
            return self.items[iid]
        return self.items[iid].get(option)

    def selection_set(self, iid):
        self.selected = iid

    def focus(self, iid):
        self.focused = iid

    def see(self, iid):
        self.seen = iid


class ClipboardTablePreviewFakeApp(ClipboardTablePreviewMixin):
    def __init__(self):
        self.raw_data = ""
        self.headers = []
        self.rows = []
        self.first_row_header_var = FakeVar(True)
        self.info_var = FakeVar("")
        self.search_var = FakeVar("")
        self.search_matches = []
        self.search_index = -1
        self.edit_entry = None
        self.tree = FakeTree()


class ClipboardTablePreviewMixinTests(unittest.TestCase):
    def test_parse_data_uses_first_row_as_header_and_refreshes_tree(self):
        app = ClipboardTablePreviewFakeApp()
        app.parse_data("姓名\t年龄\nAlice\t20\nBob")

        self.assertEqual(app.headers, ["姓名", "年龄"])
        self.assertEqual(app.rows, [["Alice", "20"], ["Bob", ""]])
        self.assertEqual(app.tree["columns"], ["姓名", "年龄"])
        self.assertEqual([app.tree.item(iid, "values") for iid in app.tree.get_children()], [["Alice", "20"], ["Bob", ""]])
        self.assertIn("解析完成：2 行 × 2 列", app.info_var.get())

    def test_parse_data_generates_headers_when_first_row_header_disabled(self):
        app = ClipboardTablePreviewFakeApp()
        app.first_row_header_var.set(False)
        app.parse_data("A,B\nC,D")

        self.assertEqual(app.headers, ["列1", "列2"])
        self.assertEqual(app.rows, [["A", "B"], ["C", "D"]])
        self.assertIn("逗号", app.info_var.get())

    def test_make_display_headers_dedupes_empty_and_duplicate_names(self):
        app = ClipboardTablePreviewFakeApp()
        self.assertEqual(app.make_display_headers(["", "字段", "字段", "字段"]), ["列1", "字段", "字段_2", "字段_3"])

    def test_search_next_prev_and_clear_marks(self):
        app = ClipboardTablePreviewFakeApp()
        app.headers = ["姓名"]
        app.rows = [["Alice"], ["Bob"], ["Alicia"]]
        app.refresh_tree()
        app.search_var.set("ali")

        app.search_main_preview()
        first_match = app.search_matches[0]
        second_match = app.search_matches[1]
        self.assertEqual(app.tree.selected, first_match)
        self.assertEqual(app.tree.item(first_match, "tags"), ("search_current",))

        app.search_main_next()
        self.assertEqual(app.tree.selected, second_match)

        app.search_main_prev()
        self.assertEqual(app.tree.selected, first_match)

        app.clear_main_search_marks()
        self.assertEqual(app.search_matches, [])
        self.assertEqual(app.tree.item(first_match, "tags"), ())

    def test_clear_preview_and_promote_next_row(self):
        app = ClipboardTablePreviewFakeApp()
        app.headers = ["旧1", "旧2"]
        app.rows = [["新1", "新2"], ["值1", "值2"]]
        app.refresh_tree()

        app.delete_header_and_promote_next_row()
        self.assertEqual(app.headers, ["新1", "新2"])
        self.assertEqual(app.rows, [["值1", "值2"]])

        app.clear_preview()
        self.assertEqual(app.raw_data, "")
        self.assertEqual(app.headers, [])
        self.assertEqual(app.rows, [])
        self.assertEqual(app.tree["columns"], [])
        self.assertEqual(app.info_var.get(), "已清空预览。")


if __name__ == "__main__":
    unittest.main()
