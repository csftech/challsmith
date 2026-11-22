import hmac
import secrets
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from challsmith_api.core.config import get_settings
from challsmith_api.core.security import now, token_hash
from challsmith_api.models import WebSession
from challsmith_api.repositories import web_session_repository
from challsmith_api.services.errors import Unauthorized

SESSION_TTL = timedelta(hours=12)


def clear_sessions(db: Session) -> int:
    n = web_session_repository.remove_all(db)
    db.commit()
    return n


def logout(db: Session, session: WebSession) -> None:
    web_session_repository.remove(db, session)
    db.commit()


def login(db: Session, username: str, password: str) -> tuple[str, datetime]:
    s = get_settings()
    # Evaluate both comparisons so timing does not reveal which field was wrong.
    user_ok = hmac.compare_digest(username.encode(), s.web_admin_user.encode())
    pw_ok = hmac.compare_digest(password.encode(), s.web_admin_password.encode())
    if not (user_ok and pw_ok and s.web_admin_password):
        raise Unauthorized()
    token = secrets.token_urlsafe(32)
    expires_at = now() + SESSION_TTL
    web_session_repository.add(db, token_hash(token), expires_at)
    db.commit()
    return token, expires_at
