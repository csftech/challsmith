"""challenge position"""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"


def upgrade() -> None:
    op.add_column("challenges", sa.Column("position", sa.Integer))
    op.execute(
        "UPDATE challenges c SET position = r.n FROM "
        "(SELECT id, row_number() OVER (ORDER BY created_at, id) AS n FROM challenges) r WHERE c.id = r.id"
    )
    op.alter_column("challenges", "position", nullable=False)


def downgrade() -> None:
    op.drop_column("challenges", "position")
