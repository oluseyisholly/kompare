"""add tips to provider reviews

Revision ID: q7e8f9a0b1c2
Revises: p6d7e8f9a0b1
Create Date: 2026-10-05
"""

from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "q7e8f9a0b1c2"
down_revision: Union[str, None] = "p6d7e8f9a0b1"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


review_type_enum = postgresql.ENUM(
    "REVIEW",
    "TIP",
    name="provider_review_type",
    create_type=False,
)

tip_category_enum = postgresql.ENUM(
    "RATE_ALERT",
    "HIDDEN_FEE_WARNING",
    "SCAM_WARNING",
    "GENERAL_TIP",
    name="provider_tip_category",
    create_type=False,
)

tip_severity_enum = postgresql.ENUM(
    "LOW",
    "MEDIUM",
    "HIGH",
    "CRITICAL",
    name="provider_tip_severity",
    create_type=False,
)


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    return any(column["name"] == column_name for column in sa.inspect(bind).get_columns(table_name))


def _has_index(table_name: str, index_name: str) -> bool:
    bind = op.get_bind()
    return any(index["name"] == index_name for index in sa.inspect(bind).get_indexes(table_name))


def _has_check_constraint(table_name: str, constraint_name: str) -> bool:
    bind = op.get_bind()
    return any(
        constraint["name"] == constraint_name
        for constraint in sa.inspect(bind).get_check_constraints(table_name)
    )


def upgrade() -> None:
    bind = op.get_bind()
    review_type_enum.create(bind, checkfirst=True)
    tip_category_enum.create(bind, checkfirst=True)
    tip_severity_enum.create(bind, checkfirst=True)

    if not _has_column("provider_reviews", "review_type"):
        op.add_column(
            "provider_reviews",
            sa.Column("review_type", review_type_enum, nullable=False, server_default="REVIEW"),
        )
    if not _has_column("provider_reviews", "tip_category"):
        op.add_column(
            "provider_reviews", sa.Column("tip_category", tip_category_enum, nullable=True)
        )
    if not _has_column("provider_reviews", "tip_severity"):
        op.add_column(
            "provider_reviews", sa.Column("tip_severity", tip_severity_enum, nullable=True)
        )

    op.alter_column("provider_reviews", "rating", existing_type=sa.Integer(), nullable=True)
    op.alter_column("provider_reviews", "title", existing_type=sa.String(), nullable=True)

    if not _has_index("provider_reviews", "ix_provider_reviews_review_type"):
        op.create_index(
            op.f("ix_provider_reviews_review_type"),
            "provider_reviews",
            ["review_type"],
            unique=False,
        )
    if not _has_index("provider_reviews", "ix_provider_reviews_tip_category"):
        op.create_index(
            op.f("ix_provider_reviews_tip_category"),
            "provider_reviews",
            ["tip_category"],
            unique=False,
        )
    if not _has_index("provider_reviews", "ix_provider_reviews_tip_severity"):
        op.create_index(
            op.f("ix_provider_reviews_tip_severity"),
            "provider_reviews",
            ["tip_severity"],
            unique=False,
        )

    if not _has_check_constraint("provider_reviews", "ck_provider_reviews_review_tip_shape"):
        op.create_check_constraint(
            "ck_provider_reviews_review_tip_shape",
            "provider_reviews",
            """
            (
                review_type = 'REVIEW'
                AND rating IS NOT NULL
                AND title IS NOT NULL
                AND tip_category IS NULL
                AND tip_severity IS NULL
            )
            OR
            (
                review_type = 'TIP'
                AND rating IS NULL
                AND title IS NULL
                AND tip_category IS NOT NULL
                AND tip_severity IS NOT NULL
            )
            """,
        )


def downgrade() -> None:
    bind = op.get_bind()

    if _has_check_constraint("provider_reviews", "ck_provider_reviews_review_tip_shape"):
        op.drop_constraint(
            "ck_provider_reviews_review_tip_shape", "provider_reviews", type_="check"
        )
    if _has_index("provider_reviews", "ix_provider_reviews_tip_category"):
        op.drop_index(op.f("ix_provider_reviews_tip_category"), table_name="provider_reviews")
    if _has_index("provider_reviews", "ix_provider_reviews_tip_severity"):
        op.drop_index(op.f("ix_provider_reviews_tip_severity"), table_name="provider_reviews")
    if _has_index("provider_reviews", "ix_provider_reviews_review_type"):
        op.drop_index(op.f("ix_provider_reviews_review_type"), table_name="provider_reviews")

    if _has_column("provider_reviews", "tip_severity"):
        op.drop_column("provider_reviews", "tip_severity")
    if _has_column("provider_reviews", "tip_category"):
        op.drop_column("provider_reviews", "tip_category")
    if _has_column("provider_reviews", "review_type"):
        op.drop_column("provider_reviews", "review_type")

    op.alter_column("provider_reviews", "title", existing_type=sa.String(), nullable=False)
    op.alter_column("provider_reviews", "rating", existing_type=sa.Integer(), nullable=False)

    tip_category_enum.drop(bind, checkfirst=True)
    tip_severity_enum.drop(bind, checkfirst=True)
    review_type_enum.drop(bind, checkfirst=True)
