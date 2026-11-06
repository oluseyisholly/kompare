"""Regression for FX upgrades batched in one PostgreSQL transaction."""

import importlib
import os
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import URL, create_engine, text


@pytest.mark.skipif(
    not os.getenv("KOMPARE_FX_TEST_PG_SOCKET"),
    reason="Requires an explicitly configured disposable PostgreSQL Unix socket",
)
@pytest.mark.parametrize("wise_already_committed", [False, True])
def test_fx_upgrade_batch_handles_new_and_existing_wise_enum(wise_already_committed):
    socket = os.environ["KOMPARE_FX_TEST_PG_SOCKET"]
    assert socket.startswith("/tmp/kompare-wise-pg.")
    engine = create_engine(
        URL.create(
            "postgresql+psycopg2",
            username="postgres",
            host=socket,
            port=55484,
            database="kompare_fx_refresh_test",
        )
    )
    schema = "fx_migration_" + uuid4().hex
    try:
        with engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
            connection.execute(text("CREATE TYPE provider_name AS ENUM ('QUIDAX')"))
            if wise_already_committed:
                connection.execute(text("ALTER TYPE provider_name ADD VALUE 'WISE'"))
            connection.execute(text("CREATE TYPE ingestion_job_type AS ENUM ('MARKET_DATA')"))
            connection.execute(
                text("""
                CREATE TABLE providers (
                    id serial PRIMARY KEY, slug text UNIQUE, name text,
                    website_url text, category text, is_active boolean,
                    has_adapter boolean, metadata_json json
                )
            """)
            )
            connection.execute(text("CREATE TABLE fetch_runs (id serial PRIMARY KEY)"))
            connection.execute(text("CREATE TABLE raw_records (id serial PRIMARY KEY)"))
            connection.execute(
                text("""
                CREATE TABLE quotes (
                    id serial PRIMARY KEY, provider provider_name NOT NULL,
                    asset_id integer, base_currency text, quote_currency text,
                    quote_type text, captured_at timestamptz,
                    superseded_at timestamptz, metadata_json json
                )
            """)
            )
            connection.execute(
                text("""
                CREATE UNIQUE INDEX uq_quotes_current_pair ON quotes
                    (provider, asset_id, base_currency, quote_currency, quote_type)
                WHERE superseded_at IS NULL
            """)
            )

        with engine.begin() as connection:
            connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
            connection.execute(
                text("""
                INSERT INTO quotes (provider, asset_id, base_currency, quote_currency,
                                    quote_type, captured_at, metadata_json)
                VALUES ('QUIDAX', 1, 'EUR', 'USD', 'SELL', now(), '{"environment":"sandbox"}')
            """)
            )
            if wise_already_committed:
                connection.execute(
                    text("""
                    INSERT INTO quotes (provider, asset_id, base_currency, quote_currency,
                                        quote_type, captured_at, superseded_at, metadata_json)
                    VALUES ('WISE', 1, 'EUR', 'USD', 'SELL', now() - interval '1 minute',
                            now(), '{"environment":"production","marker":"preserve"}'),
                           ('WISE', 1, 'EUR', 'USD', 'SELL', now(), NULL,
                            '{"environment":"sandbox"}')
                """)
                )

        # Alembic's environment batches these upgrades in one outer transaction.
        with engine.begin() as connection:
            connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
            with Operations.context(MigrationContext.configure(connection)):
                for module in (
                    "a7b8c9d0e1f2_add_wise_fx",
                    "b8c9d0e1f2a3_fx_local_conversion",
                    "c9d0e1f2a3b4_shared_fx_observations",
                    "d0e1f2a3b4c5_fx_currency_activity",
                    "e1f2a3b4c5d6_flutterwave_transfer_rates",
                ):
                    importlib.import_module(f"app.migrations.versions.{module}").upgrade()

        with engine.connect() as connection:
            connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
            assert (
                connection.execute(
                    text("SELECT environment FROM quotes WHERE provider::text = 'QUIDAX'")
                ).scalar_one()
                == "production"
            )
            assert connection.execute(text("SELECT count(*) FROM providers")).scalar_one() == 2
            assert connection.execute(text("SELECT count(*) FROM fx_currencies")).scalar_one() == 0
            if wise_already_committed:
                rows = connection.execute(
                    text("""
                    SELECT environment, superseded_at, metadata_json FROM quotes
                    WHERE provider::text = 'WISE' ORDER BY captured_at
                """)
                ).all()
                assert [row.environment for row in rows] == ["production", "sandbox"]
                assert all(row.superseded_at is None for row in rows)
                assert rows[0].metadata_json["marker"] == "preserve"
    finally:
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        engine.dispose()
