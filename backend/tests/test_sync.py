import io
import subprocess
import tarfile

import pytest
from sqlalchemy import select

from app.clients.git_client import GitRepo
from app.utils import archive_util, hash_util
from app.schemas import challenge_schema
from app.models import Challenge
from app.services import challenge_service, sync_service
from test_auth import admin_env, bearer, login  # noqa: F401  (fixture reused)


@pytest.fixture
def api(client, db, tmp_path, monkeypatch):
    monkeypatch.setattr(sync_service, "git_root", lambda: tmp_path / "git")
    client.headers.update(bearer(login(client).json()["token"]))
    return client


def make(api, slug="c1"):
    assert api.post("/challenges", json={"slug": slug, "template": "php", "name": "C"}).status_code == 200


def folder_of(db, slug="c1"):
    _, meta, files = challenge_service.load_challenge(db, slug)
    return challenge_schema.to_folder(meta, files)


def folder_hash(folder):
    meta, files = challenge_schema.from_folder(folder)
    return hash_util.content_hash(meta, files)


def sync_hash(db, slug="c1"):
    db.expire_all()
    return db.scalar(select(Challenge.sync_hash).where(Challenge.slug == slug))


def set_base(db, base, slug="c1"):
    db.scalar(select(Challenge).where(Challenge.slug == slug)).sync_hash = base
    db.commit()


def rename(folder, name):
    meta, files = challenge_schema.from_folder(folder)
    return challenge_schema.to_folder(meta.model_copy(update={"name": name}), files)


def edit(db, name="edited", slug="c1"):
    _, meta, files = challenge_service.load_challenge(db, slug)
    challenge_service.save_challenge(db, slug, meta.model_copy(update={"name": name}), files)


def bare(tmp_path):
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
    return remote


def configure(api, remote):
    r = api.put("/settings/git", json={"remote_url": str(remote), "username": "u", "token": "tok"})
    assert r.status_code == 200, r.text


def archive_preview(api, data):
    return api.post("/sync/archive/preview", files={"file": ("b.tar.gz", data)})


@pytest.mark.parametrize("base,db,src,want", [
    (None, None, "s", "new"),
    ("b", None, "s", "new"),
    ("b", "s", "s", "unchanged"),
    ("b", "b", "s", "source_changed"),
    ("b", "d", "b", "db_changed"),
    ("b", "d", "s", "conflict"),
    (None, "d", "s", "conflict"),
    (None, "s", "s", "unchanged"),
])
def test_classify(base, db, src, want):
    assert sync_service.classify(base, db, src) == want


def test_git_settings_mask_token_and_keep_on_null(api):
    assert api.put("/settings/git", json={"remote_url": "https://x/y.git", "token": "tok"}).status_code == 200
    got = api.get("/settings/git").json()
    assert got["token_set"] is True and "token" not in got
    api.put("/settings/git", json={"remote_url": "https://x/z.git", "token": None})
    assert api.get("/settings/git").json()["token_set"] is True
    assert api.put("/settings/git", json={"remote_url": "ext::sh -c id"}).status_code == 400
    assert api.put("/settings/git", json={"remote_url": "https://x/y.git", "branch": "--x"}).status_code == 400
    for url in ("https://u@x/y.git", "https://u:p@x/y.git"):
        assert api.put("/settings/git", json={"remote_url": url}).status_code == 400


def test_archive_roundtrip_all_unchanged(api):
    make(api)
    make(api, "c2")
    data = api.get("/backup")
    assert data.headers["content-type"].startswith("application/gzip")
    assert "challsmith-backup-" in data.headers["content-disposition"]
    r = archive_preview(api, data.content)
    assert r.status_code == 200
    assert {i["status"] for i in r.json()["items"]} == {"unchanged"}


def test_archive_rejects_foreign_paths(api):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        tf.addfile(tarfile.TarInfo("other/file"), io.BytesIO(b""))
    assert archive_preview(api, buf.getvalue()).status_code == 400


def test_invalid_folder_is_reported_not_fatal(api, db):
    make(api)
    good = folder_of(db)
    data = archive_util.make_tar_gz({"c1": good, "bad": {"readme": b"x"}, "c9": good})
    items = {i["slug"]: i for i in archive_preview(api, data).json()["items"]}
    assert items["c1"]["status"] == "unchanged"
    assert items["bad"]["status"] == "invalid" and items["bad"]["error"]
    assert items["c9"]["status"] == "invalid"  # folder name differs from challenge.yml slug


def test_reserved_slug_is_invalid_at_preview(api, db):
    make(api)
    meta, files = challenge_schema.from_folder(folder_of(db))
    data = archive_util.make_tar_gz({"order": challenge_schema.to_folder(meta.model_copy(update={"slug": "order"}), files)})
    pv = archive_preview(api, data).json()
    assert pv["items"] == [{"slug": "order", "status": "invalid", "error": "slug 'order' is reserved"}]
    r = api.post("/sync/apply", json={"preview_id": pv["preview_id"], "decisions": {}})
    assert r.status_code == 200 and r.json()["applied"] == []
    assert db.scalar(select(Challenge).where(Challenge.slug == "order")) is None


def test_unknown_preview_is_404(api):
    assert api.post("/sync/apply", json={"preview_id": "nope", "decisions": {}}).status_code == 404


def conflict_setup(api, db):
    """A challenge whose db and source both moved off the base; returns (archive bytes, source folder)."""
    make(api)
    base_folder = folder_of(db)
    set_base(db, folder_hash(base_folder))
    edit(db, name="db-side")
    src = rename(base_folder, "src-side")
    return archive_util.make_tar_gz({"c1": src}), src


def test_apply_requires_conflict_decisions(api, db):
    data, _ = conflict_setup(api, db)
    pv = archive_preview(api, data).json()
    assert pv["items"][0]["status"] == "conflict"
    assert api.post("/sync/apply", json={"preview_id": pv["preview_id"], "decisions": {}}).status_code == 400
    assert challenge_service.load_challenge(db, "c1")[1].name == "db-side"


def test_apply_rejects_stale_preview(api, db):
    data, _ = conflict_setup(api, db)
    pid = archive_preview(api, data).json()["preview_id"]
    edit(db, name="third")
    assert api.post("/sync/apply", json={"preview_id": pid, "decisions": {"c1": "source"}}).status_code == 409
    assert challenge_service.load_challenge(db, "c1")[1].name == "third"


def test_conflict_choose_source_writes_and_keeps_base(api, db):
    data, src = conflict_setup(api, db)
    base = sync_hash(db)
    pid = archive_preview(api, data).json()["preview_id"]
    assert api.post("/sync/apply", json={"preview_id": pid, "decisions": {"c1": "source"}}).status_code == 200
    db.expire_all()
    assert challenge_service.load_challenge(db, "c1")[1].name == "src-side"
    assert sync_hash(db) == base  # archives never move the git base
    # the preview is single use
    assert api.post("/sync/apply", json={"preview_id": pid, "decisions": {"c1": "source"}}).status_code == 404


def test_conflict_keep_db_keeps_base(api, db):
    data, _ = conflict_setup(api, db)
    base = sync_hash(db)
    pid = archive_preview(api, data).json()["preview_id"]
    assert api.post("/sync/apply", json={"preview_id": pid, "decisions": {"c1": "db"}}).status_code == 200
    db.expire_all()
    assert challenge_service.load_challenge(db, "c1")[1].name == "db-side"
    assert sync_hash(db) == base


def test_new_challenge_from_archive_has_no_base(api, db):
    make(api)
    folder = folder_of(db)
    data = archive_util.make_tar_gz({"c1": folder})
    db.delete(db.scalar(select(Challenge)))
    db.commit()
    pv = archive_preview(api, data).json()
    assert pv["items"][0]["status"] == "new"
    assert api.post("/sync/apply", json={"preview_id": pv["preview_id"], "decisions": {}}).status_code == 200
    assert sync_hash(db) is None


def test_archive_apply_keeps_base_for_source_changed_and_unchanged(api, db):
    make(api)
    make(api, "c2")
    c1, c2 = folder_of(db), folder_of(db, "c2")
    set_base(db, "old1")
    set_base(db, "old2", "c2")
    data = archive_util.make_tar_gz({"c1": rename(c1, "newer"), "c2": c2})
    set_base(db, folder_hash(c1))  # c1: db == base, src differs -> source_changed
    pv = archive_preview(api, data).json()
    assert {i["slug"]: i["status"] for i in pv["items"]} == {"c1": "source_changed", "c2": "unchanged"}
    assert api.post("/sync/apply", json={"preview_id": pv["preview_id"], "decisions": {}}).status_code == 200
    assert challenge_service.load_challenge(db, "c1")[1].name == "newer"
    assert sync_hash(db) == folder_hash(c1) and sync_hash(db, "c2") == "old2"


def test_backup_import_does_not_let_git_overwrite_newer_content(api, db, tmp_path):
    make(api)
    h1 = folder_of(db)
    configure(api, bare(tmp_path))
    assert api.post("/sync/git/export", json={"push": True}).json()["pushed"] is True  # home: base H1
    data = archive_util.make_tar_gz({"c1": rename(h1, "h2")})  # the company's backup, content H2
    pv = archive_preview(api, data).json()
    assert pv["items"][0]["status"] == "source_changed"
    assert api.post("/sync/apply", json={"preview_id": pv["preview_id"], "decisions": {}}).status_code == 200
    assert challenge_service.load_challenge(db, "c1")[1].name == "h2"
    pv = api.post("/sync/git/preview").json()
    assert pv["items"][0]["status"] == "db_changed"
    assert api.post("/sync/apply", json={"preview_id": pv["preview_id"], "decisions": {}}).status_code == 200
    db.expire_all()
    assert challenge_service.load_challenge(db, "c1")[1].name == "h2"


def test_backup_download_keeps_base(api, db, tmp_path):
    make(api)
    b_folder = folder_of(db)
    base = folder_hash(b_folder)
    set_base(db, base)
    edit(db)
    assert api.get("/backup").status_code == 200
    assert sync_hash(db) == base
    remote = bare(tmp_path)
    configure(api, remote)
    GitRepo(tmp_path / "pusher", {"remote_url": str(remote), "branch": "main", "dir": "challenges",
                                  "author_name": "a", "author_email": "a@a"}, {}).commit_and_push(
        {"c1": b_folder}, "seed", push=True)
    r = api.post("/sync/git/preview")
    assert r.status_code == 200, r.text
    assert r.json()["items"][0]["status"] == "db_changed"


def test_git_export_sets_base_and_preview_unchanged(api, db, tmp_path):
    make(api)
    configure(api, bare(tmp_path))
    r = api.post("/sync/git/export", json={"push": True})
    assert r.status_code == 200 and r.json()["pushed"] is True, r.text
    assert sync_hash(db) == folder_hash(folder_of(db))
    assert [i["status"] for i in api.post("/sync/git/preview").json()["items"]] == ["unchanged"]


def test_git_export_push_failure_keeps_base(api, db, tmp_path):
    make(api)
    configure(api, tmp_path / "missing.git")
    r = api.post("/sync/git/export", json={"push": True})
    assert r.status_code == 200 and r.json()["error"]
    assert sync_hash(db) is None


def test_git_export_without_push_keeps_base(api, db, tmp_path):
    make(api)
    remote = bare(tmp_path)
    configure(api, remote)
    assert api.post("/sync/git/export", json={"push": True}).json()["pushed"] is True
    base = sync_hash(db)
    edit(db)
    r = api.post("/sync/git/export", json={"push": False}).json()
    assert r["commit"] and r["pushed"] is False
    assert sync_hash(db) == base
    assert api.post("/sync/git/preview").json()["items"][0]["status"] == "db_changed"


def test_git_preview_symlink_invalidates_only_that_slug(api, db, tmp_path):
    make(api)
    make(api, "c2")
    remote = bare(tmp_path)
    configure(api, remote)
    api.post("/sync/git/export", json={"push": True})
    subprocess.run(["git", "clone", "-q", "-b", "main", str(remote), "cl"], cwd=tmp_path, check=True)
    cl = tmp_path / "cl"
    (cl / "challenges/c1/link").symlink_to("/etc/passwd")
    for cmd in (["add", "-A"], ["-c", "user.name=x", "-c", "user.email=x@x", "commit", "-qm", "l"], ["push", "-q"]):
        subprocess.run(["git", *cmd], cwd=cl, check=True)
    items = {i["slug"]: i for i in api.post("/sync/git/preview").json()["items"]}
    assert items["c1"]["status"] == "invalid" and items["c1"]["error"]
    assert items["c2"]["status"] == "unchanged"


def test_preview_store_is_bounded_and_apply_is_single_use(api, db):
    make(api)
    data = archive_util.make_tar_gz({"c1": folder_of(db)})
    ids = [archive_preview(api, data).json()["preview_id"] for _ in range(sync_service.MAX_PREVIEWS + 2)]
    assert len(sync_service._previews) == sync_service.MAX_PREVIEWS
    assert api.post("/sync/apply", json={"preview_id": ids[0], "decisions": {}}).status_code == 404
    assert api.post("/sync/apply", json={"preview_id": ids[-1], "decisions": {}}).status_code == 200
    assert api.post("/sync/apply", json={"preview_id": ids[-1], "decisions": {}}).status_code == 404
