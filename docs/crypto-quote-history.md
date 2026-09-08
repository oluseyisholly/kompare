# Crypto quote history

Quidax and Busha share change-based persistence in `QuoteRepository.create_many`.
The return value counts new versions, so an unchanged successful run can report
zero `quotes_created`.

- A series is identified by provider, asset, base currency, quote currency, and quote type.
- Rates are compared at the database's eight-decimal precision.
- Changes to prices, provider-asset association, or offer conditions create a version.
- Rolling high/low/open/volume/percentage-change statistics do not create versions;
  the original API payload remains available in raw records.
- `captured_at` retains the source capture timestamp for the version.
- `last_seen_at` records the most recent successful observation by our application.
- `superseded_at` records when we observed a replacement, not the exact time the
  provider changed its price. An unsuperseded row may still be stale.
- Missing pairs and failed requests do not refresh existing quotes. Missing pairs
  are not automatically marked unavailable by this change.

Each successful sample writes a small `quote_observations` row referencing the
version, run, raw record, and observation time. Trend points use these observations,
including repeated unchanged values. Missing samples are not interpolated; clients
should use ingestion health and timestamp gaps when rendering charts.

The repository locks asset rows in order and commits version replacement,
freshness, and observations together. A partial unique index additionally prevents
two current versions of the same series. Locking is effective on PostgreSQL;
SQLite unit tests do not prove concurrent PostgreSQL behaviour.

The migration preserves all old quotes and marks the latest per series current.
Historical observations are backfilled from existing capture timestamps because
their exact polling times cannot reliably be reconstructed. No historical rows
are deleted or collapsed.

Run before starting the updated application:

```sh
python3 -m alembic -c app/alembic.ini upgrade head
```

Raw records, fetch runs, and observations continue growing per fetch. This change
reduces duplicate full quotes; it is not an archival or retention policy. Gift-card
and KYC persistence are unchanged.

Verification:

```sh
python3 -m unittest discover -s tests -p test_quote_history.py -v
```
