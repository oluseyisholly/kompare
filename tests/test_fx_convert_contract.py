"""Unified customer-direction conversion API; provider fixtures never contact a network."""

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from test_fincra import ingest as ingest_fincra
from test_flutterwave import SCENARIOS
from test_flutterwave import run as ingest_flutterwave
from test_fx import NOW, ingest_rate
from test_fx import db as existing_database
from test_wise import fixture as wise_fixture
from test_wise import parse as parse_wise_quote

from app.core.exceptions import AppError
from app.models.fx import FxQuoteObservation
from app.models.quote import Quote
from app.schemas.fx import FxConversionRequest
from app.services.fx import FxService

db = existing_database
PROVIDERS = ("wise", "flutterwave", "fincra")


def payload(provider, **fields):
    return {
        "provider": provider,
        "source_currency": "USD",
        "target_currency": "NGN",
        "source_amount": "100",
        **fields,
    }


def seed(db, provider):
    if provider == "wise":
        ingest_rate(db, source="USD", target="NGN", rate="1372")
    elif provider == "flutterwave":
        ingest_flutterwave(db)
        for row in db.query(FxQuoteObservation).all():
            row.captured_at = NOW
        db.commit()
    else:
        ingest_fincra(db)


@pytest.fixture
def client(db):
    from app.core.database import get_db
    from app.main import app
    from app.routers.fx import get_fx_service

    overrides = app.dependency_overrides.copy()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_fx_service] = lambda: FxService(db, now=lambda: NOW)
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(overrides)


@pytest.mark.parametrize("provider", PROVIDERS)
def test_same_public_request_and_no_network_for_every_provider(db, client, provider):
    seed(db, provider)
    with (
        patch("httpx.AsyncClient", side_effect=AssertionError("No network in conversion")),
        patch("socket.create_connection", side_effect=AssertionError("No socket in conversion")),
    ):
        response = client.post("/fx/convert", json=payload(provider))
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert {
        "provider",
        "source_currency",
        "target_currency",
        "source_amount",
        "applied_rate",
        "gross_target_amount",
        "fee_amount",
        "fee_currency",
        "fee_status",
        "net_target_amount",
        "rate_classification",
        "observed_at",
        "provider_rate_timestamp",
        "expires_at",
        "is_stale",
        "calculation_basis",
        "warnings",
    } <= data.keys()
    assert Decimal(data["gross_target_amount"]) == (
        Decimal("148600.00") if provider == "fincra" else Decimal("137200.00")
    )
    assert data["fee_status"] == "unavailable"
    assert data["fee_amount"] is data["fee_currency"] is data["net_target_amount"] is None
    assert data["estimated_net_target_amount"] is None
    assert "rate_side" not in data and data["executable"] is False
    assert data["expires_at"] is None
    assert data["metadata"]["fetch_run_id"]
    assert data["rate_classification"] == (
        "reference_rate"
        if provider == "wise"
        else "treasury_rate"
        if provider == "fincra"
        else "transfer_rate_observation"
    )
    if provider == "fincra":
        assert data["metadata"]["fincra_mapping"]["status"] == "assumed"
        assert any("confirmation is pending" in w for w in data["warnings"])


@pytest.mark.parametrize("provider", PROVIDERS)
@pytest.mark.parametrize("side", ["buy", "sell", None])
def test_legacy_rate_side_is_explicitly_rejected(client, provider, side):
    response = client.post("/fx/convert", json=payload(provider, rate_side=side))
    assert response.status_code == 422
    assert any(
        error["type"] == "extra_forbidden" and error["loc"][-1] == "rate_side"
        for error in response.json()["data"]["details"]
    )


def test_flutterwave_uses_independently_collected_directions_and_keeps_amount_scope(db):
    seed(db, "flutterwave")
    service = FxService(db, now=lambda: NOW)
    with patch("httpx.AsyncClient", side_effect=AssertionError("No network")):
        forward = service.convert(FxConversionRequest(**payload("flutterwave"))).data
        reverse = service.convert(
            FxConversionRequest(
                **payload("flutterwave", source_currency="NGN", target_currency="USD")
            )
        ).data
    assert forward.applied_rate == Decimal("1372")
    assert reverse.applied_rate == Decimal("0.000694329")
    assert reverse.applied_rate != Decimal(1) / forward.applied_rate
    assert forward.raw_record_id != reverse.raw_record_id
    assert forward.metadata["pricing_scope"]["requested_target_amount"] == "100000"
    assert forward.metadata["pricing_scope"]["extrapolated"] is True
    assert any("extrapolates" in warning for warning in forward.warnings)
    exact = service.convert(
        FxConversionRequest(
            **payload("flutterwave", source_amount=str(forward.sample_source_amount))
        )
    ).data
    assert exact.metadata["pricing_scope"]["extrapolated"] is False
    assert exact.executable is False


def test_flutterwave_does_not_construct_reverse_or_cross_route(db, client):
    ingest_flutterwave(db, scenarios=[SCENARIOS[1]])
    for source, target in [("NGN", "USD"), ("USD", "EUR")]:
        response = client.post(
            "/fx/convert",
            json=payload("flutterwave", source_currency=source, target_currency=target),
        )
        assert response.status_code == 503
        assert response.json()["data"]["error"] == "fx_rate_unavailable"


@pytest.mark.parametrize(
    "source,target,expected_gross,side,inverted",
    [
        ("USD", "NGN", "148600.00", "buy", False),
        ("NGN", "USD", "0.07", "sell", True),
    ],
)
def test_fincra_applies_disclosed_assumption_from_customer_direction(
    db, client, source, target, expected_gross, side, inverted
):
    seed(db, "fincra")
    # Ingested metadata cannot alter the explicit application mapping policy.
    for row in db.query(Quote).all():
        row.metadata_json = {**row.metadata_json, "side_perspective": "customer"}
    db.commit()
    with patch("httpx.AsyncClient", side_effect=AssertionError("No network")):
        response = client.post(
            "/fx/convert", json=payload("fincra", source_currency=source, target_currency=target)
        )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert Decimal(data["gross_target_amount"]) == Decimal(expected_gross)
    mapping = data["metadata"]["fincra_mapping"]
    assert mapping["status"] == "assumed" and mapping["policy"] == "provider_base_currency_v1"
    assert mapping["provider_side"] == side and mapping["inverted"] == inverted
    assert mapping["base_currency"] == "USD" and mapping["quote_currency"] == "NGN"
    assert db.query(Quote).count() == 2


def test_fincra_missing_pair_stays_distinct_from_assumed_mapping(db, client):
    seed(db, "fincra")
    response = client.post("/fx/convert", json=payload("fincra", target_currency="EUR"))
    assert response.status_code == 503
    assert response.json()["data"]["error"] == "fx_rate_unavailable"


def test_observation_time_is_distinct_from_provider_valuation_time(db):
    seed(db, "wise")
    row = db.query(Quote).one()
    row.captured_at = NOW - timedelta(days=2)
    row.last_seen_at = NOW
    old_provider_time = NOW - timedelta(days=5)
    row.metadata_json = {**row.metadata_json, "provider_time": old_provider_time.isoformat()}
    db.commit()
    response = FxService(db, now=lambda: NOW).convert(FxConversionRequest(**payload("wise"))).data
    assert response.observed_at == NOW
    assert response.captured_at == NOW - timedelta(days=2)
    assert response.provider_rate_timestamp == old_provider_time
    assert response.is_stale
    assert response.expires_at is None


def test_supplied_expiry_is_preserved_and_expired_sample_is_stale(db):
    seed(db, "flutterwave")
    row = db.query(FxQuoteObservation).filter_by(source_currency="USD").one()
    row.expires_at = NOW + timedelta(seconds=10)
    db.commit()
    req = FxConversionRequest(**payload("flutterwave"))
    fresh = FxService(db, now=lambda: NOW).convert(req).data
    assert fresh.expires_at == NOW + timedelta(seconds=10)
    assert fresh.provider_rate_timestamp is None and fresh.observed_at == NOW
    assert not fresh.is_stale
    expired = FxService(db, now=lambda: NOW + timedelta(seconds=11)).convert(req).data
    assert expired.is_stale
    assert any("expired" in warning for warning in expired.warnings)


def test_zero_fee_in_a_scoped_quote_is_distinct_from_unavailable_conversion_fees(db):
    quote = wise_fixture()
    option = quote["paymentOptions"][0]
    option["fee"]["total"] = 0
    option["price"]["total"]["value"]["amount"] = 0
    known_zero = parse_wise_quote(quote).payment_options[0]
    assert known_zero.fee_total == Decimal(0)
    del option["fee"]["total"]
    del option["price"]["total"]["value"]["amount"]
    unknown = parse_wise_quote(quote).payment_options[0]
    assert unknown.fee_total is None
    seed(db, "wise")
    result = FxService(db, now=lambda: NOW).convert(FxConversionRequest(**payload("wise"))).data
    assert result.fee_status == "unavailable"
    assert result.fee_amount is result.net_target_amount is None
    assert result.gross_target_amount == Decimal("137200.00")


def test_invalid_cached_sample_preserves_data_but_cannot_be_converted(db):
    seed(db, "flutterwave")
    row = db.query(FxQuoteObservation).filter_by(source_currency="USD").one()
    original_raw_id = row.raw_record_id
    row.response_data = {**row.response_data, "source_currency": "EUR"}
    db.commit()
    with pytest.raises(AppError) as error:
        FxService(db).convert(FxConversionRequest(**payload("flutterwave")))
    assert error.value.error_code == "fx_rate_unavailable"
    assert db.get(FxQuoteObservation, row.id).raw_record_id == original_raw_id


def test_openapi_documents_common_examples_and_legacy_policy(client):
    schema = client.get("/openapi.json").json()
    request = schema["components"]["schemas"]["FxConversionRequest"]
    expected = {"provider", "source_currency", "target_currency", "source_amount"}
    assert set(request["properties"]) == set(request["required"]) == expected
    assert {e["provider"] for e in request["examples"]} == set(PROVIDERS)
    assert all(set(example) == expected for example in request["examples"])
    assert "rate_side" in schema["paths"]["/fx/convert"]["post"]["description"]
    response = schema["components"]["schemas"]["FxConversionRead"]["properties"]
    assert response["estimated_net_target_amount"]["deprecated"] is True
