"""Add United Capital provider and a distinct YTD-return snapshot field."""

import sqlalchemy as sa
from alembic import op

revision = "z6a7b8c9d0e1"
down_revision = "y5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TYPE provider_name ADD VALUE IF NOT EXISTS 'UNITED_CAPITAL'")
    op.add_column(
        "mutual_fund_snapshots", sa.Column("ytd_return_percent", sa.Numeric(24, 8), nullable=True)
    )
    op.execute(
        sa.text("""
        INSERT INTO providers (slug, name, website_url, category, is_active, has_adapter)
        VALUES ('united_capital', 'United Capital Asset Management',
                'https://unitedcapitalplcgroup.com/asset-management/', 'MUTUAL_FUND', true, true)
        ON CONFLICT (slug) DO NOTHING
    """)
    )


def downgrade():
    op.drop_column("mutual_fund_snapshots", "ytd_return_percent")
    # Keep the shared provider and enum value: existing runs/reviews may reference them.
