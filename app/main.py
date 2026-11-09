from contextlib import asynccontextmanager

import app.models  # noqa: F401
from app.core.cors import CorsFastAPI
from app.core.error_handlers import register_exception_handlers
from app.core.logger import logger
from app.core.openapi import register_provider_documentation
from app.core.security import validate_auth_secret
from app.routers import (
    admin_user_router,
    audit_log_router,
    auth_router,
    provider_review_router,
    provider_router,
    report_router,
)
from app.routers.fx import router as fx_router
from app.routers.health import router as health_router
from app.routers.mutual_fund import router as mutual_fund_router
from app.services.ingestion_scheduler import IngestionSchedulerService


@asynccontextmanager
async def lifespan(application):
    await start_scheduler()
    try:
        yield
    finally:
        await stop_scheduler()


# Initialize FastAPI application with metadata
app = CorsFastAPI(
    title="Kompare",
    version="1.0",
    description="Compare provider rates, gift cards and verification requirements.",
    docs_url="/",
    lifespan=lifespan,
    swagger_ui_parameters={"docExpansion": "none"},
)

register_exception_handlers(app)

scheduler = IngestionSchedulerService()

# Include API routers
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(audit_log_router)
app.include_router(admin_user_router)
app.include_router(provider_router)
app.include_router(provider_review_router)
app.include_router(report_router)
app.include_router(mutual_fund_router)
app.include_router(fx_router)
register_provider_documentation(app)
logger.info("API routers registered.")


async def start_scheduler() -> None:
    validate_auth_secret()
    await scheduler.start()


async def stop_scheduler() -> None:
    await scheduler.stop()
