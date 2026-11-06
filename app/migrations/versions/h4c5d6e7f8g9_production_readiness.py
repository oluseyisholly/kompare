"""Shared auth controls, durable ingestion jobs and remediation of legacy bootstrap credentials."""

import sqlalchemy as sa
from alembic import op

revision = "h4c5d6e7f8g9"
down_revision = "g3b4c5d6e7f8"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "verification_otps",
        sa.Column("failed_attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_table(
        "auth_rate_limits",
        sa.Column("bucket_key", sa.String(64), primary_key=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("resets_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_auth_rate_limits_resets_at", "auth_rate_limits", ["resets_at"])
    op.create_table(
        "ingestion_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provider_slug", sa.String(64), nullable=True),
        sa.Column("job_type", sa.String(32), nullable=False),
        sa.Column("include_kyc", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("lease_token", sa.String(64), nullable=True),
        sa.Column("leased_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "queued_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_ingestion_jobs_claim", "ingestion_jobs", ["status", "leased_until", "id"])
    # Match only the old fixed-password hash: preserve deliberately rotated accounts.
    legacy_hash = (
        "kompare_seed_superadmin$b8dcb75ef162883a982c9f0b94c71b782d8ba85bb9ed4b160abb319da9c664e6"
    )
    op.execute(
        sa.text("""
        UPDATE refresh_tokens SET is_active = false, revoked_at = CURRENT_TIMESTAMP
        WHERE user_id IN (SELECT id FROM users WHERE password_hash = :legacy_hash)
    """).bindparams(legacy_hash=legacy_hash)
    )
    op.execute(
        sa.text("""
        UPDATE users SET is_active = false, status = 'SUSPENDED',
            suspended_at = CURRENT_TIMESTAMP,
            suspended_reason = 'Legacy bootstrap credential disabled'
        WHERE password_hash = :legacy_hash
    """).bindparams(legacy_hash=legacy_hash)
    )


def downgrade():
    # Never reactivate a compromised account during rollback.
    op.drop_index("ix_ingestion_jobs_claim", table_name="ingestion_jobs")
    op.drop_table("ingestion_jobs")
    op.drop_index("ix_auth_rate_limits_resets_at", table_name="auth_rate_limits")
    op.drop_table("auth_rate_limits")
    op.drop_column("verification_otps", "failed_attempts")
