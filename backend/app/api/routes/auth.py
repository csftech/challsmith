from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_session
from app.api.deps import require_session
from app.models import WebSession
from app.schemas.auth_schema import LoginBody
from app.services import auth_service

public = APIRouter(prefix="/auth")
router = APIRouter(prefix="/auth", dependencies=[Depends(require_session)])


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
