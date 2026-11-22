from sqlalchemy import DateTime
from sqlalchemy.orm import DeclarativeBase, mapped_column


def ts(**kw):
    return mapped_column(DateTime(timezone=True), **kw)


class Base(DeclarativeBase):
    pass
