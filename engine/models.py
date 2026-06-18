# -*- coding: utf-8 -*-
"""Small serializable data models for the headless workflow API."""

from dataclasses import dataclass, field


def _copy_rows(rows):
    return [list(row) for row in (rows or [])]


@dataclass
class TableData:
    """A plain table payload shared by UI, worker, and workflow APIs."""

    headers: list = field(default_factory=list)
    rows: list = field(default_factory=list)

    @classmethod
    def from_payload(cls, payload=None, *, headers=None, rows=None):
        if isinstance(payload, cls):
            return cls(list(payload.headers), _copy_rows(payload.rows))
        if payload is None:
            return cls(list(headers or []), _copy_rows(rows or []))
        if not isinstance(payload, dict):
            raise ValueError("table payload must be a dict with headers/rows")
        payload_headers = payload.get("headers", headers or [])
        payload_rows = payload.get("rows", rows or [])
        return cls(list(payload_headers or []), _copy_rows(payload_rows or []))

    def to_dict(self):
        return {
            "type": "table",
            "headers": list(self.headers),
            "rows": _copy_rows(self.rows),
        }


@dataclass
class EngineRunResult:
    """Result returned by preview_plan/run_plan."""

    headers: list = field(default_factory=list)
    rows: list = field(default_factory=list)
    logs: list = field(default_factory=list)
    context: dict = field(default_factory=dict)
    steps: int = 0
    pc: int = 0
    cancelled: bool = False

    def to_table(self):
        return TableData(self.headers, self.rows)

    def to_dict(self, include_context=True):
        payload = {
            "ok": not self.cancelled,
            "cancelled": bool(self.cancelled),
            "table": self.to_table().to_dict(),
            "logs": list(self.logs),
            "steps": int(self.steps),
            "pc": int(self.pc),
        }
        if include_context:
            payload["context"] = self.context
        return payload
