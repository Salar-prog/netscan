"""add api_keys.expires_at

Revision ID: f1a2b3c4d5e6
Revises: e7babb57447e
Create Date: 2026-08-27 06:00:00.000000

"""

from alembic import op
import sqlalchemy as sa

revision = "f1a2b3c4d5e6"
down_revision = "e7babb57447e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("api_keys") as batch_op:
        batch_op.add_column(sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("api_keys") as batch_op:
        batch_op.drop_column("expires_at")
