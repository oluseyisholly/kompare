"""add tip severity

Revision ID: r8f9a0b1c2d3
Revises: q7e8f9a0b1c2
Create Date: 2026-10-08
"""

from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "r8f9a0b1c2d3"
down_revision: Union[str, None] = "q7e8f9a0b1c2"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


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
    tip_severity_enum.create(bind, checkfirst=True)

    if not _has_column("provider_reviews", "tip_severity"):
        op.add_column(
            "provider_reviews", sa.Column("tip_severity", tip_severity_enum, nullable=True)
        )

    op.execute(
        sa.text(
            """
            UPDATE provider_reviews
            SET tip_severity = CASE tip_category
                WHEN 'RATE_ALERT' THEN 'MEDIUM'::provider_tip_severity
                WHEN 'HIDDEN_FEE_WARNING' THEN 'HIGH'::provider_tip_severity
                WHEN 'SCAM_WARNING' THEN 'CRITICAL'::provider_tip_severity
                WHEN 'GENERAL_TIP' THEN 'LOW'::provider_tip_severity
                ELSE tip_severity
            END
            WHERE review_type = 'TIP'
            AND tip_severity IS NULL
            """
        )
    )

    if _has_check_constraint("provider_reviews", "ck_provider_reviews_review_tip_shape"):
        op.drop_constraint(
            "ck_provider_reviews_review_tip_shape", "provider_reviews", type_="check"
        )

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

    if not _has_index("provider_reviews", "ix_provider_reviews_tip_severity"):
        op.create_index(
            op.f("ix_provider_reviews_tip_severity"),
            "provider_reviews",
            ["tip_severity"],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()

    if _has_check_constraint("provider_reviews", "ck_provider_reviews_review_tip_shape"):
        op.drop_constraint(
            "ck_provider_reviews_review_tip_shape", "provider_reviews", type_="check"
        )

    op.create_check_constraint(
        "ck_provider_reviews_review_tip_shape",
        "provider_reviews",
        """
        (
            review_type = 'REVIEW'
            AND rating IS NOT NULL
            AND title IS NOT NULL
            AND tip_category IS NULL
        )
        OR
        (
            review_type = 'TIP'
            AND rating IS NULL
            AND title IS NULL
            AND tip_category IS NOT NULL
        )
        """,
    )

    if _has_index("provider_reviews", "ix_provider_reviews_tip_severity"):
        op.drop_index(op.f("ix_provider_reviews_tip_severity"), table_name="provider_reviews")
    if _has_column("provider_reviews", "tip_severity"):
        op.drop_column("provider_reviews", "tip_severity")

    tip_severity_enum.drop(bind, checkfirst=True)
