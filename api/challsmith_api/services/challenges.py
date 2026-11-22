from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from challsmith_api.formats.challenge import ChallengeMeta, safe_relpath
from challsmith_api.formats.hashing import content_hash
from challsmith_api.models import Challenge, ChallengeFile

MAX_FILE = 20 * 1024 * 1024


def meta_of(ch: Challenge) -> ChallengeMeta:
    return ChallengeMeta.model_validate(ch.meta)


def _files(db: Session, ch: Challenge) -> dict[str, bytes]:
    rows = db.execute(select(ChallengeFile.path, ChallengeFile.content).where(ChallengeFile.challenge_id == ch.id))
    return {p: bytes(c) for p, c in rows}


def load_challenge(db: Session, slug: str) -> tuple[Challenge, ChallengeMeta, dict[str, bytes]]:
    ch = db.scalar(select(Challenge).where(Challenge.slug == slug))
    if ch is None:
        raise HTTPException(404, "challenge not found")
    return ch, meta_of(ch), _files(db, ch)


def save_challenge(db: Session, slug: str, meta: ChallengeMeta, files: dict[str, bytes]) -> Challenge:
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
    return content_hash(meta_of(challenge), _files(db, challenge))


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


def service_path(meta: ChallengeMeta, raw: str, *, need_rest: bool) -> str:
    """Normalise a path that must live under services/<folder service>/ ."""
    try:
        path = safe_relpath(raw)
    except ValueError as e:
        raise HTTPException(400, str(e))
    parts = path.split("/")
    folders = {s.name for s in meta.services if not s.image}
    if parts[0] != "services" or len(parts) < 2 or parts[1] not in folders or (need_rest and len(parts) < 3):
        raise HTTPException(400, "path must be inside services/<service without image>/")
    return path


def bounded(data: bytes, limit: int) -> bytes:
    if len(data) > limit:
        raise HTTPException(413, "file too large")
    return data
