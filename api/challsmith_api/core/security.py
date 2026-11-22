from datetime import datetime, timezone

from blake3 import blake3


def token_hash(token: str) -> str:
    return blake3(token.encode()).hexdigest()


def now() -> datetime:
    return datetime.now(timezone.utc)
