import sys
from pathlib import Path


def app_root() -> Path:
    """Folder containing the ``app`` package; works from source and PyInstaller bundles."""
    bundle_dir = getattr(sys, "_MEIPASS", None)
    if bundle_dir:
        return Path(bundle_dir)
    return Path(__file__).resolve().parent.parent.parent


def resource_path(*parts: str) -> Path:
    return app_root().joinpath("app", *parts)
