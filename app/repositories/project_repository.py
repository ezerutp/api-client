from __future__ import annotations

from pathlib import Path

from app.models.project import Project
from app.storage.json_file import JsonFileError, read_json, write_json_atomic, write_text_atomic

PROJECT_FILE = "project.json"
SECRETS_FILE = ".secrets.json"
GITIGNORE_FILE = ".gitignore"
GITIGNORE_CONTENT = f"{SECRETS_FILE}\n"


class ProjectLoadError(Exception):
    """project.json is missing or unreadable. ``message`` is safe to show to users."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class ProjectRepository:
    def __init__(self, api_dir: Path) -> None:
        self.api_dir = api_dir

    @property
    def project_file(self) -> Path:
        return self.api_dir / PROJECT_FILE

    def exists(self) -> bool:
        return self.project_file.is_file()

    def load(self) -> Project:
        try:
            raw = read_json(self.project_file)
            return Project.from_dict(raw)
        except JsonFileError as exc:
            raise ProjectLoadError(f"Could not read {PROJECT_FILE}: {exc.message}.") from None
        except ValueError as exc:
            raise ProjectLoadError(f"{PROJECT_FILE} has an unexpected format: {exc}.") from None

    def save(self, project: Project) -> None:
        write_json_atomic(self.project_file, project.to_dict())

    def initialize(self, project: Project) -> None:
        """Create the api-client folder with project.json, .gitignore and an empty .secrets.json."""
        self.api_dir.mkdir(parents=True, exist_ok=True)
        self.save(project)
        self.ensure_gitignore()
        secrets = self.api_dir / SECRETS_FILE
        if not secrets.exists():
            write_json_atomic(secrets, {})

    def ensure_gitignore(self) -> None:
        gitignore = self.api_dir / GITIGNORE_FILE
        if not gitignore.exists():
            write_text_atomic(gitignore, GITIGNORE_CONTENT)
            return
        lines = gitignore.read_text(encoding="utf-8").splitlines()
        if SECRETS_FILE not in (line.strip() for line in lines):
            write_text_atomic(gitignore, "\n".join([*lines, SECRETS_FILE]) + "\n")
