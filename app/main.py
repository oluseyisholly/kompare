from fastapi import FastAPI
from fastapi.responses import RedirectResponse

from app.core.error_handlers import register_exception_handlers
from app.core.logger import logger
from app.core.openapi import register_provider_documentation
from app.services.ingestion_scheduler import IngestionSchedulerService
import app.models  # noqa: F401
from app.routers import auth_router, provider_router, report_router

# Initialize FastAPI application with metadata
app = FastAPI(
    title="Kompare",
    version="1.0",
    description="Compare provider rates, gift cards and verification requirements.",
    docs_url="/",
    swagger_ui_parameters={"docExpansion": "none"},
)

register_exception_handlers(app)

scheduler = IngestionSchedulerService()

# Include API routers
app.include_router(auth_router)
app.include_router(provider_router)
app.include_router(report_router)
register_provider_documentation(app)
logger.info("API routers registered.")


@app.on_event("startup")
async def start_scheduler() -> None:
    await scheduler.start()


@app.on_event("shutdown")
async def stop_scheduler() -> None:
    await scheduler.stop()



@app.get("/", include_in_schema=False)
def redirect_to_docs():
    """Redirect to the API documentation."""
    logger.info("Redirecting to /docs")
    return RedirectResponse(url="/docs")
