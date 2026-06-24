# 外挂插件节点协议说明：独立 Python 环境版

本版在原有插件协议基础上，增加了“插件独立环境”运行方式。目标是解决主程序打包成 exe 后，插件依赖库不一定随主程序一起打包的问题。

## 1. 推荐目录结构

```text
工具目录/
├─ 数据工作流工具.exe
├─ plugins/
│  ├─ 普通单文件插件.py
│  └─ hex_extract/
│     ├─ plugin.json
│     ├─ plugin.py
│     └─ requirements.txt
├─ plugin_envs/
│  └─ hex_extract/
│     └─ Scripts/python.exe
├─ plugin_data/
├─ logs/
└─ plan/
```

建议：

- 普通轻量插件可以继续用 `plugins/xxx.py`，在主程序环境中直接运行。
- 依赖第三方库、环境较复杂的插件，建议使用 `plugins/插件ID/plugin.json + plugin.py + requirements.txt`。
- 独立环境放到 `plugin_envs/插件ID/`，主程序通过 `subprocess` 调用该环境中的 Python。

## 2. 两种运行方式

插件节点新增运行环境：

```text
主程序内置环境
插件独立环境
```

### 主程序内置环境

主程序直接 import 插件 `.py`，然后调用：

```python
def run(input_data, params, context):
    ...
```

优点是快，缺点是插件依赖必须已经被主程序 exe 打包进去。

### 插件独立环境

主程序不在自身进程中 import 插件，而是调用：

```text
plugin_envs/插件ID/Scripts/python.exe plugins/插件ID/plugin.py --input input.json --output output.json
```

优点是插件依赖独立，主程序不用打包所有第三方库。适合 HEX、Word、Excel、图片识别、AI 模型等复杂插件。

## 3. plugin.json 格式

独立环境插件推荐使用 `plugin.json` 注册，避免主程序为了读取插件信息而 import 插件代码。

示例：

```json
{
  "plugin_info": {
    "id": "hex_extract",
    "name": "HEX软件确认数据提取",
    "version": "1.0.0",
    "api_version": "1.0",
    "category": "文件处理",
    "description": "从 HEX 文件中提取软件确认数据。",
    "input_type": "table",
    "output_type": "table",
    "danger_level": "safe_readonly",
    "run_mode": "external_python"
  },
  "entry": "plugin.py",
  "requirements": "requirements.txt",
  "schema": [
    {"name": "path_field", "label": "HEX文件路径字段", "type": "field_select", "default": "完整路径"}
  ]
}
```

主程序会扫描 `plugins/*/plugin.json` 并注册为插件节点。

## 4. 独立环境输入输出协议

主程序会生成：

```text
plugin_data/插件ID/runs/时间戳/input.json
plugin_data/插件ID/runs/时间戳/output.json
```

### input.json

```json
{
  "input_data": {
    "type": "table",
    "headers": ["文件名", "完整路径"],
    "rows": []
  },
  "params": {},
  "context": {
    "app_dir": "...",
    "db_path": "",
    "database_access": "managed_requests",
    "database_available": true,
    "plugins_dir": "...",
    "plugin_data_dir": "...",
    "log_dir": "...",
    "is_preview": true,
    "execute_actions": false,
    "workflow_name": "...",
    "node_name": "...",
    "plugin_id": "hex_extract",
    "transit_tables": {}
  }
}
```

### output.json

```json
{
  "ok": true,
  "message": "执行完成",
  "output": {
    "type": "table",
    "headers": [],
    "rows": []
  },
  "database_requests": [
    {
      "operation": "write_table",
      "table_name": "src_demo",
      "headers": ["字段1"],
      "rows": [["值1"]],
      "mode": "replace"
    }
  ],
  "logs": [],
  "summary": {}
}
```

独立环境插件不能直接连接工作流数据库。需要写表时，通过 `database_requests` 返回受控请求，主程序会按当前插件节点的表权限统一检查并执行。当前支持的操作是 `write_table`；预览模式下请求不会实际写入。

进程内插件仍应通过 `context["db"]` 访问工作流数据库，不要根据 `db_path` 自行创建 SQLite 连接。插件自己的缓存数据库不受此限制，建议继续存放在 `context["plugin_data_dir"]`。

### 插件表访问声明

插件可以声明默认表访问范围，主程序会把声明合并到插件节点的表权限配置中。动态表名建议使用模式声明：

```python
def get_table_access_spec(params=None, context=None):
    prefix = str((params or {}).get("table_prefix") or "src_")
    return [
        {
            "table_pattern": prefix + "*",
            "pattern_type": "glob",
            "write_mode": "replace",
            "permissions": {
                "read_table": False,
                "write_table": True,
                "create_table": True,
                "append_rows": False,
                "replace_table": True,
                "alter_schema": False,
            },
        }
    ]
```

`pattern_type` 支持 `glob`、`prefix` 和 `regex`。字段级的 `read_field`、`write_field`、`create_field` 和 `protect_field` 可继续放在 `field_mapping` 中声明。声明只是节点默认配置，最终执行仍由 `TableAccessManager` 按工作流权限策略校验。

如果插件失败：

```json
{
  "ok": false,
  "message": "错误信息",
  "output": {
    "type": "table",
    "headers": ["错误信息"],
    "rows": [["错误信息"]]
  },
  "logs": [
    {"level": "ERROR", "message": "错误信息"}
  ]
}
```

## 5. 独立环境进度上报

独立环境插件无法直接使用主程序中的 `context["report_progress"]` 函数，因此通过 stdout 输出 JSON 行上报进度。

示例：

```python
print(json.dumps({
    "type": "node_progress",
    "current": i,
    "total": total,
    "message": f"正在处理 {i}/{total}"
}, ensure_ascii=False), flush=True)
```

主程序会读取这些 JSON 行并更新“当前节点进度条”。

## 6. 独立环境配置建议

插件节点中可设置：

```text
运行环境：插件独立环境
独立Python：plugin_envs/插件ID/Scripts/python.exe
环境目录：plugin_envs/插件ID
外部入口：plugins/插件ID/plugin.py
超时时间：0 表示不限制
```

第一版主程序不自动创建 venv，只负责调用已存在的 Python。推荐手动创建：

```bat
python -m venv plugin_envs\hex_extract
plugin_envs\hex_extract\Scripts\python.exe -m pip install -r plugins\hex_extract\requirements.txt
```

## 7. 插件内部缓存建议

复杂文件插件建议继续使用插件内部缓存，而不是主程序全局缓存。

推荐缓存位置：

```text
context["plugin_data_dir"]/cache.sqlite
```

文件类插件可按以下信息判断缓存是否有效：

```text
文件路径
文件大小
修改时间 mtime_ns
插件版本
插件参数摘要
可选文件 hash
```

这样即使主程序因为字段推断或预览重复执行插件，插件也能快速复用结果。

## 8. 注意事项

- 独立环境插件不能直接拿到主程序内存中的 `context["db"]` 对象，也不会收到真实工作流 `db_path`；数据库写入应返回 `database_requests`。
- 如果插件需要中转副表，主程序会把 `transit_tables` 序列化到 input.json，数据很大时要注意性能。
- 插件写文件、改数据库、重命名等危险动作应检查 `context["execute_actions"]`，预览模式下不要执行真实写操作。
- 插件如果输出大量日志，建议只把摘要打印到 stdout，详细日志写到插件自己的日志文件或 output.json 的 logs 中。

## 9. 推荐开发流程

```text
1. 新建 plugins/插件ID/plugin.json
2. 新建 plugins/插件ID/plugin.py
3. 新建 plugins/插件ID/requirements.txt
4. 创建 plugin_envs/插件ID 虚拟环境
5. 安装 requirements.txt
6. 在主程序插件节点中选择“插件独立环境”
7. 选择独立 Python 路径
8. 点击“测试环境”
9. 运行工作流
```

## 10. 外部插件退出码说明

主程序会优先读取 `output.json`。

- 如果插件返回码非 0，但已经生成 `output.json`，主程序仍会读取其中的 `ok/message/output/logs`，并交给插件节点的失败策略处理。
- 如果插件返回码非 0 且没有生成 `output.json`，主程序会认为外部插件进程异常失败。

因此建议插件即使遇到业务错误，也尽量写出标准 `output.json`，方便主程序显示错误表、保存日志和继续执行失败策略。


## 11. 后台线程执行、进度与取消建议

主程序的计划 / 工作流执行采用后台线程方式运行，主界面只负责配置和显示，执行线程通过 Queue 回传进度、结果和错误信息。

插件节点可以通过两种方式上报进度：

### 主程序内置环境插件

内置环境插件可以使用 `context["report_progress"]`：

```python
def run(input_data, params, context):
    rows = input_data.get("rows", [])
    total = len(rows)
    for i, row in enumerate(rows, start=1):
        # 建议长循环定期检查取消事件
        cancel_event = context.get("cancel_event")
        if cancel_event is not None and cancel_event.is_set():
            return {
                "ok": False,
                "message": "用户取消插件执行",
                "output": input_data,
                "logs": [{"level": "WARNING", "message": "用户取消插件执行"}]
            }

        # 执行业务处理...

        if i == 1 or i % 100 == 0 or i == total:
            context["report_progress"](i, total, f"插件处理中 {i}/{total}")
```

### 插件独立环境

独立环境插件仍然通过 stdout 输出 JSON 行上报进度：

```python
print(json.dumps({
    "type": "node_progress",
    "current": i,
    "total": total,
    "message": f"正在处理 {i}/{total}"
}, ensure_ascii=False), flush=True)
```

### 取消机制

主程序点击“取消后台任务”后，会设置 `cancel_event`。内置环境插件可以读取：

```python
cancel_event = context.get("cancel_event")
if cancel_event is not None and cancel_event.is_set():
    # 尽快安全退出
    ...
```

独立环境插件由主程序负责终止外部进程，因此建议插件尽量定期写出进度，并在业务层面避免单个不可中断操作持续过久。

### 错误日志

工作流后台线程发生未捕获异常时，主程序会把错误信息和 traceback 写入：

```text
logs/workflow/workflow_error_时间戳.log
```

插件自己的详细日志仍建议写入 `context["plugin_data_dir"]` 或 `context["log_dir"]`，主程序只在界面上显示摘要，避免大量日志阻塞 UI。

### 副作用安全建议

插件进行文件写入、数据库修改、批量重命名等操作时，仍应检查：

```python
context.get("execute_actions", False)
```

预览模式下应只生成预览结果，不应修改真实文件或真实数据库。

## 12. 插件配置描述协议

插件可以可选提供：

```python
def describe_config(params, context):
    return {
        "schema_version": "your_plugin.config.v1",
        "summary": {},
        "views": [],
        "resources": [],
        "actions": [],
        "context": {},
        "models": {},
        "warnings": [],
    }
```

主程序会在 `describe_plugin_config` 中把这些内容合并到标准 `plugin_config.v1`：

- `views`：描述 UI 可展示的配置区域，例如 `summary`、`structured_list`、`form`。
- `resources`：描述配置文件、缓存或外部资源，不要求 UI 直接读写真实路径。
- `actions`：描述可触发动作，例如 `config_editor` 或兼容旧窗口入口。
- `context`：提供候选值和运行上下文快照，例如表名、字段、规则名。
- `models`：提供默认对象模板，供未来 Qt/.NET/Web 编辑器创建新配置项。

复杂插件不应把配置能力只写进某个界面。推荐先用 `describe_config` 暴露稳定结构，再由不同 UI 根据 `view.kind` 和 `action.editor_kind` 选择渲染方式。

例如可视化映射插件使用：

```text
schema_version: DataFlowKit.visual_mapping.config.v1
editor_kind:
  visual_mapping.rules
  visual_mapping.features
  visual_mapping.global_rules
  visual_mapping.linked_rules
```

第一阶段 UI 可以只显示摘要和结构化列表；第二阶段再分别实现专用编辑器。这样旧 Tk 配置窗口可以保留为兼容入口，同时新 UI 不需要继承 Tk 窗口内部逻辑。

复杂插件还可以提供顶层 `layout` 与 `ui_hints`，用于告诉不同 UI 如何组织配置视图，而不是让 Qt、.NET、Web 各自猜页签顺序和默认入口。当前可视化映射插件已使用：

- `layout.schema_version: DataFlowKit.visual_mapping.layout.v1`
- `layout.default_view_id: visual_mapping.rules`
- `layout.view_order / primary_views / advanced_views`
- `ui_hints.schema_version: DataFlowKit.visual_mapping.ui_hints.v1`
- `ui_hints.view_hints`：描述每个视图的说明、空状态、主动作和角色

Qt 已能按这些字段重排插件配置页签、默认切到推荐视图，并把视图说明合并到 tab tooltip。后续 .NET/Web 应优先消费同一批字段，而不是复制 Qt 当前布局。

### 12.1 旧 Tk 配置窗口 fallback 退场规则

`open_config_window(parent, current_params, context)` 仍可保留，但只能作为兼容入口。`describe_plugin_config` 返回的兼容动作会带有：

- `fallback: true`
- `deprecated: true`
- `lifecycle: legacy_fallback`
- `migration_target: describe_config + parameter_metadata + config_patch`
- `remove_when: 插件已提供等价 schema/patch 配置能力且目标 UI 已完成承接。`

新 UI 的推荐处理顺序：

1. 优先渲染 `parameter_metadata`、`views`、`models`、`patch_schema`、`warning_schema`、`protocol_manifest`。
2. 只有当协议配置能力不足时，才显示 `open_legacy_config` 兼容入口。
3. 兼容入口必须以降级/旧版方式展示，不应作为默认主按钮。
4. 插件完成等价协议迁移后，保留旧窗口一段过渡期，再从 UI 主路径移除。

旧窗口打开前的确认提示也应由共享 facade 生成：`describe_confirmation_prompt(action="legacy_plugin_config", compatibility_action=...)`。UI 只负责展示确认框，不应自行拼接兼容风险文案。
