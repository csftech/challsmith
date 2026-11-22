"""Pre-release cleanup. Runs in its own pytest invocation, last: it deletes every non-admin user and all web sessions."""
import secrets

from conftest import CTFD, WEB, check, nonce, start_instance, web_login
import requests

SCENARIO = "registry:5000/challsmith/scenarios/single:v1"
HELLO_PHP = {"image": "localhost:5000/challsmith/examples/hello-php:test", "port": "80", "flag": "hello_php"}


def test_cleanup(admin, create_challenge):
    web = web_login()  # its own session: the cleanup invalidates it
    name = f"e2e-cleanup-{secrets.token_hex(3)}"
    password = secrets.token_hex(12)
    check(admin.post(CTFD + "/api/v1/users", json={"name": name, "email": name + "@example.com",
                                                   "password": password, "verified": True}))
    user = requests.Session()
    r = user.post(CTFD + "/login", data={"name": name, "password": password, "nonce": nonce(user, "/login")},
                  allow_redirects=False)
    assert r.status_code == 302
    user.headers["CSRF-Token"] = nonce(user, "/challenges")
    start_instance(user, create_challenge("cleanup", SCENARIO, HELLO_PHP))

    out = check(web.post(f"{WEB}/api/cleanup", json={"confirm": "CLEANUP"}, timeout=300))
    assert out["instances"] >= 1 and out["users"] >= 1

    found = check(admin.get(CTFD + "/api/v1/users", params={"q": name, "field": "name"}))["data"]
    assert not found
    assert web.get(f"{WEB}/api/challenges").status_code == 401
