"""seed initial superadmin

Revision ID: g7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-08-31 13:35:00.000000

"""
from __future__ import annotations

import hashlib
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "g7b8c9d0e1f2"
down_revision: Union[str, None] = "f6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _hash_password(password: str) -> str:
    salt = "kompare_seed_superadmin"
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        100_000,
    ).hex()
    return f"{salt}${digest}"


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            INSERT INTO users (
                email,
                password_hash,
                first_name,
                last_name,
                role,
                is_superadmin,
                is_active,
                is_verified
            )
            SELECT
                :email,
                :password_hash,
                :first_name,
                :last_name,
                :role,
                :is_superadmin,
                :is_active,
                :is_verified
            WHERE NOT EXISTS (
                SELECT 1 FROM users WHERE email = :email
            )
            """
        ).bindparams(
            email="owoyemisholly@gmail.com",
            password_hash=_hash_password("Olusola@123"),
            first_name="Owoyemi",
            last_name="Sholly",
            role="ADMIN",
            is_superadmin=True,
            is_active=True,
            is_verified=True,
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text("DELETE FROM users WHERE email = :email").bindparams(
            email="owoyemisholly@gmail.com",
        )
    )
