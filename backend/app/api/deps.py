from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.clients import chall_manager_client, ctfd_client, docker_client, registry_client
from app.core.config import get_settings
from app.core.db import get_session
from app.models import WebSession
from app.services import auth_service


def _unauthorized() -> HTTPException:
    return HTTPException(401, "unauthorized", headers={"WWW-Authenticate": "Bearer"})


def require_session(
    authorization: str | None = Header(None),
    db: Session = Depends(get_session),
) -> WebSession:
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise _unauthorized()
    row = auth_service.validate_session(db, token)
    if row is None:
        raise _unauthorized()
    return row


def get_docker_ops() -> docker_client.DockerOps:
    s = get_settings()
    return docker_client.DockerOps(s.upstream_http_proxy, s.upstream_https_proxy, s.upstream_no_proxy)


def get_ctfd_client() -> ctfd_client.CtfdClient:
    s = get_settings()
    return ctfd_client.CtfdClient(s.ctfd_url, s.ctfd_admin_name, s.ctfd_admin_password)


def get_chall_manager():
    cm = chall_manager_client.ChallManager(get_settings().chall_manager_url)
    try:
        yield cm
    finally:
        cm.close()


def get_registry_client():
    registry = registry_client.RegistryClient(get_settings().registry_url)
    try:
        yield registry
    finally:
        registry.close()
