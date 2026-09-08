from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from datetime import UTC, datetime, timedelta

from app.core.config import ACCESS_TOKEN_EXPIRE_MINUTES, REFRESH_TOKEN_EXPIRE_DAYS, SECRET_KEY


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        100_000,
    ).hex()
    return f"{salt}${digest}"


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def verify_token_hash(token: str, expected_hash: str) -> bool:
    actual_hash = hash_token(token)
    return hmac.compare_digest(actual_hash, expected_hash)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        salt, expected_digest = password_hash.split("$", 1)
    except ValueError:
        return False

    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        100_000,
    ).hex()
    return hmac.compare_digest(digest, expected_digest)


def _create_signed_token(payload: dict) -> str:
    payload_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    payload_b64 = base64.urlsafe_b64encode(payload_bytes).decode("utf-8").rstrip("=")
    signature = hmac.new(SECRET_KEY.encode("utf-8"), payload_b64.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload_b64}.{signature}"


def create_access_token(
    *,
    subject: str,
    email: str,
    role: str,
    is_superadmin: bool,
    is_active: bool,
    is_verified: bool,
    first_name: str | None = None,
    last_name: str | None = None,
    last_login_at: datetime | None = None,
    created_at: datetime | None = None,
    updated_at: datetime | None = None,
    expires_delta: timedelta | None = None,
) -> str:
    expire_at = datetime.now(UTC) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    payload = {
        "sub": subject,
        "type": "access",
        "email": email,
        "role": role,
        "is_superadmin": is_superadmin,
        "is_active": is_active,
        "is_verified": is_verified,
        "first_name": first_name,
        "last_name": last_name,
        "last_login_at": last_login_at.isoformat() if last_login_at else None,
        "created_at": created_at.isoformat() if created_at else None,
        "updated_at": updated_at.isoformat() if updated_at else None,
        "exp": int(expire_at.timestamp()),
    }
    return _create_signed_token(payload)


def create_refresh_token(*, subject: str, token_id: str, expires_delta: timedelta | None = None) -> tuple[str, datetime]:
    expire_at = datetime.now(UTC) + (expires_delta or timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS))
    payload = {
        "sub": subject,
        "jti": token_id,
        "type": "refresh",
        "exp": int(expire_at.timestamp()),
    }
    return _create_signed_token(payload), expire_at


def decode_access_token(token: str) -> dict:
    try:
        payload_b64, signature = token.split(".", 1)
    except ValueError as exc:
        raise ValueError("Invalid token format") from exc

    expected_signature = hmac.new(
        SECRET_KEY.encode("utf-8"),
        payload_b64.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(signature, expected_signature):
        raise ValueError("Invalid token signature")

    padding = "=" * (-len(payload_b64) % 4)
    payload_bytes = base64.urlsafe_b64decode(payload_b64 + padding)
    payload = json.loads(payload_bytes.decode("utf-8"))

    if int(payload.get("exp", 0)) < int(datetime.now(UTC).timestamp()):
        raise ValueError("Token has expired")

    return payload
