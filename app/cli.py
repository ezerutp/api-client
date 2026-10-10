"""Command line interface: ``api-client <command> ...``.

Every feature of the desktop app is reachable from here: projects, collections,
requests, environments and variables, OpenAPI / cURL import, sending requests,
history and settings. Qt is never imported, so it also runs on servers and in CI.

The project is found like Git finds a repository: ``--project DIR`` or the current
folder, walking up until a folder with ``api-client/project.json`` turns up.
"""

from __future__ import annotations

import argparse
import getpass
import json
import sys
from dataclasses import fields
from datetime import datetime
from pathlib import Path
from typing import Any, TextIO

from app import API_CLIENT_DIR_NAME, APP_NAME, APP_VERSION
from app.models.api_request import (
    ApiRequest,
    BodyType,
    HttpMethod,
    KeyValue,
    PathParameter,
    RequestBody,
    RequestHeader,
    RequestParameter,
)
from app.models.auth import Authentication, AuthType
from app.models.collection import Collection
from app.models.history import HistoryEntry
from app.models.settings import AppSettings, NetworkSettings
from app.network.errors import RequestError
from app.services.curl_service import CurlParseError, base_url_for, build_curl, parse_curl
from app.services.openapi_service import OpenApiError, parse_openapi
from app.services.project_service import ProjectLoadError, ProjectService, find_api_dir
from app.services.request_builder import extract_path_param_names
from app.services.variable_service import VariableError, is_valid_variable_name
from app.storage.json_file import JsonFileError
from app.utils.formatting import format_duration, format_size

DEFAULT_OPENAPI_SOURCE = "{{base_url}}/v3/api-docs"
SECRET_MASK = "••••••"

#: First words that switch ``main.py`` from the desktop app to the CLI.
COMMANDS = {
    "project", "collection", "col", "request", "req", "run", "send", "curl", "env", "var",
    "import", "history", "settings", "help",
}
_HELP_FLAGS = {"-h", "--help", "--version", "-V"}


def is_cli_invocation(args: list[str]) -> bool:
    """``args`` excludes the program name. No arguments, or a folder, opens the desktop app."""
    return bool(args) and (args[0] in COMMANDS or args[0] in _HELP_FLAGS)


class CliError(Exception):
    """A user facing failure: printed as ``error: <message>``, exit code 1."""


# ============================================================================ context

class Cli:
    def __init__(self, args: argparse.Namespace, out: TextIO, err: TextIO, stdin: TextIO) -> None:
        self.args = args
        self.out = out
        self.err = err
        self.stdin = stdin
        self._service: ProjectService | None = None
        self._db = None

    # -- output ---------------------------------------------------------------------

    def print(self, text: str = "") -> None:
        print(text, file=self.out)

    def warn(self, text: str) -> None:
        print(f"warning: {text}", file=self.err)

    def info(self, text: str) -> None:
        print(text, file=self.err)

    def emit_json(self, value: Any) -> None:
        self.print(json.dumps(value, indent=2, ensure_ascii=False))

    def table(self, headers: list[str], rows: list[list[str]], empty: str) -> None:
        if not rows:
            self.info(empty)
            return
        widths = [max(len(h), *(len(r[i]) for r in rows)) for i, h in enumerate(headers)]
        for row in [headers, *rows]:
            self.print("  ".join(cell.ljust(w) for cell, w in zip(row, widths, strict=True)).rstrip())

    def confirm(self, question: str) -> None:
        if getattr(self.args, "yes", False):
            return
        if not self.stdin.isatty():
            raise CliError(f"{question} Pass --yes to confirm when not running interactively.")
        print(f"{question} [y/N] ", end="", file=self.err, flush=True)
        if self.stdin.readline().strip().lower() not in ("y", "yes", "s", "si", "sí"):
            raise CliError("Cancelled.")

    def read_text(self, value: str) -> str:
        """``-`` reads stdin, ``@path`` reads a file, anything else is used as is."""
        if value == "-":
            return self.stdin.read()
        if value.startswith("@"):
            return read_file(Path(value[1:]))
        return value

    # -- project --------------------------------------------------------------------

    @property
    def start_dir(self) -> Path:
        return Path(getattr(self.args, "project", None) or ".").expanduser().resolve()

    @property
    def service(self) -> ProjectService:
        if self._service is None:
            api_dir = locate_project(self.start_dir)
            if api_dir is None:
                raise CliError(f"No {API_CLIENT_DIR_NAME}/project.json found in {self.start_dir} or its parents. "
                               "Create one with: api-client project init")
            result = ProjectService.open(api_dir)
            for warning in result.warnings:
                self.warn(warning)
            self._service = result.service
        return self._service

    @property
    def db(self):
        if self._db is None:
            from app.storage.database import Database
            from app.storage.paths import user_data_dir

            data_dir = user_data_dir()
            data_dir.mkdir(parents=True, exist_ok=True)
            self._db = Database(data_dir / "api-client.db")
        return self._db

    def settings(self) -> AppSettings:
        from app.repositories import SettingsRepository

        return SettingsRepository(self.db).load()

    def close(self) -> None:
        if self._db is not None:
            self._db.close()

    # -- selectors ------------------------------------------------------------------

    def collection(self, selector: str) -> Collection:
        collections = self.service.collections
        exact = [c for c in collections if c.id == selector]
        if exact:
            return exact[0]
        matches = [c for c in collections if c.name.casefold() == selector.casefold()]
        if len(matches) == 1:
            return matches[0]
        if matches:
            raise CliError(f"More than one collection is called “{selector}”; use its id: "
                           + ", ".join(c.id for c in matches))
        raise CliError(f"Unknown collection: {selector}. See: api-client collection ls")

    def request(self, selector: str) -> tuple[Collection, ApiRequest]:
        """By id, ``collection/request name`` or a request name that is unique in the project."""
        found = self.service.find_request(selector)
        if found is not None:
            return found
        candidates = self.service.all_requests()
        if "/" in selector:
            prefix, _, name = selector.partition("/")
            try:
                collection = self.collection(prefix)
            except CliError:
                collection = None
            if collection is not None:
                candidates = [(collection, r) for r in collection.requests]
                selector = name
        matches = [(c, r) for c, r in candidates if r.name.casefold() == selector.casefold()]
        if len(matches) == 1:
            return matches[0]
        if matches:
            raise CliError(f"More than one request is called “{selector}”; use collection/name or its id: "
                           + ", ".join(f"{r.id} ({c.name})" for c, r in matches))
        raise CliError(f"Unknown request: {selector}. See: api-client request ls")

    def environment(self, name: str | None, *, default: bool) -> str | None:
        """Validate ``--env``. ``default=True`` falls back to the project's active environment."""
        if name is None:
            return self.service.default_environment() if default else None
        names = self.service.environment_names
        if name in names:
            return name
        folded = [n for n in names if n.casefold() == name.casefold()]
        if folded:
            return folded[0]
        raise CliError(f"Unknown environment: {name}. Available: {', '.join(names) or 'none'}")


def locate_project(start: Path) -> Path | None:
    for folder in (start, *start.parents):
        api_dir = find_api_dir(folder)
        if api_dir is not None:
            return api_dir
    return None


def read_file(path: Path) -> str:
    try:
        return path.expanduser().read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        reason = exc.strerror if isinstance(exc, OSError) and exc.strerror else str(exc)
        raise CliError(f"Could not read {path}: {reason}") from None


def request_summary(collection: Collection, request: ApiRequest) -> dict[str, Any]:
    return {"id": request.id, "collection": collection.id, "name": request.name,
            "method": request.method.value, "url": request.url}


# ============================================================================ project

def cmd_project_init(cli: Cli) -> None:
    root = Path(cli.args.dir).expanduser().resolve()
    if not root.is_dir():
        raise CliError(f"Folder not found: {root}")
    if find_api_dir(root) is not None:
        raise CliError(f"{root} already has an {API_CLIENT_DIR_NAME}/ project.")
    service = ProjectService.create(root, cli.args.name or root.name, cli.args.base_url)
    remember_project(cli, service)
    cli.print(f"Created project “{service.project.name}” in {service.api_dir}")


def remember_project(cli: Cli, service: ProjectService) -> None:
    """Show the project in the desktop app's recent list too (best effort)."""
    from app.repositories import RecentProjectsRepository

    try:
        RecentProjectsRepository(cli.db).touch(service.key, service.project.name)
    except Exception:
        pass


def cmd_project_show(cli: Cli) -> None:
    service = cli.service
    project = service.project
    data = {
        "name": project.name,
        "folder": str(service.api_dir),
        "base_url": project.base_url,
        "default_environment": service.default_environment(),
        "environments": service.environment_names,
        "collections": len(service.collections),
        "requests": len(service.all_requests()),
    }
    if cli.args.json:
        cli.emit_json(data)
        return
    width = max(len(k) for k in data)
    for key, value in data.items():
        if isinstance(value, list):
            value = ", ".join(value) or "—"
        cli.print(f"{key.replace('_', ' ').ljust(width)}  {value if value not in (None, '') else '—'}")


def cmd_project_set(cli: Cli) -> None:
    service = cli.service
    if cli.args.name is None and cli.args.base_url is None:
        raise CliError("Nothing to change: pass --name and/or --base-url.")
    service.update_project(
        name=service.project.name if cli.args.name is None else cli.args.name,
        base_url=service.project.base_url if cli.args.base_url is None else cli.args.base_url,
    )
    remember_project(cli, service)
    cli.print(f"Updated project “{service.project.name}” (base_url: {service.project.base_url or '—'})")


# ============================================================================ collections

def cmd_collection_ls(cli: Cli) -> None:
    collections = cli.service.collections
    if cli.args.json:
        cli.emit_json([{"id": c.id, "name": c.name, "base_path": c.base_path, "requests": len(c.requests)}
                       for c in collections])
        return
    cli.table(["ID", "NAME", "BASE PATH", "REQUESTS"],
              [[c.id, c.name, c.base_path or "—", str(len(c.requests))] for c in collections],
              "No collections yet. Create one with: api-client collection add <name>")


def cmd_collection_add(cli: Cli) -> None:
    collection = cli.service.create_collection(cli.args.name, cli.args.base_path or "")
    cli.print(f"Created collection “{collection.name}” ({collection.id})")


def cmd_collection_rename(cli: Cli) -> None:
    collection = cli.collection(cli.args.collection)
    if cli.args.name is None and cli.args.base_path is None:
        raise CliError("Nothing to change: pass a new name and/or --base-path.")
    updated = cli.service.update_collection(
        collection.id,
        name=collection.name if cli.args.name is None else cli.args.name,
        base_path=collection.base_path if cli.args.base_path is None else cli.args.base_path,
    )
    cli.print(f"Updated collection “{updated.name}” ({updated.id})")


def cmd_collection_duplicate(cli: Cli) -> None:
    copy = cli.service.duplicate_collection(cli.collection(cli.args.collection).id)
    cli.print(f"Created collection “{copy.name}” ({copy.id})")


def cmd_collection_move(cli: Cli) -> None:
    collection = cli.collection(cli.args.collection)
    steps = cli.args.steps if cli.args.direction == "down" else -cli.args.steps
    cli.service.move_collection(collection.id, steps)
    order = [c.id for c in cli.service.collections]
    cli.print(f"Moved “{collection.name}” to position {order.index(collection.id) + 1} of {len(order)}")


def cmd_collection_rm(cli: Cli) -> None:
    collection = cli.collection(cli.args.collection)
    cli.confirm(f"Delete collection “{collection.name}” and its {len(collection.requests)} request(s)?")
    cli.service.delete_collection(collection.id)
    cli.print(f"Deleted collection “{collection.name}”")


# ============================================================================ requests

def cmd_request_ls(cli: Cli) -> None:
    if cli.args.collection:
        collection = cli.collection(cli.args.collection)
        items = [(collection, r) for r in collection.requests]
    else:
        items = cli.service.all_requests()
    if cli.args.json:
        cli.emit_json([request_summary(c, r) for c, r in items])
        return
    cli.table(["ID", "COLLECTION", "METHOD", "NAME", "URL"],
              [[r.id, c.id, r.method.value, r.name, r.url] for c, r in items],
              "No requests yet. Create one with: api-client request add <collection> <name>")


def cmd_request_show(cli: Cli) -> None:
    collection, request = cli.request(cli.args.request)
    cli.emit_json({"collection": collection.id, **request.to_dict()})


def cmd_request_add(cli: Cli) -> None:
    collection = cli.collection(cli.args.collection)
    method = parse_method(cli.args.method or "GET")
    request = cli.service.create_request(collection.id, cli.args.name, method, cli.args.url)
    apply_request_options(cli, request)
    cli.service.save_request(request.id)
    cli.print(f"Created request “{request.name}” ({request.id}) in {collection.id}")


def cmd_request_edit(cli: Cli) -> None:
    _, request = cli.request(cli.args.request)
    if cli.args.name is not None:
        request.name = cli.args.name.strip() or request.name
    if cli.args.method is not None:
        request.method = parse_method(cli.args.method)
    if cli.args.url is not None:
        request.url = cli.args.url.strip()
    apply_request_options(cli, request)
    cli.service.save_request(request.id)
    cli.print(f"Updated request “{request.name}” ({request.id})")


def cmd_request_rename(cli: Cli) -> None:
    _, request = cli.request(cli.args.request)
    cli.service.rename_request(request.id, cli.args.name)
    cli.print(f"Renamed request to “{request.name}”")


def cmd_request_duplicate(cli: Cli) -> None:
    _, request = cli.request(cli.args.request)
    copy = cli.service.duplicate_request(request.id)
    cli.print(f"Created request “{copy.name}” ({copy.id})")


def cmd_request_move(cli: Cli) -> None:
    _, request = cli.request(cli.args.request)
    target = cli.collection(cli.args.collection)
    index = None if cli.args.index is None else cli.args.index - 1
    cli.service.move_request(request.id, target.id, index)
    cli.print(f"Moved “{request.name}” to {target.id}")


def cmd_request_rm(cli: Cli) -> None:
    collection, request = cli.request(cli.args.request)
    cli.confirm(f"Delete request “{request.name}” from {collection.name}?")
    cli.service.delete_request(request.id)
    cli.print(f"Deleted request “{request.name}”")


def parse_method(value: str) -> HttpMethod:
    try:
        return HttpMethod(value.upper())
    except ValueError:
        raise CliError(f"Unknown method: {value}. Use one of: {', '.join(m.value for m in HttpMethod)}") from None


def split_pair(raw: str, separator: str, what: str) -> tuple[str, str]:
    key, found, value = raw.partition(separator)
    if not found or not key.strip():
        raise CliError(f"Invalid {what} “{raw}”: expected KEY{separator}VALUE")
    return key.strip(), value.strip() if separator == ":" else value


def upsert(rows: list, row: KeyValue, *, case_insensitive: bool = False) -> None:
    same = (lambda a, b: a.lower() == b.lower()) if case_insensitive else (lambda a, b: a == b)
    for index, existing in enumerate(rows):
        if same(existing.key, row.key):
            rows[index] = row
            return
    rows.append(row)


def apply_request_options(cli: Cli, request: ApiRequest) -> None:
    """Options shared by ``request add`` and ``request edit``."""
    args = cli.args
    for raw in args.header or []:
        upsert(request.headers, RequestHeader(*split_pair(raw, ":", "header")), case_insensitive=True)
    for key in args.remove_header or []:
        request.headers = [h for h in request.headers if h.key.lower() != key.lower()]
    for raw in args.query or []:
        upsert(request.params, RequestParameter(*split_pair(raw, "=", "query parameter")))
    for key in args.remove_query or []:
        request.params = [p for p in request.params if p.key != key]
    for raw in args.path_param or []:
        key, value = split_pair(raw, "=", "path variable")
        if key not in extract_path_param_names(request.url):
            cli.warn(f"{{{key}}} does not appear in the URL {request.url}")
        upsert(request.path_params, PathParameter(key, value))
    if args.description is not None:
        request.description = args.description

    if args.body is not None:
        content = cli.read_text(args.body)
        body_type = BodyType(args.body_type) if args.body_type else (
            request.body.type if request.body.type is not BodyType.NONE else BodyType.JSON)
        request.body = RequestBody(body_type, content, request.body.content_type)
    elif args.body_type:
        request.body = RequestBody(BodyType(args.body_type), request.body.content, request.body.content_type)
    if args.content_type is not None:
        request.body.content_type = args.content_type
    if request.body.type is BodyType.JSON and request.body.content.strip():
        try:
            json.loads(request.body.content)
        except ValueError as exc:
            cli.warn(f"the JSON body is not valid ({exc}); it was saved anyway")

    if args.bearer is not None:
        request.auth = Authentication(AuthType.BEARER, token=args.bearer)
    elif args.basic is not None:
        username, _, password = args.basic.partition(":")
        request.auth = Authentication(AuthType.BASIC, username=username, password=password)
    elif args.no_auth:
        request.auth = Authentication()


# ============================================================================ run / curl

def cmd_run(cli: Cli) -> int:
    from app.services.http_client_service import HttpClientService

    _, request = cli.request(cli.args.request)
    environment = cli.environment(cli.args.env, default=True)
    context = cli.service.variable_context(environment)
    settings = cli.settings()
    network = settings.network
    if cli.args.timeout is not None:
        network.timeout_seconds = cli.args.timeout
    if cli.args.insecure:
        network.verify_ssl = False

    http = HttpClientService(lambda: network)
    prepared = http.prepare(request, context)
    try:
        response = http.execute(prepared)
    except RequestError as error:
        if not cli.args.no_history:
            record_history(cli, settings, request, prepared, None, error.title)
        raise
    if not cli.args.no_history:
        record_history(cli, settings, request, prepared, response, "")

    status = f"{response.status_text}  ·  {format_duration(response.elapsed_ms)}  ·  {format_size(response.size_bytes)}"
    if response.truncated:
        status += "  ·  truncated"
    if cli.args.include:
        cli.print(f"{response.http_version} {response.status_text}")
        for key, value in response.headers:
            cli.print(f"{key}: {value}")
        cli.print()
    elif not cli.args.quiet:
        cli.info(f"{prepared.method} {prepared.masked_url}\n{status}")

    if cli.args.output:
        try:
            Path(cli.args.output).expanduser().write_bytes(response.body)
        except OSError as exc:
            raise CliError(f"Could not write {cli.args.output}: {exc.strerror or exc}") from None
        cli.info(f"Saved body to {cli.args.output}")
    elif response.is_text:
        text = response.text if cli.args.raw else response.pretty_body()
        if text:
            cli.out.write(text if text.endswith("\n") else text + "\n")
    else:
        cli.info(f"Binary body ({format_size(len(response.body))}); use --output FILE to save it.")
    return 1 if cli.args.fail and response.status_code >= 400 else 0


def record_history(cli: Cli, settings: AppSettings, request: ApiRequest, prepared, response, error: str) -> None:
    from app.repositories import HistoryRepository

    entry = HistoryEntry(
        timestamp=datetime.now().isoformat(timespec="seconds"),
        method=prepared.method,
        url=prepared.masked_url,
        status_code=response.status_code if response else None,
        elapsed_ms=response.elapsed_ms if response else None,
        size_bytes=response.size_bytes if response else None,
        error=error,
        project_path=cli.service.key,
        request_id=request.id,
        request_name=request.name,
    )
    try:
        HistoryRepository(cli.db).add(entry, keep_last=settings.history_limit)
    except Exception as exc:
        cli.warn(f"could not store the history entry: {exc}")


def cmd_curl(cli: Cli) -> None:
    from app.services.http_client_service import HttpClientService

    _, request = cli.request(cli.args.request)
    context = cli.service.variable_context(cli.environment(cli.args.env, default=True))
    prepared = HttpClientService.prepare(request, context)
    if prepared.contains_secrets and not cli.args.show_secrets:
        cli.info("Secrets are masked; pass --show-secrets to include them.")
    cli.print(build_curl(prepared, mask_secrets=not cli.args.show_secrets))


# ============================================================================ environments

def cmd_env_ls(cli: Cli) -> None:
    service = cli.service
    default = service.default_environment()
    if cli.args.json:
        cli.emit_json([{"name": n, "default": n == default,
                        "variables": len(service.project.environments[n].variables)
                        + len(service.secrets.for_environment(n))} for n in service.environment_names])
        return
    cli.table(["", "NAME", "VARIABLES"],
              [["*" if n == default else "", n, str(len(service.project.environments[n].variables)
                                                    + len(service.secrets.for_environment(n)))]
               for n in service.environment_names],
              "No environments yet. Create one with: api-client env add <name>")


def cmd_env_add(cli: Cli) -> None:
    name = cli.service.add_environment(cli.args.name, cli.args.base_url or "")
    cli.print(f"Created environment “{name}”")


def cmd_env_rename(cli: Cli) -> None:
    old = cli.environment(cli.args.environment, default=False)
    new = cli.service.rename_environment(old, cli.args.name)
    cli.print(f"Renamed environment “{old}” to “{new}”")


def cmd_env_duplicate(cli: Cli) -> None:
    source = cli.environment(cli.args.environment, default=False)
    name = cli.service.duplicate_environment(source, cli.args.name)
    cli.print(f"Created environment “{name}”")


def cmd_env_rm(cli: Cli) -> None:
    name = cli.environment(cli.args.environment, default=False)
    cli.confirm(f"Delete environment “{name}” and its variables (including secrets)?")
    cli.service.delete_environment(name)
    cli.print(f"Deleted environment “{name}”")


def cmd_env_use(cli: Cli) -> None:
    name = cli.environment(cli.args.environment, default=False)
    cli.service.set_active_environment(name)
    cli.print(f"Default environment is now “{name}”")


# ============================================================================ variables

def scope_variables(service: ProjectService, environment: str | None) -> list[tuple[str, str, bool]]:
    """(name, value, secret) for one scope, as the variables window shows it."""
    if environment is None:
        plain = dict(service.project.variables)
        if service.project.base_url:
            plain = {"base_url": service.project.base_url, **plain}
        secrets = service.secrets.globals
    else:
        plain = service.project.environments[environment].variables
        secrets = service.secrets.for_environment(environment)
    rows = [(k, v, False) for k, v in plain.items() if k not in secrets]
    return rows + [(k, v, True) for k, v in secrets.items()]


def cmd_var_ls(cli: Cli) -> None:
    service = cli.service
    if cli.args.env is not None:
        scopes: list[str | None] = [cli.environment(cli.args.env, default=False)]
    elif cli.args.globals:
        scopes = [None]
    else:
        scopes = [None, *service.environment_names]
    rows = []
    for scope in scopes:
        for name, value, secret in scope_variables(service, scope):
            shown = value if (not secret or cli.args.show_secrets) else SECRET_MASK
            rows.append({"scope": scope or "globals", "name": name, "value": shown, "secret": secret})
    if cli.args.json:
        cli.emit_json(rows)
        return
    cli.table(["SCOPE", "NAME", "VALUE", "SECRET"],
              [[r["scope"], r["name"], r["value"], "yes" if r["secret"] else ""] for r in rows],
              "No variables yet. Add one with: api-client var set <name> <value>")


def cmd_var_set(cli: Cli) -> None:
    name = cli.args.name
    if not is_valid_variable_name(name):
        raise CliError(f"Invalid variable name: {name}. Use letters, digits, _, . or - (not starting with a digit).")
    environment = cli.environment(cli.args.env, default=False)
    value = cli.args.value
    if value in (None, "-"):
        if value is None and cli.stdin.isatty():
            value = getpass.getpass(f"Value for {name}: ") if cli.args.secret else input(f"Value for {name}: ")
        else:
            value = cli.stdin.read().rstrip("\n")
    elif value.startswith("@"):
        value = cli.read_text(value).rstrip("\n")
    cli.service.set_variable(environment, name, value, secret=cli.args.secret)
    kind = "secret" if cli.args.secret else "variable"
    cli.print(f"Saved {kind} {{{{{name}}}}} in {environment or 'globals'}")


def cmd_var_rm(cli: Cli) -> None:
    environment = cli.environment(cli.args.env, default=False)
    if not cli.service.delete_variable(environment, cli.args.name):
        raise CliError(f"{{{{{cli.args.name}}}}} is not defined in {environment or 'globals'}.")
    cli.print(f"Deleted {{{{{cli.args.name}}}}} from {environment or 'globals'}")


# ============================================================================ import

def cmd_import_openapi(cli: Cli) -> None:
    text = load_openapi_text(cli, cli.args.source or DEFAULT_OPENAPI_SOURCE)
    result = parse_openapi(text)
    service = cli.service
    result.mark_existing(service.collections)
    endpoints = result.endpoints
    if cli.args.only:
        wanted = {name.casefold() for name in cli.args.only}
        endpoints = [e for e in endpoints if e.collection.casefold() in wanted]
        if not endpoints:
            raise CliError("No endpoint belongs to the collections given with --only. Available: "
                           + ", ".join(result.collections()))
    for note in result.notes:
        cli.warn(note)

    if cli.args.dry_run:
        cli.info(f"{result.title} {result.version}".strip())
        grouped: dict[str, list] = {}
        for endpoint in endpoints:
            grouped.setdefault(endpoint.collection, []).append(endpoint)
        for collection, items in grouped.items():
            cli.print(collection)
            for e in items:
                state = "exists" if e.exists else "new"
                cli.print(f"  {e.request.method.value.ljust(7)} {e.path}  ({state})")
        return

    summary = service.import_endpoints(endpoints)
    cli.print(f"Imported {summary.requests} request(s)"
              + (f", new collections: {', '.join(summary.new_collections)}" if summary.new_collections else "")
              + (f"; skipped {summary.skipped} already in the project" if summary.skipped else ""))


def load_openapi_text(cli: Cli, source: str) -> str:
    path = Path(source).expanduser()
    if "{{" not in source and "://" not in source:
        if not path.is_file():
            raise CliError(f"File not found: {source}")
        return read_file(path)
    from app.services.http_client_service import HttpClientService

    context = cli.service.variable_context(cli.environment(cli.args.env, default=True))
    request = ApiRequest(name="OpenAPI", url=source, headers=[RequestHeader("Accept", "application/json")])
    http = HttpClientService(lambda: cli.settings().network)
    response = http.execute(http.prepare(request, context))
    if response.status_code >= 400:
        raise CliError(f"The server answered {response.status_text}. Check that springdoc-openapi is enabled "
                       "and the URL is right.")
    return response.text


def cmd_import_curl(cli: Cli) -> None:
    collection = cli.collection(cli.args.collection)
    text = cli.read_text(cli.args.command) if cli.args.command else cli.stdin.read()
    context = cli.service.variable_context(cli.environment(cli.args.env, default=True))
    imported = parse_curl(text, base_url_for(context))
    for option in imported.ignored:
        cli.warn(f"{option} has no equivalent and was ignored")
    request = cli.service.create_request(collection.id, cli.args.name or imported.request.name,
                                         imported.request.method, imported.request.url)
    imported.apply_to(request)
    cli.service.save_request(request.id)
    cli.print(f"Created request “{request.name}” ({request.id}) in {collection.id}")


# ============================================================================ history

def cmd_history_ls(cli: Cli) -> None:
    from app.repositories import HistoryRepository

    entries = HistoryRepository(cli.db).list(cli.service.key, cli.args.limit)
    if cli.args.json:
        cli.emit_json([{"timestamp": e.timestamp, "method": e.method, "url": e.url, "status": e.status_code,
                        "elapsed_ms": e.elapsed_ms, "size_bytes": e.size_bytes, "error": e.error,
                        "request_id": e.request_id, "request_name": e.request_name} for e in entries])
        return
    cli.table(["TIME", "METHOD", "STATUS", "TIME (ms)", "URL"],
              [[e.timestamp.replace("T", " "), e.method, str(e.status_code) if e.succeeded else e.error,
                format_duration(e.elapsed_ms), e.url] for e in entries],
              "No requests sent yet.")


def cmd_history_clear(cli: Cli) -> None:
    from app.repositories import HistoryRepository

    cli.confirm(f"Clear the history of “{cli.service.project.name}”?")
    HistoryRepository(cli.db).clear(cli.service.key)
    cli.print("History cleared")


# ============================================================================ settings

_CHOICES = {"theme": ("dark", "light", "system"), "language": ("system", "en", "es")}


def settings_items(settings: AppSettings) -> dict[str, Any]:
    items = {f.name: getattr(settings, f.name) for f in fields(AppSettings) if f.name != "network"}
    items.update({f"network.{f.name}": getattr(settings.network, f.name) for f in fields(NetworkSettings)})
    return items


def cmd_settings_ls(cli: Cli) -> None:
    items = settings_items(cli.settings())
    if cli.args.json:
        cli.emit_json(items)
        return
    cli.table(["KEY", "VALUE"], [[k, json.dumps(v)] for k, v in items.items()], "")


def cmd_settings_set(cli: Cli) -> None:
    from app.repositories import SettingsRepository

    settings = cli.settings()
    key = cli.args.key
    items = settings_items(settings)
    if key not in items:
        raise CliError(f"Unknown setting: {key}. Available: {', '.join(items)}")
    value = parse_setting(key, cli.args.value, items[key])
    if key.startswith("network."):
        setattr(settings.network, key.removeprefix("network."), value)
    else:
        setattr(settings, key, value)
    SettingsRepository(cli.db).save(settings)
    cli.print(f"{key} = {json.dumps(value)}")


def parse_setting(key: str, raw: str, current: Any) -> Any:
    if isinstance(current, bool):
        lowered = raw.lower()
        if lowered in ("true", "yes", "on", "1"):
            return True
        if lowered in ("false", "no", "off", "0"):
            return False
        raise CliError(f"{key} expects true or false.")
    if isinstance(current, (int, float)):
        try:
            number = type(current)(raw)
        except ValueError:
            raise CliError(f"{key} expects a number.") from None
        if number <= 0:
            raise CliError(f"{key} must be greater than zero.")
        return number
    if key in _CHOICES and raw not in _CHOICES[key]:
        raise CliError(f"{key} must be one of: {', '.join(_CHOICES[key])}")
    return raw


# ============================================================================ parser

def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("-C", "--project", metavar="DIR",
                        help="backend folder (or its api-client/ folder); default: current folder or a parent")
    as_json = argparse.ArgumentParser(add_help=False)
    as_json.add_argument("--json", action="store_true", help="print machine readable JSON")
    yes = argparse.ArgumentParser(add_help=False)
    yes.add_argument("-y", "--yes", action="store_true", help="do not ask for confirmation")
    env = argparse.ArgumentParser(add_help=False)
    env.add_argument("-e", "--env", metavar="ENV", help="environment (default: the project's default environment)")

    parser = argparse.ArgumentParser(
        prog="api-client",
        description=f"{APP_NAME} command line. Without a command (or with a folder) the desktop app opens.",
        epilog="Run 'api-client <command> -h' for the options of each command.",
    )
    parser.add_argument("-V", "--version", action="version", version=f"{APP_NAME} {APP_VERSION}")
    commands = parser.add_subparsers(dest="command", metavar="<command>")

    def group(name: str, help_text: str, aliases: tuple[str, ...] = ()) -> argparse._SubParsersAction:
        sub = commands.add_parser(name, help=help_text, aliases=list(aliases), description=help_text)
        sub.set_defaults(handler=lambda cli, p=sub: p.print_help(cli.out))
        return sub.add_subparsers(dest="action", metavar="<action>")

    def leaf(actions, name: str, handler, help_text: str, parents=(), aliases: tuple[str, ...] = ()):
        sub = actions.add_parser(name, help=help_text, description=help_text, aliases=list(aliases),
                                 parents=[common, *parents])
        sub.set_defaults(handler=handler)
        return sub

    # project
    actions = group("project", "create and configure the project")
    p = leaf(actions, "init", cmd_project_init, "create api-client/ inside a backend folder")
    p.add_argument("dir", nargs="?", default=".", help="backend folder (default: current folder)")
    p.add_argument("--name", help="project name (default: folder name)")
    p.add_argument("--base-url", default="http://localhost:8080", help="default {{base_url}}")
    leaf(actions, "show", cmd_project_show, "show the project", [as_json], aliases=("info",))
    p = leaf(actions, "set", cmd_project_set, "rename the project or change its base URL")
    p.add_argument("--name")
    p.add_argument("--base-url")

    # collection
    actions = group("collection", "manage collections", aliases=("col",))
    leaf(actions, "ls", cmd_collection_ls, "list collections", [as_json], aliases=("list",))
    p = leaf(actions, "add", cmd_collection_add, "create a collection", aliases=("create",))
    p.add_argument("name")
    p.add_argument("--base-path", help="e.g. /api/productos (pre-fills new request URLs)")
    p = leaf(actions, "rename", cmd_collection_rename, "rename a collection or change its base path",
             aliases=("edit",))
    p.add_argument("collection", help="id or name")
    p.add_argument("name", nargs="?", help="new name")
    p.add_argument("--base-path")
    p = leaf(actions, "duplicate", cmd_collection_duplicate, "copy a collection with its requests", aliases=("cp",))
    p.add_argument("collection", help="id or name")
    p = leaf(actions, "move", cmd_collection_move, "change the position of a collection in the sidebar",
             aliases=("mv",))
    p.add_argument("collection", help="id or name")
    p.add_argument("direction", choices=("up", "down"))
    p.add_argument("steps", nargs="?", type=int, default=1)
    p = leaf(actions, "rm", cmd_collection_rm, "delete a collection and its requests", [yes], aliases=("delete",))
    p.add_argument("collection", help="id or name")

    # request
    def request_options(sub: argparse.ArgumentParser) -> None:
        sub.add_argument("-X", "--method", help="GET, POST, PUT, PATCH, DELETE, HEAD or OPTIONS")
        sub.add_argument("--url", help="e.g. '{{base_url}}/api/productos/{id}'")
        sub.add_argument("-H", "--header", action="append", metavar="'KEY: VALUE'", help="add or replace a header")
        sub.add_argument("--remove-header", action="append", metavar="KEY")
        sub.add_argument("-q", "--query", action="append", metavar="KEY=VALUE", help="add or replace a query param")
        sub.add_argument("--remove-query", action="append", metavar="KEY")
        sub.add_argument("-P", "--path-param", action="append", metavar="KEY=VALUE",
                         help="value for a {KEY} path variable")
        sub.add_argument("-d", "--body", metavar="TEXT", help="body text; '@file' reads a file, '-' reads stdin")
        sub.add_argument("--body-type", choices=[t.value for t in BodyType])
        sub.add_argument("--content-type", help="override the Content-Type of the body")
        auth = sub.add_mutually_exclusive_group()
        auth.add_argument("--bearer", metavar="TOKEN", help="Bearer auth, e.g. '{{token}}'")
        auth.add_argument("--basic", metavar="USER:PASSWORD", help="Basic auth")
        auth.add_argument("--no-auth", action="store_true", help="remove authentication")
        sub.add_argument("--description")

    actions = group("request", "manage requests", aliases=("req",))
    p = leaf(actions, "ls", cmd_request_ls, "list requests", [as_json], aliases=("list",))
    p.add_argument("collection", nargs="?", help="only this collection (id or name)")
    p = leaf(actions, "show", cmd_request_show, "print a request as JSON")
    p.add_argument("request", help="id, collection/name or a unique name")
    p = leaf(actions, "add", cmd_request_add, "create a request", aliases=("create",))
    p.add_argument("collection", help="id or name")
    p.add_argument("name")
    request_options(p)
    p = leaf(actions, "edit", cmd_request_edit, "change a request", aliases=("set",))
    p.add_argument("request", help="id, collection/name or a unique name")
    p.add_argument("--name")
    request_options(p)
    p = leaf(actions, "rename", cmd_request_rename, "rename a request")
    p.add_argument("request", help="id, collection/name or a unique name")
    p.add_argument("name")
    p = leaf(actions, "duplicate", cmd_request_duplicate, "copy a request", aliases=("cp",))
    p.add_argument("request", help="id, collection/name or a unique name")
    p = leaf(actions, "move", cmd_request_move, "move a request to another collection or position",
             aliases=("mv",))
    p.add_argument("request", help="id, collection/name or a unique name")
    p.add_argument("collection", help="target collection (id or name)")
    p.add_argument("--index", type=int, help="1-based position in the target (default: last)")
    p = leaf(actions, "rm", cmd_request_rm, "delete a request", [yes], aliases=("delete",))
    p.add_argument("request", help="id, collection/name or a unique name")

    # run / curl
    p = commands.add_parser("run", aliases=["send"], parents=[common, env], help="send a request",
                            description="Send a request. The body goes to stdout, the status line to stderr.")
    p.set_defaults(handler=cmd_run)
    p.add_argument("request", help="id, collection/name or a unique name")
    p.add_argument("-i", "--include", action="store_true", help="print the status line and headers to stdout")
    p.add_argument("--raw", action="store_true", help="do not pretty-print JSON")
    p.add_argument("-o", "--output", metavar="FILE", help="save the body to a file")
    p.add_argument("-s", "--quiet", action="store_true", help="do not print the status line")
    p.add_argument("-f", "--fail", action="store_true", help="exit with 1 when the status is 4xx or 5xx")
    p.add_argument("--timeout", type=float, metavar="SECONDS")
    p.add_argument("-k", "--insecure", action="store_true", help="do not verify SSL certificates")
    p.add_argument("--no-history", action="store_true", help="do not add the request to the history")
    p = commands.add_parser("curl", parents=[common, env], help="print a request as a cURL command",
                            description="Print a request as a cURL command (secrets masked by default).")
    p.set_defaults(handler=cmd_curl)
    p.add_argument("request", help="id, collection/name or a unique name")
    p.add_argument("--show-secrets", action="store_true", help="include secret values")

    # env
    actions = group("env", "manage environments")
    leaf(actions, "ls", cmd_env_ls, "list environments (* marks the default)", [as_json], aliases=("list",))
    p = leaf(actions, "add", cmd_env_add, "create an environment", aliases=("create",))
    p.add_argument("name")
    p.add_argument("--base-url")
    p = leaf(actions, "rename", cmd_env_rename, "rename an environment")
    p.add_argument("environment")
    p.add_argument("name")
    p = leaf(actions, "duplicate", cmd_env_duplicate, "copy an environment with its variables", aliases=("cp",))
    p.add_argument("environment")
    p.add_argument("name", nargs="?")
    p = leaf(actions, "rm", cmd_env_rm, "delete an environment and its secrets", [yes], aliases=("delete",))
    p.add_argument("environment")
    p = leaf(actions, "use", cmd_env_use, "choose the default environment")
    p.add_argument("environment")

    # var
    scope = argparse.ArgumentParser(add_help=False)
    scope.add_argument("-e", "--env", metavar="ENV", help="environment (default: globals)")
    actions = group("var", "manage variables and secrets")
    p = leaf(actions, "ls", cmd_var_ls, "list variables (secrets masked)", [as_json], aliases=("list",))
    only = p.add_mutually_exclusive_group()
    only.add_argument("-e", "--env", metavar="ENV", help="only this environment")
    only.add_argument("-g", "--globals", action="store_true", help="only global variables")
    p.add_argument("--show-secrets", action="store_true")
    p = leaf(actions, "set", cmd_var_set, "create or change a variable", [scope])
    p.add_argument("name")
    p.add_argument("value", nargs="?",
                   help="value; '@file' reads a file, '-' or omitted reads stdin (or prompts)")
    p.add_argument("-s", "--secret", action="store_true", help="store it in the git-ignored .secrets.json")
    p = leaf(actions, "rm", cmd_var_rm, "delete a variable", [scope], aliases=("delete",))
    p.add_argument("name")

    # import
    actions = group("import", "import requests")
    p = leaf(actions, "openapi", cmd_import_openapi, "import an OpenAPI 3 spec (one collection per controller)",
             [env])
    p.add_argument("source", nargs="?",
                   help=f"URL or JSON file (default: {DEFAULT_OPENAPI_SOURCE})")
    p.add_argument("--only", action="append", metavar="COLLECTION", help="only import this collection")
    p.add_argument("-n", "--dry-run", action="store_true", help="list what would be imported")
    p = leaf(actions, "curl", cmd_import_curl, "create a request from a cURL command", [env])
    p.add_argument("collection", help="id or name")
    p.add_argument("command", nargs="?", help="the cURL command; '@file' reads a file, omitted reads stdin")
    p.add_argument("--name", help="request name (default: derived from the URL)")

    # history
    actions = group("history", "requests sent from this project")
    p = leaf(actions, "ls", cmd_history_ls, "list sent requests (newest first)", [as_json], aliases=("list",))
    p.add_argument("-n", "--limit", type=int, default=50)
    leaf(actions, "clear", cmd_history_clear, "delete the history of this project", [yes])

    # settings
    actions = group("settings", "application settings (shared with the desktop app)")
    leaf(actions, "ls", cmd_settings_ls, "list settings", [as_json], aliases=("list",))
    p = leaf(actions, "set", cmd_settings_set, "change a setting, e.g. network.timeout_seconds 60")
    p.add_argument("key")
    p.add_argument("value")

    help_parser = commands.add_parser("help", help="show this help")
    help_parser.set_defaults(handler=lambda cli: parser.print_help(cli.out))
    return parser


def main(argv: list[str] | None = None, *, out: TextIO | None = None, err: TextIO | None = None,
         stdin: TextIO | None = None) -> int:
    out = out or sys.stdout
    err = err or sys.stderr
    parser = build_parser()
    try:
        args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    except SystemExit as exc:  # --help, --version and usage errors
        return exc.code if isinstance(exc.code, int) else 2
    cli = Cli(args, out, err, stdin or sys.stdin)
    handler = getattr(args, "handler", None)
    try:
        if handler is None:
            parser.print_help(out)
            return 0
        return handler(cli) or 0
    except CliError as exc:
        print(f"error: {exc}", file=err)
    except RequestError as exc:
        print(f"error: {exc.title}: {exc.message}", file=err)
        if exc.hint:
            print(f"hint: {exc.hint}", file=err)
    except (ProjectLoadError, JsonFileError, OpenApiError, CurlParseError, VariableError, KeyError) as exc:
        message = exc.args[0] if isinstance(exc, KeyError) and exc.args else exc
        print(f"error: {message}", file=err)
    except OSError as exc:
        print(f"error: {exc.strerror or exc}", file=err)
    except KeyboardInterrupt:
        print("Cancelled.", file=err)
        return 130
    finally:
        cli.close()
    return 1
