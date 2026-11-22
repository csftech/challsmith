import secrets
import time
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from challsmith_api.clients import git_client
from challsmith_api.clients.git_client import GitError, GitRepo
from challsmith_api.core.config import get_settings
from challsmith_api.formats import archive_format, challenge_format, hashing_format
from challsmith_api.repositories import challenge_repository, setting_repository
from challsmith_api.services import challenge_service
from challsmith_api.services.errors import BadGateway, BadRequest, Conflict, NotFound, TooLarge

PREVIEW_TTL = 30 * 60
MAX_UPLOAD = 100 * 1024 * 1024
DEFAULT_GIT = {"remote_url": "", "username": "", "token": None, "branch": "main", "dir": "challenges",
               "author_name": "challsmith", "author_email": "challsmith@localhost"}
_URL_PREFIXES = ("https://", "http://", "file://", "/")

# preview_id -> {"expires", "items"}; in-process (single uvicorn worker), lost on restart
_previews: dict[str, dict] = {}


def git_root() -> Path:
    return Path(get_settings().data_dir) / "git"


def classify(base: str | None, db: str | None, src: str) -> str:
    if db is None:
        return "new"
    if db == src:
        return "unchanged"
    if db == base:
        return "source_changed"
    if src == base:
        return "db_changed"
    return "conflict"


# ---- git settings ----

def _git_settings(db: Session) -> dict:
    return {**DEFAULT_GIT, **(setting_repository.get(db, "git") or {})}


def get_git_settings(db: Session) -> dict:
    s = _git_settings(db)
    token = s.pop("token")
    return {**s, "token_set": bool(token)}


def put_git_settings(db: Session, values: dict) -> dict:
    if not values["remote_url"].startswith(_URL_PREFIXES):
        raise BadRequest("remote_url must start with https://, http:// or file:// (or be an absolute path)")
    for key in ("branch", "dir"):
        if not git_client.valid_ref(values[key]):
            raise BadRequest(f"invalid {key}")
    old = _git_settings(db)
    if values.get("token") is None:
        values["token"] = old["token"]
    setting_repository.put(db, "git", values)
    db.commit()
    return get_git_settings(db)


def _repo(db: Session) -> GitRepo:
    s = _git_settings(db)
    if not s["remote_url"]:
        raise BadRequest("the git remote is not configured")
    cfg = get_settings()
    proxy = {"http_proxy": cfg.upstream_http_proxy, "https_proxy": cfg.upstream_https_proxy,
             "no_proxy": cfg.upstream_no_proxy}
    try:
        return GitRepo(git_root(), s, proxy)
    except GitError as e:
        raise BadRequest(str(e))


# ---- export ----

def _folders(db: Session) -> dict[str, dict[str, bytes]]:
    out = {}
    for ch in challenge_repository.list_all(db):
        _, meta, files = challenge_service.load_challenge(db, ch.slug)
        out[ch.slug] = challenge_format.to_folder(meta, files)
    return out


def _hash_of_folder(folder: dict[str, bytes]) -> str:
    meta, files = challenge_format.from_folder(folder)
    return hashing_format.content_hash(meta, files)


def git_export(db: Session, push: bool) -> dict:
    repo = _repo(db)
    folders = _folders(db)
    hashes = {slug: _hash_of_folder(f) for slug, f in folders.items()}
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    result = repo.commit_and_push(folders, f"challsmith export {now}", push)
    # a failed push leaves git without these versions: moving the base would make the old git copy win later
    if result["error"] is None:
        for slug, h in hashes.items():
            challenge_repository.update_by_slug(db, slug, {"sync_hash": h})
        db.commit()
    return result


def backup(db: Session) -> tuple[str, bytes]:
    """The archive only; sync_hash stays, since the file may never be imported anywhere."""
    name = f"challsmith-backup-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.tar.gz"
    return name, archive_format.make_tar_gz(_folders(db))


# ---- preview / apply ----

def _prune() -> None:
    now = time.monotonic()
    for k in [k for k, v in _previews.items() if v["expires"] <= now]:
        del _previews[k]


def preview(db: Session, source: dict[str, dict[str, bytes]]) -> dict:
    items, stored = [], {}
    for slug, folder in sorted(source.items()):
        try:
            meta, files = challenge_format.from_folder(folder)
            if meta.slug != slug:
                raise ValueError(f"folder name {slug!r} does not match the slug {meta.slug!r} in challenge.yml")
            src_hash = hashing_format.content_hash(meta, files)
        except ValueError as e:
            items.append({"slug": slug, "status": "invalid", "error": str(e)})
            stored[slug] = {"status": "invalid"}
            continue
        ch = challenge_repository.get_by_slug(db, slug)
        db_hash = None if ch is None else challenge_service.current_hash(db, ch)
        status = classify(None if ch is None else ch.sync_hash, db_hash, src_hash)
        items.append({"slug": slug, "status": status})
        stored[slug] = {"status": status, "meta": meta, "files": files, "src_hash": src_hash, "db_hash": db_hash}
    _prune()
    pid = secrets.token_urlsafe(24)
    _previews[pid] = {"expires": time.monotonic() + PREVIEW_TTL, "items": stored}
    return {"preview_id": pid, "items": items}


def git_preview(db: Session) -> dict:
    repo = _repo(db)
    try:
        with GitRepo.lock:
            repo.fetch()
            source = repo.read_tree()
    except GitError as e:
        raise BadGateway(str(e))
    return preview(db, source)


def archive_preview(db: Session, data: bytes) -> dict:
    if len(data) > MAX_UPLOAD:
        raise TooLarge("archive too large")
    try:
        files = archive_format.extract_tar_gz(data)
    except ValueError as e:
        raise BadRequest(str(e))
    source: dict[str, dict[str, bytes]] = {}
    for path, content in files.items():
        parts = path.split("/", 2)
        if len(parts) != 3 or parts[0] != "challenges":
            raise BadRequest(f"unexpected path in archive: {path!r} (only challenges/<slug>/... is allowed)")
        source.setdefault(parts[1], {})[parts[2]] = content
    return preview(db, source)


def apply(db: Session, preview_id: str, decisions: dict[str, str]) -> dict:
    _prune()
    pv = _previews.get(preview_id)
    if pv is None:
        raise NotFound("preview not found or expired; run the preview again")
    items = pv["items"]
    missing = sorted(s for s, it in items.items() if it["status"] == "conflict" and s not in decisions)
    if missing:
        raise BadRequest(f"a decision (source or db) is required for: {', '.join(missing)}")
    for slug, it in items.items():
        if it["status"] == "invalid":
            continue
        ch = challenge_repository.get_by_slug_for_update(db, slug)
        now = None if ch is None else challenge_service.current_hash(db, ch)
        if now != it["db_hash"]:
            db.rollback()
            raise Conflict(f"{slug} changed since the preview; run the preview again")
    applied = []
    for slug, it in items.items():
        status = it["status"]
        if status == "conflict":
            status = "source_changed" if decisions[slug] == "source" else "keep_db"
        if status in ("new", "source_changed"):
            meta = it["meta"].model_dump(mode="json")
            ch = challenge_repository.get_by_slug(db, slug)
            if ch is None:
                challenge_repository.add(db, slug, meta, it["files"])
            else:
                challenge_repository.replace(db, ch, meta, it["files"])
            db.flush()
        elif status not in ("unchanged", "keep_db"):
            continue  # db_changed or invalid: nothing to do
        challenge_repository.update_by_slug(db, slug, {"sync_hash": it["src_hash"]})
        applied.append(slug)
    db.commit()
    del _previews[preview_id]
    return {"applied": applied}
