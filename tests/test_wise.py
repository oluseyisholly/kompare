import asyncio
import copy
import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient
from test_stanbic_ingestion import db as existing_database

from app.adapters.fx.wise import WiseAdapter, WiseResponse
from app.core.exceptions import AppError
from app.models.asset import Asset
from app.models.enums import FetchRunStatus, IngestionJobType, MarketCategory, ProviderName
from app.models.fetch_run import FetchRun
from app.models.quote import Quote, QuoteObservation
from app.models.raw_record import RawRecord
from app.models.wise import WiseIllustrativeQuote
from app.repositories.wise import WiseRepository
from app.schemas.wise import WiseQuoteRequest
from app.services.ingestion.wise import WiseIngestionService
from app.services.wise import WiseService

db = existing_database
FIXTURES = Path(__file__).parent / "fixtures" / "wise"
CAPTURED = datetime(2019, 4, 5, 13, 19, tzinfo=UTC)


def fixture(name="documented_quote.json"):
    return json.loads((FIXTURES / name).read_text(), parse_float=Decimal)


def response(payload, *, status=200, resource="quotes"):
    text = json.dumps(payload, default=str)
    return WiseResponse(f"https://api.wise.com/2026Q4/{resource}", status, payload, text)


def request(**overrides):
    fields = {"source_currency": "GBP", "target_currency": "USD", "source_amount": "100"}
    fields.update(overrides)
    return WiseQuoteRequest(**fields)


def adapter(payload=None, *, status=200):
    result = WiseAdapter(token="test-only-wise-token", quote_token="")
    result.fetch_rates = AsyncMock(
        return_value=response(
            fixture("documented_rates.json") if payload is None else payload,
            status=status,
            resource="rates",
        )
    )
    result.fetch_quote = AsyncMock(
        return_value=response(
            fixture() if payload is None else payload,
            status=status,
        )
    )
    return result


def parse(payload=None, req=None):
    return WiseAdapter(token="", quote_token="").parse_quote(
        fixture() if payload is None else payload,
        request=req or request(),
        captured_at=CAPTURED,
        source_url="https://api.wise.com/2026Q4/quotes",
    )


def test_reference_rates_parse_and_persist_existing_quote_history(db):
    service = WiseIngestionService(db, adapter=adapter())
    result = asyncio.run(service.ingest_market_data())
    assert result["status"] == "success"
    assert result["rates_observed"] == result["versions_created"] == 1
    row = db.query(Quote).one()
    assert row.provider == ProviderName.WISE
    assert row.mid_rate == Decimal("1.166")
    assert row.base_currency == "EUR" and row.quote_currency == "USD"
    assert row.metadata_json["classification"] == "reference_rate"
    assert row.metadata_json["transfer_route_verified"] is False
    assert row.metadata_json["provider_time"].startswith("2018-08-31")
    assert row.captured_at.year >= 2026
    raw = db.get(RawRecord, row.raw_record_id)
    assert raw.raw_text and raw.source_url.endswith("/2026Q4/rates")
    asset = db.get(Asset, row.asset_id)
    assert asset.category == MarketCategory.FX
    assert WiseRepository(db).register_provider().slug == "wise"


def test_reference_all_pairs_and_unchanged_timestamp_not_refreshed(db):
    rates = fixture("documented_rates.json") + [
        {"source": "GBP", "target": "JPY", "rate": "196.123456789", "time": "2018-08-31T10:43:31Z"}
    ]
    service = WiseIngestionService(db, adapter=adapter(rates))
    first = asyncio.run(service.ingest_market_data())
    second = asyncio.run(service.ingest_market_data())
    assert first["rates_observed"] == 2 and second["versions_created"] == 0
    assert db.query(Quote).count() == 2
    assert db.query(QuoteObservation).count() == 4
    data = WiseService(db).list_rates(source="GBP", target=None).data
    assert data.pagination.total == 1
    assert data.items[0].rate == Decimal("196.123456789")
    assert data.items[0].provider_time.year == 2018
    assert data.items[0].last_seen_at.year >= 2026
    assert first["fetch_run_id"] != second["fetch_run_id"]


def test_malformed_duplicate_and_regressing_rates_preserve_previous_values(db):
    asyncio.run(WiseIngestionService(db, adapter=adapter()).ingest_market_data())
    rates = [
        {"source": "EUR", "target": "USD", "rate": "2", "time": "2017-08-31T10:43:31Z"},
        {"source": "GBP", "target": "JPY", "rate": "NaN", "time": "2018-08-31T10:43:31Z"},
        {"source": "GBP", "target": "USD", "rate": "1", "time": "2018-08-31T10:43:31Z"},
    ]
    result = asyncio.run(WiseIngestionService(db, adapter=adapter(rates)).ingest_market_data())
    assert result["status"] == "partial"
    assert len(result["extraction_failures"]) == 2
    assert db.query(Quote).filter_by(base_currency="EUR").one().mid_rate == Decimal("1.166")
    valid, errors = WiseAdapter.parse_rates([rates[2], rates[2]])
    assert not valid and errors


def test_missing_token_skips_without_network_or_fixture_data(db):
    unconfigured = adapter()
    unconfigured.token = ""
    result = asyncio.run(WiseIngestionService(db, adapter=unconfigured).ingest_market_data())
    assert result["status"] == "skipped" and result["configuration_status"] == "missing_token"
    unconfigured.fetch_rates.assert_not_awaited()
    assert db.query(Quote).count() == db.query(RawRecord).count() == 0
    run = db.query(FetchRun).one()
    assert run.status == FetchRunStatus.FAILED
    assert run.metadata_json["status"] == "skipped"


def test_documented_quote_totals_and_discounts_not_double_counted():
    quoted = parse()
    option = quoted.payment_options[0]
    assert option.source_amount == option.total_source_amount == Decimal("100")
    assert option.target_amount == option.net_target_amount == Decimal("129.24")
    assert option.fee_total == Decimal("0.77")
    assert option.effective_rate == Decimal("1.2924")
    assert option.effective_rate != (Decimal("129.24") - Decimal("0.77")) / Decimal("100")
    assert option.cost_information == "complete"
    assert option.fee_treatment == "included_in_source_amount"
    assert option.fees[-1].amount == Decimal("-2.27")
    assert option.external_charges_included is False
    assert quoted.executable is quoted.rate_locked is False
    assert quoted.provider_quote_id is None


def test_separate_payment_options_and_disabled_methods():
    payload = fixture()
    card = copy.deepcopy(payload["paymentOptions"][0])
    card.update(payIn="CARD", targetAmount="128")
    card["fee"]["total"] = "2"
    card["price"]["total"]["value"]["amount"] = "2"
    disabled = copy.deepcopy(card)
    disabled.update(payIn="BALANCE", disabled=True, disabledReason={"code": "disabled"})
    payload["paymentOptions"].extend([card, disabled])
    options = parse(payload).payment_options
    assert [o.pay_in for o in options] == ["BANK_TRANSFER", "CARD", "BALANCE"]
    assert options[0].effective_rate == Decimal("1.2924")
    assert options[1].effective_rate == Decimal("1.28")
    assert options[2].effective_rate is None and options[2].disabled_reason == {"code": "disabled"}


@pytest.mark.parametrize(
    "change",
    [
        "missing_fee",
        "no_currency",
        "no_amount",
        "different_currency",
        "conflicting_fee",
        "deferred",
    ],
)
def test_incomplete_cost_information_is_never_invented(change):
    payload = fixture()
    option = payload["paymentOptions"][0]
    if change == "missing_fee":
        option.pop("fee")
        option.pop("price")
    elif change == "no_currency":
        option["price"]["total"]["value"].pop("currency")
    elif change == "no_amount":
        option.pop("sourceAmount")
    elif change == "different_currency":
        option["price"]["total"]["value"]["currency"] = "EUR"
    elif change == "conflicting_fee":
        option["fee"]["total"] = "9"
    else:
        option["price"]["deferredFee"] = {"amount": "1"}
    parsed = parse(payload).payment_options[0]
    assert parsed.effective_rate is None
    assert parsed.cost_information == "partial"
    if change in {"missing_fee", "conflicting_fee"}:
        assert parsed.fee_total is None
    if change == "no_amount":
        assert parsed.source_amount is parsed.total_source_amount is None


def test_explicit_zero_fee_is_distinct_from_missing():
    payload = fixture()
    option = payload["paymentOptions"][0]
    option["fee"]["total"] = 0
    option["price"]["total"]["value"]["amount"] = 0
    parsed = parse(payload).payment_options[0]
    assert parsed.fee_total == 0
    assert parsed.effective_rate == Decimal("1.2924")


def test_target_amount_basis_and_exact_decimal_request_body():
    payload = fixture()
    payload["providedAmountType"] = "TARGET"
    quoted = parse(payload, request(source_amount=None, target_amount="129.24"))
    assert quoted.amount_basis == "target"
    assert quoted.payment_options[0].total_source_amount == Decimal("100")
    sent = []

    def handle(req):
        sent.append(req)
        return httpx.Response(200, json={"ok": True})

    async def call():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            await WiseAdapter(token="personal-test-only", quote_token="").fetch_quote(
                request(source_amount=None, target_amount="12345.12345678"), client=client
            )

    asyncio.run(call())
    body = json.loads(sent[0].content, parse_float=Decimal)
    assert body == {
        "sourceCurrency": "GBP",
        "targetCurrency": "USD",
        "targetAmount": Decimal("12345.12345678"),
    }
    assert "authorization" not in sent[0].headers
    assert "pricingConfiguration" not in body
    assert str(sent[0].url) == "https://api.wise.com/2026Q4/quotes"


def test_real_anonymous_response_snapshot_preserves_all_nineteen_options():
    parsed = parse(fixture("live_illustrative_gbp_usd_2026-11-02.json"))
    assert len(parsed.payment_options) == 19
    assert parsed.provider_created_at == datetime(2026, 11, 2, 10, 56, 45, tzinfo=UTC)
    assert parsed.provider_rate_time == datetime(2026, 11, 2, 10, 56, 1, tzinfo=UTC)
    assert parsed.target_amount is None  # no top-level target; never select the first option
    assert parsed.payment_options[0].effective_rate == Decimal("1.3221")
    assert parsed.payment_options[-1].pay_in == "BALANCE"
    assert parsed.payment_options[-1].disabled is True


def test_scenarios_append_separately_and_keep_raw_originals(db):
    provider = adapter()
    service = WiseIngestionService(db, adapter=provider)
    first = asyncio.run(service.request_quote(request()))
    second = asyncio.run(service.request_quote(request()))
    changed = fixture()
    changed["sourceAmount"] = 200
    changed["paymentOptions"][0]["sourceAmount"] = 200
    provider.fetch_quote.return_value = response(changed)
    third = asyncio.run(service.request_quote(request(source_amount="200")))
    target = fixture()
    target["providedAmountType"] = "TARGET"
    provider.fetch_quote.return_value = response(target)
    fourth = asyncio.run(service.request_quote(request(source_amount=None, target_amount="129.24")))
    assert len({first.id, second.id, third.id, fourth.id}) == 4
    assert provider.fetch_quote.await_count == 4  # on demand; never cache stale/other scenarios
    assert db.query(WiseIllustrativeQuote).count() == 4
    assert db.query(Quote).count() == 0
    row = db.get(WiseIllustrativeQuote, first.id)
    assert row.response_data["payment_options"][0]["effective_rate"] == "1.2924"
    assert db.get(RawRecord, first.raw_record_id).raw_text
    assert first.source_amount == Decimal("100")


@pytest.mark.parametrize(
    "status,code,error,expected_status",
    [
        (422, "error.route.not.supported", "wise_unsupported_route", 422),
        (401, "invalid_token", "wise_access_unavailable", 503),
        (403, "security.error", "wise_access_unavailable", 503),
        (429, None, "wise_rate_limited", 503),
        (500, None, "wise_provider_failure", 502),
        (200, "error.route.not.supported", "wise_unsupported_route", 422),
    ],
)
def test_provider_failures_are_clear_and_raw_is_retained(db, status, code, error, expected_status):
    payload = {"errors": [{"code": code, "message": "upstream diagnostics"}]} if code else {}
    service = WiseIngestionService(db, adapter=adapter(payload, status=status))
    with pytest.raises(AppError) as exc:
        asyncio.run(service.request_quote(request()))
    assert exc.value.error_code == error and exc.value.status_code == expected_status
    assert "upstream diagnostics" not in exc.value.message
    assert db.query(RawRecord).count() == 1
    assert db.query(WiseIllustrativeQuote).count() == 0
    assert db.query(FetchRun).one().status == FetchRunStatus.FAILED


def test_malformed_quote_preserves_raw_and_other_options_are_not_hidden(db):
    provider = adapter({"sourceCurrency": "EUR", "targetCurrency": "USD"})
    with pytest.raises(AppError, match="could not be processed"):
        asyncio.run(WiseIngestionService(db, adapter=provider).request_quote(request()))
    assert db.query(RawRecord).count() == 1
    payload = fixture()
    broken = copy.deepcopy(payload["paymentOptions"][0])
    broken.update(payIn="CARD", fee="invalid")
    payload["paymentOptions"].append(broken)
    quoted = parse(payload)
    assert len(quoted.payment_options) == 2
    assert quoted.payment_options[1].pay_in == "CARD"
    assert quoted.payment_options[1].warnings
    assert quoted.payment_options[0].effective_rate is not None


def test_tokens_only_sent_to_correct_endpoint_and_never_stored(db):
    token = "test-only-private-wise-key"
    sent = []

    def handle(req):
        sent.append(req)
        return httpx.Response(403, json={"errors": [{"code": "security.error", "message": token}]})

    async def fetch():
        provider = WiseAdapter(token=token, quote_token="")
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            return await provider.fetch_rates(client=client)

    received = asyncio.run(fetch())
    assert sent[0].headers["authorization"] == f"Bearer {token}"
    assert str(sent[0].url).endswith("/2026Q4/rates") and not sent[0].url.query
    assert token not in received.raw_text and token not in str(received.payload)
    provider = adapter()
    provider.fetch_rates.return_value = received
    with pytest.raises(AppError) as error:
        asyncio.run(WiseIngestionService(db, adapter=provider).ingest_market_data())
    raw = db.query(RawRecord).one()
    assert token not in str(raw.payload) + raw.raw_text + str(error.value)


def test_rate_limiting_and_connection_retries_are_bounded():
    attempts = []

    def handle(req):
        attempts.append(req)
        return httpx.Response(429, headers={"Retry-After": "30"}, json={})

    async def call():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            return await WiseAdapter(token="test", quote_token="").fetch_rates(client=client)

    received = asyncio.run(call())
    assert len(attempts) == 1 and received.retry_after == 30  # don't retry too early

    def unreachable(req):
        attempts.append(req)
        raise httpx.ConnectError("upstream unavailable", request=req)

    async def fail():
        async with httpx.AsyncClient(transport=httpx.MockTransport(unreachable)) as client:
            return await WiseAdapter(token="test", quote_token="").fetch_rates(client=client)

    attempts.clear()
    with patch("app.adapters.fx.wise.asyncio.sleep", new_callable=AsyncMock):
        with pytest.raises(AppError, match="could not be reached"):
            asyncio.run(fail())
    assert len(attempts) == 2


def test_wise_api_envelopes_filters_and_input_validation(db):
    from app.dependencies.auth import require_admin
    from app.main import app
    from app.routers.fx import get_fx_diagnostic_service, get_fx_service
    from app.services.fx import FxService
    from app.services.ingestion.fx import FxDiagnosticService

    provider = adapter()
    service = WiseService(db, adapter=provider)
    asyncio.run(service.ingestion.ingest_market_data())
    app.dependency_overrides[get_fx_service] = lambda: FxService(db)
    app.dependency_overrides[get_fx_diagnostic_service] = lambda: FxDiagnosticService(
        db, handlers={"wise": lambda session: WiseIngestionService(session, adapter=provider)}
    )
    try:
        client = TestClient(app)
        read = client.get("/fx/wise/rates?source=eur&target=usd")
        assert read.status_code == 200
        assert read.json()["data"]["items"][0]["classification"] == "reference_rate"
        assert read.json()["data"]["items"][0]["provider_time"].startswith("2018-08-31")
        quoted = client.post(
            "/fx/wise/quotes",
            json={"source_currency": "GBP", "target_currency": "USD", "source_amount": "100"},
        )
        assert quoted.status_code == 401
        provider.fetch_quote.assert_not_awaited()
        app.dependency_overrides[require_admin] = lambda: None
        quoted = client.post(
            "/fx/wise/quotes",
            json={"source_currency": "GBP", "target_currency": "USD", "source_amount": "100"},
        )
        assert quoted.status_code == 200
        assert quoted.json()["data"]["payment_options"][0]["effective_rate"] == "1.2924"
        for body in [
            {},
            {"source_amount": "100", "target_amount": "129.24"},
            {"source_amount": "0"},
            {"source_amount": "NaN"},
            {"source_amount": "-1"},
            {"source_amount": "100", "pay_in": "CARD"},
        ]:
            result = client.post(
                "/fx/wise/quotes",
                json={
                    "source_currency": "GBP",
                    "target_currency": "USD",
                    **body,
                },
            )
            assert result.status_code == 422, result.text
        assert client.get("/fx/wise/rates?source=US").status_code == 422
        assert provider.fetch_quote.await_count == 1
    finally:
        app.dependency_overrides.clear()


def test_missing_wise_credentials_do_not_block_startup_or_cli_help():
    from app.core import config, security
    from app.main import scheduler, start_scheduler

    with (
        patch.object(config, "WISE_API_TOKEN", ""),
        patch.object(config, "WISE_QUOTE_CLIENT_TOKEN", ""),
        patch.object(security, "SECRET_KEY", "test-only-api-signing-secret-at-least-32-characters"),
        patch.object(scheduler, "start", new_callable=AsyncMock) as start,
    ):
        asyncio.run(start_scheduler())
        start.assert_awaited_once()
        assert not WiseAdapter().token


def test_wise_manual_and_scheduled_dispatch_and_restricted_jobs(db):
    from app.core.database import get_db
    from app.dependencies.auth import require_admin
    from app.main import app
    from app.services.ingestion.manual import run_provider_ingestion_job
    from app.services.ingestion_scheduler import IngestionSchedulerService

    WiseRepository(db).register_provider()
    with patch.object(WiseIngestionService, "ingest_market_data", new_callable=AsyncMock) as run:
        asyncio.run(
            IngestionSchedulerService()._dispatch_job(
                db=db, provider_slug="wise", job_type=IngestionJobType.MARKET_DATA
            )
        )
        with (
            patch("app.services.ingestion.manual.SessionLocal", return_value=db),
            patch("app.services.ingestion.manual.ProviderMetricService"),
        ):
            asyncio.run(
                run_provider_ingestion_job(
                    provider_slug="wise", job_type=IngestionJobType.MARKET_DATA
                )
            )
        assert run.await_count == 2
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[require_admin] = lambda: None
    try:
        client = TestClient(app)
        with patch("app.services.provider.launch_provider_ingestion_job") as launch:
            assert client.post("/providers/wise/ingestion-runs/market_data").status_code == 202
            launch.assert_called_once()
            for job in ("kyc", "fees", "fund_details"):
                assert client.post(f"/providers/wise/ingestion-runs/{job}").status_code == 400
            assert (
                client.post(
                    "/providers/wise/ingestion-runs/market_data?include_kyc=true"
                ).status_code
                == 400
            )
        assert (
            client.put(
                "/providers/wise/ingestion-schedules/market_data",
                json={
                    "interval_minutes": 60,
                    "is_enabled": False,
                },
            ).status_code
            == 200
        )
        assert (
            client.put(
                "/providers/wise/ingestion-schedules/fees",
                json={
                    "interval_minutes": 60,
                    "is_enabled": False,
                },
            ).status_code
            == 400
        )
    finally:
        app.dependency_overrides.clear()
