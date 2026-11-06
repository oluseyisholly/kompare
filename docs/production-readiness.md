# Production hardening and release procedure

Implemented 2026-11-05. These changes address the repository audit; approval of a
particular deployment still depends on credential rotation and infrastructure checks.
No production migration, trade, payout, provider credential change or deployment
was performed during implementation.

## Security remediation

- `.env` is removed from Git tracking, retained locally with owner-only permissions,
  excluded from Docker context, and covered by a CI check. The local API signing
  key was privately regenerated. The API refuses the known committed signing key
  by fingerprint; CLI ingestion still needs no signing key. Do not re-add this file
  or copy it into an image.
- Previously committed database, SMTP, Flutterwave and signing credentials must be
  rotated wherever they were used. Remove historical copies using the repository
  owner's approved process; this change does not rewrite Git history. Deleting a
  file in a new commit does not erase old commits. Do not paste keys into tickets.
- Fixed-password superadmin creation is removed from the historical seed revision.
  New databases do not get a privileged account automatically. The new migration
  disables accounts with the exact old seeded hash and revokes their refresh tokens;
  intentionally rotated accounts remain intact. Rollback never reactivates that account.
  API authentication also rejects that hash if the account is later reactivated.
- `PATCH /providers/{slug}` and raw-record diagnostics require current admin access.
  Authentication reads the current user record on every protected request, including
  roles, activity and verification metadata. Deleted/suspended users and demoted
  admins cannot continue using stale token claims. Ingestion CLIs need no API secret.
- Refresh rotation conditionally consumes a token exactly once and creates its
  replacement in the same transaction. A failed replacement rolls back consumption.
- Login and email/OTP endpoints have shared database-backed IP/account limits.
  Counters use hashed identifiers, not raw addresses. Public resends do not disclose
  account membership. Forwarded IP headers are not trusted by application code;
  configure the deployment's trusted proxy correctly.
- OTP verification serializes against resends and invalidates a code after the
  configured failed-attempt budget. New code issuance has a cooldown. Password/email
  inputs are bounded, and validation errors omit supplied credential values.

Defaults and environment names are in `.env.example`: login 10/account and 60/IP
per 900 seconds; OTP five failed attempts; resend cooldown 60 seconds; email requests
three/account and 20/IP per hour. Rate-limit responses include HTTP 429, a retry_after
value and Retry-After header. The worker prunes expired counter windows older than one day every six hours;
`AuthRateLimitRepository.prune_expired` is also available to operators. Active windows are retained. Edge/gateway controls
remain useful in addition to these application limits.

## Ingestion and query changes

- Empty/nonpositive crypto prices are rejected before current versions are replaced.
  Quidax/Busha report invalid records separately, retain raw evidence and leave valid
  existing prices unchanged. Partial runs are recorded as failures/partial results.
- Gift-card listings fetch current rates for the whole page in one query. Review
  vote/comment counts are grouped per page. Ingestion-health summaries aggregate in SQL
  and use bounded latest-run lookups. Mutual-fund batched snapshot retrieval remains.
- API manual/bootstrap triggers persist `ingestion_jobs` before returning 202 and a
  job_id. Scheduled requests atomically insert a job and advance next_run_at under a
  database lock. Multiple API replicas can poll without enqueueing the same due run.
- A separate worker claims jobs with PostgreSQL SKIP LOCKED and token-fenced leases,
  renews leases during work, and records completion. Expired claims can be reclaimed
  up to the configured maximum attempts. Work runs outside the API event loop.
- Queue delivery is **at least once**: a crash after upstream fetch/persistence but
  before acknowledgement can repeat work. Existing provenance, same-run uniqueness
  and refresh ordering protections remain. A killed process is not exactly-once
  delivery. Failures are visible in jobs and provider fetch runs. Expired crash retries
  stop at INGESTION_JOB_MAX_ATTEMPTS. Explicit provider failures are terminal jobs.
- Inspect provider jobs as an admin at
  `GET /providers/{slug}/ingestion-jobs/{job_id}`. Use slug `all` for an all-provider
  bootstrap job. Lease tokens are not exposed by this endpoint.
- Manual and scheduled provider execution share one registry. Direct provider CLIs
  continue to execute immediately; the API now requires a running worker for queued work.
- Fincra's user-authorized temporary side convention remains explicitly labelled
  assumed; no new mapping block or fee assumptions have been introduced.

## Release steps — operator actions

1. Rotate the credentials that were committed, update the deployment secret store,
   and configure production provider URLs/credentials. The checked-out local settings
   were not substituted for production settings. A new signing key invalidates old tokens.
2. Install the committed dependency lock or build the image. FastAPI/Starlette and
   vulnerable transitive packages were updated. Requirements are exported from uv.lock.

   ```sh
   python -m pip install uv==0.13.7
   uv sync --locked --group dev
   ```

3. Take a verified backup and apply migrations **once**, before starting the new API
   or worker. `start.sh` no longer runs migrations in every API replica.

   ```sh
   python -m alembic -c app/alembic.ini upgrade head
   ```

   New revision: `h4c5d6e7f8g9` after `g3b4c5d6e7f8`. It adds shared auth limit
   counters, OTP failed-attempt counts and durable ingestion jobs, and disables
   unrotated seeded credentials. Earlier pending migrations still apply normally.
   Migration `g3b4c5d6e7f8` cannot reconstruct removed environment labels on downgrade;
   recovery from that older schema requires a backup. Do not expect downgrade to
   re-enable compromised accounts.

4. Provision a new superadmin explicitly if needed. Use a private address that is not
   an existing account; the command refuses silent promotion or replacement. Passwords
   are prompted without echo and never passed on the command line.

   ```sh
   python -m app.scripts.create_superadmin --email operator@example.com
   ```

5. Start API and worker as separately supervised processes:

   ```sh
   python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
   python -m app.scripts.run_ingestion_worker
   ```

   Or use `docker compose --profile ingestion up --build`. This does not enable
   schedules by itself: ENABLE_INGESTION_SCHEDULER retains its configured value
   (default false). The worker processes manual jobs even with schedules disabled.
   Stop gracefully so current work can finish while its lease is renewed.

6. `/health/live` checks process liveness. `/health/ready` checks database connectivity
   and exact migration-head compatibility, returning a generic 503 when not ready.
   The container probes readiness. Place the service behind TLS with the intended
   trusted-proxy configuration and verify backups, alerting and worker supervision.
   No runtime secret values appear in these responses.

## Checks

```sh
uv run --locked ruff check app tests
uv run --locked ruff format --check app tests
uv run --locked pytest
# Full fresh migration rehearsal and real PostgreSQL concurrency tests:
uv run scripts/test-postgres.sh
# Docker runtime plus independently packaged test target:
docker build --target production -t kompare-runtime .
docker compose --profile test run --build --rm test
```

`scripts/test-postgres.sh` always creates a private disposable cluster under
`/tmp/kompare-wise-pg.*`, uses a Unix socket with no TCP listener, overrides all
application database settings, and stops it on exit. It requires PostgreSQL tools
and a free test port 55484. Never point optional integration tests at a live database.

CI runs locked installs, formatting/lint, secret-tracking checks, fresh migrations,
PostgreSQL races and Docker builds/tests. The Python test suite defaults to `tests/`;
explicitly including the old `app/tests/` location no longer fails imports.

Verification and operator-only gaps are recorded in the delivery report. Docker
builds could not be executed locally because the Docker daemon was unavailable;
the CI workflow contains these checks. Runtime dependency auditing against public
advisories found no known vulnerabilities in the refreshed lock as of 2026-11-05.
A passed audit is not a guarantee against future advisories. Run it regularly.

Final implementation verification: **400 tests passed with PostgreSQL enabled**;
lint, formatting and lock validation passed. See [the delivery results](production-hardening-results.md)
for the audit disposition and operator-only actions that remain before rollout.
