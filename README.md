# Kompare

Kompare backend for provider comparisons, stored exchange rates, gift cards and mutual funds.

---

## 🚀 Features

- **FastAPI** project structure ready for medium and large-scale applications
- **PostgreSQL** database (via Docker) with **Alembic** for migrations
- **uv** for fast dependency management
- **Ruff** for linting and code formatting (replaces Black, Flake8, isort)
- **Hot-reload** support with watchfiles for development on macOS/Linux/Windows
- **Environment variables** handled via `.env` and `python-dotenv`
- **Docker Compose** setup for running the app and database
- **Makefile** with useful shortcuts for development
- **Structured logging** included
- **Base service pattern** for clean CRUD operations

---

## ⚙️ Requirements

- **Docker** (Desktop or Rancher Desktop)
- **Make** (recommended for command shortcuts)
- **Python 3.12+** (optional, for local execution without Docker)

---

## 📁 Project Structure

```
.
├── app/
│   ├── core/              # Core configuration (database, settings, logger)
│   ├── models/            # SQLAlchemy models
│   ├── schemas/           # Pydantic schemas
│   ├── services/          # Business logic layer
│   ├── routers/           # API endpoints
│   ├── migrations/        # Alembic migrations
│   └── main.py            # FastAPI application entry point
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml         # Dependencies and tool configuration
├── uv.lock               # Locked dependencies
├── Makefile              # Development commands
└── .env                  # Environment variables
```

---

## 🧩 Environment Setup

Create a `.env` file in the project root:

```env
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_DB=mydatabase
POSTGRES_HOST=db
POSTGRES_PORT=5432
```

You can also use the provided `.env.example` as a template.

Browser CORS access allows all origins by default (`CORS_ALLOW_ORIGINS=*`). Methods
and request headers, including `Authorization`, are allowed. Protected endpoints still
require their normal bearer token and role. Cookie credentials are not enabled.
To restrict origins, set a comma-separated list of frontend origins in `.env`, then
restart the API. CORS headers also cover error responses, and `Retry-After` is exposed.

Set `SECRET_KEY` in your `.env` to a private, randomly generated value before
starting the app. Generate one with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

API startup fails if the key is missing, blank, or set to a known development
placeholder (`change-me` or `kompare-dev-secret`). Standalone ingestion commands do not
require this authentication key. Keep the key out of version control.

---

## ▶️ Run the Local Environment

Start the containers (FastAPI + PostgreSQL):

```bash
make up
```

Once the command completes, open your browser at:
👉 [http://localhost:8000](http://localhost:8000)

You'll be redirected to the FastAPI interactive docs (Swagger UI).

### Hot-Reload Development

The application supports hot-reload when you modify Python files:
- Edit any `.py` file in the `app/` directory
- Save the file
- The server automatically reloads with your changes

---

## 🧰 Useful Makefile Commands

| Command | Description |
|----------|--------------|
| `make up` | Start the environment in the foreground |
| `make upd` | Start the environment in detached mode |
| `make down` | Stop and remove containers |
| `make stop` | Stop containers without removing them |
| `make build` | Force rebuild Docker images |
| `make rm` | Remove stopped containers |
| `make test` | Run unit tests using pytest |
| `make lint` | Run Ruff linter with auto-fix |
| `make format` | Format code with Ruff |
| `make bash` | Open a bash shell inside the app container |
| `make init-migrations` | Initialize Alembic migrations folder |
| `make migrate msg="message"` | Create a new Alembic migration |
| `make exec-migration` | Apply pending migrations |
| `make migrate-up` | Wait for DB and run migrations automatically |

---

## 🧱 Database Migrations

### Initialize Alembic (first time only)

```bash
make init-migrations
```

### Generate a New Migration

```bash
make migrate msg="add users table"
```

### Apply Migrations

```bash
make exec-migration
```

Apply migrations once as a release step before starting API/worker replicas. App startup does not apply migrations. See [production hardening and release steps](docs/production-readiness.md).

---

## 🧪 Run Tests

Execute all unit tests using pytest:

```bash
make test
```

---

## 🧼 Code Quality

### Run Linter

```bash
make lint
```

This runs `ruff check --fix` to find and automatically fix code issues.

### Format Code

```bash
make format
```

This runs `ruff format` to ensure consistent code style.

### Configuration

Ruff is configured in `pyproject.toml` with:
- Line length: 100 characters
- Python 3.12+ target
- Automatic import sorting
- Per-file ignores for `__init__.py` and migration files

---

## 🏗️ Base Service Pattern

The template includes a generic `BaseService` class for CRUD operations:

```python
from services.base import BaseService
from models.item import Item

class ItemService(BaseService):
    def __init__(self, db: Session):
        super().__init__(db, Item)

# Provides: create_item, list_items, get_item, update_item, delete_item
```

---

## 🐳 Docker Details

### PostgreSQL

- Image: `postgres:15`
- Port: `5432`
- Health checks included
- Persistent volume: `postgres_data`

### FastAPI App

- Python: `3.12-slim`
- Package manager: `uv` (faster than pip)
- Hot-reload enabled with `watchfiles`
- Working directory: `/app`

---

## 🧠 Notes

- **Hot-reload on macOS**: Configured with `WATCHFILES_FORCE_POLLING=true` for reliable file change detection
- **Database connection**: Waits for PostgreSQL to be ready before starting
- **Migrations**: Automatically applied on container startup
- **Environment variables**: Loaded from `.env` file in both local and Docker environments
- **Primary keys**: BaseService automatically detects primary key names using SQLAlchemy inspection

---

## 🔧 Dependencies

Main dependencies (defined in `pyproject.toml`):

- **fastapi** - Modern web framework
- **uvicorn** - ASGI server with WebSockets support
- **sqlalchemy** - ORM for database operations
- **alembic** - Database migration tool
- **psycopg2-binary** - PostgreSQL adapter
- **python-dotenv** - Environment variable management
- **watchfiles** - File system monitoring for hot-reload

Dev dependencies:

- **ruff** - Fast Python linter and formatter
- **pytest** - Testing framework

---

## 🏁 Getting Started

1. Clone the repository
2. Copy `.env.example` to `.env` and configure
3. Run `make up` to start the environment
4. Visit [http://localhost:8000](http://localhost:8000)
5. Start building your API! 🚀

---

## 📝 License

This template is open source and available for use in your projects.

## Shared FX data

Provider-keyed FX APIs, normalized models and network-free local conversion are documented in
[the shared FX architecture](docs/fx-architecture.md). Wise collection details are in
[the Wise integration guide](docs/wise-fx-integration.md), including configuration,
API examples, migration and verification results. Frontend calculations use `POST /fx/convert`;
the live quote endpoint is an admin diagnostic. Wise credentials are optional at startup.

Flutterwave transfer-rate sampling uses the same provider-keyed APIs and ingestion
dispatcher. See [the Flutterwave guide](docs/flutterwave-fx-integration.md) for test/live
configuration, destination-amount scenarios and local estimates before fees.

Fincra FX ingestion and local estimates: see [integration guide](docs/fincra-fx-integration.md).

`POST /fx/convert` uses the same four inputs for Wise, Flutterwave and Fincra:
`provider`, `source_currency`, `target_currency`, `source_amount`. Legacy `rate_side`
is rejected with 422. Fincra temporarily assumes provider-side buying/selling of
the base currency, priced in quote per base units: direct BUY, otherwise reciprocal
reversed SELL. Responses disclose this assumption pending provider confirmation.
No database migration/configuration is needed for this policy change. See the
[unified conversion contract](docs/fx-architecture.md#unified-conversion-contract).


## Production hardening

Read [production hardening and release steps](docs/production-readiness.md) before
rollout. Rotate previously committed credentials, apply the new migration explicitly,
provision an administrator securely, and start the durable ingestion worker alongside
the API. No default administrator is created. `.env` is private and untracked.

```sh
uv sync --locked --group dev
python -m alembic -c app/alembic.ini upgrade head
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
# Separate terminal/process; required for API-triggered and scheduled ingestion:
python -m app.scripts.run_ingestion_worker
```

Direct provider ingestion commands remain available. Public liveness/readiness
probes are `/health/live` and `/health/ready`; raw diagnostics require an admin.
