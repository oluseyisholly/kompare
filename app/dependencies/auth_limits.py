"""Apply shared account/IP limits only at authentication API boundaries."""

from fastapi import Request
from sqlalchemy.orm import Session

from app.core import config
from app.repositories.auth_rate_limit import AuthRateLimitRepository


def limit_auth_request(request: Request, db: Session, *, action, account):
    repository = AuthRateLimitRepository(db)
    # Trust the ASGI peer only. Forwarded-header trust belongs to the deployment proxy.
    ip = request.client.host if request.client else "unknown"
    if action == "login":
        repository.consume(
            "login:ip",
            ip,
            limit=config.AUTH_LOGIN_IP_LIMIT,
            window_seconds=config.AUTH_LOGIN_WINDOW_SECONDS,
        )
        repository.consume(
            "login:account",
            account.lower(),
            limit=config.AUTH_LOGIN_ACCOUNT_LIMIT,
            window_seconds=config.AUTH_LOGIN_WINDOW_SECONDS,
        )
    elif action in {"verify", "reset_password"}:
        repository.consume(
            "otp:ip",
            ip,
            limit=config.AUTH_OTP_IP_LIMIT,
            window_seconds=config.AUTH_LOGIN_WINDOW_SECONDS,
        )
    else:
        if action in {"resend", "forgot_password"}:
            repository.consume(
                f"{action}:cooldown",
                account.lower(),
                limit=1,
                window_seconds=config.AUTH_OTP_RESEND_COOLDOWN_SECONDS,
            )
        repository.consume(
            f"{action}:ip", ip, limit=config.AUTH_EMAIL_IP_LIMIT, window_seconds=3600
        )
        repository.consume(
            f"{action}:account",
            account.lower(),
            limit=config.AUTH_EMAIL_ACCOUNT_LIMIT,
            window_seconds=3600,
        )
