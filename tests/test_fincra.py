import asyncio
import json
from copy import deepcopy
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient
from test_stanbic_ingestion import db as existing_database

from app.adapters.fx.fincra import HOSTS, PATH, FincraAdapter, FincraResponse
from app.core.exceptions import AppError
from app.models.enums import FetchRunStatus, IngestionJobType, ProviderName
from app.models.fetch_run import FetchRun
from app.models.quote import Quote, QuoteObservation
from app.models.raw_record import RawRecord
from app.schemas.fx import FxConversionRequest
from app.services.fx import FxService
from app.services.ingestion.fincra import FincraIngestionService
from app.services.ingestion.fx import supported_fx_jobs

db = existing_database
FIXTURE = Path(__file__).parent / "fixtures/fincra/sandbox_rates_2026-11-04.json"


def page(number=1, total=2):
    # Prices from the official USD-NGN example. Pagination is synthetic for testing.
    return {
        "success": True,
        "data": {
            "rates": [
                {
                    "baseCurrency": "USD",
                    "quoteCurrency": "NGN",
                    "side": "buy" if number == 1 else "sell",
                    "price": "1486" if number == 1 else "1503",
                }
            ],
            "pagination": {
                "page": number,
                "perPage": 1,
                "totalItems": total,
                "totalPages": total,
                "timestamp": "2025-10-07T15:24:52.930Z",
            },
        },
    }


def adapter(pages=None, environment="sandbox"):
    provider = FincraAdapter(secret_key="fixture-secret", base_url=HOSTS[environment])
    pages = pages or [page(1), page(2)]

    async def fetch(number, *, client):
        payload = pages[number - 1]
        return FincraResponse(
            200, HOSTS[environment] + PATH + f"?page={number}", json.dumps(payload), payload
        )

    provider.fetch_page = AsyncMock(side_effect=fetch)
    return provider


def ingest(db, provider=None):
    return asyncio.run(
        FincraIngestionService(db, adapter=provider or adapter()).ingest_market_data()
    )


def request(**values):
    return FxConversionRequest.model_validate(
        {
            "provider": "fincra",
            "source_currency": "USD",
            "target_currency": "NGN",
            "source_amount": "100",
            **values,
        }
    )


def stored_rate(db, side="buy"):
    repository = FxService(db).treasury
    return repository.read(repository.get_rate("USD", "NGN", side))


def test_paginated_ingestion_preserves_sides_and_uses_disclosed_customer_mapping(db):
    provider = adapter()
    result = ingest(db, provider)
    assert result["rates_observed"] == result["versions_created"] == 2
    assert provider.fetch_page.await_count == db.query(RawRecord).count() == 2
    service = FxService(db)
    with patch("httpx.AsyncClient", side_effect=AssertionError("No upstream on reads")):
        rates = service.list_rates("fincra").data
        assert rates.pagination.total == 2
        buy, sell = [stored_rate(db, side) for side in ("buy", "sell")]
        assert buy.rate == Decimal("1486") and sell.rate == Decimal("1503")
        assert buy.side == "buy" and buy.side_perspective == "unverified"
        assert buy.rate_direction == "unverified" and buy.provider_time is None
        estimate = service.convert(request()).data
        assert estimate.gross_target_amount == Decimal("148600.00")
        assert estimate.metadata["fincra_mapping"]["status"] == "assumed"
        assert estimate.reference_rate is None and estimate.rate_classification == "treasury_rate"
        assert estimate.fee_status == "unavailable" and estimate.net_target_amount is None
        assert estimate.provider_rate_timestamp is None
        assert estimate.calculation_basis == "stored_treasury_rate_estimate"
        currencies = service.list_currencies("fincra").data.items
        assert [c.code for c in currencies] == ["NGN", "USD"]
        assert all(c.discovery_basis == "observed_rate_pairs" for c in currencies)


@pytest.mark.parametrize(
    "changes",
    [
        {"rate_side": None},
        {"rate_side": "mid"},
        {"source_amount": "0"},
        {"source_amount": "NaN"},
        {"target_currency": "USD"},
    ],
)
def test_invalid_calculation_requests(changes):
    with pytest.raises(ValueError):
        request(**changes)


@pytest.mark.parametrize(
    "changes",
    [{"target_currency": "EUR"}, {"source_currency": "NGN", "target_currency": "EUR"}],
)
def test_no_cross_rate_fallback(db, changes):
    ingest(db)
    with patch("httpx.AsyncClient", side_effect=AssertionError("No upstream")):
        with pytest.raises(AppError) as error:
            FxService(db).convert(request(**changes))
    assert error.value.error_code == "fx_rate_unavailable"


@pytest.mark.parametrize(
    "kind",
    [
        "later_page_failure",
        "wrong_page",
        "changed_total",
        "duplicate_side",
        "negative",
        "empty",
        "malformed",
    ],
)
def test_bad_snapshot_preserves_prior_rates_and_raw_evidence(db, kind):
    ingest(db)
    before = [(r.id, r.superseded_at) for r in db.query(Quote).all()]
    pages = [page(1), page(2)]
    if kind == "wrong_page":
        pages[1]["data"]["pagination"]["page"] = 1
    elif kind == "changed_total":
        pages[1]["data"]["pagination"].update(totalItems=3, totalPages=3)
    elif kind == "duplicate_side":
        pages[1]["data"]["rates"][0]["side"] = "buy"
    elif kind == "negative":
        pages[1]["data"]["rates"][0]["price"] = "-1"
    elif kind == "empty":
        pages[1]["data"]["rates"] = []
    elif kind == "malformed":
        pages[1] = {"success": False}
    provider = adapter(pages)
    if kind == "later_page_failure":
        first = FincraResponse(200, HOSTS["sandbox"] + PATH, json.dumps(pages[0]), pages[0])
        provider.fetch_page.side_effect = [first, RuntimeError("network")]
    with pytest.raises(AppError):
        ingest(db, provider)
    assert [(r.id, r.superseded_at) for r in db.query(Quote).all()] == before
    assert db.query(RawRecord).count() >= 3


def test_complete_snapshot_retires_missing_side_and_currency(db):
    ingest(db)
    remaining = page(1, total=1)
    remaining["data"]["rates"][0]["quoteCurrency"] = "EUR"
    ingest(db, adapter([remaining]))
    service = FxService(db)
    assert service.list_rates("fincra").data.pagination.total == 1
    assert [r.code for r in service.list_currencies("fincra").data.items] == ["EUR", "USD"]
    assert db.query(Quote).count() == 3
    assert db.query(Quote).filter(Quote.superseded_at.is_not(None)).count() == 2


def test_missing_secret_and_bad_base_url_skip_without_network(db):
    for secret, base_url in [("", "https://sandboxapi.fincra.com"), ("x", "https://wrong.invalid")]:
        provider = FincraAdapter(secret_key=secret, base_url=base_url)
        provider.fetch_page = AsyncMock(side_effect=AssertionError("No network"))
        assert ingest(db, provider)["status"] == "skipped"
        provider.fetch_page.assert_not_awaited()
    assert db.query(Quote).count() == db.query(RawRecord).count() == 0


def test_late_older_snapshot_cannot_replace_even_unchanged_newer_snapshot(db):
    ingest(db)
    old = adapter([page(1, total=1)])
    old.fetch_page.side_effect = None

    async def delayed(number, *, client):
        await FincraIngestionService(db, adapter=adapter()).ingest_market_data()
        payload = page(1, total=1)
        payload["data"]["rates"][0]["price"] = "100"
        return FincraResponse(200, HOSTS["sandbox"] + PATH, json.dumps(payload), payload)

    old.fetch_page.side_effect = delayed
    assert ingest(db, old)["status"] == "skipped"
    assert db.query(Quote).count() == 2
    assert db.query(QuoteObservation).count() == 4
    assert stored_rate(db).rate == 1486


def test_http_auth_fixed_hosts_and_secret_redaction():
    calls = []

    def handler(req):
        calls.append(req)
        assert req.headers["api-key"] == "fixture-secret"
        assert req.url.params["page"] == "1"
        return httpx.Response(401, json={"message": "fixture-secret"})

    async def fetch():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await FincraAdapter(secret_key="fixture-secret").fetch_page(1, client=client)

    response = asyncio.run(fetch())
    assert "fixture-secret" not in response.raw_text
    with pytest.raises(AppError) as error:
        FincraAdapter.parse_page(response, 1)
    assert error.value.error_code == "fincra_access_unavailable"
    assert calls[0].url.host == "sandboxapi.fincra.com"


def test_long_retry_after_does_not_retry_early():
    calls = []

    def handler(req):
        calls.append(req)
        return httpx.Response(429, headers={"Retry-After": "60"}, json={})

    async def fetch():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await FincraAdapter(secret_key="fixture-secret").fetch_page(1, client=client)

    response = asyncio.run(fetch())
    assert len(calls) == 1
    with pytest.raises(AppError) as error:
        FincraAdapter.parse_page(response, 1)
    assert error.value.error_code == "fincra_rate_limited"


def test_shared_api_serialization_and_registry(db):
    from app.core.database import get_db
    from app.main import app
    from app.routers.fx import get_fx_service

    ingest(db)
    service = FxService(db)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_fx_service] = lambda: service
    try:
        client = TestClient(app)
        with patch("httpx.AsyncClient", side_effect=AssertionError("No upstream")):
            rates = client.get("/fx/fincra/rates")
            assert rates.status_code == 200
            assert rates.json()["data"]["items"][0]["classification"] == "treasury_rate"
            assert client.get("/fx/fincra/currencies").status_code == 200
            result = client.post("/fx/convert", json=request().model_dump(mode="json"))
            assert result.status_code == 200, result.text
            assert result.json()["data"]["metadata"]["fincra_mapping"]["status"] == "assumed"
    finally:
        app.dependency_overrides.clear()
    assert supported_fx_jobs("fincra") == {IngestionJobType.MARKET_DATA}
    assert ProviderName.FINCRA.value == "fincra"


def test_captured_mixed_asset_snapshot_collects_all_pages_and_serves_fiat_rates(db):
    provider = adapter(json.loads(FIXTURE.read_text()))
    result = ingest(db, provider)
    assert result["status"] == "success" and result["snapshot_complete"]
    assert result["pages_fetched"] == provider.fetch_page.await_count == 4
    assert result["rates_received"] == 34
    assert result["rates_observed"] == result["versions_created"] == 28
    assert result["rates_excluded"] == len(result["excluded_rates"]) == 6
    assert {r["quote_currency"] for r in result["excluded_rates"]} == {"CNGN", "USDC", "USDT"}
    assert db.query(RawRecord).count() == 4
    assert db.query(Quote).count() == db.query(QuoteObservation).count() == 28
    assert db.get(FetchRun, result["fetch_run_id"]).status == FetchRunStatus.SUCCESS
    first_raw = db.query(RawRecord).order_by(RawRecord.id).first()
    assert first_raw.payload["response"]["data"]["rates"][6]["quoteCurrency"] == "CNGN"
    service = FxService(db)
    with patch("httpx.AsyncClient", side_effect=AssertionError("No upstream on reads")):
        assert service.list_rates("fincra").data.pagination.total == 28
        codes = {item.code for item in service.list_currencies("fincra").data.items}
        assert {"USD", "NGN", "CNH"} <= codes
        assert not codes & {"CNGN", "USDC", "USDT"}
        assert stored_rate(db).rate == Decimal("1387.13")
        estimate = service.convert(request()).data
        assert estimate.gross_target_amount == Decimal("138713.00")
        assert estimate.metadata["fincra_mapping"]["provider_side"] == "buy"


def test_digital_asset_only_middle_page_does_not_end_collection(db):
    pages = [page(n, total=3) for n in range(1, 4)]
    pages[1]["data"]["rates"][0]["quoteCurrency"] = "CNGN"
    provider = adapter(pages)
    result = ingest(db, provider)
    assert provider.fetch_page.await_count == result["pages_fetched"] == 3
    assert result["rates_received"] == 3 and result["rates_excluded"] == 1
    assert result["rates_observed"] == 2 and result["snapshot_complete"]


def test_digital_asset_only_snapshot_preserves_previous_rates(db):
    ingest(db)
    before = [(q.id, q.last_seen_at, q.superseded_at) for q in db.query(Quote).all()]
    pages = [page(1), page(2)]
    for payload in pages:
        payload["data"]["rates"][0]["quoteCurrency"] = "USDT"
    with pytest.raises(AppError, match="no eligible FX rates"):
        ingest(db, adapter(pages))
    assert [(q.id, q.last_seen_at, q.superseded_at) for q in db.query(Quote).all()] == before
    run = db.query(FetchRun).order_by(FetchRun.id.desc()).first()
    assert run.metadata_json["rates_received"] == run.metadata_json["rates_excluded"] == 2
    assert run.metadata_json["snapshot_complete"] is False


@pytest.mark.parametrize("change", ["feed_timestamp", "page_order", "both"])
def test_observation_metadata_does_not_create_price_versions(db, change):
    ingest(db)
    initial = {row.id: row.captured_at for row in db.query(Quote).all()}
    pages = [page(1), page(2)]
    if change in {"feed_timestamp", "both"}:
        for payload in pages:
            payload["data"]["pagination"]["timestamp"] = "2026-11-04T20:00:00Z"
    if change in {"page_order", "both"}:
        pages[0]["data"]["rates"], pages[1]["data"]["rates"] = (
            pages[1]["data"]["rates"],
            pages[0]["data"]["rates"],
        )
    result = ingest(db, adapter(pages))
    assert result["rates_observed"] == 2 and result["versions_created"] == 0
    assert {row.id: row.captured_at for row in db.query(Quote).all()} == initial
    assert db.query(QuoteObservation).count() == 4
    for row in db.query(Quote).all():
        latest = (
            db.query(QuoteObservation)
            .filter_by(quote_id=row.id)
            .order_by(QuoteObservation.id.desc())
            .first()
        )
        assert row.raw_record_id == latest.raw_record_id
        assert row.fetch_run_id == latest.fetch_run_id == result["fetch_run_id"]
        raw = db.get(RawRecord, latest.raw_record_id)
        assert row.metadata_json["source_url"] == raw.source_url
        assert datetime.fromisoformat(
            row.metadata_json["feed_timestamp"]
        ) == datetime.fromisoformat(raw.payload["response"]["data"]["pagination"]["timestamp"])


def test_exact_price_change_still_creates_version(db):
    ingest(db)
    pages = [page(1), page(2)]
    pages[0]["data"]["rates"][0]["price"] = "1486.0000000001"
    result = ingest(db, adapter(pages))
    assert result["versions_created"] == 1
    assert db.query(Quote).count() == 3 and db.query(QuoteObservation).count() == 4
    assert stored_rate(db).rate == Decimal("1486.0000000001")


@pytest.mark.parametrize(
    "field,value", [("price", "fixture-secret"), ("quoteCurrency", "ZZZZ"), ("price", "NaN")]
)
def test_validation_errors_identify_page_row_and_field_without_echoing_input(db, field, value):
    ingest(db)
    pages = [page(1), page(2)]
    pages[1]["data"]["rates"][0][field] = value
    with pytest.raises(AppError) as raised:
        ingest(db, adapter(pages))
    error = raised.value
    assert error.data["page"] == 2 and error.data["row"] == 1
    assert error.data["base_currency"] == "USD"
    assert any(detail["loc"][0] == field for detail in error.data["errors"])
    assert "fixture-secret" not in str(error.data)
    raw = db.get(RawRecord, error.data["raw_record_id"])
    assert raw.fetch_run_id == error.data["fetch_run_id"]
    run = db.get(FetchRun, raw.fetch_run_id)
    assert run.metadata_json["error_details"]["page"] == 2
    assert not run.metadata_json["snapshot_complete"]
    assert db.query(Quote).count() == db.query(QuoteObservation).count() == 2


def test_malformed_digital_asset_record_is_not_silently_excluded(db):
    payload = page(1, total=1)
    payload["data"]["rates"][0].update(quoteCurrency="USDC", price="-1")
    with pytest.raises(AppError) as raised:
        ingest(db, adapter([payload]))
    assert raised.value.data["errors"][0]["loc"][0] == "price"
    assert db.query(Quote).count() == 0


def test_persistence_failure_rolls_back_retirement_and_latest_observation_context(db):
    from sqlalchemy import event

    ingest(db)
    before = [
        (
            q.id,
            q.raw_record_id,
            q.fetch_run_id,
            q.last_seen_at,
            q.superseded_at,
            deepcopy(q.metadata_json),
        )
        for q in db.query(Quote).order_by(Quote.id).all()
    ]
    pages = [page(1), page(2)]
    for payload in pages:
        payload["data"]["pagination"]["timestamp"] = "2026-11-04T20:00:00Z"
    pages[1]["data"]["rates"][0]["quoteCurrency"] = "EUR"
    inserts = 0

    def fail_second_observation(connection, cursor, statement, parameters, context, many):
        nonlocal inserts
        if statement.startswith("INSERT INTO quote_observations"):
            inserts += 1
            if inserts == 2:
                raise RuntimeError("Synthetic persistence failure")

    event.listen(db.bind, "before_cursor_execute", fail_second_observation)
    try:
        with pytest.raises(AppError):
            ingest(db, adapter(pages))
    finally:
        event.remove(db.bind, "before_cursor_execute", fail_second_observation)
    assert inserts == 2
    assert [
        (q.id, q.raw_record_id, q.fetch_run_id, q.last_seen_at, q.superseded_at, q.metadata_json)
        for q in db.query(Quote).order_by(Quote.id).all()
    ] == before
    assert db.query(QuoteObservation).count() == 2


def test_base_url_selects_upstream_without_partitioning_database_reads(db):
    ingest(db, adapter(environment="sandbox"))
    first = stored_rate(db, "sell")
    assert "sandboxapi.fincra.com" in first.source_url
    result = ingest(db, adapter(environment="production"))
    latest = stored_rate(db, "sell")
    assert result["versions_created"] == 0
    assert first.id == latest.id
    assert "https://api.fincra.com" in latest.source_url
    assert "environment" not in latest.model_dump()
    assert FxService(db).list_rates("fincra").data.pagination.total == 2
    assert all("environment" not in row.metadata_json for row in db.query(Quote).all())


@pytest.mark.parametrize(
    "source,target,amount,side,inverted,expected",
    [
        ("USD", "NGN", "100", "buy", False, "148600.00"),
        ("NGN", "USD", "150300", "sell", True, "100.00"),
    ],
)
def test_assumed_direction_keeps_original_price_and_observation_provenance(
    db, source, target, amount, side, inverted, expected
):
    from datetime import UTC, timedelta

    from app.services.fx import utc

    ingest(db)
    selected = FxService(db).treasury.get_rate("USD", "NGN", side)
    captured = datetime(2026, 11, 1, tzinfo=UTC)
    observed = captured + timedelta(days=1)
    selected.captured_at, selected.last_seen_at = captured, observed
    db.commit()
    before = [(q.id, q.metadata_json.copy(), q.superseded_at) for q in db.query(Quote).all()]
    with patch("httpx.AsyncClient", side_effect=AssertionError("No upstream")):
        result = (
            FxService(db, now=lambda: observed + timedelta(hours=2))
            .convert(request(source_currency=source, target_currency=target, source_amount=amount))
            .data
        )
    assert result.gross_target_amount == Decimal(expected)
    assert result.reference_rate is None
    assert result.rate_record_id == selected.id and result.raw_record_id == selected.raw_record_id
    assert result.observed_at == utc(selected.last_seen_at) and result.captured_at == captured
    assert result.provider_rate_timestamp is result.expires_at is None
    assert result.freshness_basis == "collection_timestamp" and result.is_stale
    assert (
        result.metadata["fincra_mapping"]["provider_price"]
        == selected.metadata_json["provider_price"]
    )
    assert result.metadata["fincra_mapping"]["inverted"] is inverted
    assert result.metadata["fincra_mapping"]["status"] == "assumed"
    assert result.fee_amount is result.fee_currency is result.net_target_amount is None
    assert any("assumed Fincra mapping" in warning for warning in result.warnings)
    assert [(q.id, q.metadata_json, q.superseded_at) for q in db.query(Quote).all()] == before


@pytest.mark.parametrize("remaining_side", ["buy", "sell"])
def test_missing_required_side_does_not_fall_back_to_opposite_side(db, remaining_side):
    only = page(1, total=1)
    only["data"]["rates"][0].update(
        side=remaining_side, price="1486" if remaining_side == "buy" else "1503"
    )
    ingest(db, adapter([only]))
    missing_direction = (
        {"source_currency": "NGN", "target_currency": "USD"} if remaining_side == "buy" else {}
    )
    with pytest.raises(AppError) as error:
        FxService(db).convert(request(**missing_direction))
    assert error.value.error_code == "fx_rate_unavailable"
    available_direction = (
        {} if remaining_side == "buy" else {"source_currency": "NGN", "target_currency": "USD"}
    )
    assert FxService(db).convert(request(**available_direction)).data.rate_record_id


def test_direct_buy_is_preferred_when_both_pair_orderings_are_stored(db):
    pages = [page(n, total=4) for n in range(1, 5)]
    for payload, price, side in [(pages[2], "0.0006", "buy"), (pages[3], "0.0008", "sell")]:
        payload["data"]["rates"][0].update(
            baseCurrency="NGN", quoteCurrency="USD", side=side, price=price
        )
    ingest(db, adapter(pages))
    service = FxService(db)
    forward = service.convert(request()).data
    reverse = service.convert(request(source_currency="NGN", target_currency="USD")).data
    assert forward.applied_rate == Decimal("1486")
    assert reverse.applied_rate == Decimal("0.0006")
    assert forward.metadata["fincra_mapping"]["inverted"] is False
    assert reverse.metadata["fincra_mapping"]["inverted"] is False
    assert forward.metadata["fincra_mapping"]["base_currency"] == "USD"
    assert reverse.metadata["fincra_mapping"]["base_currency"] == "NGN"


def test_mapping_is_generic_and_inverse_rounding_uses_target_precision(db):
    pages = [page(1), page(2)]
    for payload, price in zip(pages, ("1.16", "2"), strict=True):
        payload["data"]["rates"][0].update(baseCurrency="EUR", quoteCurrency="USD", price=price)
    ingest(db, adapter(pages))
    service = FxService(db)
    direct = service.convert(
        request(source_currency="EUR", target_currency="USD", source_amount="10")
    ).data
    assert direct.gross_target_amount == Decimal("11.60")
    reverse = service.convert(
        request(source_currency="USD", target_currency="EUR", source_amount="2.01")
    ).data
    assert reverse.applied_rate == Decimal("0.5")
    assert reverse.unrounded_gross_target_amount == Decimal("1.005")
    assert reverse.gross_target_amount == Decimal("1.01")


def test_inverse_precision_is_independent_of_callers_decimal_context(db):
    from decimal import ROUND_DOWN, ROUND_HALF_UP, localcontext

    ingest(db)
    req = request(source_currency="NGN", target_currency="USD", source_amount="123456.78")
    with localcontext() as context:
        context.prec = 3
        context.rounding = ROUND_DOWN
        result = FxService(db).convert(req).data
    with localcontext() as context:
        context.prec = 64
        context.rounding = ROUND_HALF_UP
        expected_rate = Decimal(1) / Decimal("1503")
    assert result.applied_rate == expected_rate
    with localcontext() as context:
        context.prec = 100
        assert result.unrounded_gross_target_amount == req.source_amount * result.applied_rate
    assert result.gross_target_amount == Decimal("82.14")


@pytest.mark.parametrize("price", ["0", "-1", "NaN", "Infinity"])
def test_invalid_stored_price_is_not_rescued_by_assumed_mapping(db, price):
    ingest(db)
    row = FxService(db).treasury.get_rate("USD", "NGN", "buy")
    row.metadata_json = {**row.metadata_json, "provider_price": price}
    db.commit()
    with pytest.raises(AppError) as error:
        FxService(db).convert(request())
    assert error.value.error_code == "fx_rate_unavailable"
    assert db.query(Quote).count() == 2
