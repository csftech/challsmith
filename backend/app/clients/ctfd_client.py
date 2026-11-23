import re
import threading

import httpx2 as httpx

NONCE_RE = re.compile(r"csrfNonce': \"([0-9a-f]+)\"")


class CtfdError(Exception):
    pass


class CtfdNotFound(CtfdError):
    pass


class CtfdClient:
    """CTFd admin API over the web login session (no API token is created). Logs in lazily."""

    def __init__(self, base_url: str, name: str, password: str, transport=None):
        self._http = httpx.Client(base_url=base_url, transport=transport, timeout=30)
        self._name, self._password = name, password
        self._ready = False
        self._lock = threading.Lock()  # sync routes run in a threadpool and share this client

    def _nonce(self, path: str) -> str:
        m = NONCE_RE.search(self._http.get(path).text)
        if not m:
            raise CtfdError(f"no csrfNonce on {path}; check that CTFD_URL points to CTFd and that CTFD_ADMIN_NAME and CTFD_ADMIN_PASSWORD match the CTFd admin")
        return m.group(1)

    def _login(self) -> None:
        r = self._http.post("/login", data={"name": self._name, "password": self._password, "nonce": self._nonce("/login")})
        if r.status_code == 429:
            raise CtfdError("CTFd refused the login: too many attempts (429), wait a few seconds")
        if r.status_code != 302:
            raise CtfdError("CTFd login failed: CTFD_ADMIN_NAME and CTFD_ADMIN_PASSWORD must match the CTFd admin account")
        self._http.headers["CSRF-Token"] = self._nonce("/challenges")  # login regenerates the session nonce
        self._ready = True

    def _ensure_login(self, stale: bool = False) -> None:
        with self._lock:
            if stale:
                self._ready = False  # callers that raced here re-login once each at worst
            if not self._ready:
                self._login()

    def _api(self, method: str, path: str, timeout: float = 30, **kw) -> dict:
        try:
            self._ensure_login()
            for attempt in (0, 1):
                # CTFd rejects session-authenticated writes whose content type is not JSON, DELETE included
                r = self._http.request(method, "/api/v1" + path, timeout=timeout, headers={"Content-Type": "application/json"}, **kw)
                # an expired session answers 401/403 (or redirects to /login): log in again, retry once
                if attempt == 0 and (r.status_code in (401, 403) or (r.status_code == 302 and "/login" in r.headers.get("location", ""))):
                    self._ensure_login(stale=True)
                    continue
                break
        except httpx.HTTPError as e:
            raise CtfdError(f"{method} {path}: {e}") from e
        if r.status_code == 404:
            raise CtfdNotFound(f"{method} {path} -> 404")
        if r.status_code == 429:
            raise CtfdError(f"{method} {path} -> 429: CTFd is rate limiting requests")
        if not r.is_success:
            raise CtfdError(f"{method} {path} -> {r.status_code}: {r.text[:500]}")
        return r.json()

    # chall-manager validates the scenario inside the CTFd request, hence the long timeout
    def create_challenge(self, payload: dict) -> int:
        return self._api("POST", "/challenges", 300, json=payload)["data"]["id"]

    def update_challenge(self, cid: int, payload: dict) -> None:
        self._api("PATCH", f"/challenges/{cid}", 300, json=payload)

    def list_positions(self) -> dict[int, tuple[int, int]]:
        """id -> (position, value) of every CTFd challenge, hidden ones included."""
        return {c["id"]: (c["position"], c["value"]) for c in self._api("GET", "/challenges", params={"view": "admin"})["data"]}

    def set_position(self, cid: int, position: int) -> None:
        self._api("PATCH", f"/challenges/{cid}", json={"position": position})

    def delete_challenge(self, cid: int) -> None:
        self._api("DELETE", f"/challenges/{cid}", 300)

    def set_tags(self, cid: int, tags: list[str]) -> None:
        have = {t["value"]: t["id"] for t in self._api("GET", f"/challenges/{cid}/tags")["data"]}
        for value, tid in have.items():
            if value not in tags:
                self._api("DELETE", f"/tags/{tid}")
        for value in tags:
            if value not in have:
                self._api("POST", "/tags", json={"challenge_id": cid, "value": value})

    def list_users(self) -> list[dict]:
        users, page = [], 1
        while page:
            body = self._api("GET", "/users", params={"page": page})
            users += body["data"]
            page = body["meta"]["pagination"]["next"]
        return users

    def get_user(self, uid: int) -> dict:  # the list view has no "type"
        return self._api("GET", f"/users/{uid}")["data"]

    def delete_user(self, uid: int) -> None:
        self._api("DELETE", f"/users/{uid}")

    def set_config(self, key: str, value) -> None:
        self._api("PATCH", "/configs", json={key: value})

    def list_iac_additional(self) -> list[dict]:
        """`additional` of every dynamic_iac challenge, hidden ones included (only the admin detail view has it)."""
        out = []
        for c in self._api("GET", "/challenges", params={"view": "admin"})["data"]:
            if "type" not in c:  # cannot tell whether it runs images: fail rather than miss them
                raise CtfdError(f"CTFd challenge {c.get('id')} has no type")
            if c["type"] != "dynamic_iac":
                continue
            detail = self._api("GET", f"/challenges/{c['id']}", params={"view": "admin"})["data"]
            if not isinstance(detail.get("additional"), dict):
                raise CtfdError(f"CTFd challenge {c['id']} has no additional")
            out.append(detail["additional"])
        return out
