"""add provider metrics

Revision ID: v2d3e4f5a6b7
Revises: u1c2d3e4f5a6
Create Date: 2026-10-09
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "v2d3e4f5a6b7"
down_revision: Union[str, None] = "u1c2d3e4f5a6"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    bind = op.get_bind()
    existing_tables = set(sa.inspect(bind).get_table_names())

    if "provider_metrics" not in existing_tables:
        op.create_table(
            "provider_metrics",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("provider_id", sa.Integer(), nullable=False),
            sa.Column("average_rating", sa.Numeric(4, 2), nullable=True),
            sa.Column("review_count", sa.Integer(), server_default="0", nullable=False),
            sa.Column("feed_health", sa.String(), server_default="unknown", nullable=False),
            sa.Column("coverage_score", sa.Integer(), server_default="0", nullable=False),
            sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_successful_run_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_failed_run_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_error_message", sa.Text(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                onupdate=sa.func.now(),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(["provider_id"], ["providers.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("provider_id", name="uq_provider_metrics_provider_id"),
        )
        op.create_index(op.f("ix_provider_metrics_id"), "provider_metrics", ["id"], unique=False)
        op.create_index(
            op.f("ix_provider_metrics_provider_id"),
            "provider_metrics",
            ["provider_id"],
            unique=False,
        )


def downgrade() -> None:
    op.drop_index(op.f("ix_provider_metrics_provider_id"), table_name="provider_metrics")
    op.drop_index(op.f("ix_provider_metrics_id"), table_name="provider_metrics")
    op.drop_table("provider_metrics")
