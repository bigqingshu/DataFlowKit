# 参数型插件UI元数据规范

## 1. 文档目的

本文用于规范 DataFlowKit 参数型插件的 UI 元数据，目标是：

1. 让 Qt / Tkinter / .NET / Web 能一致渲染插件参数表单。
2. 让插件作者清楚哪些字段是“参数定义”，哪些字段是“UI 呈现元数据”。
3. 让参数型插件不必再靠某个 UI 自己猜联动、分组、显隐和候选来源。

本文适用的典型对象：

1. `plugins/word_excel_read_to_db_plugin_v1.py`
2. `plugins/word_excel_write_from_table_plugin_v2.py`
3. `plugins/plugin_template_输出日志_后台进度_插件缓存版.py`

这类插件通常特征是：

1. 主体配置由 `get_parameter_schema()` 表达。
2. 不需要复杂专用配置窗口。
3. 主要难点不是算法，而是参数多、候选多、联动多。

---

## 2. 总体原则

参数型插件后续应遵循：

1. 参数语义由插件提供。
2. UI 呈现规则尽量通过 schema 元数据提供。
3. 各 UI 不再自己猜哪些字段该隐藏、该分组、该联动。
4. 动态候选与动态显隐，应走共享协议，而不是某个 UI 的私有逻辑。

一句话：

**参数型插件的目标不是“只有 schema”，而是“schema 足够让所有 UI 都稳定渲染”。**

---

## 3. 参数 schema 的建议基础结构

推荐每个参数字段至少采用如下结构：

```json
{
  "name": "path_field",
  "label": "文件路径字段",
  "type": "field_select",
  "default": "source_file",
  "required": false,
  "help": "用于定位源文件路径。"
}
```

后续建议区分两类字段：

1. **业务字段**：决定参数值本身。
2. **UI 元数据字段**：决定这个参数怎么显示、何时显示、候选来自哪里。

---

## 4. 推荐通用字段清单

### 4.1 基础业务字段

每个参数建议支持：

1. `name`
2. `label`
3. `type`
4. `default`
5. `required`
6. `help`

说明：

- 这部分是最基础定义。
- 所有 UI 都必须支持。

### 4.2 推荐 UI 元数据字段

后续建议统一支持：

1. `group`
2. `group_order`
3. `order`
4. `placeholder`
5. `warning`
6. `visible_when`
7. `enabled_when`
8. `choices`
9. `options_source`
10. `allow_custom`
11. `layout`
12. `width_hint`
13. `advanced`
14. `refresh_on_change`

---

## 5. 字段类型规范

### 5.1 `select`

适用：

1. 固定枚举。
2. 业务模式选择。

建议字段：

1. `choices`
2. `default`
3. `help`

示例：

```json
{
  "name": "write_mode",
  "label": "写表模式",
  "type": "select",
  "choices": ["replace", "timestamp", "fail"],
  "default": "replace"
}
```

### 5.2 `field_select`

适用：

1. 从输入表 headers 中选字段。
2. 从当前上下文表头中选字段。

推荐补充：

1. `options_source`
2. `allow_custom`
3. `empty_text`

推荐 `options_source`：

```json
{
  "type": "preview_headers"
}
```

或者：

```json
{
  "type": "table_headers",
  "table_param": "doc_table_alias"
}
```

说明：

- `field_select` 后续不要再仅靠 UI 猜“从哪张表取字段”。
- 候选来源应通过元数据说明。

### 5.3 `field_multi_select`

适用：

1. 多字段选择。
2. 字段集合配置。

建议字段：

1. `options_source`
2. `allow_custom`
3. `delimiter`

### 5.4 `table_select`

适用：

1. 选择数据库表。
2. 选择共享中间表。

建议字段：

1. `options_source`
2. `allow_custom`
3. `empty_text`

推荐 `options_source`：

```json
{
  "type": "table_names"
}
```

### 5.5 `input_table_select`

适用：

1. 选择工作流输入表别名。
2. 选择当前节点可见输入源。

建议字段：

1. `options_source = {"type": "input_tables"}`
2. `allow_current_table`

### 5.6 `dynamic_select`

适用：

1. 依赖其他参数变化而变化的候选。
2. 候选来自插件内部逻辑解析。

要求：

1. 插件必须实现对应动态候选接口。
2. 字段应声明依赖项，方便 UI 正确刷新。

建议字段：

1. `depends_on`
2. `refresh_on_change`
3. `allow_custom`
4. `empty_text`

示例：

```json
{
  "name": "planned_file_field",
  "label": "拟定新文件字段",
  "type": "dynamic_select",
  "depends_on": ["content_table_alias"],
  "allow_custom": true
}
```

### 5.7 `directory` / `folder_path`

适用：

1. 文件夹路径输入。
2. 固定目录设置。

建议统一语义：

1. schema 原始值可仍保留 `folder_path`。
2. UI 内部标准控件类型统一映射为 `directory`。

建议字段：

1. `placeholder`
2. `must_exist`
3. `pick_button`
4. `normalize_path`

### 5.8 `bool`

适用：

1. 开关项。
2. 预览写入、是否递归、是否缓存等。

建议：

1. 不要把布尔值写成 select。
2. UI 用 checkbox / switch 统一呈现。

### 5.9 `number`

适用：

1. 重试次数。
2. 间隔毫秒。
3. 阈值。

建议字段：

1. `min`
2. `max`
3. `step`
4. `unit`

---

## 6. 参数分组规范

参数型插件后续建议显式支持分组，不再只靠字段顺序硬排。

推荐字段：

1. `group`
2. `group_order`
3. `advanced`

示例：

```json
{
  "name": "win32_open_retries",
  "label": "win32打开重试次数",
  "type": "number",
  "default": 5,
  "group": "win32高级设置",
  "group_order": 40,
  "advanced": true
}
```

推荐分组思路：

1. 输入来源
2. 输出目标
3. 写入策略
4. 校验与失败处理
5. 缓存与性能
6. 高级设置

这样 Qt 和后续 .NET 都能自动折叠复杂参数区，减少界面拥挤。

---

## 7. 参数显隐与联动规范

这是参数型插件最容易在多 UI 中失真的地方。

后续建议统一两个字段：

1. `visible_when`
2. `enabled_when`

示例：

```json
{
  "name": "directory_path",
  "label": "固定目录路径",
  "type": "folder_path",
  "visible_when": {
    "path_source": "插件参数=固定目录路径"
  }
}
```

或者更通用：

```json
{
  "visible_when": {
    "all": [
      {"field": "path_source", "equals": "插件参数=固定目录路径"}
    ]
  }
}
```

要求：

1. UI 只解释条件表达式，不再内置插件名分支逻辑。
2. 插件作者不应要求某个 UI 自己硬编码字段联动。

---

## 8. 动态候选规范

参数型插件后续应统一动态候选思路。

### 8.1 哪些场景必须走动态候选

1. 字段列表依赖所选表。
2. 配置名依赖插件内部保存项。
3. 表别名依赖当前工作流上下文。
4. 某些参数候选依赖前一个模式开关。

### 8.2 字段声明建议

```json
{
  "name": "source_file_field",
  "label": "源文件字段",
  "type": "dynamic_select",
  "depends_on": ["doc_table_alias"],
  "refresh_on_change": ["doc_table_alias"],
  "allow_custom": true,
  "empty_text": "当前没有可选字段"
}
```

### 8.3 UI 责任

1. 依赖字段变化时主动刷新候选。
2. 候选为空时显示明确提示，不静默失败。
3. 若当前值已不在候选中，应允许显示旧值并提示不匹配。

---

## 9. 候选来源 `options_source` 规范

为了减少 UI 猜测，建议对常见来源做标准化。

推荐来源类型：

1. `preview_headers`
2. `table_headers`
3. `table_names`
4. `input_tables`
5. `plugin_dynamic`
6. `static_choices`

示例：

```json
{
  "name": "path_field",
  "label": "文件路径字段",
  "type": "field_select",
  "options_source": {
    "type": "preview_headers"
  }
}
```

```json
{
  "name": "sample_table",
  "label": "可选数据库表",
  "type": "table_select",
  "options_source": {
    "type": "table_names"
  }
}
```

```json
{
  "name": "config_name",
  "label": "配置名称",
  "type": "dynamic_select",
  "options_source": {
    "type": "plugin_dynamic",
    "resolver": "get_dynamic_parameter_options"
  }
}
```

---

## 10. 警告与帮助信息规范

参数型插件虽然不复杂，但也需要标准的提示信息，避免用户不理解当前状态。

建议字段：

1. `help`
2. `warning`
3. `empty_text`
4. `invalid_value_text`

示例：

```json
{
  "name": "source_file_field",
  "label": "源文件字段",
  "type": "dynamic_select",
  "empty_text": "当前文档读取表没有可选字段",
  "invalid_value_text": "当前值不在候选列表中，但仍会保留原值"
}
```

这样 UI 就不用自己拼装同类提示文案。

---

## 11. 对现有插件的直接建议

### 11.1 `word_excel_read_to_db_plugin_v1.py`

后续建议补强：

1. `path_source` 与 `path_field / dir_field / directory_path` 的显隐条件。
2. `field_select` 候选来源说明。
3. 参数分组，例如“读取引擎”“文件来源”“写库行为”“缓存与失败处理”。

### 11.2 `word_excel_write_from_table_plugin_v2.py`

后续建议补强：

1. 大量字段选择参数的分组与折叠。
2. `word_text_write_mode`、`write_engine` 相关联动显隐。
3. 对 `number` 参数补充 `min / step / unit`。
4. 对输入字段候选来源进行统一声明。

### 11.3 `plugin_template_输出日志_后台进度_插件缓存版.py`

当前状态：

1. 模板已内置 `PARAMETER_UI_METADATA`。
2. 模板字段已覆盖 `group / group_order / order`。
3. 输入字段已提供 `options_source=preview_headers` 与 `empty_text`。
4. 数据库表字段已提供 `options_source=table_names` 与 `invalid_value_text`。
5. 缓存相关字段已提供 `enabled_when / visible_when / depends_on / refresh_on_change` 示例。
6. 测试已将模板固定为参数型插件 UI 元数据样板，后续新增插件应优先沿用该写法。

---

## 12. UI 侧需要遵守的边界

各 UI 需要遵守：

1. UI 负责按 schema 渲染，不负责重建插件参数语义。
2. UI 负责解释显隐条件，不负责插件业务判断。
3. UI 负责刷新动态候选，不负责发明候选来源。
4. UI 负责展示 help / warning / empty_text，不自行吞掉提示。
5. UI 遇到未知字段时应优雅降级。

---

## 13. 最终结论

参数型插件这条线，其实不需要大改执行逻辑，关键是把 schema 从“只有参数定义”补到“足够支撑统一 UI 渲染”。

后续只要把以下几类元数据逐步收紧：

1. 分组 `group`
2. 候选来源 `options_source`
3. 联动显隐 `visible_when / enabled_when`
4. 动态刷新 `depends_on / refresh_on_change`
5. 空候选提示 `empty_text`

那么 Qt 阶段的表单体验会更稳定，后续 `.NET` UI 也能直接沿用，而不需要再回头翻插件内部代码猜参数逻辑。
