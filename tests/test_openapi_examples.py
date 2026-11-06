"""Validate the examples Swagger serves against the actual request models, offline."""

import importlib
import inspect
import pkgutil

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

import app.schemas as schema_modules
from app.main import app


def request_models():
    models = {}
    for module in pkgutil.iter_modules(schema_modules.__path__):
        for name, model in inspect.getmembers(
            importlib.import_module(f"app.schemas.{module.name}")
        ):
            if inspect.isclass(model) and issubclass(model, BaseModel):
                models[name] = model
    return models


MODELS = request_models()
SCHEMA = app.openapi()
REQUESTS = [
    (path, method, media)
    for path, operations in SCHEMA["paths"].items()
    for method, operation in operations.items()
    for media in operation.get("requestBody", {}).get("content", {}).values()
]


@pytest.mark.parametrize("path,method,media", REQUESTS, ids=[f"{m} {p}" for p, m, _ in REQUESTS])
def test_every_request_body_has_valid_explicit_examples(path, method, media):
    name = media["schema"]["$ref"].rsplit("/", 1)[1]
    definition = SCHEMA["components"]["schemas"][name]
    examples = definition.get("examples", [])
    assert examples, f"{method} {path} needs a readable example"
    model = MODELS[name]
    for example in examples:
        # Pydantic defaults to ignoring extras on several legacy models. Catch typos as well.
        assert example.keys() <= model.model_fields.keys()
        model.model_validate(example)
    for example in media.get("examples", {}).values():
        assert example["value"] in examples
        model.model_validate(example["value"])


def test_swagger_serves_readable_user_emails_in_requests_and_responses():
    # Avoid lifespan: generating documentation needs neither a database nor the scheduler.
    response = TestClient(app).get("/openapi.json")
    assert response.status_code == 200
    definitions = response.json()["components"]["schemas"]
    for name, definition in definitions.items():
        email = definition.get("properties", {}).get("email")
        if email:
            assert email["examples"] == ["user@example.com"], name
    for name in (
        "UserRegisterRequest",
        "LoginRequest",
        "VerifyEmailRequest",
        "ResendEmailVerificationOtpRequest",
    ):
        assert definitions[name]["examples"][0]["email"] == "user@example.com"
    assert definitions["AdminRegisterRequest"]["examples"][0]["email"] == "admin@example.com"


def test_fx_swagger_examples_use_shared_contract_and_exclusive_quote_amounts():
    conversion = SCHEMA["paths"]["/fx/convert"]["post"]["requestBody"]["content"][
        "application/json"
    ]
    assert set(conversion["examples"]) == {"wise", "flutterwave", "fincra"}
    for provider, example in conversion["examples"].items():
        value = example["value"]
        assert value["provider"] == provider
        assert set(value) == {"provider", "source_currency", "target_currency", "source_amount"}
    quote = SCHEMA["paths"]["/fx/{provider}/quotes"]["post"]["requestBody"]["content"][
        "application/json"
    ]
    assert set(quote["examples"]) == {"source_amount", "target_amount"}
    for amount, example in quote["examples"].items():
        assert set(example["value"]) == {"source_currency", "target_currency", amount}
    assert "Wise only" in SCHEMA["paths"]["/fx/{provider}/quotes"]["post"]["description"]


def test_documented_schedule_does_not_enable_ingestion_by_default():
    example = SCHEMA["components"]["schemas"]["IngestionScheduleUpsert"]["examples"][0]
    assert example["is_enabled"] is False
    assert example["interval_minutes"] > 0


def test_credential_examples_explain_which_real_values_are_required():
    schemas = SCHEMA["components"]["schemas"]
    assert (
        "real refresh_token"
        in schemas["RefreshTokenRequest"]["properties"]["refresh_token"]["description"]
    )
    assert "sent to your email" in schemas["VerifyEmailRequest"]["properties"]["otp"]["description"]
