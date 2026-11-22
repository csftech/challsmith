from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from challsmith_api.models import Challenge, ChallengeFile


def get_by_slug(db: Session, slug: str) -> Challenge | None:
    return db.scalar(select(Challenge).where(Challenge.slug == slug))


def get_by_slug_for_update(db: Session, slug: str) -> Challenge | None:
    """Same as get_by_slug but takes a row lock held until the caller's transaction ends."""
    return db.scalar(select(Challenge).where(Challenge.slug == slug).with_for_update())


def slug_exists(db: Session, slug: str) -> bool:
    return db.scalar(select(Challenge.id).where(Challenge.slug == slug)) is not None


def list_all(db: Session) -> list[Challenge]:
    return list(db.scalars(select(Challenge).order_by(Challenge.slug)))


def add(db: Session, slug: str, meta: dict, files: dict[str, bytes]) -> Challenge:
    ch = Challenge(slug=slug, meta=meta)
    db.add(ch)
    db.flush()  # the files need ch.id
    db.add_all(ChallengeFile(challenge_id=ch.id, path=p, content=c) for p, c in files.items())
    return ch


def delete_challenge(db: Session, ch: Challenge) -> None:
    db.delete(ch)


def files_of(db: Session, ch: Challenge) -> dict[str, bytes]:
    rows = db.execute(select(ChallengeFile.path, ChallengeFile.content).where(ChallengeFile.challenge_id == ch.id))
    return {p: bytes(c) for p, c in rows}


def replace(db: Session, ch: Challenge, meta: dict, files: dict[str, bytes]) -> None:
    """Overwrite the metadata and every file of an existing challenge."""
    ch.meta = meta
    ch.updated_at = func.now()
    db.execute(delete(ChallengeFile).where(ChallengeFile.challenge_id == ch.id))
    db.add_all(ChallengeFile(challenge_id=ch.id, path=p, content=c) for p, c in files.items())


def put_files(db: Session, ch: Challenge, put: dict[str, bytes], remove: list[str] | None) -> None:
    for path, content in put.items():
        db.merge(ChallengeFile(challenge_id=ch.id, path=path, content=content))
    if remove:
        db.execute(delete(ChallengeFile).where(ChallengeFile.challenge_id == ch.id, ChallengeFile.path.in_(remove)))
    ch.updated_at = func.now()


def update_by_slug(db: Session, slug: str, values: dict) -> None:
    db.execute(update(Challenge).where(Challenge.slug == slug).values(**values))
