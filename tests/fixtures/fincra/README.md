# Fincra sandbox rate fixture

`sandbox_rates_2026-11-04.json` contains the four read-only rate responses captured
from the authenticated sandbox endpoint on 4 November 2026. It has 34 rows, including
six digital-asset rows involving CNGN, USDC or USDT. It contains response bodies only;
no credentials, request headers or business identifiers are included.

Sandbox prices are simulated historical test data. They are not current production
rates and are never loaded by production ingestion. Additional tests mutate copies
to exercise failed refreshes and version identity.
