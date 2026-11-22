from blake3 import blake3
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import delete
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_session
from .models import WebSession

SESSION_TTL = timedelta(hours=12)

public = APIRouter(prefix="/auth")


class LoginBody(BaseModel):
    username: str
    password: str


def _hash(token: str) -> str:
    return blake3(token.encode()).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _unauthorized() -> HTTPException:
    return HTTPException(401, "unauthorized", headers={"WWW-Authenticate": "Bearer"})


def require_session(
    authorization: str | None = Header(None),
    db: Session = Depends(get_session),
) -> WebSession:
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise _unauthorized()
    row = db.get(WebSession, _hash(token))
    if row is None:
        raise _unauthorized()
    if row.expires_at <= _now():
        db.delete(row)  # lazy cleanup of expired sessions
        db.commit()
        raise _unauthorized()
    return row


def clear_sessions(db: Session) -> int:
    n = db.execute(delete(WebSession)).rowcount
    db.commit()
    return n


@public.post("/login")
def login(body: LoginBody, db: Session = Depends(get_session)):
    s = get_settings()
    # Evaluate both comparisons so timing does not reveal which field was wrong.
    user_ok = hmac.compare_digest(body.username.encode(), s.web_admin_user.encode())
    pw_ok = hmac.compare_digest(body.password.encode(), s.web_admin_password.encode())
    if not (user_ok and pw_ok and s.web_admin_password):
        raise _unauthorized()
    token = secrets.token_urlsafe(32)
    expires_at = _now() + SESSION_TTL
    db.add(WebSession(token_hash=_hash(token), expires_at=expires_at))
    db.commit()
    return {"token": token, "expires_at": expires_at.isoformat()}


router = APIRouter(prefix="/auth", dependencies=[Depends(require_session)])


@router.post("/logout", status_code=204)
def logout(session: WebSession = Depends(require_session), db: Session = Depends(get_session)):
    db.delete(session)
    db.commit()
    return Response(status_code=204)


@router.get("/me")
def me():
    return {"username": get_settings().web_admin_user}
