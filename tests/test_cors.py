import os
import runpy
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.core.cors import CorsFastAPI
from app.core.error_handlers import register_exception_handlers
from app.core.exceptions import AppError
from app.main import app


@pytest.mark.parametrize("origin", ["http://localhost:5173", "https://frontend.example.com"])
def test_any_origin_can_preflight_with_authorization_and_custom_headers(origin):
    response = TestClient(app).options(
        "/providers/wise",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "PATCH",
            "Access-Control-Request-Headers": "Authorization, Content-Type, X-Client-Id",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "*"
    assert "PATCH" in response.headers["access-control-allow-methods"]
    assert "DELETE" in response.headers["access-control-allow-methods"]
    assert response.headers["access-control-allow-headers"] == (
        "Authorization, Content-Type, X-Client-Id"
    )
    assert "access-control-allow-credentials" not in response.headers


def test_cors_does_not_bypass_authentication():
    response = TestClient(app).get("/auth/me", headers={"Origin": "https://frontend.example.com"})
    assert response.status_code == 401
    assert response.json()["data"]["error"] == "unauthorized"
    assert response.headers["access-control-allow-origin"] == "*"


def test_error_responses_and_retry_header_are_visible_to_browsers():
    application = CorsFastAPI()
    register_exception_handlers(application)

    @application.get("/limited")
    def limited():
        raise AppError("Too many attempts", status_code=429, data={"retry_after": 60})

    @application.get("/unexpected")
    def unexpected():
        raise RuntimeError("CORS test failure")

    client = TestClient(application, raise_server_exceptions=False)
    limited_response = client.get("/limited", headers={"Origin": "https://frontend.example.com"})
    assert limited_response.status_code == 429
    assert limited_response.headers["access-control-allow-origin"] == "*"
    assert limited_response.headers["retry-after"] == "60"
    assert "Retry-After" in limited_response.headers["access-control-expose-headers"]
    failure = client.get("/unexpected", headers={"Origin": "https://frontend.example.com"})
    assert failure.status_code == 500
    assert failure.json()["data"]["error"] == "internal_server_error"
    assert failure.headers["access-control-allow-origin"] == "*"


@pytest.mark.parametrize(
    "setting,expected",
    [
        (None, ["*"]),
        ("*", ["*"]),
        ("", []),
        (
            " https://one.example.com, https://two.example.com, ",
            ["https://one.example.com", "https://two.example.com"],
        ),
    ],
)
def test_origin_setting_supports_wildcard_or_explicit_list(setting, expected):
    environment = {} if setting is None else {"CORS_ALLOW_ORIGINS": setting}
    with patch.dict(os.environ, environment, clear=True), patch("dotenv.load_dotenv"):
        values = runpy.run_path(str(Path(__file__).resolve().parents[1] / "app/core/config.py"))
    assert values["CORS_ALLOW_ORIGINS"] == expected
