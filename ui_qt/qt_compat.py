# -*- coding: utf-8 -*-
"""Small Qt binding compatibility layer.

The prototype supports these bindings, in this order by default:

1. PySide6
2. PyQt6
3. PySide2
4. PyQt5

Qt is optional for the repository. Import this module freely; call ``get_qt``
only in UI entry points that actually need Qt.
"""

from __future__ import annotations

from dataclasses import dataclass
import importlib
import os
from typing import Iterable, List, Optional, Tuple


SUPPORTED_BINDINGS: Tuple[str, ...] = ("PySide6", "PyQt6", "PySide2", "PyQt5")
QT_API_ENV = "DATAFLOWKIT_QT_API"

_ALIASES = {
    "pyside6": "PySide6",
    "pyqt6": "PyQt6",
    "pyside2": "PySide2",
    "pyqt5": "PyQt5",
}


class QtBindingUnavailable(ImportError):
    """Raised when no supported Qt binding can be imported."""


class QtBindingError(RuntimeError):
    """Raised when a Qt binding imports but has an incompatible shape."""


@dataclass(frozen=True)
class QtApi:
    """Loaded Qt modules and normalized metadata."""

    binding: str
    QtCore: object
    QtGui: object
    QtWidgets: object
    Signal: object
    Slot: object
    Property: object

    @property
    def is_qt6(self) -> bool:
        return self.binding.endswith("6")

    @property
    def is_pyside(self) -> bool:
        return self.binding.startswith("PySide")

    @property
    def is_pyqt(self) -> bool:
        return self.binding.startswith("PyQt")


_cached_qt: Optional[QtApi] = None


def normalize_binding(name: str) -> str:
    """Return the canonical binding name or raise ``ValueError``."""

    key = str(name or "").strip().lower()
    if key in _ALIASES:
        return _ALIASES[key]
    allowed = ", ".join(SUPPORTED_BINDINGS)
    raise ValueError(f"Unsupported Qt binding {name!r}. Expected one of: {allowed}")


def binding_candidates(preferred: Optional[str] = None, env: Optional[dict] = None) -> Tuple[str, ...]:
    """Return ordered Qt binding candidates.

    ``preferred`` has highest priority. Otherwise ``DATAFLOWKIT_QT_API`` may
    select a binding. If neither is set, the default candidate order is used.
    """

    source_env = os.environ if env is None else env
    selected = preferred or source_env.get(QT_API_ENV, "")
    if selected:
        return (normalize_binding(selected),)
    return SUPPORTED_BINDINGS


def _import_binding(binding: str) -> QtApi:
    QtCore = importlib.import_module(f"{binding}.QtCore")
    QtGui = importlib.import_module(f"{binding}.QtGui")
    QtWidgets = importlib.import_module(f"{binding}.QtWidgets")

    if binding.startswith("PySide"):
        signal = getattr(QtCore, "Signal", None)
        slot = getattr(QtCore, "Slot", None)
        prop = getattr(QtCore, "Property", None)
    else:
        signal = getattr(QtCore, "pyqtSignal", None)
        slot = getattr(QtCore, "pyqtSlot", None)
        prop = getattr(QtCore, "pyqtProperty", None)

    if signal is None or slot is None or prop is None:
        raise QtBindingError(f"{binding} does not expose the expected signal/slot/property API")

    return QtApi(
        binding=binding,
        QtCore=QtCore,
        QtGui=QtGui,
        QtWidgets=QtWidgets,
        Signal=signal,
        Slot=slot,
        Property=prop,
    )


def load_qt(preferred: Optional[str] = None) -> QtApi:
    """Import and return the first available Qt binding."""

    failures: List[str] = []
    for binding in binding_candidates(preferred):
        try:
            return _import_binding(binding)
        except ImportError as exc:
            failures.append(f"{binding}: {exc}")
        except QtBindingError as exc:
            failures.append(f"{binding}: {exc}")

    tried = ", ".join(binding_candidates(preferred))
    detail = "; ".join(failures) if failures else "no candidates"
    raise QtBindingUnavailable(
        "No supported Qt binding is available. Install PySide6/PyQt6 for modern "
        "Windows, or PySide2/PyQt5 for a Qt5/Win7-compatible line. "
        f"Tried: {tried}. Details: {detail}"
    )


def get_qt(preferred: Optional[str] = None, force_reload: bool = False) -> QtApi:
    """Return a cached Qt binding, loading it on first use."""

    global _cached_qt
    if force_reload or _cached_qt is None or preferred:
        api = load_qt(preferred)
        if not preferred:
            _cached_qt = api
        return api
    return _cached_qt


def exec_qt(obj):
    """Call ``exec`` on Qt6 objects and ``exec_`` on older Qt objects."""

    if hasattr(obj, "exec"):
        return obj.exec()
    return obj.exec_()


def qt_enum(qt: QtApi, group_name: str, member_name: str):
    """Resolve Qt5/Qt6 enum members.

    Qt6 moved many enum values under nested classes, for example
    ``Qt.ItemDataRole.DisplayRole``. Qt5 exposes the same value as
    ``Qt.DisplayRole``. This helper hides that difference.
    """

    qt_namespace = qt.QtCore.Qt
    group = getattr(qt_namespace, group_name, None)
    if group is not None and hasattr(group, member_name):
        return getattr(group, member_name)
    return getattr(qt_namespace, member_name)


def qt_enums(qt: QtApi, group_name: str, member_names: Iterable[str]) -> Tuple[object, ...]:
    """Resolve several enum members from the same Qt enum group."""

    return tuple(qt_enum(qt, group_name, name) for name in member_names)

