from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.clients import ctfd_client, docker_client
from app.core.config import get_settings
from app.core.db import get_session
from app.core.security import now, token_hash
from app.models import WebSession
from app.repositories import web_session_repository


def _unauthorized() -> HTTPException:
    return HTTPException(401, "unauthorized", headers={"WWW-Authenticate": "Bearer"})


def require_session(
    authorization: str | None = Header(None),
    db: Session = Depends(get_session),
) -> WebSession:
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise _unauthorized()
    row = web_session_repository.get(db, token_hash(token))
    if row is None:
        raise _unauthorized()
    if row.expires_at <= now():
        web_session_repository.remove(db, row)  # lazy cleanup of expired sessions
        db.commit()
        raise _unauthorized()
    return row


def get_docker_ops() -> docker_client.DockerOps:
    s = get_settings()
    return docker_client.DockerOps(s.upstream_http_proxy, s.upstream_https_proxy, s.upstream_no_proxy)


def get_ctfd_client() -> ctfd_client.CtfdClient:
    s = get_settings()
    return ctfd_client.CtfdClient(s.ctfd_url, s.ctfd_admin_name, s.ctfd_admin_password)
