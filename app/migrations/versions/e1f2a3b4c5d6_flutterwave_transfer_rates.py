"""Flutterwave provider and distinct sampled scenarios in shared FX observations."""

import sqlalchemy as sa
from alembic import op

revision = "e1f2a3b4c5d6"
down_revision = "d0e1f2a3b4c5"
branch_labels = None
depends_on = None

SCENARIO = [
    "fetch_run_id",
    "source_currency",
    "target_currency",
    "requested_amount",
    "amount_basis",
    "classification",
]


def upgrade():
    op.execute("ALTER TYPE provider_name ADD VALUE IF NOT EXISTS 'FLUTTERWAVE'")
    op.add_column(
        "fx_quote_observations",
        sa.Column(
            "classification",
            sa.String(48),
            nullable=False,
            server_default="illustrative_transfer_quote",
        ),
    )
    # Restore classification on re-upgrade from the preserved normalized payload.
    op.execute(
        sa.text("""
        UPDATE fx_quote_observations
        SET classification = response_data ->> 'classification'
        WHERE response_data ->> 'classification' IN
            ('illustrative_transfer_quote', 'transfer_rate_observation')
    """)
    )
    for constraint in sa.inspect(op.get_bind()).get_unique_constraints("fx_quote_observations"):
        if constraint["column_names"] == ["fetch_run_id"]:
            op.drop_constraint(constraint["name"], "fx_quote_observations", type_="unique")
    op.create_unique_constraint("uq_fx_observation_scenario", "fx_quote_observations", SCENARIO)
    op.execute(
        sa.text("""
        INSERT INTO providers
            (slug, name, website_url, category, is_active, has_adapter, metadata_json)
        VALUES ('flutterwave', 'Flutterwave', 'https://flutterwave.com', 'FX', true, true,
                '{"rate_classification":"transfer_rate_observation","currency_discovery":"not_implemented"}')
        ON CONFLICT (slug) DO NOTHING
    """)
    )


def downgrade():
    duplicates = (
        op.get_bind()
        .execute(
            sa.text("""
        SELECT count(*) FROM (
            SELECT fetch_run_id FROM fx_quote_observations
            GROUP BY fetch_run_id HAVING count(*) > 1
        ) AS duplicate_runs
    """)
        )
        .scalar()
    )
    if duplicates:
        raise RuntimeError("Cannot downgrade: multiple sampled scenarios share a fetch run")
    op.drop_constraint("uq_fx_observation_scenario", "fx_quote_observations", type_="unique")
    op.create_unique_constraint(
        "uq_fx_observations_fetch_run", "fx_quote_observations", ["fetch_run_id"]
    )
    op.drop_column("fx_quote_observations", "classification")
    # Keep provider/enum history: raw records and runs may still reference Flutterwave.
