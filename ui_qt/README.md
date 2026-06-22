# DataFlowKit Qt Prototype

This package is an isolated Qt UI prototype. It does not replace the current
Tkinter UI and does not change workflow execution.

## Goals

- Keep the current Python/Tkinter UI working.
- Provide a small compatibility layer for Qt5 and Qt6 bindings.
- Validate a future `QTableView`-based table preview path.
- Keep Qt optional; importing the repository must not require PyQt or PySide.
- Provide a first Qt6 workflow shell that calls the headless protocol engine by
  `node_type_id`.

## Supported Bindings

Default probing order:

1. `PySide6`
2. `PyQt6`
3. `PySide2`
4. `PyQt5`

Use `DATAFLOWKIT_QT_API=PyQt5` or another supported binding name to force one.

## Run Demo

Install one binding first:

```powershell
python -m pip install PySide6
```

Then run:

```powershell
python -m ui_qt.demo_table
```

For a Qt5/old-Windows compatibility line, use `PySide2` or `PyQt5` instead.

## Run Qt6 Shell

Install a Qt6 binding:

```powershell
python -m pip install PySide6
```

Then run:

```powershell
python -m ui_qt.app
```

For a startup smoke test without showing a window:

```powershell
python -m ui_qt.app --offscreen --smoke
```

The first shell now uses the same broad panel shape as the original workflow
window:

- `1. 输入数据源`
- `2. 工作流节点`
- `3. 计划模板`
- `4. 节点配置`
- `执行进度`
- `5. 输出设置`
- `6. 结果预览`

It includes workflow plan load/save, JSON/CSV/TSV input import, Chinese grouped
node catalog, node add/delete/move/copy/enable toggling, form-based node config,
preview to selected node, full headless preview, execution preview, and
switching between input and result tables.

Node menus, descriptions, warnings, and form groups come from the shared
`workflow.node_ui_schema` module. Other clients can request the same structure
through the headless engine or stdio actions `list_node_ui_schemas` and
`get_node_ui_schema`.
