# -*- coding: utf-8 -*-
"""Exceptions raised by the headless workflow API."""


class HeadlessEngineError(Exception):
    """Base class for headless workflow API errors."""


class EngineCancelled(HeadlessEngineError):
    """Raised when a cancel event asks the headless engine to stop."""


class UnsupportedNodeError(HeadlessEngineError):
    """Raised when a plan contains a node that the headless engine cannot run."""


class PlanValidationError(HeadlessEngineError):
    """Raised when a plan cannot be executed by the headless engine."""

    def __init__(self, message, issues=None):
        super().__init__(message)
        self.issues = list(issues or [])
