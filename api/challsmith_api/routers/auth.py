from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from challsmith_api.core.config import get_settings
from challsmith_api.core.db import get_session
from challsmith_api.core.deps import require_session
from challsmith_api.models import WebSession
from challsmith_api.services import auth_service

public = APIRouter(prefix="/auth")
router = APIRouter(prefix="/auth", dependencies=[Depends(require_session)])


class LoginBody(BaseModel):
    username: str
    password: str


@public.post("/login")
def login(body: LoginBody, db: Session = Depends(get_session)):
    token, expires_at = auth_service.login(db, body.username, body.password)
    return {"token": token, "expires_at": expires_at.isoformat()}


@router.post("/logout", status_code=204)
def logout(session: WebSession = Depends(require_session), db: Session = Depends(get_session)):
    auth_service.logout(db, session)
    return Response(status_code=204)


@router.get("/me")
def me():
    return {"username": get_settings().web_admin_user}
