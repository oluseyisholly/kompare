# Swagger request examples

Swagger at `/` includes explicit examples for every JSON request body. Email examples use
`user@example.com` and `admin@example.com`. These are fictional accounts: use your own
registered email and password, the OTP sent to that email, and the real refresh token
returned by login or refresh.

Password recovery uses `POST /auth/forgot-password` with `email`, then
`POST /auth/reset-password` with `email`, the emailed `otp` and `new_password`.
See [password recovery](password-reset.md) for expiry, limits and session invalidation.

`POST /fx/convert` offers selectable Wise, Flutterwave and Fincra examples with the same
four fields: `provider`, `source_currency`, `target_currency`, `source_amount`. Decimal
amounts are strings. A successful calculation requires fresh stored rates for that pair.
`POST /fx/{provider}/quotes` currently supports Wise only; its two examples each supply
exactly one amount. Currency listings provide discovery, not guarantees about supported
conversion directions.

Crypto calculation queries use BTC/NGN with positive amounts; mutual-fund queries show
Stanbic and the stable fund code `stanbic-simm`. Use IDs and codes from listing responses
when querying your database. The ingestion schedule example is disabled; enabling it is
an explicit choice. KYC examples are illustrative and must be replaced with published
provider requirements.

`tests/test_openapi_examples.py` checks every request body has examples, validates them
against its Pydantic model, checks enum values and guards against undocumented fields.
It also verifies the served OpenAPI JSON, readable email examples and the FX contracts.
