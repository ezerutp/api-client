"""Runs an HTTP request on the Qt thread pool so the UI never blocks."""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, QRunnable, Signal

from app.network.errors import ErrorKind, RequestError
from app.services.http_client_service import CancelToken, HttpClientService
from app.services.request_builder import PreparedRequest

log = logging.getLogger(__name__)


class WorkerSignals(QObject):
    finished = Signal(object)  # ApiResponse
    failed = Signal(object)    # RequestError


class RequestWorker(QRunnable):
    def __init__(self, service: HttpClientService, prepared: PreparedRequest) -> None:
        super().__init__()
        self.service = service
        self.prepared = prepared
        self.token = CancelToken()
        # Created on the UI thread, so emitted signals are delivered there.
        self.signals = WorkerSignals()

    def cancel(self) -> None:
        self.token.cancel()

    def run(self) -> None:
        try:
            response = self.service.execute(self.prepared, self.token)
        except RequestError as error:
            self.signals.failed.emit(error)
        except Exception as exc:  # a worker must never crash the app
            log.exception("Unexpected error while sending request")
            self.signals.failed.emit(RequestError(ErrorKind.UNKNOWN, "Unexpected error", str(exc), "",
                                                  self.prepared.masked_url))
        else:
            self.signals.finished.emit(response)
