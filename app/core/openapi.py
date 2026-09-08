"""Swagger layers: general features, shared categories, provider-only routes."""
from fastapi import FastAPI
from fastapi.routing import APIRoute


TAGS = {
    "Authentication": "Registration, login and session management.",
    "Providers": "General provider listing and profile management.",
    "Ingestion": "Shared ingestion schedules, execution history and source records.",
    "KYC": "Verification requirements and KYC reports across providers.",
    "Reports": "General provider summaries and reports.",
    "Crypto": "Shared crypto assets, quotes, calculations and bootstrap operations. Select a provider using the path parameter.",
    "Gift Cards": "Shared gift-card variants, rates and calculations. Select a provider using the path parameter.",
    "Quidax": "Operations specific to Quidax.",
    "Busha": "Operations specific to Busha.",
    "Cardtonic": "Operations specific to Cardtonic.",
    "Tbay": "Operations specific to Tbay.",
}


def documentation_group(path: str) -> str | None:
    if path.startswith("/auth/"):
        return "Authentication"
    for slug, name in (("quidax", "Quidax"), ("busha", "Busha"),
                       ("cardtonic", "Cardtonic"), ("tbay", "Tbay")):
        if path.startswith(f"/{slug}/"):
            return name
    if "/crypto/" in path or path.endswith("/bootstrap"):
        return "Crypto"
    if "/giftcards/" in path:
        return "Gift Cards"
    if any(part in path.split("/") for part in ("kyc", "kyc-summary")):
        return "KYC"
    if any(part in path.split("/") for part in (
        "ingestion-schedules", "fetch-runs", "raw-records", "ingestion-health", "raw-activity",
    )):
        return "Ingestion"
    if path.startswith("/reports/"):
        return "Reports"
    if path.startswith("/providers"):
        return "Providers"
    return None


def register_provider_documentation(app: FastAPI) -> None:
    """Use native OpenAPI tags without expanding or modifying endpoint paths."""
    used = set()
    for route in app.routes:
        if not isinstance(route, APIRoute) or not route.include_in_schema:
            continue
        group = documentation_group(route.path)
        if group:
            route.tags = [group]
            used.add(group)
    app.openapi_tags = [{"name": name, "description": description}
                        for name, description in TAGS.items() if name in used]
    app.openapi_schema = None
