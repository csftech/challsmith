from posixpath import basename
from typing import BinaryIO

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from challsmith_api.formats import archive_format, challenge_format, hashing_format
from challsmith_api.models import Challenge, ChallengeFile
from challsmith_api.services import template_service
from challsmith_api.services.errors import BadRequest, Conflict, NotFound, TooLarge, Unprocessable

MAX_FILE = 20 * 1024 * 1024


def meta_of(ch: Challenge) -> challenge_format.ChallengeMeta:
    return challenge_format.ChallengeMeta.model_validate(ch.meta)


def _files(db: Session, ch: Challenge) -> dict[str, bytes]:
    rows = db.execute(select(ChallengeFile.path, ChallengeFile.content).where(ChallengeFile.challenge_id == ch.id))
    return {p: bytes(c) for p, c in rows}


def load_challenge(db: Session, slug: str) -> tuple[Challenge, challenge_format.ChallengeMeta, dict[str, bytes]]:
    ch = db.scalar(select(Challenge).where(Challenge.slug == slug))
    if ch is None:
        raise NotFound("challenge not found")
    return ch, meta_of(ch), _files(db, ch)


def save_challenge(db: Session, slug: str, meta: challenge_format.ChallengeMeta, files: dict[str, bytes]) -> Challenge:
    """Create or overwrite a challenge (meta and every file) in one transaction."""
    ch = db.scalar(select(Challenge).where(Challenge.slug == slug))
    if ch is None:
        ch = Challenge(slug=slug, meta=meta.model_dump(mode="json"))
        db.add(ch)
        db.flush()
    else:
        ch.meta = meta.model_dump(mode="json")
        ch.updated_at = func.now()
        db.execute(delete(ChallengeFile).where(ChallengeFile.challenge_id == ch.id))
    db.add_all(ChallengeFile(challenge_id=ch.id, path=p, content=c) for p, c in files.items())
    db.commit()
    return ch


def current_hash(db: Session, challenge: Challenge) -> str:
    return hashing_format.content_hash(meta_of(challenge), _files(db, challenge))


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


def delete_challenge(db: Session, ch: Challenge) -> None:
    # Task 6: when ch.ctfd_id is set, delete it on CTFd first (404 counts as deleted).
    db.delete(ch)
    db.commit()


def put_files(db: Session, ch: Challenge, put: dict[str, bytes] | None = None, remove: list[str] | None = None) -> None:
    for path, content in (put or {}).items():
        db.merge(ChallengeFile(challenge_id=ch.id, path=path, content=content))
    if remove:
        db.execute(delete(ChallengeFile).where(ChallengeFile.challenge_id == ch.id, ChallengeFile.path.in_(remove)))
    ch.updated_at = func.now()
    db.commit()


def service_path(meta: challenge_format.ChallengeMeta, raw: str, *, need_rest: bool) -> str:
    """Normalise a path that must live under services/<folder service>/ ."""
    try:
        path = challenge_format.safe_relpath(raw)
    except ValueError as e:
        raise BadRequest(str(e))
    parts = path.split("/")
    folders = {s.name for s in meta.services if not s.image}
    if parts[0] != "services" or len(parts) < 2 or parts[1] not in folders or (need_rest and len(parts) < 3):
        raise BadRequest("path must be inside services/<service without image>/")
    return path


def bounded(data: bytes, limit: int) -> bytes:
    if len(data) > limit:
        raise TooLarge()
    return data


def list_summaries(db: Session) -> list[dict]:
    # shortcut: hashes every challenge's files per call, cache if the list gets big
    out = []
    for ch in db.scalars(select(Challenge).order_by(Challenge.slug)):
        meta = meta_of(ch)
        out.append(
            {
                "slug": ch.slug,
                "name": meta.name,
                "category": meta.category,
                "scenario": meta.scenario,
                **status_of(ch, current_hash(db, ch)),
                "updated_at": ch.updated_at,
            }
        )
    return out


def create_challenge(db: Session, slug: str, template: str, name: str) -> None:
    if db.scalar(select(Challenge.id).where(Challenge.slug == slug)) is not None:
        raise Conflict("slug already exists")
    if template not in {t.name for t in template_service.list_templates()}:
        raise BadRequest("unknown template")
    try:
        meta, files = template_service.instantiate(template, slug, name)
    except ValueError as e:
        raise Unprocessable(str(e))
    try:
        save_challenge(db, slug, meta, files)
    except IntegrityError:
        db.rollback()
        raise Conflict("slug already exists")


def detail(db: Session, slug: str) -> dict:
    ch, meta, files = load_challenge(db, slug)
    return {
        "meta": meta.model_dump(mode="json"),
        "files": [{"path": p, "size": len(files[p])} for p in sorted(files)],
        "status": status_of(ch, hashing_format.content_hash(meta, files)),
    }


def update_meta(db: Session, slug: str, meta: challenge_format.ChallengeMeta, prune: bool) -> None:
    ch, _, files = load_challenge(db, slug)
    if meta.slug != slug:
        raise BadRequest("slug cannot be changed")
    folders = {s.name for s in meta.services if not s.image}
    orphans = sorted(p for p in files if p.startswith("services/") and p.split("/")[1] not in folders)
    if orphans and not prune:
        raise Conflict({"orphans": orphans})
    ch.meta = meta.model_dump(mode="json")
    put_files(db, ch, remove=orphans)


def read_file(db: Session, slug: str, path: str) -> bytes:
    _, _, files = load_challenge(db, slug)
    if path not in files:
        raise NotFound("file not found")
    return files[path]


def prepare_put(db: Session, slug: str, path: str) -> tuple[Challenge, str]:
    ch, meta, _ = load_challenge(db, slug)
    return ch, service_path(meta, path, need_rest=True)


def remove_file(db: Session, slug: str, path: str) -> None:
    ch, meta, files = load_challenge(db, slug)
    path = service_path(meta, path, need_rest=True)
    if path not in files:
        raise NotFound("file not found")
    put_files(db, ch, remove=[path])


def upload(db: Session, slug: str, dir: str, filename: str | None, fileobj: BinaryIO) -> list[str]:
    ch, meta, _ = load_challenge(db, slug)
    base = service_path(meta, dir, need_rest=False)
    name = basename(filename or "")
    if name.lower().endswith(".zip"):
        # compressed size is bounded by the same cap as the extracted total
        data = fileobj.read(archive_format.MAX_TOTAL + 1)
        if len(data) > archive_format.MAX_TOTAL:
            raise BadRequest("archive too large")
        try:
            new = {f"{base}/{p}": c for p, c in archive_format.extract_zip(data).items()}
        except ValueError as e:
            raise BadRequest(str(e))
    else:
        if not name:
            raise BadRequest("missing file name")
        try:
            target = challenge_format.safe_relpath(f"{base}/{name}")
        except ValueError as e:
            raise BadRequest(str(e))
        new = {target: bounded(fileobj.read(MAX_FILE + 1), MAX_FILE)}
    put_files(db, ch, new)
    return sorted(new)
