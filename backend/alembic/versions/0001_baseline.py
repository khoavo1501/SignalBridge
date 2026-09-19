"""baseline schema (PROJECT_PLAN.md §3.1)

Revision ID: 0001_baseline
Revises:
Create Date: 2026-09-19
"""

import sqlalchemy as sa
from alembic import op

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "gateways",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("gateway_id", sa.Text, nullable=False, unique=True),
        sa.Column("display_name", sa.Text, nullable=False),
        sa.Column("adapter_key", sa.Text, nullable=False, server_default="s7200_v1"),
        sa.Column("fw_version", sa.Text),
        sa.Column("hw_version", sa.Text),
        sa.Column("ip", sa.Text),
        sa.Column("mac", sa.Text),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "slaves",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "gateway_id",
            sa.BigInteger,
            sa.ForeignKey("gateways.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("slave_addr", sa.Integer, nullable=False),
        sa.Column("name", sa.Text),
        sa.Column("protocol", sa.Text),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("gateway_id", "slave_addr"),
    )

    op.create_table(
        "signal_defs",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "gateway_id",
            sa.BigInteger,
            sa.ForeignKey("gateways.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("key", sa.Text, nullable=False),
        sa.Column("display_name", sa.Text, nullable=False),
        sa.Column("unit", sa.Text),
        sa.Column("scale", sa.JSON),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("gateway_id", "key"),
        sa.CheckConstraint("kind IN ('analog','digital','counter')"),
    )

    op.create_table(
        "gateway_events",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "gateway_id",
            sa.BigInteger,
            sa.ForeignKey("gateways.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("slave_addr", sa.Integer),
        sa.Column("code", sa.Text, nullable=False),
        sa.Column("severity", sa.Text, nullable=False, server_default="info"),
        sa.Column("message", sa.Text),
        sa.Column("source", sa.Text),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw", sa.JSON),
    )
    op.create_index("idx_events_gw_time", "gateway_events", ["gateway_id", "received_at"])
    op.create_index("idx_events_code", "gateway_events", ["code", "received_at"])

    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("username", sa.Text, nullable=False, unique=True),
        sa.Column("password_hash", sa.Text, nullable=False),
        sa.Column("role", sa.Text, nullable=False, server_default="viewer"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("users")
    op.drop_index("idx_events_code", table_name="gateway_events")
    op.drop_index("idx_events_gw_time", table_name="gateway_events")
    op.drop_table("gateway_events")
    op.drop_table("signal_defs")
    op.drop_table("slaves")
    op.drop_table("gateways")
