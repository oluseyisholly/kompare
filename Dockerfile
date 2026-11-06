FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl libpq-dev postgresql-client \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock README.md ./

RUN uv export --frozen --no-dev --format requirements-txt > /tmp/requirements.txt && \
    pip install --no-cache-dir -r /tmp/requirements.txt && \
    python -m playwright install --with-deps chromium && \
    rm -rf /var/lib/apt/lists/*

COPY app ./app
COPY start.sh ./start.sh

RUN chmod +x /app/start.sh

# Run the API as an unprivileged user; the worker uses the same image.
RUN useradd --create-home --uid 10001 kompare
USER kompare

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=3)"

EXPOSE 8000

CMD ["/app/start.sh"]

FROM runtime AS test
ENV RUFF_CACHE_DIR=/tmp/ruff-cache
USER root
RUN uv export --frozen --dev --format requirements-txt > /tmp/test-requirements.txt && \
    pip install --no-cache-dir -r /tmp/test-requirements.txt
COPY tests ./tests
USER kompare
HEALTHCHECK NONE
CMD ["python", "-m", "pytest", "tests", "-q", "-p", "no:cacheprovider"]

FROM runtime AS production
