import logging
from posixpath import basename
from typing import BinaryIO

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.clients import ctfd_client
from app.clients.ctfd_client import CtfdError, CtfdNotFound
from app.core.config import get_settings
from app.utils import archive_util, hash_util
from app.schemas import challenge_schema
from app.models import Challenge
from app.repositories import challenge_repository, publish_run_repository, setting_repository
from app.services import image_cleanup_service, order_service, template_service
from app.services.errors import BadGateway, BadRequest, Conflict, NotFound, TooLarge, Unprocessable

MAX_FILE = 20 * 1024 * 1024
ORDER_LOCK = 0x6F7264  # advisory lock: one writer of the order (DB and CTFd) at a time

logger = logging.getLogger(__name__)


def meta_of(ch: Challenge) -> challenge_schema.ChallengeMeta:
    return challenge_schema.ChallengeMeta.model_validate(ch.meta)


def _files(db: Session, ch: Challenge) -> dict[str, bytes]:
    return challenge_repository.files_of(db, ch)


def load_challenge(db: Session, slug: str) -> tuple[Challenge, challenge_schema.ChallengeMeta, dict[str, bytes]]:
    ch = challenge_repository.get_by_slug(db, slug)
    if ch is None:
        raise NotFound("challenge not found")
    return ch, meta_of(ch), _files(db, ch)


def save_challenge(db: Session, slug: str, meta: challenge_schema.ChallengeMeta, files: dict[str, bytes]) -> Challenge:
    """Create or overwrite a challenge (meta and every file) in one transaction."""
    ch = challenge_repository.get_by_slug(db, slug)
    if ch is None:
        ch = challenge_repository.add(db, slug, meta.model_dump(mode="json"), files)
    else:
        challenge_repository.replace(db, ch, meta.model_dump(mode="json"), files)
    db.commit()
    return ch


def current_hash(db: Session, challenge: Challenge) -> str:
    return hash_util.content_hash(meta_of(challenge), _files(db, challenge))


def status_of(challenge: Challenge, current: str) -> dict:
    if challenge.ctfd_id is None:
        publish = "draft"
    else:
        publish = "published" if challenge.published_hash == current else "modified"
    if challenge.sync_hash is None:
        sync = "never"
    else:
        sync = "synced" if challenge.sync_hash == current else "modified"
    return {"publish": publish, "sync": sync}


def _repos(ch: Challenge) -> set[str]:
    """Registry repos the publish builds for this challenge (see publish_service)."""
    base = get_settings().registry_prefix.split("/", 1)[1]
    return {f"{base}/{ch.slug}-{s.name}" for s in meta_of(ch).services if not s.image}


def delete_challenge(db: Session, ch: Challenge, ctfd: ctfd_client.CtfdClient, docker, registry) -> None:
    if publish_run_repository.get_running(db, ch) is not None:
        raise Conflict("a publish is running for this challenge; wait for it to finish before deleting", code="publish_running")
    if ch.ctfd_id is not None:
        try:
            ctfd.delete_challenge(ch.ctfd_id)
        except CtfdNotFound:
            pass  # already gone on CTFd
        except CtfdError as e:
            raise BadGateway(f"could not delete the CTFd challenge: {e}", code="ctfd_unreachable")
    others = set().union(*(_repos(c) for c in challenge_repository.list_all(db) if c.id != ch.id))
    repos = _repos(ch) - others  # slug "a" + service "b-c" and slug "a-b" + service "c" share a repo
    challenge_repository.delete_challenge(db, ch)
    db.commit()
    try:
        image_cleanup_service.remove_repos(docker, registry, repos, logger.info)
    except Exception:
        logger.warning("could not remove the images of %s", ch.slug, exc_info=True)  # pre-release cleanup catches them


def put_files(db: Session, ch: Challenge, put: dict[str, bytes] | None = None, remove: list[str] | None = None) -> None:
    challenge_repository.put_files(db, ch, put or {}, remove)
    db.commit()


def service_path(meta: challenge_schema.ChallengeMeta, raw: str, *, need_rest: bool) -> str:
    """Normalise a path that must live under services/<folder service>/ ."""
    try:
        path = challenge_schema.safe_relpath(raw)
    except ValueError as e:
        raise BadRequest(str(e), code="invalid_path")
    parts = path.split("/")
    folders = {s.name for s in meta.services if not s.image}
    if parts[0] != "services" or len(parts) < 2 or parts[1] not in folders or (need_rest and len(parts) < 3):
        raise BadRequest("path must be inside services/<service without image>/", code="invalid_path")
    return path


def bounded(data: bytes, limit: int) -> bytes:
    if len(data) > limit:
        raise TooLarge(code="file_too_large")
    return data


def _rows(chs: list[Challenge]) -> list[order_service.Row]:
    return [order_service.Row(c.slug, meta_of(c).category, c.ctfd_id) for c in chs]


def list_summaries(db: Session, ctfd: ctfd_client.CtfdClient) -> dict:
    setting_repository.lock_key(db, ORDER_LOCK)  # before reading: a concurrent save must not be overwritten by a stale write-back
    chs = challenge_repository.list_all(db)
    ctfd_ok, pos = True, {}
    if any(c.ctfd_id is not None for c in chs):
        try:
            pos = {i: order_service.CtfdPos(*v) for i, v in ctfd.list_positions().items()}
        except CtfdError:
            ctfd_ok = False
    if ctfd_ok:
        order = order_service.reconcile(_rows(chs), pos)
        if order != [c.slug for c in chs]:
            challenge_repository.set_positions(db, order)
            by = {c.slug: c for c in chs}
            chs = [by[s] for s in order]
    db.commit()  # releases ORDER_LOCK before the slow part below
    # shortcut: hashes every challenge's files per call, cache if the list gets big
    items = []
    for ch in chs:
        meta = meta_of(ch)
        items.append(
            {
                "slug": ch.slug,
                "name": meta.name,
                "category": meta.category,
                "scenario": meta.scenario,
                **status_of(ch, current_hash(db, ch)),
                "updated_at": ch.updated_at,
                "position": ch.position,
                "ctfd_id": ch.ctfd_id,
                "ctfd_missing": ctfd_ok and ch.ctfd_id is not None and ch.ctfd_id not in pos,
                "template": meta.template,
                "services": len(meta.services),
                "value": meta.value,
            }
        )
    return {"items": items, "ctfd_ok": ctfd_ok}


def _push(ctfd: ctfd_client.CtfdClient, targets: list[tuple[str, int, int]]) -> list[str]:
    failed = []
    for slug, cid, position in targets:
        try:
            ctfd.set_position(cid, position)
        except CtfdError:
            failed.append(slug)
    return failed


def push_positions(db: Session, ctfd: ctfd_client.CtfdClient) -> list[str]:
    """Send every published challenge's position to CTFd; returns the slugs that failed."""
    setting_repository.lock_key(db, ORDER_LOCK)
    known = ctfd.list_positions()
    failed = _push(ctfd, [(c.slug, c.ctfd_id, c.position) for c in challenge_repository.list_all(db) if c.ctfd_id in known])
    db.commit()  # releases ORDER_LOCK
    return failed


def save_order(db: Session, ctfd: ctfd_client.CtfdClient, order: list[str]) -> None:
    setting_repository.lock_key(db, ORDER_LOCK)
    chs = challenge_repository.list_all(db)
    order_service.validate_order(order, _rows(chs))
    by = {c.slug: c for c in chs}
    pub = [(s, by[s].ctfd_id, i) for i, s in enumerate(order, 1) if by[s].ctfd_id is not None]
    if pub:
        try:
            known = ctfd.list_positions()
        except CtfdError as e:
            raise BadGateway(f"could not read CTFd: {e}", code="ctfd_unreachable")
        failed = _push(ctfd, [t for t in pub if t[1] in known])  # a challenge missing on CTFd keeps only its DB position
        if failed:
            db.rollback()
            raise BadGateway(f"could not set the CTFd position of: {', '.join(failed)}", code="ctfd_order_failed")
    challenge_repository.set_positions(db, order)
    db.commit()


def create_challenge(db: Session, slug: str, template: str, name: str) -> None:
    if slug in challenge_schema.RESERVED_SLUGS:
        raise BadRequest("slug is reserved", code="slug_reserved")
    if challenge_repository.slug_exists(db, slug):
        raise Conflict("slug already exists", code="slug_exists")
    if template not in {t.name for t in template_service.list_templates()}:
        raise BadRequest("unknown template", code="unknown_template")
    try:
        meta, files = template_service.instantiate(template, slug, name)
    except ValueError as e:
        raise Unprocessable(str(e), code="invalid_challenge")
    try:
        save_challenge(db, slug, meta, files)
    except IntegrityError:
        db.rollback()
        raise Conflict("slug already exists", code="slug_exists")


def detail(db: Session, slug: str) -> dict:
    ch, meta, files = load_challenge(db, slug)
    return {
        "meta": meta.model_dump(mode="json"),
        "files": [{"path": p, "size": len(files[p])} for p in sorted(files)],
        "status": status_of(ch, hash_util.content_hash(meta, files)),
    }


def update_meta(db: Session, slug: str, meta: challenge_schema.ChallengeMeta, prune: bool) -> None:
    ch, _, files = load_challenge(db, slug)
    if meta.slug != slug:
        raise BadRequest("slug cannot be changed", code="slug_immutable")
    folders = {s.name for s in meta.services if not s.image}
    orphans = sorted(p for p in files if p.startswith("services/") and p.split("/")[1] not in folders)
    if orphans and not prune:
        raise Conflict({"orphans": orphans}, code="orphan_files")
    if meta.category != meta_of(ch).category:
        setting_repository.lock_key(db, ORDER_LOCK)
        rows = [r._replace(category=meta.category) if r.slug == slug else r for r in _rows(challenge_repository.list_all(db))]
        challenge_repository.set_positions(db, order_service.move_to_category_end(rows, slug, meta.category))
    ch.meta = meta.model_dump(mode="json")
    put_files(db, ch, remove=orphans)


def read_file(db: Session, slug: str, path: str) -> bytes:
    _, _, files = load_challenge(db, slug)
    if path not in files:
        raise NotFound("file not found", code="file_not_found")
    return files[path]


def prepare_put(db: Session, slug: str, path: str) -> tuple[Challenge, str]:
    ch, meta, _ = load_challenge(db, slug)
    return ch, service_path(meta, path, need_rest=True)


def remove_file(db: Session, slug: str, path: str) -> None:
    ch, meta, files = load_challenge(db, slug)
    path = service_path(meta, path, need_rest=True)
    if path not in files:
        raise NotFound("file not found", code="file_not_found")
    put_files(db, ch, remove=[path])


def upload(db: Session, slug: str, dir: str, filename: str | None, fileobj: BinaryIO) -> list[str]:
    ch, meta, _ = load_challenge(db, slug)
    base = service_path(meta, dir, need_rest=False)
    name = basename(filename or "")
    if name.lower().endswith(".zip"):
        # compressed size is bounded by the same cap as the extracted total
        data = fileobj.read(archive_util.MAX_TOTAL + 1)
        if len(data) > archive_util.MAX_TOTAL:
            raise BadRequest("archive too large", code="archive_too_large")
        try:
            new = {f"{base}/{p}": c for p, c in archive_util.extract_zip(data).items()}
        except ValueError as e:
            raise BadRequest(str(e), code="invalid_archive")
    else:
        if not name:
            raise BadRequest("missing file name", code="missing_file_name")
        try:
            target = challenge_schema.safe_relpath(f"{base}/{name}")
        except ValueError as e:
            raise BadRequest(str(e), code="invalid_path")
        new = {target: bounded(fileobj.read(MAX_FILE + 1), MAX_FILE)}
    put_files(db, ch, new)
    return sorted(new)
