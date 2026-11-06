# Wise fixtures — test data only

These files are never imported by production adapters or ingestion services.

- `documented_rates.json`: Wise's rate response example, retrieved 2026-11-02 from
  https://docs.wise.com/api-reference/rate/rateget (version 2026Q4).
- `documented_quote.json`: **synthetic fixture assembled from documented schema
  examples**, not a real transfer offer. Amounts, timestamps, payment option and fee
  fields come from https://docs.wise.com/api-reference/quote/quote and its linked
  schema resource. Example properties in Wise's schema are general examples and
  need not reconcile with each other. The generic authenticated ID, user/profile,
  and optional pricing overrides are omitted to represent an anonymous quote.
  Tests compute the ratio of the supplied sender/recipient totals; they do not
  derive recipient amounts by multiplying a rate or subtracting example fees.
- `live_illustrative_gbp_usd_2026-11-02.json`: actual response to the one anonymous
  production data-only `POST https://api.wise.com/2026Q4/quotes` with
  `{"sourceCurrency":"GBP","targetCurrency":"USD","sourceAmount":100}`.
  No authorization or pricing override was sent. Response HTTP 200, 19 options,
  provider `createdTime` 2026-11-02T10:56:45Z. All prices/estimates are historical
  observations, not current market data or executable prices.

Test mutations (other amounts, methods, invalid data) are synthetic edge cases.
No money movement, account, recipient, or transfer was created.

- `documented_currencies.json`: exact AUD/JPY response example from
  https://docs.wise.com/api-reference/currencies/currenciesget, verified 2026-11-02
  (2026Q4). This is not a fabricated or production-supported currency list.
  The pinned SIX minor-unit data under `app/data` supplies rounding metadata only;
  it never populates the provider currency catalogue or reference rates.
