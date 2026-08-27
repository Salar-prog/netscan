"""add idempotency_records

Revision ID: e7babb57447e
Revises: e04c2d38a789
Create Date: 2026-08-27 04:22:11.049960

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'e7babb57447e'
down_revision: Union[str, Sequence[str], None] = 'e04c2d38a789'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'idempotency_records',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('idempotency_key', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('endpoint', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('request_hash', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('status_code', sa.Integer(), nullable=False),
        sa.Column('response_body', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_idempotency_records_idempotency_key',
        'idempotency_records',
        ['idempotency_key'],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index('ix_idempotency_records_idempotency_key', table_name='idempotency_records')
    op.drop_table('idempotency_records')
