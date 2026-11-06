"""Password recovery through the public API, with local storage and mocked email only."""

import re
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient
from test_production_security import authorization, otp, user
from test_stanbic_ingestion import db as existing_database

from app.core import config, security
from app.core.database import get_db
from app.core.exceptions import BadRequestError
from app.dependencies import get_auth_service
from app.main import app
from app.models.enums import UserStatus, VerificationPurpose
from app.models.refresh_token import RefreshToken
from app.models.verification_otp import VerificationOtp
from app.repositories.refresh_token import RefreshTokenRepository
from app.repositories.user import UserRepository
from app.repositories.verification_otp import VerificationOtpRepository
from app.schemas.auth import ForgotPasswordRequest, LoginRequest, ResetPasswordRequest
from app.services.auth import AuthService

db = existing_database
OLD_PASSWORD = "fixture-password-123"
NEW_PASSWORD = "new-fixture-password-456"


@pytest.fixture(autouse=True)
def settings(monkeypatch):
    monkeypatch.setattr(security, "SECRET_KEY", "isolated-password-reset-tests-only-149206731")
    monkeypatch.setattr(config, "PASSWORD_RESET_OTP_LENGTH", 6)
    monkeypatch.setattr(config, "PASSWORD_RESET_OTP_EXPIRE_MINUTES", 10)
    monkeypatch.setattr(config, "AUTH_OTP_MAX_ATTEMPTS", 5)
    monkeypatch.setattr(config, "AUTH_OTP_RESEND_COOLDOWN_SECONDS", 60)
    monkeypatch.setattr(config, "AUTH_EMAIL_IP_LIMIT", 20)
    monkeypatch.setattr(config, "AUTH_EMAIL_ACCOUNT_LIMIT", 3)
    monkeypatch.setattr(config, "AUTH_OTP_IP_LIMIT", 60)


@pytest.fixture
def service(db):
    return AuthService(
        UserRepository(db),
        RefreshTokenRepository(db),
        VerificationOtpRepository(db),
        Mock(send_email=Mock(return_value=True)),
    )


@pytest.fixture
def client(db, service):
    overrides = app.dependency_overrides.copy()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_auth_service] = lambda: service
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(overrides)


def request_code(service, row):
    service.forgot_password(ForgotPasswordRequest(email=row.email))
    return re.search(
        r"code is ([0-9]+)", service.email_service.send_email.call_args.kwargs["body"]
    )[1]


def payload(row, code, **fields):
    return {"email": row.email, "otp": code, "new_password": NEW_PASSWORD, **fields}


def test_public_flow_revokes_all_sessions_and_requires_new_login(db, client, service):
    row = user(db)
    login = client.post("/auth/login", json={"email": row.email, "password": OLD_PASSWORD})
    assert login.status_code == 200
    tokens = login.json()["data"]
    second_session = service.login(LoginRequest(email=row.email, password=OLD_PASSWORD))
    old_headers = {"Authorization": "Bearer " + tokens["access_token"]}
    assert client.get("/auth/me", headers=old_headers).status_code == 200
    response = client.post("/auth/forgot-password", json={"email": row.email.upper()})
    assert response.status_code == 200
    assert response.json()["data"] == {"status": "accepted"}
    code = re.search(
        r"code is ([0-9]+)", service.email_service.send_email.call_args.kwargs["body"]
    )[1]
    stored = db.query(VerificationOtp).filter_by(purpose=VerificationPurpose.PASSWORD_RESET).one()
    assert stored.otp_hash == security.hash_token(code) and stored.otp_hash != code
    assert code not in response.text
    assert service.email_service.send_email.call_args.kwargs["to_email"] == row.email

    result = client.post("/auth/reset-password", json=payload(row, code))
    assert result.status_code == 200
    assert result.json()["data"] == {"status": "password_reset"}
    db.refresh(row)
    db.refresh(stored)
    assert row.auth_version == 1 and stored.used_at and not stored.is_active
    assert security.verify_password(NEW_PASSWORD, row.password_hash)
    assert not security.verify_password(OLD_PASSWORD, row.password_hash)
    assert db.query(RefreshToken).filter_by(user_id=row.id, is_active=True).count() == 0
    assert client.get("/auth/me", headers=old_headers).status_code == 401
    assert (
        client.get(
            "/auth/me", headers={"Authorization": "Bearer " + second_session.access_token}
        ).status_code
        == 401
    )
    for token in (tokens["refresh_token"], second_session.refresh_token):
        assert client.post("/auth/refresh", json={"refresh_token": token}).status_code == 401
    assert (
        client.post("/auth/login", json={"email": row.email, "password": OLD_PASSWORD}).status_code
        == 401
    )
    assert client.post("/auth/reset-password", json=payload(row, code)).status_code == 400
    new_login = client.post("/auth/login", json={"email": row.email, "password": NEW_PASSWORD})
    assert new_login.status_code == 200
    new_tokens = new_login.json()["data"]
    assert (
        client.get(
            "/auth/me", headers={"Authorization": "Bearer " + new_tokens["access_token"]}
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/auth/refresh", json={"refresh_token": new_tokens["refresh_token"]}
        ).status_code
        == 200
    )


def test_forgot_response_is_uniform_for_unknown_inactive_and_suspended_accounts(
    db, client, service
):
    available = user(db)
    inactive = user(db)
    suspended = user(db)
    inactive.is_active = False
    suspended.status = UserStatus.SUSPENDED
    db.commit()
    responses = [
        client.post("/auth/forgot-password", json={"email": email})
        for email in (
            available.email,
            inactive.email,
            suspended.email,
            "unknown@example.com",
        )
    ]
    assert all(r.status_code == 200 and r.json() == responses[0].json() for r in responses)
    service.email_service.send_email.assert_called_once()
    assert db.query(VerificationOtp).count() == 1


def test_email_delivery_failure_does_not_disclose_account_existence(db, client, service):
    row = user(db)
    service.email_service.send_email.return_value = False
    known = client.post("/auth/forgot-password", json={"email": row.email})
    unknown = client.post("/auth/forgot-password", json={"email": "unknown@example.com"})
    assert known.status_code == 200 and known.json() == unknown.json()
    assert security.verify_password(OLD_PASSWORD, row.password_hash)


@pytest.mark.parametrize("registered", [True, False])
def test_forgot_password_limits_and_cooldown_are_applied_to_all_accounts(db, client, registered):
    email = user(db).email if registered else "unknown@example.com"
    assert client.post("/auth/forgot-password", json={"email": email}).status_code == 200
    limited = client.post("/auth/forgot-password", json={"email": email.upper()})
    assert limited.status_code == 429 and int(limited.headers["retry-after"]) > 0


def test_resend_rotates_only_reset_codes_and_preserves_password_until_confirmation(db, service):
    row = user(db, verified=False)
    verification = otp(db, row)
    with patch("app.services.auth.secrets.randbelow", side_effect=[123456, 654321]):
        first_code = request_code(service, row)
        first = (
            db.query(VerificationOtp).filter_by(purpose=VerificationPurpose.PASSWORD_RESET).one()
        )
        request_code(service, row)
        assert service.email_service.send_email.call_count == 1
        first.created_at = datetime.now(UTC) - timedelta(seconds=61)
        db.commit()
        second_code = request_code(service, row)
    db.refresh(first)
    db.refresh(verification)
    assert not first.is_active and verification.is_active
    assert security.verify_password(OLD_PASSWORD, row.password_hash)
    with pytest.raises(BadRequestError):
        service.reset_password(ResetPasswordRequest(**payload(row, first_code)))
    service.reset_password(ResetPasswordRequest(**payload(row, second_code)))
    db.refresh(row)
    assert not row.is_verified and row.status == UserStatus.UNVERIFIED


@pytest.mark.parametrize(
    "failure",
    ["expired", "email_verification", "wrong_target", "other_user", "inactive", "suspended"],
)
def test_invalid_proof_never_changes_password_or_reveals_account(db, client, service, failure):
    row = user(db)
    code = request_code(service, row)
    stored = db.query(VerificationOtp).one()
    if failure == "expired":
        stored.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    elif failure == "email_verification":
        stored.purpose = VerificationPurpose.EMAIL_VERIFICATION
    elif failure == "wrong_target":
        stored.target = "another@example.com"
    elif failure == "other_user":
        stored.user_id = user(db).id
    elif failure == "inactive":
        row.is_active = False
    else:
        row.status = UserStatus.SUSPENDED
    db.commit()
    result = client.post("/auth/reset-password", json=payload(row, code))
    unknown = client.post(
        "/auth/reset-password", json=payload(row, code, email="unknown@example.com")
    )
    assert result.status_code == 400 and result.json() == unknown.json()
    db.refresh(row)
    assert security.verify_password(OLD_PASSWORD, row.password_hash) and row.auth_version == 0


def test_attempt_exhaustion_does_not_revoke_valid_sessions_or_change_password(db, client, service):
    row = user(db)
    headers = authorization(row)
    code = request_code(service, row)
    wrong = "000000" if code != "000000" else "999999"
    with patch.object(config, "AUTH_OTP_MAX_ATTEMPTS", 3):
        for _ in range(3):
            assert client.post("/auth/reset-password", json=payload(row, wrong)).status_code == 400
        assert client.post("/auth/reset-password", json=payload(row, code)).status_code == 400
    stored = db.query(VerificationOtp).one()
    assert stored.failed_attempts == 3 and not stored.is_active
    assert client.get("/auth/me", headers=headers).status_code == 200
    assert security.verify_password(OLD_PASSWORD, row.password_hash)


def test_reset_ip_limit_is_shared_even_for_unknown_accounts(client):
    with patch.object(config, "AUTH_OTP_IP_LIMIT", 1):
        assert (
            client.post(
                "/auth/reset-password",
                json={
                    "email": "unknown@example.com",
                    "otp": "123456",
                    "new_password": NEW_PASSWORD,
                },
            ).status_code
            == 400
        )
        result = client.post(
            "/auth/reset-password",
            json={
                "email": "other@example.com",
                "otp": "123456",
                "new_password": NEW_PASSWORD,
            },
        )
    assert result.status_code == 429


@pytest.mark.parametrize(
    "fields",
    [
        {"new_password": "short"},
        {"new_password": "a" * 129},
        {"otp": ""},
        {"otp": "abcdef"},
        {"otp": "1234567890123"},
        {"email": "invalid"},
        {"extra_field": "ignored?"},
    ],
)
def test_invalid_payloads_leave_the_code_usable(db, client, service, fields):
    row = user(db)
    code = request_code(service, row)
    result = client.post("/auth/reset-password", json=payload(row, code, **fields))
    assert result.status_code == 422
    assert db.query(VerificationOtp).one().is_active
    assert security.verify_password(OLD_PASSWORD, row.password_hash)


def test_password_code_and_session_changes_rollback_together(db, service):
    row = user(db)
    service.login(LoginRequest(email=row.email, password=OLD_PASSWORD))
    code = request_code(service, row)
    with patch.object(
        service.refresh_token_repository,
        "revoke_all_for_user_without_commit",
        side_effect=RuntimeError("fixture failure"),
    ):
        with pytest.raises(RuntimeError, match="fixture failure"):
            service.reset_password(ResetPasswordRequest(**payload(row, code)))
    db.refresh(row)
    stored = db.query(VerificationOtp).one()
    assert row.auth_version == 0 and security.verify_password(OLD_PASSWORD, row.password_hash)
    assert stored.is_active and stored.used_at is None
    assert db.query(RefreshToken).filter_by(is_active=True).count() == 1
    service.reset_password(ResetPasswordRequest(**payload(row, code)))


def test_access_tokens_without_version_are_revoked_after_reset(db, client, service):
    row = user(db)
    claims = security.decode_access_token(authorization(row)["Authorization"].split(" ")[1])
    claims.pop("auth_version")
    headers = {"Authorization": "Bearer " + security._create_signed_token(claims)}
    assert client.get("/auth/me", headers=headers).status_code == 200
    code = request_code(service, row)
    service.reset_password(ResetPasswordRequest(**payload(row, code)))
    assert client.get("/auth/me", headers=headers).status_code == 401
