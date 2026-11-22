import json
import tempfile
from collections.abc import Callable
from pathlib import Path

from sqlalchemy.orm import Session

from app.clients import ctfd_client, docker_client
from app.clients.ctfd_client import CtfdNotFound
from app.core.config import get_settings
from app.utils import hash_util
from app.schemas import challenge_schema
from app.repositories import challenge_repository, publish_run_repository
from app.services import challenge_service
from app.services.errors import BadRequest, Conflict, NotFound


def mirror_ref(image: str, prefix: str) -> str:
    """Where an official image is copied to. Images already on the local registry are used as is."""
    if image.startswith(prefix.split("/")[0] + "/"):
        return image
    if "@" in image:
        raise BadRequest(f"image {image!r}: digest references are not supported, use a tag")
    if ":" not in image.rsplit("/", 1)[-1]:
        image += ":latest"
    return f"{prefix}/mirror/{image}"


def build_additional(meta: challenge_schema.ChallengeMeta, images: dict[str, str]) -> tuple[str, dict[str, str]]:
    s = get_settings()

    def image_of(svc: challenge_schema.ServiceSpec) -> str:
        return images.get(svc.name) or mirror_ref(svc.image, s.registry_prefix)

    common = {"flag": meta.flag, "flag_prefix": meta.flag_prefix, "protocol": meta.protocol,
              "memory": meta.instance.memory, "cpus": meta.instance.cpus}
    if meta.scenario == "single":
        svc = meta.services[0]
        add = {"image": image_of(svc), **({"port": str(svc.port)} if svc.port else {}), **common}
        return s.scenario_single, add
    services = []
    for svc in meta.services:
        d: dict = {"name": svc.name, "image": image_of(svc)}
        if svc.port:
            d["port"] = svc.port
        if svc.entry:
            d["entry"] = True
        if svc.env:
            d["env"] = svc.env
        services.append(d)
    return s.scenario_multi, {"services": json.dumps(services), **common}


def ctfd_payload(meta: challenge_schema.ChallengeMeta, scenario_ref: str, additional: dict[str, str]) -> dict:
    return {
        "name": meta.name, "category": meta.category, "description": meta.description,
        "type": "dynamic_iac", "function": "linear", "initial": meta.value, "minimum": meta.value, "decay": 0,
        "state": "visible" if meta.visible else "hidden", "scenario": scenario_ref, "additional": additional,
        "mana_cost": meta.instance.mana, "timeout": meta.instance.timeout,
    }


def start_run(db: Session, slug: str) -> int:
    # the row lock makes "one running run per challenge" race-safe
    ch = challenge_repository.get_by_slug_for_update(db, slug)
    if ch is None:
        raise NotFound("challenge not found")
    if publish_run_repository.get_running(db, ch) is not None:
        raise Conflict("a publish is already running for this challenge")
    run = publish_run_repository.add_running(db, ch)
    db.commit()
    return run.id


def get_run(db: Session, run_id: int) -> dict:
    run = publish_run_repository.get(db, run_id)
    if run is None:
        raise NotFound("publish run not found")
    return {"status": run.status, "log": run.log, "created_at": run.created_at, "finished_at": run.finished_at}


def fail_interrupted(db: Session) -> None:
    publish_run_repository.fail_running(db, "api restarted, publish interrupted\n")
    db.commit()


def _write_context(dest: Path, files: dict[str, bytes], service: str) -> None:
    prefix = f"services/{service}/"
    for path, content in files.items():
        if path.startswith(prefix):
            target = dest / path[len(prefix):]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
    # explicit modes: the image must not depend on the api's umask (php-fpm/nginx run as other users)
    dest.chmod(0o755)
    for p in dest.rglob("*"):
        p.chmod(0o755 if p.is_dir() else 0o644)


def run_publish(
    db_factory: Callable[[], Session],
    run_id: int,
    slug: str,
    docker: docker_client.DockerOps,
    ctfd: ctfd_client.CtfdClient,
) -> None:
    def log(line: str) -> None:
        # shortcut: one commit per line keeps the poller current, batch if build logs get huge
        with db_factory() as s:
            publish_run_repository.append_log(s, run_id, line)
            s.commit()

    def finish(status: str | None, ch_values: dict | None = None) -> None:
        with db_factory() as s:
            if ch_values:
                challenge_repository.update_by_slug(s, slug, ch_values)
            if status:
                publish_run_repository.set_status(s, run_id, status)
            s.commit()

    try:
        with db_factory() as s:  # snapshot: later edits do not affect this run
            ch, meta, files = challenge_service.load_challenge(s, slug)
            snapshot_hash, ctfd_id = challenge_service.current_hash(s, ch), ch.ctfd_id
        prefix = get_settings().registry_prefix
        images: dict[str, str] = {}
        for svc in meta.services:
            if svc.image:
                dst = mirror_ref(svc.image, prefix)
                if dst != svc.image:
                    log(f"mirroring {svc.image} to {dst}")
                    docker.pull(svc.image, log)
                    docker.tag(svc.image, dst, log)
                    docker.push(dst, log)
                continue
            tag = f"{prefix}/{slug}-{svc.name}:{hash_util.service_hash(files, svc.name)[:12]}"
            log(f"building {tag}")
            with tempfile.TemporaryDirectory() as tmp:
                _write_context(Path(tmp), files, svc.name)
                docker.build(Path(tmp), tag, log)
            docker.push(tag, log)
            images[svc.name] = tag
        scenario_ref, additional = build_additional(meta, images)
        payload = ctfd_payload(meta, scenario_ref, additional)
        if ctfd_id is not None:
            log(f"updating CTFd challenge {ctfd_id}")
            try:
                ctfd.update_challenge(ctfd_id, {k: v for k, v in payload.items() if k != "type"})
            except CtfdNotFound:
                log("CTFd challenge is gone, creating a new one")
                ctfd_id = None
        if ctfd_id is None:
            log("creating CTFd challenge")
            ctfd_id = ctfd.create_challenge(payload)
            finish(None, {"ctfd_id": ctfd_id})  # track it now so a later failure cannot orphan it
        ctfd.set_tags(ctfd_id, meta.tags)
        log(f"published as CTFd challenge {ctfd_id}")
        finish("succeeded", {"ctfd_id": ctfd_id, "published_hash": snapshot_hash})
    except Exception as e:
        log(f"FAILED: {getattr(e, 'detail', None) or e}")
        finish("failed")
