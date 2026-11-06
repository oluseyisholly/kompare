"""Password recovery races on isolated PostgreSQL, never the application's database."""

import importlib
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import text
from sqlalchemy.orm import Session
from test_production_postgres import pg_engine as existing_pg_engine

from app.core import config, security
from app.core.exceptions import AppError, UnauthorizedError
from app.dependencies.auth import get_current_user
from app.models.enums import UserRole, UserStatus, VerificationChannel, VerificationPurpose
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.models.verification_otp import VerificationOtp
from app.repositories.refresh_token import RefreshTokenRepository
from app.repositories.user import UserRepository
from app.repositories.verification_otp import VerificationOtpRepository
from app.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    RefreshTokenRequest,
    ResetPasswordRequest,
)
from app.services.auth import AuthService

pytestmark = pytest.mark.skipif(
    not os.getenv("KOMPARE_FX_TEST_PG_SOCKET"),
    reason="Requires explicitly configured disposable PostgreSQL socket",
)
pg_engine = existing_pg_engine
EMAIL = "reset@example.com"
OLD_PASSWORD = "old-password-fixture"


@pytest.fixture(autouse=True)
def signing_key(monkeypatch):
    monkeypatch.setattr(security, "SECRET_KEY", "isolated-reset-postgres-key-only-178249032651")


def auth_service(db, email=None):
    return AuthService(
        UserRepository(db),
        RefreshTokenRepository(db),
        VerificationOtpRepository(db),
        email or Mock(send_email=Mock(return_value=True)),
    )


def seed(engine, *, with_code=True):
    with Session(engine) as db:
        row = User(
            email=EMAIL,
            password_hash=security.hash_password(OLD_PASSWORD),
            role=UserRole.USER,
            status=UserStatus.ACTIVE,
            is_active=True,
            is_verified=True,
        )
        db.add(row)
        db.flush()
        if with_code:
            db.add(
                VerificationOtp(
                    user_id=row.id,
                    target=EMAIL,
                    purpose=VerificationPurpose.PASSWORD_RESET,
                    channel=VerificationChannel.EMAIL,
                    otp_hash=security.hash_token("123456"),
                    expires_at=datetime.now(UTC) + timedelta(minutes=10),
                )
            )
        db.commit()


def test_concurrent_resets_consume_code_once(pg_engine):
    seed(pg_engine)
    barrier = threading.Barrier(2)

    def reset(index):
        with Session(pg_engine) as db:
            barrier.wait(timeout=10)
            try:
                auth_service(db).reset_password(
                    ResetPasswordRequest(
                        email=EMAIL,
                        otp="123456",
                        new_password=f"new-password-{index}",
                    )
                )
                return index
            except AppError as exc:
                assert exc.status_code == 400
                return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(reset, range(2)))
    winners = [index for index in results if index is not None]
    assert len(winners) == 1
    with Session(pg_engine) as db:
        row = db.query(User).one()
        code = db.query(VerificationOtp).one()
        assert row.auth_version == 1 and code.used_at and not code.is_active
        assert security.verify_password(f"new-password-{winners[0]}", row.password_hash)


def test_reset_serializes_with_old_password_login_and_refresh(pg_engine):
    seed(pg_engine)
    with Session(pg_engine) as db:
        initial = auth_service(db).login(LoginRequest(email=EMAIL, password=OLD_PASSWORD))
    barrier = threading.Barrier(3)

    def operation(name):
        with Session(pg_engine) as db:
            service = auth_service(db)
            barrier.wait(timeout=10)
            try:
                if name == "reset":
                    service.reset_password(
                        ResetPasswordRequest(
                            email=EMAIL,
                            otp="123456",
                            new_password="new-password-fixture",
                        )
                    )
                    return None
                if name == "login":
                    return service.login(LoginRequest(email=EMAIL, password=OLD_PASSWORD))
                return service.refresh(RefreshTokenRequest(refresh_token=initial.refresh_token))
            except UnauthorizedError:
                assert name != "reset"
                return None

    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(operation, ("reset", "login", "refresh")))
    with Session(pg_engine) as db:
        row = db.query(User).one()
        assert (
            row.auth_version == 1 and db.query(RefreshToken).filter_by(is_active=True).count() == 0
        )
        assert security.verify_password("new-password-fixture", row.password_hash)
        for session in [initial] + [result for result in results if result is not None]:
            with pytest.raises(UnauthorizedError):
                get_current_user(
                    HTTPAuthorizationCredentials(scheme="Bearer", credentials=session.access_token),
                    db,
                )
            with pytest.raises(UnauthorizedError):
                auth_service(db).refresh(RefreshTokenRequest(refresh_token=session.refresh_token))


def test_concurrent_forgot_requests_issue_one_code_within_cooldown(pg_engine, monkeypatch):
    seed(pg_engine, with_code=False)
    monkeypatch.setattr(config, "AUTH_OTP_RESEND_COOLDOWN_SECONDS", 60)
    email = Mock(send_email=Mock(return_value=True))
    barrier = threading.Barrier(2)

    def request(_):
        with Session(pg_engine) as db:
            barrier.wait(timeout=10)
            auth_service(db, email).forgot_password(ForgotPasswordRequest(email=EMAIL))

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(request, range(2)))
    email.send_email.assert_called_once()
    with Session(pg_engine) as db:
        assert db.query(VerificationOtp).count() == 1


def test_session_version_migration_preserves_existing_users_and_has_a_default(pg_engine):
    seed(pg_engine, with_code=False)
    migration = importlib.import_module(
        "app.migrations.versions.i5d6e7f8g9h0_password_reset_sessions"
    )
    with pg_engine.begin() as connection:
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            migration.downgrade()
            migration.upgrade()
        assert connection.execute(text("SELECT auth_version FROM users")).scalar_one() == 0
        connection.execute(text("UPDATE users SET auth_version=1"))
        assert connection.execute(text("SELECT auth_version FROM users")).scalar_one() == 1
        # The server default protects inserts by older tooling during a rollout.
        connection.execute(
            text("""INSERT INTO users (email,password_hash,role,status)
            VALUES ('new@example.com','fixture','USER','ACTIVE')""")
        )
        assert (
            connection.execute(
                text("SELECT auth_version FROM users WHERE email='new@example.com'")
            ).scalar_one()
            == 0
        )
