"""Application start-up: logging, database, theme, main window."""

from __future__ import annotations

import logging
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QApplication

from app import APP_ID, APP_NAME, APP_VERSION
from app.repositories import (
    HistoryRepository, RecentProjectsRepository, SettingsRepository, UiStateRepository,
)
from app.storage.database import Database
from app.storage.paths import user_data_dir
from app.themes.manager import ThemeManager
from app.utils.logging_setup import configure_logging

log = logging.getLogger(__name__)


def _app_icon() -> QIcon:
    from app.themes.theme import DARK
    from app.ui import icons

    result = QIcon()
    for size in (16, 32, 64, 128):
        result.addPixmap(icons.pixmap("box", DARK.accent, size, 2.0))
    return result


def run(argv: list[str] | None = None) -> int:
    argv = sys.argv if argv is None else argv
    data_dir = user_data_dir()
    configure_logging(data_dir / "logs")
    log.info("Starting %s %s", APP_NAME, APP_VERSION)

    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_ID)
    app.setApplicationVersion(APP_VERSION)
    app.setDesktopFileName(APP_ID)
    app.setStyle("Fusion")
    font = QFont(app.font())
    font.setPixelSize(13)
    app.setFont(font)
    app.setWindowIcon(_app_icon())

    db = Database(data_dir / "api-client.db")
    settings_repo = SettingsRepository(db)
    settings = settings_repo.load()
    ThemeManager.instance().apply(settings.theme, editor_font_size=settings.editor_font_size)

    from app.ui.main_window import AppContext, MainWindow

    window = MainWindow(AppContext(
        db=db,
        settings_repo=settings_repo,
        recent=RecentProjectsRepository(db),
        history=HistoryRepository(db),
        ui_state=UiStateRepository(db),
        settings=settings,
    ))
    window.show()

    from pathlib import Path

    folder_arg = next((a for a in argv[1:] if not a.startswith("-")), None)
    if folder_arg:
        window.open_folder(Path(folder_arg).expanduser())
    else:
        window.open_last_project_if_enabled()

    exit_code = app.exec()
    db.close()
    return exit_code
