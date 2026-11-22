import json

import httpx2 as httpx


class ChallManagerError(Exception):
    pass


class ChallManager:
    """chall-manager REST gateway. Instance deletion runs Pulumi destroy, hence the long timeout."""

    def __init__(self, base_url: str, transport=None):
        self._http = httpx.Client(base_url=base_url, transport=transport, timeout=60)

    def close(self) -> None:
        self._http.close()

    def list_instances(self) -> list[tuple[str, str]]:
        # GET /api/v1/instance without source_id returns nothing (verified on v0.6.7); the challenge
        # store embeds every challenge's instances instead.
        r = self._http.get("/api/v1/challenge")
        if not r.is_success:
            raise ChallManagerError(f"list challenges -> {r.status_code}: {r.text[:500]}")
        out = []
        for line in r.text.splitlines():
            if not line.strip():
                continue
            msg = json.loads(line)
            if "error" in msg:
                raise ChallManagerError(f"list challenges: {msg['error'].get('message', msg['error'])}")
            out += [(i["challengeId"], i["sourceId"]) for i in msg["result"].get("instances", [])]
        return out

    def delete_instance(self, challenge_id: str, source_id: str) -> None:
        r = self._http.delete(f"/api/v1/instance/{challenge_id}/{source_id}")
        if r.status_code != 404 and not r.is_success:
            raise ChallManagerError(f"delete instance {challenge_id}/{source_id} -> {r.status_code}: {r.text[:500]}")
