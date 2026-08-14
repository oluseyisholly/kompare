# ---------- Base Image ----------
FROM python:3.12-slim AS base

ENV DEBIAN_FRONTEND=noninteractive

# Install system packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /tmp

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install uv and use it to export and install dependencies
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
RUN uv export --no-hashes > requirements.txt && \
    pip install --no-cache-dir -r requirements.txt

# Set working directory
WORKDIR /app

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]