from datetime import datetime

from sqlalchemy import delete
from sqlalchemy.orm import Session

from challsmith_api.models import WebSession


def get(db: Session, token_hash: str) -> WebSession | None:
    return db.get(WebSession, token_hash)


def add(db: Session, token_hash: str, expires_at: datetime) -> None:
    db.add(WebSession(token_hash=token_hash, expires_at=expires_at))


def remove(db: Session, session: WebSession) -> None:
    db.delete(session)


def remove_all(db: Session) -> int:
    return db.execute(delete(WebSession)).rowcount
