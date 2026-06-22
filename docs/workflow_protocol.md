# DataFlowKit Workflow JSON Protocol

This document defines the stable JSON contract used by workflow plans, nodes,
tables, runtime events, and future UI clients.

The current Tkinter UI remains a supported client. Future PyQt, Electron, .NET,
Flutter, CLI, or worker-process clients should depend on this protocol and the
headless engine API instead of importing Tkinter window classes.

## 1. Design Goals

- Keep existing `workflow_plan` JSON templates readable.
- Give every node a stable machine id that is independent from Chinese display
  names.
- Allow old clients to keep using `type` while new clients move to
  `node_type_id`.
- Keep node `config` flexible, because every node owns its own configuration
  shape.
- Keep UI layout and client-only state outside execution semantics.
- Make protocol upgrades explicit and migratable.

## 2. Versioning

There are three version fields:

| Field | Scope | Example |
|---|---|---|
| `version` | Workflow plan file format | `"1.0"` |
| `node_version` | Node type contract/config version | `"1.0.0"` |
| `api_version` | Plugin/worker API contract | `"1.0"` |

Compatibility policy:

- Minor additions must be backward compatible.
- Unknown object properties should be preserved by editors unless explicitly
  documented as transient.
- Breaking changes require a new major version and a migration step.
- Existing plan templates with `template_type = "workflow_plan"` and `nodes`
  remain valid protocol 1.0 plans.

## 3. Workflow Plan

A workflow plan is the top-level JSON object saved in the `plan/` directory.

Required fields for protocol 1.0:

- `template_type`: must be `"workflow_plan"`.
- `version`: currently `"1.0"`.
- `plan_name`: user-facing name.
- `nodes`: ordered list of workflow node instances.

Recommended fields:

- `output_mode`: default final output target.
- `output_table`: default final table name.
- `db_path`: SQLite database path for output modes that write SQLite.
- `output_path`: file path for output modes that export files such as xlsx.
- `backup_before_overwrite`: whether destructive table writes should back up.
- `table_access_policy`: one of `audit`, `prompt`, `strict`, `off`.
- `metadata`: non-execution plan metadata.
- `ui`: client layout and view state.
- `extensions`: vendor or experimental data.

Example:

```json
{
  "template_type": "workflow_plan",
  "version": "1.0",
  "plan_name": "批量处理计划",
  "nodes": [],
  "output_mode": "输出到主界面预览区",
  "output_table": "结果表",
  "db_path": "",
  "output_path": "",
  "backup_before_overwrite": true,
  "table_access_policy": "audit",
  "metadata": {
    "created_by": "DataFlowKit",
    "description": ""
  },
  "ui": {},
  "extensions": {}
}
```

## 4. Node Instance

Each item in `nodes` is a node instance. A node instance is not the same as a
node type definition. The instance stores user configuration and plan placement.

Required fields:

- `enabled`: boolean.
- `config`: object.

Compatibility fields:

- `type`: existing display/type name, often Chinese. Keep it for old plans and
  current UI compatibility.
- `name`: user-facing node name.

Recommended stable fields:

- `node_id`: unique id inside a plan tree. UUID-like strings are preferred.
- `node_type_id`: stable machine id, for example `core.filter` or
  `plugin.word_excel_read_to_db_v1`.
- `node_version`: node contract/config version.
- `table_access`: node-level table and field permission policy.
- `ui`: node layout state for visual clients.
- `extensions`: vendor or experimental data.

Example:

```json
{
  "node_id": "node_018f6d7b",
  "node_type_id": "core.file_list",
  "node_version": "1.0.0",
  "type": "获取文件列表",
  "name": "输入文件",
  "enabled": true,
  "config": {
    "directory": "D:/data",
    "recursive": true,
    "include_files": true,
    "glob_pattern": "*"
  },
  "table_access": {
    "version": 1,
    "auto_generated": true,
    "tables": []
  },
  "ui": {
    "position": [120, 80],
    "collapsed": false
  },
  "extensions": {}
}
```

### 4.1 Stable Node Type IDs

`node_type_id` is the key future clients should use. `type` remains the current
compatibility/display field.

Suggested built-in ids:

| Current `type` | Stable `node_type_id` |
|---|---|
| `获取文件列表` | `core.file_list` |
| `批量重命名` | `core.batch_rename` |
| `批量替换` | `core.replace` |
| `数据提取` | `core.extract` |
| `格式规范化 / 日期时间解析` | `core.datetime_format` |
| `新建日期时间列` | `core.current_datetime_column` |
| `新建列` | `core.new_columns` |
| `合并列` | `core.merge_columns` |
| `批量更改列名` | `core.rename_columns` |
| `去重 / 重复数据处理` | `core.dedupe` |
| `列数字运算` | `core.numeric_column` |
| `匹配值输出列名` | `core.match_value_output` |
| `复制列` | `core.copy_column` |
| `复制行` | `core.copy_row` |
| `删除列` | `core.delete_columns` |
| `删除行` | `core.delete_rows` |
| `移动列` | `core.move_columns` |
| `填充值` | `core.fill_value` |
| `序列填充` | `core.sequence_fill` |
| `区域填充` | `core.area_fill` |
| `行数据映射填充` | `core.row_data_mapping` |
| `高级筛选` | `core.filter` |
| `保存中转数据` | `core.save_transit` |
| `字段映射写入表` | `core.writeback` |
| `节点组 / 子工作流` | `core.group` |
| `循环执行起点` | `core.loop_start` |
| `循环判断回跳` | `core.loop_judge` |
| `跳转锚点节点` | `core.jump_anchor` |
| `无条件跳转节点` | `core.unconditional_jump` |
| `条件判断节点` | `core.condition_check` |
| `条件跳转节点` | `core.conditional_jump` |
| `插件节点` | `plugin.<plugin_id>` or `core.plugin` |

For plugin nodes:

- Prefer `node_type_id = "plugin.<plugin_id>"`.
- Keep `type = "插件节点"` for current UI compatibility.
- Keep the plugin id in `config.plugin_id`.

## 5. Node Type Definition

Node type definitions describe what clients need to render and validate a node.
They may be provided by built-in code, plugin manifests, or future remote
registries.

Recommended fields:

```json
{
  "node_type_id": "core.replace",
  "display_name": "批量替换",
  "category": "数据处理",
  "node_version": "1.0.0",
  "input_type": "table",
  "output_type": "table",
  "danger_level": "safe_transform",
  "config_schema": [],
  "default_config": {},
  "capabilities": {
    "preview": true,
    "execute_actions": false,
    "uses_table_access": false
  }
}
```

`config_schema` intentionally follows the existing plugin parameter schema style
instead of JSON Schema. It is optimized for generating UI controls.

Common control `type` values:

- `text`
- `number`
- `bool`
- `select`
- `field_select`
- `table_select`
- `path`
- `directory`
- `textarea`
- `json`

## 6. Table Data

Table data is used between nodes, workers, plugins, and external clients.

```json
{
  "type": "table",
  "headers": ["字段A", "字段B"],
  "rows": [["值1", "值2"]],
  "metadata": {},
  "extensions": {}
}
```

Rules:

- `headers` is an ordered array of strings.
- `rows` is an ordered array of arrays.
- Cell values should be JSON scalars or `null`.
- Clients should tolerate short rows and normalize them at execution boundaries.
- Large tables should be exchanged through files, SQLite tables, or future
  columnar formats instead of inlining every row in JSON.

## 7. Runtime Requests

The headless engine and worker APIs should use action-based request envelopes.
This keeps stdio, HTTP, WebSocket, and in-process adapters aligned.

```json
{
  "request_id": "req_001",
  "api_version": "1.0",
  "action": "preview_plan",
  "payload": {
    "plan": {},
    "input_data": {
      "type": "table",
      "headers": [],
      "rows": []
    },
    "stop_at": null
  }
}
```

Recommended actions:

- `list_node_types`
- `get_node_type`
- `list_node_ui_schemas`
- `get_node_ui_schema`
- `migrate_plan`
- `list_plan_templates`
- `load_plan_template`
- `save_plan_template`
- `validate_plan_template`
- `apply_plan_command`
- `validate_config`
- `validate_plan_configs`
- `make_default_node`
- `validate_plan`
- `preview_plan`
- `preview_node`
- `run_plan`
- `start_job`
- `cancel_job`
- `get_job_status`
- `get_job_events`
- `list_output_modes`
- `apply_output`
- `list_tables`
- `load_table`
- `get_table_page`
- `analyze_jumps`
- `validate_jumps`
- `format_jump_issue`
- `list_plugins`

Runtime identity rules:

- New clients should create and execute nodes by `node_type_id`.
- Legacy `type` is accepted for old templates and current Tkinter display
  compatibility, but headless execution must resolve it to `node_type_id`
  before validation and dispatch.
- `get_node_type` and `make_default_node` accept `node_type_id`, `node_type`,
  or legacy `type`.
- `list_node_types` keeps returning legacy display names in `node_types` and
  should also expose stable ids in `node_type_ids` plus full metadata in
  `node_catalog`.
- `list_node_ui_schemas` and `get_node_ui_schema` return shared UI metadata for
  menu paths, Chinese labels, warnings, capability badges, and form groups. Qt,
  Web, HTTP, and other clients should use these actions instead of importing a
  UI-specific metadata file.
- Clients can call `migrate_plan` after loading older templates. The service adds
  missing `node_id`, `node_type_id`, and `node_version` fields while preserving
  legacy `type` and unknown extension fields.
- Clients should use `list_plan_templates`, `load_plan_template`,
  `save_plan_template`, and `validate_plan_template` for workflow plan template
  files. These actions keep template scanning, JSON recovery, migration, and
  save-time validation behind the backend boundary.
- Clients should use `apply_plan_command` for plan edits such as inserting,
  deleting, moving, duplicating, enabling, disabling, clearing, or replacing
  nodes. This keeps node-id generation and edit semantics out of concrete UIs.
- Clients should use `validate_config` before applying node edits and
  `validate_plan_configs` before running a plan when they want field-level
  warnings/errors for supported nodes.
- Clients that do not need old template compatibility may omit legacy `type`
  when creating nodes.
- `preview_plan` always runs with `execute_actions = false` and
  `dry_run = true`.
- `run_plan` may receive `dry_run = true`; this forces `execute_actions = false`
  even when the client also sends `execute_actions = true`.
- Results that include context expose `context.safety_policy` so UIs can display
  the effective mode.
- Clients that need progress, cancellation, or polling should use
  `start_job`, `get_job_status`, `get_job_events`, and `cancel_job`.
  `start_job` accepts `job_action = preview_plan | run_plan` and stores emitted
  workflow/node events behind the returned `job_id`.
- Clients should call `apply_output` after a completed `run_plan` job when they
  need to honor the plan's output settings. `list_output_modes` returns the
  backend-supported labels and requirements. Current output modes support
  frontend preview updates, SQLite new-table writes, SQLite overwrite with an
  optional backup, and xlsx export through `WorkflowServices`. SQLite modes need
  `db_path`; xlsx export needs `output_path`.
- Clients should use `list_tables`, `load_table`, and `get_table_page` for
  table browsing and paging. The first implementation supports SQLite table
  listing/loading, table files, and inline table paging.
- Clients should use `analyze_jumps`, `validate_jumps`, and `format_jump_issue`
  for jump-anchor relations and jump precheck display instead of importing
  Tkinter jump manager helpers.

### 7.1 Shared Node UI Schema

The shared node UI schema lives outside any concrete frontend. It describes how
to render a node but does not change execution logic.

Example:

```json
{
  "schema_version": "2.0",
  "node_type_id": "core.new_columns",
  "display_name": "新建列",
  "category": "数据处理",
  "category_label": "数据处理",
  "menu": {
    "path": ["数据处理", "新建列"],
    "order": 2000
  },
  "summary": "添加字段，可设置默认值",
  "warnings": [],
  "capabilities": {
    "headless_preview": true,
    "headless_run": true,
    "execute_actions": false
  },
  "form": {
    "schema_version": "2.0",
    "dynamic_rules": true,
    "groups": []
  },
  "default_config": {}
}
```

Clients may use `form.groups[].fields[]` to build controls. Common field types
include `text`, `textarea`, `number`, `bool`, `select`, `field_select`, and
`json`. Schema v2 fields may also include:

- `options_source`: backend-owned option source such as `preview_headers` or
  `table_names`.
- `visible_when` / `enabled_when`: declarative conditions based on another
  field value.
- `depends_on`: fields that should trigger a UI refresh when changed.
- `validation`: lightweight field hints such as `required`, `integer`, and
  `min`. Clients may show these hints immediately, while backend
  `validate_config` remains the final authority.

## 8. Runtime Responses

```json
{
  "request_id": "req_001",
  "ok": true,
  "message": "完成",
  "result": {},
  "logs": [],
  "errors": []
}
```

For failures:

```json
{
  "request_id": "req_001",
  "ok": false,
  "message": "计划校验失败",
  "result": null,
  "logs": [],
  "errors": [
    {
      "code": "invalid_plan",
      "message": "nodes 字段不存在或不是列表。",
      "path": "/nodes"
    }
  ]
}
```

Issue objects should follow the shared shape:

```json
{
  "severity": "error",
  "code": "invalid_nodes",
  "message": "plan.nodes 必须是 list。",
  "path": "/nodes",
  "node_index": 0,
  "node_type_id": "core.replace",
  "suggestion": ""
}
```

## 9. Runtime Events

Events are used for progress, logs, job lifecycle, and cancellation-aware UIs.
They can be delivered through callbacks, queues, stdout JSON lines, WebSocket,
or HTTP polling.

Common fields:

- `type`: event type.
- `job_id`: current job id when applicable.
- `node_id`: current node id when applicable.
- `node_name`: display node name when applicable.
- `message`: short human-readable message.
- `timestamp`: optional ISO-like timestamp.

Recommended event types:

- `workflow_start`
- `workflow_done`
- `workflow_error`
- `workflow_cancelled`
- `job_started`
- `job_done`
- `job_failed`
- `job_cancel_requested`
- `node_start`
- `node_progress`
- `node_done`
- `node_error`
- `node_log`

Example:

```json
{
  "type": "node_progress",
  "job_id": "job_001",
  "node_id": "node_018f6d7b",
  "node_name": "Word/Excel读取入库V1",
  "current": 10,
  "total": 100,
  "message": "正在处理 10/100"
}
```

## 10. Table Access

Node table access policy controls what each node may read or write. It is
attached to the node instance under `table_access`.

```json
{
  "version": 1,
  "auto_generated": true,
  "tables": [
    {
      "role": "output",
      "source_type": "SQLite表",
      "table": "结果表",
      "table_pattern": "",
      "pattern_type": "glob",
      "declared_by": "",
      "is_current_table": false,
      "write_mode": "replace_table",
      "permissions": {
        "read_table": false,
        "write_table": true,
        "create_table": true,
        "append_rows": false,
        "update_rows": false,
        "clear_table": false,
        "replace_table": true,
        "alter_schema": false,
        "delete_rows": false,
        "drop_table": false
      },
      "field_mapping_mode": "by_name",
      "field_mapping": {},
      "log_only": false
    }
  ]
}
```

Known table permission keys:

- `read_table`
- `write_table`
- `create_table`
- `append_rows`
- `update_rows`
- `clear_table`
- `replace_table`
- `alter_schema`
- `delete_rows`
- `drop_table`

Known field permission keys:

- `read_field`
- `write_field`
- `create_field`
- `protect_field`

## 11. Plugin Compatibility

The existing plugin protocol remains valid. This workflow protocol references
plugin definitions rather than replacing them.

Plugin manifests should continue using:

- `plugin_info.id`
- `plugin_info.api_version`
- `plugin_info.input_type`
- `plugin_info.output_type`
- `schema`
- `entry`
- `requirements`

Plugin node instances should use:

```json
{
  "node_type_id": "plugin.word_excel_read_to_db_v1",
  "type": "插件节点",
  "config": {
    "plugin_id": "word_excel_read_to_db_v1",
    "params": {}
  }
}
```

External plugin `input.json`, `output.json`, and stdout JSON line progress
events continue to follow `docs/plugin_protocol.md`.

## 12. Migration Notes

Current plan templates usually contain:

```json
{
  "template_type": "workflow_plan",
  "version": "1.0",
  "plan_name": "...",
  "nodes": [
    {
      "enabled": true,
      "type": "批量替换",
      "name": "批量替换",
      "config": {}
    }
  ]
}
```

These files remain valid. The shared `migrate_plan` action performs this step without mutating the input plan.
It returns `{ok, changed, plan, issues, summary}` so frontends can show warnings
only when the migration finds invalid shapes.

`load_plan_template` returns the loaded plan plus migration and validation
metadata without writing the migrated result back to disk. `save_plan_template`
builds the plan document, migrates a copy, validates it, and only writes when no
error-level issues remain.

A migration step may add:

- `node_id`
- `node_type_id`
- `node_version`
- `table_access`
- `ui`
- `extensions`

Migration must preserve unknown fields and nested group nodes.

## 13. Schema Files

Draft-07 JSON Schema files live in `schemas/`:

- `workflow_plan.schema.json`
- `workflow_node.schema.json`
- `table_data.schema.json`
- `runtime_message.schema.json`
- `plugin_manifest.schema.json`

These schemas validate the shared envelope and stable fields. They deliberately
allow additional properties inside `config`, `metadata`, `ui`, and
`extensions`.
