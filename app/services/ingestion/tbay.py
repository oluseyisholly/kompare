from __future__ import annotations

import re
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

import httpx

from app.models.enums import ProviderName
from app.core.logger import logger


def number(value, *, positive=False):
    try:
        result = Decimal(str(value))
        if not result.is_finite() or result < 0 or (positive and result == 0):
            raise ValueError()
        return result
    except (ValueError, InvalidOperation) as exc:
        raise ValueError("Tbay returned an invalid numeric offer field") from exc


def normalize_offer(category, offer, points_rate):
    if offer.get("tradeCoin") != "Points":
        raise ValueError("Unsupported Tbay settlement unit")
    minimum = number(offer.get("minTrade"))
    maximum = number(offer.get("maxTrade"), positive=True)
    if minimum > maximum:
        raise ValueError("Invalid Tbay amount range")
    denominations = [str(number(v, positive=True)) for v in (offer.get("fixTrade") or "").split("||") if v]
    tags = offer.get("tagList") or []
    if not isinstance(tags, list) or any(not isinstance(x, str) for x in tags):
        raise ValueError("Invalid Tbay offer tags")
    multiples = re.search(r"multiples of\s+(\d+)", " ".join(tags), re.I)
    step = str(number(multiples.group(1), positive=True)) if multiples else "1"
    brand = re.sub(r"\s+gift\s*card$", "", str(category.get("nameSimple") or category.get("name") or ""), flags=re.I).strip()
    code = re.sub(r"[^A-Z0-9]+", "_", brand.upper().replace("&", "AND")).strip("_")
    if not code:
        raise ValueError("Tbay card brand is missing")
    rate = number(offer.get("discount"), positive=True) * points_rate
    return {
        "asset_code": code, "brand": brand, "external_id": offer["code"],
        "name": f'{brand} {offer["tradeCurrency"]} ({minimum}-{maximum}) — {offer["code"]}',
        "source_currency": offer["tradeCurrency"], "minimum": minimum, "maximum": maximum,
        "rate": rate, "active": str(offer.get("status")) == "1",
        "terms": offer.get("explain"),
        "conditions": {"seller_id": offer.get("userId"), "allowed_denominations": denominations,
                       "amount_step": step, "whole_units_only": True, "tags": tags,
                       "terms": offer.get("explain"), "calculation_basis": "public_discount_times_points_ngn",
                       "is_estimate": True},
    }


class TbayIngestionService:
    def __init__(self, *, adapter, catalog_repository, fetch_run_repository):
        self.adapter = adapter
        self.catalog_repository = catalog_repository
        self.fetch_run_repository = fetch_run_repository

    async def ingest_market_data(self):
        return await self.ingest()

    async def ingest(self):
        run = self.fetch_run_repository.create_pending(ProviderName.TBAY)
        result = {"fetch_run_id": run.id, "categories_processed": 0, "scopes_completed": 0,
                  "variants_processed": 0, "rates_created": 0, "raw_records_created": 0,
                  "failed_scopes": []}
        last_error = None

        def failed(category_id, currency, exc):
            result["failed_scopes"].append({"category_id": category_id, "currency": currency,
                                           "error": str(exc), "details": getattr(exc, "data", {})})
            logger.warning("Tbay scope failed category=%s currency=%s: %s", category_id, currency, exc)

        try:
            async with httpx.AsyncClient() as client:
                categories = await self.adapter.fetch_categories(client=client)
                if not categories:
                    raise ValueError("Empty Tbay catalog; existing data retained")
                points_payload = await self.adapter.fetch_points_rate("NGN", client=client)
                points = number(points_payload["mid"], positive=True)
                for category in categories:
                    category_id = category.get("code")
                    if not isinstance(category_id, str) or not category_id:
                        raise ValueError("Missing Tbay category identifier")
                    try:
                        currencies = await self.adapter.fetch_currencies(category_id, client=client)
                    except Exception as exc:
                        last_error = exc
                        failed(category_id, None, exc)
                        continue
                    result["categories_processed"] += 1
                    seen = set()
                    for currency in currencies:
                        symbol = currency.get("currency")
                        if not isinstance(symbol, str) or not symbol:
                            last_error = ValueError("Missing Tbay currency identifier")
                            failed(category_id, None, last_error)
                            continue
                        if symbol in seen:
                            continue
                        seen.add(symbol)
                        try:
                            offers = await self.adapter.fetch_offers(category_id, symbol, client=client)
                            batch = {"category": category, "currency": symbol, "offers": offers,
                                     "captured_at": datetime.now(UTC),
                                     "normalized": [normalize_offer(category, row, points) for row in offers]}
                            saved = self.catalog_repository.persist(
                                run=run, categories=[category], batches=[batch], points_payload=points_payload,
                                source_url=self.adapter.source_url("806206"), finalize=False)
                        except Exception as exc:
                            last_error = exc
                            failed(category_id, symbol, exc)
                            continue
                        result["scopes_completed"] += 1
                        for key in ("variants_processed", "rates_created", "raw_records_created"):
                            result[key] += saved[key]
                        logger.info("Tbay scope saved category=%s currency=%s offers=%s", category_id, symbol, len(offers))
            run.metadata_json = result.copy()
            run.records_fetched = result["variants_processed"]
            if not result["scopes_completed"]:
                raise last_error or ValueError("No Tbay scopes completed; existing data retained")
            if result["failed_scopes"]:
                # Existing status enum has no PARTIAL value. Do not report a
                # partially completed run as a fully successful ingestion.
                result["status"] = "partial"
                run.metadata_json = result.copy()
                self.fetch_run_repository.mark_failed(run, error_message=(
                    f'Partial ingestion: {result["scopes_completed"]} scopes saved, '
                    f'{len(result["failed_scopes"])} failed; see metadata_json'))
            else:
                result["status"] = "success"
                run.metadata_json = result.copy()
                self.fetch_run_repository.mark_success(run, records_fetched=result["variants_processed"])
            return result
        except Exception as exc:
            result["status"] = "failed"
            run.metadata_json = result.copy()
            run.records_fetched = result["variants_processed"]
            self.fetch_run_repository.mark_failed(run, error_message=str(exc))
            raise
