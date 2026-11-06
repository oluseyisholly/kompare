"""Reuse normalized FX observation storage across providers."""

import sqlalchemy as sa
from alembic import op

revision = "c9d0e1f2a3b4"
down_revision = "b8c9d0e1f2a3"
branch_labels = None
depends_on = None

INDEX_COLUMNS = ("id", "provider_id", "source_currency", "target_currency")


def upgrade():
    op.rename_table("wise_illustrative_quotes", "fx_quote_observations")
    for column in INDEX_COLUMNS:
        op.drop_index(f"ix_wise_illustrative_quotes_{column}", table_name="fx_quote_observations")
        op.create_index(f"ix_fx_quote_observations_{column}", "fx_quote_observations", [column])
    op.alter_column("fx_currencies", "name", existing_type=sa.String(), nullable=True)
    op.alter_column("fx_currencies", "supports_decimals", existing_type=sa.Boolean(), nullable=True)


def downgrade():
    # Do not fabricate missing fields if another provider has ingested unknowns.
    # Refuse that downgrade rather than deleting records or inventing capabilities.
    connection = op.get_bind()
    unknown = connection.execute(
        sa.text(
            "SELECT count(*) FROM fx_currencies WHERE name IS NULL OR supports_decimals IS NULL"
        )
    ).scalar()
    if unknown:
        raise RuntimeError(
            "Cannot downgrade: FX currencies contain unknown names or decimal support"
        )
    op.alter_column("fx_currencies", "name", existing_type=sa.String(), nullable=False)
    op.alter_column(
        "fx_currencies", "supports_decimals", existing_type=sa.Boolean(), nullable=False
    )
    for column in INDEX_COLUMNS:
        op.drop_index(f"ix_fx_quote_observations_{column}", table_name="fx_quote_observations")
        op.create_index(f"ix_wise_illustrative_quotes_{column}", "fx_quote_observations", [column])
    op.rename_table("fx_quote_observations", "wise_illustrative_quotes")
