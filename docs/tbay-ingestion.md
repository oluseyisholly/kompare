# Tbay ingestion

Apply migrations before starting the updated app, then run the full catalog:

```sh
python3 -m alembic -c app/alembic.ini upgrade head
python3 -m app.scripts.run_tbay_ingestion
```

The migration registers Tbay as a gift-card provider and adds gift-card rate
version/freshness timestamps. Historical rows are preserved. The shared rate
repository now suppresses identical rate versions for both Cardtonic and Tbay;
raw records and fetch runs still record successful runs. A partial unique index
enforces one current rate per provider, variant, and payout currency.

The Tbay adapter collects brands, currencies, seller offer pages, and the Points/NGN
price. Pagination inconsistencies are retried up to three times from page one.
Each complete card/currency scope is validated and published in its own transaction.
Failed scopes retain existing data and freshness while other scopes continue.
Missing offers are retired only in completed scopes, including confirmed empty
scopes. Legacy variants without category metadata are retained conservatively.

The script reports `status`, `scopes_completed`, and `failed_scopes`, including
pagination diagnostics. Partial completion uses the existing database `FAILED`
status with `metadata_json.status = "partial"`; successfully saved data remains
available. If every scope fails, the command raises after recording the failures.

The existing scheduler dispatches provider `tbay`, job type `market_data`. Configure
its interval using the existing provider ingestion-schedule endpoint and ensure
`ENABLE_INGESTION_SCHEDULER=true` in the running server environment. No schedule is
automatically enabled by this change.

Existing read/calculation APIs work with Tbay:

```text
GET /providers/tbay/giftcards/variants
GET /providers/tbay/giftcards/rates
GET /reports/providers/tbay/giftcards/sell-preview?rate_id=123&face_value=50
```

Replace `123` with a current Tbay rate ID. Superseded/inactive offers cannot be
used for a new preview. Tbay requires an explicit rate ID to avoid choosing a seller
implicitly. Rate listings return current versions; historical versions stay in DB.

The calculation is `face value × discount × Points/NGN`. It returns `is_estimate=true`
and `calculation_basis=public_discount_times_points_ngn`, with final NGN rounded
half-up to two decimal places. This is our display policy, not a claim to reproduce
Tbay's three-decimal display exactly. Personalized bonuses, fees, and eligibility
are not guaranteed by the estimate. Advertised reference prices and promotional
fields are preserved in sanitized source records instead of being used as the rate.

Limits, fixed denominations and explicit multiples-of-N tags are enforced. Other
seller conditions remain visible in the variant's terms and metadata. Currency
labels are retained from the source; country is not inferred from currency alone.

No live database migration or ingestion was run during implementation. Tests use
an in-memory database and stubbed upstream responses:

```sh
python3 -m unittest discover -s tests -p 'test_tbay*.py' -v
```
