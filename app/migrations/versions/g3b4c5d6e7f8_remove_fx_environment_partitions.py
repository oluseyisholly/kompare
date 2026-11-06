"""Use provider/pair identity without sandbox/production database partitions."""

import sqlalchemy as sa
from alembic import op

revision = "g3b4c5d6e7f8"
down_revision = "f2a3b4c5d6e7"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_index("uq_quotes_current_pair", table_name="quotes")
    # Keep all versions and observations. Only the most recently observed current
    # price survives when the former partitions have overlapping current pairs.
    op.execute("""
        WITH ranked AS (
            SELECT id, row_number() OVER (
                PARTITION BY provider, asset_id, base_currency, quote_currency, quote_type
                ORDER BY last_seen_at DESC, captured_at DESC, id DESC
            ) AS position,
            first_value(last_seen_at) OVER (
                PARTITION BY provider, asset_id, base_currency, quote_currency, quote_type
                ORDER BY last_seen_at DESC, captured_at DESC, id DESC
            ) AS newest_seen
            FROM quotes WHERE superseded_at IS NULL
        )
        UPDATE quotes SET superseded_at = ranked.newest_seen
        FROM ranked WHERE quotes.id = ranked.id AND ranked.position > 1
    """)
    op.drop_column("quotes", "environment")
    op.create_index(
        "uq_quotes_current_pair",
        "quotes",
        ["provider", "asset_id", "base_currency", "quote_currency", "quote_type"],
        unique=True,
        postgresql_where=sa.text("superseded_at IS NULL"),
        sqlite_where=sa.text("superseded_at IS NULL"),
    )
    op.drop_constraint("uq_fx_currencies_source", "fx_currencies", type_="unique")
    # Retain duplicate legacy currency rows and provenance as inactive history.
    # The latest recorded currency state wins, including an inactive state.
    op.execute("""
        WITH ranked AS (
            SELECT id, row_number() OVER (
                PARTITION BY provider_id, code
                ORDER BY fetch_run_id DESC, captured_at DESC, id DESC
            ) AS position FROM fx_currencies
        )
        UPDATE fx_currencies SET is_active = false
        FROM ranked WHERE fx_currencies.id = ranked.id AND ranked.position > 1
    """)
    op.drop_column("fx_currencies", "environment")
    op.create_index(
        "uq_fx_currencies_current",
        "fx_currencies",
        ["provider_id", "code"],
        unique=True,
        postgresql_where=sa.text("is_active IS true"),
        sqlite_where=sa.text("is_active IS true"),
    )
    # Normalized metadata no longer carries a partition selector. Original raw
    # content, fetched URLs, fetch runs and observation references are preserved.
    for table, column in (
        ("quotes", "metadata_json"),
        ("fx_quote_observations", "response_data"),
    ):
        op.execute(
            sa.text(f"""
            UPDATE {table} SET {column} = ({column}::jsonb - 'environment')::json
            WHERE {column}::jsonb ? 'environment'
        """)
        )


def downgrade():
    raise RuntimeError(
        "Cannot reconstruct removed FX environment partitions; restore a pre-migration backup"
    )
