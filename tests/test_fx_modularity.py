import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from test_fx import db as existing_database
from test_wise import adapter as wise_adapter
from test_wise import request as quote_request

from app.models.enums import MarketCategory, ProviderName, RawSourceType
from app.models.fx import FxCurrency, FxQuoteObservation
from app.models.provider import Provider
from app.models.raw_record import RawRecord
from app.repositories.fetch_run import FetchRunRepository
from app.repositories.fx import FxRepository
from app.repositories.raw_record import RawRecordRepository
from app.schemas.fx import FxCurrencyRecord, FxReferenceRate
from app.services.ingestion.wise import WiseIngestionService

db = existing_database
CAPTURED = datetime(2026, 11, 2, 12, tzinfo=UTC)


def normalized_provider_data(db, slug, rate, *, symbol="$"):
    # Existing enum members are synthetic FX providers in this isolated database.
    # This test does not add Busha FX functionality to the running application.
    provider = db.query(Provider).filter_by(slug=slug).one_or_none()
    if provider is None:
        provider = Provider(
            slug=slug, name=slug, category=MarketCategory.FX, is_active=True, has_adapter=True
        )
        db.add(provider)
        db.commit()
    provider_id = provider.id
    run = FetchRunRepository(db).create_pending(ProviderName(slug))
    run_id = run.id
    raw = RawRecordRepository(db).create(
        provider=ProviderName(slug),
        fetch_run_id=run_id,
        source_type=RawSourceType.API,
        source_url=f"https://{slug}.example.test/rates",
        payload={"test_only": True},
        raw_text='{"test_only":true}',
    )
    raw_id = raw.id
    repository = FxRepository(db)
    saved = repository.persist_rates(
        [
            FxReferenceRate(
                source_currency="EUR", target_currency="USD", rate=rate, provider_time=CAPTURED
            )
        ],
        provider=slug,
        source_url=f"https://{slug}.example.test/rates",
        api_version="test-only",
        fetch_run_id=run_id,
        raw_record_id=raw_id,
        captured_at=CAPTURED,
    )
    repository.persist_currencies(
        [FxCurrencyRecord(code="USD", name="US Dollar", symbol=symbol, supports_decimals=True)],
        provider_id=provider_id,
        snapshot_complete=False,
        source_url=f"https://{slug}.example.test/currencies",
        fetch_run_id=run_id,
        raw_record_id=raw_id,
        captured_at=CAPTURED,
    )
    assert saved["rates_observed"] == 1
    return provider_id, raw_id


def test_one_generic_api_filters_every_provider_without_network(db):
    from app.core.database import get_db
    from app.main import app

    normalized_provider_data(db, "wise", "1.1")
    normalized_provider_data(db, "busha", "2.2", symbol="US$")
    normalized_provider_data(db, "wise", "9.9")
    app.dependency_overrides[get_db] = lambda: db
    try:
        with patch("httpx.AsyncClient", side_effect=AssertionError("Read APIs cannot use HTTP")):
            client = TestClient(app)
            for slug, expected in [("wise", "9.9"), ("busha", "2.2")]:
                rates = client.get(f"/fx/{slug}/rates?source=EUR&target=USD")
                assert rates.status_code == 200
                items = rates.json()["data"]["items"]
                assert len(items) == 1
                assert items[0]["provider"] == slug and items[0]["rate"] == expected
                assert "environment" not in items[0]
                currencies = client.get(f"/fx/{slug}/currencies").json()["data"]["items"]
                assert len(currencies) == 1 and currencies[0]["provider"] == slug
                converted = client.post(
                    "/fx/convert",
                    json={
                        "provider": slug,
                        "source_currency": "EUR",
                        "target_currency": "USD",
                        "source_amount": "100",
                    },
                )
                assert converted.status_code == 200
                assert (
                    Decimal(converted.json()["data"]["gross_target_amount"])
                    == Decimal(expected) * 100
                )
                assert converted.json()["data"]["fee_status"] == "unavailable"
            for resource in ("rates", "currencies"):
                assert client.get(f"/fx/unknown/{resource}").status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_registered_provider_without_ingestion_or_enum_returns_empty_data(db):
    from app.core.database import get_db
    from app.main import app

    db.add(
        Provider(
            slug="future_fx",
            name="Future FX fixture",
            category=MarketCategory.FX,
            is_active=True,
            has_adapter=False,
        )
    )
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        for resource in ("rates", "currencies"):
            response = client.get(f"/fx/future_fx/{resource}")
            assert response.status_code == 200
            assert response.json()["data"]["pagination"]["total"] == 0
    finally:
        app.dependency_overrides.clear()


def test_optional_currency_capabilities_do_not_fabricate_values(db):
    provider_id, raw_id = normalized_provider_data(db, "busha", "1.5")
    repository = FxRepository(db)
    repository.persist_currencies(
        [FxCurrencyRecord(code="ZZZ")],
        provider_id=provider_id,
        snapshot_complete=False,
        source_url="https://fixture.example.test/currencies",
        captured_at=CAPTURED,
        raw_record_id=raw_id,
        fetch_run_id=db.get(RawRecord, raw_id).fetch_run_id,
    )
    row = db.query(FxCurrency).filter_by(provider_id=provider_id, code="ZZZ").one()
    assert row.name is row.symbol is row.supports_decimals is row.decimal_places is None


def test_shared_quote_observations_preserve_provider_identity_and_precision(db):
    first = asyncio.run(
        WiseIngestionService(db, adapter=wise_adapter()).request_quote(quote_request())
    )
    provider_id, raw_id = normalized_provider_data(db, "busha", "2")
    other = first.model_copy(deep=True)
    other.provider = "busha"
    other.id = None
    other.source_url = "https://fixture.example.test/quotes"
    other.raw_record_id = raw_id
    other.fetch_run_id = db.get(RawRecord, raw_id).fetch_run_id
    row = FxRepository(db).save_quote(
        other,
        provider_id=provider_id,
        raw_record_id=raw_id,
        fetch_run_id=other.fetch_run_id,
    )
    assert db.query(FxQuoteObservation).count() == 2
    assert row.response_data["provider"] == "busha"
    assert row.response_data["payment_options"][0]["effective_rate"] == "1.2924"
    with pytest.raises(ValueError, match="provider does not match"):
        FxRepository(db).save_quote(
            first,
            provider_id=provider_id,
            raw_record_id=raw_id,
            fetch_run_id=other.fetch_run_id,
        )


def test_generic_diagnostic_is_admin_only_and_dispatches_only_registered_handler(db):
    from app.core.database import get_db
    from app.dependencies.auth import require_admin
    from app.main import app
    from app.routers.fx import get_fx_diagnostic_service
    from app.services.ingestion.fx import FxDiagnosticService

    normalized_provider_data(db, "wise", "1")
    normalized_provider_data(db, "busha", "2")
    provider = wise_adapter()
    diagnostic = FxDiagnosticService(
        db,
        handlers={
            "wise": lambda session: WiseIngestionService(session, adapter=provider),
        },
    )
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_fx_diagnostic_service] = lambda: diagnostic
    try:
        client = TestClient(app)
        body = quote_request().model_dump(mode="json")
        assert client.post("/fx/wise/quotes", json=body).status_code == 401
        provider.fetch_quote.assert_not_awaited()
        app.dependency_overrides[require_admin] = lambda: None
        unsupported = client.post("/fx/busha/quotes", json=body)
        assert unsupported.status_code == 503
        assert unsupported.json()["data"]["error"] == "fx_diagnostic_unavailable"
        provider.fetch_quote.assert_not_awaited()
        diagnostic.handlers["busha"] = lambda session: object()
        assert client.post("/fx/busha/quotes", json=body).status_code == 503
        quoted = client.post("/fx/wise/quotes", json=body)
        assert quoted.status_code == 200 and quoted.json()["data"]["provider"] == "wise"
        provider.fetch_quote.assert_awaited_once()
    finally:
        app.dependency_overrides.clear()


def test_openapi_uses_one_fx_group_and_shared_provider_parameters():
    from app.main import app

    schema = app.openapi()
    for path in (
        "/fx/convert",
        "/fx/{provider}/rates",
        "/fx/{provider}/currencies",
        "/fx/{provider}/quotes",
    ):
        assert path in schema["paths"]
        operation = next(iter(schema["paths"][path].values()))
        assert operation["tags"] == ["FX"]
        if "{provider}" in path:
            assert any(
                p["name"] == "provider" and p["in"] == "path" for p in operation["parameters"]
            )
    assert not any(path.startswith("/fx/wise/") for path in schema["paths"])
    assert not any(tag["name"] == "wise-fx" for tag in schema["tags"])
