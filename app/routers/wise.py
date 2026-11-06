"""Compatibility import. All provider-parameterized FX routes live in app.routers.fx."""

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.routers.fx import router
from app.services.wise import WiseService


def get_wise_service(db: Session = Depends(get_db)):
    return WiseService(db)


__all__ = ["router", "get_wise_service"]
