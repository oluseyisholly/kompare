"""add busha provider support

Revision ID: b7d1c2e4f9a8
Revises: a9f6e3d2b1c4
Create Date: 2026-08-29 11:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b7d1c2e4f9a8"
down_revision: Union[str, None] = "a9f6e3d2b1c4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE provider_name ADD VALUE IF NOT EXISTS 'BUSHA'")

    op.execute(
        sa.text(
            """
            INSERT INTO providers (slug, name, description, website_url, category, is_active, has_adapter)
            SELECT :slug, :name, :description, :website_url, :category, :is_active, :has_adapter
            WHERE NOT EXISTS (
                SELECT 1 FROM providers WHERE slug = :slug
            )
            """
        ).bindparams(
            slug="busha",
            name="Busha",
            description="Crypto platform integrated for market data and KYC harvesting.",
            website_url="https://www.busha.co",
            category="CRYPTO",
            is_active=True,
            has_adapter=True,
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM providers WHERE slug = :slug").bindparams(slug="busha"))
