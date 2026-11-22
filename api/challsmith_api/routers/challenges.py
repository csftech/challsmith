from posixpath import basename

from fastapi import APIRouter, Depends, HTTPException, Request, Response, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from challsmith_api.core.db import get_session
from challsmith_api.formats.archive import MAX_TOTAL, extract_zip
from challsmith_api.formats.challenge import ChallengeMeta, safe_relpath
from challsmith_api.formats.hashing import content_hash
from challsmith_api.models import Challenge
from challsmith_api.services import templates
from challsmith_api.services.challenges import (
    MAX_FILE,
    bounded,
    current_hash,
    delete_challenge,
    load_challenge,
    meta_of,
    put_files,
    save_challenge,
    service_path,
    status_of,
)

router = APIRouter()


class NewChallenge(BaseModel):
    slug: str
    template: str
    name: str


@router.get("/challenges")
def list_challenges(db: Session = Depends(get_session)):
    # shortcut: hashes every challenge's files per call, cache if the list gets big
    out = []
    for ch in db.scalars(select(Challenge).order_by(Challenge.slug)):
        meta = meta_of(ch)
        out.append(
            {
                "slug": ch.slug,
                "name": meta.name,
                "category": meta.category,
                "scenario": meta.scenario,
                **status_of(ch, current_hash(db, ch)),
                "updated_at": ch.updated_at,
            }
        )
    return out


@router.post("/challenges")
def create_challenge(body: NewChallenge, db: Session = Depends(get_session)):
    if db.scalar(select(Challenge.id).where(Challenge.slug == body.slug)) is not None:
        raise HTTPException(409, "slug already exists")
    if body.template not in {t.name for t in templates.list_templates()}:
        raise HTTPException(400, "unknown template")
    try:
        meta, files = templates.instantiate(body.template, body.slug, body.name)
    except ValueError as e:
        raise HTTPException(422, str(e))
    try:
        save_challenge(db, body.slug, meta, files)
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "slug already exists")
    return {"slug": body.slug}


@router.get("/challenges/{slug}")
def get_challenge(slug: str, db: Session = Depends(get_session)):
    ch, meta, files = load_challenge(db, slug)
    return {
        "meta": meta.model_dump(mode="json"),
        "files": [{"path": p, "size": len(files[p])} for p in sorted(files)],
        "status": status_of(ch, content_hash(meta, files)),
    }


@router.put("/challenges/{slug}")
def put_meta(slug: str, meta: ChallengeMeta, prune: bool = False, db: Session = Depends(get_session)):
    ch, _, files = load_challenge(db, slug)
    if meta.slug != slug:
        raise HTTPException(400, "slug cannot be changed")
    folders = {s.name for s in meta.services if not s.image}
    orphans = sorted(p for p in files if p.startswith("services/") and p.split("/")[1] not in folders)
    if orphans and not prune:
        raise HTTPException(409, {"orphans": orphans})
    ch.meta = meta.model_dump(mode="json")
    put_files(db, ch, remove=orphans)
    return {"ok": True}


@router.delete("/challenges/{slug}")
def remove_challenge(slug: str, db: Session = Depends(get_session)):
    ch, _, _ = load_challenge(db, slug)
    delete_challenge(db, ch)
    return {"ok": True}


@router.get("/challenges/{slug}/files/{path:path}")
def get_file(slug: str, path: str, db: Session = Depends(get_session)):
    ch, _, files = load_challenge(db, slug)
    if path not in files:
        raise HTTPException(404, "file not found")
    return Response(files[path], media_type="application/octet-stream")


@router.put("/challenges/{slug}/files/{path:path}")
async def put_file(slug: str, path: str, request: Request, db: Session = Depends(get_session)):
    def check():
        ch, meta, _ = load_challenge(db, slug)
        return ch, service_path(meta, path, need_rest=True)

    ch, path = await run_in_threadpool(check)
    body = bytearray()
    async for chunk in request.stream():
        body += chunk
        if len(body) > MAX_FILE:
            raise HTTPException(413, "file too large")
    await run_in_threadpool(put_files, db, ch, {path: bytes(body)})
    return {"ok": True}


@router.delete("/challenges/{slug}/files/{path:path}")
def delete_file(slug: str, path: str, db: Session = Depends(get_session)):
    ch, meta, files = load_challenge(db, slug)
    path = service_path(meta, path, need_rest=True)
    if path not in files:
        raise HTTPException(404, "file not found")
    put_files(db, ch, remove=[path])
    return {"ok": True}


@router.post("/challenges/{slug}/upload")
def upload(slug: str, dir: str, file: UploadFile, db: Session = Depends(get_session)):
    ch, meta, _ = load_challenge(db, slug)
    base = service_path(meta, dir, need_rest=False)
    name = basename(file.filename or "")
    if name.lower().endswith(".zip"):
        # compressed size is bounded by the same cap as the extracted total
        data = file.file.read(MAX_TOTAL + 1)
        if len(data) > MAX_TOTAL:
            raise HTTPException(400, "archive too large")
        try:
            new = {f"{base}/{p}": c for p, c in extract_zip(data).items()}
        except ValueError as e:
            raise HTTPException(400, str(e))
    else:
        if not name:
            raise HTTPException(400, "missing file name")
        try:
            target = safe_relpath(f"{base}/{name}")
        except ValueError as e:
            raise HTTPException(400, str(e))
        new = {target: bounded(file.file.read(MAX_FILE + 1), MAX_FILE)}
    put_files(db, ch, new)
    return {"files": sorted(new)}
