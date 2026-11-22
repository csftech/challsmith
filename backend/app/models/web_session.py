from datetime import datetime

from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, ts


class WebSession(Base):
    __tablename__ = "web_sessions"
    token_hash: Mapped[str] = mapped_column(primary_key=True)
    expires_at: Mapped[datetime] = ts()
