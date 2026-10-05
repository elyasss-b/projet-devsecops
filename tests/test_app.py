import pytest

import app as app_module


@pytest.fixture
def client():
    app_module._notes.clear()
    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as client:
        yield client


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json()["status"] == "ok"


def test_security_headers(client):
    response = client.get("/health")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"


def test_create_and_get_note(client):
    created = client.post("/api/notes", json={"title": "Premiere note"})
    assert created.status_code == 201
    note_id = created.get_json()["id"]
    response = client.get(f"/api/notes/{note_id}")
    assert response.get_json()["title"] == "Premiere note"


@pytest.mark.parametrize("payload", [{}, {"title": ""}, {"title": "   "}, {"title": 42}])
def test_create_note_invalid(client, payload):
    assert client.post("/api/notes", json=payload).status_code == 400


def test_title_too_long(client):
    response = client.post("/api/notes", json={"title": "x" * 101})
    assert response.status_code == 400


def test_delete_note(client):
    note_id = client.post("/api/notes", json={"title": "A supprimer"}).get_json()["id"]
    assert client.delete(f"/api/notes/{note_id}").status_code == 204
    assert client.get(f"/api/notes/{note_id}").status_code == 404


def test_index_escapes_html(client):
    client.post("/api/notes", json={"title": "<script>alert(1)</script>"})
    body = client.get("/").get_data(as_text=True)
    assert "<script>alert(1)</script>" not in body
    assert "&lt;script&gt;" in body
