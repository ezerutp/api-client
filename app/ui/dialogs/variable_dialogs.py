"""Save a value (e.g. from a response) as a ``{{variable}}``."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtWidgets import QCheckBox, QComboBox, QDialog, QLineEdit, QWidget

from app.i18n import tr
from app.models.project import Project
from app.repositories.secrets_repository import Secrets
from app.services.variable_service import is_valid_variable_name, looks_secret
from app.ui.dialogs.base import BaseDialog
from app.ui.helpers import label, set_prop

_PREVIEW_LIMIT = 120


@dataclass
class SaveVariableResult:
    environment: str | None  # None -> globals
    name: str
    secret: bool


class SaveVariableDialog(BaseDialog):
    def __init__(self, parent: QWidget | None, project: Project, secrets: Secrets, current: str | None,
                 name: str, value: str) -> None:
        super().__init__(parent, tr("Save as variable"), width=460)
        self._project = project
        self._secrets = secrets
        self._current = current
        self._value = value

        self.name = QLineEdit(name)
        self.name.setPlaceholderText("token")
        self.name.textChanged.connect(self._update)
        self.scope = QComboBox()
        for env in project.environments.values():
            self.scope.addItem(env.display_name, env.name)
        self.scope.addItem(tr("Globals (every environment)"), None)
        index = self.scope.findData(current) if current in project.environments else self.scope.count() - 1
        self.scope.setCurrentIndex(index)
        self.scope.currentIndexChanged.connect(self._update)
        self.secret = QCheckBox(tr("Secret — stored in api-client/.secrets.json, never committed"))
        self.secret.setChecked(looks_secret(name))
        self.secret.toggled.connect(self._update)
        self.preview = label("", "Hint", wrap=True)
        self.notice = label("", "Hint", wrap=True)
        self.error = label("", "FieldError", wrap=True)
        self.error.hide()

        self.add_field(tr("Variable name"), self.name)
        self.add_field(tr("Save in"), self.scope)
        self.content.addWidget(self.secret)
        self.content.addSpacing(6)
        self.content.addWidget(self.preview)
        self.content.addWidget(self.notice)
        self.content.addWidget(self.error)
        self.ok_button.setText(tr("Save"))
        self._update()
        self.name.setFocus()
        self.name.selectAll()

    def _environment(self) -> str | None:
        return self.scope.currentData()

    def _defined_in(self, environment: str | None, name: str) -> bool:
        if environment is None:
            return name in self._project.variables or name in self._secrets.globals or \
                (name == "base_url" and bool(self._project.base_url))
        env = self._project.environments.get(environment)
        return (env is not None and name in env.variables) or name in self._secrets.for_environment(environment)

    def _update(self) -> None:
        name = self.name.text().strip()
        set_prop(self.name, "invalid", False)
        self.error.hide()
        value = "••••••" if self.secret.isChecked() else self._value
        if len(value) > _PREVIEW_LIMIT:
            value = value[:_PREVIEW_LIMIT] + "…"
        self.preview.setText(tr("Value: {value}", value=value or tr("(empty)")))
        environment = self._environment()
        variable = "{{" + name + "}}"
        notices = []
        if name and self._defined_in(environment, name):
            notices.append(tr("{var} already exists here; its value will be replaced.", var=variable))
        if name and environment is None and self._current and self._defined_in(self._current, name):
            notices.append(tr("The active environment also defines {var} and its value takes precedence.",
                              var=variable))
        self.notice.setText("\n".join(notices))
        self.notice.setVisible(bool(notices))

    def validate(self) -> bool:
        name = self.name.text().strip()
        if is_valid_variable_name(name):
            return True
        set_prop(self.name, "invalid", True)
        self.error.setText(tr("Use letters, numbers, _ . or -, starting with a letter or _."))
        self.error.show()
        return False

    def result_value(self) -> SaveVariableResult:
        return SaveVariableResult(self._environment(), self.name.text().strip(), self.secret.isChecked())

    @staticmethod
    def ask(parent: QWidget | None, project: Project, secrets: Secrets, current: str | None,
            name: str, value: str) -> SaveVariableResult | None:
        dialog = SaveVariableDialog(parent, project, secrets, current, name, value)
        return dialog.result_value() if dialog.exec() == QDialog.DialogCode.Accepted else None
