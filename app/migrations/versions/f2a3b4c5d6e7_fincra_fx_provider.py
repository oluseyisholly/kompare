"""Register Fincra; side-specific rates reuse existing quote history."""

from alembic import op

revision = "f2a3b4c5d6e7"
down_revision = "e1f2a3b4c5d6"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TYPE provider_name ADD VALUE IF NOT EXISTS 'FINCRA'")
    op.execute("""
        INSERT INTO providers
            (slug, name, website_url, category, is_active, has_adapter, metadata_json)
        VALUES ('fincra', 'Fincra', 'https://fincra.com', 'FX', true, true,
                '{"rate_classification":"treasury_rate","currency_discovery":"observed_rate_pairs"}')
        ON CONFLICT (slug) DO NOTHING
    """)


def downgrade():
    # Keep additive provider/enum entries: historical observations may reference them.
    pass
