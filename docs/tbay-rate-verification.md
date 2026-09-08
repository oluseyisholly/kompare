# Tbay rate mapping investigation

Checked on 2026-09-08 using public calculator API responses and the saved
calculator JavaScript. No ingestion or database writes were performed.

## Requests verified

POST `https://api.tbay.store/api?code=806206`

The multipart form contains `code`, `client=h5`, `version=1.10.16`,
`subsidiaryCode=tbay000000001`, and a JSON-encoded `json` field:

```json
{
  "giftcardType": "FK20210330135913094461312",
  "type": 0,
  "tradeCurrency": "USD",
  "start": 1,
  "limit": 6,
  "orderColumn": "comprehensive_sort_value",
  "orderDir": "desc"
}
```

The signed request returned HTTP 200, `errorCode="0"`, six offers, and
`totalCount=63`, `totalPage=11`. `start` is the page number.
HTTP success alone is insufficient: check the response's `errorCode`.

POST `https://api.tbay.store/api?code=650102` with JSON field
`{"symbol":"Points","referCurrency":"NGN"}` returned `mid=1255.19`.
These values are observations, not constants for ingestion.

## Calculation evidence

The saved rateCalculator bundle calculates Points as face value times the
selected offer's `discount`. Its usePriceCalculator helper adds coupon and
redeemed-coins amounts, then multiplies by the local conversion rate. It also
separates membership premium from its base-price display.

The offer list displays `referenceAmount / 100`; this is a different value.
Do not label that value as the unconditional payout rate.

| Offer | originRate | discount | referenceAmount per 100 | discount × Points/NGN |
| --- | ---: | ---: | ---: | ---: |
| GBA20240704142117037917567184 | 0.868358 | 0.877041 | 116625.02 | 1100.85309279 |
| GBA2026052821361722179377422 | 0.854790 | 0.863337 | 114802.73 | 1083.65196903 |

For the first offer, face values 10, 50, and 100 yield 11008.53, 55042.65,
and 110085.31 NGN respectively using `discount × mid`, rounded to two decimals.
These are formula checks, not observed browser payout results. The reference
amount for 100 is 116625.02 NGN. The response includes a new-user coupon and
premium fields; eligibility and the exact reference-price composition still
require verification. Neither `discount` nor `originRate` should yet be labelled
as a universally available rate.

## Storage implications

- Preserve the offer `code` as variant external ID to separate seller offers.
- Preserve `minTrade`, `maxTrade`, `fixTrade`, tags, and trade explanation.
- `fixTrade` contains allowed denominations separated by `||`; min/max alone
  cannot enforce these restrictions.
- The UI rejects fractional face values. Some offers also specify multiples
  of five and card-code length restrictions in their tags or explanations.
- Preserve reference price, origin rate, discount, Points conversion rate,
  and promotional fields separately with their capture time.
- Only promote a verified, explicitly described calculation basis into
  `giftcard_rates.rate_value`.
- The API returns unrelated nested seller account fields. Omit those from
  normalized data and sanitize raw records before storage; retain only seller
  identity needed to distinguish offers.

## Remaining verification

Observe browser payouts with promotional options disabled and enabled, confirm
membership assumptions and rounding, and sample a fixed-denomination offer.
The adapter can fetch these responses using the existing architectural pattern;
publishing normalized calculation rates depends on resolving these points.

## Browser follow-up

The implemented adapter independently fetched all 63 Razer USD offers across
11 pages, plus 30 categories and 16 Razer currencies.

Selecting the first USD 10–10000 Razer offer in the real public calculator gave:

| Entered face value | Displayed Points | Displayed approximate NGN |
| --- | ---: | ---: |
| 10 | 8.77041 | 11008.53 |
| 50 | 43.85205 | 55042.654 |

These displayed amounts support `face_value × discount × Points/NGN` for that
public offer. The earlier two-decimal arithmetic examples are not an exact match
for the page's display precision: it showed three decimal places for 50 units.
The page displayed a login warning and redirected to its login page before the
100-unit observation. No login or transaction was performed. Explicitly toggling
member bonuses/coupons and verifying their eligibility remains untested.

No fixed denominations occurred among the 63 sampled Razer USD offers. The adapter
preserves `fixTrade` unchanged, and its tests cover preservation of `10||50`.
Other brands and precise rounding behaviour still require validation before a
universal normalized payout policy is selected.
