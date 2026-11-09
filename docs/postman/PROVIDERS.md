# Providers API in Postman

Import both files, then select **Kompare Providers - Local example**:

- `Kompare-Providers.postman_collection.json`
- `Kompare-Providers-Local.postman_environment.json`

Folders are **Authentication**, **User** and **Admin**. Public provider reads need no
token. For admin requests, set `email` and `password` to an existing verified
`super_admin` or `support_admin` account and send **Login**. It saves `access_token`
automatically. Login again when it expires.

Set `base_url` to your running API (default `http://localhost:8000`, without a trailing
slash), and `provider_slug` to a value from the catalogue, such as `wise`.
All sample accounts, tokens, IDs and response data are illustrative.

| Method | Endpoint | Access | Purpose |
| --- | --- | --- | --- |
| GET | `/providers/` | Public | Complete provider catalogue |
| GET | `/providers/overview` | Public | Paginated overview with filters and cached metrics |
| GET | `/providers/{slug}` | Public | Provider profile |
| PATCH | `/providers/{slug}` | Admin | Update supplied profile fields |
| POST | `/providers/metrics/refresh` | Admin | Recalculate all provider metrics |
| POST | `/providers/{slug}/metrics/refresh` | Admin | Recalculate one provider's metrics |
| POST | `/providers/{slug}/ingestion-runs/{job_type}` | Admin | Queue ingestion; returns 202 |

## Getting providers by category

Use the overview endpoint:

```http
GET /providers/overview?category=fx&page=1&per_page=20
```

The collection includes separate requests for `crypto`, `giftcard`, `fx` and
`mutual_fund`. Category matching is case-insensitive. Omitting the category or sending
an empty category applies no category filter. An unrecognized category such as
`banking` returns HTTP 400:

```json
{
  "responseCode": 400,
  "message": "Invalid provider category",
  "data": {
    "error": "bad_request",
    "category": "banking",
    "allowed_values": ["crypto", "giftcard", "fx", "mutual_fund"]
  }
}
```

**Invalid category example** intentionally expects HTTP 400. The ordinary overview
request also has saved examples for invalid category, status and pagination values.
Open **Params** to enable the optional filters:

- `search`: matches provider name.
- `category`: one of the four values above.
- `status`: `active` or `inactive`, case-insensitive; empty/omitted applies no status filter.
- `page`: minimum 1, default 1.
- `per_page`: 1–100, default 20.

`GET /providers/` returns an array and does not support these filters or pagination.
`GET /providers/overview` returns `data.items` and `data.pagination`, with metrics such
as `average_rating`, `review_count`, `feed_health` and `last_synced_at`. Metrics can be
missing; for example `average_rating` stays null when no average is available.

## Admin operations

**Update provider** demonstrates a partial update:

```json
{"description": "Updated provider description."}
```

Editable fields are `name`, `description`, `logo_url`, `website_url`, `is_active`,
`has_adapter`, `metadata_json`. The update schema does not expose `slug` or `category`.
Metric refreshes recompute cached metrics from stored data; they do not ingest new
market data from providers.

**Queue provider ingestion** defaults to `provider_slug=wise`, `job_type=market_data`,
`include_kyc=false` and no JSON body. A successful response is:

```json
{
  "responseCode": 202,
  "message": "Provider ingestion queued",
  "data": {
    "provider": "wise",
    "job_type": "market_data",
    "include_kyc": false,
    "status": "accepted",
    "job_id": 101
  }
}
```

The example ID is fictional. The response script saves the actual returned ID into
`ingestion_job_id`. The ingestion worker must be running to execute the job:

```sh
python -m app.scripts.run_ingestion_worker
```

Job status is available separately under Swagger's **Ingestion** group:
`GET /providers/{slug}/ingestion-jobs/{job_id}` (admin). A 202 response means queued,
not that rates have already been fetched.

This collection covers the seven operations in Swagger's **Providers** group.
Provider Reviews has a [separate collection](PROVIDER-REVIEWS.md). Other routes grouped
under Ingestion, KYC, Crypto, Gift Cards and FX are outside this collection.
