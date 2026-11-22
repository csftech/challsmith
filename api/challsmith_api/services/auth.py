import hmac
import secrets
from datetime import datetime, timedelta, timezone

from blake3 import blake3
from fastapi import HTTPException
from sqlalchemy import delete
from sqlalchemy.orm import Session

from challsmith_api.core.config import get_settings
from challsmith_api.models import WebSession

SESSION_TTL = timedelta(hours=12)


def token_hash(token: str) -> str:
    return blake3(token.encode()).hexdigest()


def now() -> datetime:
    return datetime.now(timezone.utc)


def unauthorized() -> HTTPException:
    return HTTPException(401, "unauthorized", headers={"WWW-Authenticate": "Bearer"})


def clear_sessions(db: Session) -> int:
    n = db.execute(delete(WebSession)).rowcount
    db.commit()
    return n


def login(db: Session, username: str, password: str) -> tuple[str, datetime]:
    s = get_settings()
    # Evaluate both comparisons so timing does not reveal which field was wrong.
    user_ok = hmac.compare_digest(username.encode(), s.web_admin_user.encode())
    pw_ok = hmac.compare_digest(password.encode(), s.web_admin_password.encode())
    if not (user_ok and pw_ok and s.web_admin_password):
        raise unauthorized()
    token = secrets.token_urlsafe(32)
    expires_at = now() + SESSION_TTL
    db.add(WebSession(token_hash=token_hash(token), expires_at=expires_at))
    db.commit()
    return token, expires_at
