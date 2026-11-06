from datetime import UTC, datetime, timedelta

from sqlalchemy import case
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.core.exceptions import AppError
from app.core.security import hash_token
from app.models.auth_rate_limit import AuthRateLimit


class AuthRateLimitRepository:
    def __init__(self, db):
        self.db = db

    def consume(self, scope, identifier, *, limit, window_seconds, now=None):
        """Atomic across workers; commit denied attempts as well as allowed ones."""
        now = now or datetime.now(UTC)
        limit, window_seconds = max(1, limit), max(1, window_seconds)
        key = hash_token(f"{scope}:{identifier}")
        insert = postgres_insert if self.db.bind.dialect.name == "postgresql" else sqlite_insert
        expired = AuthRateLimit.resets_at <= now
        statement = (
            insert(AuthRateLimit)
            .values(bucket_key=key, attempts=1, resets_at=now + timedelta(seconds=window_seconds))
            .on_conflict_do_update(
                index_elements=[AuthRateLimit.bucket_key],
                set_={
                    "attempts": case(
                        (expired, 1),
                        (AuthRateLimit.attempts >= limit, limit + 1),
                        else_=AuthRateLimit.attempts + 1,
                    ),
                    "resets_at": case(
                        (expired, now + timedelta(seconds=window_seconds)),
                        else_=AuthRateLimit.resets_at,
                    ),
                },
            )
            .returning(AuthRateLimit.attempts, AuthRateLimit.resets_at)
        )
        try:
            attempts, resets_at = self.db.execute(statement).one()
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        if attempts > limit:
            resets_at = resets_at.replace(tzinfo=UTC) if resets_at.tzinfo is None else resets_at
            raise AppError(
                "Too many authentication attempts; try again later",
                status_code=429,
                error_code="auth_rate_limited",
                data={"retry_after": max(1, int((resets_at - now).total_seconds()))},
            )

    def prune_expired(self, now=None):
        self.db.query(AuthRateLimit).filter(
            AuthRateLimit.resets_at < (now or datetime.now(UTC)) - timedelta(days=1)
        ).delete(synchronize_session=False)
        self.db.commit()
