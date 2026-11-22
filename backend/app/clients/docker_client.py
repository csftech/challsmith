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

    def list_images(self, log: Log) -> list[tuple[str, str, int]]:
        """(image id, "repo:tag" or "" when untagged, size in bytes), one row per tag."""
        out = self._run(["docker", "images", "--no-trunc", "--format", "{{.ID}}\t{{.Repository}}\t{{.Tag}}"], log, quiet=True)
        rows = [line.split("\t") for line in out if line]
        ids = sorted({r[0] for r in rows})
        sizes: dict[str, int] = {}
        if ids:
            for line in self._run(["docker", "image", "inspect", "--format", "{{.Id}}\t{{.Size}}", *ids], log, quiet=True):
                if line:
                    i, size = line.split("\t")
                    sizes[i] = int(size)
        return [(i, "" if "<none>" in (repo, tag) else f"{repo}:{tag}", sizes.get(i, 0)) for i, repo, tag in rows]

    def container_image_ids(self, log: Log) -> set[str]:
        """Image ids of every container, running or stopped."""
        ids = self._run(["docker", "ps", "-a", "-q", "--no-trunc"], log, quiet=True)
        if not ids:
            return set()
        return {line for line in self._run(["docker", "inspect", "--format", "{{.Image}}", *ids], log, quiet=True) if line}

    def remove_image(self, ref: str, log: Log) -> None:
        # never -f: an image a container still uses must make this fail
        self._run(["docker", "image", "rm", "--", ref], log)

    def prune(self, log: Log) -> None:
        """Dangling images, all build cache, anonymous unused volumes (named volumes stay: no -a)."""
        self._run(["docker", "image", "prune", "-f"], log)
        self._run(["docker", "builder", "prune", "-af"], log)
        self._run(["docker", "volume", "prune", "-f"], log)

    def compose_container(self, project: str, service: str, mount: str, log: Log) -> tuple[str, str, str]:
        """(container id, image, volume mounted at `mount`) of a compose service's only container."""
        ids = self._run(["docker", "ps", "-a", "-q", "--filter", f"label=com.docker.compose.project={project}",
                         "--filter", f"label=com.docker.compose.service={service}"], log, quiet=True)
        if len(ids) != 1:
            raise DockerError(f"expected one {project} {service} container, found {len(ids)}")
        fmt = "{{.Config.Image}}\t{{range .Mounts}}{{if eq .Destination \"" + mount + "\"}}{{.Name}}{{end}}{{end}}"
        image, volume = self._run(["docker", "inspect", "--format", fmt, ids[0]], log, quiet=True)[0].split("\t")
        if not volume:
            raise DockerError(f"{service} container has no volume at {mount}")
        return ids[0], image, volume

    def stop_container(self, cid: str, log: Log) -> None:
        self._run(["docker", "stop", "--", cid], log)

    def start_container(self, cid: str, log: Log) -> None:
        self._run(["docker", "start", "--", cid], log)

    def registry_gc(self, image: str, volume: str, config: str, log: Log) -> None:
        """Run `registry garbage-collect --delete-untagged` on the registry volume (registry must be stopped)."""
        cmd = ["docker", "run", "--rm", "-v", f"{volume}:/var/lib/registry", "--entrypoint", "registry", image,
               "garbage-collect", "--delete-untagged", config]
        log("$ " + " ".join(cmd))
        out = self._run(cmd, log, quiet=True)  # one line per blob: summarise instead
        log(f"registry garbage-collect: {sum('eligible for deletion' in line for line in out)} blobs deleted")
