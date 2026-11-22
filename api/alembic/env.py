from alembic import context
from sqlalchemy import create_engine

from challsmith_api.config import get_settings
from challsmith_api.models import Base

engine = create_engine(get_settings().database_url)
with engine.connect() as conn:
    context.configure(connection=conn, target_metadata=Base.metadata)
    with context.begin_transaction():
        context.run_migrations()
