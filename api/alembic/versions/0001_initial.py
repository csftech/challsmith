"""initial schema"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0001"
down_revision = None


def _ts(name, **kw):
    return sa.Column(name, sa.DateTime(timezone=True), **kw)


def upgrade() -> None:
    op.create_table(
        "challenges",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("slug", sa.String, nullable=False, unique=True),
        sa.Column("meta", JSONB, nullable=False),
        sa.Column("ctfd_id", sa.Integer),
        sa.Column("published_hash", sa.String),
        sa.Column("sync_hash", sa.String),
        _ts("created_at", nullable=False, server_default=sa.func.now()),
        _ts("updated_at", nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "challenge_files",
        sa.Column("challenge_id", sa.Integer, sa.ForeignKey("challenges.id", ondelete="CASCADE"), nullable=False),
        sa.Column("path", sa.String, nullable=False),
        sa.Column("content", sa.LargeBinary, nullable=False),
        sa.PrimaryKeyConstraint("challenge_id", "path"),
    )
    op.create_table(
        "web_sessions",
        sa.Column("token_hash", sa.String, primary_key=True),
        _ts("expires_at", nullable=False),
    )
    op.create_table(
        "settings",
        sa.Column("key", sa.String, primary_key=True),
        sa.Column("value", JSONB, nullable=False),
    )
    op.create_table(
        "publish_runs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("challenge_id", sa.Integer, sa.ForeignKey("challenges.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String, nullable=False),
        sa.Column("log", sa.Text, nullable=False, server_default=""),
        _ts("created_at", nullable=False, server_default=sa.func.now()),
        _ts("finished_at"),
    )


def downgrade() -> None:
    for t in ("publish_runs", "settings", "web_sessions", "challenge_files", "challenges"):
        op.drop_table(t)
