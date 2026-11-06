# Flutterwave v3 test fixtures

These are documentation-derived examples, verified 2026-11-02 at:
https://developer.flutterwave.com/docs/transfer-rates

- `ngn_usd.json`: destination amount USD 1000, rate 0.000694329 USD per NGN.
- `usd_ngn.json`: destination amount NGN 100000, rate 1372 NGN per USD.
- `error.json`: the documented error envelope.

They are historical documentation examples, not current prices or evidence that
these routes/amounts are available to the application's account. The response does
not publish a timestamp or establish separate fees. Source/destination amounts are
kept as published; rounding differences are not treated as fees.

Tests may mutate these examples to exercise amounts, precision, errors and
isolation. Such variants are synthetic. Production adapters never read fixtures.
No authenticated/live Flutterwave request was made for these fixtures.
