# United Capital mutual-fund market data

Provider slug: `united_capital`. This implementation adds one adapter and one
provider-specific ingestion service with separate market-data and product-details jobs,
using the existing mutual-fund tables, source
records, fetch runs, read APIs, admin triggers and scheduler. Stanbic configuration
and undated snapshot selection remain unchanged.

## Sources and verified coverage

- [Fund prices](https://unitedcapitalplcgroup.com/fund-prices/): the only page fetched
  during market-data ingestion.
- [Asset-management catalogue](https://unitedcapitalplcgroup.com/asset-management/):
  identifies the current fund range and links to official product descriptions.

The current ten funds were verified on 2026-10-23. Codes are explicit, stable
identities, independent of DOM order and display-name spelling. Unknown fund
sections are reported, not assigned invented identities or classifications.

| Internal code (prefix `united-capital-`) | Product description | Currency | Classification |
| --- | --- | --- | --- |
| `money-market` | [Money Market](https://unitedcapitalplcgroup.com/money-market-fund/) | NGN | money_market |
| `stable-income` | [Stable Income](https://unitedcapitalplcgroup.com/stable-income-fund/) | NGN | fixed_income |
| `balanced` | [Balanced](https://unitedcapitalplcgroup.com/balanced-fund/) | NGN | balanced |
| `children-investment` | [Children Investment](https://unitedcapitalplcgroup.com/children-investment-fund/) | NGN | mixed_asset |
| `equity` | [Equity](https://unitedcapitalplcgroup.com/equity-fund/) | NGN | equity |
| `nigerian-eurobond` | [Nigerian Eurobond](https://unitedcapitalplcgroup.com/nigerian-eurobond-fund/) | USD | fixed_income |
| `wealth-for-women` | [Wealth for Women](https://unitedcapitalplcgroup.com/wealth-for-women-fund/) | NGN | mixed_asset |
| `global-fixed-income` | [Global Fixed Income](https://unitedcapitalplcgroup.com/global-fixed-income-fund/) | USD | fixed_income |
| `sukuk` | [Sukuk](https://unitedcapitalplcgroup.com/sukuk-fund/) | NGN | shariah_fixed_income |
| `fixed-income` | [Fixed Income](https://unitedcapitalplcgroup.com/fixed-income-fund/) | NGN | fixed_income |

Classifications reflect published investment policies. Wealth for Women explicitly
combines fixed income and equities; it is not classified solely by its name.
Children Investment's NGN base currency and mixed-asset policy were additionally
verified in the catalogue-linked [September 2026 official factsheet](https://unitedcapitalplcgroup.com/factsheet/september-2026/United-Capital-Children-Investment-Fund.pdf).
The factsheet is used for identity/classification verification, not price scraping.
No fees, KYC, assets under management, or calculators are collected.

## Actual HTML structure and source observations

All ten tables are in the initial HTML; browser rendering is unnecessary. Each
named `[role=tab]` button's `aria-controls` identifies its corresponding panel.
Exactly one table must belong to that panel. Its `aria-label`, when present, must
agree with the controlling fund. Table IDs and positions are not fund mappings.
Verified label aliases include `Eurobond Fund`/`Nigerian Eurobond Fund` and the
Money Market table's `MoneyMarket Funds` spelling.

Published headers are:

1. A blank/BOM date heading.
2. `Bid Price`.
3. `Offer price`.
4. `Year- to – Date Returns`.
5. `Effective Yield Day on Day Return`.

On 2026-10-23, read-only verification of the fetched full HTML selected **2026-10-07
for every fund**. This is a source observation, not a hardcoded date or evidence of
current prices. Those observations were 16 calendar days old.

The source includes blank spacer rows, identical duplicates, and contradictory
older records: Equity has conflicts on 12/13 November 2025, and Money Market has
conflicting October 2024 rows. Stable Income also has an older malformed YTD cell
(`20.05%%` on 8 December 2025). The parser reports historical conflicts/malformed
numbers without using them to replace a valid newer observation.

## Metrics and latest-record selection

- Bid and offer populate their own decimal columns. They never populate NAV.
- Published YTD return populates nullable `ytd_return_percent`, separately from yield.
  Negative returns are valid. `16.24` means 16.24%, including when a source cell is
  a bare decimal; there is no implicit multiplication by 100.
- Money Market currently has no latest YTD value. The other nine latest rows do.
- NAV is not published in the price table and remains null.
- The final column is unresolved: its combined yield/day-return label does not
  establish equivalent meaning across funds. It is **not** mapped into yield.
  `yield_percent` and `yield_label` remain null for this integration. Its exact
  published label, original cells and conservatively parsed percentage are retained
  in `raw_records.payload.source_context` and exposed through snapshot
  `published_metrics`, with a warning when populated. This does
  not block usable bid/offer or YTD data. A malformed unresolved cell is also warned
  about, without discarding otherwise valid supported metrics.
- Original HTML, fetched URL, table IDs, headers and selected rows remain available
  as raw evidence, even if extraction fails.

Dates are parsed from observed English day-month-year formats, including `Sept`,
full month names (`June`, `July`) and two-/four-digit years. Two-digit years are
interpreted as 2000–2099 for this feed. Dates are selected by maximum source date,
not DOM order. Identical latest rows collapse after decimal/date normalization;
conflicting latest rows invalidate that fund. An invalid newest financial row
cannot silently fall back to older data. Future source dates are rejected against
`Africa/Lagos` today. Unparseable nonblank dates or malformed row widths invalidate
the fund because newest-date selection cannot be verified safely.

Missing markers and blank cells remain null, while explicit zero remains zero.
Malformed/non-finite supported metrics are rejected. Every record requires at least
one usable supported price, yield or YTD-return metric.

## Persistence and freshness

Provider registration and fund creation are idempotent. Fund codes are globally
unique; same-run snapshot uniqueness remains `(fund_id, fetch_run_id)`.
Separate successful runs may save unchanged observations.

Each fund commits independently under the existing provider-row lock. A bad fund
does not roll back saved peers. No missing/failed fund is deactivated, and historical
snapshots are never erased. Runs with extraction or persistence failures use the
existing `FAILED` database status and metadata status `partial` or `failed`.
Warnings alone do not invalidate usable market data.

United Capital-specific dated persistence rejects a valuation date older than the
newest verified observation. A source-date regression is reported and saves no new
snapshot for that fund. Its latest-snapshot API orders by source valuation date,
then capture time and ID, so older late-collected legacy rows cannot become current.
Stanbic retains its capture-time ordering for undated snapshots.

Source `valuation_date` and collection `captured_at` remain distinct. Run metadata
records each parsed fund's source date, age in calendar days and `is_stale` flag,
plus `has_stale_data`, counts, warnings and failures. Configure:

```env
UNITED_CAPITAL_STALE_AFTER_DAYS=7
```

Data older than this threshold may be saved with explicit stale warnings. Seven days
is a **Kompare policy**, not a provider publication commitment. A successful fetch
or a successful run does not establish that the prices are current.

## Migration, execution and API access

Migration `z6a7b8c9d0e1`, based on `y5f6a7b8c9d0`, adds the `UNITED_CAPITAL` provider
enum, registers the provider without duplicates, and adds nullable
`Numeric(24, 8)` `ytd_return_percent`. No additional mutual-fund tables are added.
Apply through the normal process against the intended database when ready:

```sh
python -m alembic -c app/alembic.ini upgrade head
```

Run manually from the project root:

```sh
python -m app.scripts.run_united_capital_ingestion
```

The command logs progress through database preparation, fetching, parsing and each
fund save, including elapsed times. Fetch retries are logged (at most three
attempts with 30-second request timeouts). If a run is slow, the last progress line
identifies the stage still in progress. IDs are cached across commits so saving
funds does not repeatedly download the full raw HTML/JSON from the database.

Standalone ingestion does not require the API authentication signing key. It still
needs database connectivity. Existing admin-protected API routes are:

```text
POST /providers/united_capital/ingestion-runs/market_data
PUT /providers/united_capital/ingestion-schedules/market_data
```

An optional initial polling interval is 180 minutes. To configure without enabling:

```json
{"interval_minutes": 180, "is_enabled": false}
```

No schedules are automatically enabled. Deliberately enable scheduling only when
ready, with `ENABLE_INGESTION_SCHEDULER=true` on the API server. Polling frequency
does not determine provider source-update frequency. United Capital KYC, fees, and `include_kyc` are rejected.
`fund_details` is now independently supported for the verified official product pages.

Shared read APIs:

```text
GET /mutual-funds/?provider=united_capital
GET /mutual-funds/united-capital-equity/latest-snapshot
```

Fund listings now include nested `latest_snapshot` data. Both listing and single-snapshot
responses expose `published_metrics`: all four financial cells with exact published
labels, original text, Decimal values, units, interpretation and `available`,
`not_published` or `invalid` status. This includes the final yield/day-return column
without misclassifying it. Source URL and valuation/collection dates are exposed.
Older saved source contexts are supported without re-ingestion or a new migration;
JSON source-context subtrees are fetched in batches without transferring raw HTML.

Snapshots expose YTD return, yield, source date and collection time as separate
fields. Diagnostics remain available through existing fetch-run/raw-record APIs.

## Verification and limitations

```sh
python -m pytest tests -q
```

Saved HTML fixtures retain actual tab/panel/table relationships and representative
source rows. Tests cover mapping, reordered sections, aliases, units, nulls/zeros,
negative returns, unresolved metrics, date ordering, duplicates, invalid/future
newest rows, staleness, regressions, partial failures, raw evidence, idempotency,
API responses and manual/scheduled dispatch. Existing Stanbic tests run as well.

The actual downloaded full HTML was parsed read-only: ten valid latest records
were found. This is distinct from fixture tests and is not proof of production
end-to-end ingestion. Migration upgrade/downgrade/re-upgrade and fixture-backed
persistence are checked on disposable PostgreSQL only. No live database ingestion,
deployment or recurring-job activation is performed during implementation.


## Official product details

The adapter also fetches the verified product URLs in the mapping table, independently
of prices. This populates existing nullable fund fields: minimum initial investment,
minimum top-up, minimum holding days, published risk label, distribution frequency,
and structure. Product headings and currency mappings must match the fund code.
No management fee, entry/exit fee or KYC extraction is included.

For example, [Stable Income](https://unitedcapitalplcgroup.com/stable-income-fund/)
explicitly publishes a NGN 50,000,000 initial minimum, NGN 10,000,000 subsequent
multiples, 30 holding days, low risk, annual dividends and open-ended structure.
These values come from page text, not scraper constants. Subsequent multiples are
kept as monetary requirements in the fund currency, including a repeated currency
omitted within the same explicitly denominated statement. Unit-based subscription
blocks are not converted into cash. Inline tags preserve authored digit adjacency:
Eurobond's `9<strong>0 days</strong>` is parsed as 90 days.

Unpublished fields remain null. Missing/malformed details never clear prior values.
Every successful field retains the exact supporting statement, source URL,
raw-record ID and observation timestamp in `details_metadata`. Unchanged observations
refresh provenance. Each page commits independently; partial failures and conflicts
follow the existing fetch-run conventions. Details jobs never create price snapshots.

Run market data first for a new catalogue. Then collect all mapped fund details:

```sh
python -m app.scripts.run_united_capital_ingestion --job-type fund_details
```

Or fetch only the requested Stable Income page:

```sh
python -m app.scripts.run_united_capital_ingestion --job-type fund_details --fund-code united-capital-stable-income
```

The existing admin routes also support independent details jobs and schedules:

```text
POST /providers/united_capital/ingestion-runs/fund_details
PUT /providers/united_capital/ingestion-schedules/fund_details
```

An optional details polling interval is 1440 minutes; market data remains 180 minutes.
No schedules are enabled automatically. Prices and product terms have distinct jobs
so market-data runs do not incur ten additional HTTP requests. No new migration is
required for this increment; it reuses existing columns and saved source evidence.

See the [field-by-field source audit](united-capital-field-audit.md) for the observed
values and explicit blanks across all ten funds. The audit compares the rendered
browser page, raw HTML, parser, persistence and API output using a test database.
