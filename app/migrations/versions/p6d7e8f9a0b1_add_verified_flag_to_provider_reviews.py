"""add verified flag to provider reviews

Revision ID: p6d7e8f9a0b1
Revises: o5c6d7e8f9a0
Create Date: 2026-10-04
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "p6d7e8f9a0b1"
down_revision: Union[str, None] = "o5c6d7e8f9a0"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    return any(column["name"] == column_name for column in sa.inspect(bind).get_columns(table_name))


def _has_index(table_name: str, index_name: str) -> bool:
    bind = op.get_bind()
    return any(index["name"] == index_name for index in sa.inspect(bind).get_indexes(table_name))


def upgrade() -> None:
    if not _has_column("provider_reviews", "is_verified"):
        op.add_column(
            "provider_reviews",
            sa.Column("is_verified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        )
    if not _has_index("provider_reviews", "ix_provider_reviews_is_verified"):
        op.create_index(
            op.f("ix_provider_reviews_is_verified"),
            "provider_reviews",
            ["is_verified"],
            unique=False,
        )


def downgrade() -> None:
    if _has_index("provider_reviews", "ix_provider_reviews_is_verified"):
        op.drop_index(op.f("ix_provider_reviews_is_verified"), table_name="provider_reviews")
    if _has_column("provider_reviews", "is_verified"):
        op.drop_column("provider_reviews", "is_verified")
