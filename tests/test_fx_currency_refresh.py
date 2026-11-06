import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient
from test_fx import currency_adapter
from test_fx import db as existing_database
from test_wise import fixture

from app.adapters.fx.wise import WiseAdapter
from app.core.exceptions import AppError
from app.models.enums import MarketCategory, ProviderName, RawSourceType
from app.models.fx import FxCurrency
from app.repositories.fetch_run import FetchRunRepository
from app.repositories.fx import FxRepository
from app.repositories.provider import ProviderRepository
from app.repositories.raw_record import RawRecordRepository
from app.schemas.fx import FxCurrencyRecord
from app.services.fx import FxService
from app.services.ingestion.wise import WiseIngestionService

db = existing_database
CAPTURED = datetime(2026, 11, 2, 12, tzinfo=UTC)


def refresh(db, payload=None, *, pagination_pending=False, token="test-only-token"):
    adapter = currency_adapter(payload=payload, token=token)
    adapter.fetch_currencies.return_value.pagination_pending = pagination_pending
    return asyncio.run(WiseIngestionService(db, adapter=adapter).ingest_currencies())


def normalized(payload):
    records, errors = WiseAdapter.parse_currencies(payload)
    assert not errors
    return records


def context(db, *, provider="wise"):
    registered = ProviderRepository(db).get_or_create_by_slug(
        slug=provider,
        name=provider,
        category=MarketCategory.FX,
    )
    provider_id = registered.id
    run_id = FetchRunRepository(db).create_pending(ProviderName(provider)).id
    raw_id = (
        RawRecordRepository(db)
        .create(
            provider=ProviderName(provider),
            fetch_run_id=run_id,
            source_type=RawSourceType.API,
            source_url="https://fixture.example/currencies",
            payload={"test_only": True},
            raw_text='{"test_only": true}',
        )
        .id
    )
    return {
        "provider_id": provider_id,
        "fetch_run_id": run_id,
        "raw_record_id": raw_id,
        "source_url": "https://fixture.example/currencies",
        "captured_at": CAPTURED,
    }


def state(db):
    return {
        (row.provider_id, row.code): (
            row.is_active,
            row.name,
            row.captured_at,
            row.raw_record_id,
            row.fetch_run_id,
        )
        for row in db.query(FxCurrency).all()
    }


def test_complete_snapshot_retires_missing_and_reappearance_reactivates_with_provenance(db):
    refresh(db)
    old = db.query(FxCurrency).filter_by(code="JPY").one()
    old_id, old_raw_id, old_run, old_capture = (
        old.id,
        old.raw_record_id,
        old.fetch_run_id,
        old.captured_at,
    )
    result = refresh(db, fixture("documented_currencies.json")[:1])
    assert result["snapshot_complete"] is True
    assert result["currencies_observed"] == result["currencies_deactivated"] == 1
    assert FxService(db).list_currencies("wise").data.pagination.total == 1
    old = db.get(FxCurrency, old_id)
    assert not old.is_active
    assert (old.raw_record_id, old.fetch_run_id, old.captured_at) == (
        old_raw_id,
        old_run,
        old_capture,
    )
    provider_id = old.provider_id
    assert FxRepository(db).get_currency(provider_id=provider_id, code="JPY") is None
    reappeared = fixture("documented_currencies.json")
    reappeared[1]["name"] = "Updated Japanese yen"
    refresh(db, reappeared)
    updated = db.get(FxCurrency, old_id)
    assert updated.is_active and updated.name == "Updated Japanese yen"
    assert updated.raw_record_id != old_raw_id and updated.fetch_run_id != old_run
    assert db.query(FxCurrency).count() == 2
    assert FxService(db).list_currencies("wise").data.pagination.total == 2


def test_partial_parsing_updates_valid_records_without_retiring_missing_records(db):
    refresh(db)
    prior = db.query(FxCurrency).filter_by(code="JPY").one().raw_record_id
    payload = fixture("documented_currencies.json")
    payload[0]["name"] = "Updated Australian dollar"
    payload[1]["supportsDecimals"] = "invalid"
    result = refresh(db, payload)
    assert result["status"] == "partial" and result["snapshot_complete"] is False
    assert result["currencies_deactivated"] == 0
    assert db.query(FxCurrency).filter_by(code="AUD").one().name == "Updated Australian dollar"
    jpy = db.query(FxCurrency).filter_by(code="JPY").one()
    assert jpy.is_active and jpy.raw_record_id == prior


@pytest.mark.parametrize("failure", ["credentials", "network", "http", "malformed", "empty"])
def test_failed_and_empty_refreshes_preserve_current_active_records(db, failure):
    refresh(db)
    before = state(db)
    adapter = currency_adapter()
    if failure == "credentials":
        adapter.token = ""
    elif failure == "network":
        adapter.fetch_currencies.side_effect = RuntimeError("network unavailable")
    elif failure == "http":
        adapter.fetch_currencies.return_value.status_code = 503
    elif failure == "malformed":
        adapter.fetch_currencies.return_value.payload = {"unexpected": "object"}
    else:
        adapter.fetch_currencies.return_value.payload = []
    operation = WiseIngestionService(db, adapter=adapter).ingest_currencies()
    if failure == "credentials":
        assert asyncio.run(operation)["status"] == "skipped"
        adapter.fetch_currencies.assert_not_awaited()
    else:
        with pytest.raises(AppError):
            asyncio.run(operation)
    assert state(db) == before


def test_unretrieved_pagination_updates_only_seen_records(db):
    refresh(db)
    result = refresh(db, fixture("documented_currencies.json")[:1], pagination_pending=True)
    assert result["snapshot_complete"] is False and result["status"] == "partial"
    assert result["currencies_deactivated"] == 0
    assert db.query(FxCurrency).filter_by(code="JPY").one().is_active
    assert any("unretrieved pages" in f["error"] for f in result["extraction_failures"])


@pytest.mark.parametrize("relation", ["next", "prev"])
def test_adapter_detects_page_links_without_following_them(relation):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            200,
            json=fixture("documented_currencies.json"),
            headers={
                "Link": f'<https://api.wise.com/2026Q4/currencies?page=2>; rel="{relation}"',
            },
        )

    async def fetch():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await WiseAdapter(token="test-only-token", quote_token="").fetch_currencies(
                client=client
            )

    assert asyncio.run(fetch()).pagination_pending is True
    assert len(calls) == 1


def test_reconciliation_is_scoped_to_provider_across_source_urls(db):
    repository = FxRepository(db)
    records = normalized(fixture("documented_currencies.json"))
    for provider in ("wise", "busha"):
        repository.persist_currencies(
            records, **context(db, provider=provider), snapshot_complete=True
        )
    changed_source = context(db)
    changed_source["source_url"] = "https://api.wise-sandbox.com/2026Q4/currencies"
    result = repository.persist_currencies(records[:1], **changed_source, snapshot_complete=True)
    assert result["currencies_deactivated"] == 1
    retired = db.query(FxCurrency).filter_by(is_active=False).one()
    assert retired.code == "JPY"
    assert retired.provider_id == ProviderRepository(db).get_by_slug("wise").id
    assert db.query(FxCurrency).filter_by(is_active=True).count() == 3


def test_public_list_and_pagination_count_only_active_currencies_without_network(db):
    from app.core.database import get_db
    from app.main import app

    refresh(db)
    refresh(db, fixture("documented_currencies.json")[:1])
    app.dependency_overrides[get_db] = lambda: db
    try:
        with patch(
            "httpx.AsyncClient", side_effect=AssertionError("No network during currency reads")
        ):
            client = TestClient(app)
            data = client.get("/fx/wise/currencies?page=1&per_page=1").json()["data"]
            assert [row["code"] for row in data["items"]] == ["AUD"]
            assert data["pagination"]["total"] == data["pagination"]["total_pages"] == 1
            assert not data["pagination"]["has_next"]
            assert client.get("/fx/wise/currencies?page=2&per_page=1").json()["data"]["items"] == []
    finally:
        app.dependency_overrides.clear()


def test_older_refresh_cannot_overwrite_or_reactivate_after_newer_complete_snapshot(db):
    refresh(db)
    older = context(db)
    newer = context(db)
    latest = normalized(fixture("documented_currencies.json")[:1])
    latest[0].name = "Newest AUD metadata"
    repository = FxRepository(db)
    repository.persist_currencies(latest, **newer, snapshot_complete=True)
    before = state(db)
    older["captured_at"] = CAPTURED + timedelta(days=1)  # Late completion is not a newer request.
    skipped = repository.persist_currencies(
        normalized(fixture("documented_currencies.json")[1:]),
        **older,
        snapshot_complete=True,
    )
    assert skipped["superseded"] and skipped["currencies_observed"] == 0
    assert skipped["latest_currency_fetch_run_id"] == newer["fetch_run_id"]
    assert state(db) == before
    assert not db.query(FxCurrency).filter_by(code="JPY").one().is_active


def test_incomplete_snapshot_never_reconciles_and_completeness_is_required(db):
    refresh(db)
    repository = FxRepository(db)
    result = repository.persist_currencies(
        normalized(fixture("documented_currencies.json")[:1]),
        **context(db),
        snapshot_complete=False,
    )
    assert result["currencies_deactivated"] == 0
    assert db.query(FxCurrency).filter_by(code="JPY").one().is_active
    with pytest.raises(TypeError, match="snapshot_complete"):
        repository.persist_currencies(
            normalized(fixture("documented_currencies.json")[:1]), **context(db)
        )
    with pytest.raises(ValueError, match="Empty currency snapshots"):
        repository.persist_currencies([], **context(db), snapshot_complete=True)
    assert db.query(FxCurrency).filter_by(is_active=True).count() == 2


def test_upserts_and_retirement_roll_back_together_and_do_not_advance_watermark(db):
    refresh(db)
    before = state(db)
    pending_older = context(db)
    failed_newer = context(db)
    records = normalized(fixture("documented_currencies.json")[:1])
    records[0].name = "Must roll back"
    records.append(FxCurrencyRecord(code="CAD", name="New currency", supports_decimals=True))

    def fail_after_flush():
        db.flush()
        assert not db.query(FxCurrency).filter_by(code="JPY").one().is_active
        assert db.query(FxCurrency).filter_by(code="CAD").count() == 1
        raise RuntimeError("simulated failure after SQL changes")

    with patch.object(db, "commit", side_effect=fail_after_flush):
        with pytest.raises(RuntimeError, match="simulated failure"):
            FxRepository(db).persist_currencies(records, **failed_newer, snapshot_complete=True)
    assert state(db) == before
    assert db.query(FxCurrency).filter_by(code="CAD").count() == 0
    applied = FxRepository(db).persist_currencies(
        normalized(fixture("documented_currencies.json")[:1]),
        **pending_older,
        snapshot_complete=True,
    )
    assert not applied["superseded"] and applied["currencies_deactivated"] == 1


def test_inactive_provider_currency_capability_is_not_used_for_conversion_precision(db):
    from test_fx import calculate, conversion, ingest_rate

    ingest_rate(db, target="JPY", rate="160.123")
    refresh(db)
    jpy = db.query(FxCurrency).filter_by(code="JPY").one()
    jpy.decimal_places = 3  # A distinct provider-specific precision, retained only as history.
    db.commit()
    refresh(db, fixture("documented_currencies.json")[:1])
    result = calculate(db, conversion(target_currency="JPY"))
    assert result.target_decimal_places == 0
    assert "six-group.com" in result.precision_source


def test_ingestion_reports_older_overlapping_refresh_as_superseded(db):
    refresh(db)
    old_adapter = currency_adapter(payload=fixture("documented_currencies.json")[1:])
    old_response = old_adapter.fetch_currencies.return_value
    applied = {}

    async def finish_after_newer_refresh(*, client):
        applied.update(
            await WiseIngestionService(
                db,
                adapter=currency_adapter(payload=fixture("documented_currencies.json")[:1]),
            ).ingest_currencies()
        )
        return old_response

    old_adapter.fetch_currencies.side_effect = finish_after_newer_refresh
    result = asyncio.run(WiseIngestionService(db, adapter=old_adapter).ingest_currencies())
    assert result["status"] == "skipped"
    assert result["skip_reason"] == "newer_currency_refresh_already_applied"
    assert result["latest_currency_fetch_run_id"] == applied["fetch_run_id"]
    assert result["currencies_observed"] == 0
    assert not db.query(FxCurrency).filter_by(code="JPY").one().is_active


def test_partial_http_content_does_not_retire_missing_currencies(db):
    refresh(db)
    adapter = currency_adapter(payload=fixture("documented_currencies.json")[:1])
    adapter.fetch_currencies.return_value.status_code = 206
    result = asyncio.run(WiseIngestionService(db, adapter=adapter).ingest_currencies())
    assert result["status"] == "partial" and result["snapshot_complete"] is False
    assert result["currencies_observed"] == 1 and result["currencies_deactivated"] == 0
    assert db.query(FxCurrency).filter_by(code="JPY").one().is_active
