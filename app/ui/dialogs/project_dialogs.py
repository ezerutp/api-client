from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QDialog, QFileDialog, QLineEdit, QWidget

from app import API_CLIENT_DIR_NAME
from app.i18n import tr
from app.repositories.project_repository import PROJECT_FILE
from app.ui.dialogs.base import BaseDialog, field_error_label
from app.ui.helpers import button, hbox, label, set_prop


def _default_name(folder: Path) -> str:
    return folder.name.replace("-", " ").replace("_", " ").title() if folder.name else ""


class CreateProjectDialog(BaseDialog):
    """Name + backend folder + base URL. Creates ``<folder>/api-client/``."""

    def __init__(self, parent: QWidget | None, folder: Path | None = None) -> None:
        super().__init__(parent, tr("Create API Client Project"), width=500)
        self._name_touched = False
        self.name = QLineEdit(_default_name(folder) if folder else "")
        self.name.setPlaceholderText("Backend Tienda")
        self.name.textEdited.connect(self._on_name_edited)
        self.folder = QLineEdit(str(folder) if folder else "")
        self.folder.setPlaceholderText("/home/user/projects/backend-tienda")
        self.folder.textChanged.connect(self._update_preview)
        browse = button(tr("Browse…"), on_click=self._browse)
        self.base_url = QLineEdit("http://localhost:8080")
        self.preview = label("", "Hint", wrap=True)
        self.error = field_error_label()

        self.add_field(tr("Project name"), self.name)
        self.add_field(tr("Backend folder"), layout=hbox(self.folder, browse, spacing=6))
        self.add_field(tr("Base URL"), self.base_url, hint=tr("Available in requests as {{base_url}}. You can add more "
                                                          "environments (dev, production…) later."))
        self.content.addWidget(self.preview)
        self.content.addWidget(self.error)
        self.ok_button.setText(tr("Create"))
        self._update_preview()
        (self.folder if not folder else self.name).setFocus()

    def _on_name_edited(self) -> None:
        self._name_touched = True

    def _browse(self) -> None:
        start = self.folder.text() or str(Path.home())
        chosen = QFileDialog.getExistingDirectory(self, tr("Select the backend project folder"), start)
        if chosen:
            self.folder.setText(chosen)
            if not self._name_touched:
                self.name.setText(_default_name(Path(chosen)))

    def _update_preview(self) -> None:
        text = self.folder.text().strip()
        if not text:
            self.preview.setText("")
            return
        api_dir = Path(text).expanduser() / API_CLIENT_DIR_NAME
        if (api_dir / PROJECT_FILE).exists():
            self.preview.setText(tr("A project already exists in {path}. It will be opened instead.", path=api_dir))
            self.ok_button.setText(tr("Open"))
        else:
            self.preview.setText(tr("Will create {path}/ with project.json, .secrets.json and .gitignore", path=api_dir))
            self.ok_button.setText(tr("Create"))

    def validate(self) -> bool:
        folder = Path(self.folder.text().strip()).expanduser()
        problems = []
        if not self.folder.text().strip() or not folder.is_dir():
            problems.append(tr("Choose an existing folder (the root of your backend project)."))
        if not self.name.text().strip():
            problems.append(tr("Enter a project name."))
        url = self.base_url.text().strip()
        if url and not url.startswith(("http://", "https://", "{{")):
            problems.append(tr("The base URL should start with http:// or https://"))
        set_prop(self.folder, "invalid", bool(problems and "folder" in problems[0]))
        set_prop(self.name, "invalid", not self.name.text().strip())
        self.error.setText("\n".join(problems))
        self.error.setVisible(bool(problems))
        return not problems

    def values(self) -> tuple[Path, str, str]:
        return Path(self.folder.text().strip()).expanduser(), self.name.text().strip(), self.base_url.text().strip()

    @staticmethod
    def ask(parent: QWidget | None, folder: Path | None = None) -> tuple[Path, str, str] | None:
        dialog = CreateProjectDialog(parent, folder)
        return dialog.values() if dialog.exec() == QDialog.DialogCode.Accepted else None


class ProjectSettingsDialog(BaseDialog):
    def __init__(self, parent: QWidget | None, name: str, base_url: str, api_dir: Path) -> None:
        super().__init__(parent, tr("Project settings"), width=460)
        self.name = QLineEdit(name)
        self.base_url = QLineEdit(base_url)
        self.add_field(tr("Project name"), self.name)
        self.add_field(tr("Default base URL"), self.base_url,
                       hint=tr("Used as {{base_url}} when the active environment does not define its own."))
        location = label(str(api_dir), "Hint", wrap=True)
        self.add_field(tr("Location"), location)
        self.ok_button.setText(tr("Save"))

    @staticmethod
    def ask(parent: QWidget | None, name: str, base_url: str, api_dir: Path) -> tuple[str, str] | None:
        dialog = ProjectSettingsDialog(parent, name, base_url, api_dir)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.name.text().strip(), dialog.base_url.text().strip()
        return None
