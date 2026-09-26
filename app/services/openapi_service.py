"""OpenAPI 3 -> collections and requests.

``parse_openapi`` reads a JSON spec (what springdoc serves at ``/v3/api-docs``) and turns
every operation into a request grouped by tag, one tag per Spring controller.
Nothing here touches the disk: ``ProjectService.import_endpoints`` stores the result.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

from app.i18n import tr
from app.models.api_request import (
    ApiRequest,
    BodyType,
    HttpMethod,
    PathParameter,
    RequestBody,
    RequestHeader,
    RequestParameter,
)
from app.models.auth import Authentication, AuthType
from app.models.collection import Collection
from app.services.request_builder import PATH_PARAM_PATTERN

DEFAULT_SPEC_URL = "{{base_url}}/v3/api-docs"
DEFAULT_COLLECTION = "Default"

_METHODS = ("get", "post", "put", "patch", "delete", "head", "options")
# Headers the request editor already derives from the body type and auth tab.
_IMPLIED_HEADERS = {"accept", "content-type", "authorization"}
_MAX_DEPTH = 8


class OpenApiError(ValueError):
    """The text is not a usable OpenAPI 3 spec; the message is user facing."""


@dataclass
class ImportedEndpoint:
    collection: str
    request: ApiRequest
    #: Full path as sent, e.g. ``/api/productos/{id}`` (server prefix included).
    path: str
    exists: bool = False

    @property
    def key(self) -> tuple[str, str]:
        return self.request.method.value, normalize_path(self.path)


@dataclass
class OpenApiImport:
    title: str
    version: str
    endpoints: list[ImportedEndpoint] = field(default_factory=list)
    #: Things that were understood but could not be imported (e.g. form bodies).
    notes: list[str] = field(default_factory=list)

    def collections(self) -> dict[str, list[ImportedEndpoint]]:
        grouped: dict[str, list[ImportedEndpoint]] = {}
        for endpoint in self.endpoints:
            grouped.setdefault(endpoint.collection, []).append(endpoint)
        return grouped

    def mark_existing(self, collections: list[Collection]) -> None:
        """Flag endpoints whose method and path already exist anywhere in the project."""
        taken = {(r.method.value, normalize_path(r.url)) for c in collections for r in c.requests}
        for endpoint in self.endpoints:
            endpoint.exists = endpoint.key in taken


# -- helpers --------------------------------------------------------------------------

def normalize_path(url: str) -> str:
    """``{{base_url}}/api/productos/{id}?x=1`` -> ``/api/productos/{}``, used to match requests."""
    text = url.strip()
    if text.startswith("{{base_url}}"):
        text = text[len("{{base_url}}"):]
    elif "://" in text.split("?", 1)[0]:
        text = urlsplit(text).path
    path = text.split("?", 1)[0].split("#", 1)[0]
    path = PATH_PARAM_PATTERN.sub("{}", path)
    path = "/" + path.strip("/")
    return path


def common_base_path(paths: list[str]) -> str:
    """Longest shared prefix without placeholders, e.g. ``/api/productos`` for a CRUD controller."""
    split = [[s for s in p.strip("/").split("/") if s] for p in paths]
    if not split:
        return ""
    if len(split) == 1:
        split[0] = split[0][:-1]  # one endpoint: its parent is the "controller" path
    prefix: list[str] = []
    for segments in zip(*split, strict=False):
        first = segments[0]
        if any(s != first for s in segments) or "{" in first:
            break
        prefix.append(first)
    return "/" + "/".join(prefix) if prefix else ""


def humanize(identifier: str) -> str:
    """``crearProducto`` / ``crear_producto_1`` / ``producto-controller`` -> ``Crear producto`` / ``Producto``."""
    text = re.sub(r"_\d+$", "", identifier.strip())
    text = re.sub(r"[-_ ]?controller$", "", text, flags=re.IGNORECASE) or text
    text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", text)
    text = re.sub(r"[-_\s]+", " ", text).strip()
    return text[:1].upper() + text[1:].lower() if text else ""


# -- parsing --------------------------------------------------------------------------

def parse_openapi(text: str) -> OpenApiImport:
    try:
        spec = json.loads(text)
    except ValueError:
        if re.match(r"\s*(openapi|swagger)\s*:", text or ""):
            raise OpenApiError(tr("YAML specs are not supported. Use the JSON version "
                                  "(springdoc serves it at /v3/api-docs).")) from None
        raise OpenApiError(tr("The content is not valid JSON.")) from None
    if not isinstance(spec, dict):
        raise OpenApiError(tr("The content is not an OpenAPI document."))
    if "swagger" in spec:
        raise OpenApiError(tr("Swagger 2.0 specs are not supported yet. springdoc (OpenAPI 3) serves "
                              "/v3/api-docs."))
    if not str(spec.get("openapi", "")).startswith("3."):
        raise OpenApiError(tr("The content is not an OpenAPI 3 document (missing “openapi: 3.x”)."))
    return _Parser(spec).parse()


class _Parser:
    def __init__(self, spec: dict[str, Any]) -> None:
        self.spec = spec
        self.notes: list[str] = []
        info = spec.get("info") if isinstance(spec.get("info"), dict) else {}
        self.title = str(info.get("title") or "")
        self.version = str(info.get("version") or "")
        self.prefix = self._server_prefix()
        components = spec.get("components") if isinstance(spec.get("components"), dict) else {}
        self.security_schemes = components.get("securitySchemes") or {}

    def parse(self) -> OpenApiImport:
        result = OpenApiImport(self.title, self.version, notes=self.notes)
        paths = self.spec.get("paths")
        if not isinstance(paths, dict) or not paths:
            raise OpenApiError(tr("The spec does not define any paths."))
        for path, item in paths.items():
            if not isinstance(item, dict):
                continue
            item = self.resolve(item)
            shared = item.get("parameters") or []
            for method in _METHODS:
                operation = item.get(method)
                if isinstance(operation, dict):
                    result.endpoints.append(self._endpoint(str(path), method, operation, shared))
        if not result.endpoints:
            raise OpenApiError(tr("The spec does not define any operations."))
        return result

    def _server_prefix(self) -> str:
        servers = self.spec.get("servers")
        if not isinstance(servers, list) or not servers or not isinstance(servers[0], dict):
            return ""
        url = str(servers[0].get("url") or "")
        path = urlsplit(url).path if "://" in url else url
        if "{" in path:
            return ""
        return "/" + path.strip("/") if path.strip("/") else ""

    # -- references -------------------------------------------------------------

    def resolve(self, node: Any, seen: frozenset[str] = frozenset()) -> Any:
        """Follow local ``$ref`` pointers (``#/components/...``); unknown ones resolve to ``{}``."""
        while isinstance(node, dict) and isinstance(node.get("$ref"), str):
            ref = node["$ref"]
            if ref in seen or not ref.startswith("#/"):
                return {}
            seen = seen | {ref}
            target: Any = self.spec
            for part in ref[2:].split("/"):
                part = part.replace("~1", "/").replace("~0", "~")
                target = target.get(part) if isinstance(target, dict) else None
            node = target if target is not None else {}
        return node

    # -- operations -------------------------------------------------------------

    def _endpoint(self, path: str, method: str, operation: dict[str, Any], shared: list[Any]) -> ImportedEndpoint:
        full_path = self.prefix + ("/" + path.lstrip("/") if path else "")
        tags = operation.get("tags")
        collection = humanize(str(tags[0])) if isinstance(tags, list) and tags else ""
        name = str(operation.get("summary") or "").strip() or humanize(str(operation.get("operationId") or ""))
        request = ApiRequest(
            name=name or f"{method.upper()} {path}",
            method=HttpMethod(method.upper()),
            url="{{base_url}}" + full_path,
            description=str(operation.get("description") or "").strip(),
        )
        self._apply_parameters(request, shared, operation.get("parameters") or [])
        self._apply_body(request, operation, f"{method.upper()} {path}")
        request.auth = self._auth(operation, request)
        return ImportedEndpoint(collection or DEFAULT_COLLECTION, request, full_path)

    def _apply_parameters(self, request: ApiRequest, shared: list[Any], own: list[Any]) -> None:
        merged: dict[tuple[str, str], dict[str, Any]] = {}
        for raw in [*shared, *own]:  # operation level parameters override path level ones
            param = self.resolve(raw)
            if isinstance(param, dict) and param.get("name") and param.get("in"):
                merged[(str(param["in"]), str(param["name"]))] = param
        for (location, name), param in merged.items():
            value = self._parameter_value(param)
            if location == "path":
                request.path_params.append(PathParameter(name, value))
            elif location == "query":
                request.params.append(RequestParameter(name, value, enabled=bool(param.get("required"))))
            elif location == "header" and name.lower() not in _IMPLIED_HEADERS:
                request.headers.append(RequestHeader(name, value, enabled=bool(param.get("required"))))

    def _parameter_value(self, param: dict[str, Any]) -> str:
        schema = self.resolve(param.get("schema") or {})
        for candidate in (param.get("example"), _first_example(param.get("examples"), self),
                          schema.get("example") if isinstance(schema, dict) else None,
                          schema.get("default") if isinstance(schema, dict) else None):
            if candidate is not None:
                return _scalar_text(candidate)
        return ""

    def _apply_body(self, request: ApiRequest, operation: dict[str, Any], label: str) -> None:
        body = self.resolve(operation.get("requestBody"))
        content = body.get("content") if isinstance(body, dict) else None
        if not isinstance(content, dict) or not content:
            return
        json_type = next((t for t in content if t == "application/json" or t.endswith("+json")), None)
        if json_type is not None:
            media = self.resolve(content[json_type]) or {}
            sample = _media_example(media, self)
            if sample is None:
                sample = self.sample(media.get("schema") or {})
            request.body = RequestBody(BodyType.JSON, json.dumps(sample, indent=2, ensure_ascii=False),
                                       "" if json_type == "application/json" else json_type)
        elif "text/plain" in content:
            request.body = RequestBody(BodyType.TEXT, "")
        else:
            self.notes.append(tr("{endpoint}: {type} bodies are not supported, the body was left empty.",
                                 endpoint=label, type=next(iter(content))))

    def _auth(self, operation: dict[str, Any], request: ApiRequest) -> Authentication:
        requirements = operation.get("security", self.spec.get("security"))
        if not isinstance(requirements, list):
            return Authentication()
        for requirement in requirements:
            if not isinstance(requirement, dict):
                continue
            for scheme_name in requirement:
                scheme = self.resolve(self.security_schemes.get(scheme_name) or {})
                kind = str(scheme.get("type", "")).lower()
                http_scheme = str(scheme.get("scheme", "")).lower()
                if (kind == "http" and http_scheme == "bearer") or kind in ("oauth2", "openidconnect"):
                    return Authentication(AuthType.BEARER, token="{{token}}")
                if kind == "http" and http_scheme == "basic":
                    return Authentication(AuthType.BASIC, username="{{username}}", password="{{password}}")
                if kind == "apikey" and str(scheme.get("in")) == "header" and scheme.get("name"):
                    request.headers.append(RequestHeader(str(scheme["name"]), "{{api_key}}"))
                    return Authentication()
        return Authentication()

    # -- sample payloads ----------------------------------------------------------

    def sample(self, schema: Any, depth: int = 0, seen: frozenset[str] = frozenset()) -> Any:
        """A readable example value for ``schema``; recursive ``$ref`` chains stop at ``{}``."""
        if isinstance(schema, dict) and isinstance(schema.get("$ref"), str):
            ref = schema["$ref"]
            if ref in seen:
                return {}
            seen = seen | {ref}
            schema = self.resolve(schema)
        if not isinstance(schema, dict) or depth > _MAX_DEPTH:
            return None
        for key in ("example", "default"):
            if key in schema:
                return schema[key]
        if isinstance(schema.get("examples"), list) and schema["examples"]:
            return schema["examples"][0]
        if isinstance(schema.get("enum"), list) and schema["enum"]:
            return schema["enum"][0]
        if isinstance(schema.get("allOf"), list):
            merged: dict[str, Any] = {}
            for part in schema["allOf"]:
                value = self.sample(part, depth + 1, seen)
                if isinstance(value, dict):
                    merged.update(value)
            return merged
        for key in ("oneOf", "anyOf"):
            if isinstance(schema.get(key), list) and schema[key]:
                return self.sample(schema[key][0], depth + 1, seen)

        kind = schema.get("type")
        if isinstance(kind, list):  # OpenAPI 3.1: ["string", "null"]
            kind = next((k for k in kind if k != "null"), None)
        if kind == "object" or (kind is None and isinstance(schema.get("properties"), dict)):
            properties = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
            result = {}
            for name, prop in properties.items():
                resolved = self.resolve(prop, seen)
                if isinstance(resolved, dict) and resolved.get("readOnly"):
                    continue  # e.g. generated ids: the server sets them
                result[name] = self.sample(prop, depth + 1, seen)
            return result
        if kind == "array":
            item = self.sample(schema.get("items") or {}, depth + 1, seen)
            return [] if item is None else [item]
        if kind == "string":
            return _STRING_FORMATS.get(str(schema.get("format", "")), "string")
        if kind in ("integer", "number"):
            return 0
        if kind == "boolean":
            return False
        return None


_STRING_FORMATS = {
    "date": "2024-01-31",
    "date-time": "2024-01-31T10:00:00Z",
    "uuid": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "email": "user@example.com",
    "uri": "https://example.com",
    "password": "",
}


def _first_example(examples: Any, parser: _Parser) -> Any:
    if isinstance(examples, dict):
        for example in examples.values():
            example = parser.resolve(example)
            if isinstance(example, dict) and "value" in example:
                return example["value"]
    return None


def _media_example(media: dict[str, Any], parser: _Parser) -> Any:
    if "example" in media:
        return media["example"]
    return _first_example(media.get("examples"), parser)


def _scalar_text(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)
