"""Collect complete paginated snapshots; frontend requests never invoke this."""

import json
from datetime import UTC, datetime

import httpx

from app.adapters.fx.fincra import EXCLUDED_DIGITAL_ASSETS, FincraAdapter, failure
from app.core.exceptions import AppError
from app.models.enums import MarketCategory, ProviderName, RawSourceType
from app.repositories.fetch_run import FetchRunRepository
from app.repositories.fincra import FincraRepository
from app.repositories.provider import ProviderRepository
from app.repositories.raw_record import RawRecordRepository


class FincraIngestionService:
    def __init__(self, db, *, adapter=None):
        self.db = db
        self.adapter = adapter or FincraAdapter()
        self.repository = FincraRepository(db)
        self.runs = FetchRunRepository(db)
        self.raw = RawRecordRepository(db)

    async def ingest_market_data(self):
        provider = ProviderRepository(self.db).get_or_create_by_slug(
            slug="fincra",
            name="Fincra",
            category=MarketCategory.FX,
            website_url="https://fincra.com",
            has_adapter=True,
            metadata_json={
                "rate_classification": "treasury_rate",
                "currency_discovery": "observed_rate_pairs",
            },
        )
        if provider.category != MarketCategory.FX:
            raise ValueError("Fincra provider category conflict")
        provider_id = provider.id
        run = self.runs.create_pending(ProviderName.FINCRA)
        run_id = run.id
        result = {
            "fetch_run_id": run_id,
            "job_type": "market_data",
            "rates_observed": 0,
            "pages_fetched": 0,
            "rates_received": 0,
            "rates_excluded": 0,
            "excluded_rates": [],
            "snapshot_complete": False,
        }
        state = self.adapter.configuration_status()
        if state != "configured":
            result.update(status="skipped", configuration_status=state)
            run.metadata_json = result.copy()
            self.runs.mark_failed(run, error_message=f"Fincra ingestion skipped: {state}")
            return result
        try:
            records, seen, expected, page = [], set(), None, 1
            async with httpx.AsyncClient() as client:
                while True:
                    response = await self.adapter.fetch_page(page, client=client)
                    raw_id = self.raw.create(
                        provider=ProviderName.FINCRA,
                        fetch_run_id=run_id,
                        source_type=RawSourceType.API,
                        source_url=response.source_url,
                        payload={
                            "page": page,
                            "status_code": response.status_code,
                            "response": json.loads(json.dumps(response.payload, default=str)),
                        },
                        raw_text=response.raw_text,
                    ).id
                    result["pages_fetched"] += 1
                    try:
                        items, paging = self.adapter.parse_page(response, page)
                    except AppError as exc:
                        exc.data.update(raw_record_id=raw_id, fetch_run_id=run_id)
                        raise
                    shape = (paging.totalItems, paging.totalPages, paging.perPage)
                    if expected is not None and shape != expected:
                        raise failure(
                            "Fincra pagination changed during collection; retry the snapshot"
                        )
                    expected = shape
                    result["rates_received"] += len(items)
                    for item in items:
                        key = (item.baseCurrency, item.quoteCurrency, item.side)
                        if key in seen:
                            raise failure("Fincra repeated a pair/side; snapshot rejected")
                        seen.add(key)
                        if {item.baseCurrency, item.quoteCurrency} & EXCLUDED_DIGITAL_ASSETS:
                            result["rates_excluded"] += 1
                            result["excluded_rates"].append(
                                {
                                    "base_currency": item.baseCurrency,
                                    "quote_currency": item.quoteCurrency,
                                    "side": item.side,
                                    "page": page,
                                    "raw_record_id": raw_id,
                                    "reason": "digital_asset_outside_fx_scope",
                                }
                            )
                            continue
                        records.append((item, raw_id, response.source_url, paging.timestamp))
                    if page == paging.totalPages:
                        break
                    page += 1
            # Pagination counts the original provider rows, before deliberate exclusions.
            if result["rates_received"] != expected[0]:
                raise failure("Fincra snapshot count did not match pagination")
            if not records:
                raise failure(
                    "Fincra snapshot contains no eligible FX rates; current rates retained"
                )
            result["snapshot_complete"] = True
            result.update(
                self.repository.persist(
                    records,
                    provider_id=provider_id,
                    run_id=run_id,
                    captured_at=datetime.now(UTC),
                )
            )
            run.metadata_json = result.copy()
            if result["status"] == "skipped":
                self.runs.mark_failed(
                    run, error_message="Fincra snapshot superseded by newer ingestion"
                )
            else:
                self.runs.mark_success(run, records_fetched=result["rates_observed"])
            return result
        except Exception as exc:
            self.db.rollback()
            error = (
                exc if isinstance(exc, AppError) else failure("Fincra data could not be processed")
            )
            result.update(
                status="failed",
                error_code=error.error_code,
                error_message=error.message,
                error_details=error.data,
            )
            run.metadata_json = result.copy()
            self.runs.mark_failed(run, error_message=error.message)
            raise error from None
