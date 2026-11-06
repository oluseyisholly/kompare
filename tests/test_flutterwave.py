import asyncio
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient
from test_fx import db as existing_database

from app.adapters.fx.flutterwave import (
    DEFAULT_SCENARIOS,
    RATES_URL,
    FlutterwaveAdapter,
    FlutterwaveResponse,
    FlutterwaveScenario,
)
from app.core.exceptions import AppError
from app.models.enums import FetchRunStatus, IngestionJobType, ProviderName
from app.models.fetch_run import FetchRun
from app.models.fx import FxCurrency, FxQuoteObservation
from app.models.quote import Quote
from app.models.raw_record import RawRecord
from app.repositories.fx import FxRepository
from app.schemas.fx import FxConversionRequest
from app.services.fx import FxService, utc
from app.services.ingestion.flutterwave import FlutterwaveIngestionService

db = existing_database
FIXTURES = Path(__file__).parent / "fixtures" / "flutterwave"
TEST_KEY = "FLWSECK_TEST-test-only-fixture-key-X"
LIVE_KEY = "FLWSECK-live-mode-fixture-not-a-real-key-X"
SCENARIOS = [
    {"source_currency": "NGN", "destination_currency": "USD", "destination_amount": "1000"},
    {"source_currency": "USD", "destination_currency": "NGN", "destination_amount": "100000"},
]


def fixture(name="ngn_usd.json"):
    return json.loads((FIXTURES / name).read_text(), parse_float=Decimal)


def fake_adapter(*, scenarios=None, mode="test", failures=None):
    adapter = FlutterwaveAdapter(
        secret_key=TEST_KEY if mode == "test" else LIVE_KEY,
        mode=mode,
        scenarios=SCENARIOS if scenarios is None else scenarios,
    )

    async def fetch(scenario, *, client):
        if failures and scenario.source_currency in failures:
            payload, status = fixture("error.json"), 422
        else:
            payload = fixture(
                "ngn_usd.json" if scenario.source_currency == "NGN" else "usd_ngn.json"
            )
            status = 200
            # Other currencies are synthetic variants for default-list tests,
            # not documentation or live evidence of route availability/prices.
            payload["data"]["source"]["currency"] = scenario.source_currency
            payload["data"]["destination"]["currency"] = scenario.destination_currency
            original_amount = Decimal(str(payload["data"]["destination"]["amount"]))
            if original_amount != scenario.destination_amount:
                # Synthetic alternate sample; production never scales a provider response.
                payload["data"]["destination"]["amount"] = scenario.destination_amount
                payload["data"]["source"]["amount"] = scenario.destination_amount / Decimal(
                    str(payload["data"]["rate"])
                )
        return FlutterwaveResponse(status, payload, json.dumps(payload, default=str))

    adapter.fetch_rate = AsyncMock(side_effect=fetch)
    return adapter


def run(db, **kwargs):
    adapter = fake_adapter(**kwargs)
    result = asyncio.run(FlutterwaveIngestionService(db, adapter=adapter).ingest_market_data())
    return result, adapter


def request(**kwargs):
    return FxConversionRequest(
        **{
            "provider": "flutterwave",
            "source_currency": "NGN",
            "target_currency": "USD",
            "source_amount": "100",
            **kwargs,
        }
    )


def test_request_uses_destination_amount_and_v3_secret_key_authentication():
    calls = []
    scenario = FlutterwaveScenario.model_validate(SCENARIOS[0])

    def handler(req):
        calls.append(req)
        return httpx.Response(200, text=(FIXTURES / "ngn_usd.json").read_text())

    async def fetch():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await FlutterwaveAdapter(
                secret_key=TEST_KEY, mode="test", base_url="https://api.flutterwave.com/"
            ).fetch_rate(scenario, client=client)

    response = asyncio.run(fetch())
    assert len(calls) == 1
    sent = calls[0]
    assert sent.method == "GET" and str(sent.url).split("?")[0] == RATES_URL
    assert dict(sent.url.params) == {
        "source_currency": "NGN",
        "destination_currency": "USD",
        "amount": "1000",
    }
    assert sent.headers["authorization"] == f"Bearer {TEST_KEY}"
    assert TEST_KEY not in response.source_url + response.raw_text


@pytest.mark.parametrize(
    "name,scenario_index,rate,source_amount,destination_amount",
    [
        ("ngn_usd.json", 0, "0.000694329", "1440239.425", "1000"),
        ("usd_ngn.json", 1, "1372", "72.886", "100000"),
    ],
)
def test_documented_rate_direction_and_amount_meanings(
    name, scenario_index, rate, source_amount, destination_amount
):
    payload = fixture(name)
    record = FlutterwaveAdapter.parse_rate(
        FlutterwaveResponse(200, payload, json.dumps(payload, default=str)),
        scenario=FlutterwaveScenario.model_validate(SCENARIOS[scenario_index]),
        captured_at=datetime.now(UTC),
    )
    assert record.rate == Decimal(rate) and record.rate_direction == "target_per_source"
    assert record.returned_source_amount == Decimal(source_amount)
    assert (
        record.returned_destination_amount
        == record.requested_destination_amount
        == Decimal(destination_amount)
    )
    assert record.provider_time is None
    assert record.classification == "transfer_rate_observation"


def test_multiple_pairs_and_amounts_are_separate_samples_with_raw_evidence(db):
    scenarios = SCENARIOS + [dict(SCENARIOS[0], destination_amount="500")]
    result, adapter = run(db, scenarios=scenarios)
    assert result["status"] == "success"
    assert result["rates_observed"] == result["observations_created"] == 3
    rows = db.query(FxQuoteObservation).all()
    assert len(rows) == 3 and len({r.fetch_run_id for r in rows}) == 1
    assert {r.requested_amount for r in rows} == {
        Decimal("1000"),
        Decimal("100000"),
        Decimal("500"),
    }
    assert all(r.classification == "transfer_rate_observation" for r in rows)
    assert db.query(Quote).count() == db.query(FxCurrency).count() == 0
    for row in rows:
        raw = db.get(RawRecord, row.raw_record_id)
        assert raw.provider == ProviderName.FLUTTERWAVE and raw.raw_text
        assert raw.payload["request"]["destination_amount"]
    assert adapter.fetch_rate.await_count == 3
    assert len({id(call.kwargs["client"]) for call in adapter.fetch_rate.await_args_list}) == 1


@pytest.mark.parametrize(
    "source,target,amount,rate,gross,sampled",
    [
        ("NGN", "USD", "100", "0.000694329", "0.07", "1000"),
        ("USD", "NGN", "10", "1372", "13720.00", "100000"),
    ],
)
def test_local_conversion_multiplies_and_discloses_sample_and_unknown_fees(
    db, source, target, amount, rate, gross, sampled
):
    run(db)
    row = db.query(FxQuoteObservation).filter_by(source_currency=source).one()
    result = (
        FxService(db, now=lambda: utc(row.captured_at) + timedelta(seconds=10))
        .convert(
            request(source_currency=source, target_currency=target, source_amount=amount),
        )
        .data
    )
    assert result.reference_rate is None
    assert result.applied_rate == Decimal(rate)
    assert result.unrounded_gross_target_amount == Decimal(amount) * Decimal(rate)
    assert result.gross_target_amount == Decimal(gross)
    assert result.sampled_destination_amount == Decimal(sampled)
    assert result.rate_classification == "transfer_rate_observation"
    assert result.calculation_basis == "stored_sampled_transfer_rate_estimate"
    assert (
        result.provider_rate_timestamp is None and result.freshness_basis == "collection_timestamp"
    )
    assert not result.is_stale and not result.executable and not result.transfer_route_verified
    assert result.fee_status == "unavailable" and result.fee_amount is None
    assert result.fee_currency is result.estimated_net_target_amount is None
    assert result.rate_record_id == row.id


def test_sample_selection_is_explicit_deterministic_and_does_not_average(db):
    run(db, scenarios=[SCENARIOS[0], dict(SCENARIOS[0], destination_amount="500")])
    rows = db.query(FxQuoteObservation).all()
    now = datetime(2026, 11, 2, 12, tzinfo=UTC)
    for row in rows:
        row.captured_at = now
        row.response_data = {
            **row.response_data,
            "rate": "0.001" if row.requested_amount == 500 else "0.002",
        }
    db.commit()
    service = FxService(db, now=lambda: now)
    result = service.convert(request()).data
    assert result.sampled_destination_amount == 500 and result.applied_rate == Decimal("0.001")
    assert "smallest_destination_amount" in result.sample_selection_policy
    larger = next(row for row in rows if row.requested_amount == 1000)
    larger.captured_at = now + timedelta(seconds=1)
    db.commit()
    assert service.convert(request()).data.applied_rate == Decimal("0.002")


def test_partial_ingestion_preserves_successful_observations_and_failure_evidence(db):
    result, _ = run(db, failures={"NGN"})
    assert result["status"] == "partial" and result["rates_observed"] == 1
    assert result["extraction_failures"][0]["source_currency"] == "NGN"
    assert result["extraction_failures"][0]["error_code"] == "flutterwave_scenario_unavailable"
    assert db.query(RawRecord).count() == 2 and db.query(FxQuoteObservation).count() == 1
    assert db.get(FetchRun, result["fetch_run_id"]).status == FetchRunStatus.FAILED


@pytest.mark.parametrize(
    "key,mode,scenarios,configuration",
    [
        ("", "test", SCENARIOS, "missing_credentials"),
        (TEST_KEY, "live", SCENARIOS, "credential_environment_mismatch"),
        (LIVE_KEY, "test", SCENARIOS, "credential_environment_mismatch"),
        (TEST_KEY, "other", SCENARIOS, "invalid_environment"),
        (TEST_KEY, "test", "not-json", "invalid_scenarios"),
    ],
)
def test_missing_or_invalid_configuration_skips_without_fixtures_or_network(
    db, key, mode, scenarios, configuration
):
    adapter = FlutterwaveAdapter(secret_key=key, mode=mode, scenarios=scenarios)
    adapter.fetch_rate = AsyncMock(
        side_effect=AssertionError("No network with invalid configuration")
    )
    result = asyncio.run(FlutterwaveIngestionService(db, adapter=adapter).ingest_market_data())
    assert result["status"] == "skipped" and result["configuration_status"] == configuration
    adapter.fetch_rate.assert_not_awaited()
    assert db.query(RawRecord).count() == db.query(FxQuoteObservation).count() == 0


@pytest.mark.parametrize("setting", [None, "", "  ", "[]", []])
def test_default_ingestion_needs_no_scenario_configuration(db, setting):
    with patch("app.core.config.FLUTTERWAVE_FX_SCENARIOS", setting):
        adapter = FlutterwaveAdapter(secret_key=TEST_KEY, mode="test")
        adapter.fetch_rate = fake_adapter(scenarios=[]).fetch_rate
        result = asyncio.run(FlutterwaveIngestionService(db, adapter=adapter).ingest_market_data())
    assert result["status"] == "success" and result["rates_observed"] == 6
    assert adapter.fetch_rate.await_count == db.query(FxQuoteObservation).count() == 6
    assert {
        (row.source_currency, row.target_currency) for row in db.query(FxQuoteObservation).all()
    } == {(item["source_currency"], item["destination_currency"]) for item in DEFAULT_SCENARIOS}
    assert FxService(db).convert(request()).data.rate_record_id


def test_refresh_updates_local_conversion_and_failed_refresh_keeps_last_good_rate(db):
    run(db, scenarios=[])
    adapter = fake_adapter(scenarios=SCENARIOS[:1])
    payload = fixture()
    payload["data"]["rate"] = "0.00123456789123456789"
    adapter.fetch_rate = AsyncMock(
        return_value=FlutterwaveResponse(200, payload, json.dumps(payload, default=str))
    )
    result = asyncio.run(FlutterwaveIngestionService(db, adapter=adapter).ingest_market_data())
    assert result["status"] == "success"
    service = FxService(db)
    latest = service.convert(request()).data
    assert latest.applied_rate == Decimal("0.00123456789123456789")
    assert latest.unrounded_gross_target_amount == Decimal("0.12345678912345678900")
    failed, _ = run(db, scenarios=SCENARIOS[:1], failures={"NGN"})
    assert failed["status"] == "failed"
    assert service.convert(request()).data.rate_record_id == latest.rate_record_id
    assert db.query(FxQuoteObservation).count() == 7


@pytest.mark.parametrize(
    "base_url",
    ["http://api.flutterwave.com", "https://other.invalid", "https://api.flutterwave.com/v4"],
)
def test_invalid_base_url_skips_without_sending_credentials(db, base_url):
    adapter = FlutterwaveAdapter(
        secret_key=TEST_KEY, mode="test", scenarios=SCENARIOS, base_url=base_url
    )
    adapter.fetch_rate = AsyncMock(side_effect=AssertionError("No credentials sent"))
    result = asyncio.run(FlutterwaveIngestionService(db, adapter=adapter).ingest_market_data())
    assert result["status"] == "skipped" and result["configuration_status"] == "invalid_base_url"
    adapter.fetch_rate.assert_not_awaited()


@pytest.mark.parametrize(
    "changes",
    [
        {"destination_amount": "0"},
        {"destination_amount": "-1"},
        {"destination_amount": "NaN"},
        {"destination_amount": "1.5"},
        {"destination_amount": "2147483648"},
        {"source_currency": "US"},
        {"destination_currency": "NGN"},
        {"amount": "1000"},
    ],
)
def test_invalid_configured_scenario_does_not_discard_valid_scenarios(db, changes):
    result, adapter = run(db, scenarios=[SCENARIOS[1], {**SCENARIOS[0], **changes}])
    assert result["status"] == "partial" and result["rates_observed"] == 1
    assert adapter.fetch_rate.await_count == 1


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_rate",
        "negative_rate",
        "wrong_pair",
        "wrong_amount",
        "missing_source",
        "business_error",
    ],
)
def test_invalid_response_never_becomes_live_data_and_raw_is_retained(db, mutation):
    adapter = fake_adapter(scenarios=[SCENARIOS[0]])
    payload = fixture()
    if mutation == "missing_rate":
        payload["data"].pop("rate")
    elif mutation == "negative_rate":
        payload["data"]["rate"] = -1
    elif mutation == "wrong_pair":
        payload["data"]["destination"]["currency"] = "EUR"
    elif mutation == "wrong_amount":
        payload["data"]["destination"]["amount"] = 999
    elif mutation == "missing_source":
        payload["data"].pop("source")
    else:
        payload = fixture("error.json")
    adapter.fetch_rate = AsyncMock(
        return_value=FlutterwaveResponse(200, payload, json.dumps(payload, default=str))
    )
    result = asyncio.run(FlutterwaveIngestionService(db, adapter=adapter).ingest_market_data())
    assert result["status"] == "failed" and result["rates_observed"] == 0
    assert db.query(FxQuoteObservation).count() == 0 and db.query(RawRecord).count() == 1


def test_unchanged_values_in_separate_runs_append_but_same_run_retry_does_not_duplicate(db):
    first, _ = run(db, scenarios=[SCENARIOS[0]])
    second, _ = run(db, scenarios=[SCENARIOS[0]])
    assert (
        first["fetch_run_id"] != second["fetch_run_id"]
        and db.query(FxQuoteObservation).count() == 2
    )
    row = db.query(FxQuoteObservation).first()
    repository = FxRepository(db)
    record = repository.transfer_rate_read(row)
    same, created = repository.save_transfer_rate(
        record,
        provider_id=row.provider_id,
        fetch_run_id=row.fetch_run_id,
        raw_record_id=row.raw_record_id,
    )
    assert same.id == row.id and not created and db.query(FxQuoteObservation).count() == 2


def test_latest_flutterwave_sample_is_used_without_environment_partition(db):
    run(db, mode="test", scenarios=[SCENARIOS[0]])
    first = FxService(db).convert(request()).data
    run(db, mode="live", scenarios=[SCENARIOS[0]])
    latest = FxService(db).convert(request()).data
    assert first.rate_record_id != latest.rate_record_id
    assert "environment" not in latest.model_dump()
    assert db.query(FxQuoteObservation).count() == 2
    assert FxService(db).list_rates("flutterwave").data.pagination.total == 1


def test_shared_apis_are_local_on_missing_and_stale_samples_and_do_not_fabricate_currencies(db):
    from app.core.database import get_db
    from app.main import app

    run(db, mode="live", scenarios=[SCENARIOS[0]])
    row = db.query(FxQuoteObservation).one()
    row.captured_at = datetime.now(UTC) - timedelta(days=2)
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    try:
        with (
            patch("httpx.AsyncClient", side_effect=AssertionError("No network on reads")),
            patch.object(
                FlutterwaveAdapter, "fetch_rate", side_effect=AssertionError("No fallback")
            ),
        ):
            client = TestClient(app)
            result = client.post("/fx/convert", json=request().model_dump(mode="json"))
            assert result.status_code == 200 and result.json()["data"]["is_stale"] is True
            assert result.json()["data"]["provider_rate_timestamp"] is None
            missing = client.post(
                "/fx/convert",
                json=request(source_currency="USD", target_currency="NGN").model_dump(mode="json"),
            )
            assert missing.status_code == 503
            rates = client.get("/fx/flutterwave/rates").json()["data"]["items"]
            assert rates[0]["classification"] == "transfer_rate_observation"
            assert rates[0]["requested_destination_amount"] == "1000"
            currencies = client.get("/fx/flutterwave/currencies")
            assert currencies.json()["data"]["items"] == []
            assert "not implemented" in currencies.json()["message"]
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize(
    "status,expected",
    [
        (400, "flutterwave_request_rejected"),
        (401, "flutterwave_access_unavailable"),
        (422, "flutterwave_scenario_unavailable"),
        (429, "flutterwave_rate_limited"),
        (500, "flutterwave_provider_failure"),
    ],
)
def test_rate_limits_errors_and_key_redaction(db, status, expected):
    calls = []
    adapter = FlutterwaveAdapter(secret_key=TEST_KEY, mode="test", scenarios=SCENARIOS[:1])

    def handler(req):
        calls.append(req)
        return httpx.Response(
            status,
            headers={"Retry-After": "30"},
            json={"status": "error", "message": TEST_KEY, "data": None},
        )

    async def fetch():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await adapter.fetch_rate(
                FlutterwaveScenario.model_validate(SCENARIOS[0]), client=client
            )

    response = asyncio.run(fetch())
    assert len(calls) == 1 and TEST_KEY not in response.raw_text + str(response.payload)
    adapter.fetch_rate = AsyncMock(return_value=response)
    result = asyncio.run(FlutterwaveIngestionService(db, adapter=adapter).ingest_market_data())
    assert result["extraction_failures"][0]["error_code"] == expected
    assert result["extraction_failures"][0]["provider_message"] == "[REDACTED]"
    raw = db.query(RawRecord).one()
    assert TEST_KEY not in raw.raw_text + str(raw.payload) + str(result)


def test_system_token_failure_is_reported_without_claiming_the_pair_is_unsupported(db):
    # Message observed in run 109. This synthetic body reproduces the provider error.
    message = "An error occured while generating the system token. Please contact support."
    adapter = fake_adapter(scenarios=SCENARIOS[:1])
    adapter.fetch_rate = AsyncMock(
        return_value=FlutterwaveResponse(
            400,
            {"status": "error", "message": message, "data": None},
            json.dumps({"status": "error", "message": message, "data": None}),
        )
    )
    result = asyncio.run(FlutterwaveIngestionService(db, adapter=adapter).ingest_market_data())
    assert result["status"] == "failed" and result["rates_observed"] == 0
    error = result["extraction_failures"][0]
    assert error["error_code"] == "flutterwave_request_rejected"
    assert error["provider_status"] == 400 and error["provider_message"] == message
    assert db.query(FxQuoteObservation).count() == 0
    assert db.query(RawRecord).one().payload["response"]["message"] == message


def test_transport_retries_are_bounded():
    calls = []

    def handler(req):
        calls.append(req)
        raise httpx.ConnectError("failed", request=req)

    async def fetch():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await FlutterwaveAdapter(secret_key=TEST_KEY, mode="test").fetch_rate(
                FlutterwaveScenario.model_validate(SCENARIOS[0]), client=client
            )

    with patch("app.adapters.fx.flutterwave.asyncio.sleep", new_callable=AsyncMock):
        with pytest.raises(AppError):
            asyncio.run(fetch())
    assert len(calls) == 2


def test_shared_job_dispatch_supports_market_data_only(db):
    from app.core.database import get_db
    from app.dependencies.auth import require_admin
    from app.main import app
    from app.services.ingestion.fx import run_fx_ingestion, supported_fx_jobs
    from app.services.ingestion_scheduler import IngestionSchedulerService

    FlutterwaveIngestionService(db, adapter=fake_adapter()).register_provider()
    assert supported_fx_jobs("flutterwave") == {IngestionJobType.MARKET_DATA}
    with patch.object(
        FlutterwaveIngestionService, "ingest_market_data", new_callable=AsyncMock
    ) as called:
        asyncio.run(
            run_fx_ingestion(db, provider="flutterwave", job_type=IngestionJobType.MARKET_DATA)
        )
        asyncio.run(
            IngestionSchedulerService()._dispatch_job(
                db=db, provider_slug="flutterwave", job_type=IngestionJobType.MARKET_DATA
            )
        )
        assert called.await_count == 2
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[require_admin] = lambda: None
    try:
        client = TestClient(app)
        with patch("app.services.provider.launch_provider_ingestion_job") as launch:
            for job in ("currencies", "fees", "kyc", "fund_details"):
                result = client.post(f"/providers/flutterwave/ingestion-runs/{job}")
                assert result.status_code == 400
                assert result.json()["data"]["supported_jobs"] == ["market_data"]
            launch.assert_not_called()
            assert (
                client.post("/providers/flutterwave/ingestion-runs/market_data").status_code == 202
            )
        assert (
            client.put(
                "/providers/flutterwave/ingestion-schedules/currencies",
                json={"interval_minutes": 60, "is_enabled": False},
            ).status_code
            == 400
        )
        assert (
            client.put(
                "/providers/flutterwave/ingestion-schedules/market_data",
                json={"interval_minutes": 60, "is_enabled": False},
            ).status_code
            == 200
        )
    finally:
        app.dependency_overrides.clear()
