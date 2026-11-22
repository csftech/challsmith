from posixpath import basename

from fastapi.concurrency import run_in_threadpool
from fastapi import APIRouter, Depends, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import templates
from .archive import MAX_TOTAL, extract_zip
from .challenge_format import ChallengeMeta, safe_relpath
from .db import get_session
from .hashing import content_hash
from .models import Challenge, ChallengeFile

MAX_FILE = 20 * 1024 * 1024
router = APIRouter()


def _meta(ch: Challenge) -> ChallengeMeta:
    return ChallengeMeta.model_validate(ch.meta)


def _files(db: Session, ch: Challenge) -> dict[str, bytes]:
    rows = db.execute(select(ChallengeFile.path, ChallengeFile.content).where(ChallengeFile.challenge_id == ch.id))
    return {p: bytes(c) for p, c in rows}


def load_challenge(db: Session, slug: str) -> tuple[Challenge, ChallengeMeta, dict[str, bytes]]:
    ch = db.scalar(select(Challenge).where(Challenge.slug == slug))
    if ch is None:
        raise HTTPException(404, "challenge not found")
    return ch, _meta(ch), _files(db, ch)


def save_challenge(db: Session, slug: str, meta: ChallengeMeta, files: dict[str, bytes]) -> Challenge:
    """Create or overwrite a challenge (meta and every file) in one transaction."""
    ch = db.scalar(select(Challenge).where(Challenge.slug == slug))
    if ch is None:
        ch = Challenge(slug=slug, meta=meta.model_dump(mode="json"))
        db.add(ch)
        db.flush()
    else:
        ch.meta = meta.model_dump(mode="json")
        ch.updated_at = func.now()
        db.execute(delete(ChallengeFile).where(ChallengeFile.challenge_id == ch.id))
    db.add_all(ChallengeFile(challenge_id=ch.id, path=p, content=c) for p, c in files.items())
    db.commit()
    return ch


def current_hash(db: Session, challenge: Challenge) -> str:
    return content_hash(_meta(challenge), _files(db, challenge))


def status_of(challenge: Challenge, current: str) -> dict:
    if challenge.ctfd_id is None:
        publish = "draft"
    else:
        publish = "published" if challenge.published_hash == current else "modified"
    if challenge.sync_hash is None:
        sync = "never"
    else:
        sync = "synced" if challenge.sync_hash == current else "modified"
    return {"publish": publish, "sync": sync}


def delete_challenge(db: Session, ch: Challenge) -> None:
    # Task 6: when ch.ctfd_id is set, delete it on CTFd first (404 counts as deleted).
    db.delete(ch)
    db.commit()


def _put_files(db: Session, ch: Challenge, put: dict[str, bytes] | None = None, remove: list[str] | None = None) -> None:
    for path, content in (put or {}).items():
        db.merge(ChallengeFile(challenge_id=ch.id, path=path, content=content))
    if remove:
        db.execute(delete(ChallengeFile).where(ChallengeFile.challenge_id == ch.id, ChallengeFile.path.in_(remove)))
    ch.updated_at = func.now()
    db.commit()


def _service_path(meta: ChallengeMeta, raw: str, *, need_rest: bool) -> str:
    """Normalise a path that must live under services/<folder service>/ ."""
    try:
        path = safe_relpath(raw)
    except ValueError as e:
        raise HTTPException(400, str(e))
    parts = path.split("/")
    folders = {s.name for s in meta.services if not s.image}
    if parts[0] != "services" or len(parts) < 2 or parts[1] not in folders or (need_rest and len(parts) < 3):
        raise HTTPException(400, "path must be inside services/<service without image>/")
    return path


def _bounded(data: bytes, limit: int) -> bytes:
    if len(data) > limit:
        raise HTTPException(413, "file too large")
    return data


class NewChallenge(BaseModel):
    slug: str
    template: str
    name: str


@router.get("/challenges")
def list_challenges(db: Session = Depends(get_session)):
    # shortcut: hashes every challenge's files per call, cache if the list gets big
    out = []
    for ch in db.scalars(select(Challenge).order_by(Challenge.slug)):
        meta = _meta(ch)
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
    _put_files(db, ch, remove=orphans)
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
        return ch, _service_path(meta, path, need_rest=True)

    ch, path = await run_in_threadpool(check)
    body = bytearray()
    async for chunk in request.stream():
        body += chunk
        if len(body) > MAX_FILE:
            raise HTTPException(413, "file too large")
    await run_in_threadpool(_put_files, db, ch, {path: bytes(body)})
    return {"ok": True}


@router.delete("/challenges/{slug}/files/{path:path}")
def delete_file(slug: str, path: str, db: Session = Depends(get_session)):
    ch, meta, files = load_challenge(db, slug)
    path = _service_path(meta, path, need_rest=True)
    if path not in files:
        raise HTTPException(404, "file not found")
    _put_files(db, ch, remove=[path])
    return {"ok": True}


@router.post("/challenges/{slug}/upload")
def upload(slug: str, dir: str, file: UploadFile, db: Session = Depends(get_session)):
    ch, meta, _ = load_challenge(db, slug)
    base = _service_path(meta, dir, need_rest=False)
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
        new = {target: _bounded(file.file.read(MAX_FILE + 1), MAX_FILE)}
    _put_files(db, ch, new)
    return {"files": sorted(new)}
