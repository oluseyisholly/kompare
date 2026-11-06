"""add admin type to users

Revision ID: s9a0b1c2d3e4
Revises: r8f9a0b1c2d3
Create Date: 2026-10-08
"""

from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "s9a0b1c2d3e4"
down_revision: Union[str, None] = "r8f9a0b1c2d3"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


admin_type_enum = postgresql.ENUM(
    "SUPER_ADMIN",
    "SUPPORT_ADMIN",
    "CONTENT_MODERATOR",
    "INGESTION_MANAGER",
    "FINANCE_ADMIN",
    name="admin_type",
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
    admin_type_enum.create(bind, checkfirst=True)

    if not _has_column("users", "admin_type"):
        op.add_column("users", sa.Column("admin_type", admin_type_enum, nullable=True))

    op.execute(
        sa.text(
            """
            UPDATE users
            SET admin_type = 'SUPER_ADMIN'
            WHERE role = 'ADMIN'
            AND is_superadmin = true
            AND admin_type IS NULL
            """
        )
    )

    op.execute(
        sa.text(
            """
            UPDATE users
            SET admin_type = 'SUPPORT_ADMIN'
            WHERE role = 'ADMIN'
            AND is_superadmin = false
            AND admin_type IS NULL
            """
        )
    )

    if not _has_index("users", "ix_users_admin_type"):
        op.create_index(op.f("ix_users_admin_type"), "users", ["admin_type"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()

    if _has_index("users", "ix_users_admin_type"):
        op.drop_index(op.f("ix_users_admin_type"), table_name="users")
    if _has_column("users", "admin_type"):
        op.drop_column("users", "admin_type")

    admin_type_enum.drop(bind, checkfirst=True)
