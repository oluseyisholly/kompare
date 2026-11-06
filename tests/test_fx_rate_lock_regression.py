from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import event, update
from test_fx import PROVIDER_TIME, ingest_rate
from test_stanbic_ingestion import db as existing_database

from app.models.asset import Asset
from app.models.quote import Quote, QuoteObservation
from app.services.fx import FxService

db = existing_database


@pytest.mark.parametrize("environment", ["production", "sandbox"])
def test_rate_refresh_checks_timestamp_after_lock_and_refreshes_cached_row(db, environment):
    ingest_rate(db, rate="1.1", timestamp=PROVIDER_TIME, environment=environment)
    cached = db.query(Quote).one()
    old_last_seen = cached.last_seen_at
    observations = db.query(QuoteObservation).count()
    newer_metadata = {
        **cached.metadata_json,
        "provider_rate": "1.3",
        "provider_time": (PROVIDER_TIME + timedelta(minutes=2)).isoformat(),
    }
    injected = False

    def newer_writer_finishes_before_lock(state):
        nonlocal injected
        statement = state.statement
        if (
            not injected
            and state.is_select
            and statement._for_update_arg is not None
            and any(item.get("entity") is Asset for item in statement.column_descriptions)
        ):
            injected = True
            # Model a writer completing while this session waits for the parent lock.
            # Leave its identity-map copy stale to also verify populate_existing.
            db.execute(
                update(Quote)
                .where(Quote.id == cached.id)
                .values(mid_rate=Decimal("1.3"), metadata_json=newer_metadata),
                execution_options={"synchronize_session": False},
            )

    event.listen(db, "do_orm_execute", newer_writer_finishes_before_lock)
    try:
        ingest_rate(
            db,
            rate="1.2",
            timestamp=PROVIDER_TIME + timedelta(minutes=1),
        )
    finally:
        event.remove(db, "do_orm_execute", newer_writer_finishes_before_lock)
    assert injected
    result = FxService(db).list_rates("wise").data.items[0]
    assert result.rate == Decimal("1.3")
    assert result.provider_time == PROVIDER_TIME + timedelta(minutes=2)
    assert db.query(Quote).count() == 1
    assert db.query(QuoteObservation).count() == observations
    assert db.query(Quote).one().last_seen_at == old_last_seen
