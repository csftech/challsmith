import httpx2 as httpx
import pytest
from sqlalchemy import func, select

from app.api import deps
from app.clients import chall_manager_client
from app.main import app
from app.models import Challenge, WebSession
from app.services import challenge_service, cleanup_service
from app.services.errors import BadGateway
from test_auth import admin_env, bearer, login  # noqa: F401  (fixture reused)


class FakeCm:
    def __init__(self):
        self.deleted = []

    def list_instances(self):
        return [("c1", "u1"), ("c1", "u2"), ("c2", "u1")]

    def delete_instance(self, cid, sid):
        self.deleted.append((cid, sid))


class FakeCtfd:
    def __init__(self, fail=False):
        self.deleted, self.fail = [], fail

    def list_users(self):
        return [{"id": 1}, {"id": 2}, {"id": 3}]  # the real list view has no "type"

    def get_user(self, uid):
        return {"id": uid, "type": "admin" if uid == 1 else "user"}

    def delete_user(self, uid):
        if self.fail:
            raise RuntimeError("ctfd down")
        self.deleted.append(uid)

    def list_iac_additional(self):
        return [{"image": "localhost:5000/challsmith/live-app:1"}]


class FakeDocker:
    def __init__(self):
        self.calls = []

    def remove_containers(self, prefix, log):
        self.calls.append(("containers", prefix))
        return 2

    def remove_networks(self, prefix, log):
        self.calls.append(("networks", prefix))
        return 1

    def list_images(self, log):
        return [("sha256:a", "localhost:5000/challsmith/live-app:1", 5), ("sha256:b", "localhost:5000/challsmith/old-app:1", 7)]

    def container_images(self, log):
        return set()

    def remove_image(self, ref, log):
        self.calls.append(("rm", ref))

    def prune(self, log):
        self.calls.append(("prune",))

    def compose_container(self, project, service, mount, log):
        return "cid", "registry:3", "vol"

    def stop_container(self, cid, log):
        self.calls.append(("stop", cid))

    def start_container(self, cid, log):
        self.calls.append(("start", cid))

    def registry_gc(self, image, volume, config, log):
        self.calls.append(("gc",))


class FakeRegistry:
    def __init__(self):
        self.deleted = []

    def catalog(self):
        return ["challsmith/live-app", "challsmith/old-app"]

    def tags(self, repo):
        return ["1"]

    def digest(self, repo, tag):
        return "sha256:" + repo

    def delete(self, repo, digest):
        self.deleted.append(repo)

    def ping(self):
        return True

    def close(self):
        pass


IMAGE_STEP = [("rm", "localhost:5000/challsmith/old-app:1"), ("prune",), ("stop", "cid"), ("gc",), ("start", "cid")]


def test_run_cleanup(db):
    challenge_service.create_challenge(db, "c1", "php", "C")
    db.add(WebSession(token_hash="x", expires_at=db.scalar(select(func.now()))))
    db.commit()
    cm, ctfd, docker, registry, lines = FakeCm(), FakeCtfd(), FakeDocker(), FakeRegistry(), []
    out = cleanup_service.run_cleanup(db, cm, ctfd, docker, registry, lines.append)
    assert out == {"instances": 3, "containers": 2, "networks": 1, "users": 2, "sessions": 1,
                   "images": 1, "registry_tags": 1, "reclaimed_bytes": 7}
    assert len(cm.deleted) == 3 and ctfd.deleted == [2, 3]
    assert docker.calls == [("containers", "challenge-"), ("networks", "challenge-"), *IMAGE_STEP]
    assert registry.deleted == ["challsmith/old-app"]
    assert db.scalar(select(func.count()).select_from(WebSession)) == 0
    assert db.scalar(select(func.count()).select_from(Challenge)) == 1


def test_reset_instances_only_touches_instances(db):
    cm, docker = FakeCm(), FakeDocker()
    assert cleanup_service.reset_instances(cm, docker, lambda _: None) == (3, 2, 1)
    assert len(cm.deleted) == 3
    assert docker.calls == [("containers", "challenge-"), ("networks", "challenge-")]


def test_cli_instances_only_never_touches_ctfd_or_sessions(monkeypatch, capsys):
    from app.cli import cleanup as cli

    cm, docker = FakeCm(), FakeDocker()

    class Boom:
        def __init__(self, *a):
            raise AssertionError("ctfd must not be used")

    class S:
        chall_manager_url = ctfd_url = "http://x"
        ctfd_admin_name = ctfd_admin_password = "x"
        upstream_http_proxy = upstream_https_proxy = upstream_no_proxy = ""

    cm.close = lambda: None
    monkeypatch.setattr(cli, "get_settings", lambda: S)
    monkeypatch.setattr(cli.chall_manager_client, "ChallManager", lambda url: cm)
    monkeypatch.setattr(cli.ctfd_client, "CtfdClient", Boom)
    monkeypatch.setattr(cli.docker_client, "DockerOps", lambda *a: docker)
    monkeypatch.setattr(cli, "get_engine", lambda: (_ for _ in ()).throw(AssertionError("no db")))
    assert cli.main(["--instances-only", "--yes"]) == 0
    assert len(cm.deleted) == 3 and docker.calls == [("containers", "challenge-"), ("networks", "challenge-")]


def test_run_cleanup_never_deletes_when_user_lookup_fails(db):
    class Broken(FakeCtfd):
        def get_user(self, uid):
            raise RuntimeError("lookup failed")

    ctfd = Broken()
    with pytest.raises(BadGateway, match="lookup failed"):
        cleanup_service.run_cleanup(db, FakeCm(), ctfd, FakeDocker(), FakeRegistry(), lambda _: None)
    assert ctfd.deleted == []


def test_run_cleanup_stops_on_failure(db):
    db.add(WebSession(token_hash="x", expires_at=db.scalar(select(func.now()))))
    db.commit()
    lines = []
    with pytest.raises(BadGateway, match="ctfd down"):
        cleanup_service.run_cleanup(db, FakeCm(), FakeCtfd(fail=True), FakeDocker(), FakeRegistry(), lines.append)
    assert db.scalar(select(func.count()).select_from(WebSession)) == 1
    assert any("instances" in line for line in lines)


@pytest.fixture
def api(client, db):
    client.headers.update(bearer(login(client).json()["token"]))
    app.dependency_overrides[deps.get_chall_manager] = lambda: FakeCm()
    app.dependency_overrides[deps.get_ctfd_client] = lambda: FakeCtfd()
    app.dependency_overrides[deps.get_docker_ops] = lambda: FakeDocker()
    app.dependency_overrides[deps.get_registry_client] = lambda: FakeRegistry()
    yield client
    app.dependency_overrides.clear()


def test_cleanup_route_bad_confirm_touches_nothing(api):
    cm, ctfd, docker = FakeCm(), FakeCtfd(), FakeDocker()
    app.dependency_overrides[deps.get_chall_manager] = lambda: cm
    app.dependency_overrides[deps.get_ctfd_client] = lambda: ctfd
    app.dependency_overrides[deps.get_docker_ops] = lambda: docker
    assert api.post("/cleanup", json={"confirm": "nope"}).status_code == 400
    assert not (cm.deleted or ctfd.deleted or docker.calls)


def test_cleanup_route_ok(api):
    docker, registry = FakeDocker(), FakeRegistry()
    app.dependency_overrides[deps.get_docker_ops] = lambda: docker
    app.dependency_overrides[deps.get_registry_client] = lambda: registry
    r = api.post("/cleanup", json={"confirm": "CLEANUP"})
    assert r.status_code == 200 and r.json()["users"] == 2 and r.json()["sessions"] == 1
    assert r.json()["images"] == 1 and r.json()["registry_tags"] == 1 and r.json()["reclaimed_bytes"] == 7
    assert docker.calls[2:] == IMAGE_STEP and registry.deleted == ["challsmith/old-app"]
    assert api.get("/auth/me").status_code == 401


def test_run_cleanup_image_step_failure_is_reported(db):
    class NoGc(FakeDocker):
        def registry_gc(self, image, volume, config, log):
            raise RuntimeError("gc broke")

    docker = NoGc()
    with pytest.raises(BadGateway, match="gc broke"):
        cleanup_service.run_cleanup(db, FakeCm(), FakeCtfd(), docker, FakeRegistry(), lambda _: None)
    assert docker.calls[-1] == ("start", "cid")


def test_image_plan_route(api):
    r = api.get("/cleanup/images")
    assert r.status_code == 200
    body = r.json()
    assert [i["ref"] for i in body["images"]] == ["localhost:5000/challsmith/old-app:1"]
    assert body["registry"] == [{"repo": "challsmith/old-app", "tag": "1", "digest": "sha256:challsmith/old-app"}]
    assert body["kept_images"] == {"CTFd challenge": ["localhost:5000/challsmith/live-app:1"]}
    assert body["reclaimable_bytes"] == 7


def test_image_plan_route_requires_session(client):
    assert client.get("/cleanup/images").status_code == 401


def test_cli_dry_run_changes_nothing(monkeypatch, capsys):
    from app.cli import cleanup as cli

    docker, registry = FakeDocker(), FakeRegistry()
    monkeypatch.setattr(cli.ctfd_client, "CtfdClient", lambda *a: FakeCtfd())
    monkeypatch.setattr(cli.docker_client, "DockerOps", lambda *a: docker)
    monkeypatch.setattr(cli.registry_client, "RegistryClient", lambda *a: registry)
    assert cli.main(["--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "localhost:5000/challsmith/old-app:1" in out and "Registry tags to remove: 1" in out
    assert docker.calls == [] and registry.deleted == []


def stream(lines, status=200):
    return httpx.MockTransport(lambda req: httpx.Response(status, text=lines))


def test_list_instances_parses_stream():
    body = (
        '{"result": {"id": "a", "instances": [{"challengeId": "a", "sourceId": "1"}, {"challengeId": "a", "sourceId": "2"}]}}\n'
        '{"result": {"id": "b"}}\n'
    )
    cm = chall_manager_client.ChallManager("http://cm", transport=stream(body))
    assert cm.list_instances() == [("a", "1"), ("a", "2")]


def test_list_instances_error_line_raises():
    cm = chall_manager_client.ChallManager("http://cm", transport=stream('{"error": {"message": "bad"}}\n'))
    with pytest.raises(chall_manager_client.ChallManagerError, match="bad"):
        cm.list_instances()


def test_delete_instance_404_ok_and_500_raises():
    chall_manager_client.ChallManager("http://cm", transport=stream("", 404)).delete_instance("a", "1")
    with pytest.raises(chall_manager_client.ChallManagerError):
        chall_manager_client.ChallManager("http://cm", transport=stream("", 500)).delete_instance("a", "1")
