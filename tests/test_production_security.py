from datetime import UTC, datetime, timedelta
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient
from test_stanbic_ingestion import db as existing_database

from app.core import config, security
from app.core.security import create_access_token, create_refresh_token, hash_password, hash_token
from app.models.enums import (
    AdminType,
    MarketCategory,
    UserRole,
    UserStatus,
    VerificationChannel,
    VerificationPurpose,
)
from app.models.provider import Provider
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.models.verification_otp import VerificationOtp
from app.repositories.auth_rate_limit import AuthRateLimitRepository
from app.repositories.refresh_token import RefreshTokenRepository
from app.repositories.user import UserRepository
from app.repositories.verification_otp import VerificationOtpRepository
from app.schemas.auth import RefreshTokenRequest
from app.services.auth import AuthService

db = existing_database


@pytest.fixture(autouse=True)
def fixture_key():
    with patch.object(security, "SECRET_KEY", "isolated-auth-test-key-only-784bf510293bd471"):
        yield


@pytest.fixture
def client(db):
    from app.core.database import get_db
    from app.dependencies.providers import get_email_service
    from app.main import app

    overrides = app.dependency_overrides.copy()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_email_service] = lambda: Mock(send_email=Mock(return_value=True))
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(overrides)


def user(db, *, admin=False, verified=True):
    row = User(
        email=f"user-{db.query(User).count()}@example.invalid",
        password_hash=hash_password("fixture-password-123"),
        role=UserRole.ADMIN if admin else UserRole.USER,
        admin_type=AdminType.SUPPORT_ADMIN if admin else None,
        status=UserStatus.ACTIVE if verified else UserStatus.UNVERIFIED,
        is_active=True,
        is_verified=verified,
    )
    db.add(row)
    db.commit()
    return row


def authorization(row, **claims):
    fields = dict(
        subject=str(row.id),
        email=row.email,
        role=row.role.value,
        admin_type=row.admin_type.value if row.admin_type else None,
        is_superadmin=row.is_superadmin,
        is_active=row.is_active,
        is_verified=row.is_verified,
        status=row.status.value,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
    return {"Authorization": "Bearer " + create_access_token(**{**fields, **claims})}


def service(db):
    return AuthService(
        UserRepository(db), RefreshTokenRepository(db), VerificationOtpRepository(db), Mock()
    )


def test_provider_update_requires_current_admin_role(db, client):
    provider = Provider(slug="wise", name="Wise", category=MarketCategory.FX)
    db.add(provider)
    db.commit()
    payload = {"is_active": False}
    assert client.patch("/providers/wise", json=payload).status_code == 401
    ordinary = user(db)
    assert (
        client.patch("/providers/wise", json=payload, headers=authorization(ordinary)).status_code
        == 403
    )
    # Stale or inflated token roles cannot override current DB roles.
    inflated = authorization(ordinary, role="admin", admin_type="support_admin")
    assert client.patch("/providers/wise", json=payload, headers=inflated).status_code == 403
    admin = user(db, admin=True)
    headers = authorization(admin)
    assert client.patch("/providers/wise", json=payload, headers=headers).status_code == 200
    db.refresh(provider)
    assert provider.is_active is False
    admin.role = UserRole.USER
    admin.admin_type = None
    db.commit()
    assert client.patch("/providers/wise", json=payload, headers=headers).status_code == 403


def test_suspended_or_deleted_account_cannot_use_old_token(db, client):
    row = user(db)
    headers = authorization(row)
    assert client.get("/auth/me", headers=headers).status_code == 200
    row.is_active = False
    row.status = UserStatus.SUSPENDED
    db.commit()
    assert client.get("/auth/me", headers=headers).status_code == 401
    db.delete(row)
    db.commit()
    assert client.get("/auth/me", headers=headers).status_code == 401


def test_login_limits_known_and_unknown_accounts_and_emits_retry_after(db, client):
    row = user(db)
    with patch.object(config, "AUTH_LOGIN_ACCOUNT_LIMIT", 2):
        for email in (row.email, "unknown@example.invalid"):
            for _ in range(2):
                assert (
                    client.post(
                        "/auth/login", json={"email": email, "password": "wrong-password"}
                    ).status_code
                    == 401
                )
            limited = client.post(
                "/auth/login", json={"email": email, "password": "wrong-password"}
            )
            assert limited.status_code == 429
            assert int(limited.headers["retry-after"]) > 0
            assert limited.json()["data"]["error"] == "auth_rate_limited"


def test_shared_limit_window_resets_without_storing_raw_identifier(db):
    from app.core.exceptions import AppError
    from app.models.auth_rate_limit import AuthRateLimit

    now = datetime.now(UTC)
    first = AuthRateLimitRepository(db)
    second = AuthRateLimitRepository(db)
    first.consume("login", "private@example.invalid", limit=1, window_seconds=60, now=now)
    with pytest.raises(AppError):
        second.consume("login", "private@example.invalid", limit=1, window_seconds=60, now=now)
    assert "private" not in db.query(AuthRateLimit).one().bucket_key
    second.consume(
        "login",
        "private@example.invalid",
        limit=1,
        window_seconds=60,
        now=now + timedelta(seconds=61),
    )


def otp(db, row):
    value = VerificationOtp(
        user_id=row.id,
        otp_hash=hash_token("246810"),
        purpose=VerificationPurpose.EMAIL_VERIFICATION,
        channel=VerificationChannel.EMAIL,
        target=row.email,
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
    )
    db.add(value)
    db.commit()
    return value


def test_otp_attempt_budget_invalidates_code_and_preserves_account(db, client):
    row = user(db, verified=False)
    code = otp(db, row)
    with patch.object(config, "AUTH_OTP_MAX_ATTEMPTS", 3):
        for _ in range(3):
            assert (
                client.post(
                    "/auth/verify-email", json={"email": row.email, "otp": "000000"}
                ).status_code
                == 400
            )
        assert (
            client.post(
                "/auth/verify-email", json={"email": row.email, "otp": "246810"}
            ).status_code
            == 400
        )
    db.refresh(code)
    db.refresh(row)
    assert code.failed_attempts == 3 and not code.is_active and not row.is_verified


def test_valid_otp_before_budget_and_resend_cooldown(db, client):
    row = user(db, verified=False)
    code = otp(db, row)
    assert (
        client.post("/auth/resend-verification-otp", json={"email": row.email}).status_code == 200
    )
    assert (
        client.post("/auth/verify-email", json={"email": row.email, "otp": "000000"}).status_code
        == 400
    )
    assert (
        client.post("/auth/verify-email", json={"email": row.email, "otp": "246810"}).status_code
        == 200
    )
    db.refresh(code)
    assert code.used_at and not code.is_active
    assert (
        client.post(
            "/auth/resend-verification-otp", json={"email": "unknown@example.invalid"}
        ).status_code
        == 200
    )


def refresh_fixture(db, row):
    token, expires = create_refresh_token(subject=str(row.id), token_id="fixture-token-id")
    db.add(
        RefreshToken(
            user_id=row.id,
            token_id="fixture-token-id",
            token_hash=hash_token(token),
            expires_at=expires,
        )
    )
    db.commit()
    return token


def test_refresh_consumes_once_and_rolls_back_when_replacement_fails(db):
    from app.core.exceptions import UnauthorizedError

    row = user(db)
    token = refresh_fixture(db, row)
    auth = service(db)
    with patch.object(
        auth, "_issue_refresh_token", side_effect=RuntimeError("storage unavailable")
    ):
        with pytest.raises(RuntimeError):
            auth.refresh(RefreshTokenRequest(refresh_token=token))
    assert db.query(RefreshToken).filter_by(token_id="fixture-token-id").one().is_active
    result = auth.refresh(RefreshTokenRequest(refresh_token=token))
    assert result.refresh_token != token
    with pytest.raises(UnauthorizedError):
        auth.refresh(RefreshTokenRequest(refresh_token=token))
    assert db.query(RefreshToken).filter_by(is_active=True).count() == 1


def test_input_limits_and_validation_do_not_echo_passwords(client):
    response = client.post(
        "/auth/login",
        json={"email": "invalid-email", "password": "sensitive-fixture-" + ("a" * 150)},
    )
    assert response.status_code == 422
    assert (
        "sensitive-fixture" not in response.text
        and "input" not in response.json()["data"]["details"][0]
    )


def test_explicit_superadmin_provisioning_has_no_default_and_no_promotion(db):
    from app.scripts.create_superadmin import provision

    key = provision(db, email="operator@example.invalid", password="private-fixture-password")
    account = db.get(User, key)
    assert account.admin_type == AdminType.SUPER_ADMIN and account.is_verified
    with pytest.raises(ValueError, match="refusing"):
        provision(db, email=account.email, password="another-private-password")


def test_reactivating_legacy_seed_does_not_restore_compromised_credentials(db, client):
    row = user(db, admin=True)
    row.password_hash = security.LEGACY_BOOTSTRAP_PASSWORD_HASH
    db.commit()
    assert not security.verify_password("arbitrary-fixture", row.password_hash)
    assert client.get("/auth/me", headers=authorization(row)).status_code == 401
    token = refresh_fixture(db, row)
    response = client.post("/auth/refresh", json={"refresh_token": token})
    assert response.status_code == 401


def test_known_exposed_signing_key_is_rejected_without_storing_plaintext():
    import hashlib
    from unittest.mock import patch

    value = "disposable-compromised-key-fixture-only-0123456789"
    with (
        patch.object(security, "SECRET_KEY", value),
        patch.object(
            security, "COMPROMISED_SIGNING_KEY_HASHES", {hashlib.sha256(value.encode()).hexdigest()}
        ),
    ):
        with pytest.raises(ValueError, match="SECRET_KEY must be configured"):
            security.validate_auth_secret()
