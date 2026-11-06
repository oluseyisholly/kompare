"""Add nullable fund details and the independent FUND_DETAILS job type."""

import sqlalchemy as sa
from alembic import op

revision = "y5f6a7b8c9d0"
down_revision = "x4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TYPE ingestion_job_type ADD VALUE IF NOT EXISTS 'FUND_DETAILS'")
    for name in ("minimum_initial_investment", "minimum_topup", "management_fee_percent_pa"):
        op.add_column("mutual_funds", sa.Column(name, sa.Numeric(24, 8), nullable=True))
    op.add_column("mutual_funds", sa.Column("minimum_holding_days", sa.Integer(), nullable=True))
    for name in ("risk_label", "distribution_frequency", "structure"):
        op.add_column("mutual_funds", sa.Column(name, sa.String(), nullable=True))
    op.add_column("mutual_funds", sa.Column("details_metadata", sa.JSON(), nullable=True))


def downgrade():
    for name in (
        "details_metadata",
        "structure",
        "distribution_frequency",
        "management_fee_percent_pa",
        "risk_label",
        "minimum_holding_days",
        "minimum_topup",
        "minimum_initial_investment",
    ):
        op.drop_column("mutual_funds", name)
    # PostgreSQL cannot safely remove a single enum value; preserve it.
