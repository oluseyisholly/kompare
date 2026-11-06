from datetime import UTC, datetime
from decimal import Decimal

import httpx

from app.adapters.mutual_fund.stanbic import StanbicAdapter
from app.core.logger import logger
from app.models.enums import ProviderName, RawSourceType
from app.repositories.fetch_run import FetchRunRepository
from app.repositories.mutual_fund import MutualFundRepository
from app.repositories.raw_record import RawRecordRepository


class StanbicIngestionService:
    def __init__(self, db, *, adapter=None):
        self.db = db
        self.adapter = adapter or StanbicAdapter()
        self.repository = MutualFundRepository(db)
        self.fetch_runs = FetchRunRepository(db)
        self.raw_records = RawRecordRepository(db)

    async def ingest_market_data(self):
        provider = self.repository.register_stanbic()
        run = self.fetch_runs.create_pending(ProviderName.STANBIC)
        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
                html = await self.adapter.fetch_page(client=client)
            captured_at = datetime.now(UTC)
            raw = self.raw_records.create(
                provider=ProviderName.STANBIC,
                fetch_run_id=run.id,
                source_type=RawSourceType.HTML,
                source_url=self.adapter.source_url,
                payload={"content": html},
                raw_text=html,
            )
            records, failures = self.adapter.parse(html)
            if not records:
                raise ValueError(f"Stanbic extraction failed: no valid funds; {failures}")
            count = self.repository.persist(
                provider_id=provider.id,
                records=records,
                fetch_run_id=run.id,
                raw_record_id=raw.id,
                captured_at=captured_at,
            )
            result = {
                "fetch_run_id": run.id,
                "funds_parsed": len(records),
                "snapshots_created": count,
                "extraction_failures": failures,
                "status": "partial" if failures else "success",
            }
            run.metadata_json = result.copy()
            if failures:
                run.records_fetched = len(records)
                self.fetch_runs.mark_failed(run, error_message=f"Partial extraction: {failures}")
                logger.warning("Stanbic partial extraction: %s", failures)
            else:
                self.fetch_runs.mark_success(run, records_fetched=len(records))
            return result
        except Exception as exc:
            self.db.rollback()
            self.fetch_runs.mark_failed(run, error_message=str(exc))
            logger.exception("Stanbic ingestion failed")
            raise

    async def ingest_fund_details(self):
        """Collect fund terms independently of market prices; never create snapshots."""
        from app.adapters.mutual_fund.stanbic import OFFICIAL_PRODUCT_URLS
        from app.models.mutual_fund import MutualFund

        run = self.fetch_runs.create_pending(ProviderName.STANBIC)
        failures = []
        result = {
            "fetch_run_id": run.id,
            "funds_processed": 0,
            "fields_updated": 0,
            "fields_observed": 0,
            "extraction_failures": failures,
            "conflicts": [],
            "field_checks": [],
        }
        try:
            provider = self.repository.register_stanbic()
            funds = (
                self.db.query(MutualFund.code, MutualFund.currency, MutualFund.details_metadata)
                .filter_by(provider_id=provider.id)
                .order_by(MutualFund.code)
                .all()
            )
            if not funds:
                raise ValueError("No Stanbic catalogue: run market-data ingestion first")
            # Cache successful pages and exhausted failures, including shared URLs.
            async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
                cache = {}

                async def capture(url, kind):
                    if url not in cache:
                        try:
                            if kind == "listing":
                                html = await self.adapter.fetch_page(client=client)
                            elif kind == "blunest":
                                html = await self.adapter.fetch_blunest_details(url, client=client)
                            else:
                                html = await self.adapter.fetch_official_details(url, client=client)
                            raw = self.raw_records.create(
                                provider=ProviderName.STANBIC,
                                fetch_run_id=result["fetch_run_id"],
                                source_type=RawSourceType.HTML,
                                source_url=url,
                                payload={"content": html},
                                raw_text=html,
                            )
                            cache[url] = (html, raw.id, datetime.now(UTC).isoformat())
                        except Exception as exc:
                            cache[url] = exc
                    if isinstance(cache[url], Exception):
                        raise cache[url]
                    return cache[url]

                links = {}
                try:
                    html, _, _ = await capture(self.adapter.source_url, "listing")
                    links, link_failures = self.adapter.discover_detail_urls(html)
                    failures.extend(link_failures)
                except Exception as exc:
                    failures.append({"source_url": self.adapter.source_url, "error": str(exc)})
                for fund in funds:
                    if fund.code not in OFFICIAL_PRODUCT_URLS:
                        failures.append({"code": fund.code, "error": "No verified source mapping"})
                        continue
                    observations = {}
                    sources = [
                        ("blunest", links.get(fund.code)),
                        ("official", OFFICIAL_PRODUCT_URLS[fund.code]),
                    ]
                    for kind, url in sources:
                        if url is None:
                            failures.append(
                                {"code": fund.code, "error": "Analysis link absent from listing"}
                            )
                            continue
                        try:
                            html, raw_id, observed_at = await capture(url, kind)
                            parser = (
                                self.adapter.parse_blunest_details
                                if kind == "blunest"
                                else self.adapter.parse_official_details
                            )
                            details, evidence, errors = parser(
                                html, code=fund.code, currency=fund.currency
                            )
                            failures.extend(
                                dict(error, code=fund.code, source_url=url) for error in errors
                            )
                            # Missing publication is different from a broken extraction.
                            # Previously seen source labels disappearing require investigation.
                            fields = (
                                {
                                    "minimum_initial_investment",
                                    "minimum_topup",
                                    "minimum_holding_days",
                                    "risk_label",
                                }
                                if kind == "blunest"
                                else set(type(details).model_fields) - {"code", "currency"}
                            )
                            prior_fields = (fund.details_metadata or {}).get("fields", {})
                            for field in sorted(fields):
                                prior = prior_fields.get(field, {})
                                old_sources = prior.get("observations", []) + [prior]
                                seen_before = any(c.get("source_url") == url for c in old_sources)
                                failed = any(e.get("field") == field for e in errors)
                                status = (
                                    "available"
                                    if field in evidence
                                    else "failed_to_parse"
                                    if failed
                                    else "not_published"
                                )
                                check = {
                                    "code": fund.code,
                                    "field": field,
                                    "source_url": url,
                                    "raw_record_id": raw_id,
                                    "status": status,
                                    "checked_at": observed_at,
                                }
                                if field not in evidence and seen_before:
                                    check["unexpected_loss"] = True
                                    failures.append(
                                        {
                                            **check,
                                            "error": "Previously extracted source label/value lost",
                                        }
                                    )
                                result["field_checks"].append(check)
                            for field, value in details.model_dump(
                                exclude={"code", "currency"}, exclude_none=True
                            ).items():
                                observations.setdefault(field, []).append(
                                    {
                                        "value": str(value)
                                        if isinstance(value, Decimal)
                                        else value,
                                        "source_url": url,
                                        "raw_record_id": raw_id,
                                        "observed_at": observed_at,
                                        "last_successful_observation_at": observed_at,
                                        "source_kind": kind,
                                        **evidence[field],
                                    }
                                )
                        except Exception as exc:
                            self.db.rollback()
                            failures.append(
                                {"code": fund.code, "source_url": url, "error": str(exc)}
                            )
                    # Prefer the verified source once selected, including its legitimate
                    # changes. Initial selection uses field-specific precedence.
                    for field, candidates in observations.items():
                        preferred = (
                            "official"
                            if field
                            in {
                                "management_fee_percent_pa",
                                "distribution_frequency",
                                "structure",
                            }
                            else "blunest"
                        )
                        prior_url = (
                            (fund.details_metadata or {})
                            .get("fields", {})
                            .get(field, {})
                            .get("source_url")
                        )
                        candidates.sort(
                            key=lambda c: (
                                c["source_url"] != prior_url,
                                c["source_kind"] != preferred,
                            )
                        )
                    try:
                        saved = self.repository.update_details(
                            code=fund.code, currency=fund.currency, observations=observations
                        )
                        result["funds_processed"] += bool(saved["fields_observed"])
                        result["fields_updated"] += saved["fields_updated"]
                        result["fields_observed"] += saved["fields_observed"]
                        result["conflicts"].extend(saved["conflicts"])
                    except Exception as exc:
                        self.db.rollback()
                        failures.append({"code": fund.code, "error": str(exc)})
            issues = failures or result["conflicts"]
            result["status"] = (
                ("partial" if result["fields_observed"] else "failed") if issues else "success"
            )
            run.metadata_json = result.copy()
            run.records_fetched = result["funds_processed"]
            if issues:
                self.fetch_runs.mark_failed(
                    run,
                    error_message=(
                        f"Fund details {result['status']}: {len(failures)} extraction failures; "
                        f"{len(result['conflicts'])} source conflicts; see metadata"
                    ),
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
            logger.exception("Stanbic fund-details ingestion failed")
            raise
