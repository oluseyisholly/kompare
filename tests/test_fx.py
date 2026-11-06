import asyncio
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from test_wise import adapter as quote_adapter
from test_wise import db as existing_database
from test_wise import fixture as wise_fixture
from test_wise import request as quote_request

from app.adapters.fx.wise import WiseAdapter, WiseResponse
from app.core.exceptions import AppError
from app.models.enums import (
    FetchRunStatus,
    IngestionJobType,
    MarketCategory,
    ProviderName,
    QuoteType,
)
from app.models.fetch_run import FetchRun
from app.models.fx import FxCurrency
from app.models.provider import Provider
from app.models.quote import Quote
from app.models.raw_record import RawRecord
from app.repositories.quote import QuoteRepository
from app.schemas.fx import FxConversionRequest
from app.services.fx import FxService
from app.services.ingestion.wise import WiseIngestionService
from app.services.wise import WiseService

db = existing_database
NOW = datetime(2026, 11, 2, 12, tzinfo=UTC)
PROVIDER_TIME = NOW - timedelta(seconds=30)


def ingest_rate(
    db,
    *,
    source="EUR",
    target="USD",
    rate="1.166",
    environment="production",
    timestamp=PROVIDER_TIME,
):
    base = "https://api.wise-sandbox.com" if environment == "sandbox" else "https://api.wise.com"
    adapter = WiseAdapter(token="fixture-only-token", quote_token="", base_url=base)
    data = [{"source": source, "target": target, "rate": rate, "time": timestamp.isoformat()}]
    adapter.fetch_rates = AsyncMock(
        return_value=WiseResponse(
            base + "/2026Q4/rates",
            200,
            data,
            json.dumps(data),
        )
    )
    asyncio.run(WiseIngestionService(db, adapter=adapter).ingest_market_data())
    return adapter


def conversion(**fields):
    return FxConversionRequest(
        **{
            "provider": "wise",
            "source_currency": "EUR",
            "target_currency": "USD",
            "source_amount": "100.00",
            **fields,
        }
    )


def calculate(db, request=None, **kwargs):
    return FxService(db, now=lambda: NOW, **kwargs).convert(request or conversion()).data


def test_local_conversion_preserves_precision_and_unknown_fees(db):
    ingest_rate(db, rate="1.123456789123456789")
    result = calculate(db)
    assert result.reference_rate == Decimal("1.123456789123456789")
    assert result.unrounded_gross_target_amount == Decimal("112.34567891234567890000")
    assert result.gross_target_amount == Decimal("112.35")
    assert result.target_decimal_places == 2 and result.rounding_policy == "ROUND_HALF_UP"
    assert result.fee_status == "unavailable"
    assert result.fee_amount is result.fee_currency is result.estimated_net_target_amount is None
    assert not result.transfer_route_verified and not result.executable
    assert result.raw_record_id and result.rate_record_id and result.source_url
    assert result.provider_rate_timestamp == PROVIDER_TIME
    assert not result.is_stale


@pytest.mark.parametrize(
    "target,rate,amount,expected,places",
    [
        ("JPY", "162.555", "10", "1626", 0),
        ("KWD", "0.333355", "10", "3.334", 3),
        ("USD", "1.00005", "100", "100.01", 2),
    ],
)
def test_currency_precision_and_half_up_rounding(db, target, rate, amount, expected, places):
    ingest_rate(db, target=target, rate=rate)
    result = calculate(db, conversion(target_currency=target, source_amount=amount))
    assert result.gross_target_amount == Decimal(expected)
    assert result.target_decimal_places == places
    assert "six-group.com" in result.precision_source


def test_unknown_precision_stays_unrounded(db):
    ingest_rate(db, target="ZZZ", rate="1.123456789123")
    result = calculate(db, conversion(target_currency="ZZZ"))
    assert result.target_decimal_places is None
    assert result.gross_target_amount == result.unrounded_gross_target_amount
    assert result.rounding_policy == "unrounded"
    assert any("precision is unknown" in warning for warning in result.warnings)


def test_stale_provider_timestamp_is_not_hidden_by_recent_fetch(db):
    ingest_rate(db, timestamp=NOW - timedelta(days=3))
    result = calculate(db, stale_after_seconds=60)
    assert result.is_stale
    assert result.provider_rate_timestamp == NOW - timedelta(days=3)
    assert result.captured_at > result.provider_rate_timestamp
    assert any("stale" in warning for warning in result.warnings)


def test_source_url_changes_replace_one_shared_current_rate(db):
    ingest_rate(db, rate="1.166")
    first = calculate(db)
    ingest_rate(db, rate="9.99", environment="sandbox", timestamp=NOW)
    assert calculate(db).reference_rate == Decimal("9.99")
    assert calculate(db).rate_record_id != first.rate_record_id
    assert "wise-sandbox" in calculate(db).source_url
    assert WiseService(db).list_rates().data.pagination.total == 1
    ingest_rate(db, rate="10.01", environment="production", timestamp=NOW + timedelta(seconds=1))
    assert calculate(db).reference_rate == Decimal("10.01")
    assert db.query(Quote).filter(Quote.superseded_at.is_(None)).count() == 1
    assert db.query(Quote).count() == 3


def test_rates_from_sandbox_url_are_readable_without_a_database_selector(db):
    ingest_rate(db, environment="sandbox")
    with patch("httpx.AsyncClient", side_effect=AssertionError("No network")):
        assert calculate(db).reference_rate == Decimal("1.166")
        result = WiseService(db).list_rates().data.items[0]
        assert "environment" not in result.model_dump()


def test_provider_selection_is_independent_and_calculator_is_provider_neutral(db):
    ingest_rate(db)
    original = db.query(Quote).one()
    # An isolated future-provider fixture uses an existing enum member without
    # adding or changing an integration in application code.
    provider = Provider(
        slug="busha",
        name="FX provider fixture",
        category=MarketCategory.FX,
        is_active=True,
        has_adapter=False,
    )
    db.add(provider)
    db.commit()
    alternate = Quote(
        provider=ProviderName.BUSHA,
        asset_id=original.asset_id,
        quote_type=QuoteType.MARKET,
        base_currency="EUR",
        quote_currency="USD",
        mid_rate=Decimal("2.5"),
        raw_record_id=original.raw_record_id,
        captured_at=NOW,
        metadata_json={**original.metadata_json, "provider_rate": "2.5"},
    )
    QuoteRepository(db).create_many([alternate])
    assert calculate(db, conversion(provider="busha")).reference_rate == Decimal("2.5")
    assert calculate(db).reference_rate == Decimal("1.166")
    with pytest.raises(AppError) as error:
        calculate(db, conversion(provider=ProviderName.TBAY))
    assert error.value.error_code == "fx_provider_unavailable"


def test_no_inverse_or_cross_rate_is_constructed(db):
    ingest_rate(db, source="USD", target="EUR", rate="0.9")
    ingest_rate(db, source="EUR", target="JPY", rate="160")
    for req in [conversion(), conversion(source_currency="USD", target_currency="JPY")]:
        with pytest.raises(AppError) as error:
            calculate(db, req)
        assert error.value.error_code == "fx_rate_unavailable"


def test_conversion_endpoint_never_calls_network_even_for_missing_or_stale_rates(db):
    from app.core.database import get_db
    from app.main import app

    ingest_rate(db, timestamp=NOW - timedelta(days=60))
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        with (
            patch("httpx.AsyncClient", side_effect=AssertionError("No network in conversion")),
            patch.object(
                WiseAdapter, "fetch_rates", side_effect=AssertionError("No rate fallback")
            ),
            patch.object(
                WiseAdapter, "fetch_quote", side_effect=AssertionError("No quote fallback")
            ),
            patch.object(
                WiseAdapter, "fetch_currencies", side_effect=AssertionError("No currency fallback")
            ),
        ):
            result = client.post("/fx/convert", json=conversion().model_dump(mode="json"))
            assert result.status_code == 200
            assert result.json()["data"]["is_stale"] is True
            assert result.json()["data"]["fee_amount"] is None
            for req in [
                conversion(target_currency="JPY"),
                conversion(source_currency="USD", target_currency="EUR"),
            ]:
                missing = client.post("/fx/convert", json=req.model_dump(mode="json"))
                assert missing.status_code == 503
                assert missing.json()["data"]["error"] == "fx_rate_unavailable"
            assert client.get("/fx/wise/currencies").json()["data"]["items"] == []
            assert client.get("/fx/wise/rates").status_code == 200
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize(
    "changes",
    [
        {"provider": "unknown"},
        {"provider": "string"},
        {"provider": "WISE"},
        {"source_amount": "0"},
        {"source_amount": "-1"},
        {"source_amount": "NaN"},
        {"source_amount": "Infinity"},
        {"source_currency": "US"},
        {"target_amount": "1"},
        {"environment": "sandbox"},
        {"pay_in": "CARD"},
        {"source_amount": "0.123456789"},
        {"target_currency": "EUR"},
    ],
)
def test_conversion_request_validation_is_clear_without_network(db, changes):
    from app.core.database import get_db
    from app.main import app

    app.dependency_overrides[get_db] = lambda: db
    try:
        with patch("httpx.AsyncClient", side_effect=AssertionError("No network")):
            result = TestClient(app).post(
                "/fx/convert",
                json={
                    **conversion().model_dump(mode="json"),
                    **changes,
                },
            )
            assert result.status_code == 422, result.text
    finally:
        app.dependency_overrides.clear()


def currency_adapter(*, environment="production", payload=None, token="test-only-token"):
    base = "https://api.wise-sandbox.com" if environment == "sandbox" else "https://api.wise.com"
    result = WiseAdapter(token=token, quote_token="", base_url=base)
    data = wise_fixture("documented_currencies.json") if payload is None else payload
    result.fetch_currencies = AsyncMock(
        return_value=WiseResponse(
            base + "/2026Q4/currencies",
            200,
            data,
            json.dumps(data),
        )
    )
    result.fetch_rates = AsyncMock(side_effect=AssertionError("Currency ingestion only"))
    return result


def test_currency_ingestion_persists_documented_fields_and_is_idempotent(db):
    provider = currency_adapter()
    service = WiseIngestionService(db, adapter=provider)
    first = asyncio.run(service.ingest_currencies())
    second = asyncio.run(service.ingest_currencies())
    assert first["currencies_observed"] == second["currencies_observed"] == 2
    assert db.query(FxCurrency).count() == 2
    jpy = db.query(FxCurrency).filter_by(code="JPY").one()
    assert jpy.name == "Japanese yen" and jpy.symbol == "¥"
    assert not jpy.supports_decimals and jpy.decimal_places == 0
    assert jpy.precision_source.endswith("/2026Q4/currencies")
    assert jpy.country_keywords == ["JPY", "JP", "Japan", "jpn"]
    assert db.get(RawRecord, jpy.raw_record_id).raw_text
    aud = db.query(FxCurrency).filter_by(code="AUD").one()
    assert aud.supports_decimals and aud.decimal_places == 2
    assert provider.fetch_currencies.await_count == 2
    provider.fetch_rates.assert_not_awaited()
    assert db.query(Quote).count() == 0


def test_currency_failures_and_missing_credentials_preserve_good_metadata(db):
    asyncio.run(WiseIngestionService(db, adapter=currency_adapter()).ingest_currencies())
    prior = db.query(FxCurrency).filter_by(code="JPY").one().raw_record_id
    payload = wise_fixture("documented_currencies.json")
    payload[1]["supportsDecimals"] = "not-a-boolean"
    result = asyncio.run(
        WiseIngestionService(db, adapter=currency_adapter(payload=payload)).ingest_currencies()
    )
    assert result["status"] == "partial"
    assert db.query(FxCurrency).filter_by(code="JPY").one().raw_record_id == prior
    no_token = currency_adapter(token="")
    result = asyncio.run(WiseIngestionService(db, adapter=no_token).ingest_currencies())
    assert result["status"] == "skipped"
    no_token.fetch_currencies.assert_not_awaited()
    assert db.query(FxCurrency).count() == 2
    invalid = currency_adapter(payload={"unexpected": "schema"})
    with pytest.raises(AppError):
        asyncio.run(WiseIngestionService(db, adapter=invalid).ingest_currencies())
    assert db.query(FetchRun).order_by(FetchRun.id.desc()).first().status == FetchRunStatus.FAILED


def test_currency_read_endpoint_is_database_only_after_source_url_change(db):
    from app.core.database import get_db
    from app.main import app

    asyncio.run(WiseIngestionService(db, adapter=currency_adapter()).ingest_currencies())
    asyncio.run(
        WiseIngestionService(
            db, adapter=currency_adapter(environment="sandbox")
        ).ingest_currencies()
    )
    assert db.query(FxCurrency).count() == 2
    app.dependency_overrides[get_db] = lambda: db
    try:
        with patch("httpx.AsyncClient", side_effect=AssertionError("No network")):
            result = TestClient(app).get("/fx/wise/currencies")
            assert result.status_code == 200
            data = result.json()["data"]
            assert data["pagination"]["total"] == 2
            assert all("environment" not in c for c in data["items"])
            assert all(c["transfer_route_verified"] is False for c in data["items"])
    finally:
        app.dependency_overrides.clear()


def test_quote_samples_including_zero_fees_are_not_local_fee_rules(db):
    ingest_rate(db)
    sample = wise_fixture()
    sample["paymentOptions"][0]["fee"]["total"] = 0
    sample["paymentOptions"][0]["price"]["total"]["value"]["amount"] = 0
    observed = asyncio.run(
        WiseIngestionService(db, adapter=quote_adapter(sample)).request_quote(quote_request())
    )
    assert observed.payment_options[0].fee_total == 0
    assert db.get(FetchRun, observed.fetch_run_id).metadata_json["usable_as_fee_rule"] is False
    for amount in ("100", "1000"):
        result = calculate(db, conversion(source_amount=amount))
        assert result.fee_status == "unavailable" and result.fee_amount is None
        assert result.estimated_net_target_amount is None


def test_currency_job_reuses_admin_manual_and_scheduler_conventions(db):
    from app.core.database import get_db
    from app.dependencies.auth import require_admin
    from app.main import app
    from app.repositories.wise import WiseRepository
    from app.services.ingestion.manual import run_provider_ingestion_job
    from app.services.ingestion_scheduler import IngestionSchedulerService

    WiseRepository(db).register_provider()
    with patch.object(WiseIngestionService, "ingest_currencies", new_callable=AsyncMock) as run:
        asyncio.run(
            IngestionSchedulerService()._dispatch_job(
                db=db,
                provider_slug="wise",
                job_type=IngestionJobType.CURRENCIES,
            )
        )
        with (
            patch("app.services.ingestion.manual.SessionLocal", return_value=db),
            patch("app.services.ingestion.manual.ProviderMetricService"),
        ):
            asyncio.run(
                run_provider_ingestion_job(
                    provider_slug="wise", job_type=IngestionJobType.CURRENCIES
                )
            )
        assert run.await_count == 2
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[require_admin] = lambda: None
    try:
        client = TestClient(app)
        with patch("app.services.provider.launch_provider_ingestion_job") as launch:
            assert client.post("/providers/wise/ingestion-runs/currencies").status_code == 202
            assert launch.call_args.kwargs["job_type"] == IngestionJobType.CURRENCIES
        response = client.put(
            "/providers/wise/ingestion-schedules/currencies",
            json={
                "interval_minutes": 1440,
                "is_enabled": False,
            },
        )
        assert response.status_code == 200 and response.json()["data"]["is_enabled"] is False
    finally:
        app.dependency_overrides.clear()


def test_conversion_documentation_uses_existing_provider_enum_and_valid_example():
    from app.main import app

    schema = app.openapi()
    body = schema["components"]["schemas"]["FxConversionRequest"]
    assert body["properties"]["provider"]["$ref"].endswith("/ProviderName")
    values = schema["components"]["schemas"]["ProviderName"]["enum"]
    assert set(values) == {provider.value for provider in ProviderName}
    example = body["examples"][0]
    parsed = FxConversionRequest.model_validate(example)
    assert parsed.provider is ProviderName.WISE
    assert parsed.source_currency == "USD" and parsed.target_currency == "NGN"
    assert parsed.source_amount == Decimal("100.00")
    assert parsed.model_dump(mode="json")["provider"] == "wise"


def test_enum_provider_still_requires_fx_support(db):
    db.add(
        Provider(
            slug="quidax",
            name="Crypto-only fixture",
            category=MarketCategory.CRYPTO,
            is_active=True,
            has_adapter=True,
        )
    )
    db.commit()
    with pytest.raises(AppError) as error:
        calculate(db, conversion(provider=ProviderName.QUIDAX))
    assert error.value.error_code == "fx_provider_unavailable"
