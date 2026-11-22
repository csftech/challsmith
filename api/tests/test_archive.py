import io
import tarfile
import zipfile

import pytest

from challsmith_api.archive import extract_tar_gz, extract_zip, make_tar_gz


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


def _bomb() -> bytes:
    """A zip holding 101 MiB of zeros, streamed so it is never held in memory."""
    buf = io.BytesIO()
    zeros = bytes(1024 * 1024)
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        with z.open("big", "w", force_zip64=True) as f:
            for _ in range(101):
                f.write(zeros)
    return buf.getvalue()


def _lying_zip() -> bytes:
    """Same bomb, but the headers claim the member is 1 byte."""
    data = _bomb()
    size = zipfile.ZipFile(io.BytesIO(data)).infolist()[0].file_size.to_bytes(8, "little")
    assert size in data
    return data.replace(size, (1).to_bytes(8, "little"))


@pytest.mark.parametrize("data,fn", [
    (_zip({"../evil": b"x"}), extract_zip),
    (_tar((_ti("/etc/x", size=1), b"x")), extract_tar_gz),
    (_tar((_ti("l", type=tarfile.SYMTYPE, linkname="/etc/passwd"), b"")), extract_tar_gz),
    (_tar((_ti("h", type=tarfile.LNKTYPE, linkname="a"), b"")), extract_tar_gz),
    (_bomb(), extract_zip),
    (_lying_zip(), extract_zip),
], ids=["zip-dotdot", "tar-abs", "tar-symlink", "tar-hardlink", "zip-bomb", "zip-lying-header"])
def test_extract_rejects(data, fn):
    with pytest.raises(ValueError):
        fn(data)


def test_too_many_members():
    with pytest.raises(ValueError):
        extract_zip(_zip({f"f{i}": b"" for i in range(2001)}))


def test_extract_ok_with_dirs():
    assert extract_zip(_zip({"d/": b"", "d/a": b"1"})) == {"d/a": b"1"}


def test_make_tar_gz_roundtrip():
    x = {"challenge.yml": b"a", "services/app/i.php": b"b"}
    out = make_tar_gz({"s": x})
    assert extract_tar_gz(out) == {f"challenges/s/{p}": b for p, b in x.items()}
    assert make_tar_gz({"s": x}) == out
