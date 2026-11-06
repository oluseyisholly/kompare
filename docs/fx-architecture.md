# Shared FX architecture

FX providers share stored-rate APIs, schemas and local Decimal calculations.
Provider adapters handle upstream requests and normalization.

## Provider-keyed APIs

| Endpoint | Purpose |
| --- | --- |
| `GET /fx/{provider}/rates` | Current stored rates and sampled transfer rates |
| `GET /fx/{provider}/currencies` | Active stored/observed currency discovery |
| `POST /fx/convert` | Local estimates from stored rates; provider in request body |
| `POST /fx/{provider}/quotes` | Admin diagnostic for adapters implementing it |

Provider selection uses the existing `ProviderName` enum. Wise stores reference rates,
Flutterwave stores amount-specific transfer-rate observations, and Fincra stores
separate provider-labelled buy/sell treasury prices. The calculator keeps these
classifications explicit. Fees/net amounts remain unavailable without a verified rule.
No conversion/read request contacts a provider, including missing or stale data cases.
Wise and Flutterwave use directly stored directions. Fincra alone allows the
explicitly assumed reciprocal mapping described below. No synthetic cross-rates are used.

## Unified conversion contract

Every provider accepts exactly the same four fields at `POST /fx/convert`:

```json
{"provider":"wise","source_currency":"USD","target_currency":"NGN","source_amount":"100"}
```
```json
{"provider":"flutterwave","source_currency":"USD","target_currency":"NGN","source_amount":"100"}
```
```json
{"provider":"fincra","source_currency":"USD","target_currency":"NGN","source_amount":"100"}
```

`source_currency` is what the customer gives; `target_currency` is what the customer
receives. `source_amount` is unchanged by fee assumptions. Provider keys use the
existing enum. Legacy `rate_side` is rejected as an extra field with HTTP 422,
including `null`; remove it from clients. It never overrides internal selection.

The service resolves existing stored records into one internal `StoredConversionRate`:
provider, customer direction, target units per source unit, classification, observation
and provider times, expiry, original IDs/URL and sample constraints. There is no new
table or outbound request during resolution or conversion. Fincra uses the temporary,
explicitly disclosed mapping assumption below while provider confirmation is pending.

Success responses consistently contain `provider`, `source_currency`, `target_currency`,
`source_amount`, `applied_rate`, `gross_target_amount`, `fee_amount`, `fee_currency`,
`net_target_amount`, `fee_status`, `rate_classification`, `observed_at`,
`provider_rate_timestamp`, `expires_at`, `is_stale`, `calculation_basis` and `warnings`.
Original rate/raw IDs, source URL, precision/rounding fields and `captured_at` remain.
`estimated_net_target_amount` is retained as a deprecated compatibility alias for
`net_target_amount`. Sample details also remain available for existing clients.

Decimal arithmetic computes `source_amount × applied_rate`; the gross display is
rounded once using target precision and ROUND_HALF_UP. There are no verified,
reusable fee rules with sufficient scenario and fee-treatment information in these
integrations. All conversions therefore return `fee_status: unavailable`,
`fee_amount: null`, `fee_currency: null` and `net_target_amount: null`. No spread is
added, no fee is deducted, and unknown never becomes zero. A published zero in a
specific diagnostic quote remains zero in that observation; it does not establish
zero fees for these conversions, even at a similar amount. Unverified generic fee
profiles and option-specific prices are never applied as global rules.

Wise remains a reference-rate estimate. Flutterwave uses the separately collected
rate for the requested direction, never its reciprocal. Its `metadata.pricing_scope`
contains sampled target/source amounts, selection policy and `extrapolated`. A
calculation at another amount is explicitly an estimate; even matching the sample
amount does not establish fees, payout-method support or an executable quote.

`observed_at` is the latest observation time (reference/treasury-price `last_seen_at`, or
sample collection time); `captured_at` retains the original record capture time.
Neither is a provider valuation time. Provider timestamps/expiry are returned only
when actually supplied. Freshness uses provider time when available, otherwise
observation time. Stale/expired observations remain estimates with `is_stale: true`
and warnings; reads do not refresh them. Missing directions return `fx_rate_unavailable`.
Invalid stored metadata is rejected without mutating it.

Fincra retains original prices/sides and uses an explicit temporary assumption:
Fincra buys/sells the base currency; price is quote units per base unit. A request
first selects the requested pair's BUY record. If absent, it selects the reversed
pair's SELL record and takes its reciprocal. It never substitutes the opposite
side or combines pairs. Missing required prices return `fx_rate_unavailable`.
If both feed orderings exist, direct BUY takes priority over reversed SELL.

For stored USD/NGN: USD→NGN uses BUY by multiplication, and NGN→USD uses SELL
by division. Reciprocal rates use at least 64 significant Decimal digits before
the shared multiplication/target rounding. Responses have treasury_rate
classification, stored_treasury_rate_estimate calculation basis and
`metadata.fincra_mapping` with `status: assumed`, policy ID, original pair/side/price,
selection policy and inversion flag. Warnings explicitly state that provider
confirmation is pending. Fees/net amounts remain unavailable. The rule lives in
`FxService._resolve_fincra_rate`; change that mapping and its tests after confirmation.
The earlier `fx_rate_mapping_unverified` block is replaced by this authorized
assumption. Rate-list labels remain unverified because this is not provider confirmation.
See the [Fincra interpretation and official references](fincra-fx-integration.md#customer-direction-verification).

This contract update needs no new migration/configuration. Previously pending
migrations remain separate; no database migration or schedule is run automatically.

## Base URLs and storage

There are no sandbox/production partitions or environment fields in normalized FX
storage or public response schemas. Reads select by provider and currencies;
original provider sides remain internal price identity where applicable.
One current price exists per provider/asset/pair/type; price
history and raw observations remain available.

- `FINCRA_BASE_URL` selects `https://sandboxapi.fincra.com` or `https://api.fincra.com`.
- `WISE_BASE_URL` selects `https://api.wise-sandbox.com` or `https://api.wise.com`.
- Flutterwave v3 uses `https://api.flutterwave.com` in both modes; its test/live
  secret key determines upstream behavior automatically.

Use matching credentials for the selected upstream URL. `FX_DATA_ENVIRONMENT`,
`FINCRA_ENVIRONMENT` and `FLUTTERWAVE_ENVIRONMENT` are removed and ignored.
Configure each deployment's base URLs/credentials; all successful ingestion in that
deployment updates its provider's shared dataset. Original source URLs and raw
records provide provenance. `FX_RATE_STALE_AFTER_SECONDS` still controls warnings.

The shared FX ingestion registry dispatches provider-specific services for CLI,
manual admin triggers and existing schedules. No schedules are enabled automatically.

```sh
python -m app.scripts.run_fx_ingestion --provider wise --job-type market_data
python -m app.scripts.run_fx_ingestion --provider wise --job-type currencies
python -m app.scripts.run_fx_ingestion --provider flutterwave --job-type market_data
python -m app.scripts.run_fx_ingestion --provider fincra --job-type market_data
```

## Currency snapshot refresh and retirement

Public currency lists and totals include active rows only. A complete, successfully
fetched, fully parsed nonempty snapshot retires missing currencies for that provider.
Partial/failed/empty/pagination-incomplete snapshots never retire missing records.
Reappearance reactivates a stored row and updates metadata. Independent ISO precision
remains usable for local estimates; discovery is not proof of transfer-route support.

`FxRepository.persist_currencies(..., snapshot_complete=True|False)` requires explicit
completeness. Upserts/retirement share one transaction. A provider-row lock serializes
writers, including initial refreshes. Allocate the fetch run before fetching. The
maximum stored currency fetch-run ID is the provider-wide watermark: an older refresh
cannot overwrite, reactivate or retire records after a newer one commits. Partial
upserts also advance it; rollback does not. Equal-run retries can safely upsert again.

A partial unique index permits one active currency row per provider/code. Legacy
duplicate currency rows from removed partitions remain inactive with their original
provenance. Upserts deterministically select the newest stored row for that code.

## Migration

Migration `g3b4c5d6e7f8`, after `f2a3b4c5d6e7`, removes `quotes.environment` and
`fx_currencies.environment`, removes the normalized JSON selectors, and rebuilds
current-record uniqueness without an environment key. When former partitions have
multiple current prices for the same key, the most recently observed row wins, with
capture time/ID breaking ties. Other rows are superseded; none are deleted.
Currency duplicates are retained inactive; the latest stored state wins, including
an inactive state. Quote IDs, observations, raw records and references are preserved.

```sh
python -m alembic -c app/alembic.ini upgrade head
```

The migration cannot reconstruct removed partitions on downgrade; restore a
pre-migration backup if that old schema is needed. It was tested only on disposable
PostgreSQL data. No migration is applied to the configured application database by
implementation or ordinary tests.

The shared quotes table is also used by crypto, so its unused environment column
is removed there too. Gift-card and mutual-fund ingestion do not use these database
partitions. Their separate domain models and calculations remain in place.

See [Wise](wise-fx-integration.md), [Flutterwave](flutterwave-fx-integration.md) and
[Fincra](fincra-fx-integration.md) for provider-specific collection details.
