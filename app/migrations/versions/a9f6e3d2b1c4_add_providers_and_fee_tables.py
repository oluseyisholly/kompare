"""add providers and fee tables

Revision ID: a9f6e3d2b1c4
Revises: 61c846c055cd
Create Date: 2026-08-25 12:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "a9f6e3d2b1c4"
down_revision: Union[str, None] = "61c846c055cd"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


market_category_enum = postgresql.ENUM(
    "CRYPTO",
    "GIFTCARD",
    "FX",
    name="market_category",
    create_type=False,
)


fee_category_enum = postgresql.ENUM(
    "TRADE",
    "WITHDRAWAL",
    "DEPOSIT",
    "TRANSFER",
    "SWAP",
    "NETWORK",
    name="fee_category",
    create_type=False,
)

fee_type_enum = postgresql.ENUM(
    "FLAT",
    "PERCENTAGE",
    "SPREAD",
    "TIERED",
    name="fee_type",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    fee_category_enum.create(bind, checkfirst=True)
    fee_type_enum.create(bind, checkfirst=True)

    op.create_table(
        "providers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("logo_url", sa.String(), nullable=True),
        sa.Column("website_url", sa.String(), nullable=True),
        sa.Column("category", market_category_enum, nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("has_adapter", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_providers_id"), "providers", ["id"], unique=False)
    op.create_index(op.f("ix_providers_slug"), "providers", ["slug"], unique=True)
    op.create_index(op.f("ix_providers_category"), "providers", ["category"], unique=False)

    op.bulk_insert(
        sa.table(
            "providers",
            sa.column("slug", sa.String()),
            sa.column("name", sa.String()),
            sa.column("description", sa.Text()),
            sa.column("website_url", sa.String()),
            sa.column("category", market_category_enum),
            sa.column("is_active", sa.Boolean()),
            sa.column("has_adapter", sa.Boolean()),
        ),
        [
            {
                "slug": "quidax",
                "name": "Quidax",
                "description": "Crypto platform integrated for market data and KYC harvesting.",
                "website_url": "https://www.quidax.com",
                "category": "CRYPTO",
                "is_active": True,
                "has_adapter": True,
            }
        ],
    )

    op.create_table(
        "fee_profiles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("provider_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(), nullable=True),
        sa.Column("source_url", sa.String(), nullable=True),
        sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("fetch_run_id", sa.Integer(), nullable=True),
        sa.Column("raw_record_id", sa.Integer(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["fetch_run_id"], ["fetch_runs.id"]),
        sa.ForeignKeyConstraint(["provider_id"], ["providers.id"]),
        sa.ForeignKeyConstraint(["raw_record_id"], ["raw_records.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_fee_profiles_id"), "fee_profiles", ["id"], unique=False)
    op.create_index(op.f("ix_fee_profiles_provider_id"), "fee_profiles", ["provider_id"], unique=False)
    op.create_index(op.f("ix_fee_profiles_fetch_run_id"), "fee_profiles", ["fetch_run_id"], unique=False)
    op.create_index(op.f("ix_fee_profiles_raw_record_id"), "fee_profiles", ["raw_record_id"], unique=False)

    op.create_table(
        "fee_rules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("fee_profile_id", sa.Integer(), nullable=False),
        sa.Column("provider_id", sa.Integer(), nullable=False),
        sa.Column("provider_asset_id", sa.Integer(), nullable=True),
        sa.Column("asset_id", sa.Integer(), nullable=True),
        sa.Column("fee_category", fee_category_enum, nullable=False),
        sa.Column("fee_type", fee_type_enum, nullable=False),
        sa.Column("from_currency", sa.String(), nullable=True),
        sa.Column("to_currency", sa.String(), nullable=True),
        sa.Column("value", sa.Numeric(precision=24, scale=8), nullable=False),
        sa.Column("value_currency", sa.String(), nullable=True),
        sa.Column("min_value", sa.Numeric(precision=24, scale=8), nullable=True),
        sa.Column("max_value", sa.Numeric(precision=24, scale=8), nullable=True),
        sa.Column("network", sa.String(), nullable=True),
        sa.Column("transaction_side", sa.String(), nullable=True),
        sa.Column("condition_text", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"]),
        sa.ForeignKeyConstraint(["fee_profile_id"], ["fee_profiles.id"]),
        sa.ForeignKeyConstraint(["provider_asset_id"], ["provider_assets.id"]),
        sa.ForeignKeyConstraint(["provider_id"], ["providers.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_fee_rules_id"), "fee_rules", ["id"], unique=False)
    op.create_index(op.f("ix_fee_rules_fee_profile_id"), "fee_rules", ["fee_profile_id"], unique=False)
    op.create_index(op.f("ix_fee_rules_provider_id"), "fee_rules", ["provider_id"], unique=False)
    op.create_index(op.f("ix_fee_rules_provider_asset_id"), "fee_rules", ["provider_asset_id"], unique=False)
    op.create_index(op.f("ix_fee_rules_asset_id"), "fee_rules", ["asset_id"], unique=False)
    op.create_index(op.f("ix_fee_rules_fee_category"), "fee_rules", ["fee_category"], unique=False)
    op.create_index(op.f("ix_fee_rules_fee_type"), "fee_rules", ["fee_type"], unique=False)
    op.create_index(op.f("ix_fee_rules_from_currency"), "fee_rules", ["from_currency"], unique=False)
    op.create_index(op.f("ix_fee_rules_to_currency"), "fee_rules", ["to_currency"], unique=False)
    op.create_index(op.f("ix_fee_rules_network"), "fee_rules", ["network"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_fee_rules_network"), table_name="fee_rules")
    op.drop_index(op.f("ix_fee_rules_to_currency"), table_name="fee_rules")
    op.drop_index(op.f("ix_fee_rules_from_currency"), table_name="fee_rules")
    op.drop_index(op.f("ix_fee_rules_fee_type"), table_name="fee_rules")
    op.drop_index(op.f("ix_fee_rules_fee_category"), table_name="fee_rules")
    op.drop_index(op.f("ix_fee_rules_asset_id"), table_name="fee_rules")
    op.drop_index(op.f("ix_fee_rules_provider_asset_id"), table_name="fee_rules")
    op.drop_index(op.f("ix_fee_rules_provider_id"), table_name="fee_rules")
    op.drop_index(op.f("ix_fee_rules_fee_profile_id"), table_name="fee_rules")
    op.drop_index(op.f("ix_fee_rules_id"), table_name="fee_rules")
    op.drop_table("fee_rules")

    op.drop_index(op.f("ix_fee_profiles_raw_record_id"), table_name="fee_profiles")
    op.drop_index(op.f("ix_fee_profiles_fetch_run_id"), table_name="fee_profiles")
    op.drop_index(op.f("ix_fee_profiles_provider_id"), table_name="fee_profiles")
    op.drop_index(op.f("ix_fee_profiles_id"), table_name="fee_profiles")
    op.drop_table("fee_profiles")

    op.drop_index(op.f("ix_providers_category"), table_name="providers")
    op.drop_index(op.f("ix_providers_slug"), table_name="providers")
    op.drop_index(op.f("ix_providers_id"), table_name="providers")
    op.drop_table("providers")

    bind = op.get_bind()
    fee_type_enum.drop(bind, checkfirst=True)
    fee_category_enum.drop(bind, checkfirst=True)
