# 多UI共享 Payload 清单

## 1. 目的

这份清单不是再讲一次“为什么要解耦”，而是把当前已经相对稳定、可以直接给 Qt / Tk / `.NET` / 未来 worker UI 消费的共享 payload 列出来。

目标是两点：

1. 后续新 UI 不需要再从 `ui_qt` 代码里倒推协议。
2. 后端继续收口时，优先补“还没形成稳定 payload 的区域”。


## 2. 当前已经比较稳定的共享对象

### 2.1 `message_panel`

用途：统一说明、问题、日志三类消息面板。

当前关键字段：

- `mode`: `info | success | warning | error`
- `title`: 面板标题
- `body`: 主体文本，兼容旧消费方式
- `info_body`: 说明页正文
- `issue_body`: 问题页正文
- `issues`: 结构化问题列表
- `logs`: 日志列表
- `preferred_tab`: `info | issues | logs`

适用场景：

- 计划打开/保存/导入反馈
- 校验反馈
- 节点配置校验反馈
- 后台任务启动/轮询/完成反馈
- 预览来源切换反馈
- 模板列表刷新反馈

对多 UI 的价值：

- Qt、Tk、`.NET` 都可以自己决定用 tab、accordion、message list 还是侧栏来展示。
- 后端已经把“默认应该看哪个页签”一起给出，前端不用再自己猜。


### 2.2 `feedback`

用途：统一动作反馈结果。

当前关键字段：

- `level`
- `code`
- `title`
- `status_message`
- `issue_message`
- `issues`
- `logs`
- `message_panel`

典型来源：

- `describe_plan_command_feedback()`
- `describe_plan_file_failure()`
- `describe_selection_feedback()`
- `describe_job_run_conflict()`
- `describe_job_start_failure()`
- `describe_validation_feedback()`
- `apply_node_config_state()` 返回中的 `feedback`

对多 UI 的价值：

- 工具栏状态栏、toast、消息面板、日志区都能从一个 payload 拆开消费。
- `.NET` 或网页前端可以保留自己的视觉体系，但不需要重写错误归类逻辑。


### 2.3 `view_state`

用途：统一“当前视图应该怎么切”的状态提示。

当前已出现的关键字段：

- `table_kind`
- `table_title`
- `status_message`
- `has_table`
- `should_refresh_preview_sources`
- `refresh_preview_sources`
- `visible_field_keys`

主要来源：

- `finalize_job_result()`
- `load_preview_source()`
- `build_output_panel_state()`

对多 UI 的价值：

- 前端可以把“显示哪个表”“标题显示什么”“要不要刷新预览来源”“哪些输出字段该显示”都交给后端结果驱动。
- 这类字段特别适合 `.NET`、Qt、Web 共用，因为它本质上是状态而不是控件实现。


### 2.4 `file_dialog`

用途：统一文件动作的对话框描述。

当前关键字段：

- `dialog`: `open_file | save_file`
- `title`
- `initial_path`
- `filters`

主要来源：

- `describe_file_action("import_table")`
- `describe_file_action("open_plan")`
- `describe_file_action("save_plan")`

对多 UI 的价值：

- 前端仍然自己弹本地文件对话框，但动作语义、默认路径、筛选器来源已经统一。
- 这对桌面 UI 很直接；对 Web 端则可转成 accept/filter 配置。


### 2.5 `prompt`

用途：统一确认提示。

当前关键字段：

- `required`
- `code`
- `title`
- `message`
- `details`

主要来源：

- `describe_confirmation_prompt(action="clear_nodes")`
- `describe_confirmation_prompt(action="run_plan")`

对多 UI 的价值：

- 前端只负责决定用 modal、drawer 还是 inline warning。
- 提示理由、风险说明、执行前摘要由后端统一给出。


## 3. 当前已形成闭环的业务 payload

### 3.1 计划模板列表状态

当前来源：`build_template_list_state()`

关键字段：

- `templates`: 模板记录列表，至少包含 `name`、`path`
- `template_count`
- `status_message`
- `message_panel`

说明：

- Qt 现在已经不再自己拼“模板刷新完成：N 个”，而是消费共享状态。
- 后续 `.NET` 可以直接用 `templates` 填充下拉框或列表面板。


### 3.2 输出设置面板状态

当前来源：`build_output_panel_state()`

关键字段：

- `settings`: 当前输出设置值
- `fields`: 字段定义列表
- `mode_meta`: 模式元数据
- `view_state.visible_field_keys`
- `view_state.refresh_preview_sources`
- `message_panel`

说明：

- 这一块已经不只是“输出模式列表”，而是一个能驱动表单显隐的共享状态。
- 对 `.NET`/Web 尤其有用，因为表单显示逻辑已经开始脱离 Qt 本地判断。


### 3.3 节点配置应用结果

当前来源：`apply_node_config_state()`

关键字段：

- `validation`
- `feedback`
- `apply_result`

说明：

- 前端负责把表单值收集成 node，再交给后端统一校验、应用、返回结果。
- 这一块已经很接近“UI 只是 node config editor”的目标。


### 3.4 预览来源状态

当前来源：`list_preview_sources()`、`load_preview_source()`、`build_preview_panel_state()`

关键字段：

- `sources`
- `selected_key`
- `title`
- `table`
- `view_state`
- `message_panel`

说明：

- 这使“输入表 / 预览表 / 其他来源”切换开始具备统一结构。
- 后续如果 `.NET` 想做更强的多表签切换，这部分可以直接复用。


### 3.5 后台任务完成结果

当前来源：`finalize_job_result()`

关键字段：

- `table`
- `logs`
- `message_panel`
- `view_state`
- `progress`

说明：

- 任务完成后的表格结果、日志、标题、刷新行为已经开始统一返回。
- 前端不需要再根据 `job_action` 写一堆分支去猜结果怎么落到界面。


## 4. 当前适合给 `.NET` 直接消费的层次

如果现在就给 `.NET` UI 壳一个推荐接法，建议分三层：

### 第一层：直接消费共享 payload

优先直接吃这些：

- `message_panel`
- `feedback`
- `prompt`
- `file_dialog`
- `view_state`
- `templates`
- `output panel state`
- `preview panel state`

这一层不需要理解 Qt 的控件做法，只要理解字段语义。


### 4.1 `.NET` 推荐 ViewModel 映射

如果是 Avalonia / WPF / WinUI 这类 MVVM 路线，建议不要直接把后端 payload 原样塞进控件，而是统一映射成几组稳定 ViewModel。

推荐最小集合：

- `MessagePanelViewModel`
  - 对应 `message_panel`
  - 建议字段：`Mode`、`Title`、`InfoText`、`IssueText`、`Logs`、`PreferredTab`

- `FeedbackViewModel`
  - 对应 `feedback`
  - 建议字段：`Level`、`Code`、`StatusMessage`、`Summary`、`Panel`

- `TemplateListViewModel`
  - 对应 `build_template_list_state()`
  - 建议字段：`Templates`、`TemplateCount`、`StatusMessage`、`Panel`

- `OutputPanelViewModel`
  - 对应 `build_output_panel_state()`
  - 建议字段：`Settings`、`Fields`、`VisibleFieldKeys`、`RefreshPreviewSources`

- `PreviewPanelViewModel`
  - 对应 `build_preview_panel_state()` / `load_preview_source()`
  - 建议字段：`Sources`、`SelectedKey`、`CurrentTable`、`Title`、`ViewState`

- `JobResultViewModel`
  - 对应 `finalize_job_result()`
  - 建议字段：`Table`、`Logs`、`Progress`、`ViewState`、`Panel`

这样做的意义是：

- 后端协议可以继续演进；
- `.NET` 侧界面绑定对象保持稳定；
- 将来换成 Electron / Flutter，也能照着同样的分层做 adapter。


### 第二层：消费节点协议与 UI schema

包括：

- 节点目录 `catalog`
- 节点详情 `detail`
- 表单 schema
- 字段 action 描述
- 结构化列表 item schema
- `options_source`
- `visible_when`

这一层决定的是“.NET 能不能像 Qt 一样做成真正的工作流配置界面”。


### 4.2 节点表单推荐拆分

`.NET` 侧如果要真正把节点配置面板做顺，不建议把所有 field schema 当成一种控件处理，建议最少拆成下面几类 ViewModel：

- `ScalarFieldViewModel`
  - 文本、数字、布尔、下拉单选

- `PickerFieldViewModel`
  - 带 `action` 的字段，如 `pick_preview_header`、`pick_table_name`、`pick_table_field`
  - 需要把 `options_source`、`action`、`validation` 一起挂上

- `StructuredListFieldViewModel`
  - 对应 `structured_list`
  - 重点保存 `item_schema.columns`、每行当前值、行内 action 能力

- `DynamicRuleViewModel`
  - 对应 `visible_when`、依赖字段、候选联动

这样比“一个超大通用字段类”更适合后续复杂节点扩展，也更容易和 Qt 当前的协议保持一致。


### 第三层：消费任务与执行接口

包括：

- 校验请求
- 预览请求
- 执行请求
- worker 事件流
- 最终结果 payload

这一层完成后，多 UI 才算真正共用同一后端能力，而不是只共用静态配置描述。


### 4.3 状态同步建议

对 `.NET` 来说，最容易踩坑的不是画控件，而是状态同步。建议固定成三条线：

- `PlanState`
  - 当前工作流 JSON、本地选择状态、当前模板路径

- `ViewState`
  - 当前表标题、当前表类型、可见字段、是否需要刷新预览来源

- `FeedbackState`
  - 最近一次状态栏消息、最近一次结构化反馈、最近一次消息面板内容

这样前端切 tab、切表、切节点时，不需要把业务判断重新散落到多个窗口事件里。


## 5. 当前还不够稳定、后续要继续补的区域

### 5.1 字段选择器类动作仍偏前端实现

例如：

- 选单表
- 选单字段
- 选多字段
- 选表字段

现状：

- 字段候选来源已经大多协议化。
- 但交互方式本身仍主要由前端自己决定。
- 当前已经补上了一层共享 picker 反馈，至少“无候选项 / 缺少关联表上下文”不必再由各前端各写一套提示。

这本身不是问题，但还可以继续补两类共享信息：

- 候选为空时的标准反馈
- 某类 picker 的推荐展示方式或限制说明


### 5.2 模板动作仍只有“列表状态”比较统一

目前模板刷新已经收口，但这些点仍可继续统一：

- 新建模板时的命名提示
- 模板覆盖风险确认
- 模板分类/标签元信息


### 5.3 某些 payload 命名仍带桌面气味

例如：

- `message_panel`

当前判断：

- 先不急着改名。
- 只要字段含义稳定，Qt / `.NET` / Web 都能消费。
- 等 worker / `.NET` / Web 真正接入后，再根据实际摩擦决定要不要抽象成更中性的名字。


## 6. 后续建议的自然顺序

### 6.1 第一优先级

- 继续把高频 Qt 本地交互闭环下沉成共享状态
- 尤其是节点配置、候选项刷新、复杂 picker 反馈、任务结果切换这类高频路径


### 6.2 第二优先级

- 为 `.NET` 明确补一层“payload -> view model”映射约定
- 不一定写死实现，但最好把字段分组、必填项、常见状态列出来


### 6.3 第三优先级

- 等 `stdio-worker-api` 接口收稳后，把这些 payload 再看一遍
- 检查是否存在只适合本地桌面、但不适合跨进程/跨端的字段


## 7. 当前结论

从现在的状态看，项目已经不只是“有一个 Qt 壳”，而是开始形成一套可以被多个 UI 直接消费的共享描述层。

当前最有价值的成果不是某个具体控件，而是这些已经开始稳定的 payload：

- `message_panel`
- `feedback`
- `view_state`
- `file_dialog`
- `prompt`
- `template_list_state`
- `output_panel_state`
- `preview_source_state`
- `node_config_apply_result`
- `finalize_job_result`

后续 Qt 要继续做，但每做一步，最好都尽量让 `.NET` 看起来像“跟着吃同一份后端描述”，而不是“再复刻一次 Qt 逻辑”。
