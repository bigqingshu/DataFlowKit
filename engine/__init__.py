# -*- coding: utf-8 -*-
"""Headless DataFlowKit workflow API.

This package is intentionally UI-free.  It is the first stable surface for
future PyQt, stdio-worker, HTTP, or other frontends to call into the existing
workflow core without importing Tkinter windows.
"""

from engine.errors import (
    EngineCancelled,
    HeadlessEngineError,
    PlanValidationError,
    UnsupportedNodeError,
)
from engine.headless import HeadlessWorkflowEngine
from engine.models import EngineRunResult, TableData
from engine.stdio_worker import StdioWorker

__all__ = [
    "EngineCancelled",
    "EngineRunResult",
    "HeadlessEngineError",
    "HeadlessWorkflowEngine",
    "PlanValidationError",
    "StdioWorker",
    "TableData",
    "UnsupportedNodeError",
]
