from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import httpx
from bs4 import BeautifulSoup

from app.core import config
from app.core.logger import logger
from app.schemas.mutual_fund import ParsedFund
from app.utils.mutual_fund_metrics import build_published_metrics
from app.utils.scraper import get_browser_headers, get_html

PRICES_URL = f"{config.UNITED_CAPITAL_BASE_URL.rstrip('/')}/fund-prices/"
CATALOGUE_URL = f"{config.UNITED_CAPITAL_BASE_URL.rstrip('/')}/asset-management/"
# Verified product descriptions, not classifications inferred from marketing names.
# Children Investment mixed-asset policy and NGN currency verified in the linked
# September 2026 official factsheet; other policies verified on product pages.
FUND_MAPPINGS = {
    "Children Investment Fund": (
        "children-investment",
        "Children Investment Fund",
        "mixed_asset",
        "NGN",
        "children-investment-fund",
    ),
    "Equity Fund": ("equity", "Equity Fund", "equity", "NGN", "equity-fund"),
    "Balanced Fund": ("balanced", "Balanced Fund", "balanced", "NGN", "balanced-fund"),
    "Wealth for Women Fund": (
        "wealth-for-women",
        "Wealth for Women Fund",
        "mixed_asset",
        "NGN",
        "wealth-for-women-fund",
    ),
    "Sukuk Fund": ("sukuk", "Sukuk Fund", "shariah_fixed_income", "NGN", "sukuk-fund"),
    "Fixed Income Fund": (
        "fixed-income",
        "Fixed Income Fund",
        "fixed_income",
        "NGN",
        "fixed-income-fund",
    ),
    "Eurobond Fund": (
        "nigerian-eurobond",
        "Nigerian Eurobond Fund",
        "fixed_income",
        "USD",
        "nigerian-eurobond-fund",
    ),
    "Global Fixed Income Fund": (
        "global-fixed-income",
        "Global Fixed Income Fund",
        "fixed_income",
        "USD",
        "global-fixed-income-fund",
    ),
    "Money Market Fund": (
        "money-market",
        "Money Market Fund",
        "money_market",
        "NGN",
        "money-market-fund",
    ),
    "Stable Income Fund": (
        "stable-income",
        "Stable Income Fund",
        "fixed_income",
        "NGN",
        "stable-income-fund",
    ),
}
TABLE_ALIASES = {
    "moneymarket funds": "Money Market Fund",
    "eurobond fund": "Eurobond Fund",
    "nigerian eurobond fund": "Eurobond Fund",
}
NUMBER = r"[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"
MISSING = {"", "-", "–", "—", "n/a", "na", "nil"}


def source_today():
    return datetime.now(ZoneInfo("Africa/Lagos")).date()


def parse_decimal(value, *, percent=False):
    text = value.strip().replace("\u00a0", " ")
    if text.lower() in MISSING:
        return None
    if percent and text.endswith("%"):
        text = text[:-1].strip()
    if not re.fullmatch(NUMBER, text):
        raise ValueError(f"Malformed financial number: {value!r}")
    number = Decimal(text.replace(",", ""))
    if not number.is_finite():
        raise ValueError("Non-finite financial number")
    return number


def parse_date(value):
    match = re.fullmatch(r"(\d{1,2})-([A-Za-z]+)-(\d{2}|\d{4})", value.strip())
    if not match:
        raise ValueError(f"Unrecognized valuation date: {value!r}")
    day, month, year = match.groups()
    month = "Sep" if month.lower() == "sept" else month
    year = int(year) + (2000 if len(year) == 2 else 0)
    for fmt in ("%d-%b-%Y", "%d-%B-%Y"):
        try:
            return datetime.strptime(f"{day}-{month}-{year}", fmt).date()
        except ValueError:
            pass
    raise ValueError(f"Invalid valuation date: {value!r}")


def normalize(text):
    return " ".join(text.replace("\ufeff", "").split()).lower()


@dataclass
class ExtractionResult:
    records: list[ParsedFund] = field(default_factory=list)
    failures: list[dict] = field(default_factory=list)
    warnings: list[dict] = field(default_factory=list)
    source_context: dict = field(default_factory=dict)


class UnitedCapitalAdapter:
    source_url = PRICES_URL

    async def fetch_page(self, *, client=None):
        # At most three attempts, only for transport failures or transient HTTP errors.
        for attempt in range(3):
            try:
                return await get_html(
                    self.source_url, client=client, headers=get_browser_headers(), timeout=30
                )
            except (httpx.TransportError, httpx.HTTPStatusError) as exc:
                transient = not isinstance(
                    exc, httpx.HTTPStatusError
                ) or exc.response.status_code in {408, 429, 500, 502, 503, 504}
                if not transient or attempt == 2:
                    raise
                logger.warning(
                    "United Capital: fetch attempt %d/3 failed (%s); retrying",
                    attempt + 1,
                    type(exc).__name__,
                )
                await asyncio.sleep(0.25 * (attempt + 1))

    def parse(self, html, *, today: date | None = None):
        today = today or source_today()
        soup = BeautifulSoup(html, "html.parser")
        result = ExtractionResult()
        tables_by_label = {}
        tab_labels = {normalize(name): name for name in FUND_MAPPINGS}
        panel_owners = {}
        for tab in soup.select('[role="tab"][aria-controls]'):
            panel_owners.setdefault(tab["aria-controls"], []).append(tab)
        for tab in soup.select('[role="tab"][aria-controls]'):
            label = tab.get_text(" ", strip=True)
            canonical = TABLE_ALIASES.get(normalize(label), tab_labels.get(normalize(label)))
            if canonical is None:
                result.failures.append({"fund": label, "error": "Unfamiliar fund section"})
                continue
            panels = soup.find_all(id=tab["aria-controls"])
            if len(panels) != 1 or len(panel_owners[tab["aria-controls"]]) != 1:
                result.failures.append(
                    {"fund": canonical, "error": "Missing or ambiguous tab panel"}
                )
                tables_by_label.setdefault(canonical, []).append(None)
                continue
            tables = panels[0].select("table")
            tables_by_label.setdefault(canonical, []).extend(tables or [None])
        for label, mapping in FUND_MAPPINGS.items():
            slug, name, fund_type, currency, product = mapping
            code = f"united-capital-{slug}"
            tables = tables_by_label.get(label, [])
            try:
                if len(tables) != 1 or tables[0] is None:
                    raise ValueError("Missing, duplicate or ambiguous fund table")
                table = tables[0]
                table_label = table.get("aria-label")
                if table_label:
                    canonical = TABLE_ALIASES.get(
                        normalize(table_label), tab_labels.get(normalize(table_label))
                    )
                    if canonical != label:
                        raise ValueError("Table label contradicts controlling fund tab")
                record, context, warnings = self.parse_table(
                    table,
                    code=code,
                    name=name,
                    fund_type=fund_type,
                    currency=currency,
                    today=today,
                )
                context["product_url"] = f"{config.UNITED_CAPITAL_BASE_URL.rstrip('/')}/{product}/"
                context["tab_label"] = label
                context["published_metrics"] = [
                    m.model_dump(mode="json")
                    for m in build_published_metrics(record, context, currency=currency)
                ]
                result.source_context[code] = context
                result.records.append(record)
                result.warnings.extend(dict(warning, code=code) for warning in warnings)
            except ValueError as exc:
                result.failures.append({"code": code, "fund": label, "error": str(exc)})
        if not result.records and not result.failures:
            result.failures.append({"error": "No fund tabs or usable tables found"})
        return result

    def parse_table(self, table, *, code, name, fund_type, currency, today):
        headers = [h.get_text(" ", strip=True) for h in table.select("thead th")]
        normalized = [normalize(h) for h in headers]
        ytd = "year- to – date returns"
        ambiguous = "effective yield day on day return"
        if len(headers) != 5 or set(normalized) != {"", "bid price", "offer price", ytd, ambiguous}:
            raise ValueError(f"Unexpected fund table headers: {headers}")
        # A blank/BOM date header is the actual published heading; never guess a price column.
        positions = {header: i for i, header in enumerate(normalized)}
        rows_by_date = {}
        for row in table.select("tbody tr"):
            cells = [cell.get_text(" ", strip=True) for cell in row.select("td")]
            if not any(cells):
                continue
            if len(cells) != 5:
                raise ValueError(
                    "Malformed row width; newest observation cannot be determined safely"
                )
            dated = parse_date(cells[positions[""]])
            rows_by_date.setdefault(dated, []).append(cells)
        if not rows_by_date:
            raise ValueError("No dated financial rows")
        newest = max(rows_by_date)
        if newest > today:
            raise ValueError(f"Future valuation date {newest} (Africa/Lagos today {today})")
        warnings = []
        # Older contradictions are reported, but cannot choose or change the newest observation.
        for dated, rows in rows_by_date.items():
            signatures = {tuple(normalize(c) for c in row) for row in rows}
            if len(signatures) > 1 and dated != newest:
                warnings.append(
                    {"type": "historical_duplicate_conflict", "valuation_date": dated.isoformat()}
                )
            if dated != newest:
                for cells in rows:
                    for header in ("bid price", "offer price", ytd, ambiguous):
                        try:
                            parse_decimal(
                                cells[positions[header]], percent=header in {ytd, ambiguous}
                            )
                        except ValueError as exc:
                            warnings.append(
                                {
                                    "type": "historical_malformed_number",
                                    "valuation_date": dated.isoformat(),
                                    "label": headers[positions[header]],
                                    "error": str(exc),
                                }
                            )
        latest = []
        context_rows = []
        for cells in rows_by_date[newest]:
            fields = {
                field: parse_decimal(
                    cells[positions[header]], percent=field == "ytd_return_percent"
                )
                for field, header in [
                    ("bid_price", "bid price"),
                    ("offer_price", "offer price"),
                    ("ytd_return_percent", ytd),
                ]
            }
            # Do not infer a yield from a shared, unresolved yield/day-return header.
            metric_raw = cells[positions[ambiguous]]
            try:
                metric = parse_decimal(metric_raw, percent=True)
                metric_signature = metric
            except ValueError:
                metric = None
                metric_signature = metric_raw
                warnings.append({"type": "malformed_unresolved_metric", "value": metric_raw})
            record = ParsedFund(
                code=code,
                name=name,
                fund_type=fund_type,
                currency=currency,
                valuation_date=newest,
                **fields,
            )
            latest.append((record, metric_signature))
            context_rows.append(
                {
                    "cells": cells,
                    "unresolved_metric": {
                        "label": headers[positions[ambiguous]],
                        "published_value": metric_raw,
                        "parsed_percent": str(metric) if metric is not None else None,
                    },
                }
            )
        first, metric = latest[0]
        if any(record != first or other != metric for record, other in latest[1:]):
            raise ValueError(f"Conflicting rows for newest valuation date {newest}")
        if len(latest) > 1:
            warnings.append(
                {
                    "type": "identical_duplicates_collapsed",
                    "count": len(latest),
                    "valuation_date": newest.isoformat(),
                }
            )
        if any(
            c["unresolved_metric"]["published_value"].strip().lower() not in MISSING
            for c in context_rows
        ):
            warnings.append(
                {"type": "unresolved_yield_or_daily_return", "label": headers[positions[ambiguous]]}
            )
        return (
            first,
            {
                "table_id": table.get("id"),
                "headers": headers,
                "valuation_date": newest.isoformat(),
                "latest_rows": context_rows,
            },
            warnings,
        )

    def product_url(self, code):
        mapping = next(
            (m for m in FUND_MAPPINGS.values() if f"united-capital-{m[0]}" == code), None
        )
        if mapping is None:
            raise ValueError(f"Unknown United Capital fund code: {code}")
        return f"{config.UNITED_CAPITAL_BASE_URL.rstrip('/')}/{mapping[4]}/"

    async def fetch_product_page(self, code, *, client):
        return await get_html(
            self.product_url(code), client=client, headers=get_browser_headers(), timeout=30
        )

    def parse_product_details(self, html, *, code, currency):
        from app.schemas.mutual_fund import ParsedFundDetails

        mapping = next(
            (m for m in FUND_MAPPINGS.values() if f"united-capital-{m[0]}" == code), None
        )
        if mapping is None or currency != mapping[3]:
            raise ValueError("Product code/currency does not match verified fund mapping")
        soup = BeautifulSoup(html, "html.parser")
        expected = {mapping[1]}
        if code == "united-capital-global-fixed-income":
            expected.add("Global Income Fixed Fund")  # Actual official product heading.
        headings = {
            " ".join(h.get_text().split()) for h in soup.select("h2.elementor-heading-title")
        }
        if not expected.intersection(headings):
            raise ValueError(f"Product heading does not match {code}")
        widgets = [
            w
            for w in soup.select(".elementor-widget-text-editor")
            if re.search(
                r"minimum (?:holding|invest|entry)|start with a minimum",
                w.get_text(" ", strip=True),
                re.I,
            )
        ]
        if len(widgets) != 1:
            raise ValueError("Missing or ambiguous product-details content block")
        fields, evidence, failures, invalid = {}, {}, [], set()

        def save(field, value, text):
            try:
                valid = ParsedFundDetails(code=code, currency=currency, **{field: value})
                value = getattr(valid, field)
                if field in fields and fields[field] != value:
                    raise ValueError("Conflicting product statements")
                fields[field] = value
                evidence[field] = {"published_label": text, "supporting_text": text}
            except ValueError as exc:
                invalid.add(field)
                failures.append({"field": field, "error": str(exc), "supporting_text": text})

        cash = r"(?P<unit>US\$|USD|NGN|₦|N|\$)\s*(?P<amount>[^\s]+)"

        def money(unit, amount):
            actual = "USD" if unit.upper() in {"US$", "USD", "$"} else "NGN"
            if actual != currency:
                raise ValueError(f"Published currency {actual} does not match {currency}")
            return parse_decimal(amount.removesuffix("."))

        for node in widgets[0].select("p,li"):
            # Preserve authored spacing inside inline tags: 9<strong>0 days</strong>
            # is 90 days, not a malformed "9 0 days" created by text joining.
            text = " ".join(node.get_text().split())
            section = ""
            if node.name == "li":
                previous = node.parent.find_previous_sibling("p")
                if previous:
                    section = " ".join(previous.get_text().split())
            scoped = f"{section} {text}".strip()
            initial = re.search(
                r"(?:start with a minimum of(?: just)?|subscriptions can start as low as|"
                r"minimum entry amount:|minimum investible amount:(?: initial:)?|"
                r"minimum investable amount of)\s*" + cash,
                scoped,
                re.I,
            )
            if initial:
                try:
                    save(
                        "minimum_initial_investment",
                        money(initial["unit"], initial["amount"]),
                        scoped,
                    )
                    # The second amount is a monetary multiple in the same statement;
                    # an omitted repeated currency inherits the explicit first currency.
                    tail = scoped[initial.end() :]
                    topup = re.search(
                        r"multiples of\s*(?:(US\$|USD|NGN|₦|N|\$)\s*)?([^\s]+)", tail, re.I
                    )
                    if topup and not re.match(r"\s*units\b", tail[topup.end() :], re.I):
                        save(
                            "minimum_topup",
                            money(topup.group(1) or initial["unit"], topup.group(2)),
                            scoped,
                        )
                except ValueError as exc:
                    failures.append(
                        {
                            "field": "minimum_initial_investment",
                            "error": str(exc),
                            "supporting_text": scoped,
                        }
                    )
            subsequent = re.search(
                r"minimum investible amount:\s*subsequent:\s*" + cash, scoped, re.I
            )
            if subsequent:
                try:
                    save("minimum_topup", money(subsequent["unit"], subsequent["amount"]), scoped)
                except ValueError as exc:
                    failures.append(
                        {"field": "minimum_topup", "error": str(exc), "supporting_text": scoped}
                    )
            if re.search(r"minimum holding period", scoped, re.I):
                hold = re.search(
                    r"minimum holding period(?: of)?\s+(\d+)\s+days?\.?$", scoped, re.I
                )
                if hold:
                    save("minimum_holding_days", int(hold.group(1)), scoped)
            risk = re.search(r"\b(low|moderate|high)[ -]risk\b", text, re.I)
            if risk:
                save("risk_label", risk.group(1).capitalize(), text)
            if re.search(r"\bopen\s*[–-]?\s*ended\b", text, re.I):
                save("structure", "open_ended", text)
            distribution = re.search(
                r"\b(quarterly|annual|annually|monthly)\s+dividends?\b", text, re.I
            )
            if not distribution and re.search(r"dividend payout", section, re.I):
                distribution = re.search(r"\b(quarterly|annual|annually|monthly)\b", text, re.I)
            if distribution:
                frequency = distribution.group(1).lower()
                save(
                    "distribution_frequency",
                    "annually" if frequency == "annual" else frequency,
                    scoped,
                )
        for invalid_field in invalid:
            fields.pop(invalid_field, None)
            evidence.pop(invalid_field, None)
        if not fields:
            failures.append({"error": "No supported product details extracted"})
        return ParsedFundDetails(code=code, currency=currency, **fields), evidence, failures
