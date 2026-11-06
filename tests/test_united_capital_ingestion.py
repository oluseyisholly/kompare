import asyncio
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from bs4 import BeautifulSoup
from fastapi.testclient import TestClient
from test_stanbic_ingestion import db as existing_database

from app.adapters.mutual_fund.united_capital import (
    UnitedCapitalAdapter,
    parse_date,
    parse_decimal,
)
from app.core.database import get_db
from app.models.enums import FetchRunStatus, IngestionJobType
from app.models.fetch_run import FetchRun
from app.models.mutual_fund import MutualFund, MutualFundSnapshot
from app.models.provider import Provider
from app.models.raw_record import RawRecord
from app.repositories.mutual_fund import MutualFundRepository
from app.schemas.mutual_fund import ParsedFund
from app.services.ingestion.united_capital import UnitedCapitalIngestionService
from app.services.ingestion_scheduler import IngestionSchedulerService

db = existing_database
HTML = (Path(__file__).parent / "fixtures" / "united_capital_prices.html").read_text()
TODAY = date(2026, 10, 23)


def parse(html=HTML, today=TODAY):
    return UnitedCapitalAdapter().parse(html, today=today)


def mutate_table(label, mutate):
    soup = BeautifulSoup(HTML, "html.parser")
    tab = next(t for t in soup.select("[role=tab]") if t.get_text(" ", strip=True) == label)
    table = soup.find(id=tab["aria-controls"]).select_one("table")
    mutate(table)
    return str(soup)


def run_ingestion(db, html=HTML, stale_after_days=7):
    adapter = UnitedCapitalAdapter()
    adapter.fetch_page = AsyncMock(return_value=html)
    with patch("app.services.ingestion.united_capital.source_today", return_value=TODAY):
        result = asyncio.run(
            UnitedCapitalIngestionService(
                db, adapter=adapter, stale_after_days=stale_after_days
            ).ingest_market_data()
        )
    adapter.fetch_page.assert_awaited_once()
    return result


def test_actual_tab_mapping_metrics_and_currencies():
    result = parse()
    assert not result.failures
    funds = {record.code: record for record in result.records}
    assert len(funds) == 10
    assert funds["united-capital-equity"].bid_price == Decimal("2.4801")
    assert funds["united-capital-equity"].ytd_return_percent == Decimal("46.29")
    assert funds["united-capital-nigerian-eurobond"].currency == "USD"
    assert funds["united-capital-global-fixed-income"].currency == "USD"
    assert funds["united-capital-stable-income"].fund_type == "fixed_income"
    assert funds["united-capital-children-investment"].fund_type == "mixed_asset"
    assert funds["united-capital-sukuk"].fund_type == "shariah_fixed_income"
    assert all(f.valuation_date == date(2026, 10, 7) for f in funds.values())
    assert all(f.nav_per_unit is f.yield_percent is f.yield_label is None for f in funds.values())
    unresolved = result.source_context["united-capital-money-market"]["latest_rows"][0][
        "unresolved_metric"
    ]
    assert unresolved["label"] == "Effective Yield Day on Day Return"
    assert unresolved["published_value"] == "15.38%"
    assert result.warnings


def test_panel_order_is_irrelevant_and_label_contradictions_fail():
    soup = BeautifulSoup(HTML, "html.parser")
    for panel in reversed(soup.select("[role=tabpanel]")):
        soup.append(panel.extract())
    assert {f.code: f for f in parse(str(soup)).records} == {f.code: f for f in parse().records}
    bad = mutate_table(
        "Equity Fund", lambda table: table.__setitem__("aria-label", "Balanced Fund")
    )
    result = parse(bad)
    assert len(result.records) == 9
    assert any("contradicts" in f["error"] for f in result.failures)


@pytest.mark.parametrize(
    "text, expected",
    [(" 1,234.5600 ", "1234.5600"), ("-4.29%", "-4.29"), ("0%", "0"), ("0.1624", "0.1624")],
)
def test_decimal_and_percent_conventions(text, expected):
    assert parse_decimal(text, percent=True) == Decimal(expected)


@pytest.mark.parametrize("text", ["", "—", "-", "N/A", "  "])
def test_missing_numbers_remain_null(text):
    assert parse_decimal(text, percent=True) is None


@pytest.mark.parametrize("text", ["NaN", "Infinity", "1,23", "12x", "2%%"])
def test_bad_numbers_rejected(text):
    with pytest.raises(ValueError):
        parse_decimal(text, percent=True)


@pytest.mark.parametrize(
    "text, expected",
    [
        ("30-Sept-26", date(2026, 9, 30)),
        ("5-July-24", date(2024, 7, 5)),
        ("28-June-2024", date(2024, 6, 28)),
    ],
)
def test_published_date_formats(text, expected):
    assert parse_date(text) == expected


def test_ytd_only_record_and_negative_returns_are_valid():
    def replace(table):
        cells = table.select("tbody tr")[0].select("td")
        cells[1].string = ""
        cells[2].string = "—"
        cells[3].string = "-4.29%"

    record = next(
        f
        for f in parse(mutate_table("Equity Fund", replace)).records
        if f.code == "united-capital-equity"
    )
    assert record.bid_price is record.offer_price is None
    assert record.ytd_return_percent == Decimal("-4.29")
    with pytest.raises(ValueError):
        ParsedFund(code="empty", name="Empty", fund_type="equity", currency="NGN")


def test_latest_is_selected_by_date_not_row_order():
    def reorder(table):
        row = table.select("tbody tr")[0]
        table.select_one("tbody").append(row.extract())

    equity = next(
        f
        for f in parse(mutate_table("Equity Fund", reorder)).records
        if f.code == "united-capital-equity"
    )
    assert equity.valuation_date == date(2026, 10, 7)


def test_identical_duplicates_collapse_but_conflicts_do_not_publish():
    import copy

    def identical(table):
        table.select_one("tbody").append(copy.deepcopy(table.select_one("tbody tr")))

    result = parse(mutate_table("Equity Fund", identical))
    assert len(result.records) == 10
    assert any(w["type"] == "identical_duplicates_collapsed" for w in result.warnings)

    def conflict(table):
        row = copy.deepcopy(table.select_one("tbody tr"))
        row.select("td")[1].string = "99"
        table.select_one("tbody").append(row)

    result = parse(mutate_table("Equity Fund", conflict))
    assert len(result.records) == 9
    assert any("Conflicting rows" in f["error"] for f in result.failures)


def test_invalid_newest_row_does_not_fall_back_to_older():
    def invalid(table):
        table.select("tbody tr")[0].select("td")[1].string = "NaN"

    result = parse(mutate_table("Equity Fund", invalid))
    assert len(result.records) == 9
    assert not any(f.code == "united-capital-equity" for f in result.records)
    assert result.failures


def test_future_dates_rejected_and_unknown_tabs_visible():
    def future(table):
        table.select("tbody tr")[0].select("td")[0].string = "24-Oct-26"

    result = parse(mutate_table("Equity Fund", future))
    assert any("Future valuation" in f["error"] for f in result.failures)
    result = parse(HTML + '<button role="tab" aria-controls="unknown">New Fund</button>')
    assert any("Unfamiliar" in f["error"] for f in result.failures)


def test_ingestion_staleness_evidence_idempotency_and_repeated_runs(db):
    result = run_ingestion(db)
    assert result["status"] == "success"
    assert result["snapshots_created"] == 10
    assert result["has_stale_data"]
    assert all(d["age_days"] == 16 for d in result["source_dates"].values())
    raw = db.query(RawRecord).one()
    assert raw.raw_text == raw.payload["content"] == HTML
    assert raw.source_url == UnitedCapitalAdapter.source_url
    assert (
        raw.payload["source_context"]["united-capital-money-market"]["latest_rows"][0][
            "unresolved_metric"
        ]["published_value"]
        == "15.38%"
    )
    repo = MutualFundRepository(db)
    record = parse().records[0]
    assert (
        repo.persist_dated(
            provider_id=db.query(Provider).one().id,
            record=record,
            fetch_run_id=result["fetch_run_id"],
            raw_record_id=raw.id,
        )
        == 0
    )
    assert db.query(MutualFundSnapshot).count() == 10
    run_ingestion(db)
    assert db.query(Provider).count() == 1
    assert db.query(MutualFund).count() == 10
    assert db.query(MutualFundSnapshot).count() == 20
    assert db.query(FetchRun).order_by(FetchRun.id.desc()).first().status == FetchRunStatus.SUCCESS


def test_staleness_threshold_is_configurable(db):
    result = run_ingestion(db, stale_after_days=20)
    assert not result["has_stale_data"]
    assert not any(w["type"] == "stale_source" for w in result["warnings"])


def test_regression_preserves_current_and_does_not_deactivate(db):
    run_ingestion(db)
    result = run_ingestion(
        db,
        HTML.replace("07-Oct-26", "01-Oct-26")
        .replace("06-Oct-26", "01-Oct-26")
        .replace("02-Oct-26", "01-Oct-26"),
    )
    # Same-date contradictions are extraction failures, never a reason to publish older rows.
    assert result["status"] == "failed"
    assert db.query(MutualFundSnapshot).count() == 10
    older = HTML.replace("07-Oct-26", "01-Oct-26")
    result = run_ingestion(db, older)
    assert result["status"] == "failed"
    assert any("Source-date regression" in f["error"] for f in result["extraction_failures"])
    assert db.query(MutualFund).filter_by(is_active=True).count() == 10
    assert db.query(MutualFundSnapshot).count() == 10


def test_partial_invalid_and_totally_invalid_pages_keep_evidence(db):
    def bad(table):
        table.select_one("thead th").string = "Unexpected date header"

    result = run_ingestion(db, mutate_table("Equity Fund", bad))
    assert result["status"] == "partial"
    assert result["snapshots_created"] == 9
    assert db.query(FetchRun).one().status == FetchRunStatus.FAILED
    result = run_ingestion(db, "<html>Upstream error</html>")
    assert result["status"] == "failed"
    assert result["snapshots_created"] == 0
    assert db.query(RawRecord).count() == 2
    assert db.query(MutualFundSnapshot).count() == 9


def test_api_provider_filter_and_latest_dates(db):
    from app.main import app

    run_ingestion(db)
    repo = MutualFundRepository(db)
    fund = repo.get_by_code("united-capital-equity")
    # Simulate an older legacy row collected later; current is still the newest source date.
    first = repo.latest_snapshot(fund.id)
    from app.models.enums import ProviderName
    from app.repositories.fetch_run import FetchRunRepository

    extra = FetchRunRepository(db).create_pending(ProviderName.UNITED_CAPITAL)
    db.add(
        MutualFundSnapshot(
            fund_id=fund.id,
            fetch_run_id=extra.id,
            raw_record_id=first.raw_record_id,
            valuation_date=date(2026, 9, 1),
            captured_at=datetime.now(UTC) + timedelta(days=1),
            bid_price=99,
        )
    )
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        response = client.get("/mutual-funds/?provider=united_capital")
        assert response.status_code == 200
        assert response.json()["data"]["pagination"]["total"] == 10
        latest = client.get("/mutual-funds/united-capital-equity/latest-snapshot").json()["data"]
        assert latest["valuation_date"] == "2026-10-07"
        assert Decimal(str(latest["ytd_return_percent"])) == Decimal("46.29")
        assert latest["yield_percent"] is latest["nav_per_unit"] is None
        assert latest["captured_at"]
    finally:
        app.dependency_overrides.clear()


def test_manual_trigger_schedule_and_dispatch(db):
    from app.dependencies.auth import require_admin
    from app.main import app
    from app.services.ingestion.manual import run_provider_ingestion_job

    run_ingestion(db)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[require_admin] = lambda: None
    try:
        client = TestClient(app)
        with patch("app.services.provider.launch_provider_ingestion_job") as launch:
            assert (
                client.post("/providers/united_capital/ingestion-runs/market_data").status_code
                == 202
            )
            assert launch.call_args.kwargs["job_type"] == IngestionJobType.MARKET_DATA
            for job in ["fees", "kyc"]:
                assert (
                    client.post(f"/providers/united_capital/ingestion-runs/{job}").status_code
                    == 400
                )
                assert (
                    client.put(
                        f"/providers/united_capital/ingestion-schedules/{job}",
                        json={"interval_minutes": 180},
                    ).status_code
                    == 400
                )
            assert (
                client.post(
                    "/providers/united_capital/ingestion-runs/market_data?include_kyc=true"
                ).status_code
                == 400
            )
        assert (
            client.put(
                "/providers/united_capital/ingestion-schedules/market_data",
                json={"interval_minutes": 180, "is_enabled": False},
            ).status_code
            == 200
        )
    finally:
        app.dependency_overrides.clear()
    with patch.object(
        UnitedCapitalIngestionService, "ingest_market_data", new_callable=AsyncMock
    ) as run:
        asyncio.run(
            IngestionSchedulerService()._dispatch_job(
                db=db, provider_slug="united_capital", job_type=IngestionJobType.MARKET_DATA
            )
        )
        with (
            patch("app.services.ingestion.manual.SessionLocal", return_value=db),
            patch("app.services.ingestion.manual.ProviderMetricService"),
        ):
            asyncio.run(
                run_provider_ingestion_job(
                    provider_slug="united_capital", job_type=IngestionJobType.MARKET_DATA
                )
            )
        assert run.await_count == 2


def test_bounded_transient_fetch_retries():
    adapter = UnitedCapitalAdapter()
    transient = httpx.ConnectError("temporary")
    with (
        patch(
            "app.adapters.mutual_fund.united_capital.get_html",
            new_callable=AsyncMock,
            side_effect=[transient, HTML],
        ) as fetch,
        patch("app.adapters.mutual_fund.united_capital.asyncio.sleep", new_callable=AsyncMock),
    ):
        assert asyncio.run(adapter.fetch_page()) == HTML
        assert fetch.await_count == 2
    with (
        patch(
            "app.adapters.mutual_fund.united_capital.get_html",
            new_callable=AsyncMock,
            side_effect=transient,
        ) as fetch,
        patch("app.adapters.mutual_fund.united_capital.asyncio.sleep", new_callable=AsyncMock),
    ):
        with pytest.raises(httpx.ConnectError):
            asyncio.run(adapter.fetch_page())
        assert fetch.await_count == 3


def test_verified_name_alias_keeps_same_internal_identity():
    soup = BeautifulSoup(HTML, "html.parser")
    tab = next(
        t for t in soup.select("[role=tab]") if t.get_text(" ", strip=True) == "Eurobond Fund"
    )
    tab.select_one(".e-n-tab-title-text").string = "Nigerian Eurobond Fund"
    result = parse(str(soup))
    assert not result.failures
    assert len([r for r in result.records if r.code == "united-capital-nigerian-eurobond"]) == 1


def test_duplicate_tab_targets_and_missing_funds_are_reported():
    soup = BeautifulSoup(HTML, "html.parser")
    tabs = soup.select("[role=tab]")
    tabs[1]["aria-controls"] = tabs[0]["aria-controls"]
    assert len(parse(str(soup)).records) == 8
    assert parse(str(soup)).failures
    soup = BeautifulSoup(HTML, "html.parser")
    soup.select("[role=tab]")[0].decompose()
    result = parse(str(soup))
    assert len(result.records) == 9
    assert any("Missing" in failure["error"] for failure in result.failures)


def test_explicit_zero_record_is_not_empty_and_unresolved_malformed_is_nonblocking():
    def zero(table):
        cells = table.select_one("tbody tr").select("td")
        for cell in cells[1:4]:
            cell.string = "0"
        cells[4].string = "bad%%"

    result = parse(mutate_table("Equity Fund", zero))
    record = next(r for r in result.records if r.code == "united-capital-equity")
    assert record.bid_price == record.offer_price == record.ytd_return_percent == 0
    assert record.yield_percent is None
    assert any(w["type"] == "malformed_unresolved_metric" for w in result.warnings)


def test_fetch_failure_records_failed_run_without_data_loss(db):
    run_ingestion(db)
    adapter = UnitedCapitalAdapter()
    adapter.fetch_page = AsyncMock(side_effect=httpx.ConnectError("offline"))
    with pytest.raises(httpx.ConnectError):
        asyncio.run(UnitedCapitalIngestionService(db, adapter=adapter).ingest_market_data())
    assert db.query(MutualFundSnapshot).count() == 10
    assert db.query(RawRecord).count() == 1
    assert db.query(FetchRun).order_by(FetchRun.id.desc()).first().status == FetchRunStatus.FAILED


def test_one_persistence_failure_does_not_rollback_other_funds(db):
    persist = MutualFundRepository.persist_dated

    def fail_one(repository, **kwargs):
        if kwargs["record"].code == "united-capital-equity":
            raise RuntimeError("fund write failed")
        return persist(repository, **kwargs)

    with patch.object(MutualFundRepository, "persist_dated", fail_one):
        result = run_ingestion(db)
    assert result["status"] == "partial"
    assert db.query(MutualFundSnapshot).count() == 9
    assert any("fund write failed" in f["error"] for f in result["extraction_failures"])


def test_saving_funds_does_not_reload_the_source_blob(db):
    from sqlalchemy import event

    raw_reads = []

    def observe(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT") and "FROM raw_records" in statement:
            raw_reads.append(statement)

    event.listen(db.bind, "before_cursor_execute", observe)
    try:
        result = run_ingestion(db)
    finally:
        event.remove(db.bind, "before_cursor_execute", observe)
    assert result["snapshots_created"] == 10
    # One initial refresh by RawRecordRepository; no re-read for each fund commit.
    assert len(raw_reads) == 1


def test_published_metrics_expose_all_live_table_columns_and_old_evidence(db):
    from app.main import app

    result = run_ingestion(db)
    money = next(r for r in result["latest_data"] if r["code"] == "united-capital-money-market")
    assert money["persistence_status"] == "saved"
    assert len(money["published_metrics"]) == 4
    assert money["published_metrics"][-1]["value"] == "15.38"
    # Earlier ingestion versions saved cells/context without the new metrics list.
    raw = db.query(RawRecord).one()
    context = dict(raw.payload["source_context"])
    for fund in context.values():
        fund.pop("published_metrics", None)
    raw.payload = {**raw.payload, "source_context": context}
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        listing = client.get("/mutual-funds/?provider=united_capital").json()["data"]["items"]
        assert len(listing) == 10
        for fund in listing:
            snap = fund["latest_snapshot"]
            assert snap and len(snap["published_metrics"]) == 4
            assert snap["source_url"] == UnitedCapitalAdapter.source_url
        fund = next(f for f in listing if f["code"] == "united-capital-money-market")
        metrics = fund["latest_snapshot"]["published_metrics"]
        assert metrics[2]["value"] is None and metrics[2]["status"] == "not_published"
        assert metrics[3]["label"] == "Effective Yield Day on Day Return"
        assert Decimal(metrics[3]["value"]) == Decimal("15.38")
        assert metrics[3]["interpretation"] == "unresolved_yield_or_daily_return"
        response = client.get("/mutual-funds/united-capital-money-market/latest-snapshot").json()[
            "data"
        ]
        assert response["published_metrics"] == metrics
        assert response["yield_percent"] is None  # Still not claimed to be an annual yield.
    finally:
        app.dependency_overrides.clear()


def test_fund_listing_does_not_load_full_source_html_or_issue_per_fund_queries(db):
    from sqlalchemy import event

    from app.services.mutual_fund import MutualFundService

    run_ingestion(db)
    statements = []

    def observe(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(db.bind, "before_cursor_execute", observe)
    try:
        result = MutualFundService(MutualFundRepository(db)).list_funds(
            page=1, per_page=20, provider_slug="united_capital"
        )
    finally:
        event.remove(db.bind, "before_cursor_execute", observe)
    assert len(result.data.items) == 10
    raw_queries = [s for s in statements if "FROM raw_records" in s]
    assert len(raw_queries) == 1
    assert "raw_records.raw_text" not in raw_queries[0]
    assert len(statements) <= 5
