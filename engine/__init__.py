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
from engine.issue_schema import (
    has_error_issues,
    is_error_issue,
    make_issue,
    normalize_issue,
    normalize_issues,
)
from engine.job_service import JobService
from engine.models import EngineRunResult, TableData
from engine.output_service import OutputService, OutputSettings
from engine.plan_templates import PlanTemplateService
from engine.safety_policy import SafetyPolicy, resolve_safety_policy
from engine.stdio_worker import StdioWorker
from engine.table_data_service import TableDataService
from engine.workflow_services import WorkflowServices

__all__ = [
    "EngineCancelled",
    "EngineRunResult",
    "HeadlessEngineError",
    "HeadlessWorkflowEngine",
    "JobService",
    "OutputService",
    "OutputSettings",
    "PlanValidationError",
    "PlanTemplateService",
    "SafetyPolicy",
    "StdioWorker",
    "TableDataService",
    "WorkflowServices",
    "TableData",
    "UnsupportedNodeError",
    "has_error_issues",
    "is_error_issue",
    "make_issue",
    "normalize_issue",
    "normalize_issues",
    "resolve_safety_policy",
]
