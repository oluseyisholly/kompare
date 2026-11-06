import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from test_stanbic_ingestion import db as existing_database

from app.models.asset import Asset
from app.models.enums import IngestionJobType, MarketCategory, ProviderName, QuoteType
from app.models.ingestion_job import IngestionJob
from app.models.ingestion_schedule import IngestionSchedule
from app.models.provider import Provider
from app.models.provider_asset import ProviderAsset
from app.models.quote import Quote
from app.repositories.ingestion_job import IngestionJobRepository
from app.repositories.ingestion_schedule import IngestionScheduleRepository
from app.repositories.quote import QuoteRepository
from app.services.ingestion.manual import launch_provider_ingestion_job

db = existing_database


def test_empty_quote_is_rejected_before_superseding_prior_price(db):
    asset = Asset(code="BTC", name="Bitcoin", category=MarketCategory.CRYPTO)
    db.add(asset)
    db.commit()
    fields = dict(
        provider=ProviderName.QUIDAX,
        asset_id=asset.id,
        quote_type=QuoteType.SPOT,
        base_currency="BTC",
        quote_currency="NGN",
    )
    repository = QuoteRepository(db)
    repository.create_many([Quote(**fields, buy_rate=100)])
    old = db.query(Quote).one()
    with pytest.raises(ValueError, match="no usable price"):
        repository.create_many([Quote(**fields)])
    db.refresh(old)
    assert old.superseded_at is None and db.query(Quote).count() == 1


def test_provider_shaped_bad_ticker_preserves_valid_quote_and_reports_partial_failure(db):
    from app.repositories.fetch_run import FetchRunRepository
    from app.repositories.kyc import KycRepository
    from app.repositories.provider_asset import ProviderAssetRepository
    from app.repositories.raw_record import RawRecordRepository
    from app.services.ingestion.quidax import QuidaxIngestionService

    asset = Asset(code="BTC", name="Bitcoin", category=MarketCategory.CRYPTO)
    db.add(asset)
    db.flush()
    pa = ProviderAsset(
        provider=ProviderName.QUIDAX,
        asset_id=asset.id,
        provider_symbol="btcngn",
        is_active=True,
        metadata_json={"quote_unit": "NGN"},
    )
    db.add(pa)
    db.commit()
    adapter = SimpleNamespace(
        tickers_url="https://example.invalid/tickers",
        fetch_tickers=AsyncMock(
            return_value={
                "data": {"btcngn": {"ticker": {"buy": "100", "sell": "101", "last": "100.5"}}}
            }
        ),
    )
    service = QuidaxIngestionService(
        db,
        adapter=adapter,
        fetch_run_repository=FetchRunRepository(db),
        raw_record_repository=RawRecordRepository(db),
        provider_asset_repository=ProviderAssetRepository(db),
        quote_repository=QuoteRepository(db),
        kyc_repository=KycRepository(db),
        focus_selector=Mock(should_use_provider_asset=Mock(return_value=True)),
    )
    asyncio.run(service.ingest_market_data())
    old = db.query(Quote).one()
    adapter.fetch_tickers.return_value = {"data": {"btcngn": {"ticker": {}}}}
    result = asyncio.run(service.ingest_market_data())
    assert result["extraction_failures"] and result["quotes_created"] == 0
    db.refresh(old)
    assert old.superseded_at is None
    assert db.query(Quote).count() == 1


def test_manual_acknowledgement_survives_request_session_and_claim_is_fenced(db):
    key = launch_provider_ingestion_job(
        db=db, provider_slug="wise", job_type=IngestionJobType.MARKET_DATA
    )
    db.expire_all()
    now = datetime.now(UTC)
    repository = IngestionJobRepository(db)
    first = repository.claim(lease_seconds=10, max_attempts=3, now=now)
    token = first.lease_token
    assert first.id == key and repository.claim(lease_seconds=10, max_attempts=3, now=now) is None
    second = repository.claim(lease_seconds=10, max_attempts=3, now=now + timedelta(seconds=11))
    assert second.id == key and second.attempts == 2 and second.lease_token != token
    assert not repository.finish(key, token, success=True, now=now + timedelta(seconds=12))
    assert repository.finish(key, second.lease_token, success=True, now=now + timedelta(seconds=12))
    assert db.get(IngestionJob, key).status == "success"


def test_schedule_and_queue_insert_commit_together_and_retry_does_not_duplicate(db):
    provider = Provider(slug="wise", name="Wise fixture", category=MarketCategory.FX)
    db.add(provider)
    db.flush()
    now = datetime.now(UTC)
    schedule = IngestionSchedule(
        provider_id=provider.id,
        job_type=IngestionJobType.MARKET_DATA,
        is_enabled=True,
        interval_minutes=60,
        next_run_at=now - timedelta(seconds=1),
    )
    db.add(schedule)
    db.commit()
    repository = IngestionScheduleRepository(db)
    assert repository.enqueue_due(schedule.id, now=now)
    assert repository.enqueue_due(schedule.id, now=now) is None
    assert db.query(IngestionJob).count() == 1


def test_exhausted_crash_retries_are_terminal(db):
    repository = IngestionJobRepository(db)
    key = repository.enqueue(provider_slug="wise", job_type="market_data")
    now = datetime.now(UTC)
    repository.claim(lease_seconds=5, max_attempts=1, now=now)
    assert repository.claim(lease_seconds=5, max_attempts=1, now=now + timedelta(seconds=6)) is None
    db.expire_all()
    assert db.get(IngestionJob, key).status == "failed"


def test_worker_executes_job_and_updates_durable_status(db):
    # The synchronous executor is run outside the API/worker event loop.
    from sqlalchemy.orm import sessionmaker

    from app.services.ingestion_worker import IngestionWorker

    factory = sessionmaker(bind=db.bind)
    key = IngestionJobRepository(db).enqueue(provider_slug="wise", job_type="market_data")
    executor = Mock(return_value={"status": "success"})
    worker = IngestionWorker(session_factory=factory, executor=executor)
    assert asyncio.run(worker.run_once())
    executor.assert_called_once_with("wise", "market_data", False)
    db.expire_all()
    assert db.get(IngestionJob, key).status == "success"


def test_readiness_and_job_status_are_safe_api_operations(db):
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    from fastapi.testclient import TestClient
    from sqlalchemy import text

    from app.core.database import get_db
    from app.dependencies.auth import require_admin
    from app.main import app

    overrides = app.dependency_overrides.copy()
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        assert client.get("/health/live").status_code == 200
        assert client.get("/health/ready").status_code == 503
        head = ScriptDirectory.from_config(Config("app/alembic.ini")).get_current_head()
        db.execute(text("CREATE TABLE alembic_version (version_num varchar(32) PRIMARY KEY)"))
        db.execute(text("INSERT INTO alembic_version VALUES (:head)"), {"head": head})
        db.commit()
        assert client.get("/health/ready").status_code == 200
        assert client.get("/providers/wise/raw-records").status_code == 401
        key = IngestionJobRepository(db).enqueue(provider_slug="wise", job_type="market_data")
        assert client.get(f"/providers/wise/ingestion-jobs/{key}").status_code == 401
        app.dependency_overrides[require_admin] = lambda: None
        response = client.get(f"/providers/wise/ingestion-jobs/{key}")
        assert response.status_code == 200 and response.json()["data"]["status"] == "pending"
        assert "lease_token" not in response.json()["data"]
        assert client.get(f"/providers/fincra/ingestion-jobs/{key}").status_code == 404
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(overrides)


def test_schedule_claim_rolls_back_queue_and_next_run_on_commit_failure(db):
    from unittest.mock import patch

    provider = Provider(slug="wise", name="Wise fixture", category=MarketCategory.FX)
    db.add(provider)
    db.flush()
    now = datetime.now(UTC)
    schedule = IngestionSchedule(
        provider_id=provider.id,
        job_type=IngestionJobType.MARKET_DATA,
        interval_minutes=60,
        is_enabled=True,
        next_run_at=now - timedelta(minutes=1),
    )
    db.add(schedule)
    db.commit()
    key = schedule.id
    with patch.object(db, "commit", side_effect=RuntimeError("commit unavailable")):
        with pytest.raises(RuntimeError):
            IngestionScheduleRepository(db).enqueue_due(key, now=now)
    assert db.query(IngestionJob).count() == 0
    value = db.get(IngestionSchedule, key).next_run_at
    value = value.replace(tzinfo=UTC) if value.tzinfo is None else value
    assert value == now - timedelta(minutes=1)


def test_heartbeat_extends_lease_and_completion_updates_schedule(db):
    provider = Provider(slug="wise", name="Wise fixture", category=MarketCategory.FX)
    db.add(provider)
    db.flush()
    now = datetime.now(UTC)
    schedule = IngestionSchedule(
        provider_id=provider.id,
        job_type=IngestionJobType.MARKET_DATA,
        interval_minutes=60,
        is_enabled=True,
        next_run_at=now - timedelta(minutes=1),
    )
    db.add(schedule)
    db.commit()
    IngestionScheduleRepository(db).enqueue_due(schedule.id, now=now)
    repository = IngestionJobRepository(db)
    job = repository.claim(lease_seconds=10, max_attempts=3, now=now)
    assert repository.heartbeat(
        job.id, job.lease_token, lease_seconds=10, now=now + timedelta(seconds=9)
    )
    assert (
        repository.claim(lease_seconds=10, max_attempts=3, now=now + timedelta(seconds=11)) is None
    )
    assert repository.finish(job.id, job.lease_token, success=True, now=now + timedelta(seconds=12))
    db.refresh(schedule)
    value = (
        schedule.last_run_at.replace(tzinfo=UTC)
        if schedule.last_run_at.tzinfo is None
        else schedule.last_run_at
    )
    assert value == now + timedelta(seconds=12)
