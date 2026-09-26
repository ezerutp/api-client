import pytest

from app.models.environment import Environment
from app.models.project import Project
from app.repositories.secrets_repository import Secrets
from app.services.variable_service import (
    CircularVariableError,
    MissingVariablesError,
    VariableContext,
    VariableResolver,
    build_variable_context,
    find_variables,
)


def resolver(**values: str) -> VariableResolver:
    return VariableResolver(VariableContext(values=values))


def test_resolves_simple_variables():
    assert resolver(base_url="http://localhost:8080").resolve("{{base_url}}/api") == "http://localhost:8080/api"


def test_tolerates_spaces_inside_braces():
    assert resolver(token="abc").resolve("Bearer {{ token }}") == "Bearer abc"


def test_nested_variables():
    r = resolver(host="localhost", base_url="http://{{host}}:8080")
    assert r.resolve("{{base_url}}/x") == "http://localhost:8080/x"


def test_missing_variables_are_all_reported():
    with pytest.raises(MissingVariablesError) as info:
        resolver().resolve("{{a}}/{{b}}")
    assert info.value.names == ["a", "b"]


def test_circular_reference_detected():
    with pytest.raises(CircularVariableError):
        resolver(a="{{b}}", b="{{a}}").resolve("{{a}}")


def test_values_are_never_evaluated():
    r = resolver(x="__import__('os').system('echo hi')")
    assert r.resolve("{{x}}") == "__import__('os').system('echo hi')"


def test_single_braces_are_left_alone():
    assert resolver().resolve("/api/{id}") == "/api/{id}"


def test_find_variables_deduplicates():
    assert find_variables("{{a}} {{b}} {{a}}") == ["a", "b"]


def test_context_precedence():
    project = Project(
        name="p", base_url="http://default", variables={"token": "global", "user_id": "1"},
        environments={"local": Environment("local", {"base_url": "http://local", "token": "envvar"})},
    )
    secrets = Secrets(globals={"api_key": "g-secret"}, by_environment={"local": {"token": "env-secret"}})
    ctx = build_variable_context(project, secrets, "local")
    assert ctx.values["base_url"] == "http://local"
    assert ctx.values["token"] == "env-secret"
    assert ctx.values["user_id"] == "1"
    assert ctx.is_secret("token") and ctx.is_secret("api_key")
    assert "env-secret" in ctx.secret_values()


def test_context_without_environment_uses_project_base_url():
    ctx = build_variable_context(Project(name="p", base_url="http://x"), Secrets(), None)
    assert ctx.values["base_url"] == "http://x"
