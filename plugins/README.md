# Plugins

This folder contains bundled DataFlowKit plugins that are safe to publish.

Included:

- `word_excel_read_to_db_plugin_v1.py`
  - `.doc/.docx/.docm` 统一遵循“读取策略”，支持临时转换 docx 后使用 XML 或 Win32 读取。
  - “保留旧格式转换docx后用win32读取”会保留源文档兼容模式，所有转换均不修改源文件。
- `word_excel_write_from_table_plugin_v2.py`
  - Word 支持段落、表格单元格、`word_text_range` 精确范围和 `word_global_replace` 全文/页眉页脚/形状文本替换。
  - 文件先写入同目录临时副本，成功后再替换目标；可配置失败恢复或保留写入前备份。
  - 支持内置运行和独立插件 `--input/--output` 协议。
- `plugin_template_输出日志_后台进度_插件缓存版.py`

The HEX processing plugin is intentionally excluded.
