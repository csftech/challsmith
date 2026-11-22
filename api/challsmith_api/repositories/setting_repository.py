from sqlalchemy.orm import Session

from challsmith_api.models import Setting


def get(db: Session, key: str) -> dict | None:
    row = db.get(Setting, key)
    return None if row is None else row.value


def put(db: Session, key: str, value: dict) -> None:
    db.merge(Setting(key=key, value=value))
