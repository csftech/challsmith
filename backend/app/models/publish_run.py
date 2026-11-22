from datetime import datetime

from sqlalchemy import ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, ts


class PublishRun(Base):
    __tablename__ = "publish_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    challenge_id: Mapped[int] = mapped_column(ForeignKey("challenges.id", ondelete="CASCADE"))
    status: Mapped[str]  # running | succeeded | failed
    log: Mapped[str] = mapped_column(Text, server_default="")
    created_at: Mapped[datetime] = ts(server_default=func.now())
    finished_at: Mapped[datetime | None] = ts()
