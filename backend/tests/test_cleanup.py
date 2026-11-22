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


class FakeDocker:
    def __init__(self):
        self.calls = []

    def remove_containers(self, prefix, log):
        self.calls.append(("containers", prefix))
        return 2

    def remove_networks(self, prefix, log):
        self.calls.append(("networks", prefix))
        return 1


def test_run_cleanup(db):
    challenge_service.create_challenge(db, "c1", "php", "C")
    db.add(WebSession(token_hash="x", expires_at=db.scalar(select(func.now()))))
    db.commit()
    cm, ctfd, docker, lines = FakeCm(), FakeCtfd(), FakeDocker(), []
    out = cleanup_service.run_cleanup(db, cm, ctfd, docker, lines.append)
    assert out == {"instances": 3, "containers": 2, "networks": 1, "users": 2, "sessions": 1}
    assert len(cm.deleted) == 3 and ctfd.deleted == [2, 3]
    assert docker.calls == [("containers", "challenge-"), ("networks", "challenge-")]
    assert db.scalar(select(func.count()).select_from(WebSession)) == 0
    assert db.scalar(select(func.count()).select_from(Challenge)) == 1


def test_run_cleanup_stops_on_failure(db):
    db.add(WebSession(token_hash="x", expires_at=db.scalar(select(func.now()))))
    db.commit()
    lines = []
    with pytest.raises(BadGateway, match="ctfd down"):
        cleanup_service.run_cleanup(db, FakeCm(), FakeCtfd(fail=True), FakeDocker(), lines.append)
    assert db.scalar(select(func.count()).select_from(WebSession)) == 1
    assert any("instances" in line for line in lines)


@pytest.fixture
def api(client, db):
    client.headers.update(bearer(login(client).json()["token"]))
    app.dependency_overrides[deps.get_chall_manager] = lambda: FakeCm()
    app.dependency_overrides[deps.get_ctfd_client] = lambda: FakeCtfd()
    app.dependency_overrides[deps.get_docker_ops] = lambda: FakeDocker()
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
    r = api.post("/cleanup", json={"confirm": "CLEANUP"})
    assert r.status_code == 200 and r.json()["users"] == 2 and r.json()["sessions"] == 1
    assert api.get("/auth/me").status_code == 401


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
