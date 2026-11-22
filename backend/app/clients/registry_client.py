import httpx2 as httpx

# every manifest type the registry may hold; Docker-Content-Digest is only right when the stored type is accepted
ACCEPT = ", ".join([
    "application/vnd.oci.image.index.v1+json",
    "application/vnd.oci.image.manifest.v1+json",
    "application/vnd.docker.distribution.manifest.list.v2+json",
    "application/vnd.docker.distribution.manifest.v2+json",
])


class RegistryError(Exception):
    pass


class RegistryClient:
    """Docker registry HTTP API v2 of the local registry."""

    def __init__(self, base_url: str, transport=None):
        self._http = httpx.Client(base_url=base_url, transport=transport, timeout=30)

    def close(self) -> None:
        self._http.close()

    def ping(self) -> bool:
        try:
            return self._http.get("/v2/", timeout=5).status_code == 200
        except httpx.HTTPError:
            return False

    def _pages(self, path: str, key: str) -> list[str]:
        out, url = [], path
        while url:
            r = self._http.get(url)
            if r.status_code == 404:
                return out
            if not r.is_success:
                raise RegistryError(f"GET {url} -> {r.status_code}: {r.text[:300]}")
            out += r.json().get(key) or []
            url = r.links.get("next", {}).get("url")
        return out

    def catalog(self) -> list[str]:
        return self._pages("/v2/_catalog", "repositories")

    def tags(self, repo: str) -> list[str]:
        return self._pages(f"/v2/{repo}/tags/list", "tags")

    def digest(self, repo: str, tag: str) -> str | None:
        r = self._http.head(f"/v2/{repo}/manifests/{tag}", headers={"Accept": ACCEPT})
        if r.status_code == 404:
            return None
        digest = r.headers.get("Docker-Content-Digest")
        if not r.is_success or not digest:
            raise RegistryError(f"HEAD {repo}:{tag} -> {r.status_code}, digest {digest!r}")
        return digest

    def delete(self, repo: str, digest: str) -> None:
        r = self._http.delete(f"/v2/{repo}/manifests/{digest}")
        if r.status_code not in (202, 404):
            raise RegistryError(f"DELETE {repo}@{digest} -> {r.status_code}: {r.text[:300]}")
