from datetime import datetime

from sqlalchemy import ForeignKey, LargeBinary, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, ts


class Challenge(Base):
    __tablename__ = "challenges"
    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(unique=True)
    meta: Mapped[dict] = mapped_column(JSONB)
    ctfd_id: Mapped[int | None]
    published_hash: Mapped[str | None]
    sync_hash: Mapped[str | None]
    created_at: Mapped[datetime] = ts(server_default=func.now())
    updated_at: Mapped[datetime] = ts(server_default=func.now(), onupdate=func.now())


class ChallengeFile(Base):
    __tablename__ = "challenge_files"
    challenge_id: Mapped[int] = mapped_column(ForeignKey("challenges.id", ondelete="CASCADE"), primary_key=True)
    path: Mapped[str] = mapped_column(primary_key=True)
    content: Mapped[bytes] = mapped_column(LargeBinary)
