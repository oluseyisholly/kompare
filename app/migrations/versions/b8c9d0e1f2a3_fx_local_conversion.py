"""Isolate quote environments and add harvested FX currencies."""

import sqlalchemy as sa
from alembic import op

revision = "b8c9d0e1f2a3"
down_revision = "a7b8c9d0e1f2"
branch_labels = None
depends_on = None

PAIR = ["provider", "asset_id", "base_currency", "quote_currency", "quote_type"]


def upgrade():
    op.execute("ALTER TYPE ingestion_job_type ADD VALUE IF NOT EXISTS 'CURRENCIES'")
    op.add_column(
        "quotes",
        sa.Column("environment", sa.String(16), nullable=False, server_default="production"),
    )
    op.drop_index("uq_quotes_current_pair", table_name="quotes")
    # An upgrade batch can add WISE in the preceding revision without a commit.
    # Compare text so PostgreSQL need not cast the literal to that new enum value.
    op.execute("""
        UPDATE quotes SET environment = metadata_json->>'environment'
        WHERE provider::text = 'WISE' AND metadata_json->>'environment' IN ('production', 'sandbox')
    """)
    # Recover the current version within each Wise environment, including a
    # production row previously superseded by a sandbox observation.
    op.execute("""
        WITH history AS (
            SELECT id, lead(captured_at) OVER (
                PARTITION BY provider, asset_id, base_currency, quote_currency,
                             quote_type, environment
                ORDER BY captured_at, id
            ) AS next_capture
            FROM quotes WHERE provider::text = 'WISE'
        )
        UPDATE quotes SET superseded_at = history.next_capture
        FROM history WHERE quotes.id = history.id
    """)
    op.create_index(
        "uq_quotes_current_pair",
        "quotes",
        PAIR + ["environment"],
        unique=True,
        postgresql_where=sa.text("superseded_at IS NULL"),
        sqlite_where=sa.text("superseded_at IS NULL"),
    )
    op.create_table(
        "fx_currencies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provider_id", sa.Integer(), sa.ForeignKey("providers.id"), nullable=False),
        sa.Column("environment", sa.String(16), nullable=False),
        sa.Column("code", sa.String(3), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("symbol", sa.String()),
        sa.Column("supports_decimals", sa.Boolean(), nullable=False),
        sa.Column("decimal_places", sa.Integer()),
        sa.Column("precision_source", sa.String()),
        sa.Column("country_keywords", sa.JSON()),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_url", sa.String(), nullable=False),
        sa.Column("fetch_run_id", sa.Integer(), sa.ForeignKey("fetch_runs.id"), nullable=False),
        sa.Column("raw_record_id", sa.Integer(), sa.ForeignKey("raw_records.id"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("provider_id", "environment", "code", name="uq_fx_currencies_source"),
    )
    op.create_index("ix_fx_currencies_id", "fx_currencies", ["id"])
    op.create_index("ix_fx_currencies_provider_id", "fx_currencies", ["provider_id"])


def downgrade():
    op.drop_table("fx_currencies")
    op.drop_index("uq_quotes_current_pair", table_name="quotes")
    # The legacy key cannot keep both environments current. Prefer production,
    # preserving every historical row and its metadata before removing the column.
    op.execute("""
        WITH current_rows AS (
            SELECT id, row_number() OVER (
                PARTITION BY provider, asset_id, base_currency, quote_currency, quote_type
                ORDER BY CASE WHEN environment = 'production' THEN 0 ELSE 1 END,
                         captured_at DESC, id DESC
            ) AS position
            FROM quotes WHERE superseded_at IS NULL
        )
        UPDATE quotes SET superseded_at = CURRENT_TIMESTAMP
        FROM current_rows WHERE quotes.id = current_rows.id AND current_rows.position > 1
    """)
    op.drop_column("quotes", "environment")
    op.create_index(
        "uq_quotes_current_pair",
        "quotes",
        PAIR,
        unique=True,
        postgresql_where=sa.text("superseded_at IS NULL"),
        sqlite_where=sa.text("superseded_at IS NULL"),
    )
    # Keep the additive enum label; schedules can reference it in shared history.
