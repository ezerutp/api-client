import os
import sys
from pathlib import Path

from app import APP_ID


def user_data_dir() -> Path:
    """Per-user folder for the SQLite database and logs (never inside a repository)."""
    override = os.environ.get("API_CLIENT_DATA_DIR")
    if override:
        return Path(override).expanduser()
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / APP_ID
