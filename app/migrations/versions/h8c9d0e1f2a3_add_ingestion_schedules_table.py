"""add ingestion schedules table

Revision ID: h8c9d0e1f2a3
Revises: g7b8c9d0e1f2
Create Date: 2026-08-31 17:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "h8c9d0e1f2a3"
down_revision: Union[str, None] = "g7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


ingestion_job_type_enum = postgresql.ENUM(
    "MARKET_DATA",
    "KYC",
    "FEES",
    name="ingestion_job_type",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    ingestion_job_type_enum.create(bind, checkfirst=True)

    op.create_table(
        "ingestion_schedules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("provider_id", sa.Integer(), nullable=False),
        sa.Column("job_type", ingestion_job_type_enum, nullable=False),
        sa.Column("interval_minutes", sa.Integer(), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.String(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["provider_id"], ["providers.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider_id", "job_type", name="uq_ingestion_schedules_provider_job_type"),
    )
    op.create_index(op.f("ix_ingestion_schedules_id"), "ingestion_schedules", ["id"], unique=False)
    op.create_index(op.f("ix_ingestion_schedules_provider_id"), "ingestion_schedules", ["provider_id"], unique=False)
    op.create_index(op.f("ix_ingestion_schedules_job_type"), "ingestion_schedules", ["job_type"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_ingestion_schedules_job_type"), table_name="ingestion_schedules")
    op.drop_index(op.f("ix_ingestion_schedules_provider_id"), table_name="ingestion_schedules")
    op.drop_index(op.f("ix_ingestion_schedules_id"), table_name="ingestion_schedules")
    op.drop_table("ingestion_schedules")

    bind = op.get_bind()
    ingestion_job_type_enum.drop(bind, checkfirst=True)
