"""Keep offline FX tests independent of the developer's freshness setting."""

import pytest

from app.core import config


@pytest.fixture(autouse=True)
def fx_test_defaults(monkeypatch):
    monkeypatch.setattr(config, "FX_RATE_STALE_AFTER_SECONDS", 3600)
