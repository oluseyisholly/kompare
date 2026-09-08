"""add giftcard tables

Revision ID: j0e1f2a3b4c5
Revises: i9d0e1f2a3b4
Create Date: 2026-09-01 16:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "j0e1f2a3b4c5"
down_revision: Union[str, None] = "i9d0e1f2a3b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


giftcard_type_enum = postgresql.ENUM(
    "ECODE",
    "PHYSICAL",
    "OTHER",
    name="giftcard_type",
    create_type=False,
)

giftcard_rate_unit_enum = postgresql.ENUM(
    "PER_FACE_VALUE_UNIT",
    name="giftcard_rate_unit",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    giftcard_type_enum.create(bind, checkfirst=True)
    giftcard_rate_unit_enum.create(bind, checkfirst=True)

    op.create_table(
        "giftcard_variants",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("provider_id", sa.Integer(), nullable=False),
        sa.Column("asset_id", sa.Integer(), nullable=False),
        sa.Column("external_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("brand_name", sa.String(), nullable=True),
        sa.Column("region", sa.String(), nullable=True),
        sa.Column("source_currency", sa.String(), nullable=True),
        sa.Column("card_type", giftcard_type_enum, nullable=True),
        sa.Column("minimum_face_value", sa.Numeric(precision=24, scale=8), nullable=True),
        sa.Column("maximum_face_value", sa.Numeric(precision=24, scale=8), nullable=True),
        sa.Column("terms_of_transaction", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"]),
        sa.ForeignKeyConstraint(["provider_id"], ["providers.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider_id", "external_id", name="uq_giftcard_variants_provider_external_id"),
    )
    op.create_index(op.f("ix_giftcard_variants_id"), "giftcard_variants", ["id"], unique=False)
    op.create_index(op.f("ix_giftcard_variants_provider_id"), "giftcard_variants", ["provider_id"], unique=False)
    op.create_index(op.f("ix_giftcard_variants_asset_id"), "giftcard_variants", ["asset_id"], unique=False)
    op.create_index(op.f("ix_giftcard_variants_external_id"), "giftcard_variants", ["external_id"], unique=False)
    op.create_index(op.f("ix_giftcard_variants_region"), "giftcard_variants", ["region"], unique=False)
    op.create_index(op.f("ix_giftcard_variants_source_currency"), "giftcard_variants", ["source_currency"], unique=False)
    op.create_index(op.f("ix_giftcard_variants_card_type"), "giftcard_variants", ["card_type"], unique=False)

    op.create_table(
        "giftcard_rates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("provider_id", sa.Integer(), nullable=False),
        sa.Column("giftcard_variant_id", sa.Integer(), nullable=False),
        sa.Column("fetch_run_id", sa.Integer(), nullable=True),
        sa.Column("raw_record_id", sa.Integer(), nullable=True),
        sa.Column("rate_value", sa.Numeric(precision=24, scale=8), nullable=False),
        sa.Column("rate_currency", sa.String(), server_default="NGN", nullable=False),
        sa.Column("rate_unit", giftcard_rate_unit_enum, server_default="PER_FACE_VALUE_UNIT", nullable=False),
        sa.Column("source_currency", sa.String(), nullable=True),
        sa.Column("minimum_face_value", sa.Numeric(precision=24, scale=8), nullable=True),
        sa.Column("maximum_face_value", sa.Numeric(precision=24, scale=8), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["fetch_run_id"], ["fetch_runs.id"]),
        sa.ForeignKeyConstraint(["giftcard_variant_id"], ["giftcard_variants.id"]),
        sa.ForeignKeyConstraint(["provider_id"], ["providers.id"]),
        sa.ForeignKeyConstraint(["raw_record_id"], ["raw_records.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_giftcard_rates_id"), "giftcard_rates", ["id"], unique=False)
    op.create_index(op.f("ix_giftcard_rates_provider_id"), "giftcard_rates", ["provider_id"], unique=False)
    op.create_index(op.f("ix_giftcard_rates_giftcard_variant_id"), "giftcard_rates", ["giftcard_variant_id"], unique=False)
    op.create_index(op.f("ix_giftcard_rates_fetch_run_id"), "giftcard_rates", ["fetch_run_id"], unique=False)
    op.create_index(op.f("ix_giftcard_rates_raw_record_id"), "giftcard_rates", ["raw_record_id"], unique=False)
    op.create_index(op.f("ix_giftcard_rates_rate_currency"), "giftcard_rates", ["rate_currency"], unique=False)
    op.create_index(op.f("ix_giftcard_rates_rate_unit"), "giftcard_rates", ["rate_unit"], unique=False)
    op.create_index(op.f("ix_giftcard_rates_source_currency"), "giftcard_rates", ["source_currency"], unique=False)
    op.create_index(op.f("ix_giftcard_rates_captured_at"), "giftcard_rates", ["captured_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_giftcard_rates_captured_at"), table_name="giftcard_rates")
    op.drop_index(op.f("ix_giftcard_rates_source_currency"), table_name="giftcard_rates")
    op.drop_index(op.f("ix_giftcard_rates_rate_unit"), table_name="giftcard_rates")
    op.drop_index(op.f("ix_giftcard_rates_rate_currency"), table_name="giftcard_rates")
    op.drop_index(op.f("ix_giftcard_rates_raw_record_id"), table_name="giftcard_rates")
    op.drop_index(op.f("ix_giftcard_rates_fetch_run_id"), table_name="giftcard_rates")
    op.drop_index(op.f("ix_giftcard_rates_giftcard_variant_id"), table_name="giftcard_rates")
    op.drop_index(op.f("ix_giftcard_rates_provider_id"), table_name="giftcard_rates")
    op.drop_index(op.f("ix_giftcard_rates_id"), table_name="giftcard_rates")
    op.drop_table("giftcard_rates")

    op.drop_index(op.f("ix_giftcard_variants_card_type"), table_name="giftcard_variants")
    op.drop_index(op.f("ix_giftcard_variants_source_currency"), table_name="giftcard_variants")
    op.drop_index(op.f("ix_giftcard_variants_region"), table_name="giftcard_variants")
    op.drop_index(op.f("ix_giftcard_variants_external_id"), table_name="giftcard_variants")
    op.drop_index(op.f("ix_giftcard_variants_asset_id"), table_name="giftcard_variants")
    op.drop_index(op.f("ix_giftcard_variants_provider_id"), table_name="giftcard_variants")
    op.drop_index(op.f("ix_giftcard_variants_id"), table_name="giftcard_variants")
    op.drop_table("giftcard_variants")

    bind = op.get_bind()
    giftcard_rate_unit_enum.drop(bind, checkfirst=True)
    giftcard_type_enum.drop(bind, checkfirst=True)
