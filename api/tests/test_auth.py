import hashlib
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from challsmith_api.config import get_settings
from challsmith_api.main import app
from challsmith_api.models import WebSession

CREDS = {"username": "boss", "password": "s3cret-pw"}


@pytest.fixture(autouse=True)
def admin_env(monkeypatch):
    monkeypatch.setenv("WEB_ADMIN_USER", CREDS["username"])
    monkeypatch.setenv("WEB_ADMIN_PASSWORD", CREDS["password"])
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def login(client, **over):
    return client.post("/auth/login", json={**CREDS, **over})


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def test_login_and_me(client, db):
    r = login(client)
    assert r.status_code == 200
    token = r.json()["token"]
    assert datetime.fromisoformat(r.json()["expires_at"]) > datetime.now(timezone.utc)
    me = client.get("/auth/me", headers=bearer(token))
    assert me.status_code == 200
    assert me.json() == {"username": "boss"}


@pytest.mark.parametrize("over", [{"password": "nope"}, {"username": "other"}, {"password": ""}])
def test_bad_credentials(client, over):
    assert login(client, **over).status_code == 401


def test_empty_configured_password_never_logs_in(client, monkeypatch):
    monkeypatch.setenv("WEB_ADMIN_PASSWORD", "")
    get_settings.cache_clear()
    assert login(client, password="").status_code == 401


def test_missing_and_garbage_token(client):
    assert client.get("/auth/me").status_code == 401
    assert client.get("/auth/me", headers=bearer("garbage")).status_code == 401
    assert client.get("/auth/me", headers={"Authorization": "Basic abc"}).status_code == 401


def test_expired_token(client, db):
    token = login(client).json()["token"]
    row = db.get(WebSession, hashlib.sha256(token.encode()).hexdigest())
    row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()
    assert client.get("/auth/me", headers=bearer(token)).status_code == 401


def test_logout_invalidates_token(client):
    token = login(client).json()["token"]
    assert client.post("/auth/logout", headers=bearer(token)).status_code == 204
    assert client.get("/auth/me", headers=bearer(token)).status_code == 401


def test_token_not_stored_in_plaintext(client, db):
    token = login(client).json()["token"]
    rows = db.execute(text("SELECT token_hash FROM web_sessions")).scalars().all()
    assert rows == [hashlib.sha256(token.encode()).hexdigest()]
    assert token not in rows


def test_clear_sessions(client, db):
    from challsmith_api.auth import clear_sessions

    login(client)
    login(client)
    assert clear_sessions(db) == 2
    assert db.execute(text("SELECT count(*) FROM web_sessions")).scalar() == 0


def walk_routes(routes, prefix=""):
    # Newer FastAPI keeps included routers lazy (_IncludedRouter), so unwrap them.
    for r in routes:
        if hasattr(r, "original_router"):
            yield from walk_routes(r.original_router.routes, prefix + r.include_context.prefix)
        elif getattr(r, "methods", None):
            yield prefix + r.path, r.methods


def test_all_routes_require_session(client):
    exempt = {"/health", "/auth/login"}
    checked = 0
    for path, methods in walk_routes(app.routes):
        if path in exempt:
            continue
        for method in methods - {"HEAD", "OPTIONS"}:
            url = path.replace("{", "").replace("}", "")
            assert client.request(method, url).status_code == 401, (method, path)
            checked += 1
    assert checked >= 2
    for p in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(p).status_code == 404
