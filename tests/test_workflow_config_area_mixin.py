# -*- coding: utf-8 -*-
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from workflow.workflow_config_area_mixin import WorkflowConfigAreaMixin


class FakeChild:
    def __init__(self):
        self.destroyed = False

    def destroy(self):
        self.destroyed = True


class FakeFrame:
    def __init__(self, children=None):
        self.children = list(children or [])

    def winfo_children(self):
        return list(self.children)


class FakeCanvas:
    def __init__(self):
        self.configures = []
        self.items = []
        self.binds = []
        self.unbinds = []
        self.y_scrolls = []
        self.x_scrolls = []
        self.moves = []
        self.after_idle_callbacks = []

    def bbox(self, value):
        return (0, 0, 100, 200)

    def configure(self, **kwargs):
        self.configures.append(kwargs)

    def itemconfigure(self, item, **kwargs):
        self.items.append((item, kwargs))

    def bind_all(self, event, callback):
        self.binds.append((event, callback))

    def unbind_all(self, event):
        self.unbinds.append(event)

    def yview_scroll(self, amount, unit):
        self.y_scrolls.append((amount, unit))

    def xview_scroll(self, amount, unit):
        self.x_scrolls.append((amount, unit))

    def yview_moveto(self, value):
        self.moves.append(("y", value))

    def xview_moveto(self, value):
        self.moves.append(("x", value))

    def after_idle(self, callback):
        self.after_idle_callbacks.append(callback)
        callback()


class FakeLabel:
    created = []

    def __init__(self, parent, **kwargs):
        self.parent = parent
        self.kwargs = kwargs
        self.packs = []
        FakeLabel.created.append(self)

    def pack(self, **kwargs):
        self.packs.append(kwargs)


class FakeWindow(WorkflowConfigAreaMixin):
    def __init__(self):
        self.config_canvas = FakeCanvas()
        self.config_canvas_window = "window-id"
        self.children = [FakeChild(), FakeChild()]
        self.config_frame = FakeFrame(self.children)
        self.current_config_widgets = {"x": 1}
        self.separator_widgets = ["sep"]
        self.field_listbox = object()


class WorkflowConfigAreaMixinTests(unittest.TestCase):
    def test_configure_handlers_update_scrollregion_and_width(self):
        window = FakeWindow()

        window._on_config_frame_configure()
        window._on_config_canvas_configure(SimpleNamespace(width=320))

        self.assertEqual(window.config_canvas.configures[0], {"scrollregion": (0, 0, 100, 200)})
        self.assertEqual(window.config_canvas.items, [("window-id", {"width": 320})])

    def test_mousewheel_bindings_and_scroll_handlers(self):
        window = FakeWindow()

        window._bind_config_mousewheel()
        window._on_config_mousewheel(SimpleNamespace(delta=120))
        window._on_config_shift_mousewheel(SimpleNamespace(delta=-240))
        window._unbind_config_mousewheel()

        self.assertEqual([event for event, _ in window.config_canvas.binds], ["<MouseWheel>", "<Shift-MouseWheel>"])
        self.assertEqual(window.config_canvas.y_scrolls, [(-1, "units")])
        self.assertEqual(window.config_canvas.x_scrolls, [(2, "units")])
        self.assertEqual(window.config_canvas.unbinds, ["<MouseWheel>", "<Shift-MouseWheel>"])

    def test_clear_config_frame_resets_widgets_and_scroll_position(self):
        window = FakeWindow()

        window.clear_config_frame()

        self.assertTrue(all(child.destroyed for child in window.children))
        self.assertEqual(window.current_config_widgets, {})
        self.assertEqual(window.separator_widgets, [])
        self.assertIsNone(window.field_listbox)
        self.assertEqual(window.config_canvas.moves, [("y", 0), ("x", 0)])
        self.assertEqual(window.config_canvas.configures[-1], {"scrollregion": (0, 0, 100, 200)})

    def test_show_empty_config_adds_placeholder_label(self):
        window = FakeWindow()
        FakeLabel.created = []

        with patch("workflow.workflow_config_area_mixin.ttk.Label", new=FakeLabel):
            window.show_empty_config()

        self.assertEqual(len(FakeLabel.created), 1)
        label = FakeLabel.created[0]
        self.assertEqual(label.parent, window.config_frame)
        self.assertIn("请先添加并选择一个节点", label.kwargs["text"])
        self.assertEqual(label.kwargs["foreground"], "gray")
        self.assertEqual(label.packs, [{"anchor": "w"}])


if __name__ == "__main__":
    unittest.main()
