import json

import httpx2 as httpx
import pytest

from app.clients import ctfd_client

LOGIN_PAGE = "<script>init = {'csrfNonce': \"abc123\"}</script>"


def make(handler):
    return ctfd_client.CtfdClient("http://ctfd", "admin", "pw", transport=httpx.MockTransport(handler))


def ok_login(calls, extra=None):
    def handler(req: httpx.Request):
        calls.append((req.method, req.url.path, req.headers.get("csrf-token")))
        if req.url.path in ("/login", "/challenges") and req.method == "GET":
            return httpx.Response(200, text=LOGIN_PAGE)
        if req.url.path == "/login":
            return httpx.Response(302, headers={"location": "/"})
        return extra(req)

    return handler


def test_login_without_nonce_fails():
    c = make(lambda r: httpx.Response(200, text="nothing"))
    with pytest.raises(ctfd_client.CtfdError, match="CTFD_ADMIN_NAME"):
        c.delete_challenge(1)


def test_login_wrong_password_fails():
    def h(req):
        return httpx.Response(200, text=LOGIN_PAGE)  # CTFd re-renders the form on bad credentials

    with pytest.raises(ctfd_client.CtfdError, match="CTFD_ADMIN_PASSWORD"):
        make(h).delete_challenge(1)


def test_csrf_header_and_not_found():
    calls = []
    c = make(ok_login(calls, lambda r: httpx.Response(404, json={"success": False})))
    with pytest.raises(ctfd_client.CtfdNotFound):
        c.update_challenge(5, {"name": "x"})
    assert calls[-1] == ("PATCH", "/api/v1/challenges/5", "abc123")


def test_set_tags_diff():
    calls = []

    def extra(req):
        if req.method == "GET":
            return httpx.Response(200, json={"data": [{"id": 1, "value": "a"}, {"id": 2, "value": "b"}]})
        if req.method == "POST":
            calls.append(("add", json.loads(req.content)["value"]))
        else:
            calls.append(("del", req.url.path))
        return httpx.Response(200, json={"success": True})

    make(ok_login([], extra)).set_tags(9, ["b", "c"])
    assert calls == [("del", "/api/v1/tags/1"), ("add", "c")]


def test_list_users_follows_pages():
    def extra(req):
        page = int(req.url.params.get("page", "1"))
        nxt = 2 if page == 1 else None
        return httpx.Response(200, json={"data": [{"id": page}], "meta": {"pagination": {"next": nxt}}})

    assert make(ok_login([], extra)).list_users() == [{"id": 1}, {"id": 2}]


def test_set_config_patches_configs():
    calls, bodies = [], []
    make(ok_login(calls, lambda r: (bodies.append(json.loads(r.content)), httpx.Response(200, json={"success": True}))[1])).set_config("chall-manager:chall-manager_mana_total", 0)
    assert ("PATCH", "/api/v1/configs", "abc123") in calls
    assert bodies == [{"chall-manager:chall-manager_mana_total": 0}]


def iac_client(listed, details):
    def extra(req):
        if req.url.path == "/api/v1/challenges":
            return httpx.Response(200, json={"success": True, "data": listed})
        cid = int(req.url.path.rsplit("/", 1)[1])
        return httpx.Response(200, json={"success": True, "data": details[cid]})

    return make(ok_login([], extra))


def test_list_iac_additional():
    c = iac_client([{"id": 1, "type": "dynamic_iac"}, {"id": 2, "type": "standard"}], {1: {"additional": {"image": "a:1"}}})
    assert c.list_iac_additional() == [{"image": "a:1"}]


@pytest.mark.parametrize("listed, details", [
    ([{"id": 1}], {}),  # no type
    ([{"id": 1, "type": "dynamic_iac"}], {1: {"name": "x"}}),  # no additional
])
def test_list_iac_additional_fails_closed(listed, details):
    with pytest.raises(ctfd_client.CtfdError):
        iac_client(listed, details).list_iac_additional()
