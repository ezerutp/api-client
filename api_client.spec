# PyInstaller spec:  pyinstaller api_client.spec
# Produces dist/api-client/ (one folder, fast start-up). Use --onefile for a single binary.
import sys
from pathlib import Path

block_cipher = None
root = Path(SPECPATH)

_windows_icon = root / "assets" / "api-client.ico"
icon = str(_windows_icon) if sys.platform == "win32" and _windows_icon.exists() else None

a = Analysis(
    [str(root / "main.py")],
    pathex=[str(root)],
    datas=[(str(root / "app" / "themes" / "style.qss"), "app/themes")],
    hiddenimports=["PySide6.QtSvg"],
    excludes=["tkinter", "PySide6.QtWebEngineCore", "PySide6.QtQml", "PySide6.Qt3DCore"],
    cipher=block_cipher,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# One console-subsystem exe (CLI on PATH, see README > Command line: stdout/stderr need
# a real console) and, on Windows only, a second windowed one with no console at all for
# desktop/Start Menu shortcuts -- mirrors python.exe vs pythonw.exe. Both share the same
# Analysis/PYZ, so this costs two small extra stub binaries, not a second full build.
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="api-client", console=True, icon=icon)
binaries = [exe]
if sys.platform == "win32":
    exe_windowed = EXE(
        pyz, a.scripts, [], exclude_binaries=True, name="api-clientw", console=False, icon=icon,
    )
    binaries.append(exe_windowed)

coll = COLLECT(*binaries, a.binaries, a.zipfiles, a.datas, name="api-client")
