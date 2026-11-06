"""add provider reviews

Revision ID: n4b5c6d7e8f9
Revises: m3a4b5c6d7e8
Create Date: 2026-10-02
"""

from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "n4b5c6d7e8f9"
down_revision: Union[str, None] = "m3a4b5c6d7e8"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


review_status_enum = postgresql.ENUM(
    "PENDING",
    "PUBLISHED",
    "HIDDEN",
    name="provider_review_status",
    create_type=False,
)

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


def upgrade() -> None:
    bind = op.get_bind()
    review_status_enum.create(bind, checkfirst=True)
    review_type_enum.create(bind, checkfirst=True)
    tip_category_enum.create(bind, checkfirst=True)
    tip_severity_enum.create(bind, checkfirst=True)
    existing_tables = set(sa.inspect(bind).get_table_names())

    if "provider_reviews" not in existing_tables:
        op.create_table(
            "provider_reviews",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("provider_id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=True),
            sa.Column("review_type", review_type_enum, nullable=False, server_default="REVIEW"),
            sa.Column("tip_category", tip_category_enum, nullable=True),
            sa.Column("tip_severity", tip_severity_enum, nullable=True),
            sa.Column("rating", sa.Integer(), nullable=True),
            sa.Column("title", sa.String(), nullable=True),
            sa.Column("body", sa.Text(), nullable=False),
            sa.Column(
                "tags",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
            ),
            sa.Column("is_verified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("status", review_status_enum, nullable=False, server_default="PENDING"),
            sa.Column(
                "reviewed_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                onupdate=sa.func.now(),
                nullable=False,
            ),
            sa.CheckConstraint(
                "rating >= 1 AND rating <= 5", name="ck_provider_reviews_rating_range"
            ),
            sa.CheckConstraint(
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
                name="ck_provider_reviews_review_tip_shape",
            ),
            sa.ForeignKeyConstraint(["provider_id"], ["providers.id"]),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_provider_reviews_id"), "provider_reviews", ["id"], unique=False)
        op.create_index(
            op.f("ix_provider_reviews_provider_id"),
            "provider_reviews",
            ["provider_id"],
            unique=False,
        )
        op.create_index(
            op.f("ix_provider_reviews_user_id"), "provider_reviews", ["user_id"], unique=False
        )
        op.create_index(
            op.f("ix_provider_reviews_review_type"),
            "provider_reviews",
            ["review_type"],
            unique=False,
        )
        op.create_index(
            op.f("ix_provider_reviews_tip_category"),
            "provider_reviews",
            ["tip_category"],
            unique=False,
        )
        op.create_index(
            op.f("ix_provider_reviews_tip_severity"),
            "provider_reviews",
            ["tip_severity"],
            unique=False,
        )
        op.create_index(
            op.f("ix_provider_reviews_is_verified"),
            "provider_reviews",
            ["is_verified"],
            unique=False,
        )
        op.create_index(
            op.f("ix_provider_reviews_status"), "provider_reviews", ["status"], unique=False
        )
        op.create_index(
            op.f("ix_provider_reviews_reviewed_at"),
            "provider_reviews",
            ["reviewed_at"],
            unique=False,
        )
        op.create_index(
            "ix_provider_reviews_provider_status_reviewed_at",
            "provider_reviews",
            ["provider_id", "status", "reviewed_at"],
            unique=False,
        )
        op.create_index(
            "ix_provider_reviews_tags",
            "provider_reviews",
            ["tags"],
            unique=False,
            postgresql_using="gin",
        )

    if "provider_review_comments" not in existing_tables:
        op.create_table(
            "provider_review_comments",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("review_id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=True),
            sa.Column("body", sa.Text(), nullable=False),
            sa.Column("status", review_status_enum, nullable=False, server_default="PENDING"),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                onupdate=sa.func.now(),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(["review_id"], ["provider_reviews.id"]),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            op.f("ix_provider_review_comments_id"), "provider_review_comments", ["id"], unique=False
        )
        op.create_index(
            op.f("ix_provider_review_comments_review_id"),
            "provider_review_comments",
            ["review_id"],
            unique=False,
        )
        op.create_index(
            op.f("ix_provider_review_comments_user_id"),
            "provider_review_comments",
            ["user_id"],
            unique=False,
        )
        op.create_index(
            op.f("ix_provider_review_comments_status"),
            "provider_review_comments",
            ["status"],
            unique=False,
        )

    if "provider_review_votes" not in existing_tables:
        op.create_table(
            "provider_review_votes",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("review_id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("is_helpful", sa.Boolean(), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                onupdate=sa.func.now(),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(["review_id"], ["provider_reviews.id"]),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "review_id", "user_id", name="uq_provider_review_votes_review_user"
            ),
        )
        op.create_index(
            op.f("ix_provider_review_votes_id"), "provider_review_votes", ["id"], unique=False
        )
        op.create_index(
            op.f("ix_provider_review_votes_review_id"),
            "provider_review_votes",
            ["review_id"],
            unique=False,
        )
        op.create_index(
            op.f("ix_provider_review_votes_user_id"),
            "provider_review_votes",
            ["user_id"],
            unique=False,
        )
        op.create_index(
            op.f("ix_provider_review_votes_is_helpful"),
            "provider_review_votes",
            ["is_helpful"],
            unique=False,
        )

    if "audit_logs" not in existing_tables:
        op.create_table(
            "audit_logs",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("actor_user_id", sa.Integer(), nullable=True),
            sa.Column("action", sa.String(), nullable=False),
            sa.Column("entity_type", sa.String(), nullable=False),
            sa.Column("entity_id", sa.String(), nullable=True),
            sa.Column("old_values", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("new_values", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_audit_logs_id"), "audit_logs", ["id"], unique=False)
        op.create_index(
            op.f("ix_audit_logs_actor_user_id"), "audit_logs", ["actor_user_id"], unique=False
        )
        op.create_index(op.f("ix_audit_logs_action"), "audit_logs", ["action"], unique=False)
        op.create_index(
            op.f("ix_audit_logs_entity_type"), "audit_logs", ["entity_type"], unique=False
        )
        op.create_index(op.f("ix_audit_logs_entity_id"), "audit_logs", ["entity_id"], unique=False)
        op.create_index(
            op.f("ix_audit_logs_created_at"), "audit_logs", ["created_at"], unique=False
        )
        op.create_index(
            "ix_audit_logs_entity_type_entity_id",
            "audit_logs",
            ["entity_type", "entity_id"],
            unique=False,
        )
        op.create_index(
            "ix_audit_logs_actor_action_created_at",
            "audit_logs",
            ["actor_user_id", "action", "created_at"],
            unique=False,
        )


def downgrade() -> None:
    op.drop_index("ix_audit_logs_actor_action_created_at", table_name="audit_logs")
    op.drop_index("ix_audit_logs_entity_type_entity_id", table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_created_at"), table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_entity_id"), table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_entity_type"), table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_action"), table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_actor_user_id"), table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_id"), table_name="audit_logs")
    op.drop_table("audit_logs")

    op.drop_index(op.f("ix_provider_review_votes_is_helpful"), table_name="provider_review_votes")
    op.drop_index(op.f("ix_provider_review_votes_user_id"), table_name="provider_review_votes")
    op.drop_index(op.f("ix_provider_review_votes_review_id"), table_name="provider_review_votes")
    op.drop_index(op.f("ix_provider_review_votes_id"), table_name="provider_review_votes")
    op.drop_table("provider_review_votes")

    op.drop_index(op.f("ix_provider_review_comments_status"), table_name="provider_review_comments")
    op.drop_index(
        op.f("ix_provider_review_comments_user_id"), table_name="provider_review_comments"
    )
    op.drop_index(
        op.f("ix_provider_review_comments_review_id"), table_name="provider_review_comments"
    )
    op.drop_index(op.f("ix_provider_review_comments_id"), table_name="provider_review_comments")
    op.drop_table("provider_review_comments")

    op.drop_index("ix_provider_reviews_tags", table_name="provider_reviews")
    op.drop_index("ix_provider_reviews_provider_status_reviewed_at", table_name="provider_reviews")
    op.drop_index(op.f("ix_provider_reviews_reviewed_at"), table_name="provider_reviews")
    op.drop_index(op.f("ix_provider_reviews_status"), table_name="provider_reviews")
    op.drop_index(op.f("ix_provider_reviews_is_verified"), table_name="provider_reviews")
    op.drop_index(op.f("ix_provider_reviews_tip_severity"), table_name="provider_reviews")
    op.drop_index(op.f("ix_provider_reviews_tip_category"), table_name="provider_reviews")
    op.drop_index(op.f("ix_provider_reviews_review_type"), table_name="provider_reviews")
    op.drop_index(op.f("ix_provider_reviews_user_id"), table_name="provider_reviews")
    op.drop_index(op.f("ix_provider_reviews_provider_id"), table_name="provider_reviews")
    op.drop_index(op.f("ix_provider_reviews_id"), table_name="provider_reviews")
    op.drop_table("provider_reviews")

    bind = op.get_bind()
    tip_severity_enum.drop(bind, checkfirst=True)
    tip_category_enum.drop(bind, checkfirst=True)
    review_type_enum.drop(bind, checkfirst=True)
    review_status_enum.drop(bind, checkfirst=True)
