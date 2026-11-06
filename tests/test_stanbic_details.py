import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from test_stanbic_ingestion import HTML, ingest
from test_stanbic_ingestion import db as existing_database

from app.adapters.mutual_fund.stanbic import (
    OFFICIAL_PRODUCT_URLS,
    StanbicAdapter,
)
from app.models.enums import FetchRunStatus, IngestionJobType
from app.models.fetch_run import FetchRun
from app.models.mutual_fund import MutualFund, MutualFundSnapshot
from app.models.raw_record import RawRecord
from app.repositories.mutual_fund import MutualFundRepository
from app.schemas.mutual_fund import ParsedFund, ParsedFundDetails
from app.services.ingestion.stanbic import StanbicIngestionService
from app.services.ingestion_scheduler import IngestionSchedulerService

db = existing_database

FIXTURES = Path(__file__).parent / "fixtures" / "stanbic_details"


def fixture(kind, code="simm"):
    return (FIXTURES / f"{kind}-{code}.html").read_text()


def adapter_with_pages(*, fail=None, override=None):
    adapter = StanbicAdapter()
    adapter.fetch_page = AsyncMock(return_value=HTML)

    async def fetch(url, *, client):
        if url == fail:
            raise RuntimeError("upstream unavailable")
        if override and url in override:
            return override[url]
        kind = "official" if url in OFFICIAL_PRODUCT_URLS.values() else "blunest"
        code = (
            next(k for k, v in OFFICIAL_PRODUCT_URLS.items() if v == url)
            if kind == "official"
            else "stanbic-" + url.rstrip("/").split("/")[-1]
        )
        return fixture(kind, code.removeprefix("stanbic-"))

    adapter.fetch_blunest_details = AsyncMock(side_effect=fetch)
    adapter.fetch_official_details = AsyncMock(side_effect=fetch)
    return adapter


def details_run(db, **kwargs):
    adapter = adapter_with_pages(**kwargs)
    result = asyncio.run(StanbicIngestionService(db, adapter=adapter).ingest_fund_details())
    return result, adapter


def test_blunest_extracts_precise_labels_and_ignores_dashboard():
    details, evidence, errors = StanbicAdapter().parse_blunest_details(
        fixture("blunest"), code="stanbic-simm", currency="NGN"
    )
    assert not errors
    assert details.minimum_initial_investment == Decimal("5000")
    assert details.minimum_topup == Decimal("5000")
    assert details.minimum_holding_days == 30
    assert details.risk_label == "Low"
    assert details.management_fee_percent_pa is None
    assert evidence["minimum_topup"]["published_label"] == "Minimum Subsequent Subscription"
    assert len(evidence) == 4


def test_official_extracts_only_fund_highlights():
    details, evidence, errors = StanbicAdapter().parse_official_details(
        fixture("official"), code="stanbic-simm", currency="NGN"
    )
    assert not errors
    assert details.management_fee_percent_pa == Decimal("1.5")
    assert details.structure == "open_ended"
    assert details.distribution_frequency == "quarterly"
    assert details.minimum_initial_investment == Decimal("5000")
    assert "per annum" in evidence["management_fee_percent_pa"]["published_label"]


@pytest.mark.parametrize(
    "code", ["simm", "sidf", "siefif", "sigf", "sfif", "sibal", "snef", "stef", "simaan"]
)
def test_all_verified_fund_sources_match(code):
    for kind in ("blunest", "official"):
        parsed, evidence, _ = getattr(StanbicAdapter(), f"parse_{kind}_details")(
            fixture(kind, code), code=f"stanbic-{code}", currency="USD" if code == "sidf" else "NGN"
        )
        assert evidence
        assert parsed.code == f"stanbic-{code}"
    with pytest.raises(ValueError, match="does not match"):
        StanbicAdapter().parse_blunest_details(
            fixture("blunest", code), code="stanbic-invalid", currency="NGN"
        )


@pytest.mark.parametrize("value", ["5,000 units", "$5,000", "5000", "₦NaN", "₦-1", "₦5,00"])
def test_wrong_currency_units_and_malformed_cash_rejected(value):
    html = fixture("blunest").replace("₦5,000", value)
    parsed, _, errors = StanbicAdapter().parse_blunest_details(
        html, code="stanbic-simm", currency="NGN"
    )
    assert parsed.minimum_initial_investment is None
    assert parsed.minimum_topup is None
    assert parsed.minimum_holding_days == 30
    assert errors


def test_explicit_zero_and_missing_are_distinct():
    parsed, _, _ = StanbicAdapter().parse_blunest_details(
        fixture("blunest", "sfif"), code="stanbic-sfif", currency="NGN"
    )
    assert parsed.minimum_holding_days == 0
    parsed, _, errors = StanbicAdapter().parse_blunest_details(
        fixture("blunest").replace("₦5,000", ""), code="stanbic-simm", currency="NGN"
    )
    assert parsed.minimum_initial_investment is None
    assert errors
    with pytest.raises(ValueError):
        ParsedFund(code="x", name="x", fund_type="x", currency="NGN")
    assert ParsedFundDetails(code="stanbic-simm", currency="NGN").minimum_topup is None


@pytest.mark.parametrize("code", ["sidf", "stef"])
def test_annual_fee_basis_not_inferred(code):
    parsed, _, errors = StanbicAdapter().parse_official_details(
        fixture("official", code),
        code=f"stanbic-{code}",
        currency="USD" if code == "sidf" else "NGN",
    )
    assert parsed.management_fee_percent_pa is None
    assert any("annual basis" in error["error"] for error in errors)


def test_discovery_rejects_unexpected_hosts():
    links, _ = StanbicAdapter().discover_detail_urls(HTML)
    assert len(links) == 9
    assert links["stanbic-simm"].endswith("/fund/simm")
    malicious = HTML.replace('./fund/simm"', 'https://evil.example/v2/invest-now/fund/simm"')
    links, errors = StanbicAdapter().discover_detail_urls(malicious)
    assert "stanbic-simm" not in links
    assert any("Unexpected" in error["error"] for error in errors)


def test_details_job_evidence_precedence_conflicts_and_bounded_fetches(db):
    ingest(db)
    result, adapter = details_run(db)
    assert result["status"] == "partial"
    assert result["funds_processed"] == 9
    assert db.query(MutualFundSnapshot).count() == 9
    assert db.query(RawRecord).count() == 20  # initial listing + details listing + 18 detail pages
    assert db.query(FetchRun).order_by(FetchRun.id.desc()).first().status == FetchRunStatus.FAILED
    assert result["conflicts"]
    fund = db.query(MutualFund).filter_by(code="stanbic-simm").one()
    assert fund.risk_label == "Low"
    assert fund.management_fee_percent_pa == Decimal("1.5")
    meta = fund.details_metadata["fields"]
    assert meta["risk_label"]["source_kind"] == "blunest"
    assert meta["management_fee_percent_pa"]["source_kind"] == "official"
    for field, provenance in meta.items():
        raw = db.get(RawRecord, provenance["raw_record_id"])
        assert raw.source_url == provenance["source_url"]
        assert raw.raw_text
        assert provenance["last_successful_observation_at"]
    adapter.fetch_page.assert_awaited_once()
    assert (
        adapter.fetch_blunest_details.await_count == adapter.fetch_official_details.await_count == 9
    )
    clients = {
        id(call.kwargs["client"])
        for call in adapter.fetch_blunest_details.await_args_list
        + adapter.fetch_official_details.await_args_list
        + adapter.fetch_page.await_args_list
    }
    assert len(clients) == 1
    for method in (adapter.fetch_blunest_details, adapter.fetch_official_details):
        assert len({c.args[0] for c in method.await_args_list}) == 9


def test_failed_page_does_not_block_other_funds_or_clear_values(db):
    ingest(db)
    details_run(db)
    fund = db.query(MutualFund).filter_by(code="stanbic-simm").one()
    prior = fund.details_metadata["fields"]["minimum_topup"].copy()
    result, _ = details_run(
        db, fail="https://blunest.stanbicibtcassetmanagement.com/v2/invest-now/fund/simm"
    )
    assert result["status"] == "partial"
    assert result["funds_processed"] == 9  # official fallback still has successful fields
    assert fund.minimum_topup == Decimal("5000")
    assert fund.is_active
    assert fund.details_metadata["fields"]["minimum_topup"] == prior
    assert db.query(MutualFundSnapshot).count() == 9


def test_unchanged_observations_refresh_provenance_and_api(db):
    from app.core.database import get_db
    from app.main import app

    ingest(db)
    details_run(db)
    fund = db.query(MutualFund).filter_by(code="stanbic-simm").one()
    old = fund.details_metadata["fields"]["minimum_topup"]["raw_record_id"]
    result, _ = details_run(db)
    assert result["fields_updated"] == 0
    assert result["fields_observed"] > 0
    assert fund.details_metadata["fields"]["minimum_topup"]["raw_record_id"] != old
    app.dependency_overrides[get_db] = lambda: db
    try:
        response = TestClient(app).get("/mutual-funds/?provider=stanbic")
        data = next(f for f in response.json()["data"]["items"] if f["code"] == "stanbic-simm")
        assert Decimal(str(data["management_fee_percent_pa"])) == Decimal("1.5")
        assert data["details_metadata"]["fields"]["structure"]["source_kind"] == "official"
    finally:
        app.dependency_overrides.clear()


def test_requires_catalogue_and_records_failure(db):
    with pytest.raises(ValueError, match="market-data ingestion first"):
        details_run(db)
    assert db.query(FetchRun).one().status == FetchRunStatus.FAILED
    assert db.query(MutualFundSnapshot).count() == 0


def test_parse_failure_preserves_raw_html_and_other_funds(db):
    ingest(db)
    url = OFFICIAL_PRODUCT_URLS["stanbic-simm"]
    result, _ = details_run(db, override={url: "<h1>Unexpected product</h1>"})
    assert result["status"] == "partial"
    assert any(e.get("source_url") == url for e in result["extraction_failures"])
    raw = db.query(RawRecord).filter_by(source_url=url).one()
    assert raw.raw_text == "<h1>Unexpected product</h1>"


def test_repository_preserves_verified_value_against_conflicting_fallback(db):
    ingest(db)
    repo = MutualFundRepository(db)

    def observe(value, url):
        return {
            "minimum_topup": [
                {
                    "value": str(value),
                    "source_url": url,
                    "raw_record_id": 1,
                    "last_successful_observation_at": datetime.now(UTC).isoformat(),
                    "published_label": "Minimum Subsequent Subscription",
                }
            ]
        }

    repo.update_details(code="stanbic-simm", currency="NGN", observations=observe(0, "primary"))
    saved = repo.update_details(
        code="stanbic-simm", currency="NGN", observations=observe(100, "fallback")
    )
    fund = repo.get_by_code("stanbic-simm")
    assert fund.minimum_topup == 0
    assert saved["conflicts"]
    assert fund.details_metadata["fields"]["minimum_topup"]["source_url"] == "primary"
    repo.update_details(code="stanbic-simm", currency="NGN", observations={})
    assert fund.minimum_topup == 0


def test_fund_details_manual_and_scheduler_dispatch(db):
    from app.services.ingestion.manual import run_provider_ingestion_job

    with patch.object(
        StanbicIngestionService, "ingest_fund_details", new_callable=AsyncMock
    ) as run:
        asyncio.run(
            IngestionSchedulerService()._dispatch_job(
                db=db, provider_slug="stanbic", job_type=IngestionJobType.FUND_DETAILS
            )
        )
        run.assert_awaited_once()
        with (
            patch("app.services.ingestion.manual.SessionLocal", return_value=db),
            patch("app.services.ingestion.manual.ProviderMetricService"),
        ):
            asyncio.run(
                run_provider_ingestion_job(
                    provider_slug="stanbic", job_type=IngestionJobType.FUND_DETAILS
                )
            )
        assert run.await_count == 2


def test_fund_details_manual_trigger_and_schedule(db):
    from app.core.database import get_db
    from app.dependencies.auth import require_admin
    from app.main import app

    MutualFundRepository(db).register_stanbic()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[require_admin] = lambda: None
    try:
        client = TestClient(app)
        with patch("app.services.provider.launch_provider_ingestion_job") as launch:
            assert client.post("/providers/stanbic/ingestion-runs/fund_details").status_code == 202
            assert launch.call_args.kwargs["job_type"] == IngestionJobType.FUND_DETAILS
            assert (
                client.post(
                    "/providers/stanbic/ingestion-runs/fund_details?include_kyc=true"
                ).status_code
                == 400
            )
        response = client.put(
            "/providers/stanbic/ingestion-schedules/fund_details",
            json={"interval_minutes": 1440, "is_enabled": False},
        )
        assert response.status_code == 200
        assert response.json()["data"]["job_type"] == "fund_details"
        assert response.json()["data"]["is_enabled"] is False
    finally:
        app.dependency_overrides.clear()


def test_malformed_fields_preserve_prior_values_and_provenance(db):
    ingest(db)
    details_run(db)
    fund = MutualFundRepository(db).get_by_code("stanbic-simm")
    old_fee = fund.details_metadata["fields"]["management_fee_percent_pa"].copy()
    old_minimum = fund.details_metadata["fields"]["minimum_initial_investment"].copy()
    overrides = {
        OFFICIAL_PRODUCT_URLS["stanbic-simm"]: fixture("official")
        .replace("1.5% per annum", "invalid% per annum")
        .replace("N5,000.00", "5,000 units"),
        "https://blunest.stanbicibtcassetmanagement.com/v2/invest-now/fund/simm": fixture(
            "blunest"
        ).replace("₦5,000", "$5,000"),
    }
    result, _ = details_run(db, override=overrides)
    assert result["status"] == "partial"
    assert fund.management_fee_percent_pa == Decimal("1.5")
    assert fund.minimum_initial_investment == Decimal("5000")
    assert fund.details_metadata["fields"]["management_fee_percent_pa"] == old_fee
    assert fund.details_metadata["fields"]["minimum_initial_investment"] == old_minimum


def test_existing_fallback_observation_refreshes_when_primary_conflicts(db):
    ingest(db)
    repo = MutualFundRepository(db)

    def observation(value, source, timestamp):
        return {
            "value": value,
            "source_url": source,
            "raw_record_id": 1,
            "last_successful_observation_at": timestamp,
            "published_label": "Investment Risk",
        }

    old = observation("Conservative", "official", "2026-10-22T00:00:00+00:00")
    repo.update_details(code="stanbic-simm", currency="NGN", observations={"risk_label": [old]})
    fresh = observation("Conservative", "official", "2026-10-23T00:00:00+00:00")
    primary = observation("Low", "blunest", "2026-10-23T00:00:00+00:00")
    result = repo.update_details(
        code="stanbic-simm", currency="NGN", observations={"risk_label": [primary, fresh]}
    )
    fund = repo.get_by_code("stanbic-simm")
    assert fund.risk_label == "Conservative"
    assert result["conflicts"]
    assert (
        fund.details_metadata["fields"]["risk_label"]["last_successful_observation_at"]
        == fresh["last_successful_observation_at"]
    )


def test_different_fund_terms_and_currency_are_not_shared():
    money, _, _ = StanbicAdapter().parse_blunest_details(
        fixture("blunest"), code="stanbic-simm", currency="NGN"
    )
    dollar, _, _ = StanbicAdapter().parse_blunest_details(
        fixture("blunest", "sidf"), code="stanbic-sidf", currency="USD"
    )
    assert (money.minimum_initial_investment, money.minimum_holding_days) == (Decimal("5000"), 30)
    assert (dollar.minimum_initial_investment, dollar.minimum_holding_days) == (Decimal("100"), 182)


def test_navigation_and_unrelated_product_widgets_are_ignored():
    from bs4 import BeautifulSoup

    noise = BeautifulSoup(fixture("blunest"), "html.parser").select_one(".nk-iv-wg3-nav")
    noise = str(noise).replace("₦5,000", "₦900,000")
    html = "<nav><h4>Other fund</h4>" + noise + "</nav>" + fixture("blunest")
    # A nested promotional product card must not supply terms for the parent fund.
    html = html.replace("</ul></div>", '</ul><div class="card">' + noise + "</div></div>")
    parsed, _, errors = StanbicAdapter().parse_blunest_details(
        html, code="stanbic-simm", currency="NGN"
    )
    assert not errors
    assert parsed.minimum_topup == Decimal("5000")
    official_noise = fixture("official").replace("1.5% per annum", "99% per annum")
    html = "<nav>" + official_noise.replace("<main>", "").replace("</main>", "") + "</nav>"
    parsed, _, errors = StanbicAdapter().parse_official_details(
        html + fixture("official"), code="stanbic-simm", currency="NGN"
    )
    assert not errors
    assert parsed.management_fee_percent_pa == Decimal("1.5")


def test_repeated_conflicting_label_invalidates_only_that_field():
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(fixture("blunest"), "html.parser")
    duplicate = str(soup.select_one(".nk-iv-wg3-nav li")).replace("₦5,000", "₦900,000")
    soup.select_one(".nk-iv-wg3-nav").append(BeautifulSoup(duplicate, "html.parser"))
    parsed, _, errors = StanbicAdapter().parse_blunest_details(
        str(soup), code="stanbic-simm", currency="NGN"
    )
    assert parsed.minimum_initial_investment is None
    assert parsed.minimum_topup == Decimal("5000")
    assert any("Conflicting" in error["error"] for error in errors)


def test_multiples_condition_and_published_risk_wording_are_preserved():
    html = fixture("blunest").replace("₦5,000", "₦5,000 in multiples of ₦1,000")
    html = html.replace(">Low<", ">Moderately conservative<")
    parsed, evidence, errors = StanbicAdapter().parse_blunest_details(
        html, code="stanbic-simm", currency="NGN"
    )
    assert not errors
    assert parsed.minimum_initial_investment == Decimal("5000")
    assert evidence["minimum_topup"]["conditions"] == "₦5,000 in multiples of ₦1,000"
    assert parsed.risk_label == "Moderately conservative"


def test_redemption_distribution_options_and_other_percentages_are_not_terms():
    html = (
        fixture("official")
        .replace("The Fund has a 30-day minimum holding period", "Redemption settlement is 2 days")
        .replace(
            "The distribution frequency is quarterly and it is an open-ended fund",
            "You may receive or reinvest distributions",
        )
        .replace("The management fee is 1.5% per annum", "The expense ratio is 3% per annum")
    )
    parsed, _, errors = StanbicAdapter().parse_official_details(
        html, code="stanbic-simm", currency="NGN"
    )
    assert not errors
    assert parsed.minimum_holding_days is None
    assert parsed.distribution_frequency is None
    assert parsed.management_fee_percent_pa is None


def test_fee_annual_basis_must_apply_to_management_fee():
    html = fixture("official").replace(
        "The management fee is 1.5% per annum",
        "The management fee is 1.5%; the expense ratio is 3% per annum",
    )
    parsed, _, errors = StanbicAdapter().parse_official_details(
        html, code="stanbic-simm", currency="NGN"
    )
    assert parsed.management_fee_percent_pa is None
    assert errors


def test_missing_publication_and_lost_labels_have_distinct_diagnostics(db):
    from bs4 import BeautifulSoup

    ingest(db)
    first, _ = details_run(db)
    assert any(
        c["code"] == "stanbic-simm"
        and c["field"] == "minimum_topup"
        and c["status"] == "not_published"
        for c in first["field_checks"]
    )
    assert any(
        c["code"] == "stanbic-sidf"
        and c["field"] == "management_fee_percent_pa"
        and c["status"] == "failed_to_parse"
        for c in first["field_checks"]
    )
    fund = MutualFundRepository(db).get_by_code("stanbic-simm")
    old = fund.details_metadata["fields"]["management_fee_percent_pa"].copy()
    soup = BeautifulSoup(fixture("official"), "html.parser")
    next(li for li in soup.select("li") if "management fee" in li.text).decompose()
    result, _ = details_run(db, override={OFFICIAL_PRODUCT_URLS["stanbic-simm"]: str(soup)})
    assert any(
        c.get("unexpected_loss") and c["field"] == "management_fee_percent_pa"
        for c in result["field_checks"]
    )
    assert fund.details_metadata["fields"]["management_fee_percent_pa"] == old
    assert fund.management_fee_percent_pa == Decimal("1.5")


def test_source_can_change_its_own_value_with_raw_history(db):
    ingest(db)
    details_run(db)
    fund = MutualFundRepository(db).get_by_code("stanbic-simm")
    old = fund.details_metadata["fields"]["minimum_topup"].copy()
    url = "https://blunest.stanbicibtcassetmanagement.com/v2/invest-now/fund/simm"
    details_run(db, override={url: fixture("blunest").replace("₦5,000", "₦7,500")})
    current = fund.details_metadata["fields"]["minimum_topup"]
    assert fund.minimum_topup == Decimal("7500")
    assert current["observed_at"] == current["last_successful_observation_at"]
    assert current["source_label"] == "Minimum Subsequent Subscription"
    assert current["raw_record_id"] != old["raw_record_id"]
    assert "₦5,000" in db.get(RawRecord, old["raw_record_id"]).raw_text
    assert "₦7,500" in db.get(RawRecord, current["raw_record_id"]).raw_text
    assert db.query(MutualFundSnapshot).count() == 9


def test_failed_listing_still_allows_mapped_official_pages(db):
    ingest(db)
    adapter = adapter_with_pages()
    adapter.fetch_page = AsyncMock(side_effect=RuntimeError("Listing unavailable"))
    result = asyncio.run(StanbicIngestionService(db, adapter=adapter).ingest_fund_details())
    assert result["status"] == "partial"
    assert result["funds_processed"] == 9
    assert adapter.fetch_blunest_details.await_count == 0
    assert adapter.fetch_official_details.await_count == 9
    assert db.query(MutualFundSnapshot).count() == 9


@pytest.mark.parametrize("failure", ["transport", 503, 404, 302])
def test_fetch_retry_is_bounded_and_only_for_transient_failures(failure):
    import httpx

    request = httpx.Request("GET", OFFICIAL_PRODUCT_URLS["stanbic-simm"])
    error = (
        httpx.ConnectError("TLS failed", request=request)
        if failure == "transport"
        else httpx.HTTPStatusError(
            "upstream", request=request, response=httpx.Response(failure, request=request)
        )
    )
    retryable = failure in {"transport", 503}
    with (
        patch("app.adapters.mutual_fund.stanbic.get_html", new_callable=AsyncMock) as fetch,
        patch("app.adapters.mutual_fund.stanbic.asyncio.sleep", new_callable=AsyncMock),
    ):
        fetch.side_effect = [error, "<html>ok</html>"]
        operation = StanbicAdapter().fetch_official_details(str(request.url), client=object())
        if retryable:
            assert asyncio.run(operation) == "<html>ok</html>"
            assert fetch.await_count == 2
            fetch.reset_mock()
            fetch.side_effect = error
            with pytest.raises(type(error)):
                asyncio.run(StanbicAdapter().fetch_official_details(str(request.url), client=None))
            assert fetch.await_count == 2
        else:
            with pytest.raises(type(error)):
                asyncio.run(operation)
            assert fetch.await_count == 1


@pytest.mark.parametrize(
    "code,expected",
    [
        ("simm", "1.5"),
        ("siefif", "1.25"),
        ("sigf", "1.5"),
        ("sfif", "1.5"),
        ("sibal", "1.25"),
        ("snef", "3.0"),
        ("simaan", "1.5"),
    ],
)
def test_each_explicit_annual_fee_is_extracted(code, expected):
    parsed, _, errors = StanbicAdapter().parse_official_details(
        fixture("official", code), code=f"stanbic-{code}", currency="NGN"
    )
    assert not errors
    assert parsed.management_fee_percent_pa == Decimal(expected)


def test_legitimate_changes_from_chosen_fallback_source_are_preserved(db):
    ingest(db)
    url = "https://blunest.stanbicibtcassetmanagement.com/v2/invest-now/fund/simm"
    details_run(db, fail=url)
    fund = MutualFundRepository(db).get_by_code("stanbic-simm")
    assert fund.risk_label == "Conservative"
    result, _ = details_run(
        db,
        override={
            OFFICIAL_PRODUCT_URLS["stanbic-simm"]: fixture("official").replace(
                "Conservative", "Aggressive"
            )
        },
    )
    assert fund.risk_label == "Aggressive"
    assert fund.details_metadata["fields"]["risk_label"]["source_kind"] == "official"
    assert any(
        c["code"] == fund.code and c["field"] == "risk_label" and c["alternative"]["value"] == "Low"
        for c in result["conflicts"]
    )


def test_equivalent_repeated_amount_does_not_drop_multiples_condition():
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(fixture("blunest"), "html.parser")
    nav = soup.select_one(".nk-iv-wg3-nav")
    first = nav.select_one("li")
    duplicate = str(first)
    first.select_one(".number-sm").string = "₦5,000 in multiples of ₦1,000"
    nav.append(BeautifulSoup(duplicate, "html.parser"))
    parsed, evidence, errors = StanbicAdapter().parse_blunest_details(
        str(soup), code="stanbic-simm", currency="NGN"
    )
    assert not errors
    assert parsed.minimum_initial_investment == Decimal("5000")
    assert "multiples of ₦1,000" in evidence["minimum_initial_investment"]["conditions"]
    assert "multiples of ₦1,000" in evidence["minimum_initial_investment"]["supporting_text"]
