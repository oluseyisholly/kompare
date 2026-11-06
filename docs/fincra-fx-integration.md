# Fincra FX ingestion and local estimates

Implemented for Kompare's existing background ingestion and database-only calculator.
No trades, transfers, payouts or wallets are created. Frontend reads never call Fincra.

## Contract and limitations

Reviewed 2026-11-05:
- https://docs.fincra.com/reference/rates
- https://docs.fincra.com/docs/api-environments
- https://docs.fincra.com/docs/live-environment
- https://docs.fincra.com/reference/generate-quote

The read-only endpoint is GET /quotes/treasury-orders/rates, authenticated with
`api-key`. Production host: https://api.fincra.com; sandbox: https://sandboxapi.fincra.com.
Pagination uses page/perPage and data.pagination. Every page is fetched; invalid,
empty, duplicate or inconsistent snapshots fail without modifying current prices.
Raw page responses remain available for diagnosis. Collection is bounded to 100 pages.

This initial FX integration explicitly excludes provider rows involving the documented
digital assets `CNGN`, `USDC` and `USDT`. They remain distinct from NGN and USD and
are retained in raw responses. Page sizes, totals, duplicate detection and validation
apply to the original rows before exclusions. All pages are fetched, including a
page containing only digital assets. Run metadata reports `rates_received`,
`rates_excluded`, `excluded_rates` (pair/side/page/raw reference) and
`snapshot_complete`. Unknown symbols or malformed values fail the snapshot rather
than being silently skipped. An entirely excluded snapshot preserves current rates.

Validation failures identify the page, row, pair where available, invalid fields and
raw-record reference in `error_details`. Invalid input values and credentials are
excluded from these diagnostics.

## Customer direction verification

The official [Rates reference](https://docs.fincra.com/reference/rates) documents
`baseCurrency`, `quoteCurrency`, `side` and `price`, but does not explicitly define
whose buy/sell perspective applies or give a normative price-unit equation.
Its examples alone are insufficient verification. Both original labels and exact
prices remain stored; rate-list `rate_direction` is `unverified`.

The separate [Generate a Quote reference](https://docs.fincra.com/reference/generate-quote)
defines customer source/destination currencies, amount basis and quote expiry. It
does not establish how treasury-feed sides map to those directions. Its short-lived,
scenario-specific quotes cannot verify a universal cached rate or fee rule.

The temporary implementation uses a user-authorized assumption, not a verified
provider convention: Fincra buys/sells the base currency and price is quote units
per one base unit. Original raw data and stored side labels are unchanged.

| Customer gives → receives | Selected stored price | Normalized rate |
| --- | --- | --- |
| Base → quote | BUY | price |
| Quote → base | SELL | 1 / price |

For USD/NGN, USD→NGN multiplies by BUY, while NGN→USD divides by SELL.
The resolver first tries a direct BUY, then a reversed-pair SELL. If both orderings
exist, the direct BUY wins. It never selects another side merely because the
required side is missing. No cross-rates or provider calls are introduced.

`FxService._resolve_fincra_rate` centralizes this policy for later confirmation.
Conversion metadata labels it `status: assumed`, `policy: provider_base_currency_v1`,
with the selected original side/pair/price, price units, selection policy and inversion
flag. Warnings disclose the pending confirmation; transfer_route_verified/executable remain false.
The former `fx_rate_mapping_unverified` block no longer prevents these estimates.
A missing required price or invalid stored price returns `fx_rate_unavailable`.

Provider confirmation is still needed for the side perspective, price-unit equation
and each customer direction. Confirmation should update this one resolver and its
regression tests; this provisional choice is not evidence of provider semantics.

Pagination timestamp is retained as feed metadata, not labelled as the price's
valuation time. Freshness uses the last successful observation time. This does not
establish when Fincra last changed a rate. Repeated identical snapshots retain quote
history and record a new observation. Changing feed timestamps or pagination URLs
alone does not create price versions. Unchanged prices keep their ID and original
capture time while refreshing last-seen time, feed metadata and raw/run references
together. Earlier evidence remains linked through `quote_observations`.
Complete snapshots retire missing pair/sides;
failed snapshots do not. Provider locking and observation run IDs prevent older jobs
from overwriting newer snapshots, including unchanged snapshots.

Fees and net amounts remain unavailable: the rate feed is not a fee schedule.
A spread already reflected in the price is not added again. Fincra's separate quote
API is scenario-specific, requires business details, and is not called by this
integration. No universal local fee formula is inferred from sample quotes.

## Setup

Apply migration `f2a3b4c5d6e7` through the normal reviewed deployment process:

```sh
python -m alembic -c app/alembic.ini upgrade head
```

The migration registers FINCRA and its provider entry; existing quote/observation
storage handles separate BUY and SELL records. Downgrade retains additive registration
because historical runs may refer to it. No new table is required.

```dotenv
FINCRA_SECRET_KEY=
FINCRA_BASE_URL=https://sandboxapi.fincra.com
FX_RATE_STALE_AFTER_SECONDS=3600
```

Use credentials matching the configured base URL. Both official hosts are allowed;
no separate ingestion or database environment selector is used.
Live access requires Fincra KYC/approval. Never paste secrets into chat or frontend code.
Missing credentials skip ingestion and never load fixture prices.

```sh
python -m app.scripts.run_fx_ingestion --provider fincra --job-type market_data
```

Existing admin ingestion triggers and schedules support Fincra market_data. Schedules
are not enabled by this change. A currencies job is not required: currency codes are
derived from currently stored rate pairs. They are labelled observed_rate_pairs,
not an official transfer-currency catalogue; currency names/capabilities are unknown.

## Local APIs

```http
GET /fx/fincra/rates?source=USD&target=NGN
GET /fx/fincra/currencies
POST /fx/convert
Content-Type: application/json

{"provider":"fincra","source_currency":"USD","target_currency":"NGN","source_amount":"100"}
```

This is the [common conversion contract](fx-architecture.md#unified-conversion-contract),
with no provider-specific inputs. Legacy `rate_side`, including null, returns 422.
For the historical fixture BUY price 1486 NGN per USD, 100 USD yields an estimated
gross 148600.00 NGN. This is fixture arithmetic, not a live price. Response fields include:

```json
{
  "provider": "fincra",
  "source_currency": "USD",
  "target_currency": "NGN",
  "source_amount": "100",
  "applied_rate": "1486",
  "gross_target_amount": "148600.00",
  "reference_rate": null,
  "rate_classification": "treasury_rate",
  "calculation_basis": "stored_treasury_rate_estimate",
  "fee_status": "unavailable",
  "fee_amount": null,
  "fee_currency": null,
  "net_target_amount": null,
  "provider_rate_timestamp": null,
  "expires_at": null,
  "metadata": {
    "fincra_mapping": {
      "status": "assumed",
      "policy": "provider_base_currency_v1",
      "side_perspective": "provider",
      "price_units": "quote_per_base",
      "selection_policy": "direct_buy_then_reverse_sell",
      "provider_side": "buy",
      "base_currency": "USD",
      "quote_currency": "NGN",
      "provider_price": "1486",
      "inverted": false
    }
  }
}
```

Actual responses also retain observation/capture times, freshness, source/raw/run
references and explicit assumption/fee warnings. Inverse normalization uses at least
64 significant Decimal digits; the shared calculator multiplies and rounds once
at target precision using ROUND_HALF_UP. Prices are not averaged or spread-adjusted.

Original provider price/side records, raw responses and provenance remain accessible
through the listing APIs. Derived currency entries have null IDs; provider/code is
their identity. Listing is discovery, not confirmation of a customer conversion route.

## Validation

Offline tests cover both sides, pagination, failures, retirement, overlapping jobs,
precision, credentials, provider isolation, assumption-based directional conversion and shared API
serialization. Test pagination is synthetic; price examples come from official docs.
Authenticated sandbox calls have been verified against the implementation in an
isolated in-memory SQLite database: four pages, 34 received rows, six reported
digital-asset exclusions and 28 stored FX rates. A local USD-NGN calculation was
checked using the disclosed temporary assumption. Production was not called.
No migrations, deployment or schedule changes were performed.

Set `FINCRA_BASE_URL=https://api.fincra.com` for production collection, or
`https://sandboxapi.fincra.com` for sandbox collection. Both use the same stored
provider dataset. Reads and local conversions have no environment selector.
The obsolete environment variables have been removed from the local `.env`.
Apply migration `g3b4c5d6e7f8` and restart the API after updating the application.

The regression fixture captures all four authenticated sandbox pages on
2026-11-04: 34 provider rows, six explicitly excluded digital-asset rows and 28
eligible FX rows. It is historical simulated data, not production pricing.

Validation including the temporary mapping (2026-11-05): **365 tests passed**, with five
opt-in PostgreSQL tests skipped because no disposable test socket was configured.
Regression coverage includes mixed-asset pages, excluded-only pages
and snapshots, detailed validation errors, unchanged/changed price versions, latest
raw provenance, atomic rollback, and the default behavior of other quote providers.
Fincra lint/format checks passed; shared quote files introduced no new lint findings.
Offline test read settings are isolated from the local application's `.env`.

The unified conversion contract adds no migration or configuration. No trades,
transfers, payouts, live database migrations or schedule changes were performed.
