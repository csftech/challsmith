from fastapi import Depends, Header
from sqlalchemy.orm import Session

from challsmith_api.core.db import get_session
from challsmith_api.models import WebSession
from challsmith_api.services.auth import now, token_hash, unauthorized


def require_session(
    authorization: str | None = Header(None),
    db: Session = Depends(get_session),
) -> WebSession:
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise unauthorized()
    row = db.get(WebSession, token_hash(token))
    if row is None:
        raise unauthorized()
    if row.expires_at <= now():
        db.delete(row)  # lazy cleanup of expired sessions
        db.commit()
        raise unauthorized()
    return row
