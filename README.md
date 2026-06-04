# DataFlowKit

DataFlowKit is a Windows-oriented table workflow tool built with Tkinter and SQLite. It reads clipboard tables, lets users build node-based data workflows, and supports external plugin nodes with background progress, cancellation, logs, transit tables, and optional plugin-local caches.

## Highlights

- Clipboard table parsing and editable preview UI.
- SQLite table save/load, filtering, matching, write-back, and workflow output.
- Node-based workflow processing with preview, execution, progress bars, and cancellation.
- Plugin system with two execution modes:
  - main-program environment for simple plugins;
  - independent Python environment for plugins with extra dependencies.
- External plugin process protocol using `input.json` / `output.json` plus stdout JSON progress messages.
- Word/Excel read/write plugins included for document/table automation.

## Included Plugins

- `plugins/word_excel_read_to_db_plugin_v1.py`
  - Reads Word/Excel files into workflow tables or SQLite tables.
  - Supports Win32 Office automation and ZIP/XML parsing modes.
  - Includes plugin cache/progress/cancel support.

- `plugins/word_excel_write_from_table_plugin_v2.py`
  - Writes workflow data back into Word/Excel files.
  - Supports preview protection, target-file copy/write flows, and Win32 Office process reuse inside the node.

- `plugins/plugin_template_输出日志_后台进度_插件缓存版.py`
  - Template for plugin authors, including logs, progress, cancellation, database API, and cache examples.

The HEX processing plugin is intentionally not included in this repository.

## Quick Start

```powershell
python DataFlowKit.py
```

Recommended environment: Windows + Python 3.8+.

Install optional dependencies:

```powershell
python -m pip install -r requirements.txt
```

Some plugin features require Microsoft Office and `pywin32` when using Win32 read/write engines.

## Build EXE

```powershell
python scripts/build_exe.py
```

The application searches for plugins in the `plugins` directory next to the executable or script. If you distribute a single-file exe, keep the `plugins` folder beside the exe unless you also change the plugin lookup strategy.

## Plugin Notes

For plugins that need dependencies not bundled into the main exe, prefer the independent Python environment mode. A plugin can be registered by:

- a single `.py` file with `PLUGIN_INFO`; or
- a plugin folder containing `plugin.json` and an entry script.

See `docs/plugin_protocol.md` for the external plugin protocol.

## Project Layout

```text
DataFlowKit.py            # main application
plugins/                  # bundled non-HEX plugins and template
docs/plugin_protocol.md   # plugin protocol notes
scripts/build_exe.py      # PyInstaller build helper
```
