from datetime import UTC, datetime

import httpx

from app.adapters.fx.wise import WiseAdapter, json_safe, wise_error
from app.core.exceptions import AppError
from app.models.enums import ProviderName, RawSourceType
from app.repositories.fetch_run import FetchRunRepository
from app.repositories.raw_record import RawRecordRepository
from app.repositories.wise import WiseRepository


class WiseIngestionService:
    def __init__(self, db, *, adapter=None):
        self.db = db
        self.adapter = adapter or WiseAdapter()
        self.repository = WiseRepository(db)
        self.runs = FetchRunRepository(db)
        self.raw_records = RawRecordRepository(db)

    def _capture(self, response, *, run_id, request=None):
        # No request headers or tokens. Retain responses before parsing or raising
        # provider errors; the adapter redacts any echoed configured credentials.
        raw = self.raw_records.create(
            provider=ProviderName.WISE,
            fetch_run_id=run_id,
            source_type=RawSourceType.API,
            source_url=response.source_url,
            payload={
                "response": json_safe(response.payload),
                "status_code": response.status_code,
                "request": request.model_dump(mode="json") if request else None,
            },
            raw_text=response.raw_text,
        )
        raw_id = raw.id
        self.adapter.check_response(response)
        return raw_id

    def _mark_failure(self, run, exc, *, job_type):
        self.db.rollback()
        error = (
            exc
            if isinstance(exc, AppError)
            else wise_error(
                "Wise returned data that could not be processed", "wise_invalid_response"
            )
        )
        run.metadata_json = {"job_type": job_type, "status": "failed", "error": error.error_code}
        self.runs.mark_failed(run, error_message=error.message)
        return error

    async def ingest_market_data(self):
        self.repository.register_provider()
        run = self.runs.create_pending(ProviderName.WISE)
        run_id = run.id
        if not self.adapter.token:
            result = {
                "fetch_run_id": run_id,
                "status": "skipped",
                "configuration_status": "missing_token",
                "rates_observed": 0,
                "job_type": "market_data",
            }
            # The existing run enum has no SKIPPED state; metadata retains that distinction.
            run.metadata_json = result.copy()
            self.runs.mark_failed(
                run, error_message="WISE_API_TOKEN is not configured; ingestion skipped"
            )
            return result
        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
                response = await self.adapter.fetch_rates(client=client)
            captured_at = datetime.now(UTC)
            raw_id = self._capture(response, run_id=run_id)
            records, failures = self.adapter.parse_rates(response.payload)
            if not records:
                raise ValueError("No valid Wise reference rates")
            persisted = self.repository.persist_rates(
                records,
                fetch_run_id=run_id,
                raw_record_id=raw_id,
                captured_at=captured_at,
                adapter=self.adapter,
            )
            failures.extend(persisted.pop("persistence_failures"))
            result = {
                "fetch_run_id": run_id,
                "job_type": "market_data",
                **persisted,
                "classification": "reference_rate",
                "extraction_failures": failures,
                "status": "partial"
                if failures and persisted["rates_observed"]
                else "failed"
                if failures
                else "success",
            }
            run.metadata_json = result.copy()
            run.records_fetched = persisted["rates_observed"]
            if failures:
                self.runs.mark_failed(
                    run, error_message="Wise reference rates partially unavailable; see metadata"
                )
            else:
                self.runs.mark_success(run, records_fetched=persisted["rates_observed"])
            return result
        except Exception as exc:
            raise self._mark_failure(run, exc, job_type="market_data") from None

    async def ingest_currencies(self):
        provider_id = self.repository.register_provider().id
        run = self.runs.create_pending(ProviderName.WISE)
        run_id = run.id
        if not self.adapter.token:
            result = {
                "fetch_run_id": run_id,
                "job_type": "currencies",
                "status": "skipped",
                "configuration_status": "missing_token",
                "currencies_observed": 0,
            }
            run.metadata_json = result.copy()
            self.runs.mark_failed(
                run, error_message="WISE_API_TOKEN is not configured; currencies skipped"
            )
            return result
        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
                response = await self.adapter.fetch_currencies(client=client)
            captured_at = datetime.now(UTC)
            raw_id = self._capture(response, run_id=run_id)
            records, failures = self.adapter.parse_currencies(response.payload)
            if not records:
                raise ValueError("No valid Wise currencies")
            if response.pagination_pending:
                failures.append({"error": "Currency snapshot has unretrieved pages"})
            if response.status_code != 200:
                failures.append(
                    {
                        "error": "Currency snapshot response is not a complete HTTP 200",
                        "provider_status": response.status_code,
                    }
                )
            # Wise documents a full, unpaginated array. A successful nonempty
            # array with zero parsing errors and no remaining pages is complete.
            snapshot_complete = not failures and len(records) == len(response.payload)
            persisted = self.repository.persist_currencies(
                records,
                provider_id=provider_id,
                source_url=response.source_url,
                captured_at=captured_at,
                fetch_run_id=run_id,
                raw_record_id=raw_id,
                snapshot_complete=snapshot_complete,
            )
            result = {
                "fetch_run_id": run_id,
                "job_type": "currencies",
                **persisted,
                "extraction_failures": failures,
                "status": "skipped"
                if persisted["superseded"]
                else "partial"
                if failures
                else "success",
            }
            run.metadata_json = result.copy()
            run.records_fetched = persisted["currencies_observed"]
            if persisted["superseded"]:
                result["skip_reason"] = "newer_currency_refresh_already_applied"
                run.metadata_json = result.copy()
                self.runs.mark_failed(
                    run, error_message="Currency refresh superseded by a newer stored refresh"
                )
            elif failures:
                self.runs.mark_failed(
                    run, error_message="Partial Wise currency extraction; see metadata"
                )
            else:
                self.runs.mark_success(run, records_fetched=persisted["currencies_observed"])
            return result
        except Exception as exc:
            raise self._mark_failure(run, exc, job_type="currencies") from None

    async def request_quote(self, request):
        provider_id = self.repository.register_provider().id
        run = self.runs.create_pending(ProviderName.WISE)
        run_id = run.id
        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
                response = await self.adapter.fetch_quote(request, client=client)
            captured_at = datetime.now(UTC)
            raw_id = self._capture(response, run_id=run_id, request=request)
            quote = self.adapter.parse_quote(
                response.payload,
                request=request,
                captured_at=captured_at,
                source_url=response.source_url,
            )
            quote.raw_record_id = raw_id
            quote.fetch_run_id = run_id
            saved = self.repository.save_quote(
                quote,
                provider_id=provider_id,
                raw_record_id=raw_id,
                fetch_run_id=run_id,
            )
            quote.id = saved.id
            run.metadata_json = {
                "job_type": "illustrative_quote",
                "classification": "amount_specific_historical_observation",
                "usable_as_fee_rule": False,
                "status": "success",
                "quote_id": saved.id,
                "payment_options": len(quote.payment_options),
            }
            self.runs.mark_success(run, records_fetched=1)
            return quote
        except Exception as exc:
            raise self._mark_failure(run, exc, job_type="illustrative_quote") from None
