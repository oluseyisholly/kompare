from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.exceptions import AppError

router = APIRouter(tags=["health"])


@router.get("/health/live", include_in_schema=False)
def live():
    return {"status": "ok"}


@router.get("/health/ready", include_in_schema=False)
def ready(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        from pathlib import Path

        from alembic.config import Config
        from alembic.script import ScriptDirectory

        path = Path(__file__).resolve().parents[1] / "alembic.ini"
        expected = ScriptDirectory.from_config(Config(str(path))).get_heads()
        revisions = set(db.execute(text("SELECT version_num FROM alembic_version")).scalars())
        if revisions != set(expected):
            raise ValueError("Pending database migrations")
    except Exception:
        db.rollback()
        raise AppError(
            "Service is not ready", status_code=503, error_code="service_not_ready"
        ) from None
    return {"status": "ready"}
