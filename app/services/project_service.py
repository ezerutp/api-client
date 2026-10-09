"""Everything that happens inside an open ``api-client/`` folder.

Qt-free: the UI calls these methods and reacts to their results.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from app import API_CLIENT_DIR_NAME
from app.models.api_request import ApiRequest, BodyType, HttpMethod, RequestBody
from app.models.collection import Collection
from app.models.environment import Environment
from app.models.project import Project
from app.repositories.collection_repository import CollectionRepository
from app.repositories.project_repository import PROJECT_FILE, ProjectLoadError, ProjectRepository
from app.repositories.secrets_repository import Secrets, SecretsRepository
from app.services.openapi_service import ImportedEndpoint, common_base_path, normalize_path
from app.services.variable_service import VariableContext, build_variable_context
from app.utils.logging_setup import secret_registry
from app.utils.slug import unique_name, unique_slug

log = logging.getLogger(__name__)

__all__ = ["ProjectLoadError", "ProjectService", "find_api_dir"]


def find_api_dir(folder: Path) -> Path | None:
    """Locate ``api-client/project.json`` for a selected folder.

    Accepts the backend root (``backend-tienda/``) or the ``api-client/`` folder itself.
    """
    folder = folder.expanduser().resolve()
    if folder.name == API_CLIENT_DIR_NAME and (folder / PROJECT_FILE).is_file():
        return folder
    candidate = folder / API_CLIENT_DIR_NAME
    if (candidate / PROJECT_FILE).is_file():
        return candidate
    return None


@dataclass
class OpenResult:
    service: ProjectService
    warnings: list[str] = field(default_factory=list)


@dataclass
class ImportSummary:
    requests: int = 0
    new_collections: list[str] = field(default_factory=list)
    #: Endpoints left out because the project already has the same method and path.
    skipped: int = 0


class ProjectService:
    def __init__(self, api_dir: Path, project: Project, collections: list[Collection], secrets: Secrets) -> None:
        self.api_dir = api_dir
        self.project = project
        self.secrets = secrets
        self._projects = ProjectRepository(api_dir)
        self._collections_repo = CollectionRepository(api_dir)
        self._secrets_repo = SecretsRepository(api_dir)
        self._collections = collections
        self._sort_collections()
        self._refresh_secret_registry()

    # -- lifecycle ------------------------------------------------------------------

    @property
    def root_dir(self) -> Path:
        return self.api_dir.parent

    @property
    def key(self) -> str:
        """Stable identifier for local state (recent projects, history, UI state)."""
        return str(self.root_dir)

    @classmethod
    def open(cls, api_dir: Path) -> OpenResult:
        projects = ProjectRepository(api_dir)
        if not projects.exists():
            raise ProjectLoadError(f"No {PROJECT_FILE} found in {api_dir}.")
        project = projects.load()
        projects.ensure_gitignore()
        collections, collection_warnings = CollectionRepository(api_dir).load_all()
        secrets, secrets_warning = SecretsRepository(api_dir).load()
        warnings = [f"{w.file_name}: {w.message}" for w in collection_warnings]
        if secrets_warning:
            warnings.append(secrets_warning)
        return OpenResult(cls(api_dir, project, collections, secrets), warnings)

    @classmethod
    def create(cls, root_dir: Path, name: str, base_url: str) -> ProjectService:
        api_dir = root_dir.expanduser().resolve() / API_CLIENT_DIR_NAME
        project = Project.new(name.strip() or root_dir.name, base_url.strip())
        ProjectRepository(api_dir).initialize(project)
        return cls(api_dir, project, [], Secrets())

    def reload(self) -> list[str]:
        result = ProjectService.open(self.api_dir)
        self.project = result.service.project
        self.secrets = result.service.secrets
        self._collections = result.service._collections
        self._refresh_secret_registry()
        return result.warnings

    # -- collections ----------------------------------------------------------------

    @property
    def collections(self) -> list[Collection]:
        return list(self._collections)

    def collection(self, collection_id: str) -> Collection | None:
        return next((c for c in self._collections if c.id == collection_id), None)

    def find_request(self, request_id: str) -> tuple[Collection, ApiRequest] | None:
        for collection in self._collections:
            request = collection.find_request(request_id)
            if request is not None:
                return collection, request
        return None

    def all_requests(self) -> list[tuple[Collection, ApiRequest]]:
        return [(c, r) for c in self._collections for r in c.requests]

    def create_collection(self, name: str, base_path: str = "") -> Collection:
        name = name.strip() or "New collection"
        collection_id = unique_slug(name, self._taken_collection_ids())
        collection = Collection(id=collection_id, name=name, base_path=normalize_base_path(base_path))
        self._collections_repo.save(collection)
        self._collections.append(collection)
        self._save_order()
        return collection

    def update_collection(self, collection_id: str, *, name: str, base_path: str) -> Collection:
        """Rename a collection; its file is renamed too so the folder stays readable."""
        collection = self._require_collection(collection_id)
        name = name.strip() or collection.name
        new_id = collection.id
        if name != collection.name:
            taken = self._taken_collection_ids() - {collection.id}
            new_id = unique_slug(name, taken)
        collection.name = name
        collection.base_path = normalize_base_path(base_path)
        if new_id != collection.id:
            old_id = collection.id
            collection.id = new_id
            self._collections_repo.save(collection)
            self._collections_repo.delete(old_id)
            self.project.collection_order = [new_id if c == old_id else c for c in self.project.collection_order]
            self._save_order()
        else:
            self._collections_repo.save(collection)
        return collection

    def duplicate_collection(self, collection_id: str) -> Collection:
        source = self._require_collection(collection_id)
        name = unique_name(source.name, {c.name for c in self._collections})
        copy = Collection(
            id=unique_slug(name, self._taken_collection_ids()),
            name=name,
            base_path=source.base_path,
            description=source.description,
            requests=[r.clone() for r in source.requests],
        )
        self._collections_repo.save(copy)
        self._collections.insert(self._collections.index(source) + 1, copy)
        self._save_order()
        return copy

    def import_endpoints(self, endpoints: list[ImportedEndpoint]) -> ImportSummary:
        """Add imported requests, grouped by collection name. Existing method + path pairs are skipped,
        so importing the same spec again only brings in what is new."""
        summary = ImportSummary()
        taken = {(r.method.value, normalize_path(r.url)) for c in self._collections for r in c.requests}
        grouped: dict[str, list[ImportedEndpoint]] = {}
        for endpoint in endpoints:
            if endpoint.key in taken:
                summary.skipped += 1
                continue
            taken.add(endpoint.key)
            grouped.setdefault(endpoint.collection, []).append(endpoint)
        for name, items in grouped.items():
            collection = next((c for c in self._collections if c.name.casefold() == name.casefold()), None)
            if collection is None:
                collection = Collection(id=unique_slug(name, self._taken_collection_ids()), name=name,
                                        base_path=common_base_path([e.path for e in items]))
                self._collections.append(collection)
                summary.new_collections.append(name)
            collection.requests += [e.request.clone() for e in items]
            self._collections_repo.save(collection)
            summary.requests += len(items)
        if summary.new_collections:
            self._save_order()
        return summary

    def delete_collection(self, collection_id: str) -> Collection:
        collection = self._require_collection(collection_id)
        self._collections_repo.delete(collection.id)
        self._collections.remove(collection)
        self._save_order()
        return collection

    def move_collection(self, collection_id: str, offset: int) -> None:
        collection = self._require_collection(collection_id)
        index = self._collections.index(collection)
        target = max(0, min(len(self._collections) - 1, index + offset))
        self._collections.insert(target, self._collections.pop(index))
        self._save_order()

    # -- requests -------------------------------------------------------------------

    def create_request(self, collection_id: str, name: str, method: HttpMethod, url: str | None = None) -> ApiRequest:
        collection = self._require_collection(collection_id)
        if url is None:
            url = "{{base_url}}" + collection.base_path
        body = RequestBody(BodyType.JSON, "{\n  \n}") if method.usually_has_body else RequestBody()
        request = ApiRequest(name=name.strip() or "New request", method=method, url=url.strip(), body=body)
        collection.requests.append(request)
        self._collections_repo.save(collection)
        return request

    def save_request(self, request_id: str) -> None:
        """Persist the in-memory state of a request (used by autosave)."""
        found = self.find_request(request_id)
        if found is None:
            return
        collection, request = found
        request.touch()
        self._collections_repo.save(collection)

    def save_collection(self, collection_id: str) -> None:
        self._collections_repo.save(self._require_collection(collection_id))

    def rename_request(self, request_id: str, name: str) -> ApiRequest:
        collection, request = self._require_request(request_id)
        request.name = name.strip() or request.name
        request.touch()
        self._collections_repo.save(collection)
        return request

    def duplicate_request(self, request_id: str) -> ApiRequest:
        collection, request = self._require_request(request_id)
        copy = request.clone(name=unique_name(request.name, {r.name for r in collection.requests}))
        collection.requests.insert(collection.index_of(request_id) + 1, copy)
        self._collections_repo.save(collection)
        return copy

    def move_request(self, request_id: str, target_collection_id: str, index: int | None = None) -> None:
        source, request = self._require_request(request_id)
        target = self._require_collection(target_collection_id)
        source.requests.remove(request)
        position = len(target.requests) if index is None else max(0, min(index, len(target.requests)))
        target.requests.insert(position, request)
        request.touch()
        # Write the destination first: a crash in between duplicates rather than loses the request.
        self._collections_repo.save(target)
        if source is not target:
            self._collections_repo.save(source)

    def delete_request(self, request_id: str) -> ApiRequest:
        collection, request = self._require_request(request_id)
        collection.requests.remove(request)
        self._collections_repo.save(collection)
        return request

    # -- environments & variables ---------------------------------------------------

    @property
    def environment_names(self) -> list[str]:
        return list(self.project.environments)

    def default_environment(self) -> str | None:
        names = self.environment_names
        if self.project.active_environment in names:
            return self.project.active_environment
        return names[0] if names else None

    def variable_context(self, environment: str | None) -> VariableContext:
        return build_variable_context(self.project, self.secrets, environment)

    def save_environments(
        self,
        global_variables: dict[str, str],
        global_secrets: dict[str, str],
        environments: dict[str, tuple[dict[str, str], dict[str, str]]],
    ) -> None:
        """Replace all variables. ``environments`` maps name -> (variables, secrets)."""
        variables = dict(global_variables)
        # The global base_url lives in the project default; removing it (or making it secret) clears that.
        self.project.base_url = variables.pop("base_url", "")
        self.project.variables = variables
        self.project.environments = {
            name: Environment(name, dict(values)) for name, (values, _) in environments.items()
        }
        if self.project.active_environment not in self.project.environments:
            self.project.active_environment = next(iter(self.project.environments), "")
        self.secrets = Secrets(
            globals=dict(global_secrets),
            by_environment={name: dict(secret) for name, (_, secret) in environments.items() if secret},
        )
        self._projects.save(self.project)
        self._secrets_repo.save(self.secrets)
        self._projects.ensure_gitignore()
        self._refresh_secret_registry()

    def set_variable(self, environment: str | None, name: str, value: str, *, secret: bool = False) -> None:
        """Create or replace one variable. ``environment=None`` means the globals.

        A variable lives in exactly one place per scope: saving it as secret removes the plain
        copy (and the other way round), so the stored value is the one that gets used.
        """
        if environment is not None and environment not in self.project.environments:
            raise KeyError(f"Unknown environment: {environment}")
        if environment is None:
            plain = self.project.variables
            secrets = self.secrets.globals
        else:
            plain = self.project.environments[environment].variables
            secrets = self.secrets.by_environment.setdefault(environment, {})
        if secret:
            plain.pop(name, None)
            if environment is None and name == "base_url":
                self.project.base_url = ""
            secrets[name] = value
        else:
            secrets.pop(name, None)
            if environment is None and name == "base_url":
                self.project.base_url = value
            else:
                plain[name] = value
        if environment is not None and not secrets:
            self.secrets.by_environment.pop(environment, None)
        self._projects.save(self.project)
        self._secrets_repo.save(self.secrets)
        if secret:
            self._projects.ensure_gitignore()
        self._refresh_secret_registry()

    def add_environment(self, name: str, base_url: str = "") -> str:
        name = unique_slug(name, set(self.project.environments), fallback="environment")
        variables = {"base_url": base_url} if base_url else {}
        self.project.environments[name] = Environment(name, variables)
        self._projects.save(self.project)
        return name

    def delete_variable(self, environment: str | None, name: str) -> bool:
        """Remove a variable (plain or secret) from one scope. Returns False if it was not there."""
        if environment is not None and environment not in self.project.environments:
            raise KeyError(f"Unknown environment: {environment}")
        if environment is None:
            plain, secrets = self.project.variables, self.secrets.globals
        else:
            plain = self.project.environments[environment].variables
            secrets = self.secrets.by_environment.get(environment, {})
        found = plain.pop(name, None) is not None
        found = secrets.pop(name, None) is not None or found
        if environment is None and name == "base_url" and self.project.base_url:
            self.project.base_url = ""
            found = True
        if environment is not None and not secrets:
            self.secrets.by_environment.pop(environment, None)
        if found:
            self._projects.save(self.project)
            self._secrets_repo.save(self.secrets)
            self._refresh_secret_registry()
        return found

    def rename_environment(self, old: str, new: str) -> str:
        self._require_environment(old)
        new = unique_slug(new, set(self.project.environments) - {old}, fallback="environment")
        if new == old:
            return old
        self.project.environments = {
            (new if k == old else k): (Environment(new, env.variables) if k == old else env)
            for k, env in self.project.environments.items()
        }
        if old in self.secrets.by_environment:
            self.secrets.by_environment[new] = self.secrets.by_environment.pop(old)
        if self.project.active_environment == old:
            self.project.active_environment = new
        self._projects.save(self.project)
        self._secrets_repo.save(self.secrets)
        return new

    def duplicate_environment(self, source: str, name: str | None = None) -> str:
        env = self._require_environment(source)
        name = unique_slug(name or f"{source}-copy", set(self.project.environments), fallback="environment")
        self.project.environments[name] = Environment(name, dict(env.variables))
        if source in self.secrets.by_environment:
            self.secrets.by_environment[name] = dict(self.secrets.by_environment[source])
        self._projects.save(self.project)
        self._secrets_repo.save(self.secrets)
        return name

    def delete_environment(self, name: str) -> None:
        self._require_environment(name)
        del self.project.environments[name]
        self.secrets.by_environment.pop(name, None)
        if self.project.active_environment == name:
            self.project.active_environment = next(iter(self.project.environments), "")
        self._projects.save(self.project)
        self._secrets_repo.save(self.secrets)
        self._refresh_secret_registry()

    def set_active_environment(self, name: str) -> None:
        """The environment selected by default when the project is opened."""
        self._require_environment(name)
        self.project.active_environment = name
        self._projects.save(self.project)

    def update_project(self, *, name: str, base_url: str) -> None:
        self.project.name = name.strip() or self.project.name
        old_base_url, new_base_url = self.project.base_url, base_url.strip()
        self.project.base_url = new_base_url
        # Environments created with a copy of the default keep following it; custom ones stay as they are.
        for env in self.project.environments.values():
            if env.variables.get("base_url") == old_base_url:
                env.variables["base_url"] = new_base_url
        self._projects.save(self.project)

    # -- helpers --------------------------------------------------------------------

    def _require_collection(self, collection_id: str) -> Collection:
        collection = self.collection(collection_id)
        if collection is None:
            raise KeyError(f"Unknown collection: {collection_id}")
        return collection

    def _require_request(self, request_id: str) -> tuple[Collection, ApiRequest]:
        found = self.find_request(request_id)
        if found is None:
            raise KeyError(f"Unknown request: {request_id}")
        return found

    def _require_environment(self, name: str) -> Environment:
        env = self.project.environments.get(name)
        if env is None:
            raise KeyError(f"Unknown environment: {name}")
        return env

    def _taken_collection_ids(self) -> set[str]:
        taken = {c.id for c in self._collections}
        # Files we could not load still occupy their name: never overwrite them.
        taken |= {p.stem for p in self._collections_repo.collection_files()}
        return taken

    def _sort_collections(self) -> None:
        order = {cid: i for i, cid in enumerate(self.project.collection_order)}
        self._collections.sort(key=lambda c: (order.get(c.id, len(order)), c.name.lower()))

    def _save_order(self) -> None:
        self.project.collection_order = [c.id for c in self._collections]
        self._projects.save(self.project)

    def _refresh_secret_registry(self) -> None:
        secret_registry.replace_all(self.secrets.all_values())


def normalize_base_path(path: str) -> str:
    path = path.strip()
    if not path:
        return ""
    if "{{" not in path and not path.startswith("/"):
        path = "/" + path
    return path.rstrip("/") if len(path) > 1 else path

