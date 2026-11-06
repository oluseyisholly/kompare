import os
import runpy
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from app.core import security

CONFIG_PATH = Path(__file__).resolve().parents[1] / "app" / "core" / "config.py"


@pytest.mark.parametrize("secret", [None, "", "   ", "kompare-dev-secret", "change-me"])
def test_shared_config_loads_without_authentication_secret(secret):
    environment = {} if secret is None else {"SECRET_KEY": secret}
    with patch.dict(os.environ, environment, clear=True), patch("dotenv.load_dotenv"):
        settings = runpy.run_path(str(CONFIG_PATH))
    assert settings["SECRET_KEY"] == (secret or "")


@pytest.mark.parametrize("secret", ["", "   ", "kompare-dev-secret", "change-me"])
def test_authentication_rejects_missing_or_placeholder_secret(secret):
    with patch.object(security, "SECRET_KEY", secret):
        with pytest.raises(ValueError, match="SECRET_KEY must be configured"):
            security._create_signed_token({"sub": "1"})
        with pytest.raises(ValueError, match="SECRET_KEY must be configured"):
            security.decode_access_token("payload.signature")


def test_config_preserves_explicit_secret():
    secret = "test-only-explicit-signing-key-7f81a264"
    with patch.dict(os.environ, {"SECRET_KEY": secret}, clear=True), patch("dotenv.load_dotenv"):
        settings = runpy.run_path(str(CONFIG_PATH))
    assert settings["SECRET_KEY"] == secret
    with patch.object(security, "SECRET_KEY", secret):
        token = security._create_signed_token({"sub": "1", "exp": 4102444800})
        assert security.decode_access_token(token)["sub"] == "1"


@pytest.mark.parametrize(
    "module",
    [
        "app.scripts.run_stanbic_ingestion",
        "app.scripts.run_fx_ingestion",
        "app.scripts.run_ingestion_worker",
    ],
)
def test_ingestion_cli_imports_without_secret(module):
    # A fresh process catches transitive imports; disable dotenv so a local key
    # cannot accidentally hide an import-time authentication dependency.
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import os, runpy, sys
from unittest.mock import patch
os.environ["SECRET_KEY"] = ""
module = sys.argv[1]
sys.argv = [module, "--help"]
with patch("dotenv.load_dotenv"):
    runpy.run_module(module, run_name="__main__")
""",
            module,
        ],
        cwd=CONFIG_PATH.parents[2],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "usage:" in result.stdout


def test_api_startup_validates_secret_before_starting_scheduler():
    import asyncio
    from unittest.mock import AsyncMock

    from app.main import scheduler, start_scheduler

    with (
        patch.object(security, "SECRET_KEY", ""),
        patch.object(scheduler, "start", new_callable=AsyncMock) as start,
    ):
        with pytest.raises(ValueError, match="SECRET_KEY must be configured"):
            asyncio.run(start_scheduler())
        start.assert_not_awaited()
