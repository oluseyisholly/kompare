from datetime import UTC, datetime
from time import perf_counter

import httpx

from app.adapters.mutual_fund.united_capital import UnitedCapitalAdapter, source_today
from app.core.config import UNITED_CAPITAL_STALE_AFTER_DAYS
from app.core.logger import logger
from app.models.enums import MarketCategory, ProviderName, RawSourceType
from app.models.provider import Provider
from app.repositories.fetch_run import FetchRunRepository
from app.repositories.mutual_fund import MutualFundRepository
from app.repositories.provider import ProviderRepository
from app.repositories.raw_record import RawRecordRepository


class UnitedCapitalIngestionService:
    def __init__(self, db, *, adapter=None, stale_after_days=UNITED_CAPITAL_STALE_AFTER_DAYS):
        if stale_after_days < 0:
            raise ValueError("United Capital staleness threshold must be non-negative")
        self.db = db
        self.adapter = adapter or UnitedCapitalAdapter()
        self.stale_after_days = stale_after_days
        self.repository = MutualFundRepository(db)
        self.fetch_runs = FetchRunRepository(db)
        self.raw_records = RawRecordRepository(db)

    async def ingest_market_data(self):
        started = perf_counter()
        logger.info("United Capital: connecting to database and preparing ingestion run")
        provider = ProviderRepository(self.db).get_or_create_by_slug(
            slug="united_capital",
            name="United Capital Asset Management",
            category=MarketCategory.MUTUAL_FUND,
            has_adapter=True,
            website_url="https://unitedcapitalplcgroup.com/asset-management/",
        )
        provider_id = provider.id
        run = self.fetch_runs.create_pending(ProviderName.UNITED_CAPITAL)
        run_id = run.id
        failures, warnings = [], []
        result = {
            "fetch_run_id": run_id,
            "funds_parsed": 0,
            "snapshots_created": 0,
            "extraction_failures": failures,
            "warnings": warnings,
            "source_dates": {},
            "stale_after_days": self.stale_after_days,
            "latest_data": [],
        }
        try:
            stage_started = perf_counter()
            logger.info("United Capital: fetching %s", self.adapter.source_url)
            async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
                html = await self.adapter.fetch_page(client=client)
            logger.info("United Capital: fetched page in %.2fs", perf_counter() - stage_started)
            captured_at = datetime.now(UTC)
            today = source_today()
            logger.info("United Capital: saving source HTML")
            raw = self.raw_records.create(
                provider=ProviderName.UNITED_CAPITAL,
                fetch_run_id=run_id,
                source_type=RawSourceType.HTML,
                source_url=self.adapter.source_url,
                payload={"content": html},
                raw_text=html,
            )
            # Commits expire ORM objects. Cache IDs so later funds do not reload
            # the full source HTML/JSON just to read raw.id again.
            raw_id = raw.id
            stage_started = perf_counter()
            logger.info("United Capital: parsing fund tables")
            extraction = self.adapter.parse(html, today=today)
            logger.info(
                "United Capital: parsed %d funds in %.2fs",
                len(extraction.records),
                perf_counter() - stage_started,
            )
            failures.extend(extraction.failures)
            warnings.extend(extraction.warnings)
            result["funds_parsed"] = len(extraction.records)
            # Persist parsed labels and unresolved values separately from financial columns.
            raw.payload = {
                "content": html,
                "source_context": extraction.source_context,
                "warnings": warnings.copy(),
                "extraction_failures": failures.copy(),
            }
            self.db.commit()
            for index, record in enumerate(extraction.records, start=1):
                observation = record.model_dump(mode="json")
                observation["published_metrics"] = extraction.source_context[record.code].get(
                    "published_metrics", []
                )
                observation["persistence_status"] = "pending"
                result["latest_data"].append(observation)
                age = (today - record.valuation_date).days
                freshness = {
                    "valuation_date": record.valuation_date.isoformat(),
                    "age_days": age,
                    "is_stale": age > self.stale_after_days,
                }
                result["source_dates"][record.code] = freshness
                if freshness["is_stale"]:
                    warnings.append({"code": record.code, "type": "stale_source", **freshness})
                try:
                    stage_started = perf_counter()
                    logger.info(
                        "United Capital: saving fund %d/%d (%s)",
                        index,
                        len(extraction.records),
                        record.code,
                    )
                    # Each fund commits independently. A rejected fund cannot roll back valid peers.
                    result["snapshots_created"] += self.repository.persist_dated(
                        provider_id=provider_id,
                        record=record,
                        fetch_run_id=run_id,
                        raw_record_id=raw_id,
                        captured_at=captured_at,
                    )
                    observation["persistence_status"] = "saved"
                    logger.info(
                        "United Capital: saved %s in %.2fs",
                        record.code,
                        perf_counter() - stage_started,
                    )
                except Exception as exc:
                    self.db.rollback()
                    observation["persistence_status"] = "failed"
                    failures.append({"code": record.code, "error": str(exc)})
            result["status"] = (
                ("partial" if result["snapshots_created"] else "failed") if failures else "success"
            )
            result["has_stale_data"] = any(d["is_stale"] for d in result["source_dates"].values())
            run.metadata_json = result.copy()
            run.records_fetched = result["snapshots_created"]
            if failures:
                self.fetch_runs.mark_failed(
                    run,
                    error_message=(
                        f"United Capital {result['status']}: {len(failures)} "
                        "extraction/persistence "
                        "failures; see run metadata"
                    ),
                )
                logger.warning("United Capital ingestion failures: %s", failures)
            else:
                self.fetch_runs.mark_success(run, records_fetched=result["snapshots_created"])
            logger.info(
                "United Capital: finished (%s), %d snapshots in %.2fs",
                result["status"],
                result["snapshots_created"],
                perf_counter() - started,
            )
            return result
        except Exception as exc:
            self.db.rollback()
            failures.append({"error": str(exc)})
            result["status"] = "failed"
            run.metadata_json = result.copy()
            self.fetch_runs.mark_failed(run, error_message=str(exc))
            logger.exception("United Capital ingestion failed")
            raise

    async def ingest_fund_details(self, *, fund_code=None):
        """Official product terms, independently scheduled from market data."""
        from decimal import Decimal

        from app.models.mutual_fund import MutualFund

        run = self.fetch_runs.create_pending(ProviderName.UNITED_CAPITAL)
        run_id = run.id
        result = {
            "fetch_run_id": run_id,
            "funds_processed": 0,
            "fields_updated": 0,
            "fields_observed": 0,
            "extraction_failures": [],
            "conflicts": [],
        }
        try:
            query = (
                self.db.query(MutualFund)
                .join(Provider, Provider.id == MutualFund.provider_id)
                .filter(Provider.slug == "united_capital")
            )
            if fund_code is not None:
                query = query.filter(MutualFund.code == fund_code)
            funds = [(f.code, f.currency) for f in query.order_by(MutualFund.code).all()]
            if not funds:
                raise ValueError(
                    "No matching United Capital catalogue: run market-data ingestion first"
                )
            async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
                for code, currency in funds:
                    url = None
                    try:
                        url = self.adapter.product_url(code)
                        logger.info("United Capital: fetching product details for %s", code)
                        html = await self.adapter.fetch_product_page(code, client=client)
                        raw = self.raw_records.create(
                            provider=ProviderName.UNITED_CAPITAL,
                            fetch_run_id=run_id,
                            source_type=RawSourceType.HTML,
                            source_url=url,
                            payload={"content": html},
                            raw_text=html,
                        )
                        raw_id = raw.id
                        observed_at = datetime.now(UTC).isoformat()
                        details, evidence, errors = self.adapter.parse_product_details(
                            html, code=code, currency=currency
                        )
                        result["extraction_failures"].extend(
                            dict(e, code=code, source_url=url) for e in errors
                        )
                        observations = {}
                        for field, value in details.model_dump(
                            exclude={"code", "currency"}, exclude_none=True
                        ).items():
                            observations[field] = [
                                {
                                    "value": str(value) if isinstance(value, Decimal) else value,
                                    "source_url": url,
                                    "raw_record_id": raw_id,
                                    "last_successful_observation_at": observed_at,
                                    "source_kind": "official",
                                    **evidence[field],
                                }
                            ]
                        saved = self.repository.update_details(
                            code=code, currency=currency, observations=observations
                        )
                        result["funds_processed"] += bool(saved["fields_observed"])
                        result["fields_updated"] += saved["fields_updated"]
                        result["fields_observed"] += saved["fields_observed"]
                        result["conflicts"].extend(saved["conflicts"])
                    except Exception as exc:
                        self.db.rollback()
                        result["extraction_failures"].append(
                            {"code": code, "source_url": url, "error": str(exc)}
                        )
            issues = result["extraction_failures"] or result["conflicts"]
            result["status"] = (
                ("partial" if result["fields_observed"] else "failed") if issues else "success"
            )
            run.metadata_json = result.copy()
            run.records_fetched = result["funds_processed"]
            if issues:
                self.fetch_runs.mark_failed(
                    run, error_message=f"United Capital details {result['status']}; see metadata"
                )
            else:
                self.fetch_runs.mark_success(run, records_fetched=result["funds_processed"])
            return result
        except Exception as exc:
            self.db.rollback()
            result["status"] = "failed"
            result["extraction_failures"].append({"error": str(exc)})
            run.metadata_json = result.copy()
            self.fetch_runs.mark_failed(run, error_message=str(exc))
            raise
