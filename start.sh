#!/usr/bin/env sh
set -eu

# Apply migrations once as an explicit release step, never from API replicas.
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
