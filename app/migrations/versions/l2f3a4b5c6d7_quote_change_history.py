"""Track quote versions and successful observations without deleting history."""
from alembic import op
import sqlalchemy as sa

revision = "l2f3a4b5c6d7"
down_revision = "k1f2a3b4c5d6"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("quotes", sa.Column("last_seen_at", sa.DateTime(timezone=True)))
    op.add_column("quotes", sa.Column("superseded_at", sa.DateTime(timezone=True)))
    quotes = sa.table("quotes", sa.column("id"), sa.column("provider"),
        sa.column("asset_id"), sa.column("base_currency"), sa.column("quote_currency"),
        sa.column("quote_type"), sa.column("captured_at"), sa.column("last_seen_at"),
        sa.column("superseded_at"), sa.column("fetch_run_id"), sa.column("raw_record_id"))
    op.execute(quotes.update().values(last_seen_at=quotes.c.captured_at))
    versions = sa.select(quotes.c.id, sa.func.lead(quotes.c.captured_at).over(
        partition_by=[quotes.c.provider, quotes.c.asset_id, quotes.c.base_currency,
                      quotes.c.quote_currency, quotes.c.quote_type],
        order_by=[quotes.c.captured_at, quotes.c.id],
    ).label("next_at")).subquery()
    op.execute(quotes.update().where(quotes.c.id == versions.c.id).values(
        superseded_at=versions.c.next_at))
    op.alter_column("quotes", "last_seen_at", nullable=False, server_default=sa.func.now())
    op.create_index("uq_quotes_current_pair", "quotes",
        ["provider", "asset_id", "base_currency", "quote_currency", "quote_type"],
        unique=True, postgresql_where=quotes.c.superseded_at.is_(None))
    observations = op.create_table("quote_observations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("quote_id", sa.Integer(), sa.ForeignKey("quotes.id"), nullable=False),
        sa.Column("fetch_run_id", sa.Integer(), sa.ForeignKey("fetch_runs.id")),
        sa.Column("raw_record_id", sa.Integer(), sa.ForeignKey("raw_records.id")),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_quote_observations_quote_id", "quote_observations", ["quote_id"])
    op.create_index("ix_quote_observations_observed_at", "quote_observations", ["observed_at"])
    op.execute(observations.insert().from_select(
        ["quote_id", "fetch_run_id", "raw_record_id", "observed_at"],
        sa.select(quotes.c.id, quotes.c.fetch_run_id, quotes.c.raw_record_id, quotes.c.captured_at)))


def downgrade():
    op.drop_table("quote_observations")
    op.drop_index("uq_quotes_current_pair", table_name="quotes")
    op.drop_column("quotes", "superseded_at")
    op.drop_column("quotes", "last_seen_at")
