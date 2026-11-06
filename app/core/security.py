from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from datetime import UTC, datetime, timedelta

from app.core.config import ACCESS_TOKEN_EXPIRE_MINUTES, REFRESH_TOKEN_EXPIRE_DAYS, SECRET_KEY

# Historical bootstrap hash must remain unusable even if its account is reactivated.
LEGACY_BOOTSTRAP_PASSWORD_HASH = (
    "kompare_seed_superadmin$b8dcb75ef162883a982c9f0b94c71b782d8ba85bb9ed4b160abb319da9c664e6"
)


def has_legacy_bootstrap_password(password_hash: str) -> bool:
    return hmac.compare_digest(password_hash, LEGACY_BOOTSTRAP_PASSWORD_HASH)


# Fingerprint only: never retain the signing key that was committed to Git.
COMPROMISED_SIGNING_KEY_HASHES = {
    "81128f79fce27209aa218ec3ef08a14c773eeeb6a381490ccb775bab0c42d5b8"
}


def validate_auth_secret() -> None:
    if (
        len(SECRET_KEY.strip()) < 32
        or SECRET_KEY.strip() in {"kompare-dev-secret", "change-me"}
        or hashlib.sha256(SECRET_KEY.encode()).hexdigest() in COMPROMISED_SIGNING_KEY_HASHES
    ):
        raise ValueError(
            "SECRET_KEY must be configured with a private, randomly generated value "
            "for API authentication. Generate one with: "
            'python -c "import secrets; print(secrets.token_urlsafe(32))"'
        )


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
    if has_legacy_bootstrap_password(password_hash):
        return False
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
    validate_auth_secret()
    payload_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    payload_b64 = base64.urlsafe_b64encode(payload_bytes).decode("utf-8").rstrip("=")
    signature = hmac.new(
        SECRET_KEY.encode("utf-8"), payload_b64.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return f"{payload_b64}.{signature}"


def create_access_token(
    *,
    subject: str,
    email: str,
    role: str,
    admin_type: str | None,
    is_superadmin: bool,
    is_active: bool,
    is_verified: bool,
    phone_number: str | None = None,
    is_phone_verified: bool = False,
    status: str | None = None,
    first_name: str | None = None,
    last_name: str | None = None,
    last_login_at: datetime | None = None,
    created_at: datetime | None = None,
    updated_at: datetime | None = None,
    auth_version: int = 0,
    expires_delta: timedelta | None = None,
) -> str:
    expire_at = datetime.now(UTC) + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    payload = {
        "sub": subject,
        "type": "access",
        "auth_version": auth_version,
        "email": email,
        "role": role,
        "admin_type": admin_type,
        "is_superadmin": is_superadmin,
        "is_active": is_active,
        "is_verified": is_verified,
        "phone_number": phone_number,
        "is_phone_verified": is_phone_verified,
        "status": status,
        "first_name": first_name,
        "last_name": last_name,
        "last_login_at": last_login_at.isoformat() if last_login_at else None,
        "created_at": created_at.isoformat() if created_at else None,
        "updated_at": updated_at.isoformat() if updated_at else None,
        "exp": int(expire_at.timestamp()),
    }
    return _create_signed_token(payload)


def create_refresh_token(
    *, subject: str, token_id: str, expires_delta: timedelta | None = None
) -> tuple[str, datetime]:
    expire_at = datetime.now(UTC) + (expires_delta or timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS))
    payload = {
        "sub": subject,
        "jti": token_id,
        "type": "refresh",
        "exp": int(expire_at.timestamp()),
    }
    return _create_signed_token(payload), expire_at


def decode_access_token(token: str) -> dict:
    validate_auth_secret()
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
