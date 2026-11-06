# Flutterwave FX integration

Flutterwave v3 rates are collected through the shared FX ingestion dispatcher using
built-in currency pairs. The shared APIs read stored observations, and `POST /fx/convert` performs
Decimal arithmetic locally. Conversion requests never contact Flutterwave, including
when data is missing or stale. Wise reference-rate handling remains available.

## Verified contract

Verified against official documentation on 2 November 2026:

- [Transfer rates](https://developer.flutterwave.com/docs/transfer-rates):
  `GET https://api.flutterwave.com/v3/transfers/rates` takes directed source and
  destination currencies. **`amount` is the destination amount.** The returned
  rate means destination units per source unit: destination = source × rate.
- [Endpoint reference](https://developer.flutterwave.com/reference/check-transfer-rates):
  the request amount is documented as int32. This initial implementation accepts
  positive whole destination amounts up to 2,147,483,647.
- [Authentication](https://developer.flutterwave.com/docs/authentication):
  v3 uses `Authorization: Bearer <secret-key>`. Test and live keys select the mode
  on the same v3 host; this integration does not use the v4 OAuth flow.

The response publishes `rate`, `source.currency`, `source.amount`,
`destination.currency` and `destination.amount`. It does not document a provider
timestamp. That field remains null; collection time is recorded separately.
Responses must match the requested direction and destination amount. Missing,
nonpositive or nonfinite financial values fail extraction.

## Configuration and collection

Set these server-side variables, following `.env.example`:

```dotenv
FLUTTERWAVE_SECRET_KEY=
FLUTTERWAVE_BASE_URL=https://api.flutterwave.com
FX_RATE_STALE_AFTER_SECONDS=3600
```

Supply the appropriate v3 test or live secret key privately. The credential prefix
determines the mode automatically. `FLUTTERWAVE_BASE_URL` is
`https://api.flutterwave.com` for both modes; invalid origins are rejected before
sending credentials. There are no environment partitions in stored data or reads.
The freshness threshold is a Kompare policy. Missing keys skip ingestion explicitly.

No scenario JSON is required. Each run requests these default directed pairs:

| Directions | Destination amount used for collection |
| --- | --- |
| NGN → USD / GBP / EUR | 1,000 of the destination currency |
| USD / GBP / EUR → NGN | 100,000 NGN |

These are collection targets, not verified executable routes for your account.
Flutterwave validates each pair; a failed pair does not discard successful rates.
An absent, blank or `[]` value for `FLUTTERWAVE_FX_SCENARIOS` uses these defaults,
so the existing `.env` needs no scenario changes. Users can convert different source
amounts with the collected rate; the sampling amount is an upstream request detail.

An optional nonempty `FLUTTERWAVE_FX_SCENARIOS` array replaces the default list.
For example, to collect only the following two directions:

```dotenv
FLUTTERWAVE_FX_SCENARIOS='[{"source_currency":"NGN","destination_currency":"USD","destination_amount":"1000"},{"source_currency":"USD","destination_currency":"NGN","destination_amount":"100000"}]'
```

Codes must be three uppercase letters. Directions and sampled amounts are distinct;
duplicate or invalid scenarios are reported individually. No all-pairs API or full
currency catalogue is assumed.

After reviewing and applying migrations through your normal process, run:

```sh
python -m app.scripts.run_fx_ingestion --provider flutterwave --job-type market_data
```

The existing admin provider ingestion trigger and schedule controls also dispatch
`flutterwave` through the shared registry. Only `market_data` is implemented;
currencies, fees and other jobs are rejected with supported-job information. No
schedule is created or enabled automatically. Requests time out after 15 seconds;
transport failures and short rate limits have at most one retry. Longer rate limits
are reported without sleeping for the provider's full wait period.

Each response, request scenario, HTTP status and source URL is retained in
`raw_records` before parsing, with credentials excluded/redacted. Scenario errors
appear in fetch-run metadata. Good observations survive failures elsewhere in the
run; a partial run is reported as partial (and FAILED in the existing run-status
enum). Separate successful runs may retain unchanged observations.

The ordinary flow is periodic/manual ingestion → stored rates → local conversions.
Use the existing `market_data` schedule controls for periodic refreshes. Every
successful refresh becomes available to conversions immediately; failed refreshes
keep the last good rates. History is retained for now; retention/deletion is deferred.

HTTP 400 failures include the redacted `provider_message` in run output/metadata.
They are reported as `flutterwave_request_rejected`, rather than assuming the pair
is unsupported. For example, "An error occured while generating the system token.
Please contact support." was observed for all six test-mode requests in run 109.
That response requires investigation by Flutterwave support; changing request pairs
does not establish a fix. Existing observations remain available after such failures.

## Shared APIs and local estimates

```http
GET /fx/flutterwave/rates?source=USD&target=NGN
POST /fx/convert
Content-Type: application/json

{"provider":"flutterwave","source_currency":"USD","target_currency":"NGN","source_amount":"100"}
```

For the documentation fixture with rate `1372`, the response data includes the
following illustrative fields (other timestamps, provenance and warnings omitted):

```json
{
  "provider": "flutterwave",
  "source_amount": "100",
  "reference_rate": null,
  "applied_rate": "1372",
  "rate_direction": "target_per_source",
  "rate_classification": "transfer_rate_observation",
  "calculation_basis": "stored_sampled_transfer_rate_estimate",
  "sampled_destination_amount": "100000",
  "sample_source_amount": "72.886",
  "sample_target_amount": "100000",
  "sample_selection_policy": "latest_collection_then_smallest_destination_amount_then_newest_id",
  "gross_target_amount": "137200.00",
  "fee_status": "unavailable",
  "fee_amount": null,
  "fee_currency": null,
  "net_target_amount": null,
  "estimated_net_target_amount": null,
  "observed_at": "2026-11-02T12:00:00Z",
  "provider_rate_timestamp": null,
  "expires_at": null,
  "freshness_basis": "collection_timestamp"
}
```

The calculator selects the newest collected observation for the exact directed
pair/provider. Ties choose the smallest requested destination amount,
then newest observation ID. The rates endpoint keeps the newest observation for
each distinct pair and sampled amount. No averaging, interpolation, inversion or
cross-rates are performed. Responses expose the selected sample and raw-record ID.

The estimate multiplies the user's source amount by that stored rate and applies
the existing target-currency precision policy. Sampling one amount does not
guarantee the same price for another amount or any payout method. Separate fees
have not been established: fee amounts/currency and net amounts remain null. The
gross estimate is not the final wallet debit or recipient payout. No fee is inferred
from rounded provider amounts.

Freshness uses collection time when the provider timestamp is absent. Stale data is
flagged with warnings and never refreshed during conversion; a missing direct rate
returns `fx_rate_unavailable`. No automatic Flutterwave currency discovery is
implemented: its currency endpoint remains empty with that explanation. Configured
pairs are collection targets, not an official supported-route catalogue.

## Storage, migration and validation

Migration `e1f2a3b4c5d6`, after `d0e1f2a3b4c5`, adds the provider enum/registration
and a classification column to shared `fx_quote_observations`. Existing Wise rows
receive `illustrative_transfer_quote`. The old one-row-per-run constraint becomes
one-row-per-run-and-scenario, preserving multiple amounts. Retrying persistence of
the same scenario/run returns the existing observation. Rates and returned amounts
retain exact Decimal strings in the existing JSON payload, alongside provider,
direction, requested amount, timestamps and raw/run references.
No additional table is introduced. A downgrade refuses when multiple observations
in a run cannot fit the old unique constraint; it never deletes them to proceed.

Offline tests use explicitly labelled documentation fixtures and synthetic variants.
They cover request semantics, arithmetic, scenario failures, retries, configuration,
sample identity/selection, isolation and shared API behavior. Fixtures are never
loaded by production ingestion. The contract was verified from documentation and
fixtures; **no authenticated live Flutterwave response was obtained**. Transfers,
payments, recipients, wallet operations, fee harvesting and currency discovery are
deferred. No live migration, schedule enablement or deployment is part of this work.

Validation: **295 tests passed** in `tests/`, including 47 Flutterwave cases;
three optional PostgreSQL tests were skipped in this run. Default-pair collection,
optional overrides, latest-rate conversion and last-good-rate preservation passed.
Scoped FX lint and formatting checks passed. Earlier disposable PostgreSQL checks verified Wise data
preservation, multiple samples per run, retry identity, provider filtering and
safe downgrade/re-upgrade with classification restored. Existing framework
deprecation warnings remain. Root-level pytest discovery additionally encounters
an existing obsolete `from core.database` import in the empty `app/tests` scaffold;
that unrelated scaffold was left unchanged.

Migration `g3b4c5d6e7f8` removes the former normalized environment fields. See the
[shared architecture](fx-architecture.md) for the current storage policy.

## Unified conversion contract

`POST /fx/convert` accepts the same provider, source_currency, target_currency and
source_amount fields as Wise/Fincra; see the [shared contract](fx-architecture.md#unified-conversion-contract).
Legacy rate_side is rejected with 422. Each requested direction uses its own
collected rate. A missing direction never uses the reciprocal of another sample.
`observed_at` identifies collection time; provider time and expiry remain null
because the v3 response does not supply them. Actually supplied stored expiry is
preserved, and an expired observation is marked stale rather than refreshed.

`metadata.pricing_scope` preserves sample source/target amounts and sets
`extrapolated` when the requested source amount differs from the observed source
amount. Such calculations are explicitly estimates. A matching amount is still
not an executable quote. No reusable fee rule is verified: fee_amount,
fee_currency and net_target_amount remain null with fee_status unavailable.
The old estimated_net_target_amount alias remains deprecated for compatibility.
This contract change adds no migration or configuration.
