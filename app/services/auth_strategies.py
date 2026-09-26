"""How each authentication type turns into HTTP headers.

To add a new scheme (e.g. OAuth2 client credentials) add an ``AuthType`` value
and register a strategy here; the request builder does not need to change.
"""

from __future__ import annotations

import base64
from collections.abc import Callable
from typing import Protocol

from app.models.auth import Authentication, AuthType


class AuthConfigurationError(Exception):
    pass


class AuthStrategy(Protocol):
    def headers(self, auth: Authentication, resolve: Callable[[str], str]) -> list[tuple[str, str]]: ...

    def secret_values(self, auth: Authentication, resolve: Callable[[str], str]) -> set[str]: ...


class NoAuthStrategy:
    def headers(self, auth: Authentication, resolve: Callable[[str], str]) -> list[tuple[str, str]]:
        return []

    def secret_values(self, auth: Authentication, resolve: Callable[[str], str]) -> set[str]:
        return set()


class BearerAuthStrategy:
    def headers(self, auth: Authentication, resolve: Callable[[str], str]) -> list[tuple[str, str]]:
        token = resolve(auth.token).strip()
        if not token:
            raise AuthConfigurationError("Bearer token is empty. Set it in the Auth tab or disable authentication.")
        return [("Authorization", f"Bearer {token}")]

    def secret_values(self, auth: Authentication, resolve: Callable[[str], str]) -> set[str]:
        return {resolve(auth.token).strip()} - {""}


class BasicAuthStrategy:
    def headers(self, auth: Authentication, resolve: Callable[[str], str]) -> list[tuple[str, str]]:
        username = resolve(auth.username)
        if not username:
            raise AuthConfigurationError("Basic Auth username is empty.")
        credentials = f"{username}:{resolve(auth.password)}".encode()
        return [("Authorization", "Basic " + base64.b64encode(credentials).decode("ascii"))]

    def secret_values(self, auth: Authentication, resolve: Callable[[str], str]) -> set[str]:
        password = resolve(auth.password)
        encoded = base64.b64encode(f"{resolve(auth.username)}:{password}".encode()).decode("ascii")
        return {password, encoded} - {""}


_STRATEGIES: dict[AuthType, AuthStrategy] = {
    AuthType.NONE: NoAuthStrategy(),
    AuthType.BEARER: BearerAuthStrategy(),
    AuthType.BASIC: BasicAuthStrategy(),
}


def strategy_for(auth_type: AuthType) -> AuthStrategy:
    return _STRATEGIES.get(auth_type, _STRATEGIES[AuthType.NONE])


def register_strategy(auth_type: AuthType, strategy: AuthStrategy) -> None:
    _STRATEGIES[auth_type] = strategy
