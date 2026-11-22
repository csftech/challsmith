import gzip
import io
import posixpath
import stat
import tarfile
import zipfile
import zlib

from app.schemas import challenge_schema

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


_ZIP_ERRORS = (zipfile.BadZipFile, zlib.error, NotImplementedError, RuntimeError, OSError, EOFError)


def _name(raw: str, is_dir: bool) -> str | None:
    """Safe relative name, or None for the root directory member ("." or "./")."""
    if is_dir and posixpath.normpath(raw) == ".":
        return None
    return challenge_schema.safe_relpath(raw.rstrip("/"))


def extract_zip(data: bytes) -> dict[str, bytes]:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            infos = zf.infolist()
            if len(infos) > MAX_MEMBERS:
                raise ValueError("too many archive members")
            if sum(i.file_size for i in infos) > MAX_TOTAL:
                raise ValueError("archive too large when extracted")
            plan = []
            for i in infos:
                name = _name(i.filename, i.is_dir())
                if stat.S_IFMT(i.external_attr >> 16) not in (0, stat.S_IFREG, stat.S_IFDIR):
                    raise ValueError(f"unsupported member type: {i.filename!r}")
                if name is not None and not i.is_dir():
                    plan.append((name, i))
            out: dict[str, bytes] = {}
            total = 0
            for name, i in plan:
                if name in out:
                    raise ValueError(f"duplicate member: {name!r}")
                with zf.open(i) as f:
                    out[name], total = _read_capped(f, total)
            return out
    except _ZIP_ERRORS as e:
        raise ValueError(f"invalid zip: {e}") from e


def extract_tar_gz(data: bytes) -> dict[str, bytes]:
    try:
        tf = tarfile.open(fileobj=io.BytesIO(data), mode="r:gz")
    except (tarfile.TarError, OSError, EOFError) as e:
        raise ValueError(f"invalid tar.gz: {e}") from e
    with tf:
        try:
            plan = []
            size = count = 0
            for m in tf:
                count += 1
                if count > MAX_MEMBERS:
                    raise ValueError("too many archive members")
                if not (m.isfile() or m.isdir()):
                    raise ValueError(f"unsupported member type: {m.name!r}")
                name = _name(m.name, m.isdir())
                if name is not None and m.isfile():
                    plan.append((name, m))
                size += m.size
                if size > MAX_TOTAL:
                    raise ValueError("archive too large when extracted")
            out: dict[str, bytes] = {}
            total = 0
            for name, m in plan:
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
