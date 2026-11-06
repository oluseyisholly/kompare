from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.adapters.mutual_fund.stanbic import StanbicAdapter
from app.core.database import Base, get_db
from app.models.enums import FetchRunStatus, IngestionJobType
from app.models.fetch_run import FetchRun
from app.models.mutual_fund import MutualFund, MutualFundSnapshot
from app.models.provider import Provider
from app.models.raw_record import RawRecord
from app.repositories.mutual_fund import MutualFundRepository
from app.services.ingestion.stanbic import StanbicIngestionService
from app.services.ingestion_scheduler import IngestionSchedulerService

HTML = (Path(__file__).parent / "fixtures" / "stanbic_funds.html").read_text()


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def ingest(db, html=HTML):
    import asyncio

    adapter = StanbicAdapter()
    adapter.fetch_page = AsyncMock(return_value=html)
    result = asyncio.run(StanbicIngestionService(db, adapter=adapter).ingest_market_data())
    adapter.fetch_page.assert_awaited_once()
    return result


def test_parse_real_cards_and_nullable_values():
    records, failures = StanbicAdapter().parse(HTML)
    assert not failures
    assert len(records) == 9
    funds = {r.code: r for r in records}
    money = funds["stanbic-simm"]
    assert money.yield_percent == Decimal("16.24")
    assert money.yield_label == "Indicative Yield"
    assert money.bid_price is money.offer_price is money.nav_per_unit is None
    dollar = funds["stanbic-sidf"]
    assert dollar.currency == "USD"
    assert dollar.bid_price == Decimal("1.7248")
    assert dollar.yield_percent is dollar.yield_label is None
    assert funds["stanbic-sibal"].offer_price == Decimal("13840.35")
    assert all(r.nav_per_unit is None and r.valuation_date is None for r in records)


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-1", "1,23", "oops"])
def test_invalid_price_is_reported_per_fund(value):
    records, failures = StanbicAdapter().parse(
        HTML.replace("$1.7248 / $1.7248", f"${value} / $1.7248")
    )
    assert len(records) == 8
    assert failures[0]["code"] == "sidf"
    assert failures[0]["error"]


def test_missing_single_value_remains_null():
    records, failures = StanbicAdapter().parse(HTML.replace("$1.7248 / $1.7248", "— / $1.7248"))
    assert not failures
    dollar = next(r for r in records if r.code == "stanbic-sidf")
    assert dollar.bid_price is None
    assert dollar.offer_price == Decimal("1.7248")


def test_stable_matching_uses_link_not_name(db):
    ingest(db)
    first = db.query(MutualFund).filter_by(code="stanbic-simm").one()
    original_id = first.id
    renamed = HTML.replace("Stanbic IBTC Money Market Fund", "Renamed Money Market Fund")
    ingest(db, renamed)
    assert db.query(Provider).count() == 1
    assert db.query(MutualFund).count() == 9
    assert db.query(MutualFund).filter_by(code="stanbic-simm").one().id == original_id
    assert first.name == "Renamed Money Market Fund"
    assert db.query(MutualFundSnapshot).count() == 18


def test_same_run_retry_and_database_constraint(db):
    result = ingest(db)
    raw = db.query(RawRecord).one()
    assert raw.source_url == StanbicAdapter.source_url
    assert raw.raw_text == raw.payload["content"] == HTML
    records, _ = StanbicAdapter().parse(HTML)
    repo = MutualFundRepository(db)
    assert (
        repo.persist(
            provider_id=db.query(Provider).one().id,
            records=records,
            fetch_run_id=result["fetch_run_id"],
            raw_record_id=raw.id,
        )
        == 0
    )
    assert db.query(MutualFundSnapshot).count() == 9
    snapshot = db.query(MutualFundSnapshot).first()
    db.add(
        MutualFundSnapshot(
            fund_id=snapshot.fund_id, fetch_run_id=snapshot.fetch_run_id, raw_record_id=raw.id
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_failed_extraction_preserves_prior_data_and_raw_evidence(db):
    ingest(db)
    with pytest.raises(ValueError, match="no mutual-fund cards"):
        ingest(db, "<html>Unexpected upstream page</html>")
    assert db.query(MutualFundSnapshot).count() == 9
    assert db.query(MutualFund).filter_by(is_active=True).count() == 9
    assert db.query(RawRecord).count() == 2
    failed = db.query(FetchRun).order_by(FetchRun.id.desc()).first()
    assert failed.status == FetchRunStatus.FAILED
    assert "no mutual-fund cards" in failed.error_message


def test_partial_failure_saves_only_valid_funds(db):
    ingest(db)
    result = ingest(db, HTML.replace("16.24%", "broken%"))
    assert result["status"] == "partial"
    assert result["snapshots_created"] == 8
    assert result["extraction_failures"][0]["code"] == "simm"
    fund = db.query(MutualFund).filter_by(code="stanbic-simm").one()
    assert fund.is_active
    assert db.query(MutualFundSnapshot).filter_by(fund_id=fund.id).count() == 1
    assert db.query(FetchRun).order_by(FetchRun.id.desc()).first().status == FetchRunStatus.FAILED


def test_duplicate_or_unmapped_codes_are_reported():
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(HTML, "html.parser")
    duplicate = str(soup.select_one("li.plan-item"))
    records, failures = StanbicAdapter().parse(HTML + duplicate)
    assert len(records) == 8
    assert "Duplicate" in failures[0]["error"]
    records, failures = StanbicAdapter().parse(HTML.replace("fund/simm", "fund/unknown"))
    assert len(records) == 8
    assert "Unmapped" in failures[0]["error"]


def test_network_failure_records_failed_run(db):
    import asyncio

    adapter = StanbicAdapter()
    adapter.fetch_page = AsyncMock(side_effect=RuntimeError("network unavailable"))
    with pytest.raises(RuntimeError, match="network unavailable"):
        asyncio.run(StanbicIngestionService(db, adapter=adapter).ingest_market_data())
    assert db.query(FetchRun).one().status == FetchRunStatus.FAILED
    assert db.query(MutualFund).count() == 0


def test_persistence_failure_rolls_back_all_funds(db):
    with patch.object(MutualFundRepository, "persist", side_effect=RuntimeError("write failure")):
        with pytest.raises(RuntimeError, match="write failure"):
            ingest(db)
    assert db.query(MutualFund).count() == 0
    assert db.query(RawRecord).count() == 1
    assert db.query(FetchRun).one().status == FetchRunStatus.FAILED


def test_invalid_persistence_batch_is_atomic(db):
    ingest(db)
    records, _ = StanbicAdapter().parse(HTML)
    records[0].name = "Must roll back this rename"
    bad = records[1].model_dump()
    bad["offer_price"] = Decimal("NaN")
    from app.models.enums import ProviderName
    from app.repositories.fetch_run import FetchRunRepository

    run = FetchRunRepository(db).create_pending(ProviderName.STANBIC)
    with pytest.raises(ValueError):
        MutualFundRepository(db).persist(
            provider_id=db.query(Provider).one().id,
            records=[records[0], bad],
            fetch_run_id=run.id,
            raw_record_id=db.query(RawRecord).one().id,
        )
    assert db.query(MutualFundSnapshot).count() == 9
    assert db.query(MutualFund).filter_by(code="stanbic-simm").one().name != records[0].name


def test_manual_trigger_and_schedule_api(db):
    from app.dependencies.auth import require_admin
    from app.main import app

    MutualFundRepository(db).register_stanbic()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[require_admin] = lambda: None
    try:
        client = TestClient(app)
        with patch("app.services.provider.launch_provider_ingestion_job") as launch:
            response = client.post("/providers/stanbic/ingestion-runs/market_data")
            assert response.status_code == 202
            launch.assert_called_once_with(
                db=db,
                provider_slug="stanbic",
                job_type=IngestionJobType.MARKET_DATA,
                include_kyc=False,
            )
            assert client.post("/providers/stanbic/ingestion-runs/kyc").status_code == 400
            assert (
                client.post(
                    "/providers/stanbic/ingestion-runs/market_data?include_kyc=true",
                ).status_code
                == 400
            )
            assert launch.call_count == 1
        response = client.put(
            "/providers/stanbic/ingestion-schedules/market_data",
            json={"interval_minutes": 1440, "is_enabled": True},
        )
        assert response.status_code == 200
        assert response.json()["data"]["provider_slug"] == "stanbic"
        assert (
            client.put(
                "/providers/stanbic/ingestion-schedules/fees", json={"interval_minutes": 1440}
            ).status_code
            == 400
        )
    finally:
        app.dependency_overrides.clear()


def test_api_lists_and_returns_latest_nullable_snapshot(db):
    from app.main import app

    ingest(db)
    ingest(db)
    app.dependency_overrides[get_db] = lambda: db
    try:
        # Avoid application lifespan: no scheduler or external database is started.
        client = TestClient(app)
        response = client.get("/mutual-funds/?provider=stanbic&per_page=2")
        assert response.status_code == 200
        assert response.json()["data"]["pagination"]["total"] == 9
        assert len(response.json()["data"]["items"]) == 2
        response = client.get("/mutual-funds/stanbic-simm/latest-snapshot")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["fetch_run_id"] == 2
        assert Decimal(str(data["yield_percent"])) == Decimal("16.24")
        assert data["nav_per_unit"] is data["valuation_date"] is None
        assert client.get("/mutual-funds/missing/latest-snapshot").status_code == 404
        assert client.get("/mutual-funds/?provider=missing").status_code == 404
        assert client.get("/mutual-funds/?per_page=0").status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_scheduler_dispatches_stanbic(db):
    import asyncio

    with patch.object(StanbicIngestionService, "ingest_market_data", new_callable=AsyncMock) as run:
        asyncio.run(
            IngestionSchedulerService()._dispatch_job(
                db=db, provider_slug="stanbic", job_type=IngestionJobType.MARKET_DATA
            )
        )
        run.assert_awaited_once()


def test_manual_job_dispatches_stanbic(db):
    import asyncio

    from app.services.ingestion.manual import run_provider_ingestion_job

    with (
        patch("app.services.ingestion.manual.SessionLocal", return_value=db),
        patch.object(StanbicIngestionService, "ingest_market_data", new_callable=AsyncMock) as run,
        patch("app.services.ingestion.manual.ProviderMetricService") as metrics,
    ):
        asyncio.run(
            run_provider_ingestion_job(
                provider_slug="stanbic",
                job_type=IngestionJobType.MARKET_DATA,
            )
        )
        run.assert_awaited_once()
        metrics.return_value.refresh_provider_by_slug.assert_called_once_with("stanbic")
