"""Register Tbay and add gift-card rate freshness/version timestamps."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "m3a4b5c6d7e8"
down_revision = "l2f3a4b5c6d7"
branch_labels = depends_on = None


def upgrade():
    op.execute("ALTER TYPE provider_name ADD VALUE IF NOT EXISTS 'TBAY'")
    provider = sa.table("providers", sa.column("slug"), sa.column("name"), sa.column("category"),
                        sa.column("website_url"), sa.column("is_active"), sa.column("has_adapter"))
    op.execute(provider.insert().from_select(
        ["slug", "name", "category", "website_url", "is_active", "has_adapter"],
        sa.select(sa.literal("tbay"), sa.literal("Tbay"), sa.cast(sa.literal("GIFTCARD"),
                  postgresql.ENUM(name="market_category", create_type=False)),
                  sa.literal("https://tbay.store"), sa.true(), sa.true()).where(
                      ~sa.exists(sa.select(1).select_from(provider).where(provider.c.slug == "tbay")))))
    op.add_column("giftcard_rates", sa.Column("last_seen_at", sa.DateTime(timezone=True)))
    op.add_column("giftcard_rates", sa.Column("superseded_at", sa.DateTime(timezone=True)))
    rates = sa.table("giftcard_rates", *[sa.column(x) for x in (
        "id", "provider_id", "giftcard_variant_id", "rate_currency", "captured_at", "last_seen_at", "superseded_at")])
    op.execute(rates.update().values(last_seen_at=rates.c.captured_at))
    history = sa.select(rates.c.id, sa.func.lead(rates.c.captured_at).over(
        partition_by=[rates.c.provider_id, rates.c.giftcard_variant_id, rates.c.rate_currency],
        order_by=[rates.c.captured_at, rates.c.id]).label("next_at")).subquery()
    op.execute(rates.update().where(rates.c.id == history.c.id).values(superseded_at=history.c.next_at))
    op.alter_column("giftcard_rates", "last_seen_at", nullable=False, server_default=sa.func.now())
    op.create_index("uq_giftcard_rates_current", "giftcard_rates",
                    ["provider_id", "giftcard_variant_id", "rate_currency"], unique=True,
                    postgresql_where=rates.c.superseded_at.is_(None))


def downgrade():
    op.drop_index("uq_giftcard_rates_current", table_name="giftcard_rates")
    op.drop_column("giftcard_rates", "superseded_at")
    op.drop_column("giftcard_rates", "last_seen_at")
    # Keep provider and enum value: ingested records may reference them.
