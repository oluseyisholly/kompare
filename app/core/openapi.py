"""Swagger layers: general features, shared categories, provider-only routes."""

from fastapi import FastAPI

TAGS = {
    "Authentication": "Registration, login and session management.",
    "Providers": "General provider listing and profile management.",
    "Provider Reviews": "Provider reviews, tips, comments, votes and moderation.",
    "Ingestion": "Shared ingestion schedules, execution history and source records.",
    "KYC": "Verification requirements and KYC reports across providers.",
    "Reports": "General provider summaries and reports.",
    "Crypto": (
        "Shared crypto assets, quotes, calculations and bootstrap operations. "
        "Select a provider using the path parameter."
    ),
    "Gift Cards": (
        "Shared gift-card variants, rates and calculations. "
        "Select a provider using the path parameter."
    ),
    "FX": "Stored FX rates and currencies, local conversions and admin harvesting diagnostics.",
    "Mutual Funds": "Fund catalogues and published valuation snapshots.",
    "Quidax": "Operations specific to Quidax.",
    "Busha": "Operations specific to Busha.",
    "Cardtonic": "Operations specific to Cardtonic.",
    "Tbay": "Operations specific to Tbay.",
}


def documentation_group(path: str) -> str | None:
    if path.startswith("/fx/"):
        return "FX"
    if path.startswith("/mutual-funds"):
        return "Mutual Funds"
    if path.startswith("/auth/"):
        return "Authentication"
    for slug, name in (
        ("quidax", "Quidax"),
        ("busha", "Busha"),
        ("cardtonic", "Cardtonic"),
        ("tbay", "Tbay"),
    ):
        if path.startswith(f"/{slug}/"):
            return name
    if "/crypto/" in path or path.endswith("/bootstrap"):
        return "Crypto"
    if "/giftcards/" in path:
        return "Gift Cards"
    if any(part in path.split("/") for part in ("kyc", "kyc-summary")):
        return "KYC"
    if any(
        part in path.split("/")
        for part in (
            "ingestion-schedules",
            "ingestion-jobs",
            "fetch-runs",
            "raw-records",
            "ingestion-health",
            "raw-activity",
        )
    ):
        return "Ingestion"
    if path.startswith("/reports/"):
        return "Reports"
    if path.startswith("/providers"):
        return "Providers"
    return None


def register_provider_documentation(app: FastAPI) -> None:
    """Tag the public generated schema, including lazily included routers."""
    original_openapi = app.openapi

    def grouped_openapi():
        if app.openapi_schema is not None:
            return app.openapi_schema
        schema = original_openapi()
        used = set()
        for path, operations in schema.get("paths", {}).items():
            for method, operation in operations.items():
                if method in {"get", "post", "put", "patch", "delete", "head", "options"}:
                    # Reviews span provider, review and admin URLs; retain their router group.
                    group = (
                        "Provider Reviews"
                        if "Provider Reviews" in operation.get("tags", [])
                        else documentation_group(path)
                    )
                    if group is None:
                        continue
                    operation["tags"] = [group]
                    used.add(group)
        schema["tags"] = [
            {"name": name, "description": description}
            for name, description in TAGS.items()
            if name in used
        ]
        app.openapi_schema = schema
        return schema

    app.openapi_schema = None
    app.openapi = grouped_openapi
