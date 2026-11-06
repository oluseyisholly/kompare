"""add mutual fund market category

Revision ID: u1c2d3e4f5a6
Revises: t0b1c2d3e4f5
Create Date: 2026-10-09
"""

from typing import Union

from alembic import op

revision: str = "u1c2d3e4f5a6"
down_revision: Union[str, None] = "t0b1c2d3e4f5"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE market_category ADD VALUE IF NOT EXISTS 'MUTUAL_FUND'")


def downgrade() -> None:
    # PostgreSQL does not support dropping a single enum value safely.
    pass
