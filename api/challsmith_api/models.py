from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, LargeBinary, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _ts(**kw):
    return mapped_column(DateTime(timezone=True), **kw)


class Base(DeclarativeBase):
    pass


class Challenge(Base):
    __tablename__ = "challenges"
    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(unique=True)
    meta: Mapped[dict] = mapped_column(JSONB)
    ctfd_id: Mapped[int | None]
    published_hash: Mapped[str | None]
    sync_hash: Mapped[str | None]
    created_at: Mapped[datetime] = _ts(server_default=func.now())
    updated_at: Mapped[datetime] = _ts(server_default=func.now(), onupdate=func.now())


class ChallengeFile(Base):
    __tablename__ = "challenge_files"
    challenge_id: Mapped[int] = mapped_column(ForeignKey("challenges.id", ondelete="CASCADE"), primary_key=True)
    path: Mapped[str] = mapped_column(primary_key=True)
    content: Mapped[bytes] = mapped_column(LargeBinary)


class WebSession(Base):
    __tablename__ = "web_sessions"
    token_hash: Mapped[str] = mapped_column(primary_key=True)
    expires_at: Mapped[datetime] = _ts()


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(primary_key=True)
    value: Mapped[dict] = mapped_column(JSONB)


class PublishRun(Base):
    __tablename__ = "publish_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    challenge_id: Mapped[int] = mapped_column(ForeignKey("challenges.id", ondelete="CASCADE"))
    status: Mapped[str]  # running | succeeded | failed
    log: Mapped[str] = mapped_column(Text, server_default="")
    created_at: Mapped[datetime] = _ts(server_default=func.now())
    finished_at: Mapped[datetime | None] = _ts()
