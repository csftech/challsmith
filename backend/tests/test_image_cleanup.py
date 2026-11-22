from pathlib import Path

import httpx2 as httpx
import pytest

from app.clients import docker_client, registry_client
from app.services import image_cleanup_service as ics

HOSTS = {"localhost:5000", "registry:5000"}
KEEP = {"csftech/php-ext:*": "keep list", "php:8.6.0-cli-alpine3.24": "template base image", "mariadb:11.8": "template base image"}
L = "localhost:5000/challsmith/"


def decide(images=(), used=(), ctfd=(), tags=()):
    return ics.decide(list(images), set(used), set(ctfd), KEEP, list(tags), HOSTS)


def kept(p):
    return {r: why for why, refs in p.kept_images.items() for r in refs}


def kept_reg(p):
    return {r: why for why, refs in p.kept_registry.items() for r in refs}


def test_local_images_keep_and_remove():
    images = [
        ("sha256:a", "redis:8.10-alpine", 10),  # in use
        ("sha256:b", L + "hello-app:1", 20),  # CTFd
        ("sha256:c", "php:8.6.0-cli-alpine3.24", 30),  # template FROM
        ("sha256:d", "csftech/php-ext:8.6", 40),  # keep glob
        ("sha256:e", "", 50),  # dangling
        ("sha256:f", "challsmith/api-test:latest", 60),  # unknown
        ("sha256:g", L + "e2e-x-app:old", 70),  # old build, same image also tagged as kept below
        ("sha256:g", L + "hello-app:2", 70),
        ("sha256:h", L + "mirror/mariadb:11.8", 5),  # mirror of a template image
    ]
    p = decide(images, used={"sha256:a"}, ctfd={L + "hello-app:1", "registry:5000/challsmith/hello-app:2"})
    assert kept(p) == {
        "redis:8.10-alpine": "in use by a container",
        L + "hello-app:1": "CTFd challenge",
        L + "hello-app:2": "CTFd challenge",  # the other registry host names the same image
        "php:8.6.0-cli-alpine3.24": "template base image",
        "csftech/php-ext:8.6": "keep list",
        L + "mirror/mariadb:11.8": "template base image",
    }
    assert [i["ref"] for i in p.images] == ["", "challsmith/api-test:latest", L + "e2e-x-app:old"]
    assert p.reclaimable_bytes == 110  # g keeps another tag: untagging frees nothing


def test_in_use_beats_everything():
    p = decide([("sha256:a", "", 5), ("sha256:a", "x:1", 5)], used={"sha256:a"})
    assert p.images == [] and p.reclaimable_bytes == 0


def test_container_image_name_keeps_rebuilt_tag():
    # the ctfd container still runs the old id; the compose tag now names a newer build
    p = decide([("sha256:new", "challsmith/ctfd:3.8.9", 5)], used={"sha256:old", "challsmith/ctfd:3.8.9"})
    assert p.images == [] and kept(p) == {"challsmith/ctfd:3.8.9": "in use by a container"}


def test_registry_rules():
    tags = [
        ("challsmith/scenarios/single", "v1", "sha256:s"),
        ("challsmith/hello-app", "1", "sha256:k"),  # CTFd
        ("challsmith/hello-app", "0", "sha256:o"),  # old
        ("challsmith/copy-app", "1", "sha256:k"),  # same digest as a kept tag
        ("challsmith/gone-app", "abc", "sha256:g"),  # challenge deleted from the DB and CTFd
        ("challsmith/mirror/mariadb", "11.8", "sha256:m"),  # template image
        ("challsmith/mirror/nginx", "1.30", "sha256:n"),  # mirror nobody uses
        ("other/thing", "1", "sha256:x"),  # not ours
    ]
    p = decide(ctfd={L + "hello-app:1"}, tags=tags)
    assert [(t["repo"], t["tag"]) for t in p.registry] == [
        ("challsmith/hello-app", "0"), ("challsmith/gone-app", "abc"), ("challsmith/mirror/nginx", "1.30")]
    assert kept_reg(p) == {
        "challsmith/scenarios/single:v1": "scenario",
        "challsmith/hello-app:1": "CTFd challenge",
        "challsmith/copy-app:1": "same digest as a kept tag",
        "challsmith/mirror/mariadb:11.8": "template base image",
        "other/thing:1": "outside challsmith/",
    }


def test_scenarios_never_deleted_even_if_digest_unique():
    p = decide(tags=[("challsmith/scenarios/multi", "old", "sha256:z")])
    assert p.registry == []


def test_template_images(tmp_path: Path):
    (tmp_path / "t" / "app").mkdir(parents=True)
    (tmp_path / "t" / "app" / "Dockerfile").write_text(
        "ARG V=1\nFROM --platform=linux/amd64 node:26 AS build\nFROM python:${V}\nFROM scratch\nfrom alpine\n")
    (tmp_path / "t" / "template.yml").write_text("services:\n  - name: db\n    image: mariadb:11.8\n  - name: app\n")
    assert ics.template_images(tmp_path) == {"node:26", "alpine:latest", "mariadb:11.8"}


def test_repo_templates_resolve():
    images = ics.template_images(Path("/app/templates"))
    assert {"php:8.6.0-cli-alpine3.24", "mariadb:11.8", "alpine:3.24.4"} <= images


def test_ctfd_images():
    adds = [{"image": "a:1"}, {"services": '[{"name": "w", "image": "b:1"}, {"name": "x"}]'}, {}]
    assert ics.ctfd_images(adds) == {"a:1", "b:1"}
    with pytest.raises(ValueError):
        ics.ctfd_images([{"services": "not json"}])


class FakeDocker:
    def __init__(self, images=(), fail_gc=False):
        self.calls, self.images, self.fail_gc = [], list(images), fail_gc

    def list_images(self, log):
        return self.images

    def remove_image(self, ref, log):
        self.calls.append(("rm", ref))

    def prune(self, log):
        self.calls.append(("prune",))

    def compose_container(self, project, service, mount, log):
        return "cid", "registry:3", "challsmith_registry"

    def stop_container(self, cid, log):
        self.calls.append(("stop", cid))

    def start_container(self, cid, log):
        self.calls.append(("start", cid))

    def registry_gc(self, image, volume, config, log):
        self.calls.append(("gc", image, volume, config))
        if self.fail_gc:
            raise docker_client.DockerError("gc broke")


class FakeRegistry:
    def __init__(self, tags=()):
        self.tag_list, self.deleted = list(tags), []

    def catalog(self):
        return list(dict.fromkeys(r for r, _, _ in self.tag_list))

    def tags(self, repo):
        return [t for r, t, _ in self.tag_list if r == repo]

    def digest(self, repo, tag):
        return next(d for r, t, d in self.tag_list if (r, t) == (repo, tag))

    def delete(self, repo, digest):
        self.deleted.append((repo, digest))

    def ping(self):
        return True


def test_execute_deletes_each_digest_once_and_restarts_registry():
    p = ics.CleanupPlan(images=[{"ref": "x:1", "id": "a", "size": 1}, {"ref": "", "id": "b", "size": 2}],
                        registry=[{"repo": "challsmith/r", "tag": "1", "digest": "d"},
                                  {"repo": "challsmith/r", "tag": "2", "digest": "d"}], reclaimable_bytes=3)
    docker, registry = FakeDocker(), FakeRegistry()
    assert ics.execute(p, docker, registry, lambda _: None) == {"images": 2, "registry_tags": 2, "reclaimed_bytes": 3}
    assert registry.deleted == [("challsmith/r", "d")]
    assert docker.calls == [("rm", "x:1"), ("prune",), ("stop", "cid"),
                            ("gc", "registry:3", "challsmith_registry", "/etc/distribution/config.yml"), ("start", "cid")]


def test_gc_failure_still_restarts_registry():
    docker = FakeDocker(fail_gc=True)
    with pytest.raises(docker_client.DockerError):
        ics.garbage_collect(docker, FakeRegistry(), lambda _: None)
    assert docker.calls[-1] == ("start", "cid")


def test_remove_repos_keeps_shared_digest():
    docker = FakeDocker([("a", L + "gone-app:1", 1), ("b", L + "keep-app:1", 1), ("c", "", 1)])
    registry = FakeRegistry([("challsmith/gone-app", "1", "d1"), ("challsmith/gone-app", "2", "shared"),
                             ("challsmith/keep-app", "1", "shared")])
    ics.remove_repos(docker, registry, {"challsmith/gone-app"}, lambda _: None)
    assert docker.calls == [("rm", L + "gone-app:1")]
    assert registry.deleted == [("challsmith/gone-app", "d1")]


# registry_client over a mock transport


def test_registry_client_digest_tags_delete():
    seen = []

    def handler(req: httpx.Request):
        seen.append((req.method, req.url.path))
        if req.url.path == "/v2/_catalog":
            if "last" in str(req.url):
                return httpx.Response(200, json={"repositories": ["b"]})
            return httpx.Response(200, json={"repositories": ["a"]}, headers={"Link": '</v2/_catalog?last=a&n=1>; rel="next"'})
        if req.url.path == "/v2/a/tags/list":
            return httpx.Response(200, json={"name": "a", "tags": None})
        if req.method == "HEAD":
            assert "application/vnd.oci.image.index.v1+json" in req.headers["Accept"]
            if req.url.path.endswith("/missing"):
                return httpx.Response(404)
            return httpx.Response(200, headers={"Docker-Content-Digest": "sha256:abc"})
        if req.method == "DELETE":
            return httpx.Response(202)
        return httpx.Response(200)

    r = registry_client.RegistryClient("http://registry:5000", transport=httpx.MockTransport(handler))
    assert r.catalog() == ["a", "b"]
    assert r.tags("a") == []
    assert r.digest("a", "1") == "sha256:abc" and r.digest("a", "missing") is None
    r.delete("a", "sha256:abc")
    assert seen[-1] == ("DELETE", "/v2/a/manifests/sha256:abc")
    assert r.ping()


def test_registry_client_delete_disabled_raises():
    r = registry_client.RegistryClient("http://r", transport=httpx.MockTransport(lambda req: httpx.Response(405)))
    with pytest.raises(registry_client.RegistryError, match="405"):
        r.delete("a", "sha256:x")


# docker_client parsing


def test_docker_list_images_and_container_images(monkeypatch):
    out = {
        "images": ["sha256:a\tredis\t8", "sha256:b\t<none>\t<none>", "sha256:a\tlocalhost:5000/x\t1"],
        "image": ["sha256:a\t100", "sha256:b\t7"],
        "ps": ["c1", "c2"],
        "inspect": ["sha256:a\tredis:8", "sha256:c\tregistry:3"],
    }
    d = docker_client.DockerOps()
    monkeypatch.setattr(d, "_run", lambda cmd, log, shown=None, quiet=False: out[cmd[1]])
    assert d.list_images(print) == [("sha256:a", "redis:8", 100), ("sha256:b", "", 7), ("sha256:a", "localhost:5000/x:1", 100)]
    assert d.container_images(print) == {"sha256:a", "redis:8", "sha256:c", "registry:3"}


def test_docker_remove_image_never_forces(monkeypatch):
    cmds = []
    d = docker_client.DockerOps()
    monkeypatch.setattr(d, "_run", lambda cmd, log, shown=None, quiet=False: cmds.append(cmd) or [])
    d.remove_image("x:1", print)
    d.prune(print)
    assert cmds[0] == ["docker", "image", "rm", "--", "x:1"]
    assert ["docker", "volume", "prune", "-f"] in cmds
    assert not any("-a" in c for c in cmds if c[1] == "volume") and not any("-f" in c for c in cmds if c[2] == "rm")


def test_docker_compose_container(monkeypatch):
    d = docker_client.DockerOps()
    out = {"ps": ["cid"], "inspect": ["registry:3\tchallsmith_registry"]}
    monkeypatch.setattr(d, "_run", lambda cmd, log, shown=None, quiet=False: out[cmd[1]])
    assert d.compose_container("challsmith", "registry", "/var/lib/registry", print) == ("cid", "registry:3", "challsmith_registry")
    out["ps"] = []
    with pytest.raises(docker_client.DockerError):
        d.compose_container("challsmith", "registry", "/var/lib/registry", print)
