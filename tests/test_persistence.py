import json

from app.models.api_request import ApiRequest, BodyType, HttpMethod, RequestBody, RequestHeader
from app.models.auth import Authentication, AuthType
from app.models.collection import Collection
from app.repositories.collection_repository import CollectionRepository
from app.services.project_service import ProjectService, find_api_dir


def sample_request() -> ApiRequest:
    return ApiRequest(
        name="Crear producto", method=HttpMethod.POST, url="{{base_url}}/api/productos",
        headers=[RequestHeader("Accept", "application/json")],
        auth=Authentication(AuthType.BEARER, token="{{token}}"),
        body=RequestBody(BodyType.JSON, '{\n  "nombre": "Monitor",\n  "precio": 800\n}'),
    )


def test_request_round_trip():
    request = sample_request()
    restored = ApiRequest.from_dict(json.loads(json.dumps(request.to_dict())))
    assert restored == request


def test_request_from_hand_written_json_is_lenient():
    request = ApiRequest.from_dict({"name": "x", "method": "post", "body": {"type": "json", "content": {"a": 1}}})
    assert request.method is HttpMethod.POST
    assert json.loads(request.body.content) == {"a": 1}


def test_collection_read_write(tmp_path):
    repo = CollectionRepository(tmp_path)
    collection = Collection(id="productos", name="Productos", base_path="/api/productos", requests=[sample_request()])
    repo.save(collection)
    text = (tmp_path / "productos.json").read_text()
    assert '"name": "Productos"' in text  # human readable
    loaded, warnings = repo.load_all()
    assert warnings == []
    assert loaded == [collection]


def test_corrupt_collection_is_reported_and_untouched(tmp_path):
    (tmp_path / "project.json").write_text("{}")
    broken = tmp_path / "rota.json"
    broken.write_text("{ not json")
    collections, warnings = CollectionRepository(tmp_path).load_all()
    assert collections == []
    assert warnings[0].file_name == "rota.json"
    assert broken.read_text() == "{ not json"


def test_create_and_reopen_project(tmp_path):
    service = ProjectService.create(tmp_path, "Backend Tienda", "http://localhost:8080")
    api_dir = tmp_path / "api-client"
    assert (api_dir / "project.json").is_file()
    assert (api_dir / ".gitignore").read_text() == ".secrets.json\n"
    assert json.loads((api_dir / ".secrets.json").read_text()) == {}
    assert find_api_dir(tmp_path) == api_dir.resolve()

    collection = service.create_collection("Productos", "api/productos")
    request = service.create_request(collection.id, "Crear producto", HttpMethod.POST)
    assert request.url == "{{base_url}}/api/productos"
    request.body.content = '{"nombre": "Monitor"}'
    service.save_request(request.id)

    reopened = ProjectService.open(api_dir).service
    assert reopened.project.name == "Backend Tienda"
    _, again = reopened.find_request(request.id)
    assert again.body.content == '{"nombre": "Monitor"}'
    assert again.method is HttpMethod.POST


def test_rename_collection_renames_file(tmp_path):
    service = ProjectService.create(tmp_path, "P", "http://x")
    collection = service.create_collection("Productos")
    service.update_collection(collection.id, name="Products", base_path="")
    assert (tmp_path / "api-client" / "products.json").exists()
    assert not (tmp_path / "api-client" / "productos.json").exists()
    assert service.project.collection_order == ["products"]


def test_duplicate_move_delete_request(tmp_path):
    service = ProjectService.create(tmp_path, "P", "http://x")
    a = service.create_collection("A")
    b = service.create_collection("B")
    request = service.create_request(a.id, "Login", HttpMethod.POST)
    copy = service.duplicate_request(request.id)
    assert copy.name == "Login copy" and copy.id != request.id
    service.move_request(copy.id, b.id)
    reopened = ProjectService.open(tmp_path / "api-client").service
    assert [r.name for r in reopened.collection(b.id).requests] == ["Login copy"]
    service.delete_request(request.id)
    assert ProjectService.open(tmp_path / "api-client").service.collection(a.id).requests == []


def test_secrets_saved_separately(tmp_path):
    service = ProjectService.create(tmp_path, "P", "http://x")
    service.save_environments(
        {"base_url": "http://localhost:8080"}, {"api_key": "k"},
        {"local": ({"user_id": "1"}, {"token": "abc"})},
    )
    api_dir = tmp_path / "api-client"
    project = json.loads((api_dir / "project.json").read_text())
    secrets = json.loads((api_dir / ".secrets.json").read_text())
    assert "abc" not in json.dumps(project)
    assert secrets == {"api_key": "k", "local": {"token": "abc"}}
    assert project["base_url"] == "http://localhost:8080"
    ctx = ProjectService.open(api_dir).service.variable_context("local")
    assert ctx.values["token"] == "abc"
