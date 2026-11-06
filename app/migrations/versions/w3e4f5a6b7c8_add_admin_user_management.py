"""add admin user management

Revision ID: w3e4f5a6b7c8
Revises: v2d3e4f5a6b7
Create Date: 2026-10-09
"""

from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "w3e4f5a6b7c8"
down_revision: Union[str, None] = "v2d3e4f5a6b7"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


user_status_enum = postgresql.ENUM(
    "ACTIVE",
    "PENDING",
    "UNVERIFIED",
    "SUSPENDED",
    name="user_status",
    create_type=False,
)
verification_purpose_enum = postgresql.ENUM(
    "EMAIL_VERIFICATION",
    "PHONE_VERIFICATION",
    "PASSWORD_RESET",
    name="verification_purpose",
    create_type=False,
)
verification_channel_enum = postgresql.ENUM(
    "EMAIL",
    "SMS",
    name="verification_channel",
    create_type=False,
)
deletion_status_enum = postgresql.ENUM(
    "REQUESTED",
    "PROCESSING",
    "COMPLETED",
    "CANCELLED",
    name="user_deletion_request_status",
    create_type=False,
)


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    return any(column["name"] == column_name for column in sa.inspect(bind).get_columns(table_name))


def _has_index(table_name: str, index_name: str) -> bool:
    bind = op.get_bind()
    return any(index["name"] == index_name for index in sa.inspect(bind).get_indexes(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    existing_tables = set(sa.inspect(bind).get_table_names())
    user_status_enum.create(bind, checkfirst=True)
    verification_purpose_enum.create(bind, checkfirst=True)
    verification_channel_enum.create(bind, checkfirst=True)
    deletion_status_enum.create(bind, checkfirst=True)

    if not _has_column("users", "phone_number"):
        op.add_column("users", sa.Column("phone_number", sa.String(), nullable=True))
        op.create_index(op.f("ix_users_phone_number"), "users", ["phone_number"], unique=False)
    if not _has_column("users", "is_phone_verified"):
        op.add_column(
            "users",
            sa.Column("is_phone_verified", sa.Boolean(), server_default="false", nullable=False),
        )
    if not _has_column("users", "status"):
        op.add_column(
            "users",
            sa.Column("status", user_status_enum, server_default="UNVERIFIED", nullable=False),
        )
        op.create_index(op.f("ix_users_status"), "users", ["status"], unique=False)
        op.execute(
            """
            UPDATE users
            SET status = CASE
                WHEN is_active = false THEN 'SUSPENDED'::user_status
                WHEN is_verified = true THEN 'ACTIVE'::user_status
                ELSE 'UNVERIFIED'::user_status
            END
            """
        )
    if not _has_column("users", "suspended_at"):
        op.add_column("users", sa.Column("suspended_at", sa.DateTime(timezone=True), nullable=True))
    if not _has_column("users", "suspended_reason"):
        op.add_column("users", sa.Column("suspended_reason", sa.String(), nullable=True))

    if "verification_otps" not in existing_tables:
        op.create_table(
            "verification_otps",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("otp_hash", sa.Text(), nullable=False),
            sa.Column("purpose", verification_purpose_enum, nullable=False),
            sa.Column("channel", verification_channel_enum, nullable=False),
            sa.Column("target", sa.String(), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
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
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_verification_otps_id"), "verification_otps", ["id"], unique=False)
        op.create_index(
            op.f("ix_verification_otps_user_id"), "verification_otps", ["user_id"], unique=False
        )
        op.create_index(
            op.f("ix_verification_otps_purpose"), "verification_otps", ["purpose"], unique=False
        )
        op.create_index(
            op.f("ix_verification_otps_channel"), "verification_otps", ["channel"], unique=False
        )
        op.create_index(
            op.f("ix_verification_otps_target"), "verification_otps", ["target"], unique=False
        )
        op.create_index(
            op.f("ix_verification_otps_expires_at"),
            "verification_otps",
            ["expires_at"],
            unique=False,
        )
        op.create_index(
            op.f("ix_verification_otps_is_active"), "verification_otps", ["is_active"], unique=False
        )

    if "user_deletion_requests" not in existing_tables:
        op.create_table(
            "user_deletion_requests",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("status", deletion_status_enum, server_default="REQUESTED", nullable=False),
            sa.Column("reason", sa.Text(), nullable=True),
            sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("grace_ends_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("processing_started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("processed_by_user_id", sa.Integer(), nullable=True),
            sa.Column("admin_note", sa.Text(), nullable=True),
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
            sa.ForeignKeyConstraint(["processed_by_user_id"], ["users.id"]),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            op.f("ix_user_deletion_requests_id"), "user_deletion_requests", ["id"], unique=False
        )
        op.create_index(
            op.f("ix_user_deletion_requests_user_id"),
            "user_deletion_requests",
            ["user_id"],
            unique=False,
        )
        op.create_index(
            op.f("ix_user_deletion_requests_status"),
            "user_deletion_requests",
            ["status"],
            unique=False,
        )
        op.create_index(
            op.f("ix_user_deletion_requests_requested_at"),
            "user_deletion_requests",
            ["requested_at"],
            unique=False,
        )
        op.create_index(
            op.f("ix_user_deletion_requests_grace_ends_at"),
            "user_deletion_requests",
            ["grace_ends_at"],
            unique=False,
        )
        op.create_index(
            op.f("ix_user_deletion_requests_processed_by_user_id"),
            "user_deletion_requests",
            ["processed_by_user_id"],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    existing_tables = set(sa.inspect(bind).get_table_names())

    if "user_deletion_requests" in existing_tables:
        op.drop_index(
            op.f("ix_user_deletion_requests_processed_by_user_id"),
            table_name="user_deletion_requests",
        )
        op.drop_index(
            op.f("ix_user_deletion_requests_grace_ends_at"), table_name="user_deletion_requests"
        )
        op.drop_index(
            op.f("ix_user_deletion_requests_requested_at"), table_name="user_deletion_requests"
        )
        op.drop_index(op.f("ix_user_deletion_requests_status"), table_name="user_deletion_requests")
        op.drop_index(
            op.f("ix_user_deletion_requests_user_id"), table_name="user_deletion_requests"
        )
        op.drop_index(op.f("ix_user_deletion_requests_id"), table_name="user_deletion_requests")
        op.drop_table("user_deletion_requests")

    if "verification_otps" in existing_tables:
        op.drop_index(op.f("ix_verification_otps_is_active"), table_name="verification_otps")
        op.drop_index(op.f("ix_verification_otps_expires_at"), table_name="verification_otps")
        op.drop_index(op.f("ix_verification_otps_target"), table_name="verification_otps")
        op.drop_index(op.f("ix_verification_otps_channel"), table_name="verification_otps")
        op.drop_index(op.f("ix_verification_otps_purpose"), table_name="verification_otps")
        op.drop_index(op.f("ix_verification_otps_user_id"), table_name="verification_otps")
        op.drop_index(op.f("ix_verification_otps_id"), table_name="verification_otps")
        op.drop_table("verification_otps")

    if _has_column("users", "suspended_reason"):
        op.drop_column("users", "suspended_reason")
    if _has_column("users", "suspended_at"):
        op.drop_column("users", "suspended_at")
    if _has_column("users", "status"):
        if _has_index("users", "ix_users_status"):
            op.drop_index(op.f("ix_users_status"), table_name="users")
        op.drop_column("users", "status")
    if _has_column("users", "is_phone_verified"):
        op.drop_column("users", "is_phone_verified")
    if _has_column("users", "phone_number"):
        if _has_index("users", "ix_users_phone_number"):
            op.drop_index(op.f("ix_users_phone_number"), table_name="users")
        op.drop_column("users", "phone_number")
