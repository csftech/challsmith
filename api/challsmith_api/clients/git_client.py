import os
import re
import shutil
import subprocess
import threading
from pathlib import Path

from challsmith_api.formats import archive_format

TIMEOUT = 120
_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")
_PUSH_HINT = "push failed; use the backup archive (GET /backup) to move the challenges instead."
_ASKPASS = '#!/bin/sh\ncase "$1" in\n  Username*) printf "%s\\n" "$CS_GIT_USERNAME" ;;\n  *) printf "%s\\n" "$CS_GIT_TOKEN" ;;\nesac\n'


class GitError(Exception):
    pass


def valid_ref(value: str) -> bool:
    return bool(_NAME.match(value)) and ".." not in value and not value.endswith(("/", ".lock"))


class GitRepo:
    # one process, one worker: git operations are serialised across all instances
    lock = threading.RLock()

    def __init__(self, workdir: Path, settings: dict, proxy_env: dict):
        self.workdir = Path(workdir)
        self.s = settings
        self.home = self.workdir.with_name(self.workdir.name + "-home")
        self.proxy_env = proxy_env
        for key in ("branch", "dir"):
            if not valid_ref(settings[key]):
                raise GitError(f"invalid git {key}: {settings[key]!r}")

    @property
    def branch(self) -> str:
        return self.s["branch"]

    def _env(self) -> dict:
        askpass = self.home / "askpass.sh"
        if not askpass.exists():
            self.home.mkdir(parents=True, exist_ok=True)
            askpass.write_text(_ASKPASS)
            askpass.chmod(0o700)
        env = {
            "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
            "HOME": str(self.home),
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_ALLOW_PROTOCOL": "http:https:file",  # blocks ext:: and friends
            "GIT_ASKPASS": str(askpass),
            "CS_GIT_USERNAME": self.s.get("username") or "",
            "CS_GIT_TOKEN": self.s.get("token") or "",
            "GIT_AUTHOR_NAME": self.s["author_name"],
            "GIT_AUTHOR_EMAIL": self.s["author_email"],
            "GIT_COMMITTER_NAME": self.s["author_name"],
            "GIT_COMMITTER_EMAIL": self.s["author_email"],
        }
        return {**env, **{k: v for k, v in self.proxy_env.items() if v}}

    def _scrub(self, text: str) -> str:
        token = self.s.get("token")
        return text.replace(token, "***") if token else text

    def _run(self, *args: str, check: bool = True) -> subprocess.CompletedProcess:
        self.workdir.mkdir(parents=True, exist_ok=True)
        try:
            p = subprocess.run(["git", *args], cwd=self.workdir, env=self._env(), capture_output=True, timeout=TIMEOUT)
        except subprocess.TimeoutExpired:
            raise GitError(f"git {args[0]} timed out after {TIMEOUT}s")
        if check and p.returncode != 0:
            out = self._scrub((p.stderr or p.stdout).decode(errors="replace").strip())
            raise GitError(f"git {args[0]} failed: {out}")
        return p

    def _init(self) -> None:
        if not (self.workdir / ".git").exists():
            self._run("init", "-q")
        self._run("symbolic-ref", "HEAD", f"refs/heads/{self.branch}")
        if self._run("remote", "get-url", "origin", check=False).returncode == 0:
            self._run("remote", "set-url", "origin", self.s["remote_url"])
        else:
            self._run("remote", "add", "origin", self.s["remote_url"])

    def fetch(self) -> bool:
        with self.lock:
            self._init()
            if not self._run("ls-remote", "--heads", "origin", f"refs/heads/{self.branch}").stdout.strip():
                return False
            self._run("fetch", "-q", "origin", f"+refs/heads/{self.branch}:refs/remotes/origin/{self.branch}")
            return True

    def read_tree(self) -> dict[str, dict[str, bytes]]:
        with self.lock:
            ref, d = f"refs/remotes/origin/{self.branch}", self.s["dir"]
            if self._run("rev-parse", "--verify", "-q", ref, check=False).returncode != 0:
                return {}
            if not self._run("ls-tree", ref, "--", f"{d}/").stdout.strip():
                return {}
            tar = self._run("archive", "--format=tar.gz", ref, "--", d).stdout
            try:
                files = archive_format.extract_tar_gz(tar)
            except ValueError as e:
                raise GitError(f"unusable repository content: {e}")
            out: dict[str, dict[str, bytes]] = {}
            for path, data in files.items():
                parts = path.removeprefix(d + "/").split("/", 1)
                if path.startswith(d + "/") and len(parts) == 2:
                    out.setdefault(parts[0], {})[parts[1]] = data
            return out

    def commit_and_push(self, folders: dict[str, dict[str, bytes]], message: str, push: bool) -> dict:
        with self.lock:
            try:
                return self._commit_and_push(folders, message, push)
            except GitError as e:
                return {"commit": None, "pushed": False, "error": str(e)}

    def _commit_and_push(self, folders, message, push) -> dict:
        has_remote = self.fetch()
        if has_remote:
            self._run("checkout", "-q", "-f", "-B", self.branch, f"origin/{self.branch}")
        else:
            self._run("update-ref", "-d", f"refs/heads/{self.branch}", check=False)
            self._run("read-tree", "--empty")
        self._run("clean", "-qfdx")
        root = self.workdir / self.s["dir"]
        for slug, folder in folders.items():
            shutil.rmtree(root / slug, ignore_errors=True)
            for rel, data in folder.items():
                target = root / slug / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
        self._run("add", "-A", "--", self.s["dir"])
        if not self._run("status", "--porcelain").stdout.strip():
            return {"commit": None, "pushed": False, "error": None}
        self._run("-c", "commit.gpgsign=false", "commit", "-q", "-m", message)
        sha = self._run("rev-parse", "HEAD").stdout.decode().strip()
        if not push:
            return {"commit": sha, "pushed": False, "error": None}
        p = self._run("push", "origin", f"{self.branch}:refs/heads/{self.branch}", check=False)
        if p.returncode != 0:
            out = self._scrub((p.stderr or p.stdout).decode(errors="replace").strip())
            return {"commit": sha, "pushed": False, "error": f"{out}\n{_PUSH_HINT}"}
        return {"commit": sha, "pushed": True, "error": None}
