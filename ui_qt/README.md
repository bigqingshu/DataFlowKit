# DataFlowKit Qt Prototype

This package is an isolated Qt UI prototype. It does not replace the current
Tkinter UI and does not change workflow execution.

## Goals

- Keep the current Python/Tkinter UI working.
- Provide a small compatibility layer for Qt5 and Qt6 bindings.
- Validate a future `QTableView`-based table preview path.
- Keep Qt optional; importing the repository must not require PyQt or PySide.

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

