"""Keep offline FX tests independent of the developer's freshness setting."""

import pytest

from app.core import config


@pytest.fixture(autouse=True)
def fx_test_defaults(monkeypatch):
    monkeypatch.setattr(config, "FX_RATE_STALE_AFTER_SECONDS", 3600)


@pytest.fixture(autouse=True)
def auth_test_defaults(monkeypatch):
    # Tests explicitly opt in to non-production OTP behaviour.
    monkeypatch.setattr(config, "IS_PRODUCTION", True)
