# -*- coding: utf-8 -*-
"""Generic toplevel geometry helpers for UI windows."""


class WindowGeometryMixin:
    """Compatibility methods for centering and showing toplevel windows."""

    def center_toplevel(self, win, parent=None, width=None, height=None):
        """把 Toplevel 放到父窗口中心；没有父窗口时放到屏幕中心。"""
        try:
            parent = parent or self.window
            win.update_idletasks()
            w = int(width or win.winfo_width() or win.winfo_reqwidth() or 600)
            h = int(height or win.winfo_height() or win.winfo_reqheight() or 400)
            if parent is not None and parent.winfo_exists():
                parent.update_idletasks()
                px = parent.winfo_rootx()
                py = parent.winfo_rooty()
                pw = parent.winfo_width()
                ph = parent.winfo_height()
                if pw <= 1 or ph <= 1:
                    px = py = 0
                    pw = win.winfo_screenwidth()
                    ph = win.winfo_screenheight()
            else:
                px = py = 0
                pw = win.winfo_screenwidth()
                ph = win.winfo_screenheight()
            x = max(0, px + (pw - w) // 2)
            y = max(0, py + (ph - h) // 2)
            win.geometry(f"{w}x{h}+{x}+{y}" if width or height else f"+{x}+{y}")
        except Exception:
            pass

    def show_centered_toplevel(self, win, parent=None, width=None, height=None):
        self.center_toplevel(win, parent, width, height)
        try:
            win.deiconify()
        except Exception:
            pass
        try:
            win.lift()
        except Exception:
            pass
        try:
            win.focus_set()
        except Exception:
            pass
