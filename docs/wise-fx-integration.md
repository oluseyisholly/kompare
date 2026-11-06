# Wise adapter within the shared FX integration

The [shared FX architecture](fx-architecture.md) defines provider-keyed APIs and
normalized models. All FX endpoints appear under one **FX** documentation group;
Wise is one implemented adapter within the shared API architecture.

The normal application flow is:

```text
manual/scheduled ingestion → Wise API → database → POST /fx/convert → Decimal calculation
```

**Frontend conversions and currency/rate discovery never contact Wise**, including
missing-rate, stale-rate and empty-catalogue requests. No automatic refresh,
inversion or cross-rate construction occurs. No money movement is implemented.

## Local conversion API

Uses the [unified four-field contract](fx-architecture.md#unified-conversion-contract).
Legacy `rate_side` is rejected with 422 for every provider. `net_target_amount` is
canonical; `estimated_net_target_amount` remains a deprecated alias. Unknown fees
remain null. Observation time is distinct from provider valuation time; rates do
not invent expiry from diagnostic quote lifetimes.

```http
POST /fx/convert
Content-Type: application/json

{"provider":"wise","source_currency":"EUR","target_currency":"USD","source_amount":"100.00"}
```

Only a positive finite **source** amount is supported (up to eight decimal places
and 24 total digits). Currency codes normalize to uppercase. Target amounts,
funding/payout selectors and client-selected environments are rejected.
The selected provider must be active and categorized as FX.

Example response, using a synthetic stored EUR/USD reference rate of 1.166:

```json
{
  "responseCode": 200,
  "message": "Local estimate before fees from stored rates",
  "data": {
    "provider": "wise",
    "source_currency": "EUR",
    "target_currency": "USD",
    "source_amount": "100.00",
    "reference_rate": "1.166",
    "gross_target_amount": "116.60",
    "unrounded_gross_target_amount": "116.60000",
    "target_decimal_places": 2,
    "rounding_policy": "ROUND_HALF_UP",
    "precision_source": "https://www.six-group.com/dam/download/financial-information/data-center/iso-currrency/lists/list-one.xml",
    "fee_status": "unavailable",
    "fee_amount": null,
    "fee_currency": null,
    "net_target_amount": null,
    "estimated_net_target_amount": null,
    "observed_at": "2026-11-02T11:59:45Z",
    "provider_rate_timestamp": "2026-11-02T11:59:30Z",
    "expires_at": null,
    "captured_at": "2026-11-02T11:59:45Z",
    "last_seen_at": "2026-11-02T11:59:45Z",
    "is_stale": false,
    "stale_after_seconds": 3600,
    "rate_record_id": 123,
    "raw_record_id": 456,
    "source_url": "https://api.wise.com/2026Q4/rates",
    "calculation_basis": "stored_reference_rate_estimate",
    "transfer_route_verified": false,
    "executable": false,
    "warnings": [
      "Estimate from stored reference rates; transfer-route availability is not verified.",
      "Fees are unavailable and excluded. The gross amount is not a provider delivery quote."
    ]
  }
}
```

The exact gross result is `source_amount × stored_rate`. Decimal multiplication
uses enough working precision for both operands. The full provider rate comes
from stored `provider_rate` metadata, not the legacy eight-decimal `mid_rate`
column. `unrounded_gross_target_amount` preserves the product; the displayed gross
is rounded once using `ROUND_HALF_UP` and reliable target precision.

A missing direct rate returns HTTP 503 with `data.error: fx_rate_unavailable`.
Provider keys outside the existing `ProviderName` enum return 422. Known enum
members that are unregistered, inactive or non-FX return `fx_provider_unavailable`
(404). Neither
case invokes an adapter. A recent fetch does not make old provider data fresh:
`is_stale` compares the actual provider timestamp with the configured threshold.
Stale results remain explicitly marked estimates and receive a warning.

The calculator/repository are provider-neutral. A future FX ingestion adapter can
write shared quote history with a registered FX provider, an upstream source URL,
and metadata containing `classification: reference_rate`, `provider_rate`,
`provider_time` and `source_url`, together with raw/capture references.

## Fees: currently unavailable for local calculations

The existing `FeeProfile` and `FeeRule` tables were inspected. Generic numeric
rules and condition text do not establish Wise's complete amount/method-specific
pricing, fee treatment, environment, or exact applicability. Neither the official
quote examples nor sampled quotes establish a reusable pricing formula.

The local calculator therefore applies **no Wise fee rule**. It returns the gross
conversion, `fee_status: unavailable`, null fee/currency and null estimated net.
It does not select the cheapest funding method or invent a zero fee. Verified
zero fees in diagnostic observations remain explicit zeroes in those historical
records, distinct from missing fees; they are not extrapolated to other scenarios.
No new generic fee engine was introduced.

## Database-only discovery APIs

```text
GET /fx/{provider}/rates?source=EUR&target=USD&page=1&per_page=20
GET /fx/{provider}/currencies?page=1&per_page=20

# With the Wise provider key:
GET /fx/wise/rates?source=EUR&target=USD&page=1&per_page=20
GET /fx/wise/currencies?page=1&per_page=20
```

Rates and currencies are read from the provider's shared stored dataset.
Responses use the existing pagination/envelope conventions. An empty currency
catalogue returns an empty list and an explicit message to run currency ingestion
when credentials are available. Missing tokens never fabricate a supported list.

Currency rows preserve code, English name, symbol, `supports_decimals`, country
keywords, collection timestamp, source URL and raw/run references.
Currency discovery and reference-rate availability are **not** a supported-route
matrix: neither proves that Wise can execute a transfer for a currency direction.

## Verified currency contract and precision

Checked on **2026-11-02** against the current stable **2026Q4** documentation:

- [Wise currencies API](https://docs.wise.com/api-reference/currencies/currenciesget):
  `GET /2026Q4/currencies`, authenticated with a user/personal bearer token. The
  documented array contains `code`, `name`, `symbol`, `countryKeywords` and
  `supportsDecimals`. Names default to English when no language is requested.
- [Wise reference rates](https://docs.wise.com/api-reference/rate/rateget):
  `GET /2026Q4/rates` without currency filters retrieves all available pairs.
- [SIX ISO 4217 maintenance agency](https://www.six-group.com/en/products-services/financial-information/market-reference-data/data-standards.html)
  and its linked [List One XML](https://www.six-group.com/dam/download/financial-information/data-center/iso-currrency/lists/list-one.xml).

Wise's `supportsDecimals` is a boolean, **not** a number of decimal places.
`false` explicitly establishes zero places. Otherwise the pinned official ISO
minor-unit metadata supplies precision (for example USD 2, JPY 0, KWD 3). The
snapshot in `app/data/iso4217_minor_units.json` was retrieved on 2026-11-02,
published 2026-09-17, and contains 165 codes with numeric minor units. It is
rounding metadata, not Wise currency discovery, route support or market rates.

Harvested currency metadata takes precedence. A contradictory provider flag or
unknown precision remains unknown; we return the exact unrounded gross result
with a warning rather than assume two places. Without harvested currency metadata,
conversion can still use the reliable pinned ISO precision. All precision lookup
is local. Refresh the pinned metadata deliberately when the official list changes.

## Configuration and ingestion

```dotenv
WISE_BASE_URL=https://api.wise.com
WISE_API_VERSION=2026Q4
WISE_API_TOKEN=
WISE_QUOTE_CLIENT_TOKEN=
FX_RATE_STALE_AFTER_SECONDS=3600
```

Wise credentials remain optional at startup. Set `WISE_BASE_URL` to the desired
upstream URL, using its matching token. Database reads have no environment selector;
changing the upstream URL does not create a separate stored dataset.

```sh
python -m app.scripts.run_wise_ingestion --job-type market_data
python -m app.scripts.run_wise_ingestion --job-type currencies
```

Both authenticated operations skip gracefully when `WISE_API_TOKEN` is missing,
with zero observations and `configuration_status: missing_token`. The existing
fetch-run enum has no skipped value: database status is `FAILED`, with metadata
status `skipped`. No fixture data enters production ingestion.

Existing admin-protected controls now support both jobs:

```text
POST /providers/wise/ingestion-runs/market_data
POST /providers/wise/ingestion-runs/currencies
PUT  /providers/wise/ingestion-schedules/market_data
PUT  /providers/wise/ingestion-schedules/currencies
```

Suggested checking intervals are 60 minutes for rates and 1440 minutes for
currencies; these are our policies, not Wise publishing promises. Schedules remain
disabled unless deliberately configured and the existing scheduler switch enabled.
No broad quote harvesting is scheduled. KYC, generic fees and fund-details jobs
remain unsupported for Wise.

## Historical quote diagnostics, not frontend conversion

Repository consumers were inspected: the old quote endpoint was referenced only
by its service/router, tests and documentation; no frontend consumer exists here.
`POST /fx/{provider}/quotes` (using `wise` as the provider key) is retained
**behind the existing `require_admin` control**
for single-scenario diagnostic harvesting. It may contact Wise. Normal users get
401/403 before a request is made. Frontend conversions must use `/fx/convert`.

The adapter preserves source/target amount bases, separate payment options, fee
currencies/line items, delivery estimates, expiry and original responses. These
are `amount_specific_historical_observation` records with `usable_as_fee_rule:
false`, still marked illustrative, non-executable and not rate-locked. Observations
are appended rather than reused or cached for another amount or method.

The [illustrative quote contract](https://docs.wise.com/api-reference/quote/quotecreateunauthenticated)
permits anonymous requests. Optional partner-specific pricing uses a separate
client-credentials token, not the personal rate token. No partner fee overrides
are sent. The [quote guide](https://docs.wise.com/guides/product/send-money/quotes)
defines the source amount as the total sent and target amount as received after
fees; the diagnostic parser does not subtract fees twice. None of this pricing
is consulted by `/fx/convert`.

## Migration and reliability

Apply the migration chain through `g3b4c5d6e7f8`:

```sh
python -m alembic -c app/alembic.ini upgrade head
```

The latest migration removes the earlier FX environment partitions while preserving
history. It keeps one current rate per provider/pair/type and one active currency
per provider/code. Legacy currency duplicates remain inactive. See the
[shared architecture](fx-architecture.md) for collision handling and downgrade limits.

Raw responses are retained before parsing, including failures. Invalid/missing
extraction does not clear valid rates/currencies or deactivate them. Existing
bounded timeouts/retries, credential redaction and provider error handling remain.
No live database migration, production schedule, deployment or money movement is
performed by this change.

## Verification

Verification passed: **249 tests**, including 84 FX/Wise tests; scoped FX/Wise
Ruff checks and CLI/diff checks passed. Existing shared-file style findings and
framework deprecation warnings remain. PostgreSQL upgrade, currency persistence,
legacy migration behavior, and preservation of an
unrelated mutual-fund record were checked in the isolated `/tmp` test database.
That server was stopped afterward; the configured live database was not accessed.

Offline tests use mocked Wise responses and isolated SQLite databases. They cover
network-free conversion/read paths, no live fallback on missing/stale rates,
multiple pairs, provider isolation, direct directions only, exact
Decimal products, 0/2/3-place rounding, unknown precision/fees, quote samples not
becoming rules, currency persistence/errors, admin diagnostics and job dispatch.

The official currency response example is saved as
`tests/fixtures/wise/documented_currencies.json`, explicitly test-only. Currency
and reference-rate authenticated live requests remain unverified pending a token.
The earlier anonymous quote HTTP-200/19-option observation is preserved as a
historical fixture; no new live quote was needed for local conversion work.

```sh
python -m pytest tests -q -p no:cacheprovider
ruff check app/adapters/fx app/models/fx.py app/schemas/fx.py app/schemas/wise.py app/repositories/fx.py app/repositories/wise.py app/services/fx.py app/services/wise.py app/services/ingestion/wise.py app/routers/fx.py app/routers/wise.py app/utils/currency_precision.py app/scripts/run_wise_ingestion.py app/migrations/versions/b8c9d0e1f2a3_fx_local_conversion.py tests/test_fx.py tests/test_wise.py
```


### Currency refresh correction

Currency ingestion now retires missing rows only after a complete, nonempty,
successfully parsed HTTP-200 snapshot. Partial, failed, empty and pagination-incomplete
refreshes preserve missing rows. Reappearing currencies become active again.
Provider isolation and a transactional provider lock plus fetch-run
ordering protect overlapping refreshes. Public currency lists/counts and current
capability lookup include active entries only. Historical rows/provenance are kept;
ISO precision and local conversion arithmetic remain independent.

Apply new migration `d0e1f2a3b4c5` through the normal process; existing currencies
start active. See [currency snapshot handling](fx-architecture.md#currency-snapshot-refresh-and-retirement)
for completeness, atomicity and concurrency details. No live migrations or schedules
were performed by this change.
