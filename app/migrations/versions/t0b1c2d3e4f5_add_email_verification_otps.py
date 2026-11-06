"""add email verification otps

Revision ID: t0b1c2d3e4f5
Revises: s9a0b1c2d3e4
Create Date: 2026-10-08
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "t0b1c2d3e4f5"
down_revision: Union[str, None] = "s9a0b1c2d3e4"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    bind = op.get_bind()
    existing_tables = set(sa.inspect(bind).get_table_names())

    if "email_verification_otps" not in existing_tables:
        op.create_table(
            "email_verification_otps",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("otp_hash", sa.Text(), nullable=False),
            sa.Column("purpose", sa.String(), server_default="email_verification", nullable=False),
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
        op.create_index(
            op.f("ix_email_verification_otps_id"), "email_verification_otps", ["id"], unique=False
        )
        op.create_index(
            op.f("ix_email_verification_otps_user_id"),
            "email_verification_otps",
            ["user_id"],
            unique=False,
        )
        op.create_index(
            op.f("ix_email_verification_otps_purpose"),
            "email_verification_otps",
            ["purpose"],
            unique=False,
        )
        op.create_index(
            op.f("ix_email_verification_otps_expires_at"),
            "email_verification_otps",
            ["expires_at"],
            unique=False,
        )
        op.create_index(
            op.f("ix_email_verification_otps_is_active"),
            "email_verification_otps",
            ["is_active"],
            unique=False,
        )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_email_verification_otps_is_active"), table_name="email_verification_otps"
    )
    op.drop_index(
        op.f("ix_email_verification_otps_expires_at"), table_name="email_verification_otps"
    )
    op.drop_index(op.f("ix_email_verification_otps_purpose"), table_name="email_verification_otps")
    op.drop_index(op.f("ix_email_verification_otps_user_id"), table_name="email_verification_otps")
    op.drop_index(op.f("ix_email_verification_otps_id"), table_name="email_verification_otps")
    op.drop_table("email_verification_otps")
