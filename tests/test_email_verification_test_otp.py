import os
import runpy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from test_production_security import client as existing_client
from test_production_security import db as existing_database
from test_production_security import fixture_key as existing_fixture_key
from test_production_security import otp, user

from app.core import config, security
from app.models.enums import UserStatus, VerificationPurpose
from app.models.verification_otp import VerificationOtp

db = existing_database
client = existing_client
fixture_key = existing_fixture_key


def verify(client, row, code="000000"):
    return client.post("/auth/verify-email", json={"email": row.email, "otp": code})


@pytest.mark.parametrize(
    "value,expected",
    [
        (None, True),
        ("true", True),
        ("TRUE", True),
        ("1", True),
        ("false", False),
        (" FALSE ", False),
        ("0", False),
        ("off", False),
        ("no", False),
        ("", True),
        ("typo", True),
        ("production", True),
    ],
)
def test_production_flag_requires_explicit_false_to_allow_test_otp(value, expected):
    environment = {} if value is None else {"IS_PRODUCTION": value}
    path = Path(__file__).resolve().parents[1] / "app/core/config.py"
    with patch.dict(os.environ, environment, clear=True), patch("dotenv.load_dotenv"):
        assert runpy.run_path(str(path))["IS_PRODUCTION"] is expected


def test_test_code_is_disabled_by_default(db, client):
    path = Path(__file__).resolve().parents[1] / "app/core/config.py"
    with patch.dict(os.environ, {}, clear=True), patch("dotenv.load_dotenv"):
        assert runpy.run_path(str(path))["IS_PRODUCTION"] is True
    row = user(db, verified=False)
    stored = otp(db, row)
    assert verify(client, row).status_code == 400
    db.refresh(row)
    db.refresh(stored)
    assert not row.is_verified and stored.failed_attempts == 1


def test_registration_email_failure_does_not_block_verification_and_login(db, client, monkeypatch):
    from app.dependencies.providers import get_email_service
    from app.main import app

    monkeypatch.setattr(config, "IS_PRODUCTION", False)
    email = Mock(send_email=Mock(return_value=False))
    app.dependency_overrides[get_email_service] = lambda: email
    registered = client.post(
        "/auth/register",
        json={
            "email": "test-account@example.com",
            "password": "ExamplePassword123!",
        },
    )
    assert registered.status_code == 201 and not registered.json()["data"]["is_verified"]
    stored = db.query(VerificationOtp).one()
    verified = client.post(
        "/auth/verify-email",
        json={
            "email": "test-account@example.com",
            "otp": "000000",
        },
    )
    assert verified.status_code == 200 and verified.json()["data"]["is_verified"]
    db.refresh(stored)
    assert stored.used_at and not stored.is_active
    logged_in = client.post(
        "/auth/login",
        json={
            "email": "test-account@example.com",
            "password": "ExamplePassword123!",
        },
    )
    assert logged_in.status_code == 200
    assert logged_in.json()["data"]["access_token"]
    assert (
        client.post(
            "/auth/login",
            json={
                "email": "test-account@example.com",
                "password": "wrong-password",
            },
        ).status_code
        == 401
    )
    email.send_email.assert_called_once()


@pytest.mark.parametrize("is_production", [False, True])
def test_real_emailed_code_continues_to_work(db, client, monkeypatch, is_production):
    monkeypatch.setattr(config, "IS_PRODUCTION", is_production)
    row = user(db, verified=False)
    otp(db, row)
    assert verify(client, row, "246810").status_code == 200


@pytest.mark.parametrize(
    "failure",
    [
        "missing",
        "expired",
        "used",
        "exhausted",
        "password_reset",
        "wrong_target",
        "inactive_user",
        "suspended_user",
    ],
)
def test_temporary_code_preserves_code_and_account_restrictions(db, client, monkeypatch, failure):
    monkeypatch.setattr(config, "IS_PRODUCTION", False)
    row = user(db, verified=False)
    stored = otp(db, row)
    if failure == "missing":
        db.delete(stored)
    elif failure == "expired":
        stored.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    elif failure == "used":
        stored.used_at = datetime.now(UTC)
    elif failure == "exhausted":
        stored.failed_attempts = config.AUTH_OTP_MAX_ATTEMPTS
    elif failure == "password_reset":
        stored.purpose = VerificationPurpose.PASSWORD_RESET
    elif failure == "wrong_target":
        stored.target = "someone-else@example.com"
    elif failure == "inactive_user":
        row.is_active = False
    elif failure == "suspended_user":
        row.status = UserStatus.SUSPENDED
    db.commit()
    assert verify(client, row).status_code == 400
    db.refresh(row)
    assert not row.is_verified


@pytest.mark.parametrize("wrong_code", ["00000", "0000000", "111111"])
def test_only_exactly_six_zeros_is_the_temporary_code(db, client, monkeypatch, wrong_code):
    monkeypatch.setattr(config, "IS_PRODUCTION", False)
    row = user(db, verified=False)
    otp(db, row)
    assert verify(client, row, wrong_code).status_code == 400


def test_switching_to_production_requires_real_otp(db, client, monkeypatch):
    first = user(db, verified=False)
    otp(db, first)
    monkeypatch.setattr(config, "IS_PRODUCTION", False)
    assert verify(client, first).status_code == 200
    row = user(db, verified=False)
    stored = otp(db, row)
    monkeypatch.setattr(config, "IS_PRODUCTION", True)
    assert verify(client, row).status_code == 400
    assert verify(client, row, "246810").status_code == 200
    db.refresh(stored)
    assert stored.used_at


def test_temporary_verification_code_cannot_reset_password(db, client, monkeypatch):
    monkeypatch.setattr(config, "IS_PRODUCTION", False)
    row = user(db)
    stored = otp(db, row)
    stored.purpose = VerificationPurpose.PASSWORD_RESET
    db.commit()
    response = client.post(
        "/auth/reset-password",
        json={
            "email": row.email,
            "otp": "000000",
            "new_password": "NewPassword123!",
        },
    )
    assert response.status_code == 400
    db.refresh(row)
    assert security.verify_password("fixture-password-123", row.password_hash)
    assert (
        client.post(
            "/auth/reset-password",
            json={
                "email": row.email,
                "otp": "246810",
                "new_password": "NewPassword123!",
            },
        ).status_code
        == 200
    )
