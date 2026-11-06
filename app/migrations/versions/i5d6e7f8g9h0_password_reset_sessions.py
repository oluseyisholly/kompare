"""Invalidate existing access tokens when a password is reset."""

import sqlalchemy as sa
from alembic import op

revision = "i5d6e7f8g9h0"
down_revision = "h4c5d6e7f8g9"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "users", sa.Column("auth_version", sa.Integer(), nullable=False, server_default="0")
    )


def downgrade():
    op.drop_column("users", "auth_version")
