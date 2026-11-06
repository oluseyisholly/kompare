"""Real concurrency and upgrade checks restricted to disposable PostgreSQL."""

import importlib
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import URL, create_engine, text
from sqlalchemy.orm import Session

from app.core import security
from app.core.database import Base
from app.core.exceptions import AppError
from app.core.security import create_refresh_token, hash_token
from app.models.enums import IngestionJobType, MarketCategory, UserRole, UserStatus
from app.models.ingestion_job import IngestionJob
from app.models.ingestion_schedule import IngestionSchedule
from app.models.provider import Provider
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.repositories.auth_rate_limit import AuthRateLimitRepository
from app.repositories.ingestion_job import IngestionJobRepository
from app.repositories.ingestion_schedule import IngestionScheduleRepository
from app.repositories.refresh_token import RefreshTokenRepository
from app.repositories.user import UserRepository
from app.repositories.verification_otp import VerificationOtpRepository
from app.schemas.auth import RefreshTokenRequest
from app.services.auth import AuthService

pytestmark = pytest.mark.skipif(
    not os.getenv("KOMPARE_FX_TEST_PG_SOCKET"),
    reason="Requires explicitly configured disposable PostgreSQL socket",
)


@pytest.fixture
def pg_engine():
    socket = os.environ["KOMPARE_FX_TEST_PG_SOCKET"]
    assert socket.startswith("/tmp/kompare-wise-pg.")
    url = URL.create(
        "postgresql+psycopg2",
        username="postgres",
        host=socket,
        port=55484,
        database="kompare_fx_refresh_test",
    )
    root = create_engine(url)
    schema = "production_test_" + uuid4().hex
    with root.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"}, pool_size=10)
    Base.metadata.create_all(engine)
    try:
        yield engine
    finally:
        engine.dispose()
        with root.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        root.dispose()


def test_limits_are_atomic_across_connections(pg_engine):
    barrier = threading.Barrier(8)

    def attempt(_):
        with Session(pg_engine) as db:
            barrier.wait(timeout=10)
            try:
                AuthRateLimitRepository(db).consume(
                    "login", "fixture@example.invalid", limit=2, window_seconds=60
                )
                return True
            except AppError as exc:
                assert exc.status_code == 429
                return False

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(attempt, range(8)))
    assert sum(results) == 2


def test_one_refresh_consumer_and_rollback_preserves_original(pg_engine):
    with patch.object(
        security, "SECRET_KEY", "isolated-postgres-test-key-fixture-not-for-deployment"
    ):
        with Session(pg_engine) as db:
            user = User(
                email="refresh@example.invalid",
                password_hash="not-used",
                role=UserRole.USER,
                is_active=True,
                is_verified=True,
                status=UserStatus.ACTIVE,
            )
            db.add(user)
            db.flush()
            token, expires = create_refresh_token(subject=str(user.id), token_id="fixture-refresh")
            db.add(
                RefreshToken(
                    user_id=user.id,
                    token_id="fixture-refresh",
                    token_hash=hash_token(token),
                    expires_at=expires,
                )
            )
            db.commit()
        barrier = threading.Barrier(2)

        def refresh(_):
            with Session(pg_engine) as db:
                service = AuthService(
                    UserRepository(db),
                    RefreshTokenRepository(db),
                    VerificationOtpRepository(db),
                    Mock(),
                )
                barrier.wait(timeout=10)
                try:
                    service.refresh(RefreshTokenRequest(refresh_token=token))
                    return True
                except AppError as exc:
                    assert exc.status_code == 401
                    return False

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(refresh, range(2)))
        assert sum(results) == 1
        with Session(pg_engine) as db:
            assert db.query(RefreshToken).filter_by(is_active=True).count() == 1


def test_two_schedulers_enqueue_one_job_and_workers_claim_once(pg_engine):
    now = datetime.now(UTC)
    with Session(pg_engine) as db:
        provider = Provider(slug="wise", name="Fixture", category=MarketCategory.FX)
        db.add(provider)
        db.flush()
        schedule = IngestionSchedule(
            provider_id=provider.id,
            job_type=IngestionJobType.MARKET_DATA,
            interval_minutes=60,
            is_enabled=True,
            next_run_at=now - timedelta(seconds=1),
        )
        db.add(schedule)
        db.commit()
        key = schedule.id
    barrier = threading.Barrier(2)

    def enqueue(_):
        with Session(pg_engine) as db:
            barrier.wait(timeout=10)
            return IngestionScheduleRepository(db).enqueue_due(key, now=now)

    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = list(pool.map(enqueue, range(2)))
    assert len([j for j in jobs if j is not None]) == 1
    barrier = threading.Barrier(2)

    def claim(_):
        with Session(pg_engine) as db:
            barrier.wait(timeout=10)
            row = IngestionJobRepository(db).claim(lease_seconds=60, max_attempts=3)
            return row.id if row else None

    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(claim, range(2)))
    assert len([j for j in claims if j is not None]) == 1
    with Session(pg_engine) as db:
        assert db.query(IngestionJob).count() == 1


def test_readiness_upgrade_disables_only_legacy_credentials(pg_engine):
    migration = importlib.import_module("app.migrations.versions.h4c5d6e7f8g9_production_readiness")
    # Extract the old hash from the migration without exposing it in output.
    import ast
    from pathlib import Path

    tree = ast.parse(Path(migration.__file__).read_text())
    legacy = next(
        n.value.value
        for n in ast.walk(tree)
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "legacy_hash" for t in n.targets)
    )
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE ingestion_jobs"))
        conn.execute(text("DROP TABLE auth_rate_limits"))
        conn.execute(text("ALTER TABLE verification_otps DROP COLUMN failed_attempts"))
        for address, password in [
            ("legacy@example.invalid", legacy),
            ("rotated@example.invalid", "rotated-hash"),
        ]:
            conn.execute(
                text("""INSERT INTO users (email,password_hash,role,admin_type,status,
                         is_superadmin,is_active,is_verified)
                VALUES (:email,:password,'ADMIN','SUPER_ADMIN','ACTIVE',true,true,true)"""),
                {"email": address, "password": password},
            )
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            migration.upgrade()
        states = dict(conn.execute(text("SELECT email,is_active FROM users")).all())
        assert states == {"legacy@example.invalid": False, "rotated@example.invalid": True}
        assert (
            conn.execute(
                text("SELECT status FROM users WHERE email='legacy@example.invalid'")
            ).scalar_one()
            == "SUSPENDED"
        )
        with Operations.context(ctx):
            migration.downgrade()
        assert (
            conn.execute(
                text("SELECT is_active FROM users WHERE email='legacy@example.invalid'")
            ).scalar_one()
            is False
        )
