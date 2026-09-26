from __future__ import annotations

import copy

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QListWidget,
    QSpinBox,
    QStackedWidget,
    QWidget,
)

from app.i18n import SUPPORTED_LANGUAGES, tr
from app.models.settings import AppSettings
from app.ui.dialogs.base import BaseDialog
from app.ui.helpers import hbox, label, vbox


def _row(caption: str, widget: QWidget, hint: str = "") -> QWidget:
    row = QWidget()
    left = vbox(label(caption), spacing=2)
    if hint:
        left.addWidget(label(hint, "Hint", wrap=True))
    row.setLayout(hbox(left, None, widget, spacing=16, margins=(0, 4, 0, 4)))
    return row


class SettingsDialog(BaseDialog):
    def __init__(self, parent: QWidget | None, settings: AppSettings) -> None:
        super().__init__(parent, tr("Settings"), width=640)
        self.setMinimumHeight(400)
        self._settings = copy.deepcopy(settings)

        self.open_last = QCheckBox()
        self.open_last.setChecked(settings.open_last_project)
        self.autosave = QCheckBox()
        self.autosave.setChecked(settings.autosave)
        self.recent_limit = QSpinBox()
        self.recent_limit.setRange(1, 50)
        self.recent_limit.setValue(settings.recent_limit)
        self.history_limit = QSpinBox()
        self.history_limit.setRange(10, 10_000)
        self.history_limit.setSingleStep(50)
        self.history_limit.setValue(settings.history_limit)

        self.language = QComboBox()
        self.language.addItem(tr("System default"), "system")
        for code, name in SUPPORTED_LANGUAGES.items():
            self.language.addItem(name, code)
        self.language.setCurrentIndex(max(0, self.language.findData(settings.language)))
        self.theme = QComboBox()
        for key, text in (("dark", tr("Dark")), ("light", tr("Light")), ("system", tr("System"))):
            self.theme.addItem(text, key)
        self.theme.setCurrentIndex(max(0, self.theme.findData(settings.theme)))
        self.font_size = QSpinBox()
        self.font_size.setRange(9, 24)
        self.font_size.setSuffix(tr(" px"))
        self.font_size.setValue(settings.editor_font_size)

        self.timeout = QDoubleSpinBox()
        self.timeout.setRange(1, 600)
        self.timeout.setDecimals(0)
        self.timeout.setSuffix(tr(" s"))
        self.timeout.setValue(settings.network.timeout_seconds)
        self.verify_ssl = QCheckBox()
        self.verify_ssl.setChecked(settings.network.verify_ssl)
        self.follow_redirects = QCheckBox()
        self.follow_redirects.setChecked(settings.network.follow_redirects)
        for spin in (self.recent_limit, self.history_limit, self.font_size, self.timeout):
            spin.setFixedWidth(110)
        self.theme.setFixedWidth(130)
        self.language.setFixedWidth(190)

        general = self._page(
            _row(tr("Open last project on startup"), self.open_last),
            _row(tr("Autosave"), self.autosave, tr("Save request changes automatically while you type.")),
            _row(tr("Recent projects shown"), self.recent_limit),
            _row(tr("History entries kept per project"), self.history_limit),
        )
        appearance = self._page(
            _row(tr("Language"), self.language, tr("Interface language.")),
            _row(tr("Theme"), self.theme),
            _row(tr("Editor font size"), self.font_size, tr("Body and response editors.")),
        )
        network = self._page(
            _row(tr("Timeout"), self.timeout, tr("Maximum time to wait for the server.")),
            _row(tr("Verify SSL certificates"), self.verify_ssl, tr("Disable only for local self-signed certificates.")),
            _row(tr("Follow redirects"), self.follow_redirects),
        )
        self.pages = QStackedWidget()
        for page in (general, appearance, network):
            self.pages.addWidget(page)
        self.nav = QListWidget()
        self.nav.setObjectName("SettingsNav")
        self.nav.addItems([tr("General"), tr("Appearance"), tr("Network")])
        self.nav.setFixedWidth(150)
        self.nav.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.nav.setCurrentRow(0)
        self.content.addLayout(hbox(self.nav, 12, self.pages, spacing=8), 1)
        self.ok_button.setText(tr("Save"))

    @staticmethod
    def _page(*rows: QWidget) -> QWidget:
        page = QWidget()
        page.setLayout(vbox(*rows, None, spacing=4))
        return page

    def result_value(self) -> AppSettings:
        s = self._settings
        s.open_last_project = self.open_last.isChecked()
        s.autosave = self.autosave.isChecked()
        s.recent_limit = self.recent_limit.value()
        s.history_limit = self.history_limit.value()
        s.theme = self.theme.currentData()
        s.language = self.language.currentData()
        s.editor_font_size = self.font_size.value()
        s.network.timeout_seconds = float(self.timeout.value())
        s.network.verify_ssl = self.verify_ssl.isChecked()
        s.network.follow_redirects = self.follow_redirects.isChecked()
        return s

    @staticmethod
    def ask(parent: QWidget | None, settings: AppSettings) -> AppSettings | None:
        dialog = SettingsDialog(parent, settings)
        return dialog.result_value() if dialog.exec() == QDialog.DialogCode.Accepted else None
