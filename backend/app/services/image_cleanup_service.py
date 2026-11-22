"""Unused Docker images and local-registry tags: decide what goes (pure), then remove it."""
import fnmatch
import json
import re
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from app.core.config import get_settings

OWNED = "challsmith/"  # registry repos this app may delete from
SCENARIOS = "challsmith/scenarios/"
MIRROR = "challsmith/mirror/"
GC_CONFIG = "/etc/distribution/config.yml"  # registry:3 default config
FROM_RE = re.compile(r"^\s*FROM\s+(.+)$", re.IGNORECASE | re.MULTILINE)


@dataclass
class CleanupPlan:
    images: list[dict] = field(default_factory=list)  # {"ref", "id", "size"}; ref "" = dangling
    registry: list[dict] = field(default_factory=list)  # {"repo", "tag", "digest"}
    kept_images: dict[str, list[str]] = field(default_factory=dict)  # reason -> refs
    kept_registry: dict[str, list[str]] = field(default_factory=dict)
    reclaimable_bytes: int = 0


def _with_tag(image: str) -> str:
    return image if ":" in image.rsplit("/", 1)[-1] else image + ":latest"


def template_images(templates_dir: Path) -> set[str]:
    """Base images of the templates (Dockerfile FROM lines) and their image-only services."""
    out = set()
    for dockerfile in templates_dir.glob("*/**/Dockerfile"):
        for line in FROM_RE.findall(dockerfile.read_text(encoding="utf-8")):
            words = [w for w in line.split() if not w.startswith("--")]
            if words and "$" not in words[0] and words[0].lower() != "scratch":
                out.add(_with_tag(words[0]))
    for spec in templates_dir.glob("*/template.yml"):
        for svc in (yaml.safe_load(spec.read_text(encoding="utf-8")) or {}).get("services") or []:
            if svc.get("image"):
                out.add(_with_tag(svc["image"]))
    return out


def ctfd_images(additionals: list[dict]) -> set[str]:
    """Images the CTFd challenges run: single `image`, multi `services[].image` (a JSON string)."""
    out = set()
    for add in additionals:
        if not add.get("image") and not add.get("services"):
            raise ValueError(f"a dynamic_iac challenge has neither image nor services in additional: {add}")
        if add.get("image"):
            out.add(add["image"])
        services = add.get("services") or []
        if isinstance(services, str):
            services = json.loads(services)  # unparsable: fail rather than treat the images as unused
        out |= {s["image"] for s in services if s.get("image")}
    return out


def _path(ref: str, hosts: set[str]) -> str | None:
    """`challsmith/x:tag` when ref names an image on the local registry."""
    host, _, rest = ref.partition("/")
    return rest if host in hosts and rest else None


def _mirrored(path: str | None) -> list[str]:
    """The official image a mirror copy stands for, so keep patterns like mariadb:11.8 match it."""
    return [path[len(MIRROR):]] if path and path.startswith(MIRROR) else []


def decide(
    images: list[tuple[str, str, int]],
    used_ids: set[str],
    ctfd_refs: set[str],
    keep: dict[str, str],
    registry_tags: list[tuple[str, str, str]],
    hosts: set[str],
) -> CleanupPlan:
    """images: (id, repo:tag or "", size); used_ids: container image ids; keep: glob pattern -> reason;
    registry_tags: (repo, tag, digest). reclaimable_bytes adds whole image sizes, so shared layers count once
    per image: an upper bound."""
    ctfd_paths = {p for r in ctfd_refs if (p := _path(r, hosts))}

    def reason(names: list[str], path: str | None) -> str | None:
        if any(n in ctfd_refs for n in names) or (path and path in ctfd_paths):
            return "CTFd challenge"
        if path and path.startswith(SCENARIOS):
            return "scenario"
        for pattern, why in keep.items():
            if any(fnmatch.fnmatchcase(n, pattern) for n in names):
                return why
        return None

    plan = CleanupPlan()
    kept_img, kept_reg = defaultdict(list), defaultdict(list)
    for img_id, ref, size in images:
        path = ref and _path(ref, hosts)
        why = "in use by a container" if img_id in used_ids else (ref and reason([ref, *_mirrored(path)], path))
        if why:
            kept_img[why].append(ref or img_id)
        else:
            plan.images.append({"ref": ref, "id": img_id, "size": size})
    removed_rows = {(i["id"], i["ref"]) for i in plan.images}
    kept_ids = {i for i, ref, _ in images if (i, ref) not in removed_rows}  # untagging alone frees nothing
    plan.reclaimable_bytes = sum({i["id"]: i["size"] for i in plan.images if i["id"] not in kept_ids}.values())

    kept_digests, candidates = set(), []
    for repo, tag, digest in registry_tags:
        path = f"{repo}:{tag}"
        if not repo.startswith(OWNED):
            why = "outside challsmith/"
        else:
            why = reason([path, *(f"{h}/{path}" for h in hosts), *_mirrored(path)], path)
        if why:
            kept_reg[why].append(path)
            kept_digests.add(digest)
        else:
            candidates.append({"repo": repo, "tag": tag, "digest": digest})
    for c in candidates:
        if c["digest"] in kept_digests:  # deleting by digest would take the kept tag with it
            kept_reg["same digest as a kept tag"].append(f"{c['repo']}:{c['tag']}")
        else:
            plan.registry.append(c)
    plan.kept_images, plan.kept_registry = dict(kept_img), dict(kept_reg)
    return plan


def registry_tags(registry) -> list[tuple[str, str, str]]:
    return [(repo, tag, d) for repo in registry.catalog() for tag in registry.tags(repo) if (d := registry.digest(repo, tag))]


def registry_hosts() -> set[str]:
    s = get_settings()
    return {s.registry_prefix.split("/")[0], s.registry_url.split("://")[-1].rstrip("/")}


def plan(docker, registry, ctfd, log) -> CleanupPlan:
    s = get_settings()
    keep = {p.strip(): "keep list" for p in s.cleanup_keep_images.split(",") if p.strip()}
    bases = template_images(Path(s.templates_dir))
    if not bases:  # a missing templates dir must not make every base image look unused
        raise RuntimeError(f"no template base images found under {s.templates_dir}")
    for image in sorted(bases):
        keep.setdefault(image, "template base image")
    return decide(
        docker.list_images(log),
        docker.container_image_ids(log),
        ctfd_images(ctfd.list_iac_additional()),
        keep,
        registry_tags(registry),
        registry_hosts(),
    )


def _delete_manifests(registry, items: list[dict], log) -> None:
    for repo, digest in dict.fromkeys((i["repo"], i["digest"]) for i in items):
        log(f"deleting {repo}@{digest}")
        registry.delete(repo, digest)


def garbage_collect(docker, registry, log, wait: float = 60) -> None:
    """Stop the registry, garbage-collect its volume, start it again whatever happened."""
    cid, image, volume = docker.compose_container("challsmith", "registry", "/var/lib/registry", log)
    docker.stop_container(cid, log)
    gc_error = None
    try:
        docker.registry_gc(image, volume, GC_CONFIG, log)
    except Exception as e:
        gc_error = e
    try:
        docker.start_container(cid, log)
        deadline = time.monotonic() + wait
        while not registry.ping():
            if time.monotonic() > deadline:
                raise RuntimeError("the registry did not answer on /v2/ after the restart")
            time.sleep(1)
    except Exception as e:
        raise RuntimeError(f"{e}" + (f" (garbage-collect had failed first: {gc_error})" if gc_error else "")) from e
    if gc_error is not None:
        raise gc_error


def execute(p: CleanupPlan, docker, registry, log) -> dict:
    for item in p.images:
        if item["ref"]:
            docker.remove_image(item["ref"], log)
    docker.prune(log)  # dangling images go here
    _delete_manifests(registry, p.registry, log)
    garbage_collect(docker, registry, log)
    return {"images": len(p.images), "registry_tags": len(p.registry), "reclaimed_bytes": p.reclaimable_bytes}


def remove_repos(docker, registry, repos: set[str], log) -> None:
    """Local tags and registry manifests of these registry repos (`challsmith/<slug>-<service>`).
    A digest another repo's tag also points to stays. No garbage collection here."""
    hosts = registry_hosts()
    for _, ref, _ in docker.list_images(log):
        path = ref and _path(ref, hosts)
        if path and path.rsplit(":", 1)[0] in repos:
            try:
                docker.remove_image(ref, log)
            except Exception as e:  # e.g. a container still uses it
                log(f"kept {ref}: {e}")
    tags = registry_tags(registry)
    kept = {d for repo, _, d in tags if repo not in repos}
    _delete_manifests(registry, [{"repo": r, "digest": d} for r, _, d in tags if r in repos and d not in kept], log)
