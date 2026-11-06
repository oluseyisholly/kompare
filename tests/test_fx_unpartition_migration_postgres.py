"""Run only against the explicitly configured disposable PostgreSQL test database."""

import importlib
import os
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import URL, create_engine, inspect, text
from sqlalchemy.exc import IntegrityError


@pytest.mark.skipif(not os.getenv("KOMPARE_FX_TEST_PG_SOCKET"), reason="Disposable PostgreSQL only")
@pytest.mark.parametrize("newest", ["production", "sandbox"])
def test_remove_environment_preserves_history_and_selects_latest_observation(newest):
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
    schema = "fx_unpartition_" + uuid4().hex
    try:
        with engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
            statements = [
                """CREATE TABLE quotes (
                    id integer PRIMARY KEY, provider text, asset_id integer,
                    base_currency text, quote_currency text, quote_type text,
                    environment text NOT NULL, captured_at timestamptz,
                    last_seen_at timestamptz, superseded_at timestamptz, metadata_json json)""",
                """CREATE UNIQUE INDEX uq_quotes_current_pair ON quotes
                    (provider, asset_id, base_currency, quote_currency, quote_type, environment)
                    WHERE superseded_at IS NULL""",
                """CREATE TABLE fx_currencies (
                    id integer PRIMARY KEY, provider_id integer, environment text,
                    code text, is_active boolean, captured_at timestamptz,
                    fetch_run_id integer, raw_record_id integer,
                    CONSTRAINT uq_fx_currencies_source UNIQUE(provider_id, environment, code))""",
                "CREATE TABLE fx_quote_observations (id integer PRIMARY KEY, response_data json)",
                "CREATE TABLE raw_records (id integer PRIMARY KEY, payload json)",
                """CREATE TABLE quote_observations (
                    id integer PRIMARY KEY,
                    quote_id integer REFERENCES quotes(id), raw_record_id integer)""",
            ]
            for statement in statements:
                connection.execute(text(statement))
            for row_id, provider, side, environment in (
                (1, "FINCRA", "SELL", "production"),
                (2, "FINCRA", "SELL", "sandbox"),
                (3, "FINCRA", "BUY", "production"),
                (4, "BUSHA", "SELL", "production"),
            ):
                seen = "2026-11-05T12:00:00Z" if environment == newest else "2026-11-04T12:00:00Z"
                connection.execute(
                    text("""
                    INSERT INTO quotes VALUES (:id, :provider, 1, 'USD', 'NGN', :side, :env,
                        '2026-11-01T12:00:00Z', :seen, NULL,
                        json_build_object('environment', :env, 'provider_price', '1405.82'))
                """),
                    {
                        "id": row_id,
                        "provider": provider,
                        "side": side,
                        "env": environment,
                        "seen": seen,
                    },
                )
                connection.execute(
                    text("INSERT INTO quote_observations VALUES (:id, :id, :id)"), {"id": row_id}
                )
            connection.execute(
                text("""
                INSERT INTO fx_currencies VALUES
                    (1, 1, 'production', 'AUD', true, '2026-11-01', 10, 1),
                    (2, 1, 'sandbox', 'AUD', true, '2026-11-02', 20, 2),
                    (3, 1, 'production', 'JPY', true, '2026-11-01', 10, 1),
                    (4, 1, 'sandbox', 'JPY', false, '2026-11-02', 20, 2),
                    (5, 2, 'production', 'AUD', true, '2026-11-01', 10, 1)
            """)
            )
            connection.execute(
                text("""
                INSERT INTO fx_quote_observations VALUES
                    (1, '{"environment":"sandbox","rate":"0.00123456789123456789"}')
            """)
            )
            connection.execute(
                text("""
                INSERT INTO raw_records VALUES
                    (1, '{"environment":"sandbox","original":"preserve"}')
            """)
            )
            migration = importlib.import_module(
                "app.migrations.versions.g3b4c5d6e7f8_remove_fx_environment_partitions"
            )
            with Operations.context(MigrationContext.configure(connection)):
                migration.upgrade()
            for table in ("quotes", "fx_currencies"):
                assert "environment" not in {
                    c["name"] for c in inspect(connection).get_columns(table)
                }
            assert connection.execute(text("SELECT count(*) FROM quotes")).scalar_one() == 4
            assert (
                connection.execute(text("SELECT count(*) FROM quote_observations")).scalar_one()
                == 4
            )
            winner = connection.execute(
                text("""
                SELECT id FROM quotes WHERE provider='FINCRA' AND quote_type='SELL'
                AND superseded_at IS NULL
            """)
            ).scalar_one()
            assert winner == (1 if newest == "production" else 2)
            assert (
                connection.execute(
                    text("SELECT count(*) FROM quotes WHERE superseded_at IS NULL")
                ).scalar_one()
                == 3
            )
            assert connection.execute(text("SELECT count(*) FROM fx_currencies")).scalar_one() == 5
            assert (
                connection.execute(
                    text("SELECT id FROM fx_currencies WHERE provider_id=1 AND is_active")
                ).scalar_one()
                == 2
            )
            assert (
                connection.execute(
                    text("SELECT count(*) FROM fx_currencies WHERE provider_id=2 AND is_active")
                ).scalar_one()
                == 1
            )
            assert connection.execute(
                text("SELECT metadata_json FROM quotes WHERE id=1")
            ).scalar_one() == {"provider_price": "1405.82"}
            assert connection.execute(
                text("SELECT response_data FROM fx_quote_observations")
            ).scalar_one() == {"rate": "0.00123456789123456789"}
            assert connection.execute(text("SELECT payload FROM raw_records")).scalar_one() == {
                "environment": "sandbox",
                "original": "preserve",
            }
            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(
                    text("""
                    INSERT INTO quotes (id, provider, asset_id, base_currency, quote_currency,
                                        quote_type) VALUES (5, 'FINCRA', 1, 'USD', 'NGN', 'SELL')
                """)
                )
            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(
                    text("""
                    INSERT INTO fx_currencies (id, provider_id, code, is_active)
                    VALUES (6, 1, 'AUD', true)
                """)
                )
            with pytest.raises(RuntimeError, match="Cannot reconstruct"):
                migration.downgrade()
    finally:
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        engine.dispose()
