"""cURL <-> request conversion.

``build_curl`` exports a prepared request; ``parse_curl`` imports a command copied from
a browser ("Copy as cURL", bash or cmd flavour), API docs or a terminal.
"""

from __future__ import annotations

import base64
import binascii
import json
import re
import shlex
from dataclasses import dataclass, field
from urllib.parse import parse_qsl, quote, urlsplit, urlunsplit

from app.i18n import tr
from app.models.api_request import ApiRequest, BodyType, HttpMethod, RequestBody, RequestHeader, RequestParameter
from app.models.auth import Authentication, AuthType
from app.services.request_builder import PreparedRequest
from app.services.variable_service import VariableContext, VariableError, VariableResolver


def build_curl(prepared: PreparedRequest, *, mask_secrets: bool = True) -> str:
    """A POSIX shell command equivalent to ``prepared``. Secrets are masked unless asked otherwise."""
    headers = prepared.masked_headers() if mask_secrets else prepared.headers
    url = prepared.masked_url if mask_secrets else prepared.url
    parts: list[str] = ["curl"]
    if prepared.method == "HEAD":
        parts.append("-I")
    elif prepared.method != "GET" or prepared.body:
        parts.append(f"-X {prepared.method}")
    lines = [" ".join(parts) + " " + shlex.quote(url)]
    lines += [f"-H {shlex.quote(f'{key}: {value}')}" for key, value in headers]
    if prepared.body:
        body = prepared.body_text
        if mask_secrets:
            body = prepared.mask(body)
        lines.append(f"--data-raw {shlex.quote(body)}")
    return " \\\n  ".join(lines)


# -- import ---------------------------------------------------------------------------

class CurlParseError(ValueError):
    """The text is not a usable cURL command; the message is user facing."""


@dataclass
class CurlImport:
    request: ApiRequest
    #: Options that were understood but have no equivalent here (``-F``, ``-o``...).
    ignored: list[str] = field(default_factory=list)

    def apply_to(self, request: ApiRequest) -> None:
        """Replace what the command defines; the request keeps its id, name and description."""
        source = self.request
        request.method = source.method
        request.url = source.url
        request.params = list(source.params)
        request.path_params = []
        request.headers = list(source.headers)
        request.auth = source.auth.copy()
        request.body = RequestBody(source.body.type, source.body.content, source.body.content_type)


_FORM_TYPE = "application/x-www-form-urlencoded"
_CURL_START = re.compile(r"^\s*(?:\$\s*)?curl(?:\.exe)?\s", re.IGNORECASE)

# Options that take a value, by every spelling. Anything else is treated as a flag.
_WITH_VALUE = {
    "-X": "method", "--request": "method",
    "-H": "header", "--header": "header",
    "-d": "data", "--data": "data", "--data-ascii": "data", "--data-binary": "data", "--data-raw": "data_raw",
    "--data-urlencode": "data_urlencode",
    "--json": "json",
    "-u": "user", "--user": "user",
    "-A": "user_agent", "--user-agent": "user_agent",
    "-e": "referer", "--referer": "referer",
    "-b": "cookie", "--cookie": "cookie",
    "--url": "url",
    "-F": "unsupported", "--form": "unsupported", "--form-string": "unsupported",
    "-T": "unsupported", "--upload-file": "unsupported",
    "-o": "ignored", "--output": "ignored", "-m": "ignored", "--max-time": "ignored",
    "--connect-timeout": "ignored", "-w": "ignored", "--write-out": "ignored", "--retry": "ignored",
    "-x": "unsupported", "--proxy": "unsupported", "--cacert": "ignored", "--cert": "unsupported",
    "-E": "unsupported", "--key": "unsupported", "-c": "ignored", "--cookie-jar": "ignored",
    "--resolve": "unsupported", "-r": "unsupported", "--range": "unsupported", "--limit-rate": "ignored",
    "-D": "ignored", "--dump-header": "ignored", "-K": "unsupported", "--config": "unsupported",
    "--oauth2-bearer": "bearer",
}
_HEAD_FLAGS = {"-I", "--head"}
_GET_FLAGS = {"-G", "--get"}


def base_url_for(context: VariableContext) -> str:
    """The resolved ``{{base_url}}`` of the active environment, or "" if it is not usable."""
    if not context.is_defined("base_url"):
        return ""
    try:
        return VariableResolver(context).resolve_variable("base_url")
    except VariableError:
        return ""


def looks_like_curl(text: str) -> bool:
    return bool(_CURL_START.match(text or ""))


def parse_curl(text: str, base_url: str = "") -> CurlImport:
    """Turn a cURL command into a request. URLs under ``base_url`` become ``{{base_url}}/...``."""
    if not looks_like_curl(text):
        raise CurlParseError(tr("The text does not start with curl."))
    try:
        tokens = _tokenize(_join_lines(text))
    except ValueError as exc:
        raise CurlParseError(tr("Could not read the command: {error}", error=exc)) from None
    if tokens and tokens[0] == "$":  # pasted with the shell prompt
        tokens = tokens[1:]
    tokens = tokens[1:]  # "curl"

    method: str | None = None
    url = ""
    head = force_get = False
    headers: list[tuple[str, str]] = []
    data: list[str] = []
    json_body = False
    auth = Authentication()
    ignored: list[str] = []

    for option, value in _options(tokens):
        kind = _WITH_VALUE.get(option) if option else "url"
        if option in _HEAD_FLAGS:
            head = True
        elif option in _GET_FLAGS:
            force_get = True
        elif kind == "url":
            url = url or value
        elif kind == "method":
            method = value.upper()
        elif kind == "header":
            header = _parse_header(value)
            if header is not None:
                headers.append(header)
        elif kind in ("data", "data_raw"):
            if kind == "data" and value.startswith("@"):
                ignored.append(f"{option} {value}")
                continue
            data.append(value if kind == "data_raw" else value.replace("\r", "").replace("\n", ""))
        elif kind == "data_urlencode":
            data.append(_urlencode_data(value))
        elif kind == "json":
            json_body = True
            data.append(value)
        elif kind == "user":
            username, _, password = value.partition(":")
            auth = Authentication(AuthType.BASIC, username=username, password=password)
        elif kind == "bearer":
            auth = Authentication(AuthType.BEARER, token=value)
        elif kind == "user_agent":
            headers.append(("User-Agent", value))
        elif kind == "referer":
            headers.append(("Referer", value))
        elif kind == "cookie":
            if "=" in value:
                headers.append(("Cookie", value))
            else:
                ignored.append(f"{option} {value}")  # a cookie file
        elif kind == "unsupported":
            ignored.append(f"{option} {value}")
        # "ignored" options and plain flags (-s, -L, -k, --compressed...) change nothing here.

    if not url:
        raise CurlParseError(tr("The command has no URL."))

    url, params = _split_query(url)
    body_text = "&".join(data)
    if force_get and data:
        params += [RequestParameter(k, v) for k, v in parse_qsl(body_text, keep_blank_values=True)]
        body_text, data = "", []

    if method is None:
        method = "HEAD" if head else ("POST" if data else "GET")
    if method not in HttpMethod.__members__:
        ignored.append(f"-X {method}")
    http_method = HttpMethod.parse(method)

    headers, auth = _extract_auth(headers, auth)
    if json_body:
        _set_default(headers, "Content-Type", "application/json")
        _set_default(headers, "Accept", "application/json")
    body, headers = _make_body(body_text, bool(data), headers)

    request = ApiRequest(
        name=_suggest_name(url, http_method),
        method=http_method,
        url=_with_base_url(url, base_url),
        params=params,
        headers=[RequestHeader(k, v) for k, v in headers],
        auth=auth,
        body=body,
    )
    return CurlImport(request, ignored)


def _join_lines(text: str) -> str:
    """Undo line continuations: ``\\`` (bash), ``^`` (cmd) and `` ` `` (PowerShell)."""
    text = text.replace("\r\n", "\n").strip()
    if re.search(r'\^\n|\^"', text):  # Chrome "Copy as cURL (cmd)"
        text = re.sub(r"\^\n", " ", text)
        return re.sub(r"\^(.)", r"\1", text)
    text = re.sub(r"\\\n", " ", text)
    text = re.sub(r"`\n", " ", text)
    return text.replace("\n", " ")


def _tokenize(text: str) -> list[str]:
    """POSIX shell words, plus ``$'...'`` (ANSI-C quoting, used by browsers for bodies)."""
    tokens: list[str] = []
    current: list[str] = []
    in_word = False
    i, n = 0, len(text)
    while i < n:
        char = text[i]
        if char.isspace():
            if in_word:
                tokens.append("".join(current))
                current, in_word = [], False
            i += 1
        elif char == "'":
            end = text.find("'", i + 1)
            if end < 0:
                raise ValueError(tr("unclosed single quote"))
            current.append(text[i + 1:end])
            in_word, i = True, end + 1
        elif char == "$" and i + 1 < n and text[i + 1] == "'":
            value, i = _ansi_c_string(text, i + 2)
            current.append(value)
            in_word = True
        elif char == '"':
            i += 1
            while True:
                if i >= n:
                    raise ValueError(tr("unclosed double quote"))
                if text[i] == '"':
                    i += 1
                    break
                if text[i] == "\\" and i + 1 < n and text[i + 1] in '"\\$`':
                    current.append(text[i + 1])
                    i += 2
                else:
                    current.append(text[i])
                    i += 1
            in_word = True
        elif char == "\\" and i + 1 < n:
            current.append(text[i + 1])
            in_word, i = True, i + 2
        else:
            current.append(char)
            in_word, i = True, i + 1
    if in_word:
        tokens.append("".join(current))
    return tokens


_ANSI_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "\\": "\\", "'": "'", '"': '"', "a": "\a", "b": "\b",
                 "e": "\x1b", "f": "\f", "v": "\v", "?": "?"}


def _ansi_c_string(text: str, i: int) -> tuple[str, int]:
    out: list[str] = []
    n = len(text)
    while i < n:
        char = text[i]
        if char == "'":
            return "".join(out), i + 1
        if char == "\\" and i + 1 < n:
            nxt = text[i + 1]
            if nxt in _ANSI_ESCAPES:
                out.append(_ANSI_ESCAPES[nxt])
                i += 2
                continue
            digits = {"x": 2, "u": 4, "U": 8}.get(nxt)
            if digits:
                match = re.match(rf"[0-9a-fA-F]{{1,{digits}}}", text[i + 2:])
                if match:
                    out.append(chr(int(match.group(0), 16)))
                    i += 2 + len(match.group(0))
                    continue
            out.append(char)
            i += 1
            continue
        out.append(char)
        i += 1
    raise ValueError(tr("unclosed single quote"))


def _options(tokens: list[str]):
    """Yield ``(option, value)``; positional arguments (the URL) come as ``(None, value)``."""
    i = 0
    while i < len(tokens):
        token = tokens[i]
        i += 1
        if token.startswith("--") and len(token) > 2:
            name, eq, inline = token.partition("=")
            if name in _WITH_VALUE:
                if eq:
                    yield name, inline
                elif i < len(tokens):
                    yield name, tokens[i]
                    i += 1
            else:
                yield token, ""
        elif token.startswith("-") and len(token) > 1:
            # Short options can be bundled: -sSL, -XPOST, -H'Accept: x'
            j = 1
            while j < len(token):
                name = "-" + token[j]
                if name in _WITH_VALUE:
                    rest = token[j + 1:]
                    if rest:
                        yield name, rest
                    elif i < len(tokens):
                        yield name, tokens[i]
                        i += 1
                    break
                yield name, ""
                j += 1
        else:
            yield None, token


def _parse_header(raw: str) -> tuple[str, str] | None:
    key, sep, value = raw.partition(":")
    if sep:
        return (key.strip(), value.strip()) if key.strip() else None
    if raw.endswith(";"):  # curl's syntax for a header with an empty value
        return raw[:-1].strip(), ""
    return None


def _urlencode_data(value: str) -> str:
    name, sep, content = value.partition("=")
    if sep:
        return f"{name}={quote(content, safe='')}" if name else quote(content, safe="")
    return quote(value, safe="")


def _split_query(url: str) -> tuple[str, list[RequestParameter]]:
    try:
        parts = urlsplit(url)
    except ValueError:
        return url, []
    if not parts.query:
        return urlunsplit((parts.scheme, parts.netloc, parts.path, "", parts.fragment)) if "?" in url else url, []
    params = [RequestParameter(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", parts.fragment)), params


def _header_index(headers: list[tuple[str, str]], name: str) -> int | None:
    lower = name.lower()
    return next((i for i, (k, _) in enumerate(headers) if k.lower() == lower), None)


def _set_default(headers: list[tuple[str, str]], name: str, value: str) -> None:
    if _header_index(headers, name) is None:
        headers.append((name, value))


def _extract_auth(headers: list[tuple[str, str]], auth: Authentication) -> tuple[list[tuple[str, str]], Authentication]:
    """An ``Authorization: Bearer|Basic`` header becomes the request's authentication."""
    index = _header_index(headers, "Authorization")
    if index is None or auth.type is not AuthType.NONE:
        return headers, auth
    scheme, _, credentials = headers[index][1].partition(" ")
    credentials = credentials.strip()
    if scheme.lower() == "bearer" and credentials:
        auth = Authentication(AuthType.BEARER, token=credentials)
    elif scheme.lower() == "basic" and credentials:
        try:
            decoded = base64.b64decode(credentials, validate=True).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError):
            return headers, auth
        username, _, password = decoded.partition(":")
        auth = Authentication(AuthType.BASIC, username=username, password=password)
    else:
        return headers, auth
    return headers[:index] + headers[index + 1:], auth


def _make_body(text: str, has_data: bool, headers: list[tuple[str, str]]) -> tuple[RequestBody, list[tuple[str, str]]]:
    """Pick the body type and move Content-Type from the headers into the body."""
    if not has_data:
        return RequestBody(), headers
    index = _header_index(headers, "Content-Type")
    content_type = headers[index][1] if index is not None else ""
    if index is not None:
        headers = headers[:index] + headers[index + 1:]
    try:
        parsed = json.loads(text)
        is_json = isinstance(parsed, (dict, list))
    except ValueError:
        is_json = False
    # A JSON-looking body sent without a Content-Type is almost always meant as JSON.
    if is_json and (not content_type or "json" in content_type.lower()):
        content = json.dumps(parsed, indent=2, ensure_ascii=False)
        body_type = BodyType.JSON
    else:
        content = text
        body_type = BodyType.TEXT
        content_type = content_type or _FORM_TYPE  # what curl sends for -d
    if content_type == body_type.default_content_type:
        content_type = ""
    return RequestBody(body_type, content, content_type), headers


def _with_base_url(url: str, base_url: str) -> str:
    base = base_url.strip()
    if not base or "{{" in base:
        return url
    stripped = base.rstrip("/")
    if url in (stripped, base):
        return "{{base_url}}"
    if base.endswith("/") and url.startswith(base):
        return "{{base_url}}" + url[len(base):]
    if url.startswith(stripped) and url[len(stripped)] in "/?#":
        return "{{base_url}}" + url[len(stripped):]
    return url


def _suggest_name(url: str, method: HttpMethod) -> str:
    try:
        parts = urlsplit(url if "://" in url else "http://" + url)
    except ValueError:
        return method.value
    segments = [s for s in parts.path.split("/") if s]
    return segments[-1] if segments else (parts.hostname or method.value)
