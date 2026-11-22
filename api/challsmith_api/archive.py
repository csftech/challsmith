import gzip
import io
import stat
import tarfile
import zipfile

from .challenge_format import safe_relpath

MAX_MEMBERS = 2000
MAX_TOTAL = 100 * 1024 * 1024
_CHUNK = 1024 * 1024


def _read_capped(f, total: int) -> tuple[bytes, int]:
    """Read a member, aborting as soon as the running total exceeds the cap."""
    parts = []
    while chunk := f.read(_CHUNK):
        total += len(chunk)
        if total > MAX_TOTAL:
            raise ValueError("archive too large when extracted")
        parts.append(chunk)
    return b"".join(parts), total


def _name(raw: str) -> str:
    return safe_relpath(raw.rstrip("/"))


def extract_zip(data: bytes) -> dict[str, bytes]:
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as e:
        raise ValueError(f"invalid zip: {e}") from e
    with zf:
        infos = zf.infolist()
        if len(infos) > MAX_MEMBERS:
            raise ValueError("too many archive members")
        if sum(i.file_size for i in infos) > MAX_TOTAL:
            raise ValueError("archive too large when extracted")
        plan = []
        for i in infos:
            name = _name(i.filename)
            if stat.S_ISLNK(i.external_attr >> 16):
                raise ValueError(f"symlink not allowed: {i.filename!r}")
            plan.append((name, i))
        out: dict[str, bytes] = {}
        total = 0
        for name, i in plan:
            if i.is_dir():
                continue
            if name in out:
                raise ValueError(f"duplicate member: {name!r}")
            with zf.open(i) as f:
                out[name], total = _read_capped(f, total)
        return out


def extract_tar_gz(data: bytes) -> dict[str, bytes]:
    try:
        tf = tarfile.open(fileobj=io.BytesIO(data), mode="r:gz")
    except (tarfile.TarError, OSError, EOFError) as e:
        raise ValueError(f"invalid tar.gz: {e}") from e
    with tf:
        try:
            plan = []
            size = 0
            for m in tf:
                if len(plan) >= MAX_MEMBERS:
                    raise ValueError("too many archive members")
                if not (m.isfile() or m.isdir()):
                    raise ValueError(f"unsupported member type: {m.name!r}")
                plan.append((_name(m.name), m))
                size += m.size
                if size > MAX_TOTAL:
                    raise ValueError("archive too large when extracted")
            out: dict[str, bytes] = {}
            total = 0
            for name, m in plan:
                if m.isdir():
                    continue
                if name in out:
                    raise ValueError(f"duplicate member: {name!r}")
                out[name], total = _read_capped(tf.extractfile(m), total)
            return out
        except (tarfile.TarError, OSError, EOFError) as e:
            raise ValueError(f"invalid tar.gz: {e}") from e


def make_tar_gz(folders: dict[str, dict[str, bytes]]) -> bytes:
    files = {f"challenges/{slug}/{p}": b for slug, folder in folders.items() for p, b in folder.items()}
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz, tarfile.open(
        fileobj=gz, mode="w", format=tarfile.GNU_FORMAT
    ) as tf:
        for path in sorted(files):
            ti = tarfile.TarInfo(path)
            ti.size, ti.mtime, ti.mode = len(files[path]), 0, 0o644
            tf.addfile(ti, io.BytesIO(files[path]))
    return buf.getvalue()
