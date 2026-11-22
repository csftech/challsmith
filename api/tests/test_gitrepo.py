import subprocess

import pytest

from challsmith_api.clients.git_client import GitError, GitRepo

TOKEN = "s3cret-token-value"


def git(*args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


def settings(remote, **over):
    return {"remote_url": str(remote), "username": "bob", "token": TOKEN, "branch": "main", "dir": "challenges",
            "author_name": "challsmith", "author_email": "challsmith@localhost", **over}


@pytest.fixture
def remote(tmp_path):
    path = tmp_path / "remote.git"
    git("init", "--bare", str(path), cwd=tmp_path)
    return path


def repo_for(tmp_path, remote, name="work", **over):
    return GitRepo(tmp_path / name, settings(remote, **over), {})


def folders(body=b"a"):
    return {"c1": {"challenge.yml": b"slug: c1\n", "src/index.php": body}}


def clone(tmp_path, remote, name="clone"):
    git("clone", "-b", "main", str(remote), name, cwd=tmp_path)
    git("config", "user.email", "x@x", cwd=tmp_path / name)
    git("config", "user.name", "x", cwd=tmp_path / name)
    return tmp_path / name


def test_push_then_clone_sees_files(tmp_path, remote):
    r = repo_for(tmp_path, remote).commit_and_push(folders(), "first", push=True)
    assert r["error"] is None and r["pushed"] and r["commit"]
    c = clone(tmp_path, remote)
    assert (c / "challenges/c1/challenge.yml").read_bytes() == b"slug: c1\n"
    assert (c / "challenges/c1/src/index.php").read_bytes() == b"a"


def test_unchanged_export_makes_no_commit(tmp_path, remote):
    repo = repo_for(tmp_path, remote)
    repo.commit_and_push(folders(), "first", push=True)
    r = repo.commit_and_push(folders(), "second", push=True)
    assert r["commit"] is None and r["error"] is None


def test_replace_folder_keeps_other_folders(tmp_path, remote):
    repo = repo_for(tmp_path, remote)
    repo.commit_and_push({**folders(), "c2": {"challenge.yml": b"x"}}, "first", push=True)
    repo.commit_and_push({"c1": {"challenge.yml": b"y"}}, "second", push=True)
    c = clone(tmp_path, remote)
    assert not (c / "challenges/c1/src").exists()
    assert (c / "challenges/c2/challenge.yml").exists()


def test_fetch_and_read_tree_sees_remote_change(tmp_path, remote):
    repo = repo_for(tmp_path, remote)
    assert repo.fetch() is False and repo.read_tree() == {}
    repo.commit_and_push(folders(), "first", push=True)
    c = clone(tmp_path, remote)
    (c / "challenges/c1/src/index.php").write_bytes(b"b")
    git("commit", "-am", "edit", cwd=c)
    git("push", "origin", "main", cwd=c)
    assert repo.fetch() is True
    assert repo.read_tree()["c1"]["src/index.php"] == b"b"


def test_missing_remote_returns_error_without_raising(tmp_path):
    r = repo_for(tmp_path, tmp_path / "nope.git").commit_and_push(folders(), "m", push=True)
    assert r["error"] and r["pushed"] is False and TOKEN not in r["error"]


def test_token_never_stored_or_leaked(tmp_path, remote):
    repo = repo_for(tmp_path, remote)
    repo.commit_and_push(folders(), "first", push=True)
    assert TOKEN not in (tmp_path / "work/.git/config").read_text()
    with pytest.raises(GitError) as e:
        repo_for(tmp_path, tmp_path / "nope.git", name="w2").fetch()
    assert TOKEN not in str(e.value)


def test_rejects_option_like_branch(tmp_path, remote):
    with pytest.raises(GitError):
        repo_for(tmp_path, remote, branch="--upload-pack=x").fetch()


def test_fetch_after_branch_deleted_drops_stale_tracking_ref(tmp_path, remote):
    repo = repo_for(tmp_path, remote)
    repo.commit_and_push(folders(), "first", push=True)
    assert repo.fetch() is True and repo.read_tree()
    git("branch", "-m", "main", "other", cwd=remote)
    assert repo.fetch() is False
    assert repo.read_tree() == {}


def test_symlink_invalidates_only_its_slug(tmp_path, remote):
    repo = repo_for(tmp_path, remote)
    repo.commit_and_push({**folders(), "c2": {"challenge.yml": b"x"}}, "first", push=True)
    c = clone(tmp_path, remote)
    (c / "challenges/c1/link").symlink_to("/etc/passwd")
    git("add", "-A", cwd=c)
    git("commit", "-m", "link", cwd=c)
    git("push", "origin", "main", cwd=c)
    repo.fetch()
    tree = repo.read_tree()
    assert list(tree) == ["c2"] and list(repo.invalid) == ["c1"]
