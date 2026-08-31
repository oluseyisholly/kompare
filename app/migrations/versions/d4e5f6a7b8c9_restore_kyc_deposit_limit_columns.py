"""restore kyc deposit limit columns

Revision ID: d4e5f6a7b8c9
Revises: c3f4a98b2d11
Create Date: 2026-08-31 10:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "c3f4a98b2d11"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("kyc_levels", sa.Column("fiat_deposit_limit", sa.String(), nullable=True))
    op.add_column("kyc_levels", sa.Column("crypto_deposit_limit", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("kyc_levels", "crypto_deposit_limit")
    op.drop_column("kyc_levels", "fiat_deposit_limit")
