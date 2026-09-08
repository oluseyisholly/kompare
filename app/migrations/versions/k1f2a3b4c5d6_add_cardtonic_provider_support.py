"""add cardtonic provider support

Revision ID: k1f2a3b4c5d6
Revises: j0e1f2a3b4c5
Create Date: 2026-09-01 16:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "k1f2a3b4c5d6"
down_revision: Union[str, None] = "j0e1f2a3b4c5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE provider_name ADD VALUE IF NOT EXISTS 'CARDTONIC'")

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
            slug="cardtonic",
            name="Cardtonic",
            description="Gift card platform integrated for gift card rate harvesting.",
            website_url="https://cardtonic.com",
            category="GIFTCARD",
            is_active=True,
            has_adapter=True,
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM providers WHERE slug = :slug").bindparams(slug="cardtonic"))
