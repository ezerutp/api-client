"""Turns low level exceptions into messages a developer can act on."""

from __future__ import annotations

import socket
import ssl
from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import urlsplit

import httpx

from app.i18n import tr


class ErrorKind(StrEnum):
    CONNECTION_REFUSED = "connection_refused"
    DNS = "dns"
    TIMEOUT = "timeout"
    SSL = "ssl"
    INVALID_URL = "invalid_url"
    MISSING_VARIABLE = "missing_variable"
    INVALID_JSON = "invalid_json"
    INVALID_REQUEST = "invalid_request"
    TOO_MANY_REDIRECTS = "too_many_redirects"
    PROTOCOL = "protocol"
    NETWORK = "network"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


@dataclass
class RequestError(Exception):
    kind: ErrorKind
    title: str
    message: str
    hint: str = ""
    url: str = ""
    #: 1-based line in the JSON body editor, for INVALID_JSON errors.
    line: int | None = None

    def __str__(self) -> str:
        return f"{self.title}: {self.message}"


def _origin(url: str) -> str:
    try:
        parts = urlsplit(url)
        return f"{parts.scheme}://{parts.netloc}" if parts.netloc else url
    except ValueError:
        return url


def _causes(exc: BaseException) -> list[BaseException]:
    chain: list[BaseException] = []
    current: BaseException | None = exc
    while current is not None and current not in chain:
        chain.append(current)
        current = current.__cause__ or current.__context__
    return chain


def map_exception(exc: BaseException, url: str, timeout: float) -> RequestError:
    origin = _origin(url)
    chain = _causes(exc)
    text = " ".join(str(e) for e in chain).lower()

    if isinstance(exc, httpx.TimeoutException):
        phase = {
            httpx.ConnectTimeout: tr("connecting to"),
            httpx.ReadTimeout: tr("waiting for a response from"),
            httpx.WriteTimeout: tr("sending data to"),
            httpx.PoolTimeout: tr("waiting for a free connection to"),
        }.get(type(exc), tr("talking to"))
        return RequestError(
            ErrorKind.TIMEOUT, tr("Request timed out"),
            tr("No answer after {seconds} s while {phase}\n{origin}", seconds=f"{timeout:g}", phase=phase,
               origin=origin),
            tr("The server may be busy or stuck. You can raise the timeout in Settings → Network."), url,
        )
    if isinstance(exc, httpx.TooManyRedirects):
        return RequestError(
            ErrorKind.TOO_MANY_REDIRECTS, tr("Too many redirects"),
            tr("The server kept redirecting the request.\n{url}", url=url),
            tr("Check for a redirect loop, or disable 'Follow redirects' in Settings → Network."), url,
        )
    if isinstance(exc, (httpx.UnsupportedProtocol, httpx.InvalidURL)):
        return RequestError(
            ErrorKind.INVALID_URL, tr("Invalid URL"), f"{url}\n{exc}",
            tr("URLs must start with http:// or https:// and include a host, e.g. http://localhost:8080/api."), url,
        )
    if any(isinstance(e, ssl.SSLError) for e in chain) or "ssl" in text or "certificate" in text:
        return RequestError(
            ErrorKind.SSL, tr("SSL error"), tr("Secure connection to {origin} failed.", origin=origin) + f"\n{chain[-1]}",
            tr("The certificate may be self-signed or expired. For local development you can disable "
               "SSL verification in Settings → Network."), url,
        )
    if any(isinstance(e, socket.gaierror) for e in chain) or any(
        s in text for s in ("name or service not known", "nodename nor servname", "getaddrinfo failed",
                            "temporary failure in name resolution", "no address associated")
    ):
        host = urlsplit(url).hostname or origin
        return RequestError(
            ErrorKind.DNS, tr("Host not found"), tr("Could not resolve the host name:\n{host}", host=host),
            tr("Check the URL for typos and verify your network or VPN connection."), url,
        )
    if any(isinstance(e, ConnectionRefusedError) for e in chain) or "connection refused" in text or \
            "actively refused" in text or "errno 111" in text:
        return RequestError(
            ErrorKind.CONNECTION_REFUSED, tr("Connection refused"), tr("Could not connect to:\n{origin}", origin=origin),
            tr("Make sure the server is running and listening on that port."), url,
        )
    if isinstance(exc, (httpx.RemoteProtocolError, httpx.LocalProtocolError)):
        return RequestError(
            ErrorKind.PROTOCOL, tr("Protocol error"), tr("The server response could not be understood.") + f"\n{exc}",
            tr("The server may have closed the connection unexpectedly or is not speaking HTTP on this port."), url,
        )
    if isinstance(exc, (httpx.NetworkError, httpx.TransportError, OSError)):
        return RequestError(
            ErrorKind.NETWORK, tr("Network error"), tr("The request to {origin} failed.", origin=origin) + f"\n{exc}",
            tr("Check your network connection and that the server is reachable."), url,
        )
    return RequestError(ErrorKind.UNKNOWN, tr("Unexpected error"), f"{type(exc).__name__}: {exc}", "", url)
