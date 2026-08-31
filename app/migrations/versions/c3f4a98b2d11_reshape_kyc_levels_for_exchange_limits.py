"""reshape kyc levels for exchange limits

Revision ID: c3f4a98b2d11
Revises: b7d1c2e4f9a8
Create Date: 2026-08-29 12:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c3f4a98b2d11"
down_revision: Union[str, None] = "b7d1c2e4f9a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("kyc_levels", sa.Column("limit_reference", sa.String(), nullable=True))
    op.add_column("kyc_levels", sa.Column("exchange_limit_text", sa.Text(), nullable=True))
    op.add_column("kyc_levels", sa.Column("exchange_limit_period", sa.String(), nullable=True))
    op.add_column("kyc_levels", sa.Column("notes", sa.Text(), nullable=True))
    op.add_column("kyc_levels", sa.Column("metadata_json", sa.JSON(), nullable=True))

    op.execute(
        """
        UPDATE kyc_levels
        SET limit_reference = 'kyc_level',
            exchange_limit_text = COALESCE(
                fiat_withdrawal_limit,
                crypto_withdrawal_limit,
                fiat_deposit_limit,
                crypto_deposit_limit
            ),
            exchange_limit_period = 'daily'
        WHERE fiat_deposit_limit IS NOT NULL
           OR fiat_withdrawal_limit IS NOT NULL
           OR crypto_deposit_limit IS NOT NULL
           OR crypto_withdrawal_limit IS NOT NULL
        """
    )


def downgrade() -> None:
    op.drop_column("kyc_levels", "metadata_json")
    op.drop_column("kyc_levels", "notes")
    op.drop_column("kyc_levels", "exchange_limit_period")
    op.drop_column("kyc_levels", "exchange_limit_text")
    op.drop_column("kyc_levels", "limit_reference")
