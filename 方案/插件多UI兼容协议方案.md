# 插件多UI兼容协议方案

> 目的：在现有插件执行协议、插件 schema、旧自定义窗口兼容能力的基础上，整理一版适合 Qt / Tkinter / .NET / Web / Electron 共同使用的插件配置与运行协议方案。
>
> 本文关注的重点不是“插件怎么执行”，而是“插件如何在不同 UI 下保持一致可配置、可校验、可预览、可扩展”。

---

## 1. 当前问题定义

DataFlowKit 当前的插件体系，执行层已经具备较好的基础：

1. 支持主程序内置环境插件。
2. 支持插件独立环境 / 外部进程插件。
3. 支持 `plugin.json` 元数据。
4. 支持 `input.json / output.json / stdout JSON lines`。
5. 支持受控 `database_requests` 回写。

因此，插件体系当前的主要短板，**不是运行协议，而是配置协议与多 UI 兼容协议**。

现在最典型的矛盾是：

- 普通节点正在向 `node_ui_schema + headless` 收敛。
- 插件节点虽然已有 schema，但仍保留“插件自己弹设置窗口”的旧路径。
- 一旦插件继续依赖 `open_config_window(...)`，后续 Qt / .NET / Web 都要重复处理旧窗口兼容问题。

所以插件这条线需要明确主次：

**执行协议继续沿用现有方案，配置协议要从“窗口驱动”切换为“声明式 + 命令式补充”。**

---

## 2. 当前插件体系现状判断

## 2.1 已经具备的能力

当前代码里，插件体系其实已经有了多 UI 兼容的几个关键地基：

1. `PluginService.get_plugin_schema(...)`
   - 已能返回插件节点 schema、默认配置、菜单、能力标记、基础表单分组。
2. `PluginService.validate_plugin_config_patch(...)`
   - 已支持复杂插件的局部配置修改校验。
3. `PluginService.apply_plugin_config_patch(...)`
   - 已支持结构化配置写回。
4. `PluginService.run_plugin(...)`
   - 已统一主程序内置模式与独立环境模式。
5. 外部插件协议
   - 已支持 `stdout` 进度、`database_requests`、`output.json`。

这说明项目并不是要“推倒重做插件系统”，而是要把这些已有能力从“辅助能力”升级为“官方主路径”。

## 2.2 当前仍然不兼容的部分

当前最影响多 UI 的部分主要有三类：

1. 旧式 `open_config_window(parent, current_params, context)`。
2. 一些插件复杂交互仍把事实配置逻辑藏在 Tkinter 窗口内部。
3. 插件动态候选、复杂规则编辑、输入表规格编辑，尚未全部走统一协议。

这三类问题会导致：

1. Qt 能兼容一部分插件，但体验不稳定。
2. `.NET` / Web 无法直接复用“插件自带窗口”。
3. 插件作者会继续沿着旧习惯写“窗口逻辑型插件”，加重后续维护成本。

---

## 3. 多UI兼容的总原则

插件后续应遵循以下原则：

1. UI 不直接依赖插件窗口对象。
2. 插件配置主路径必须可通过协议描述。
3. 插件复杂交互应拆成“状态 + 命令 + 校验 + 预览”，而不是只能在某个 GUI 里临时计算。
4. 插件运行环境与插件配置方式解耦。
5. 旧自定义窗口只保留兼容地位，不再作为推荐开发方式。

用一句话概括：

**插件的“怎么运行”和“怎么配置”要分开；配置必须能被任何 UI 消费。**

---

## 4. 推荐的插件协议分层

后续插件协议建议分成三层：

1. 元数据层
2. 配置描述层
3. 执行层

---

## 5. 元数据层

元数据层主要由 `plugin.json` 与主程序扫描器承担。

推荐保留并强化以下信息：

```json
{
  "plugin_info": {
    "id": "example_plugin",
    "name": "示例插件",
    "version": "1.0.0",
    "api_version": "1.0",
    "category": "文件处理",
    "description": "示例说明",
    "input_type": "table",
    "output_type": "table",
    "danger_level": "safe_readonly",
    "run_mode": "builtin_or_external"
  },
  "entry": "plugin.py",
  "requirements": "requirements.txt",
  "schema": []
}
```

建议补充或规范的元数据点：

1. `supports_schema_config`
   - 是否支持 schema 主路径。
2. `supports_config_patch`
   - 是否支持复杂结构化编辑。
3. `supports_option_resolver`
   - 是否支持动态候选接口。
4. `supports_preview_config_effect`
   - 是否支持配置效果预览。
5. `legacy_custom_config`
   - 是否仍依赖旧自定义窗口。

这些标记可以体现在 `PluginService.get_plugin_schema(...).capabilities` 中，而不一定都硬写在 `plugin.json`。

---

## 6. 配置描述层

这是后续多 UI 兼容的核心。

### 6.1 主路径：声明式 schema

插件配置主路径应是：

- 插件返回 schema
- UI 读取 schema
- UI 渲染配置面板
- UI 把变更回传给共享服务

至少应支持以下字段能力：

1. label
2. type
3. default
4. help
5. required
6. choices
7. group
8. warning
9. placeholder
10. visibility / dependency

示意：

```json
{
  "key": "path_field",
  "label": "文件路径字段",
  "type": "field_select",
  "required": true,
  "choices": ["完整路径", "文件名"],
  "help": "用于定位要处理的源文件。"
}
```

### 6.2 第二层：动态候选接口

很多插件不是固定字段列表，而是依赖当前配置和输入数据动态变化。

例如：

1. 选择某个输入表后，再刷新字段候选。
2. 选择某个模式后，再决定下一个参数可选项。
3. 读取当前工作流传入表头、插件输入表 headers、transit table 名单后生成候选。

因此推荐统一一个动态候选接口，逻辑上可定义为：

```python
def resolve_options(config, context, request):
    ...
```

输入建议包含：

1. 当前完整 config
2. 当前 params
3. input tables 摘要
4. preview headers
5. table names / table columns
6. 请求字段 key
7. 触发依赖字段列表

返回建议包含：

1. choices
2. warnings
3. disabled reason
4. refresh hints

这样 Qt / .NET / Web 都可以统一做“依赖变化后刷新候选”。

### 6.3 第三层：局部配置 patch 协议

复杂插件通常不只是几个平面字段，而是：

1. 规则列表
2. 映射列表
3. 功能配置集
4. 嵌套条件
5. 输入表规格列表

这种结构如果靠 UI 整体覆写 params，容易乱。

因此建议将现在已有的：

1. `validate_config_patch`
2. `apply_config_patch`

正式定义为复杂插件主路径的一部分。

推荐 patch 形态：

```json
{
  "section": "linked_rules",
  "action": "add",
  "payload": {
    "name": "规则1",
    "target_field": "结果字段"
  }
}
```

或者：

```json
{
  "section": "input_tables",
  "action": "update",
  "index": 0,
  "payload": {
    "source_type": "sqlite",
    "table_name": "src_demo"
  }
}
```

这样 UI 不需要知道插件内部整个 params 结构怎么维护，只要按命令改。

### 6.4 第四层：配置效果预览接口

复杂插件配置后，用户经常需要知道：

1. 会增加哪些字段
2. 会读取哪些输入表
3. 会不会写数据库
4. 是否需要独立环境
5. 是否有风险提示

因此推荐加一个可选接口：

```python
def preview_config_effect(config, context):
    ...
```

返回建议包含：

1. summary
2. warnings
3. issues
4. expected_output_fields
5. required_input_tables
6. side_effect_flags

这个接口对 Qt 很有用，对后续 `.NET` / Web 也同样有价值。

---

## 7. 执行层继续沿用现有协议

执行层不需要大改，重点是保持稳定：

### 7.1 内置环境插件

继续支持：

```python
def run(input_data, params, context):
    ...
```

### 7.2 独立环境插件

继续支持：

1. `input.json`
2. `output.json`
3. `stdout JSON lines`
4. `database_requests`
5. 预览 / 执行模式区分
6. 后台线程进度汇报

### 7.3 执行层与配置层解耦

必须明确：

1. 插件能否多 UI 兼容，主要取决于配置层，而不是执行层。
2. 即使插件只能独立环境运行，也依然可以做到多 UI 兼容配置。
3. 即使插件在主程序内运行，如果配置依赖旧窗口，也仍然不兼容多 UI。

---

## 8. 旧自定义窗口的定位

这部分要态度明确，不然后面还会回到旧路。

### 8.1 旧窗口保留，但只作为兼容层

`open_config_window(...)` 建议保留一段时间，原因是：

1. 现有复杂插件已经在用。
2. 一次性彻底废掉会影响旧插件可用性。
3. 某些复杂插件短期内还没完成 schema/patch 化。

但它的定位必须改为：

**legacy fallback，不再作为推荐主路径。**

推荐协议字段：

1. `preferred=false`
2. `ui_role=fallback_action`
3. `ui_prominence=low`
4. `ui_placement=compatibility_menu`
5. `requires_confirmation=true`

### 8.2 UI 对旧窗口的处理建议

不同 UI 的处理方式建议如下：

1. Tkinter 主程序
   - 继续允许调用旧窗口。
2. Qt
   - 可选兼容，但应明确提示“旧版插件设置窗口”，并放在低优先级兼容入口。
3. `.NET` / Web / Electron
   - 默认不直接支持旧窗口，提示该插件需要迁移到 schema 配置模式。

也就是说，后续不能把“.NET 也兼容 Tk 窗口”作为目标，而应该把“插件迁移到协议配置”作为目标。

---

## 9. 对插件作者的统一约束建议

后续如果要让插件生态更稳定，建议逐步建立以下约束：

### 9.1 新插件默认要求

新插件建议默认满足：

1. 必须提供 `plugin.json`
2. 必须提供 schema 配置
3. 复杂配置建议提供 patch 接口
4. 涉及动态候选建议提供 option resolver
5. 不再推荐只提供 `open_config_window(...)`

### 9.2 旧插件迁移等级

可以把插件分成三档：

1. A档：完全 schema 化
   - 可直接多 UI 兼容
2. B档：schema + patch 混合
   - 可兼容，但复杂部分还在补
3. C档：仅旧自定义窗口
   - 仅兼容旧主程序 / 临时兼容 Qt，其他 UI 默认提示迁移到协议配置

这样主程序、Qt、后续 .NET 都能对插件兼容性给出明确提示。

---

## 10. 推荐实施顺序

建议按下面顺序推进，而不是一次把所有插件都重写。

### 第一步：把现有能力正式“主路径化”

也就是明确：

1. `get_plugin_schema` 是主入口。
2. `validate_config_patch` / `apply_config_patch` 是复杂配置主入口。
3. `open_config_window` 是 fallback。

### 第二步：先迁移最复杂、最典型的插件

优先迁移那些：

1. 已经有复杂规则编辑器
2. 当前 Qt 使用频繁
3. 后续 .NET 也很可能要用

例如视觉映射/写入类插件，就很适合作为协议化样板。

### 第三步：在 UI 层明确显示插件兼容能力

建议在插件节点详情 / 配置面板显示：

1. 支持 schema 配置
2. 支持动态候选
3. 支持结构化 patch
4. 仅旧版自定义窗口
5. 仅独立环境运行

这样用户和开发者都能快速看清现状。

### 第四步：逐步停止新增旧窗口型插件

项目规范上建议明确：

1. 新插件优先 schema 化。
2. 不再鼓励新增只靠 Tkinter 自定义窗口的插件。
3. 真有特殊情况，旧窗口也只是临时兼容。

---

## 11. 和当前项目解耦主线的关系

这份插件方案并不是独立的新路线，而是当前项目总解耦路线的一部分。

它和主线的关系是：

1. 普通节点通过 `node_ui_schema` 走向多 UI。
2. 插件节点通过 `plugin schema + options + patch + run` 走向多 UI。
3. 两者最终都汇聚到“前端只渲染，后端负责规则”的统一方向。

因此插件方案的意义，不只是“让插件更好用”，而是：

**避免插件节点成为整个多 UI 架构里的最后一个大例外。**

---

## 12. 当前一句话结论

DataFlowKit 当前的插件执行协议已经够用了，真正需要升级的是插件配置协议。

后续最稳的路线不是继续兼容各种插件自带窗口，而是把插件配置正式收敛到：

- schema 描述
- 动态候选
- patch 编辑
- 配置预览
- 统一执行

旧 `open_config_window(...)` 可以留着，但只能作为兼容层，而不应再作为未来主路径。
