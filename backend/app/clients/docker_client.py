import subprocess
from collections import deque
from collections.abc import Callable
from pathlib import Path

Log = Callable[[str], None]


class DockerError(Exception):
    pass


class DockerOps:
    def __init__(self, http_proxy: str = "", https_proxy: str = "", no_proxy: str = ""):
        pairs = {"HTTP_PROXY": http_proxy, "http_proxy": http_proxy, "HTTPS_PROXY": https_proxy,
                 "https_proxy": https_proxy, "NO_PROXY": no_proxy, "no_proxy": no_proxy}
        self._build_args = {k: v for k, v in pairs.items() if v}

    def _run(self, cmd: list[str], log: Log, shown: str | None = None, quiet: bool = False) -> list[str]:
        """Run cmd, streaming merged stdout/stderr to log; raise DockerError on a non-zero exit."""
        if not quiet:
            log("$ " + (shown or " ".join(cmd)))
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace")
        lines: list[str] = []
        tail: deque[str] = deque(maxlen=20)
        for line in p.stdout:
            line = line.rstrip("\n")
            lines.append(line)
            tail.append(line)
            if not quiet:
                log(line)
        if p.wait() != 0:
            raise DockerError(f"{cmd[0]} {cmd[1]} exited with {p.returncode}:\n" + "\n".join(tail))
        return lines

    def build(self, context_dir: Path, tag: str, log: Log) -> None:
        args = [a for k, v in self._build_args.items() for a in ("--build-arg", f"{k}={v}")]
        cmd = ["docker", "build", "--progress=plain", "-t", tag, *args, str(context_dir)]
        redacted = ["docker", "build", "--progress=plain", "-t", tag,
                    *[a for k in self._build_args for a in ("--build-arg", f"{k}=***")], str(context_dir)]
        self._run(cmd, log, " ".join(redacted))

    def push(self, tag: str, log: Log) -> None:
        self._run(["docker", "push", "--", tag], log)

    def pull(self, image: str, log: Log) -> None:
        self._run(["docker", "pull", "--", image], log)

    def tag(self, src: str, dst: str, log: Log) -> None:
        self._run(["docker", "tag", "--", src, dst], log)

    def remove_containers(self, name_prefix: str, log: Log) -> int:
        ids = self._run(["docker", "ps", "-a", "-q", "--filter", f"name=^{name_prefix}"], log, quiet=True)
        if ids:
            self._run(["docker", "rm", "-f", *ids], log)
        return len(ids)

    def remove_networks(self, name_prefix: str, log: Log) -> int:
        ids = self._run(["docker", "network", "ls", "-q", "--filter", f"name=^{name_prefix}"], log, quiet=True)
        if ids:
            self._run(["docker", "network", "rm", *ids], log)
        return len(ids)
