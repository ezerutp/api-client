from __future__ import annotations

import shlex

from app.services.request_builder import PreparedRequest


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
