import json
import os

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.clients import ctfd_client, docker_client
from app.api import deps
from app.core.db import get_engine
from app.main import app
from app.models import Challenge, PublishRun
from app.services import challenge_service, publish_service
from app.services.errors import BadRequest
from test_auth import admin_env, bearer, login  # noqa: F401  (fixture reused)

PREFIX = "localhost:5000/challsmith"


class FakeDocker:
    def __init__(self, fail_build=False):
        self.calls, self.fail_build = [], fail_build

    def build(self, context_dir, tag, log):
        assert (context_dir / "Dockerfile").exists()
        self.calls.append(("build", tag))
        log("step 1/1")
        if self.fail_build:
            raise docker_client.DockerError("boom")

    def push(self, tag, log):
        self.calls.append(("push", tag))

    def pull(self, image, log):
        self.calls.append(("pull", image))

    def tag(self, src, dst, log):
        self.calls.append(("tag", src, dst))


class FakeCtfd:
    def __init__(self, missing=False, tags_fail=False):
        self.tags_fail = tags_fail
        self.created, self.updated, self.tags, self.deleted, self.missing = [], [], [], [], missing

    def create_challenge(self, payload):
        self.created.append(payload)
        return 12

    def update_challenge(self, cid, payload):
        if self.missing:
            raise ctfd_client.CtfdNotFound("gone")
        self.updated.append((cid, payload))

    def set_tags(self, cid, tags):
        if self.tags_fail:
            raise ctfd_client.CtfdError("tags down")
        self.tags.append((cid, tags))

    def delete_challenge(self, cid):
        self.deleted.append(cid)


def factory():
    return Session(get_engine())


def test_build_additional_single(db):
    challenge_service.create_challenge(db, "php-strcmp", "php", "P")
    meta = challenge_service.meta_of(db.scalar(select(Challenge)))
    meta = meta.model_copy(update={"flag": "php_strcmp_array"})
    img = f"{PREFIX}/php-strcmp-app:abc"
    assert publish_service.build_additional(meta, {"app": img}) == (
        "registry:5000/challsmith/scenarios/single:v1",
        {"image": img, "port": "80", "protocol": "http", "flag": "php_strcmp_array", "flag_prefix": "CTF",
         "memory": "256m", "cpus": "0.5"},
    )


def test_build_additional_multi(db):
    challenge_service.create_challenge(db, "n", "nginx-php-db", "N")
    meta = challenge_service.meta_of(db.scalar(select(Challenge)))
    images = {"web": f"{PREFIX}/n-web:1", "php": f"{PREFIX}/n-php:1"}
    ref, add = publish_service.build_additional(meta, images)
    assert ref.endswith("multi:v1")
    svcs = {s["name"]: s for s in json.loads(add["services"])}
    assert svcs["db"]["image"] == f"{PREFIX}/mirror/mariadb:11.8"
    assert svcs["web"]["entry"] is True and svcs["web"]["port"] == 80
    assert add["memory"] == "512m" and all(isinstance(v, str) for v in add.values())


def test_write_context_modes(tmp_path):
    old = os.umask(0o077)
    try:
        ctx = tmp_path / "ctx"
        ctx.mkdir(mode=0o700)
        publish_service._write_context(ctx, {"services/app/a/b.php": b"x", "services/app/Dockerfile": b"y",
                                             "services/other/z": b"z"}, "app")
    finally:
        os.umask(old)
    modes = {str(p.relative_to(ctx)): oct(p.stat().st_mode & 0o777) for p in [ctx, *ctx.rglob("*")]}
    assert modes == {".": "0o755", "a": "0o755", "a/b.php": "0o644", "Dockerfile": "0o644"}


def test_mirror_ref():
    m = publish_service.mirror_ref
    assert m("mariadb:11.8", PREFIX) == f"{PREFIX}/mirror/mariadb:11.8"
    assert m("library/redis:8", PREFIX) == f"{PREFIX}/mirror/library/redis:8"
    assert m("nginx", PREFIX) == f"{PREFIX}/mirror/nginx:latest"
    assert m("localhost:5000/x:1", PREFIX) == "localhost:5000/x:1"
    with pytest.raises(BadRequest, match="digest"):
        m("nginx@sha256:" + "a" * 64, PREFIX)


def test_publish_success(db):
    challenge_service.create_challenge(db, "c1", "nginx-php-db", "C")
    ch = db.scalar(select(Challenge))
    before = challenge_service.current_hash(db, ch)
    run_id = publish_service.start_run(db, "c1")
    docker, ctfd = FakeDocker(), FakeCtfd()
    publish_service.run_publish(factory, run_id, "c1", docker, ctfd)
    db.expire_all()
    run = db.get(PublishRun, run_id)
    assert run.status == "succeeded" and run.finished_at and "step 1/1" in run.log
    assert (ch.ctfd_id, ch.published_hash) == (12, before)
    assert "flags" not in ctfd.created[0] and ctfd.created[0]["type"] == "dynamic_iac"
    assert ctfd.tags == [(12, [])]
    assert [c[0] for c in docker.calls].count("build") == 2 and ("pull", "mariadb:11.8") in docker.calls
    assert ("push", f"{PREFIX}/mirror/mariadb:11.8") in docker.calls


def test_publish_build_failure_stops(db):
    challenge_service.create_challenge(db, "c1", "php", "C")
    run_id = publish_service.start_run(db, "c1")
    ctfd = FakeCtfd()
    publish_service.run_publish(factory, run_id, "c1", FakeDocker(fail_build=True), ctfd)
    db.expire_all()
    run, ch = db.get(PublishRun, run_id), db.scalar(select(Challenge))
    assert run.status == "failed" and "boom" in run.log
    assert not (ctfd.created or ctfd.updated)
    assert ch.ctfd_id is None and ch.published_hash is None


def test_publish_recreates_when_ctfd_missing(db):
    challenge_service.create_challenge(db, "c1", "php", "C")
    db.scalar(select(Challenge)).ctfd_id = 7
    db.commit()
    run_id = publish_service.start_run(db, "c1")
    ctfd = FakeCtfd(missing=True)
    publish_service.run_publish(factory, run_id, "c1", FakeDocker(), ctfd)
    db.expire_all()
    assert db.scalar(select(Challenge)).ctfd_id == 12 and ctfd.created[0]["type"] == "dynamic_iac"


@pytest.mark.parametrize("start_id,missing", [(None, False), (7, True)])
def test_created_id_survives_set_tags_failure(db, start_id, missing):
    challenge_service.create_challenge(db, "c1", "php", "C")
    ch = db.scalar(select(Challenge))
    ch.ctfd_id = start_id
    db.commit()
    run1 = publish_service.start_run(db, "c1")
    publish_service.run_publish(factory, run1, "c1", FakeDocker(), FakeCtfd(missing=missing, tags_fail=True))
    db.expire_all()
    assert db.get(PublishRun, run1).status == "failed"
    assert (ch.ctfd_id, ch.published_hash) == (12, None)
    run2 = publish_service.start_run(db, "c1")
    ctfd = FakeCtfd()
    publish_service.run_publish(factory, run2, "c1", FakeDocker(), ctfd)
    db.expire_all()
    assert db.get(PublishRun, run2).status == "succeeded"
    assert ctfd.updated and not ctfd.created and ch.published_hash


@pytest.fixture
def api(client, db):
    client.headers.update(bearer(login(client).json()["token"]))
    app.dependency_overrides[deps.get_docker_ops] = lambda: FakeDocker()
    app.dependency_overrides[deps.get_ctfd_client] = lambda: FakeCtfd()
    yield client
    app.dependency_overrides.clear()


def test_publish_route_and_conflict(api, db):
    api.post("/challenges", json={"slug": "c1", "template": "php", "name": "C"})
    r = api.post("/challenges/c1/publish")
    assert r.status_code == 200
    run = api.get(f"/publish-runs/{r.json()['run_id']}").json()
    assert run["status"] == "succeeded" and run["finished_at"] and run["created_at"]
    assert api.get("/publish-runs/999").status_code == 404
    db.add(PublishRun(challenge_id=db.scalar(select(Challenge.id)), status="running"))
    db.commit()
    assert api.post("/challenges/c1/publish").status_code == 409
    assert api.post("/challenges/nope/publish").status_code == 404


def test_fail_interrupted(db):
    challenge_service.create_challenge(db, "c1", "php", "C")
    run_id = publish_service.start_run(db, "c1")
    publish_service.fail_interrupted(db)
    db.expire_all()
    run = db.get(PublishRun, run_id)
    assert run.status == "failed" and "restart" in run.log and run.finished_at


def test_delete_removes_ctfd_challenge(api, db):
    api.post("/challenges", json={"slug": "c1", "template": "php", "name": "C"})
    db.scalar(select(Challenge)).ctfd_id = 5
    db.commit()
    fake = FakeCtfd()
    app.dependency_overrides[deps.get_ctfd_client] = lambda: fake
    assert api.delete("/challenges/c1").status_code == 200
    assert fake.deleted == [5]
