"""Executes prepared requests with httpx. Blocking: call it from a worker thread."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable

import httpx

from app.models.api_request import ApiRequest
from app.models.api_response import ApiResponse
from app.models.settings import NetworkSettings
from app.network.errors import ErrorKind, RequestError, map_exception
from app.services.request_builder import PreparedRequest, RequestBuilder
from app.services.variable_service import VariableContext

log = logging.getLogger(__name__)

MAX_BODY_BYTES = 50 * 1024 * 1024
_CHUNK_SIZE = 64 * 1024


class CancelToken:
    """Shared between the UI and the worker; closing the client interrupts blocking I/O."""

    def __init__(self) -> None:
        self._event = threading.Event()
        self._client: httpx.Client | None = None
        self._lock = threading.Lock()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def cancel(self) -> None:
        self._event.set()
        with self._lock:
            client = self._client
        if client is not None:
            try:
                client.close()
            except Exception:  # closing from another thread is best effort
                pass

    def attach(self, client: httpx.Client | None) -> None:
        with self._lock:
            self._client = client


def _cancelled_error(url: str) -> RequestError:
    return RequestError(ErrorKind.CANCELLED, "Request cancelled", "The request was cancelled.", "", url)


class HttpClientService:
    def __init__(self, settings_provider: Callable[[], NetworkSettings]) -> None:
        self._settings_provider = settings_provider

    @staticmethod
    def prepare(request: ApiRequest, context: VariableContext) -> PreparedRequest:
        return RequestBuilder(context).build(request)

    def execute(self, prepared: PreparedRequest, cancel: CancelToken | None = None) -> ApiResponse:
        settings = self._settings_provider()
        cancel = cancel or CancelToken()
        log.info("%s %s", prepared.method, prepared.masked_url)
        client = httpx.Client(
            timeout=httpx.Timeout(settings.timeout_seconds),
            verify=settings.verify_ssl,
            follow_redirects=settings.follow_redirects,
            proxy=settings.proxy or None,
        )
        cancel.attach(client)
        started = time.perf_counter()
        try:
            with client, client.stream(prepared.method, prepared.url, headers=prepared.headers,
                               content=prepared.body) as response:
                body, truncated = self._read_body(response, cancel)
                elapsed_ms = (time.perf_counter() - started) * 1000
                return ApiResponse(
                    status_code=response.status_code,
                    reason=response.reason_phrase,
                    headers=[(k, v) for k, v in response.headers.multi_items()],
                    body=body,
                    elapsed_ms=elapsed_ms,
                    url=str(response.url),
                    method=prepared.method,
                    http_version=response.http_version,
                    request_headers=prepared.masked_headers(),
                    truncated=truncated,
                )
        except RequestError:
            raise
        except Exception as exc:  # every failure becomes a readable RequestError
            if cancel.cancelled:
                raise _cancelled_error(prepared.url) from None
            error = map_exception(exc, prepared.url, settings.timeout_seconds)
            log.info("%s %s failed: %s", prepared.method, prepared.masked_url, error.title)
            raise error from None
        finally:
            cancel.attach(None)

    @staticmethod
    def _read_body(response: httpx.Response, cancel: CancelToken) -> tuple[bytes, bool]:
        chunks: list[bytes] = []
        total = 0
        for chunk in response.iter_bytes(_CHUNK_SIZE):
            if cancel.cancelled:
                raise _cancelled_error(str(response.url))
            chunks.append(chunk)
            total += len(chunk)
            if total > MAX_BODY_BYTES:
                return b"".join(chunks)[:MAX_BODY_BYTES], True
        return b"".join(chunks), False
