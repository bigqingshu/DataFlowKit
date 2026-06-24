# Qt UI 后续方向与输入数据源管理方案

## 1. 当前定位

Qt UI 当前应定位为新的多 UI 协议客户端，而不是源 Tk 主程序的一比一复刻。

当前 Qt 工作流面板已经具备以下基础能力：

- 通过共享 `node_type_id` 节点协议加载节点目录。
- 通过 `node_ui_schema` 渲染节点菜单、说明、警告和配置表单。
- 通过 `plan_command` 执行节点增删、移动、复制、启停和配置写回。
- 通过 headless engine 执行预览、完整运行、后台任务、进度和日志。
- 通过插件 schema / `describe_plugin_config` / `apply_plugin_config_patch` 显示和修改部分插件结构化配置。
- 通过 stdio worker 暴露大部分协议接口，后续 .NET / Web UI 可以复用。

因此 Qt 后续不建议照搬 Tk 主程序整体界面，而应继续保持当前“左侧工作流导航 + 右侧配置/预览/输出”的结构，把源主程序里仍然有价值的功能拆成独立能力模块。

## 2. 与源主程序的差异

源主程序仍然承担完整生产入口，包含：

- 剪贴板读取和表格解析。
- SQLite 数据库选择、表列表刷新、表载入、保存、删除。
- 主预览表搜索、单元格编辑、字段名处理。
- 批量替换、数据提取、合并列、高级筛选等专用窗口。
- 工作流窗口里的字段权限层、权限预检、审计日志、跳转管理、组模板、手动循环执行。

Qt 当前已覆盖工作流主链路，但还没有覆盖完整数据源管理链路。尤其是“1. 输入数据源”区域目前只显示输入摘要和示例输入按钮，离源主程序“先准备数据，再进入工作流”的使用习惯还有距离。

## 3. 推荐方向

保持 Qt 工作流面板的现有形态，不把源主程序工作流按钮、节点操作按钮、批量处理入口直接搬进 Qt。

在 Qt 的“1. 输入数据源”区域增加两个核心控件：

- `输入数据源管理` 按钮：打开一个独立的数据源管理窗口。
- `选择表` 下拉菜单：快速选择当前数据库中的表，并载入为工作流输入。

数据源管理窗口可以参考源主程序最开始的主界面，但只保留数据准备相关功能：

- 读取剪贴板并解析。
- 导入 CSV / TSV / JSON 表格文件。
- 选择 SQLite 数据库。
- 刷新并选择 SQLite 表。
- 搜索当前表格。
- 开启编辑模式并修改单元格。
- 删除字段名并使用下一行作为字段名。
- 清空当前预览。
- 保存当前表格到 SQLite。
- 删除当前 SQLite 表，需保留高风险确认。
- 将当前表格设置为工作流输入。

不放入以下功能：

- 计划 / 工作流处理。
- 节点操作。
- 批量替换 / 数据处理入口。
- 数据提取 / 字段生成入口。
- 合并列 / 生成新列入口。
- 高级筛选 / 数据匹配入口。

这些功能后续应继续以工作流节点或独立工具协议形式进入 Qt，而不是塞进数据源管理窗口。

## 4. 建议的 Qt 交互形态

### 4.1 输入数据源区域

当前“1. 输入数据源”可调整为：

- 第一行：当前输入摘要，例如 `当前输入：120 行 x 8 列`。
- 第二行：`选择表` 下拉框 + `载入` 按钮。
- 第三行：`输入数据源管理` 按钮 + `重新载入示例输入` 按钮。

`选择表` 下拉框的数据来源应来自当前数据源数据库，而不是输出设置里的数据库路径。短期可以临时复用现有输出数据库路径，长期建议引入独立的 `input_db_path` 或 `workspace_db_path`。

### 4.2 输入数据源管理窗口

建议做成独立 `QDialog` 或 `QMainWindow`：

- 顶部工具栏：读取剪贴板、导入文件、清空、修改模式、设置为工作流输入。
- 数据库栏：数据库路径、选择数据库、刷新表、表名下拉、载入表。
- 保存栏：保存表名、保存到 SQLite、删除当前表。
- 搜索栏：关键词、搜索、上一个、下一个。
- 主区域：`QTableView` 表格预览。
- 底部状态栏：解析、载入、保存、编辑、搜索结果提示。

窗口关闭不应自动覆盖工作流输入；只有点击“设置为工作流输入”或“载入到工作流”才更新 Qt 主面板的 `current_headers/current_rows`。

## 5. 数据流设计

建议新增一个 UI 无关的数据源状态模型：

```json
{
  "source": {
    "type": "clipboard|file|sqlite|memory",
    "db_path": "",
    "table_name": "",
    "path": ""
  },
  "headers": [],
  "rows": [],
  "dirty": false,
  "display_name": "",
  "row_count": 0,
  "column_count": 0
}
```

Qt 主窗口只持有当前工作流输入：

- `current_headers`
- `current_rows`
- `current_input_source`

数据源管理窗口内部可以有自己的编辑状态。点击“设置为工作流输入”后再把状态写回主窗口，并刷新：

- 输入摘要。
- 表格预览。
- 节点配置候选字段。
- 表/字段候选上下文。
- 预览来源下拉。

如果当前已有预览结果，输入变更后建议提示“输入已变更，旧预览可能不再对应当前输入”，并可以清空 `last_preview_headers/last_preview_rows`。

## 6. 共享接口建议

为了后续 .NET UI 复用，不建议 Qt 直接复制 Tk mixin 逻辑。应把源主界面的数据逻辑继续下沉。

优先补充的共享能力：

- `parse_clipboard_table(text, first_row_header=True)`：解析剪贴板文本。
- `normalize_table_headers(headers)`：字段名去空、去重、补默认名。
- `promote_first_row_to_headers(table)`：删除当前字段名并提升下一行为字段名。
- `patch_table_cell(table, row, column, value)`：编辑单元格。
- `search_table(table, keyword)`：返回命中行列位置。
- `save_table(db_path, table_name, table, mode)`：保存到 SQLite。
- `delete_table(db_path, table_name, backup=True, confirmed=True)`：删除表。
- `list_tables(db_path)`：已有，可继续复用。
- `load_table(db_path, table_name)`：已有，可继续复用。
- `import_table_file(path)`：已有，可继续复用。

其中读取剪贴板本身属于 UI 能力，Qt / .NET 各自从系统剪贴板拿文本，然后交给共享解析函数。

## 7. 与现有后端的关系

现有 `TableDataService` 已经支持：

- 列出 SQLite 表。
- 载入 SQLite 表。
- 载入文件表。
- 表分页和 table handle。
- 解析剪贴板文本为表格。
- 字段名规范化与首行提升。
- 单元格 patch。
- 表格搜索与搜索导航。
- 保存/删除 SQLite 表。
- 描述 `data_source_service.v1`、`data_source_actions.v1`、`table_save_modes.v1`。
- 描述 `table_actions`，固定 `list_tables / load_table / get_table_page / create_table_handle / get_table_handle_page / list_table_handles / release_table_handle` 的 action id、engine action 和结果 schema。
- 描述 `data_source_manager_layout.v1` 与 `data_source_manager_ui_hints.v1`，把数据源管理窗口的区域顺序、动作归属、默认焦点、动作优先级和提示信息沉到共享 payload。

现有 `WorkflowFacade` 已经支持：

- 导入表格文件。
- 构建预览来源。
- 载入预览来源。

现有 `StdioWorker` 已经暴露：

- `describe_data_source_service`
- `describe_table_save_modes`
- `list_tables`
- `load_table`
- `get_table_page`
- `save_table`
- `delete_table`
- `create_table_handle`
- `list_table_handles`
- `get_table_handle_page`
- `release_table_handle`

当前剩余重点已经从“先有没有服务”转为：

- Qt 是否充分消费 `data_source_service.v1` 和 action schema，而不是继续手写按钮状态。
- Qt / `.NET` / Web 是否消费 `data_source_manager_layout.v1` 和 `data_source_manager_ui_hints.v1`，而不是各自重新设计窗口区域与按钮优先级。
- Qt 是否把大表路径更多切到 `table_actions` 中的 table handle/page。
- 输入数据库路径、工作区数据库路径、输出数据库路径是否继续拆清。
- `.NET` / Web 是否只依赖 stdio/headless payload，不复用 Python UI 代码。

## 8. 实施顺序

### 第一阶段：只补数据源服务

当前状态：**已基本完成**

目标是不动 Qt 界面或少动界面，先把主程序数据准备逻辑抽成共享函数。

- 从 Tk 主界面解析逻辑中抽出剪贴板表格解析。
- 抽出字段名规范化、提升首行为字段名。
- 抽出搜索和单元格 patch。
- 给保存/删除 SQLite 表补统一 service。
- 给这些能力补轻量测试。

### 第二阶段：Qt 输入数据源区域轻改

当前状态：**已完成主要入口，仍需继续收紧状态来源**

- 在“1. 输入数据源”加入 `选择表` 下拉。
- 加入 `载入` 按钮。
- 加入 `输入数据源管理` 按钮。
- 数据库路径先使用主窗口中的当前工作数据库设置，后续再独立。

### 第三阶段：Qt 数据源管理窗口

当前状态：**已落地可用窗口，继续按共享服务削薄 UI 逻辑**

- 新增 `ui_qt/data_source_window.py`。
- 使用 `QTableView` 显示和编辑表格。
- 支持读取剪贴板、导入文件、载入 SQLite 表。
- 支持搜索、编辑、清空、字段名提升。
- 支持保存到 SQLite。
- 支持设置为工作流输入。

### 第四阶段：大表和多 UI 兼容

当前状态：**后端与 stdio 已具备基础，Qt 和 .NET/Web 消费方式还需继续推进**

- 大表载入改用 table handle / 分页。
- stdio worker 暴露同一批数据源动作。
- `data_source_manager_state.v1` 已携带 manager layout 与 UI hints，后续 UI 可以按协议组织顶部工具栏、数据库行、载入表行、分页行、保存行、搜索行、表格区和状态区。
- .NET UI 只调用 stdio worker，不复用 Python UI 代码。
- Qt 和 .NET 的数据源窗口共享同一套 payload 和行为规则。

下一步建议拆成两块：

1. Qt 侧优先改为从 `describe_data_source_service` 与 `data_source_manager_state` 获取能力、动作、布局与提示说明，减少按钮逻辑硬编码。
2. 大表载入路径优先使用 table handle/page，避免后续 `.NET` / Web 一开始就复制整表传输模式。

## 9. 风险点

- 不要把输出数据库路径和输入数据库路径长期绑死，否则后续工作流输入源和输出目标会互相干扰。
- 删除 SQLite 表必须保留确认和备份策略，服务层只执行已确认操作。
- 剪贴板读取是 UI 行为，解析才是共享后端行为。
- 大表不应长期整表塞进 UI；后续需要分页或 handle。
- 数据源管理窗口不要再放工作流按钮，否则 Qt 会重新走向源主程序一比一复制。

## 10. 阶段结论

这个方向是合适的：Qt 不复刻主程序完整界面，只吸收“输入数据准备”这块刚需能力。

推荐把它做成独立数据源管理窗口，并把底层能力先沉到共享服务。这样当前 Qt 工作流面板会更实用，后续 .NET UI 也能复用同一套数据源协议，不会再次绑定到 Tk 或 Qt 的具体控件逻辑。
