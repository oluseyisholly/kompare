# Tbay adapter

`app/adapters/giftcard/tbay.py` implements the public calculator API transport.
It has no database dependencies and does not create provider records or schedules.

Settings in `.env` / `.env.example`: `TBAY_BASE_URL`, `TBAY_SITE_URL`,
`TBAY_CLIENT_VERSION`, `TBAY_SIGNING_SALT`. The salt is part of the public client
protocol, not an account credential. No account login is used.

```python
import httpx
from app.adapters.giftcard.tbay import TbayAdapter

async def inspect_tbay():
    adapter = TbayAdapter()
    async with httpx.AsyncClient() as client:
        categories = await adapter.fetch_categories(client=client)
        category_id = categories[0]["code"]
        currencies = await adapter.fetch_currencies(category_id, client=client)
        offers = await adapter.fetch_offers(category_id, "USD", client=client)
        points_rate = await adapter.fetch_points_rate("NGN", client=client)
        return categories, currencies, offers, points_rate
```

Methods return the validated `data` portion of the upstream response. Offers are
sanitized to retain offer terms, seller ID, prices and promotional fields while
discarding nested seller-account data. Fixed denominations (`fixTrade`) remain
intact for the future normalization layer.

Server time is synchronized before requests and refreshed after five minutes.
Requests have explicit timeouts. HTTP errors propagate, while business errors,
invalid payloads, incomplete pagination, and stalled pagination raise
`TbayResponseError`. A caller must record the failed ingestion and retry later;
the adapter retries pagination mismatches from page one up to three times, but
does not silently return partial data or retry throttled requests.

Live check: 30 categories, 16 Razer currencies, and 63 distinct Razer USD offers
were fetched, with all 11 offer pages collected. These counts can change.

The adapter intentionally keeps `originRate`, `discount`, `referenceAmount`, and
Points/NGN separate. It does not publish a calculated `rate_value`: eligibility
and rounding verification are documented in `tbay-rate-verification.md`.

Run transport regression tests:

```sh
python3 -m unittest discover -s tests -p test_tbay_adapter.py -v
```
