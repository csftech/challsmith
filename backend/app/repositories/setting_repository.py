from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Setting


def get(db: Session, key: str) -> dict | None:
    row = db.get(Setting, key)
    return None if row is None else row.value


def put(db: Session, key: str, value: dict) -> None:
    db.merge(Setting(key=key, value=value))


def delete(db: Session, key: str) -> None:
    row = db.get(Setting, key)
    if row is not None:
        db.delete(row)


def lock_key(db: Session, key: int) -> None:
    """Transaction-scoped advisory lock: serialises check-then-mark sections across processes."""
    db.execute(select(func.pg_advisory_xact_lock(key)))
