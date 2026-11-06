# Stanbic mutual-fund ingestion

Provider `stanbic` represents Stanbic IBTC Asset Management. The implementation
retains two mutual-fund tables and one Stanbic ingestion service, with two
independent jobs. No schedules are automatically enabled.

## Sources and jobs

### `market_data`

The adapter fetches the [BluNest listing](https://blunest.stanbicibtcassetmanagement.com/v2/invest-now/)
once per run. Fund codes come from analysis links (for example `stanbic-simm`),
not display names. Each valid fund produces a decimal-valued snapshot containing
published bid/offer prices or yield. Changed names retain the same identity.

`16.24` means 16.24%. The published label `Indicative Yield` is preserved; this is
not a historical one-year return. Bid/offer prices are not substituted for NAV.
Collection time is not a valuation date. The current listing does not publish NAV
or a valuation date; these remain null. Yield-change and illustrative-profit
figures from dashboards are not collected or used to calculate investment returns.

A unique `(fund_id, fetch_run_id)` constraint prevents same-run duplicate snapshots.
Separate runs may record unchanged values. Fetch failures and invalid cards do not
deactivate funds or overwrite previous snapshots. Valid cards can still be saved
when other cards fail, using `FAILED` status with metadata status `partial`.

### `fund_details`

Run market-data ingestion first to populate the catalogue. The details job fetches
the listing to rediscover analysis links, then each matched BluNest analysis page
and explicitly mapped official product page at most once. It uses a shared HTTP
client, 30-second request timeouts and sequential requests. Each unique URL has one
capture operation per run, cached on success or exhausted failure: at most 19 pages
for nine funds. Transient transport errors and HTTP 408/429/500/502/503/504 receive
one retry after 0.5 seconds (at most 38 request attempts in the worst case). Other
HTTP errors are not retried. Unexpected hosts, non-HTTPS URLs and redirects are
not followed. Unknown codes are reported for mapping review, not guessed.

Verified product URLs are recorded explicitly in `OFFICIAL_PRODUCT_URLS` in
`app/adapters/mutual_fund/stanbic.py`. Each page's product heading is checked against
the mapped fund. The Enhanced fund has verified long/short name variants.

| Stable code | Verified official product page |
| --- | --- |
| `stanbic-simm` | [Stanbic IBTC Money Market Fund](https://www.stanbicibtcassetmanagement.com/nigeriaassetmanagement/individual-investor/products-and-services/mutual-funds/fixed-income-funds/Stanbic-IBTC-Money-Market-Fund) |
| `stanbic-sidf` | [Stanbic IBTC Dollar Fund](https://www.stanbicibtcassetmanagement.com/nigeriaassetmanagement/individual-investor/products-and-services/mutual-funds/fixed-income-funds/stanbic-ibtc-dollar-fund/stanbic-ibtc-dollar-fund) |
| `stanbic-siefif` | [Stanbic IBTC Enhanced Short-Term Fixed Income Fund](https://www.stanbicibtcassetmanagement.com/nigeriaassetmanagement/individual-investor/products-and-services/mutual-funds/fixed-income-funds/Stanbic-IBTC-enhanced-short–term-fixed-income-fund/Stanbic-IBTC-Enhanced-Short–Term-Fixed-Income-Fund) |
| `stanbic-sigf` | [Stanbic IBTC Guaranteed Investment Fund](https://www.stanbicibtcassetmanagement.com/nigeriaassetmanagement/individual-investor/products-and-services/mutual-funds/fixed-income-funds/Stanbic-IBTC-Guaranteed-Investment-Fund) |
| `stanbic-sfif` | [Stanbic IBTC Shari’ah Fixed Income Fund](https://www.stanbicibtcassetmanagement.com/nigeriaassetmanagement/individual-investor/products-and-services/mutual-funds/fixed-income-funds/sibtc-shariah-fixed-income-fund/Stanbic-IBTC-Shari’ah-Fixed-Income-Fund) |
| `stanbic-sibal` | [Stanbic IBTC Balanced Fund](https://www.stanbicibtcassetmanagement.com/nigeriaassetmanagement/individual-investor/products-and-services/mutual-funds/Stanbic-IBTC-Balanced-Fund) |
| `stanbic-snef` | [Stanbic IBTC Nigerian Equity Fund](https://www.stanbicibtcassetmanagement.com/nigeriaassetmanagement/individual-investor/products-and-services/mutual-funds/equity-biased-funds/stanbic-ibtc-nigerian-equity-fund) |
| `stanbic-stef` | [Stanbic IBTC Ethical Fund](https://www.stanbicibtcassetmanagement.com/nigeriaassetmanagement/individual-investor/products-and-services/mutual-funds/equity-biased-funds/Stanbic-IBTC-Ethical-Fund) |
| `stanbic-simaan` | [Stanbic IBTC Imaan Fund](https://www.stanbicibtcassetmanagement.com/nigeriaassetmanagement/individual-investor/products-and-services/mutual-funds/equity-biased-funds/Stanbic-IBTC-Imaan-Fund) |

The mappings were reverified against links in the [official catalogue](https://www.stanbicibtcassetmanagement.com/nigeriaassetmanagement/individual-investor/products-and-services/mutual-funds)
and each product heading on 2026-10-23. BluNest analysis links are discovered
from each listing card, rather than constructed from a name. Example sources:

- [Money Market analysis](https://blunest.stanbicibtcassetmanagement.com/v2/invest-now/fund/simm)
- [Official Money Market product](https://www.stanbicibtcassetmanagement.com/nigeriaassetmanagement/individual-investor/products-and-services/mutual-funds/fixed-income-funds/Stanbic-IBTC-Money-Market-Fund)

## Details, units and precedence

All details are nullable columns on `mutual_funds` and are returned by the existing
fund-list API. A separate parsed-details schema leaves price/yield validation intact.

| Field | Preferred source / extraction |
| --- | --- |
| `minimum_initial_investment` | BluNest: `Minimum Initial Investment` |
| `minimum_topup` | BluNest: `Minimum Subsequent Subscription` |
| `minimum_holding_days` | BluNest: `Minimum Holding Days`, explicit whole days |
| `risk_label` | BluNest: `Investment Risk`, published wording |
| `management_fee_percent_pa` | Official product Highlights, explicit annual management fee |
| `distribution_frequency` | Official product Highlights, explicit distribution-frequency statement |
| `structure` | Official product Highlights, explicit open/closed-ended statement |

Official Highlights can provide fallback monetary minimums, holding days and risk
when their scope matches. Monetary minimums require an explicit matching currency
(`NGN`/`N`/`₦` or `USD`/`US$`/`$`); unit-based subscriptions and unlabelled amounts
are not converted to cash. Explicit “multiples of” cash conditions are retained
in field metadata. Percentages are decimals, with `1.5` meaning 1.5% per
annum. Annual fees are populated only when that basis is explicit. Published fees
are not deducted from yields, which may already be net of fees.

Holding period is separate from maturity and fund structure. An explicit statement
of no minimum holding period can yield zero days. Missing or malformed fields never
clear prior valid values. New observations update provenance even when unchanged.
The details job does not create price snapshots or deactivate missing funds.

## Provenance, conflicts and failures

Every fetched page is saved separately in `raw_records`, with its exact fetched URL
and original HTML, before extraction. Parsing failures retain that evidence. A page
failure does not stop the remaining funds or the corresponding alternative source.

`details_metadata.fields.<field>` stores the selected value, source URL,
`raw_record_id`, `observed_at`, `last_successful_observation_at` (compatibility key),
source kind, `source_label`, published label and supporting text. No effective or
reporting date is inferred; none was published for the extracted profile conditions
in the inspected content. Its `observations` list retains the latest valid source
candidates.
Whole-object JSON assignment ensures SQLAlchemy persists changes reliably.

On first observation, field-specific source precedence selects the value. When
sources disagree, both observations are preserved and a conflict is reported. A
conflicting different source cannot replace a previously verified value; a new
observation from that verified source refreshes its provenance. That source remains
first in subsequent selection, so legitimate changes from it are also accepted even
when another source disagrees. Its earlier original pages remain in raw history.
Conflict evidence is retained in
`details_metadata.conflicts` and in the run metadata; no semantic equivalence is
assumed between different risk labels.

Each details run records funds processed, fields updated, fields observed, extraction
failures and conflicts in `fetch_runs.metadata_json`. Per-source `field_checks`
distinguish `available`, `not_published`, and `failed_to_parse`. A previously observed
source label/value disappearing adds an `unexpected_loss` diagnostic and an
extraction failure. Failed checks never refresh field observation timestamps.
A listing failure is reported but does not stop verified official product pages.
Partial runs use database status
`FAILED` and metadata status `partial`; total failures use `failed`. Inspect metadata
rather than treating the trigger's HTTP 202 as completed ingestion.

### Current source limitations

The inspected pages have different risk labels across the two sites. Nigerian
Equity and Ethical holding periods differ (BluNest 90 days versus official 91 days),
and Imaan differs (BluNest 90 days versus the official no-minimum statement).
These are retained as conflicts; the scraper does not resolve them by inference.

The Dollar and Ethical official Highlights publish management-fee percentages
without an annual basis; their annual fee fields remain null and the omission is
reported. Distribution frequency is currently extracted only where explicitly
published in Highlights (Money Market). Other absent values remain null.

### Verified extraction coverage (2026-10-23)

This is a **read-only live-page check**, separate from fixture and database tests.
The listing, catalogue and all 18 individual source pages were retrieved without
running ingestion or accessing a configured database. The local Python TLS client
failed during this check; certificate-verified curl retrieved the pages, including
a successful retry of the Ethical analysis page. The final parsers were then run
on all downloaded original HTML. This verifies HTML extraction, not a successful
end-to-end live ingestion run through the Python HTTP client.

The first four fields below use BluNest on initial selection; fees, frequency and
structure use official Highlights. `—` denotes no supported value, not zero.
Every listed fund explicitly supports `open_ended` structure.

| Code suffix | Currency | Initial | Top-up | Holding days | Published risk | Annual management fee % | Distribution |
| --- | --- | ---: | ---: | ---: | --- | ---: | --- |
| simm | NGN | 5,000 | 5,000 | 30 | Low | 1.5 | quarterly |
| sidf | USD | 100 | 100 | 182 | Moderate | — | — |
| siefif | NGN | 5,000 | 5,000 | 90 | Moderate | 1.25 | — |
| sigf | NGN | 5,000 | 5,000 | 91 | Moderate | 1.5 | — |
| sfif | NGN | 5,000 | 5,000 | 0 | Low | 1.5 | — |
| sibal | NGN | 5,000 | 5,000 | 91 | High | 1.25 | — |
| snef | NGN | 5,000 | 5,000 | 90 | High | 3.0 | — |
| stef | NGN | 5,000 | 5,000 | 90 | High | — | — |
| simaan | NGN | 5,000 | 5,000 | 90 | High | 1.5 | — |

Coverage: monetary minimums, top-ups, holding days, risk and structure for 9/9 funds;
explicit annual management fees for 7/9; distribution frequency for 1/9. Official
fallback top-up is explicit only for Dollar; other top-ups rely on BluNest.

| Code suffix | BluNest risk / official risk | BluNest / official holding days when conflicting |
| --- | --- | --- |
| simm | Low / Conservative | — |
| sidf | Moderate / Aggressive | — |
| siefif | Moderate / Moderately Aggressive | — |
| sigf | Moderate / Aggressive | — |
| sfif | Low / Aggressive | — |
| sibal | High / Moderately Aggressive | — |
| snef | High / Aggressive | 90 / 91 |
| stef | High / Aggressive | 90 / 91 |
| simaan | High / Aggressive | 90 / 0 (explicit no minimum) |

## Migration and execution

This increment requires **no new migration**: the fields, enum, read APIs, manual
dispatch and scheduler support already exist (current Alembic head `z6a7b8c9d0e1`).
No migration was applied during this increment.

The initial migration is `x4e5f6a7b8c9`; the existing migration
`y5f6a7b8c9d0` adds the eight nullable details columns and the `FUND_DETAILS` enum value.
It does not rewrite the initial migration. Apply pending migrations through the
normal process against the intended database when ready:

```sh
python -m alembic -c app/alembic.ini upgrade head
```

Standalone manual execution, in order for a new catalogue:

```sh
python -m app.scripts.run_stanbic_ingestion --job-type market_data
python -m app.scripts.run_stanbic_ingestion --job-type fund_details
```

Existing admin-protected manual triggers:

```text
POST /providers/stanbic/ingestion-runs/market_data
POST /providers/stanbic/ingestion-runs/fund_details
```

Independent admin-protected schedule configuration:

```text
PUT /providers/stanbic/ingestion-schedules/market_data
PUT /providers/stanbic/ingestion-schedules/fund_details
```

Suggested polling settings are 180 minutes for `market_data` and 1440 minutes for
`fund_details`. These are our polling intervals, not promises about Stanbic's
publication frequency. An example configuration that remains disabled is:

```json
{"interval_minutes": 1440, "is_enabled": false}
```

Only deliberately enable a schedule when ready, with
`ENABLE_INGESTION_SCHEDULER=true` on the server. Separate Stanbic fees/KYC jobs and `include_kyc`
remain unsupported. United Capital has its own independent `fund_details` job;
its implementation was not modified in this increment.

## APIs and verification

```text
GET /mutual-funds/?provider=stanbic&page=1&per_page=20
GET /mutual-funds/stanbic-simm/latest-snapshot
```

Fund listings expose details and provenance. Latest-snapshot retrieval continues to
return prices/yield only, ordered by capture time and ID. Unknown funds and funds
without snapshots return 404. Existing response and pagination envelopes are used.

```sh
python -m pytest tests -q -p no:cacheprovider
ruff check app/adapters/mutual_fund/stanbic.py app/services/ingestion/stanbic.py tests/test_stanbic_details.py
```

Tests use saved source markup and SQLite with foreign keys enabled. They cover
stable matching, nulls/zeros, currency/units, annual-fee basis, provenance, conflicts,
per-page failures, unchanged observations, source retention, duplicate prevention,
API output, repeated labels and navigation noise, bounded retries, missing-label
diagnostics, chosen-source changes and independent manual/scheduler dispatch.
The regression run passed 165 tests, including United Capital coverage; scoped Ruff
checks passed. Existing framework deprecation warnings remain. Earlier verification
covered the migration chain and details migration downgrade/re-upgrade against a
disposable local PostgreSQL database, including existing-row preservation. No live database changes,
recurring jobs or deployments were performed. Standalone ingestion does not require `SECRET_KEY`; API authentication does.
