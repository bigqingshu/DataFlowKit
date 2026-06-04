# DataFlowKit

## 中文简介

DataFlowKit - 节点式表格与文件数据工作流工具。

一个基于 SQLite、Tkinter 和插件节点的数据工作流工具，支持表格解析、字段处理、批量重命名、子工作流和外部插件扩展。

DataFlowKit 面向 Windows 桌面场景，适合把剪贴板表格、SQLite 表、文件列表、Word/Excel 文档处理和自定义插件串成可预览、可执行、可复用的数据工作流。

## English Introduction

DataFlowKit is a node-based workflow tool for table and file data.

Built on SQLite, Tkinter, and plugin nodes, it supports table parsing, field processing, batch renaming, sub-workflows, and external plugin extensions.

It is designed for Windows desktop workflows where clipboard tables, SQLite tables, file lists, Word/Excel automation, and custom plugins need to be connected into previewable and reusable data pipelines.

## 主要功能 / Features

- 剪贴板表格解析与可编辑预览。 / Clipboard table parsing with editable preview.
- SQLite 表读取、保存、筛选、匹配和写回。 / SQLite table loading, saving, filtering, matching, and write-back.
- 节点式工作流，支持预览到节点、完整预览和正式执行。 / Node-based workflows with step preview, full preview, and execution.
- 文件列表、字段处理、批量重命名、子工作流。 / File listing, field processing, batch renaming, and sub-workflows.
- 后台执行、进度条、取消信号和错误日志。 / Background execution, progress reporting, cancellation, and error logs.
- 插件节点支持主程序环境和插件独立 Python 环境。 / Plugin nodes support both main-program and independent Python environments.
- 外部插件协议支持 `input.json` / `output.json` 和 stdout JSON 进度消息。 / External plugin protocol supports `input.json` / `output.json` and stdout JSON progress messages.

## 已包含插件 / Included Plugins

- `plugins/word_excel_read_to_db_plugin_v1.py`
  - 中文：读取 Word/Excel 文件，输出明细表，并可写入 SQLite。
  - English: Reads Word/Excel files, outputs detail rows, and can write results to SQLite.

- `plugins/word_excel_write_from_table_plugin_v2.py`
  - 中文：按输入表数据写回 Word/Excel，支持预览保护、批量目标文件和 Win32 Office 进程复用。
  - English: Writes table data back to Word/Excel with preview protection, batch target files, and Win32 Office process reuse.

- `plugins/plugin_template_输出日志_后台进度_插件缓存版.py`
  - 中文：插件开发模板，演示日志、后台进度、取消、数据库 API 和缓存。
  - English: Plugin development template demonstrating logs, progress, cancellation, database API, and caching.

> 中文：HEX 处理插件未包含在本仓库中。
>
> English: The HEX processing plugin is intentionally not included in this repository.

## 快速开始 / Quick Start

```powershell
python DataFlowKit.py
```

推荐环境：Windows + Python 3.8+。

Recommended environment: Windows + Python 3.8+.

安装可选依赖 / Install optional dependencies:

```powershell
python -m pip install -r requirements.txt
```

部分 Word/Excel Win32 功能需要 Microsoft Office 和 `pywin32`。

Some Word/Excel Win32 features require Microsoft Office and `pywin32`.

## 打包 EXE / Build EXE

```powershell
python scripts/build_exe.py
```

中文：程序会在脚本或 exe 同级目录查找 `plugins` 文件夹。发布单文件 exe 时，请把 `plugins` 文件夹放在 exe 同级目录，除非你修改了插件查找策略。

English: The application searches for the `plugins` folder next to the script or exe. When distributing a single-file exe, keep the `plugins` folder beside the exe unless you change the plugin lookup strategy.

## 插件说明 / Plugin Notes

中文：如果插件依赖没有打包进主程序，建议使用“插件独立环境”运行模式。插件可以通过单文件 `.py` 的 `PLUGIN_INFO` 注册，也可以通过 `plugin.json + entry.py` 的插件包注册。

English: If a plugin depends on packages not bundled into the main app, use the independent plugin Python environment. Plugins can be registered through a single `.py` file with `PLUGIN_INFO`, or through a `plugin.json + entry.py` package.

更多协议细节见 / See protocol details:

```text
docs/plugin_protocol.md
```

## 项目结构 / Project Layout

```text
DataFlowKit.py            # 主程序 / Main application
plugins/                  # 非 HEX 插件与模板 / Non-HEX plugins and template
docs/plugin_protocol.md   # 插件协议 / Plugin protocol
scripts/build_exe.py      # PyInstaller 打包脚本 / PyInstaller build helper
```
