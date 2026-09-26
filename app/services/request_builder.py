"""Turns a stored ``ApiRequest`` into a concrete, ready-to-send HTTP request.

Order of operations:
1. resolve ``{{variables}}`` in the URL
2. substitute ``{path}`` parameters (values may contain variables, and are URL-encoded)
3. append enabled query parameters
4. resolve headers, add authentication and the body Content-Type
5. resolve and validate the body

Every problem is reported as a ``RequestError`` before anything is sent.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from urllib.parse import quote, urlencode, urlsplit, urlunsplit

from app.i18n import tr
from app.models.api_request import ApiRequest, BodyType, KeyValue
from app.models.auth import AuthType
from app.network.errors import ErrorKind, RequestError
from app.services.auth_strategies import AuthConfigurationError, strategy_for
from app.services.json_service import translate_json_error
from app.services.variable_service import (
    CircularVariableError,
    MissingVariablesError,
    VariableContext,
    VariableResolver,
)
from app.utils.logging_setup import MASK

PATH_PARAM_PATTERN = re.compile(r"(?<!\{)\{([A-Za-z_][A-Za-z0-9_\-]*)\}(?!\})")
_QUERY_SAFE = ",:/@$!*'()"


@dataclass
class PreparedRequest:
    method: str
    url: str
    headers: list[tuple[str, str]]
    body: bytes | None = None
    secret_values: frozenset[str] = field(default_factory=frozenset)

    def header(self, name: str) -> str | None:
        lower = name.lower()
        return next((v for k, v in self.headers if k.lower() == lower), None)

    @property
    def body_text(self) -> str:
        return self.body.decode("utf-8", errors="replace") if self.body else ""

    def mask(self, text: str) -> str:
        for value in sorted(self.secret_values, key=len, reverse=True):
            if len(value) >= 3:
                text = text.replace(value, MASK)
        return text

    @property
    def masked_url(self) -> str:
        return self.mask(self.url)

    def masked_headers(self) -> list[tuple[str, str]]:
        masked = []
        for key, value in self.headers:
            if key.lower() in ("authorization", "proxy-authorization"):
                scheme = value.split(" ", 1)[0] if " " in value else ""
                value = f"{scheme} {MASK}".strip()
            masked.append((key, self.mask(value)))
        return masked

    @property
    def contains_secrets(self) -> bool:
        if any(k.lower() in ("authorization", "proxy-authorization", "cookie") for k, _ in self.headers):
            return True
        haystack = self.url + "\n" + "\n".join(v for _, v in self.headers) + "\n" + self.body_text
        return any(len(v) >= 3 and v in haystack for v in self.secret_values)


def extract_path_param_names(url: str) -> list[str]:
    """``{{base_url}}/api/productos/{id}`` -> ``["id"]`` (only the path part is inspected)."""
    path = url.split("?", 1)[0].split("#", 1)[0]
    return list(dict.fromkeys(PATH_PARAM_PATTERN.findall(path)))


def ensure_scheme(url: str) -> str:
    stripped = url.strip()
    if stripped and "://" not in stripped.split("?", 1)[0]:
        return "http://" + stripped
    return stripped


def _enabled(rows: list[KeyValue]) -> list[KeyValue]:
    return [row for row in rows if row.enabled and row.key.strip()]


class RequestBuilder:
    def __init__(self, context: VariableContext) -> None:
        self.context = context
        self.resolver = VariableResolver(context)

    def build(self, request: ApiRequest) -> PreparedRequest:
        self._check_variables(request)
        try:
            return self._build(request)
        except MissingVariablesError as exc:  # pragma: no cover - guarded by _check_variables
            raise self._missing_error(exc, request.url) from None
        except CircularVariableError as exc:
            raise RequestError(ErrorKind.MISSING_VARIABLE, tr("Circular variable"), str(exc),
                               tr("Make sure variables do not reference each other in a loop."), request.url) from None

    def build_url(self, request: ApiRequest) -> str:
        """Final URL only; raises ``RequestError`` if it cannot be built."""
        texts = [request.url, *(p.value for p in _enabled(request.params)), *(p.key for p in _enabled(request.params))]
        texts += [p.value for p in request.path_params if p.enabled]
        missing = self.resolver.missing_in(texts)
        if missing:
            raise self._missing_error(MissingVariablesError(missing, self.context.environment), request.url)
        try:
            return self._build_url(request)
        except CircularVariableError as exc:
            raise RequestError(ErrorKind.MISSING_VARIABLE, tr("Circular variable"), str(exc), "", request.url) from None

    # -- internals -----------------------------------------------------------------

    def _check_variables(self, request: ApiRequest) -> None:
        texts = [request.url]
        texts += [f"{p.key}{p.value}" for p in _enabled(request.params)]
        texts += [p.value for p in request.path_params if p.enabled]
        texts += [f"{h.key}{h.value}" for h in _enabled(request.headers)]
        if request.auth.type is AuthType.BEARER:
            texts.append(request.auth.token)
        elif request.auth.type is AuthType.BASIC:
            texts += [request.auth.username, request.auth.password]
        if request.body.type is not BodyType.NONE:
            texts.append(request.body.content)
        missing = self.resolver.missing_in(texts)
        if missing:
            raise self._missing_error(MissingVariablesError(missing, self.context.environment), request.url)

    def _missing_error(self, exc: MissingVariablesError, url: str) -> RequestError:
        if exc.environment:
            hint = tr("Define it in the \"{env}\" environment (Environments) or in api-client/.secrets.json.",
                      env=exc.environment)
        else:
            hint = tr("Define it in the current environment (Environments) or in api-client/.secrets.json.")
        return RequestError(ErrorKind.MISSING_VARIABLE, tr("Missing variable"), str(exc), hint, url)

    def _build(self, request: ApiRequest) -> PreparedRequest:
        url = self._build_url(request)
        resolve = self.resolver.resolve

        headers: list[tuple[str, str]] = [
            (resolve(h.key).strip(), resolve(h.value)) for h in _enabled(request.headers)
        ]
        strategy = strategy_for(request.auth.type)
        try:
            auth_headers = strategy.headers(request.auth, resolve)
        except AuthConfigurationError as exc:
            raise RequestError(ErrorKind.INVALID_REQUEST, tr("Authentication incomplete"), str(exc), "", url) from None
        auth_names = {k.lower() for k, _ in auth_headers}
        headers = [h for h in headers if h[0].lower() not in auth_names] + auth_headers

        body = self._build_body(request, url)
        content_type = request.body.effective_content_type
        if body is not None and content_type and not any(k.lower() == "content-type" for k, _ in headers):
            headers.append(("Content-Type", content_type))

        secrets = set(self.context.secret_values()) | strategy.secret_values(request.auth, resolve)
        return PreparedRequest(request.method.value, url, headers, body, frozenset(secrets))

    def _build_url(self, request: ApiRequest) -> str:
        resolve = self.resolver.resolve
        raw_url = resolve(request.url).strip()
        if not raw_url:
            raise RequestError(ErrorKind.INVALID_URL, tr("URL is empty"), tr("Enter the URL of the endpoint to call."),
                               tr("Example: {{base_url}}/api/productos"))
        url = ensure_scheme(raw_url)
        try:
            parts = urlsplit(url)
        except ValueError as exc:
            raise RequestError(ErrorKind.INVALID_URL, tr("Invalid URL"), f"{url}\n{exc}", "", url) from None
        if parts.scheme.lower() not in ("http", "https"):
            raise RequestError(ErrorKind.INVALID_URL, tr("Unsupported URL scheme"),
                               tr('"{scheme}" is not supported. Use http:// or https://.', scheme=parts.scheme), "", url)
        if not parts.netloc:
            raise RequestError(ErrorKind.INVALID_URL, tr("Invalid URL"), tr("The URL has no host:\n{url}", url=url),
                               tr("Example: http://localhost:8080/api/productos"), url)

        path = self._substitute_path_params(parts.path, request, url)
        query_pairs = [(resolve(p.key), resolve(p.value)) for p in _enabled(request.params)]
        extra_query = urlencode(query_pairs, quote_via=quote, safe=_QUERY_SAFE)
        query = "&".join(q for q in (parts.query, extra_query) if q)
        return urlunsplit((parts.scheme, parts.netloc, path, query, parts.fragment))

    def _substitute_path_params(self, path: str, request: ApiRequest, url: str) -> str:
        values = {p.key: p for p in request.path_params if p.key}

        def replace(match: re.Match[str]) -> str:
            name = match.group(1)
            param = values.get(name)
            if param is None or not param.enabled or not param.value.strip():
                raise RequestError(
                    ErrorKind.INVALID_REQUEST, tr("Missing path parameter"),
                    tr("The path parameter {param} has no value.", param="{" + name + "}"),
                    tr("Fill it in the Params tab under Path Variables."), url,
                )
            return quote(self.resolver.resolve(param.value).strip(), safe="")

        return PATH_PARAM_PATTERN.sub(replace, path)

    def _build_body(self, request: ApiRequest, url: str) -> bytes | None:
        body = request.body
        if body.type is BodyType.NONE or (not body.content.strip() and body.type is BodyType.JSON):
            return None
        content = self.resolver.resolve(body.content)
        if body.type is BodyType.JSON:
            try:
                json.loads(content)
            except json.JSONDecodeError as exc:
                raise RequestError(
                    ErrorKind.INVALID_JSON, tr("Invalid JSON body"),
                    tr("Line {line}, column {column}: {message}", line=exc.lineno, column=exc.colno,
                       message=translate_json_error(exc.msg)),
                    tr("Fix the body before sending (Ctrl+Shift+F formats valid JSON)."), url, line=exc.lineno,
                ) from None
        return content.encode("utf-8")
