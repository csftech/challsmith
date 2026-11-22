import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from challsmith_api.core.db import get_engine
from challsmith_api.main import app
from challsmith_api.models import Base


@pytest.fixture(scope="session", autouse=True)
def _migrated():
    command.upgrade(Config("alembic.ini"), "head")


@pytest.fixture
def db():
    with Session(get_engine()) as session:
        yield session
    names = ", ".join(t.name for t in Base.metadata.sorted_tables)
    with get_engine().begin() as conn:
        conn.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))


@pytest.fixture
def client():
    return TestClient(app)
