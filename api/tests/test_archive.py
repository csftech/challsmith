import io
import stat
import tarfile
import zipfile

import pytest

from challsmith_api.formats import archive_format


def _zip(members: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for n, b in members.items():
            z.writestr(n, b)
    return buf.getvalue()


def _tar(*infos: tuple[tarfile.TarInfo, bytes]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as t:
        for ti, b in infos:
            t.addfile(ti, io.BytesIO(b))
    return buf.getvalue()


def _ti(name, **kw):
    ti = tarfile.TarInfo(name)
    for k, v in kw.items():
        setattr(ti, k, v)
    return ti


def _zip_attr(name: str, fmt: int) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        zi = zipfile.ZipInfo(name)
        zi.external_attr = (fmt | 0o644) << 16
        z.writestr(zi, b"x")
    return buf.getvalue()


def _bomb() -> bytes:
    """A zip holding 101 MiB of zeros, streamed so it is never held in memory."""
    buf = io.BytesIO()
    zeros = bytes(1024 * 1024)
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        with z.open("big", "w", force_zip64=True) as f:
            for _ in range(101):
                f.write(zeros)
    return buf.getvalue()


@pytest.mark.parametrize("data,fn", [
    (_zip({"../evil": b"x"}), archive_format.extract_zip),
    (_tar((_ti("/etc/x", size=1), b"x")), archive_format.extract_tar_gz),
    (_tar((_ti("l", type=tarfile.SYMTYPE, linkname="/etc/passwd"), b"")), archive_format.extract_tar_gz),
    (_tar((_ti("h", type=tarfile.LNKTYPE, linkname="a"), b"")), archive_format.extract_tar_gz),
    (_bomb(), archive_format.extract_zip),
    (_zip_attr("l", stat.S_IFLNK), archive_format.extract_zip),
    (_zip_attr("p", stat.S_IFIFO), archive_format.extract_zip),
    (_zip_attr("c", stat.S_IFCHR), archive_format.extract_zip),
    (_zip({"a": b"hello"}).replace(b"hello", b"jello"), archive_format.extract_zip),
], ids=["zip-dotdot", "tar-abs", "tar-symlink", "tar-hardlink", "zip-bomb",
        "zip-symlink", "zip-fifo", "zip-device", "zip-bad-crc"])
def test_extract_rejects(data, fn):
    with pytest.raises(ValueError):
        fn(data)


def test_too_many_members():
    with pytest.raises(ValueError):
        archive_format.extract_zip(_zip({f"f{i}": b"" for i in range(2001)}))


def test_extract_ok_with_dirs():
    assert archive_format.extract_zip(_zip({"d/": b"", "d/a": b"1"})) == {"d/a": b"1"}


def test_make_tar_gz_roundtrip():
    x = {"challenge.yml": b"a", "services/app/i.php": b"b"}
    out = archive_format.make_tar_gz({"s": x})
    assert archive_format.extract_tar_gz(out) == {f"challenges/s/{p}": b for p, b in x.items()}
    assert archive_format.make_tar_gz({"s": x}) == out


def test_zip_running_byte_guard(monkeypatch):
    # zipfile itself bounds reads by header size, so exercise the guard with a lowered cap
    monkeypatch.setattr(archive_format, "MAX_TOTAL", 10)
    with pytest.raises(ValueError, match="too large"):
        archive_format._read_capped(io.BytesIO(b"x" * 11), 0)


def test_root_dir_member_ignored():
    assert archive_format.extract_zip(_zip({"./": b"", "a": b"1"})) == {"a": b"1"}
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as t:
        t.addfile(_ti(".", type=tarfile.DIRTYPE))
        t.addfile(_ti("a", size=1), io.BytesIO(b"1"))
    assert archive_format.extract_tar_gz(buf.getvalue()) == {"a": b"1"}
