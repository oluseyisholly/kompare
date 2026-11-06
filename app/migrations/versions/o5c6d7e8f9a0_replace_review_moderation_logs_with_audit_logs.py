"""replace review moderation logs with audit logs

Revision ID: o5c6d7e8f9a0
Revises: n4b5c6d7e8f9
Create Date: 2026-10-02
"""

from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "o5c6d7e8f9a0"
down_revision: Union[str, None] = "n4b5c6d7e8f9"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def _drop_index_if_exists(index_name: str, table_name: str) -> None:
    bind = op.get_bind()
    existing_indexes = {index["name"] for index in sa.inspect(bind).get_indexes(table_name)}
    if index_name in existing_indexes:
        op.drop_index(index_name, table_name=table_name)


def upgrade() -> None:
    bind = op.get_bind()
    existing_tables = set(sa.inspect(bind).get_table_names())

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

    if "provider_review_moderation_logs" in existing_tables:
        _drop_index_if_exists(
            "ix_provider_review_moderation_logs_admin_user_id", "provider_review_moderation_logs"
        )
        _drop_index_if_exists(
            "ix_provider_review_moderation_logs_review_id", "provider_review_moderation_logs"
        )
        _drop_index_if_exists(
            "ix_provider_review_moderation_logs_id", "provider_review_moderation_logs"
        )
        op.drop_table("provider_review_moderation_logs")


def downgrade() -> None:
    bind = op.get_bind()
    existing_tables = set(sa.inspect(bind).get_table_names())
    review_status_enum = postgresql.ENUM(
        "PENDING",
        "PUBLISHED",
        "HIDDEN",
        name="provider_review_status",
        create_type=False,
    )

    if "provider_review_moderation_logs" not in existing_tables:
        op.create_table(
            "provider_review_moderation_logs",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("review_id", sa.Integer(), nullable=False),
            sa.Column("admin_user_id", sa.Integer(), nullable=False),
            sa.Column("old_status", review_status_enum, nullable=True),
            sa.Column("new_status", review_status_enum, nullable=False),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(["review_id"], ["provider_reviews.id"]),
            sa.ForeignKeyConstraint(["admin_user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            op.f("ix_provider_review_moderation_logs_id"),
            "provider_review_moderation_logs",
            ["id"],
            unique=False,
        )
        op.create_index(
            op.f("ix_provider_review_moderation_logs_review_id"),
            "provider_review_moderation_logs",
            ["review_id"],
            unique=False,
        )
        op.create_index(
            op.f("ix_provider_review_moderation_logs_admin_user_id"),
            "provider_review_moderation_logs",
            ["admin_user_id"],
            unique=False,
        )

    if "audit_logs" in existing_tables:
        _drop_index_if_exists("ix_audit_logs_actor_action_created_at", "audit_logs")
        _drop_index_if_exists("ix_audit_logs_entity_type_entity_id", "audit_logs")
        _drop_index_if_exists("ix_audit_logs_created_at", "audit_logs")
        _drop_index_if_exists("ix_audit_logs_entity_id", "audit_logs")
        _drop_index_if_exists("ix_audit_logs_entity_type", "audit_logs")
        _drop_index_if_exists("ix_audit_logs_action", "audit_logs")
        _drop_index_if_exists("ix_audit_logs_actor_user_id", "audit_logs")
        _drop_index_if_exists("ix_audit_logs_id", "audit_logs")
        op.drop_table("audit_logs")
