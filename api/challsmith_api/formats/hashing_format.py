from blake3 import blake3
import json

from challsmith_api.formats import challenge_format


def _norm(data: bytes) -> bytes:
    return data if b"\0" in data else data.replace(b"\r\n", b"\n")


def _digest(head: bytes, files: dict[str, bytes]) -> str:
    h = blake3(head)
    for path in sorted(files):
        body = _norm(files[path])
        h.update(b"\0F\0" + path.encode() + b"\0" + str(len(body)).encode() + b"\0" + body)
    return h.hexdigest()


def content_hash(meta: challenge_format.ChallengeMeta, files: dict[str, bytes]) -> str:
    head = json.dumps(meta.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return _digest(head.encode(), files)


def service_hash(files: dict[str, bytes], service: str) -> str:
    prefix = f"services/{service}/"
    return _digest(b"", {p: b for p, b in files.items() if p.startswith(prefix)})
