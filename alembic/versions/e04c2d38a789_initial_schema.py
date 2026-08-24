"""initial schema

Revision ID: e04c2d38a789
Revises: 
Create Date: 2026-08-21 05:22:52.793340

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e04c2d38a789'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "subnets",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("cidr", sa.String(), index=True, unique=True, nullable=False),
        sa.Column("name", sa.String(), index=True, nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("scan_interval_minutes", sa.Integer(), server_default="60"),
        sa.Column("miss_threshold", sa.Integer(), server_default="3"),
        sa.Column("quarantine_hours", sa.Integer(), server_default="48"),
        sa.Column("is_active", sa.Boolean(), server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "ip_addresses",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("subnet_id", sa.Uuid(), sa.ForeignKey("subnets.id"), index=True, nullable=False),
        sa.Column("ip", sa.String(), index=True, nullable=False),
        sa.Column("status", sa.String(), index=True, nullable=False),
        sa.Column("hostname", sa.String(), index=True, nullable=True),
        sa.Column("mac_address", sa.String(), index=True, nullable=True),
        sa.Column("mac_vendor", sa.String(), nullable=True),
        sa.Column("open_ports", sa.JSON(), nullable=True),
        sa.Column("discovery_method", sa.String(), nullable=False),
        sa.Column("consecutive_misses", sa.Integer(), server_default="0"),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_scanned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("custom_metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "scan_jobs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("subnet_id", sa.Uuid(), sa.ForeignKey("subnets.id"), index=True, nullable=False),
        sa.Column("status", sa.String(), index=True, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("total_ips", sa.Integer(), server_default="0"),
        sa.Column("active_ips", sa.Integer(), server_default="0"),
        sa.Column("uncertain_ips", sa.Integer(), server_default="0"),
        sa.Column("available_ips", sa.Integer(), server_default="0"),
        sa.Column("reserved_ips", sa.Integer(), server_default="0"),
        sa.Column("error_message", sa.String(), nullable=True),
        sa.Column("triggered_by", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "ip_history",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("ip_address_id", sa.Uuid(), sa.ForeignKey("ip_addresses.id"), index=True, nullable=False),
        sa.Column("event_type", sa.String(), index=True, nullable=False),
        sa.Column("old_status", sa.String(), nullable=True),
        sa.Column("new_status", sa.String(), nullable=True),
        sa.Column("probe_details", sa.JSON(), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), index=True, nullable=False),
    )

    op.create_table(
        "webhooks",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("url", sa.String(), nullable=False),
        sa.Column("secret", sa.String(), nullable=False),
        sa.Column("events", sa.JSON(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "api_keys",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("key_hash", sa.String(), index=True, unique=True, nullable=False),
        sa.Column("prefix", sa.String(), index=True, nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="1"),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("api_keys")
    op.drop_table("webhooks")
    op.drop_table("ip_history")
    op.drop_table("scan_jobs")
    op.drop_table("ip_addresses")
    op.drop_table("subnets")
