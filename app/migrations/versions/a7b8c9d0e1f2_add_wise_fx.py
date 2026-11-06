"""Wise provider and append-only illustrative transfer quotes."""

import sqlalchemy as sa
from alembic import op

revision = "a7b8c9d0e1f2"
down_revision = "z6a7b8c9d0e1"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TYPE provider_name ADD VALUE IF NOT EXISTS 'WISE'")
    op.create_table(
        "wise_illustrative_quotes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provider_id", sa.Integer(), sa.ForeignKey("providers.id"), nullable=False),
        sa.Column("source_currency", sa.String(3), nullable=False),
        sa.Column("target_currency", sa.String(3), nullable=False),
        sa.Column("requested_amount", sa.Numeric(24, 8), nullable=False),
        sa.Column("amount_basis", sa.String(6), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column(
            "fetch_run_id",
            sa.Integer(),
            sa.ForeignKey("fetch_runs.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("raw_record_id", sa.Integer(), sa.ForeignKey("raw_records.id"), nullable=False),
        sa.Column("response_data", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    for column in ("id", "provider_id", "source_currency", "target_currency"):
        op.create_index(
            f"ix_wise_illustrative_quotes_{column}", "wise_illustrative_quotes", [column]
        )
    op.execute(
        sa.text("""
        INSERT INTO providers
            (slug, name, website_url, category, is_active, has_adapter, metadata_json)
        VALUES ('wise', 'Wise', 'https://wise.com', 'FX', true, true,
                '{"rate_classification":"reference_rate"}')
        ON CONFLICT (slug) DO NOTHING
    """)
    )


def downgrade():
    op.drop_table("wise_illustrative_quotes")
    # Retain the shared provider and enum label: historical runs/raw records may use them.
