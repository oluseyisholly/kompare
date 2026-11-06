DOCKER_COMPOSE := docker compose
DOCKER := $(shell which docker)

# Start development
up:
	$(DOCKER_COMPOSE) up

# Start development (detached mode)
upd:
	$(DOCKER_COMPOSE) up -d

# Down containers
down:
	$(DOCKER_COMPOSE) down

# Stop containers
stop:
	$(DOCKER_COMPOSE) stop

# Force build of docker
build:
	$(DOCKER_COMPOSE) build

# Delete containers
rm:
	$(DOCKER_COMPOSE) rm

# Pull docker images
pull:
	$(DOCKER_COMPOSE) pull

# Run unit tests locally
test:
	$(DOCKER_COMPOSE) --profile test run --build --rm test

# Run code linter and formatter (Ruff)
lint:
	uv run --locked ruff check app tests

# Format code only (Ruff)
format:
	uv run --locked ruff format app tests

# Access to container bash
bash:
	$(DOCKER) exec -it app bash

# Initialize Alembic migrations folder (only needed once)
init-migrations:
	$(DOCKER_COMPOSE) run --rm app python -m alembic -c app/alembic.ini init migrations

# Generate migration file
migrate:
	$(DOCKER_COMPOSE) run --rm app python -m alembic -c app/alembic.ini revision --autogenerate -m "$(msg)"

# Execute last migration file
exec-migration:
	$(DOCKER_COMPOSE) run --rm app python -m alembic -c app/alembic.ini upgrade head
