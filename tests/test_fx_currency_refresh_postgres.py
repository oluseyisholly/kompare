"""Optional real locking check; restricted to our disposable Unix-socket database."""

import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from sqlalchemy import URL, create_engine, text
from sqlalchemy.orm import Session
from test_fx_currency_refresh import context, normalized
from test_fx_currency_refresh import (
    test_upserts_and_retirement_roll_back_together_and_do_not_advance_watermark as check_atomicity,
)
from test_wise import fixture

from app.models.fx import FxCurrency
from app.models.provider import Provider
from app.repositories.fx import FxRepository


@pytest.mark.skipif(
    not os.getenv("KOMPARE_FX_TEST_PG_SOCKET"),
    reason="Requires an explicitly configured disposable PostgreSQL Unix socket",
)
def test_postgres_overlapping_refresh_waits_then_rejects_older_snapshot():
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
    locked, release = threading.Event(), threading.Event()
    application_name = "fx-refresh-old-" + uuid4().hex
    try:
        with Session(engine) as db:
            initial = context(db)
            db.query(FxCurrency).filter_by(
                provider_id=initial["provider_id"],
            ).delete()
            db.commit()
            FxRepository(db).persist_currencies(
                normalized(fixture("documented_currencies.json")),
                **initial,
                snapshot_complete=True,
            )
            older, newer = context(db), context(db)

        def newer_refresh():
            with Session(engine) as db:
                db.query(Provider.id).filter_by(id=newer["provider_id"]).with_for_update().one()
                locked.set()
                assert release.wait(8), "Test did not release the provider lock"
                records = normalized(fixture("documented_currencies.json")[:1])
                records[0].name = "Newest metadata"
                return FxRepository(db).persist_currencies(records, **newer, snapshot_complete=True)

        def older_refresh():
            with Session(engine) as db:
                db.execute(
                    text("SELECT set_config('application_name', :name, false)"),
                    {"name": application_name},
                )
                db.execute(text("SET LOCAL lock_timeout = '8s'"))
                # Preload old ORM objects too; a cached session must not beat the watermark.
                db.query(FxCurrency).filter_by(provider_id=older["provider_id"]).all()
                return FxRepository(db).persist_currencies(
                    normalized(fixture("documented_currencies.json")[1:]),
                    **older,
                    snapshot_complete=True,
                )

        with ThreadPoolExecutor(max_workers=2) as workers:
            new_job = workers.submit(newer_refresh)
            try:
                assert locked.wait(5)
                old_job = workers.submit(older_refresh)
                deadline = time.monotonic() + 5
                waiting = False
                while time.monotonic() < deadline:
                    with engine.connect() as connection:
                        waiting = connection.execute(
                            text("""
                            SELECT EXISTS (
                                SELECT 1 FROM pg_stat_activity
                                WHERE application_name = :name AND wait_event_type = 'Lock'
                            )
                        """),
                            {"name": application_name},
                        ).scalar()
                    if waiting:
                        break
                    time.sleep(0.01)
                assert waiting, "Older refresh did not wait on the provider row lock"
            finally:
                release.set()
            assert new_job.result(timeout=8)["currencies_deactivated"] == 1
            assert old_job.result(timeout=8)["superseded"] is True
        with Session(engine) as db:
            assert db.query(FxCurrency).filter_by(is_active=True).count() == 1
            aud = db.query(FxCurrency).filter_by(code="AUD").one()
            assert aud.name == "Newest metadata" and aud.fetch_run_id == newer["fetch_run_id"]
            assert not db.query(FxCurrency).filter_by(code="JPY").one().is_active
            check_atomicity(db)
    finally:
        release.set()
        engine.dispose()
