# Production hardening results — 2026-11-05

The identified code defects have fixes and regression coverage. This report does
not approve a deployment before the operator actions below are completed.

| Audit finding | Delivered change |
| --- | --- |
| Committed `.env` | Git tracking removed; local file retained with owner-only permissions; Docker context exclusion and CI tracking check added. Local signing key rotated privately; known committed signing-key fingerprint rejected by API authentication. |
| Fixed superadmin | Automatic seed disabled; explicit password-prompt provisioning command added. Forward migration disables exact legacy seeded hash and revokes refresh tokens. Runtime guards reject that legacy hash even after reactivation. |
| Anonymous provider update | Current admin authorization required; anonymous and ordinary-user regression checks added. Raw source diagnostics restricted to admins. |
| Stale token account state | Every authenticated API request reads current account activity/roles; suspension, deletion, role inflation and demotion tested. |
| Login/OTP abuse | Shared database IP/account windows, OTP failed-attempt budget, resend cooldown and safe validation responses implemented. |
| Refresh race | Atomic conditional token consumption and replacement in one transaction; rollback and concurrent consumers tested. |
| Empty crypto price replacement | Quotes validated before replacement; provider-shaped malformed extraction preserves valid prices and reports failures. |
| Query-per-item lists | Gift-card latest rates and review engagement counts fetched in batches; bounded query-count tests plus value/moderation tests added. |
| Unbounded health history | SQL aggregates and bounded latest-run lookups replace loading all fetch-run objects. |
| Scheduler replica race | Due schedule locking and durable enqueue share one transaction; concurrent schedule and claim checks pass on PostgreSQL. |
| Lost manual tasks | API/bootstrap jobs stored before acknowledgement; separate leased worker with heartbeats, recovery and owner-fenced completion. Delivery is at least once, not exactly once. |
| Startup migrations | Removed from API start script; explicit one-time release migration documented. |
| Health/build/test workflow | Liveness/readiness probes, nonroot container, test image, CI, repaired legacy collection and consistent dependency exports added. |
| Repository lint | Formatter/import cleanup completed across existing code while preserving behavior and earlier FX changes. |
| Dependency drift/security | Stale lock regenerated; compatible FastAPI/Starlette and transitive packages updated. Requirements exported from the lock; CI audits runtime dependencies. |

## Verified

- **400 passed**, no skipped tests, using the refreshed locked environment and
  disposable PostgreSQL, including the repaired legacy collection path.
- Ruff 0.14.0: all checks pass; all 229 Python files checked are formatted.
- Lock validation and shell syntax checks pass; Git diff whitespace checks pass.
- Runtime dependency audit: **zero known vulnerabilities**, compared with 27 unique
  package/advisory pairs across ten packages in the previous lock. Checked against
  public advisories on 2026-11-05; this result can change as advisories are published.
- Two fresh database migration rehearsals passed, including one using the new lock.
- Temporary API live/readiness/auth/OpenAPI smoke and separate worker startup passed
  against disposable data. Worker startup with no SECRET_KEY also passed.
- Reproductions now return 401 for anonymous provider updates and suspended tokens.
  Gift-card listings use four SELECTs for both one-item and five-item pages. An OTP
  remains unusable after its failed-attempt budget is exhausted.
- No application database migration, deployment, schedule enablement or provider
  trade/transfer/payout was performed. Provider credentials were not sent anywhere
  during the work. Package audits sent package names and versions to public services.

## Operator actions still required

1. Rotate previously committed database, SMTP and provider credentials wherever used;
   install a fresh private signing key in each deployed environment. The local key
   rotation does not change secrets held by a remote deployment. Historical copies
   remain in Git until the repository owner carries out an approved cleanup.
2. Install the lock, back up the database, and explicitly apply migration
   `h4c5d6e7f8g9` and any earlier pending revisions. Provision a new administrator if
   the legacy seeded account was the only administrator. No automatic promotion or
   password replacement occurs.
3. Run the durable worker alongside the API. API-triggered ingestion now queues
   work and requires a worker; direct provider CLI commands remain immediate.
4. Run Docker builds/tests in CI or with a running Docker daemon. Local Docker
   execution was unavailable because the daemon was not running. The images and
   workflow have not been represented as locally executed builds.
5. Verify deployment TLS/proxy trust, monitoring, worker supervision, backup recovery
   and representative production load/query plans. These require deployment access
   or realistic operational data and are not established by the isolated regressions.

See [the release procedure](production-readiness.md) for commands, environment
settings and the migration/worker behavior. Fincra's explicitly authorized mapping
assumption and unavailable fees remain disclosed product limitations.
