"""Add Stanbic mutual fund ingestion tables and provider.

Revision ID: x4e5f6a7b8c9
Revises: w3e4f5a6b7c8
"""

import sqlalchemy as sa
from alembic import op

revision = "x4e5f6a7b8c9"
down_revision = "w3e4f5a6b7c8"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TYPE provider_name ADD VALUE IF NOT EXISTS 'STANBIC'")
    op.create_table(
        "mutual_funds",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provider_id", sa.Integer(), sa.ForeignKey("providers.id"), nullable=False),
        sa.Column("code", sa.String(), nullable=False, unique=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("fund_type", sa.String(), nullable=False),
        sa.Column("currency", sa.String(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_mutual_funds_provider_id", "mutual_funds", ["provider_id"])
    op.create_table(
        "mutual_fund_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("fund_id", sa.Integer(), sa.ForeignKey("mutual_funds.id"), nullable=False),
        sa.Column("bid_price", sa.Numeric(24, 8), nullable=True),
        sa.Column("offer_price", sa.Numeric(24, 8), nullable=True),
        sa.Column("nav_per_unit", sa.Numeric(24, 8), nullable=True),
        sa.Column("yield_percent", sa.Numeric(24, 8), nullable=True),
        sa.Column("yield_label", sa.String(), nullable=True),
        sa.Column("valuation_date", sa.Date(), nullable=True),
        sa.Column(
            "captured_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("fetch_run_id", sa.Integer(), sa.ForeignKey("fetch_runs.id"), nullable=False),
        sa.Column("raw_record_id", sa.Integer(), sa.ForeignKey("raw_records.id"), nullable=False),
        sa.UniqueConstraint("fund_id", "fetch_run_id", name="uq_mutual_fund_snapshot_run"),
    )
    op.create_index("ix_mutual_fund_snapshots_fund_id", "mutual_fund_snapshots", ["fund_id"])
    op.create_index(
        "ix_mutual_fund_snapshots_fetch_run_id", "mutual_fund_snapshots", ["fetch_run_id"]
    )
    op.execute(
        sa.text("""
        INSERT INTO providers (slug, name, website_url, category, is_active, has_adapter)
        VALUES ('stanbic', 'Stanbic IBTC Asset Management',
                'https://blunest.stanbicibtcassetmanagement.com', 'MUTUAL_FUND', true, true)
        ON CONFLICT (slug) DO NOTHING
    """)
    )


def downgrade():
    op.drop_table("mutual_fund_snapshots")
    op.drop_table("mutual_funds")
    # Keep the provider: shared runs, schedules and reviews may reference it.
    # PostgreSQL cannot safely remove an individual provider_name enum value.
