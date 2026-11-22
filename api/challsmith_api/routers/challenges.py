from fastapi import APIRouter, Depends, Request, Response, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from sqlalchemy.orm import Session

from challsmith_api.clients import ctfd_client
from challsmith_api.core.db import get_session
from challsmith_api.core.deps import get_ctfd_client
from challsmith_api.formats import challenge_format
from challsmith_api.services import challenge_service

router = APIRouter()


class NewChallenge(BaseModel):
    slug: str
    template: str
    name: str


@router.get("/challenges")
def list_challenges(db: Session = Depends(get_session)):
    return challenge_service.list_summaries(db)


@router.post("/challenges")
def create_challenge(body: NewChallenge, db: Session = Depends(get_session)):
    challenge_service.create_challenge(db, body.slug, body.template, body.name)
    return {"slug": body.slug}


@router.get("/challenges/{slug}")
def get_challenge(slug: str, db: Session = Depends(get_session)):
    return challenge_service.detail(db, slug)


@router.put("/challenges/{slug}")
def put_meta(slug: str, meta: challenge_format.ChallengeMeta, prune: bool = False, db: Session = Depends(get_session)):
    challenge_service.update_meta(db, slug, meta, prune)
    return {"ok": True}


@router.delete("/challenges/{slug}")
def remove_challenge(
    slug: str,
    db: Session = Depends(get_session),
    ctfd: ctfd_client.CtfdClient = Depends(get_ctfd_client),
):
    ch, _, _ = challenge_service.load_challenge(db, slug)
    challenge_service.delete_challenge(db, ch, ctfd)
    return {"ok": True}


@router.get("/challenges/{slug}/files/{path:path}")
def get_file(slug: str, path: str, db: Session = Depends(get_session)):
    return Response(challenge_service.read_file(db, slug, path), media_type="application/octet-stream")


@router.put("/challenges/{slug}/files/{path:path}")
async def put_file(slug: str, path: str, request: Request, db: Session = Depends(get_session)):
    ch, path = await run_in_threadpool(challenge_service.prepare_put, db, slug, path)
    body = bytearray()
    async for chunk in request.stream():
        body += chunk
        challenge_service.bounded(body, challenge_service.MAX_FILE)  # stop reading as soon as the limit is passed
    await run_in_threadpool(challenge_service.put_files, db, ch, {path: bytes(body)})
    return {"ok": True}


@router.delete("/challenges/{slug}/files/{path:path}")
def delete_file(slug: str, path: str, db: Session = Depends(get_session)):
    challenge_service.remove_file(db, slug, path)
    return {"ok": True}


@router.post("/challenges/{slug}/upload")
def upload(slug: str, dir: str, file: UploadFile, db: Session = Depends(get_session)):
    return {"files": challenge_service.upload(db, slug, dir, file.filename, file.file)}
