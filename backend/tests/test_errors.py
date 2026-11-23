from app.services import errors
from test_challenges import api, make  # noqa: F401  (fixture reused)
from test_auth import admin_env  # noqa: F401  (fixture reused)


def test_conflict_has_code(api):
    assert make(api).status_code == 200
    r = make(api)
    assert r.status_code == 409
    assert r.json() == {"detail": "slug already exists", "code": "slug_exists"}


def test_not_found_has_code(api):
    r = api.get("/challenges/nope")
    assert r.status_code == 404 and r.json()["code"] == "not_found"


def test_unauthorized_has_code(client):
    r = client.get("/challenges")
    assert r.status_code == 401 and r.json()["code"] == "unauthorized"
    assert r.headers["www-authenticate"] == "Bearer"


def test_default_code():
    assert errors.BadRequest("x").code == "bad_request"
