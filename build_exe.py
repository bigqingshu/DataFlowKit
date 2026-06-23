import subprocess

subprocess.run([
    "python", "-m", "PyInstaller",
    "-F", "DataFlowKit.py",
    "--hidden-import", "serial",
    "--hidden-import", "serial.tools.list_ports",
#    "--noconsole"
])
