from datetime import UTC, datetime

import httpx

from app.adapters.fx.flutterwave import FlutterwaveAdapter, json_safe
from app.core.exceptions import AppError
from app.models.enums import MarketCategory, ProviderName, RawSourceType
from app.repositories.fetch_run import FetchRunRepository
from app.repositories.fx import FxRepository
from app.repositories.provider import ProviderRepository
from app.repositories.raw_record import RawRecordRepository


class FlutterwaveIngestionService:
    def __init__(self, db, *, adapter=None):
        self.db = db
        self.adapter = adapter or FlutterwaveAdapter()
        self.repository = FxRepository(db)
        self.runs = FetchRunRepository(db)
        self.raw_records = RawRecordRepository(db)

    def register_provider(self):
        repository = ProviderRepository(self.db)
        metadata = {
            "rate_classification": "transfer_rate_observation",
            "currency_discovery": "not_implemented",
        }
        provider = repository.get_or_create_by_slug(
            slug="flutterwave",
            name="Flutterwave",
            category=MarketCategory.FX,
            website_url="https://flutterwave.com",
            has_adapter=True,
            metadata_json=metadata,
        )
        if provider.category != MarketCategory.FX:
            raise ValueError("Existing Flutterwave provider is not categorized as FX")
        merged = {**(provider.metadata_json or {}), **metadata}
        if merged != provider.metadata_json or not provider.has_adapter:
            provider = repository.update(provider, has_adapter=True, metadata_json=merged)
        return provider

    async def ingest_market_data(self):
        provider_id = self.register_provider().id
        run = self.runs.create_pending(ProviderName.FLUTTERWAVE)
        run_id = run.id
        result = {
            "fetch_run_id": run_id,
            "job_type": "market_data",
            "classification": "transfer_rate_observation",
            "rates_observed": 0,
            "observations_created": 0,
            "extraction_failures": [],
        }
        configuration = self.adapter.configuration_status()
        if configuration != "configured":
            return self._skip(run, result, configuration)
        scenarios, failures = self.adapter.scenarios()
        result["extraction_failures"].extend(failures)
        if not scenarios:
            return self._skip(run, result, "invalid_scenarios")
        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
                for scenario in scenarios:
                    try:
                        response = await self.adapter.fetch_rate(scenario, client=client)
                        captured_at = datetime.now(UTC)
                        raw_id = self.raw_records.create(
                            provider=ProviderName.FLUTTERWAVE,
                            fetch_run_id=run_id,
                            source_type=RawSourceType.API,
                            source_url=response.source_url,
                            payload={
                                "request": scenario.model_dump(mode="json"),
                                "status_code": response.status_code,
                                "response": json_safe(response.payload),
                            },
                            raw_text=response.raw_text,
                        ).id
                        record = self.adapter.parse_rate(
                            response,
                            scenario=scenario,
                            captured_at=captured_at,
                        )
                        _, created = self.repository.save_transfer_rate(
                            record,
                            provider_id=provider_id,
                            fetch_run_id=run_id,
                            raw_record_id=raw_id,
                        )
                        result["rates_observed"] += 1
                        result["observations_created"] += int(created)
                    except Exception as exc:
                        self.db.rollback()
                        result["extraction_failures"].append(
                            {
                                **scenario.model_dump(mode="json"),
                                "error": exc.message
                                if isinstance(exc, AppError)
                                else "Flutterwave response could not be processed",
                                "error_code": exc.error_code
                                if isinstance(exc, AppError)
                                else "flutterwave_invalid_response",
                                **(exc.data if isinstance(exc, AppError) else {}),
                            }
                        )
            result["status"] = (
                "partial"
                if result["extraction_failures"] and result["rates_observed"]
                else "failed"
                if result["extraction_failures"]
                else "success"
            )
            run.metadata_json = result.copy()
            run.records_fetched = result["rates_observed"]
            if result["extraction_failures"]:
                self.runs.mark_failed(
                    run, error_message="Flutterwave scenario failures; see metadata"
                )
            else:
                self.runs.mark_success(run, records_fetched=result["rates_observed"])
            return result
        except Exception:
            self.db.rollback()
            result["status"] = "failed"
            run.metadata_json = result.copy()
            self.runs.mark_failed(run, error_message="Flutterwave ingestion could not be completed")
            raise

    def _skip(self, run, result, configuration):
        result.update(status="skipped", configuration_status=configuration)
        run.metadata_json = result.copy()
        self.runs.mark_failed(run, error_message=f"Flutterwave ingestion skipped: {configuration}")
        return result
