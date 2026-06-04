import subprocess
import sys

subprocess.run([
    sys.executable,
    "-m",
    "PyInstaller",
    "-F",
    "DataFlowKit.py",
    "--hidden-import",
    "serial",
    "--hidden-import",
    "serial.tools.list_ports",
], check=True)
