"""Tiny in-memory REST backend to try API Client without a Spring Boot app.

    python tools/mock_server.py [port]      (default 8080)

Endpoints: /api/productos (CRUD), /api/usuarios (GET, POST), /api/auth/login (POST), and the springdoc-style
OpenAPI spec describing them at /v3/api-docs.
Write operations on /api/productos require an ``Authorization: Bearer ...`` header.
"""

from __future__ import annotations

import json
import re
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

_lock = threading.Lock()
_products: dict[int, dict] = {
    1: {"id": 1, "nombre": "Laptop", "precio": 2500, "stock": 10},
    2: {"id": 2, "nombre": "Teclado", "precio": 120, "stock": 40},
    3: {"id": 3, "nombre": "Mouse", "precio": 45, "stock": 75},
}
_users: list[dict] = [{"id": 1, "nombre": "Admin", "email": "admin@example.com"}]
_ITEM = re.compile(r"^/api/productos/(\d+)$")

_PRODUCT_ID = {"name": "id", "in": "path", "required": True, "schema": {"type": "integer", "format": "int64"}}
_JSON_PRODUCT = {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/Producto"}}},
                 "required": True}
_BEARER = [{"bearerAuth": []}]
# Shaped like what springdoc-openapi generates for Spring controllers (one tag per controller).
OPENAPI_SPEC = {
    "openapi": "3.0.1",
    "info": {"title": "Tienda API", "version": "v1"},
    "servers": [{"url": "http://localhost:8080", "description": "Generated server url"}],
    "paths": {
        "/api/productos": {
            "get": {"tags": ["producto-controller"], "operationId": "listarProductos",
                    "parameters": [
                        {"name": "page", "in": "query", "schema": {"type": "integer", "default": 0}},
                        {"name": "size", "in": "query", "schema": {"type": "integer", "default": 20}},
                        {"name": "sort", "in": "query", "schema": {"type": "string"}, "example": "nombre"},
                    ],
                    "responses": {"200": {"description": "OK"}}},
            "post": {"tags": ["producto-controller"], "operationId": "crearProducto", "security": _BEARER,
                     "requestBody": _JSON_PRODUCT, "responses": {"201": {"description": "Created"}}},
        },
        "/api/productos/{id}": {
            "get": {"tags": ["producto-controller"], "operationId": "obtenerProducto", "parameters": [_PRODUCT_ID],
                    "responses": {"200": {"description": "OK"}}},
            "put": {"tags": ["producto-controller"], "operationId": "actualizarProducto", "security": _BEARER,
                    "parameters": [_PRODUCT_ID], "requestBody": _JSON_PRODUCT,
                    "responses": {"200": {"description": "OK"}}},
            "delete": {"tags": ["producto-controller"], "operationId": "eliminarProducto", "security": _BEARER,
                       "parameters": [_PRODUCT_ID], "responses": {"204": {"description": "No Content"}}},
        },
        "/api/usuarios": {
            "get": {"tags": ["usuario-controller"], "operationId": "listarUsuarios",
                    "responses": {"200": {"description": "OK"}}},
            "post": {"tags": ["usuario-controller"], "operationId": "crearUsuario",
                     "requestBody": {"content": {"application/json": {
                         "schema": {"$ref": "#/components/schemas/Usuario"}}}},
                     "responses": {"201": {"description": "Created"}}},
        },
        "/api/auth/login": {
            "post": {"tags": ["auth-controller"], "summary": "Iniciar sesión", "operationId": "login",
                     "requestBody": {"content": {"application/json": {
                         "example": {"username": "admin", "password": "admin"}}}},
                     "responses": {"200": {"description": "OK"}}},
        },
    },
    "components": {
        "schemas": {
            "Producto": {"type": "object", "required": ["nombre"], "properties": {
                "id": {"type": "integer", "format": "int64", "readOnly": True},
                "nombre": {"type": "string", "example": "Monitor"},
                "precio": {"type": "number", "example": 350},
                "stock": {"type": "integer", "example": 5},
            }},
            "Usuario": {"type": "object", "properties": {
                "id": {"type": "integer", "format": "int64", "readOnly": True},
                "nombre": {"type": "string"},
                "email": {"type": "string", "format": "email"},
            }},
        },
        "securitySchemes": {"bearerAuth": {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}},
    },
}


class Handler(BaseHTTPRequestHandler):
    server_version = "MockSpring/1.0"

    def _send(self, status: int, payload: object | None = None) -> None:
        body = b"" if payload is None else json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        if payload is not None:
            self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body and self.command != "HEAD":
            self.wfile.write(body)

    def _json_body(self) -> dict | None:
        length = int(self.headers.get("Content-Length") or 0)
        try:
            data = json.loads(self.rfile.read(length) or b"null")
        except ValueError:
            return None
        return data if isinstance(data, dict) else None

    def _authorized(self) -> bool:
        if (self.headers.get("Authorization") or "").startswith("Bearer "):
            return True
        self._send(401, {"status": 401, "error": "Unauthorized", "message": "Missing bearer token"})
        return False

    def _error(self, status: int, message: str) -> None:
        self._send(status, {"status": status, "error": self.responses[status][0], "message": message,
                            "path": urlsplit(self.path).path})

    def do_GET(self) -> None:
        parts = urlsplit(self.path)
        if parts.path == "/v3/api-docs":
            self._send(200, OPENAPI_SPEC)
        elif parts.path == "/api/productos":
            query = parse_qs(parts.query)
            page, size = int(query.get("page", ["0"])[0]), int(query.get("size", ["20"])[0])
            with _lock:
                items = sorted(_products.values(), key=lambda p: str(p.get(query.get("sort", ["id"])[0], "")))
            self._send(200, {"content": items[page * size:(page + 1) * size], "page": page, "size": size,
                             "totalElements": len(items)})
        elif match := _ITEM.match(parts.path):
            product = _products.get(int(match.group(1)))
            self._send(200, product) if product else self._error(404, "Producto no encontrado")
        elif parts.path == "/api/usuarios":
            self._send(200, _users)
        else:
            self._error(404, "No handler found")

    do_HEAD = do_GET

    def do_POST(self) -> None:
        path = urlsplit(self.path).path
        body = self._json_body()
        if path == "/api/auth/login":
            if body and body.get("username") == "admin" and body.get("password") == "admin":
                self._send(200, {"token": "local-dev-token", "type": "Bearer", "expiresIn": 3600})
            else:
                self._error(401, "Credenciales inválidas")
            return
        if path == "/api/usuarios":
            if body is None:
                return self._error(400, "Invalid JSON body")
            user = {"id": len(_users) + 1, **body}
            _users.append(user)
            return self._send(201, user)
        if path != "/api/productos":
            return self._error(404, "No handler found")
        if not self._authorized():
            return
        if body is None or "nombre" not in body:
            return self._error(400, "El campo 'nombre' es obligatorio")
        with _lock:
            new_id = max(_products, default=0) + 1
            _products[new_id] = {"id": new_id, **body}
        self._send(201, _products[new_id])

    def do_PUT(self) -> None:
        match = _ITEM.match(urlsplit(self.path).path)
        if not match:
            return self._error(404, "No handler found")
        if not self._authorized():
            return
        body = self._json_body()
        product_id = int(match.group(1))
        if product_id not in _products:
            return self._error(404, "Producto no encontrado")
        if body is None:
            return self._error(400, "Invalid JSON body")
        with _lock:
            _products[product_id] = {"id": product_id, **body}
        self._send(200, _products[product_id])

    do_PATCH = do_PUT

    def do_DELETE(self) -> None:
        match = _ITEM.match(urlsplit(self.path).path)
        if not match:
            return self._error(404, "No handler found")
        if not self._authorized():
            return
        with _lock:
            removed = _products.pop(int(match.group(1)), None)
        self._send(204) if removed else self._error(404, "Producto no encontrado")


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Mock backend listening on http://localhost:{port}  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
