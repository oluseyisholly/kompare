from fastapi import FastAPI
from fastapi.responses import RedirectResponse

from app.core.error_handlers import register_exception_handlers
from app.core.logger import logger
import app.models  # noqa: F401
from app.routers import busha_router, item_router, platform_router, provider_router, quidax_router, report_router

# Initialize FastAPI application with metadata
app = FastAPI(
    title="Kompare",
    version="1.0",
    description="A project starter for FastAPI",
    docs_url="/",
)

register_exception_handlers(app)

# Include API routers
app.include_router(item_router)
app.include_router(busha_router)
app.include_router(platform_router)
app.include_router(provider_router)
app.include_router(quidax_router)
app.include_router(report_router)
logger.info("API routers registered.")



@app.get("/", include_in_schema=False)
def redirect_to_docs():
    """Redirect to the API documentation."""
    logger.info("Redirecting to /docs")
    return RedirectResponse(url="/docs")
