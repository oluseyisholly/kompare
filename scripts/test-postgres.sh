#!/usr/bin/env sh
# Always use a new private cluster; never use POSTGRES_* from the application .env.
set -eu

if command -v initdb >/dev/null 2>&1; then
  kompare_pg_bin=$(dirname "$(command -v initdb)")
else
  kompare_pg_bin=$(pg_config --bindir)
fi
kompare_test_pg=$(mktemp -d /tmp/kompare-wise-pg.XXXXXX)
cleanup() {
  "$kompare_pg_bin/pg_ctl" -D "$kompare_test_pg/data" -m fast -w stop >/dev/null 2>&1 || true
}
trap cleanup EXIT HUP INT TERM
"$kompare_pg_bin/initdb" -D "$kompare_test_pg/data" --auth=trust -U postgres > "$kompare_test_pg/init.log"
"$kompare_pg_bin/pg_ctl" -D "$kompare_test_pg/data" -l "$kompare_test_pg/server.log" \
  -o "-k $kompare_test_pg -p 55484 -c listen_addresses=''" -w start
"$kompare_pg_bin/createdb" -h "$kompare_test_pg" -p 55484 -U postgres kompare_fx_refresh_test
export POSTGRES_HOST="$kompare_test_pg" POSTGRES_PORT=55484 POSTGRES_USER=postgres
export POSTGRES_PASSWORD='' POSTGRES_DB=kompare_fx_refresh_test PYTHONDONTWRITEBYTECODE=1
export KOMPARE_FX_TEST_PG_SOCKET="$kompare_test_pg"
python -m alembic -c app/alembic.ini upgrade head
python -m pytest tests -q -p no:cacheprovider
