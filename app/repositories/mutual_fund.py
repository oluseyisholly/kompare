from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models.enums import MarketCategory
from app.models.mutual_fund import MutualFund, MutualFundSnapshot
from app.models.provider import Provider
from app.repositories.pagination import paginate_query
from app.repositories.provider import ProviderRepository
from app.schemas.mutual_fund import ParsedFund


class MutualFundRepository:
    def __init__(self, db: Session):
        self.db = db

    def register_stanbic(self) -> Provider:
        return ProviderRepository(self.db).get_or_create_by_slug(
            slug="stanbic",
            name="Stanbic IBTC Asset Management",
            category=MarketCategory.MUTUAL_FUND,
            has_adapter=True,
            website_url="https://blunest.stanbicibtcassetmanagement.com",
        )

    def persist(self, *, provider_id, records, fetch_run_id, raw_record_id, captured_at=None):
        # Lock the provider to serialize fund creation and same-run persistence retries.
        self.db.query(Provider).filter(Provider.id == provider_id).with_for_update().one()
        captured_at = captured_at or datetime.now(UTC)
        created = 0
        try:
            for record in records:
                record = ParsedFund.model_validate(
                    record.model_dump() if isinstance(record, ParsedFund) else record
                )
                fund = self.db.query(MutualFund).filter_by(code=record.code).first()
                if fund is not None and fund.provider_id != provider_id:
                    raise ValueError("Fund code belongs to a different provider")
                if (
                    fund is not None
                    and self.db.query(MutualFundSnapshot)
                    .filter_by(
                        fund_id=fund.id,
                        fetch_run_id=fetch_run_id,
                    )
                    .first()
                    is not None
                ):
                    continue
                identity = record.model_dump(include={"code", "name", "fund_type", "currency"})
                if fund is None:
                    fund = MutualFund(provider_id=provider_id, **identity)
                    self.db.add(fund)
                    self.db.flush()
                else:
                    for key, value in identity.items():
                        setattr(fund, key, value)
                self.db.add(
                    MutualFundSnapshot(
                        fund_id=fund.id,
                        fetch_run_id=fetch_run_id,
                        raw_record_id=raw_record_id,
                        captured_at=captured_at,
                        **record.model_dump(exclude={"code", "name", "fund_type", "currency"}),
                    )
                )
                created += 1
            self.db.commit()
            return created
        except Exception:
            self.db.rollback()
            raise

    def list_funds(self, *, page, per_page, provider_id=None):
        query = self.db.query(MutualFund)
        if provider_id is not None:
            query = query.filter_by(provider_id=provider_id)
        return paginate_query(
            query.order_by(MutualFund.name, MutualFund.id), page=page, per_page=per_page
        )

    def get_by_code(self, code):
        return self.db.query(MutualFund).filter_by(code=code).first()

    def latest_snapshot(self, fund_id):
        query = self.db.query(MutualFundSnapshot).filter_by(fund_id=fund_id)
        dated_provider = (
            self.db.query(MutualFund.id)
            .join(
                Provider,
                MutualFund.provider_id == Provider.id,
            )
            .filter(MutualFund.id == fund_id, Provider.slug == "united_capital")
            .first()
        )
        if dated_provider:
            query = query.order_by(MutualFundSnapshot.valuation_date.desc().nullslast())
        return query.order_by(
            MutualFundSnapshot.captured_at.desc(),
            MutualFundSnapshot.id.desc(),
        ).first()

    def persist_dated(self, *, provider_id, record, fetch_run_id, raw_record_id, captured_at=None):
        """United Capital only: reject regressions under the existing provider lock."""
        from sqlalchemy import func

        try:
            provider = self.db.query(Provider).filter_by(id=provider_id).with_for_update().one()
            if provider.slug != "united_capital":
                raise ValueError("Dated persistence is reserved for United Capital")
            record = ParsedFund.model_validate(record.model_dump())
            if record.valuation_date is None:
                raise ValueError("United Capital observations require a source valuation date")
            fund = self.get_by_code(record.code)
            if fund is not None:
                if fund.provider_id != provider_id:
                    raise ValueError("Fund code belongs to a different provider")
                same_run = (
                    self.db.query(MutualFundSnapshot.id)
                    .filter_by(
                        fund_id=fund.id,
                        fetch_run_id=fetch_run_id,
                    )
                    .first()
                )
                if same_run:
                    self.db.commit()
                    return 0
                newest = (
                    self.db.query(func.max(MutualFundSnapshot.valuation_date))
                    .filter_by(
                        fund_id=fund.id,
                    )
                    .scalar()
                )
                if newest is not None and record.valuation_date < newest:
                    raise ValueError(
                        f"Source-date regression: {record.valuation_date} "
                        f"precedes verified {newest}"
                    )
            # Reuse the locked provider and loaded fund instead of querying them
            # again through persist(). Keep the same per-fund transaction boundary.
            identity = record.model_dump(include={"code", "name", "fund_type", "currency"})
            if fund is None:
                fund = MutualFund(provider_id=provider_id, **identity)
                self.db.add(fund)
                self.db.flush()
            else:
                for key, value in identity.items():
                    setattr(fund, key, value)
            self.db.add(
                MutualFundSnapshot(
                    fund_id=fund.id,
                    fetch_run_id=fetch_run_id,
                    raw_record_id=raw_record_id,
                    captured_at=captured_at or datetime.now(UTC),
                    **record.model_dump(exclude={"code", "name", "fund_type", "currency"}),
                )
            )
            self.db.commit()
            return 1
        except Exception:
            self.db.rollback()
            raise

    def update_details(self, *, code, currency, observations):
        """Apply validated observations to an existing fund; never clear missing fields."""
        from app.schemas.mutual_fund import ParsedFundDetails

        fund = self.db.query(MutualFund).filter_by(code=code).with_for_update().one_or_none()
        if fund is None:
            raise ValueError(f"{code}: run market-data ingestion first")
        if fund.currency != currency:
            raise ValueError(f"{code}: details currency does not match catalogue")
        metadata = dict(fund.details_metadata or {})
        provenance = dict(metadata.get("fields", {}))
        conflicts, changed, observed = [], 0, 0
        try:
            for field, candidates in observations.items():
                if field in {"code", "currency"} or field not in ParsedFundDetails.model_fields:
                    raise ValueError(f"Unsupported details field: {field}")
                validated = []
                for candidate in candidates:
                    record = ParsedFundDetails(
                        code=code, currency=currency, **{field: candidate["value"]}
                    )
                    value = getattr(record, field)
                    if value is not None:
                        validated.append((value, dict(candidate)))
                if not validated:
                    continue
                value, candidate = validated[0]
                selected = dict(candidate)
                old_value = getattr(fund, field)
                prior = provenance.get(field)
                # A different source cannot silently replace an existing verified value.
                if (
                    old_value is not None
                    and prior
                    and prior["source_url"] != selected["source_url"]
                    and old_value != value
                ):
                    selected = dict(prior)
                    value = old_value
                    for observed_value, observation in validated:
                        if (
                            observed_value == old_value
                            and observation["source_url"] == prior["source_url"]
                        ):
                            selected = dict(observation)
                            break
                for alternative_value, alternative in validated:
                    if alternative_value != value:
                        conflicts.append(
                            {
                                "code": code,
                                "field": field,
                                "retained": selected,
                                "alternative": alternative,
                            }
                        )
                if old_value != value:
                    setattr(fund, field, value)
                    changed += 1
                selected["observations"] = [candidate for _, candidate in validated]
                provenance[field] = selected
                observed += 1
            metadata["fields"] = provenance
            metadata["conflicts"] = list(metadata.get("conflicts", [])) + conflicts
            fund.details_metadata = metadata
            self.db.commit()
            return {"fields_updated": changed, "fields_observed": observed, "conflicts": conflicts}
        except Exception:
            self.db.rollback()
            raise

    def latest_snapshots_for_funds(self, fund_ids):
        """Batch latest rows so fund listings do not issue one query per fund."""
        from sqlalchemy import case, func

        if not fund_ids:
            return {}
        ranked = (
            self.db.query(
                MutualFundSnapshot.id.label("snapshot_id"),
                func.row_number()
                .over(
                    partition_by=MutualFundSnapshot.fund_id,
                    order_by=[
                        case(
                            (Provider.slug == "united_capital", MutualFundSnapshot.valuation_date),
                            else_=None,
                        )
                        .desc()
                        .nullslast(),
                        MutualFundSnapshot.captured_at.desc(),
                        MutualFundSnapshot.id.desc(),
                    ],
                )
                .label("position"),
            )
            .join(MutualFund, MutualFund.id == MutualFundSnapshot.fund_id)
            .join(
                Provider,
                Provider.id == MutualFund.provider_id,
            )
            .filter(MutualFundSnapshot.fund_id.in_(fund_ids))
            .subquery()
        )
        rows = (
            self.db.query(MutualFundSnapshot)
            .join(
                ranked,
                ranked.c.snapshot_id == MutualFundSnapshot.id,
            )
            .filter(ranked.c.position == 1)
            .all()
        )
        return {row.fund_id: row for row in rows}

    def source_contexts(self, raw_record_ids):
        from app.models.raw_record import RawRecord

        if not raw_record_ids:
            return {}
        # Select only the small JSON subtree. Never load the original HTML here.
        rows = (
            self.db.query(
                RawRecord.id,
                RawRecord.source_url,
                RawRecord.payload["source_context"].label("source_context"),
            )
            .filter(RawRecord.id.in_(raw_record_ids))
            .all()
        )
        return {
            row.id: {"source_url": row.source_url, "funds": row.source_context or {}}
            for row in rows
        }
