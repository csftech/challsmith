"""Fixtures and helpers for the challsmith end-to-end tests (CTFd + ctfd-chall-manager)."""
import os
import re
import secrets
import time

import pytest
import requests

CTFD = os.environ.get("CTFD_URL", "http://127.0.0.1:8000")
INSTANCE_TIMEOUT = 300  # Pulumi run + image pull


def nonce(session, path):
    html = session.get(CTFD + path).text
    m = re.search(r"csrfNonce': \"([0-9a-f]+)\"", html)
    assert m, f"no csrfNonce on {path}"
    return m.group(1)


def check(r):
    assert r.ok, f"{r.request.method} {r.url} -> {r.status_code}: {r.text[:500]}"
    return r.json()


@pytest.fixture(scope="session")
def admin():
    s = requests.Session()
    r = s.post(CTFD + "/login", data={
        "name": os.environ["CTFD_ADMIN_NAME"],
        "password": os.environ["CTFD_ADMIN_PASSWORD"],
        "nonce": nonce(s, "/login"),
    }, allow_redirects=False)
    assert r.status_code == 302, "admin login failed"
    s.headers["CSRF-Token"] = nonce(s, "/challenges")
    token = check(s.post(CTFD + "/api/v1/tokens", json={"description": "e2e"}))["data"]
    api = requests.Session()
    api.headers["Authorization"] = "Token " + token["value"]
    yield api
    api.delete(f"{CTFD}/api/v1/tokens/{token['id']}")


@pytest.fixture
def register_user(admin):
    ids = []

    def register(name):
        s = requests.Session()
        name = f"e2e-{name}-{secrets.token_hex(3)}"
        r = s.post(CTFD + "/register", data={
            "name": name, "email": name + "@example.com",
            "password": secrets.token_hex(12), "nonce": nonce(s, "/register"),
        }, allow_redirects=False)
        assert r.status_code == 302, f"register {name} failed"
        s.headers["CSRF-Token"] = nonce(s, "/challenges")  # login regenerates the session nonce
        ids.append(check(s.get(CTFD + "/api/v1/users/me"))["data"]["id"])
        return s

    yield register
    for uid in ids:
        check(admin.delete(f"{CTFD}/api/v1/users/{uid}"))


@pytest.fixture
def create_challenge(admin):
    ids = []

    def create(name, scenario, additional):
        data = check(admin.post(CTFD + "/api/v1/challenges", json={
            "name": f"e2e-{name}-{secrets.token_hex(3)}", "category": "e2e",
            "description": "challsmith end-to-end test", "type": "dynamic_iac",
            "function": "linear", "initial": 100, "minimum": 100, "decay": 0,
            "state": "visible", "scenario": scenario, "additional": additional,
            "mana_cost": 1, "timeout": 600,
        }, timeout=INSTANCE_TIMEOUT))["data"]
        ids.append(data["id"])
        return data["id"]

    yield create
    for cid in ids:  # deleting the challenge also destroys its instances in chall-manager
        check(admin.delete(f"{CTFD}/api/v1/challenges/{cid}", timeout=INSTANCE_TIMEOUT))


def start_instance(user, challenge_id):
    """Start the user's instance and return its connectionInfo."""
    url = CTFD + "/api/v1/plugins/ctfd-chall-manager/instance"
    r = user.post(url, json={"challengeId": str(challenge_id)}, timeout=INSTANCE_TIMEOUT)
    data = check(r)
    assert data["success"], data
    deadline = time.time() + INSTANCE_TIMEOUT
    while not data.get("data", {}).get("connectionInfo"):
        assert time.time() < deadline, f"no connectionInfo for challenge {challenge_id}"
        time.sleep(3)
        data = check(user.get(url, params={"challengeId": challenge_id}))
    return data["data"]["connectionInfo"]


def submit(user, challenge_id, flag):
    r = user.post(CTFD + "/api/v1/challenges/attempt",
                  json={"challenge_id": challenge_id, "submission": flag})
    return check(r)["data"]["status"]


def get_until(url, needle, timeout=60):
    """GET url until the body contains needle; return the body."""
    deadline = time.time() + timeout
    while True:
        try:
            body = requests.get(url, timeout=40).text
            if needle in body:
                return body
        except requests.RequestException:
            body = None
        assert time.time() < deadline, f"{url} never returned {needle!r}, last: {body!r}"
        time.sleep(2)
