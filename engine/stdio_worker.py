# -*- coding: utf-8 -*-
"""JSON-lines stdio worker API for non-Python DataFlowKit frontends."""

from __future__ import annotations

import argparse
import json
import sys
import traceback

from engine.errors import PlanValidationError
from engine.headless import HeadlessWorkflowEngine


SUPPORTED_API_VERSION = "1.0"


class StdioWorker:
    """Handle protocol request envelopes using a HeadlessWorkflowEngine."""

    def __init__(self, engine=None):
        self.engine = engine or HeadlessWorkflowEngine()

    def handle_request(self, request):
        request_id = ""
        try:
            if not isinstance(request, dict):
                return self._response("", False, "请求必须是 JSON object", errors=[self._error("invalid_request", "请求必须是 JSON object")])
            request_id = str(request.get("request_id", "") or "")
            api_version = str(request.get("api_version", SUPPORTED_API_VERSION) or "")
            if api_version != SUPPORTED_API_VERSION:
                return self._response(
                    request_id,
                    False,
                    f"不支持的 api_version：{api_version}",
                    errors=[self._error("unsupported_api_version", f"当前支持 {SUPPORTED_API_VERSION}")],
                )

            action = str(request.get("action", "") or "")
            payload = request.get("payload", {})
            if not isinstance(payload, dict):
                return self._response(
                    request_id,
                    False,
                    "payload 必须是 object",
                    errors=[self._error("invalid_payload", "payload 必须是 object")],
                )

            result = self._dispatch(action, payload)
            return self._response(request_id, True, "完成", result=result)
        except PlanValidationError as exc:
            return self._response(
                request_id,
                False,
                str(exc),
                errors=[self._error("plan_validation_error", str(exc), issues=exc.issues)],
            )
        except Exception as exc:
            return self._response(
                request_id,
                False,
                str(exc),
                errors=[self._error("runtime_error", str(exc), traceback=traceback.format_exc())],
            )

    def _dispatch(self, action, payload):
        if action == "list_node_types":
            return {
                "node_types": self.engine.list_node_types(
                    include_unsupported=bool(payload.get("include_unsupported", True))
                ),
                "node_type_ids": self.engine.list_node_type_ids(
                    include_unsupported=bool(payload.get("include_unsupported", True))
                ),
                "node_catalog": self.engine.list_node_catalog(
                    include_unsupported=bool(payload.get("include_unsupported", True))
                ),
            }
        if action == "list_node_ui_schemas":
            return {
                "node_ui_schemas": self.engine.list_node_ui_schemas(
                    include_unsupported=bool(payload.get("include_unsupported", True)),
                    preview_headers=payload.get("preview_headers"),
                    table_names=payload.get("table_names"),
                    table_columns=payload.get("table_columns"),
                )
            }
        if action == "get_node_ui_schema":
            node_type = payload.get("node_type") or payload.get("type") or payload.get("node_type_id")
            return self.engine.get_node_ui_schema(
                node_type,
                preview_headers=payload.get("preview_headers"),
                table_names=payload.get("table_names"),
                table_columns=payload.get("table_columns"),
            )
        if action == "migrate_plan":
            return self.engine.migrate_plan(
                payload.get("plan", {}),
                target_version=payload.get("target_version") or payload.get("protocol_version"),
            )
        if action == "list_plan_templates":
            return self.engine.list_plan_templates(payload.get("plan_dir", "plan"))
        if action == "load_plan_template":
            return self.engine.load_plan_template(
                payload.get("path", ""),
                migrate=bool(payload.get("migrate", True)),
                target_version=payload.get("target_version") or payload.get("protocol_version"),
            )
        if action == "save_plan_template":
            return self.engine.save_plan_template(
                payload.get("path", ""),
                payload.get("plan", {}),
                headers=payload.get("headers"),
                rows=payload.get("rows"),
                output_mode=payload.get("output_mode"),
                output_table=payload.get("output_table"),
                backup_before_overwrite=payload.get("backup_before_overwrite"),
                db_path=payload.get("db_path") or payload.get("output_db_path"),
                output_path=payload.get("output_path"),
                migrate=bool(payload.get("migrate", True)),
                target_version=payload.get("target_version") or payload.get("protocol_version"),
            )
        if action == "validate_plan_template":
            return self.engine.validate_plan_template(payload.get("plan", {}))
        if action == "get_node_type":
            node_type = payload.get("node_type") or payload.get("type") or payload.get("node_type_id")
            return self.engine.get_node_type(
                node_type,
                preview_headers=payload.get("preview_headers"),
                table_names=payload.get("table_names"),
                table_columns=payload.get("table_columns"),
            )
        if action == "make_default_node":
            node_type = payload.get("node_type") or payload.get("type") or payload.get("node_type_id")
            return {
                "node": self.engine.make_default_node(
                    node_type,
                    preview_headers=payload.get("preview_headers"),
                    table_names=payload.get("table_names"),
                    table_columns=payload.get("table_columns"),
                    name=payload.get("name"),
                    include_legacy_type=bool(payload.get("include_legacy_type", True)),
                )
            }
        if action == "apply_plan_command":
            return self.engine.apply_plan_command(
                payload.get("plan", {}),
                payload.get("command", {}),
                preview_headers=payload.get("preview_headers"),
                table_names=payload.get("table_names"),
                table_columns=payload.get("table_columns"),
            )
        if action == "validate_config":
            node = payload.get("node")
            node_or_type = node if isinstance(node, dict) else (
                payload.get("node_type") or payload.get("type") or payload.get("node_type_id")
            )
            return self.engine.validate_config(
                node_or_type,
                payload.get("config"),
                preview_headers=payload.get("preview_headers"),
                table_names=payload.get("table_names"),
                table_columns=payload.get("table_columns"),
            )
        if action == "validate_plan_configs":
            return self.engine.validate_plan_configs(
                payload.get("plan", {}),
                preview_headers=payload.get("preview_headers"),
                table_names=payload.get("table_names"),
                table_columns=payload.get("table_columns"),
            )
        if action == "validate_plan":
            return self.engine.validate_plan(
                payload.get("plan", {}),
                stop_index=self._optional_int(payload.get("stop_at", payload.get("stop_index"))),
                start_index=int(payload.get("start_index", 0) or 0),
            )
        if action == "preview_plan":
            result = self.engine.preview_plan(
                payload.get("plan", {}),
                input_table=payload.get("input_data", payload.get("input_table")),
                stop_index=self._optional_int(payload.get("stop_at", payload.get("stop_index"))),
                start_index=int(payload.get("start_index", 0) or 0),
                initial_context=payload.get("context"),
                dry_run=bool(payload.get("dry_run", True)),
                safety_mode=payload.get("safety_mode"),
                return_context=bool(payload.get("return_context", True)),
            )
            return result.to_dict(include_context=bool(payload.get("return_context", True)))
        if action == "run_plan":
            result = self.engine.run_plan(
                payload.get("plan", {}),
                input_table=payload.get("input_data", payload.get("input_table")),
                execute_actions=bool(payload.get("execute_actions", True)),
                dry_run=bool(payload.get("dry_run", False)),
                safety_mode=payload.get("safety_mode"),
                stop_index=self._optional_int(payload.get("stop_at", payload.get("stop_index"))),
                start_index=int(payload.get("start_index", 0) or 0),
                initial_context=payload.get("context"),
                return_context=bool(payload.get("return_context", True)),
            )
            return result.to_dict(include_context=bool(payload.get("return_context", True)))
        if action == "start_job":
            job_action = payload.get("job_action") or payload.get("mode") or "preview_plan"
            return self.engine.start_job(job_action, payload)
        if action == "cancel_job":
            return self.engine.cancel_job(payload.get("job_id", ""))
        if action == "get_job_status":
            return self.engine.get_job_status(
                payload.get("job_id", ""),
                include_result=bool(payload.get("include_result", True)),
            )
        if action == "get_job_events":
            return self.engine.get_job_events(
                payload.get("job_id", ""),
                since=int(payload.get("since", 0) or 0),
            )
        if action == "list_output_modes":
            return self.engine.list_output_modes()
        if action == "apply_output":
            return self.engine.apply_output(
                headers=payload.get("headers"),
                rows=payload.get("rows"),
                logs=payload.get("logs"),
                settings=payload.get("settings"),
                output_mode=payload.get("output_mode"),
                output_table=payload.get("output_table"),
                backup_before_overwrite=payload.get("backup_before_overwrite"),
                db_path=payload.get("db_path") or payload.get("output_db_path"),
                output_path=payload.get("output_path"),
            )
        if action == "list_tables":
            return self.engine.list_tables(db_path=payload.get("db_path"))
        if action == "load_table":
            return self.engine.load_table(
                payload.get("source"),
                db_path=payload.get("db_path"),
                table_name=payload.get("table_name") or payload.get("table"),
                path=payload.get("path"),
                limit=payload.get("limit"),
                offset=payload.get("offset", 0),
            )
        if action == "get_table_page":
            return self.engine.get_table_page(
                payload.get("table", {}),
                limit=payload.get("limit"),
                offset=payload.get("offset", 0),
                source=payload.get("source"),
            )
        if action == "create_table_handle":
            return self.engine.create_table_handle(
                payload.get("table", payload.get("source")),
                source=payload.get("source"),
                db_path=payload.get("db_path"),
                table_name=payload.get("table_name") or payload.get("table"),
                path=payload.get("path"),
                limit=payload.get("limit"),
                offset=payload.get("offset", 0),
            )
        if action == "get_table_handle_page":
            return self.engine.get_table_handle_page(
                payload.get("handle", ""),
                limit=payload.get("limit"),
                offset=payload.get("offset", 0),
            )
        if action == "list_table_handles":
            return self.engine.list_table_handles()
        if action == "release_table_handle":
            return self.engine.release_table_handle(payload.get("handle", ""))
        if action == "build_table_access":
            return self.engine.build_table_access(payload.get("node", {}))
        if action == "precheck_access":
            return self.engine.precheck_access(
                payload.get("plan"),
                nodes=payload.get("nodes"),
                execute_actions=bool(payload.get("execute_actions", True)),
                stop_index=self._optional_int(payload.get("stop_at", payload.get("stop_index"))),
                db_path=payload.get("db_path") or payload.get("output_db_path"),
                sqlite_tables=payload.get("sqlite_tables"),
                output_mode=payload.get("output_mode"),
                output_table=payload.get("output_table"),
                table_access_policy=payload.get("table_access_policy"),
                current_transit_tables=payload.get("current_transit_tables"),
                confirmed=bool(payload.get("confirmed", False)),
            )
        if action == "format_access_issue":
            return {"text": self.engine.format_access_issue(payload.get("issue", {}))}
        if action == "record_access_audit":
            return self.engine.record_access_audit(payload.get("event", {}))
        if action == "list_access_audit_logs":
            return self.engine.list_access_audit_logs(
                selected_status=payload.get("selected_status", "全部"),
                keyword=payload.get("keyword", ""),
            )
        if action == "format_access_audit_event":
            return {"text": self.engine.format_access_audit_event(payload.get("event", {}))}
        if action == "analyze_jumps":
            return self.engine.analyze_jumps(
                payload.get("plan"),
                nodes=payload.get("nodes"),
            )
        if action == "validate_jumps":
            return self.engine.validate_jumps(
                payload.get("plan"),
                nodes=payload.get("nodes"),
            )
        if action == "format_jump_issue":
            return {"text": self.engine.format_jump_issue(payload.get("issue", {}))}
        if action == "get_plugin_schema":
            plugin_id = payload.get("plugin_id") or payload.get("node_type_id")
            return self.engine.get_plugin_schema(
                plugin_id,
                plugins_dir=payload.get("plugins_dir"),
                preview_headers=payload.get("preview_headers"),
                table_names=payload.get("table_names"),
                table_columns=payload.get("table_columns"),
            )
        if action == "make_plugin_default_config":
            plugin_id = payload.get("plugin_id") or payload.get("node_type_id")
            return self.engine.make_plugin_default_config(
                plugin_id,
                plugins_dir=payload.get("plugins_dir"),
            )
        if action == "list_plugins":
            return self.engine.list_plugins(
                plugins_dir=payload.get("plugins_dir"),
                refresh=payload.get("refresh"),
            )
        if action == "preview_node":
            raise ValueError("preview_node 暂未实现，请使用单节点 plan 调用 preview_plan。")
        raise ValueError(f"未知 action：{action}")

    @staticmethod
    def _optional_int(value):
        if value is None or value == "":
            return None
        return int(value)

    @staticmethod
    def _error(code, message, **extra):
        payload = {"code": code, "message": message}
        payload.update(extra)
        return payload

    @staticmethod
    def _response(request_id, ok, message, result=None, logs=None, errors=None):
        return {
            "request_id": request_id,
            "ok": bool(ok),
            "message": message,
            "result": result,
            "logs": list(logs or []),
            "errors": list(errors or []),
        }


def iter_json_lines(input_stream, output_stream, worker=None):
    """Read one JSON request per line and write one JSON response per line."""

    worker = worker or StdioWorker()
    for raw_line in input_stream:
        line = raw_line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError as exc:
            response = StdioWorker._response(
                "",
                False,
                f"JSON 解析失败：{exc}",
                errors=[StdioWorker._error("invalid_json", str(exc))],
            )
        else:
            response = worker.handle_request(request)
        output_stream.write(json.dumps(response, ensure_ascii=False, separators=(",", ":")) + "\n")
        try:
            output_stream.flush()
        except Exception:
            pass


def main(argv=None, input_stream=None, output_stream=None):
    parser = argparse.ArgumentParser(description="DataFlowKit headless stdio worker")
    parser.add_argument("--stdio", action="store_true", help="Run JSON-lines stdio loop")
    args = parser.parse_args(argv)
    if not args.stdio:
        parser.error("stdio worker currently requires --stdio")
    iter_json_lines(input_stream or sys.stdin, output_stream or sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
