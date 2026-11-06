from __future__ import annotations

import asyncio
import re
from decimal import Decimal
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from app.core import config
from app.schemas.mutual_fund import ParsedFund
from app.utils.scraper import get_browser_headers, get_html

STANBIC_URL = f"{config.STANBIC_BASE_URL.rstrip('/')}/v2/invest-now/"
# Classification and currency are explicit provider-specific mappings, not price inference.
FUND_DETAILS = {
    "simm": ("money_market", "NGN"),
    "sidf": ("fixed_income", "USD"),
    "siefif": ("fixed_income", "NGN"),
    "sigf": ("guaranteed", "NGN"),
    "sfif": ("shariah_fixed_income", "NGN"),
    "sibal": ("balanced", "NGN"),
    "snef": ("equity", "NGN"),
    "stef": ("ethical_equity", "NGN"),
    "simaan": ("shariah_equity", "NGN"),
}
NUMBER = r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"


def decimal_value(text: str) -> Decimal | None:
    if text.strip() in {"", "-", "—", "N/A"}:
        return None
    if not re.fullmatch(NUMBER, text.strip()):
        raise ValueError(f"Invalid published number: {text!r}")
    return Decimal(text.replace(",", "").strip())


class StanbicAdapter:
    source_url = STANBIC_URL

    async def fetch_page(self, *, client=None) -> str:
        return await self._fetch_html(self.source_url, client=client)

    @staticmethod
    async def _fetch_html(url, *, client):
        # Retry only transient failures, once. Successful pages are cached by the job.
        for attempt in range(2):
            try:
                return await get_html(url, headers=get_browser_headers(), timeout=30, client=client)
            except (httpx.TransportError, httpx.HTTPStatusError) as exc:
                transient = not isinstance(exc, httpx.HTTPStatusError) or (
                    exc.response.status_code in {408, 429, 500, 502, 503, 504}
                )
                if attempt or not transient:
                    raise
                await asyncio.sleep(0.5)

    def parse(self, html: str) -> tuple[list[ParsedFund], list[dict]]:
        soup = BeautifulSoup(html, "html.parser")
        cards = soup.select('li.plan-item[data-category="mutualfund"]')
        if not cards:
            raise ValueError("Stanbic extraction failed: no mutual-fund cards found")
        records, failures = [], []
        seen = set()
        for card in cards:
            title = card.select_one(".plan-item-title")
            name = title.get_text(" ", strip=True) if title else ""
            code = None
            try:
                codes = set()
                for link in card.select("a[href]"):
                    url = urlparse(urljoin(self.source_url, link["href"]))
                    match = re.fullmatch(r"/v2/invest-now/fund/([a-z0-9]+)/?", url.path)
                    if url.netloc == urlparse(self.source_url).netloc and match:
                        codes.add(match.group(1))
                if len(codes) != 1:
                    raise ValueError("Missing or ambiguous stable fund link")
                code = codes.pop()
                if code in seen:
                    raise ValueError(f"Duplicate fund code: {code}")
                seen.add(code)
                if code not in FUND_DETAILS:
                    raise ValueError(f"Unmapped fund code: {code}")
                fund_type, currency = FUND_DETAILS[code]
                price = card.select_one(".fund-price")
                label_node = price.find_next_sibling("span") if price else None
                if price is None or label_node is None:
                    raise ValueError("Missing published value or label")
                value = price.get_text(" ", strip=True)
                label = label_node.get_text(" ", strip=True)
                fields = {}
                if label == "Bid Price / Offer Price":
                    parts = value.split("/")
                    if len(parts) != 2:
                        raise ValueError("Expected bid and offer price")
                    symbol = "$" if currency == "USD" else "₦"
                    for key, part in zip(("bid_price", "offer_price"), parts):
                        fields[key] = decimal_value(part.strip().removeprefix(symbol).strip())
                elif "yield" in label.lower():
                    if not value.endswith("%"):
                        raise ValueError("Yield is missing its percentage unit")
                    fields = {"yield_percent": decimal_value(value[:-1]), "yield_label": label}
                else:
                    raise ValueError(f"Unsupported published value label: {label}")
                records.append(
                    ParsedFund(
                        code=f"stanbic-{code}",
                        name=name,
                        fund_type=fund_type,
                        currency=currency,
                        **fields,
                    )
                )
            except ValueError as exc:
                failures.append({"code": code, "name": name, "error": str(exc)})
        # Ambiguous duplicate cards must not publish either interpretation.
        duplicates = {f["code"] for f in failures if "Duplicate fund code" in f["error"]}
        records = [r for r in records if r.code.removeprefix("stanbic-") not in duplicates]
        return records, failures

    def discover_detail_urls(self, html):
        """Discover analysis links independently of whether today's prices parsed."""
        soup = BeautifulSoup(html, "html.parser")
        urls, failures = {}, []
        duplicates = set()
        for card in soup.select('li.plan-item[data-category="mutualfund"]'):
            try:
                links = set()
                for link in card.select("a[href]"):
                    target = urljoin(self.source_url, link["href"])
                    parsed = urlparse(target)
                    if "/fund/" not in parsed.path or parsed.path.endswith("/subscribe"):
                        continue
                    self.validate_detail_url(target, official=False)
                    if re.fullmatch(r"/v2/invest-now/fund/[a-z0-9]+/?", parsed.path):
                        links.add(target.rstrip("/"))
                if len(links) != 1:
                    raise ValueError("Missing or ambiguous analysis URL")
                url = links.pop()
                code = "stanbic-" + urlparse(url).path.rstrip("/").split("/")[-1]
                if code in urls:
                    duplicates.add(code)
                    raise ValueError(f"Duplicate analysis URL for {code}")
                if code.removeprefix("stanbic-") not in FUND_DETAILS:
                    raise ValueError(f"Unknown fund code: {code}")
                urls[code] = url
            except ValueError as exc:
                failures.append({"error": str(exc)})
        for code in duplicates:
            urls.pop(code, None)
        if not urls:
            raise ValueError(f"No valid fund analysis links: {failures}")
        return urls, failures

    @staticmethod
    def validate_detail_url(url, *, official):
        parsed = urlparse(url)
        host = (
            "www.stanbicibtcassetmanagement.com"
            if official
            else "blunest.stanbicibtcassetmanagement.com"
        )
        if (
            parsed.scheme != "https"
            or parsed.netloc != host
            or parsed.query
            or parsed.fragment
            or parsed.username
        ):
            raise ValueError(f"Unexpected fund-detail URL: {url}")

    async def fetch_blunest_details(self, url, *, client):
        self.validate_detail_url(url, official=False)
        return await self._fetch_html(url, client=client)

    async def fetch_official_details(self, url, *, client):
        self.validate_detail_url(url, official=True)
        return await self._fetch_html(url, client=client)

    def parse_blunest_details(self, html, *, code, currency):
        soup = BeautifulSoup(html, "html.parser")
        headings = soup.select(".card h4")
        # Compare the page's product title with the configured fund, not global navigation.
        expected = OFFICIAL_PRODUCT_NAMES.get(code)
        aliases = (
            {
                OFFICIAL_PRODUCT_NAMES.get("stanbic-siefif"),
                "Stanbic IBTC Enhanced Fixed Income Fund",
            }
            if code == "stanbic-siefif"
            else {expected}
        )
        headings = [h for h in headings if h.get_text(" ", strip=True) in aliases]
        if len(headings) != 1:
            raise ValueError(f"BluNest fund heading does not match {code}")
        scope = headings[0].find_parent(class_="card")
        labels = {
            "Minimum Initial Investment": "minimum_initial_investment",
            "Minimum Subsequent Subscription": "minimum_topup",
            "Minimum Holding Days": "minimum_holding_days",
            "Investment Risk": "risk_label",
        }
        entries = []
        for block in scope.select(".nk-iv-wg3-nav .nk-iv-wg3-sub"):
            if block.find_parent(class_="card") is not scope:
                continue
            label = block.select_one(".nk-iv-wg3-subtitle")
            value = block.select_one(".number-sm")
            if label and label.get_text(" ", strip=True) in labels:
                published_label = label.get_text(" ", strip=True)
                entries.append(
                    (
                        labels[published_label],
                        published_label,
                        value.get_text(" ", strip=True) if value else "",
                    )
                )
        details, evidence, errors = parse_detail_entries(entries, code=code, currency=currency)
        present = {entry[0] for entry in entries}
        errors.extend(
            {"field": field, "error": "Expected BluNest detail label missing"}
            for field in labels.values()
            if field not in present
        )
        return details, evidence, errors

    def parse_official_details(self, html, *, code, currency):
        soup = BeautifulSoup(html, "html.parser")
        main = soup.select_one("main")
        headings = main.select("h1") if main else []
        if len(headings) != 1 or headings[0].get_text(
            " ", strip=True
        ) != OFFICIAL_PRODUCT_NAMES.get(code):
            raise ValueError(f"Official product heading does not match {code}")
        products = main.select(".tabs__product")
        if len(products) != 1:
            raise ValueError("Missing or ambiguous official product details section")
        lines = set()
        for section in products[0].select(".accordion__items"):
            title = section.select_one(".accordion__title")
            if title and title.get_text(" ", strip=True) == "Highlights":
                lines.update(
                    " ".join(li.get_text(" ", strip=True).split())
                    for li in section.select(".accordion__item-content li")
                )
        if not lines:
            raise ValueError("Official product Highlights missing or empty")
        entries, failures = [], []
        for text in sorted(lines):
            lower = text.lower()
            if "management fee" in lower:
                match = re.search(
                    r"\bmanagement fee(?:\s+(?:of|for)\s+the\s+fund)?\s+is\s+("
                    + NUMBER
                    + r"\s*%)\s*(per annum|p\.?a\.?)\b",
                    text,
                    re.I,
                )
                if match:
                    entries.append(("management_fee_percent_pa", text, match.group(1)))
                else:
                    failures.append(
                        {
                            "field": "management_fee_percent_pa",
                            "error": "Management fee has no valid explicit annual basis",
                            "supporting_text": text,
                        }
                    )
            if "distribution frequency" in lower:
                match = re.search(
                    r"distribution frequency is (quarterly|monthly|annually|semi-annually)\b",
                    text,
                    re.I,
                )
                entries.append(
                    ("distribution_frequency", text, match.group(1).lower() if match else "")
                )
            if re.search(
                r"\b(?:it is|fund is|is an?)\s+(?:an?\s+)?(?:open|closed)[ -]ended", lower
            ):
                match = re.search(r"\b(open|closed)[ -]ended\b", lower)
                entries.append(("structure", text, match.group(1) + "_ended"))
            if "minimum investment amount is" in lower:
                # Delimit a second clause without dropping thousands separators.
                amount = re.split(r",\s*while\b", text, flags=re.I)[0]
                amount = re.split(r"minimum investment amount is\s+", amount, flags=re.I)[-1]
                entries.append(("minimum_initial_investment", text, amount))
                topup = re.search(r"additional investment is\s+(.+)$", text, re.I)
                if topup:
                    entries.append(("minimum_topup", text, topup.group(1)))
            if "minimum holding period" in lower:
                match = re.search(r"\b(\d+)[ -]days?\s+minimum holding period", text, re.I)
                if match:
                    entries.append(("minimum_holding_days", text, match.group(1) + " days"))
                elif re.search(r"\bno minimum holding period\b", lower):
                    entries.append(("minimum_holding_days", text, "0 days"))
                elif "penalty" not in lower and "redeem" not in lower:
                    entries.append(("minimum_holding_days", text, ""))
            if "risk profile" in lower:
                match = re.search(r"risk profile.*?\bis\s+[“\"]([^”\"]+)[”\"]", text, re.I)
                entries.append(("risk_label", text, match.group(1) if match else ""))
        details, evidence, errors = parse_detail_entries(entries, code=code, currency=currency)
        return details, evidence, failures + errors


# Verified from official product navigation and each product heading, 2026-10-23.
OFFICIAL_PRODUCT_URLS = {
    "stanbic-simm": "https://www.stanbicibtcassetmanagement.com/nigeriaassetmanagement/individual-investor/products-and-services/mutual-funds/fixed-income-funds/Stanbic-IBTC-Money-Market-Fund",
    "stanbic-sidf": "https://www.stanbicibtcassetmanagement.com/nigeriaassetmanagement/individual-investor/products-and-services/mutual-funds/fixed-income-funds/stanbic-ibtc-dollar-fund/stanbic-ibtc-dollar-fund",
    "stanbic-siefif": "https://www.stanbicibtcassetmanagement.com/nigeriaassetmanagement/individual-investor/products-and-services/mutual-funds/fixed-income-funds/Stanbic-IBTC-enhanced-short–term-fixed-income-fund/Stanbic-IBTC-Enhanced-Short–Term-Fixed-Income-Fund",
    "stanbic-sigf": "https://www.stanbicibtcassetmanagement.com/nigeriaassetmanagement/individual-investor/products-and-services/mutual-funds/fixed-income-funds/Stanbic-IBTC-Guaranteed-Investment-Fund",
    "stanbic-sfif": "https://www.stanbicibtcassetmanagement.com/nigeriaassetmanagement/individual-investor/products-and-services/mutual-funds/fixed-income-funds/sibtc-shariah-fixed-income-fund/Stanbic-IBTC-Shari’ah-Fixed-Income-Fund",
    "stanbic-sibal": "https://www.stanbicibtcassetmanagement.com/nigeriaassetmanagement/individual-investor/products-and-services/mutual-funds/Stanbic-IBTC-Balanced-Fund",
    "stanbic-snef": "https://www.stanbicibtcassetmanagement.com/nigeriaassetmanagement/individual-investor/products-and-services/mutual-funds/equity-biased-funds/stanbic-ibtc-nigerian-equity-fund",
    "stanbic-stef": "https://www.stanbicibtcassetmanagement.com/nigeriaassetmanagement/individual-investor/products-and-services/mutual-funds/equity-biased-funds/Stanbic-IBTC-Ethical-Fund",
    "stanbic-simaan": "https://www.stanbicibtcassetmanagement.com/nigeriaassetmanagement/individual-investor/products-and-services/mutual-funds/equity-biased-funds/Stanbic-IBTC-Imaan-Fund",
}
OFFICIAL_PRODUCT_NAMES = {
    "stanbic-simm": "Stanbic IBTC Money Market Fund",
    "stanbic-sidf": "Stanbic IBTC Dollar Fund",
    "stanbic-siefif": "Stanbic IBTC Enhanced Short-Term Fixed Income Fund",
    "stanbic-sigf": "Stanbic IBTC Guaranteed Investment Fund",
    "stanbic-sfif": "Stanbic IBTC Shari’ah Fixed Income Fund",
    "stanbic-sibal": "Stanbic IBTC Balanced Fund",
    "stanbic-snef": "Stanbic IBTC Nigerian Equity Fund",
    "stanbic-stef": "Stanbic IBTC Ethical Fund",
    "stanbic-simaan": "Stanbic IBTC Imaan Fund",
}


def parse_detail_entries(entries, *, code, currency):
    from app.schemas.mutual_fund import ParsedFundDetails

    fields, evidence, failures = {}, {}, []
    invalid = set()
    for field, label, value in entries:
        try:
            if field in {"minimum_initial_investment", "minimum_topup"}:
                units = r"(?:₦|NGN|N)" if currency == "NGN" else r"(?:\$|USD|US\$)"
                amount = units + r"\s*(" + NUMBER + r")"
                match = re.fullmatch(
                    amount
                    + r"(?:(?:,\s*|\s+)(?:and\s+)?(?:in\s+)?multiples of\s+"
                    + units
                    + r"\s*"
                    + NUMBER
                    + r")?\.?",
                    value,
                    re.I,
                )
                if not match:
                    raise ValueError(f"Expected explicit {currency} monetary minimum")
                parsed = decimal_value(match.group(1))
            elif field == "minimum_holding_days":
                match = re.fullmatch(r"(\d+)\s+days?", value, re.I)
                if not match:
                    raise ValueError("Expected an explicit whole-day holding period")
                parsed = int(match.group(1))
            elif field == "management_fee_percent_pa":
                if not value.endswith("%"):
                    raise ValueError("Expected a percentage")
                parsed = decimal_value(value[:-1].strip())
            elif field == "risk_label":
                if (
                    value.lower() in {"", "n/a", "not available", "-", "—"}
                    or len(value) > 80
                    or not re.fullmatch(r"[A-Za-z][A-Za-z /()–—-]*", value)
                ):
                    raise ValueError("Missing or unsupported risk label")
                parsed = value
            else:
                parsed = value
            validated = ParsedFundDetails(code=code, currency=currency, **{field: parsed})
            parsed = getattr(validated, field)
            if parsed is None:
                raise ValueError("No value extracted")
            if field in fields and fields[field] != parsed:
                invalid.add(field)
                raise ValueError("Conflicting values within the same page")
            fields[field] = parsed
            previous_evidence = evidence.get(field, {})
            supporting_text = f"{label}: {value}"
            if previous_evidence and supporting_text != previous_evidence["supporting_text"]:
                supporting_text = previous_evidence["supporting_text"] + "\n" + supporting_text
            evidence[field] = {
                "source_label": label,
                "published_label": label,
                "supporting_text": supporting_text,
            }
            conditions = previous_evidence.get("conditions")
            if "multiples of" in value.lower():
                conditions = (
                    conditions + "\n" + value if conditions and conditions != value else value
                )
            if conditions:
                evidence[field]["conditions"] = conditions
        except ValueError as exc:
            invalid.add(field)
            failures.append(
                {
                    "field": field,
                    "error": str(exc),
                    "published_label": label,
                    "supporting_text": value,
                }
            )
    for field in invalid:
        fields.pop(field, None)
        evidence.pop(field, None)
    if not fields:
        failures.append({"error": "No supported fund details extracted"})
    return ParsedFundDetails(code=code, currency=currency, **fields), evidence, failures
