import io
import zipfile

import pytest
from sqlalchemy import select

from challsmith_api.challenges import current_hash, load_challenge
from challsmith_api.models import Challenge
from test_auth import admin_env, bearer, login  # noqa: F401  (fixture reused)

BIG = 20 * 1024 * 1024 + 1


@pytest.fixture
def api(client, db):
    client.headers.update(bearer(login(client).json()["token"]))
    return client


def make(api, slug="c1", template="php"):
    return api.post("/challenges", json={"slug": slug, "template": template, "name": "C One"})


def folder_svc(api, slug="c1"):
    return next(s["name"] for s in api.get(f"/challenges/{slug}").json()["meta"]["services"] if not s.get("image"))


def zipped(members: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for n, b in members.items():
            z.writestr(n, b)
    return buf.getvalue()


def test_create_list_get(api):
    assert make(api).status_code == 200
    rows = api.get("/challenges").json()
    assert len(rows) == 1
    r = rows[0]
    assert (r["slug"], r["name"], r["publish"], r["sync"]) == ("c1", "C One", "draft", "never")
    assert r["category"] and r["scenario"] and r["updated_at"]
    d = api.get("/challenges/c1").json()
    assert d["meta"]["slug"] == "c1" and d["status"] == {"publish": "draft", "sync": "never"}
    assert any(f["path"].startswith("services/") and f["size"] > 0 for f in d["files"])
    assert api.get("/challenges/nope").status_code == 404


def test_create_errors(api):
    assert make(api).status_code == 200
    assert make(api).status_code == 409
    assert make(api, "c2", "nope").status_code == 400
    assert make(api, "c3", "..").status_code == 400
    assert make(api, "BAD SLUG").status_code == 422


def test_file_edit_roundtrip_bumps_updated_at(api):
    make(api)
    svc = folder_svc(api)
    before = api.get("/challenges").json()[0]["updated_at"]
    path = f"services/{svc}/Dockerfile"
    assert api.put(f"/challenges/c1/files/{path}", content=b"FROM x\r\n\0bin").status_code == 200
    assert api.get(f"/challenges/c1/files/{path}").content == b"FROM x\r\n\0bin"
    assert api.get("/challenges").json()[0]["updated_at"] > before
    assert api.put(f"/challenges/c1/files/services/{svc}/new/n.txt", content=b"n").status_code == 200


def test_file_delete(api):
    make(api)
    path = f"services/{folder_svc(api)}/Dockerfile"
    before = api.get("/challenges").json()[0]["updated_at"]
    assert api.delete(f"/challenges/c1/files/{path}").status_code == 200
    assert api.get("/challenges").json()[0]["updated_at"] > before
    assert api.get(f"/challenges/c1/files/{path}").status_code == 404
    assert api.delete(f"/challenges/c1/files/{path}").status_code == 404


@pytest.mark.parametrize("path", ["..%2Fx", "services%2F..%2F..%2Fx", "challenge.yml", "services/nope/x", "services/SVC", "services/SVC/"])
def test_put_file_bad_path(api, path):
    make(api)
    path = path.replace("SVC", folder_svc(api))
    assert api.put(f"/challenges/c1/files/{path}", content=b"x").status_code == 400


def test_put_file_to_image_service_rejected(api):
    make(api, "m1", "nginx-php-db")
    d = api.get("/challenges/m1").json()
    img = next(s["name"] for s in d["meta"]["services"] if s.get("image"))
    assert api.put(f"/challenges/m1/files/services/{img}/x", content=b"x").status_code == 400


def test_put_file_too_big(api):
    make(api)
    r = api.put(f"/challenges/c1/files/services/{folder_svc(api)}/big", content=b"a" * BIG)
    assert r.status_code == 413


def test_put_meta(api):
    make(api)
    meta = api.get("/challenges/c1").json()["meta"]
    assert api.put("/challenges/c1", json={**meta, "value": 250}).status_code == 200
    assert api.get("/challenges/c1").json()["meta"]["value"] == 250
    assert api.put("/challenges/c1", json={**meta, "slug": "other"}).status_code == 400
    r = api.put("/challenges/c1", json={**meta, "value": -1})
    assert r.status_code == 422 and r.json()["detail"]
    assert api.put("/challenges/nope", json=meta).status_code == 404


def test_upload_zip(api):
    make(api)
    svc = folder_svc(api)
    z = zipped({"a/b.txt": b"hi", "top.txt": b"t"})
    r = api.post(f"/challenges/c1/upload?dir=services/{svc}/sub", files={"file": ("x.zip", z)})
    assert r.status_code == 200
    assert api.get(f"/challenges/c1/files/services/{svc}/sub/a/b.txt").content == b"hi"
    assert api.get(f"/challenges/c1/files/services/{svc}/sub/top.txt").content == b"t"


def test_upload_single_file(api):
    make(api)
    svc = folder_svc(api)
    r = api.post(f"/challenges/c1/upload?dir=services/{svc}", files={"file": ("../r.bin", b"data")})
    assert r.status_code == 200
    assert api.get(f"/challenges/c1/files/services/{svc}/r.bin").content == b"data"


def test_upload_rejections_change_nothing(api):
    make(api)
    svc = folder_svc(api)
    before = api.get("/challenges/c1").json()["files"]
    z = zipped({"ok.txt": b"ok", "../evil": b"x"})
    up = f"/challenges/c1/upload?dir=services/{svc}"
    assert api.post(up, files={"file": ("e.zip", z)}).status_code == 400
    assert api.post(up, files={"file": ("bad.zip", b"notzip")}).status_code == 400
    assert api.post("/challenges/c1/upload?dir=services/nope", files={"file": ("a.txt", b"x")}).status_code == 400
    assert api.post("/challenges/c1/upload?dir=..", files={"file": ("a.txt", b"x")}).status_code == 400
    assert api.post(up, files={"file": ("a.bin", b"a" * BIG)}).status_code == 413
    assert api.get("/challenges/c1").json()["files"] == before


def test_status_published_then_modified(api, db):
    make(api)
    ch, _, _ = load_challenge(db, "c1")
    ch.ctfd_id, ch.published_hash = 1, current_hash(db, ch)
    db.commit()
    assert api.get("/challenges/c1").json()["status"]["publish"] == "published"
    api.put(f"/challenges/c1/files/services/{folder_svc(api)}/Dockerfile", content=b"changed")
    assert api.get("/challenges/c1").json()["status"]["publish"] == "modified"
    ch.sync_hash = "x"
    db.commit()
    assert api.get("/challenges").json()[0]["sync"] == "modified"


def test_delete_challenge(api, db):
    make(api)
    assert api.delete("/challenges/c1").status_code == 200
    assert api.get("/challenges/c1").status_code == 404
    assert db.scalars(select(Challenge)).all() == []
    assert api.delete("/challenges/c1").status_code == 404
