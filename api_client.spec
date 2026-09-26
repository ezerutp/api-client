# PyInstaller spec:  pyinstaller api_client.spec
# Produces dist/api-client/ (one folder, fast start-up). Use --onefile for a single binary.
from pathlib import Path

block_cipher = None
root = Path(SPECPATH)

a = Analysis(
    [str(root / "main.py")],
    pathex=[str(root)],
    datas=[(str(root / "app" / "themes" / "style.qss"), "app/themes")],
    hiddenimports=["PySide6.QtSvg"],
    excludes=["tkinter", "PySide6.QtWebEngineCore", "PySide6.QtQml", "PySide6.Qt3DCore"],
    cipher=block_cipher,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="api-client", console=False)
coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas, name="api-client")
