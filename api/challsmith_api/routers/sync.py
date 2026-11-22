from typing import Literal

from fastapi import APIRouter, Depends, Response, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from challsmith_api.core.db import get_session
from challsmith_api.services import sync_service

router = APIRouter()


class GitSettings(BaseModel):
    remote_url: str
    username: str = ""
    token: str | None = None
    branch: str = "main"
    dir: str = "challenges"
    author_name: str = "challsmith"
    author_email: str = "challsmith@localhost"


class ExportBody(BaseModel):
    push: bool = True


class ApplyBody(BaseModel):
    preview_id: str
    decisions: dict[str, Literal["source", "db"]] = {}


@router.get("/settings/git")
def get_git(db: Session = Depends(get_session)):
    return sync_service.get_git_settings(db)


@router.put("/settings/git")
def put_git(body: GitSettings, db: Session = Depends(get_session)):
    return sync_service.put_git_settings(db, body.model_dump())


@router.post("/sync/git/export")
def git_export(body: ExportBody, db: Session = Depends(get_session)):
    return sync_service.git_export(db, body.push)


@router.post("/sync/git/preview")
def git_preview(db: Session = Depends(get_session)):
    return sync_service.git_preview(db)


@router.post("/sync/archive/preview")
def archive_preview(file: UploadFile, db: Session = Depends(get_session)):
    return sync_service.archive_preview(db, file.file.read(sync_service.MAX_UPLOAD + 1))


@router.post("/sync/apply")
def apply(body: ApplyBody, db: Session = Depends(get_session)):
    return sync_service.apply(db, body.preview_id, body.decisions)


@router.get("/backup")
def backup(db: Session = Depends(get_session)):
    name, data = sync_service.backup(db)
    return Response(data, media_type="application/gzip", headers={"Content-Disposition": f'attachment; filename="{name}"'})
