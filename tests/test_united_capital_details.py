import asyncio
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from test_united_capital_ingestion import db as existing_database
from test_united_capital_ingestion import run_ingestion

from app.adapters.mutual_fund.united_capital import FUND_MAPPINGS, UnitedCapitalAdapter
from app.core.database import get_db
from app.models.enums import FetchRunStatus, IngestionJobType
from app.models.fetch_run import FetchRun
from app.models.mutual_fund import MutualFundSnapshot
from app.models.raw_record import RawRecord
from app.repositories.mutual_fund import MutualFundRepository
from app.services.ingestion.united_capital import UnitedCapitalIngestionService
from app.services.ingestion_scheduler import IngestionSchedulerService

db = existing_database
FIXTURES = Path(__file__).parent / "fixtures" / "united_capital_details"


def fixture(slug):
    return (FIXTURES / f"{slug}.html").read_text()


def details_run(db, *, fail=None, override=None, code=None):
    adapter = UnitedCapitalAdapter()

    async def fetch(fund_code, *, client):
        if fail == fund_code:
            raise RuntimeError("page unavailable")
        if override and fund_code in override:
            return override[fund_code]
        return fixture(adapter.product_url(fund_code).rstrip("/").split("/")[-1])

    adapter.fetch_product_page = AsyncMock(side_effect=fetch)
    result = asyncio.run(
        UnitedCapitalIngestionService(db, adapter=adapter).ingest_fund_details(fund_code=code)
    )
    return result, adapter


def test_stable_income_full_details():
    details, evidence, errors = UnitedCapitalAdapter().parse_product_details(
        fixture("stable-income-fund"), code="united-capital-stable-income", currency="NGN"
    )
    assert not errors
    assert details.minimum_initial_investment == Decimal("50000000")
    assert details.minimum_topup == Decimal("10000000")
    assert details.minimum_holding_days == 30
    assert details.risk_label == "Low"
    assert details.distribution_frequency == "annually"
    assert details.structure == "open_ended"
    assert details.management_fee_percent_pa is None
    assert all(e["supporting_text"] for e in evidence.values())


@pytest.mark.parametrize("mapping", list(FUND_MAPPINGS.values()))
def test_all_verified_product_pages_match_fund_code(mapping):
    slug, name, fund_type, currency, product = mapping
    details, evidence, errors = UnitedCapitalAdapter().parse_product_details(
        fixture(product), code="united-capital-" + slug, currency=currency
    )
    assert not errors
    assert details.minimum_initial_investment is not None
    assert evidence


def test_inline_digits_and_unit_based_minimums():
    adapter = UnitedCapitalAdapter()
    details, _, errors = adapter.parse_product_details(
        fixture("nigerian-eurobond-fund"), code="united-capital-nigerian-eurobond", currency="USD"
    )
    assert not errors
    assert details.minimum_holding_days == 90  # Source: 9<strong>0 days</strong>.
    assert details.minimum_initial_investment == Decimal("100")  # Cash entry, not 10 units.
    details, _, errors = adapter.parse_product_details(
        fixture("sukuk-fund"), code="united-capital-sukuk", currency="NGN"
    )
    assert details.minimum_initial_investment == Decimal("10000")
    assert details.minimum_topup == Decimal("5000")


def test_wrong_fund_currency_and_missing_content_rejected():
    adapter = UnitedCapitalAdapter()
    with pytest.raises(ValueError, match="currency"):
        adapter.parse_product_details(
            fixture("stable-income-fund"), code="united-capital-stable-income", currency="USD"
        )
    with pytest.raises(ValueError, match="heading"):
        adapter.parse_product_details(
            fixture("equity-fund"), code="united-capital-stable-income", currency="NGN"
        )


def test_details_persist_all_available_fields_and_provenance_without_snapshots(db):
    run_ingestion(db)
    result, adapter = details_run(db)
    assert result["status"] == "success"
    assert result["funds_processed"] == 10
    assert adapter.fetch_product_page.await_count == 10
    assert db.query(MutualFundSnapshot).count() == 10
    fund = MutualFundRepository(db).get_by_code("united-capital-stable-income")
    assert fund.minimum_initial_investment == Decimal("50000000")
    assert fund.minimum_topup == Decimal("10000000")
    for field, source in fund.details_metadata["fields"].items():
        assert source["source_url"] == "https://unitedcapitalplcgroup.com/stable-income-fund/"
        raw = db.get(RawRecord, source["raw_record_id"])
        assert raw.raw_text == fixture("stable-income-fund")
    old = fund.details_metadata["fields"]["minimum_topup"]["raw_record_id"]
    again, _ = details_run(db)
    assert again["fields_updated"] == 0
    assert fund.details_metadata["fields"]["minimum_topup"]["raw_record_id"] != old


def test_failed_product_keeps_prior_details_and_other_funds_process(db):
    run_ingestion(db)
    details_run(db)
    result, _ = details_run(db, fail="united-capital-stable-income")
    assert result["status"] == "partial"
    assert result["funds_processed"] == 9
    fund = MutualFundRepository(db).get_by_code("united-capital-stable-income")
    assert fund.minimum_initial_investment == Decimal("50000000")
    assert fund.is_active
    assert db.query(FetchRun).order_by(FetchRun.id.desc()).first().status == FetchRunStatus.FAILED


def test_details_requires_catalogue_and_retains_bad_page_evidence(db):
    with pytest.raises(ValueError, match="market-data ingestion first"):
        details_run(db)
    run_ingestion(db)
    result, _ = details_run(
        db,
        code="united-capital-stable-income",
        override={"united-capital-stable-income": "<html>Wrong product</html>"},
    )
    assert result["status"] == "failed"
    assert db.query(RawRecord).filter_by(raw_text="<html>Wrong product</html>").count() == 1


def test_manual_and_scheduled_details(db):
    from app.dependencies.auth import require_admin
    from app.main import app
    from app.services.ingestion.manual import run_provider_ingestion_job

    run_ingestion(db)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[require_admin] = lambda: None
    try:
        client = TestClient(app)
        with patch("app.services.provider.launch_provider_ingestion_job"):
            assert (
                client.post("/providers/united_capital/ingestion-runs/fund_details").status_code
                == 202
            )
        assert (
            client.put(
                "/providers/united_capital/ingestion-schedules/fund_details",
                json={"interval_minutes": 1440, "is_enabled": False},
            ).status_code
            == 200
        )
    finally:
        app.dependency_overrides.clear()
    with patch.object(
        UnitedCapitalIngestionService, "ingest_fund_details", new_callable=AsyncMock
    ) as fetch:
        asyncio.run(
            IngestionSchedulerService()._dispatch_job(
                db=db, provider_slug="united_capital", job_type=IngestionJobType.FUND_DETAILS
            )
        )
        with (
            patch("app.services.ingestion.manual.SessionLocal", return_value=db),
            patch("app.services.ingestion.manual.ProviderMetricService"),
        ):
            asyncio.run(
                run_provider_ingestion_job(
                    provider_slug="united_capital", job_type=IngestionJobType.FUND_DETAILS
                )
            )
        assert fetch.await_count == 2


def test_malformed_details_do_not_replace_valid_minimums(db):
    run_ingestion(db)
    details_run(db, code="united-capital-stable-income")
    fund = MutualFundRepository(db).get_by_code("united-capital-stable-income")
    before = fund.details_metadata["fields"]["minimum_initial_investment"].copy()
    bad = fixture("stable-income-fund").replace("N50,000,000", "Nnot-a-number")
    result, _ = details_run(
        db, code="united-capital-stable-income", override={"united-capital-stable-income": bad}
    )
    assert result["status"] == "partial"
    assert result["extraction_failures"]
    assert fund.minimum_initial_investment == Decimal("50000000")
    assert fund.details_metadata["fields"]["minimum_initial_investment"] == before


def test_wrong_published_currency_is_not_converted():
    bad = fixture("stable-income-fund").replace("N50,000,000", "$50,000,000")
    details, _, errors = UnitedCapitalAdapter().parse_product_details(
        bad, code="united-capital-stable-income", currency="NGN"
    )
    assert details.minimum_initial_investment is None
    assert errors
