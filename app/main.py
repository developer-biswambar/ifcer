"""Main FastAPI application for IFCER Batch Service."""

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.config import settings
from app.routers import processing_routes, files_routes, certificates_routes
from app.middleware.correlation_id import CorrelationIdMiddleware
from app.utils.logger import setup_logger, log_exception
from app import __version__

# Initialize logger
logger = setup_logger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title=settings.app_name,
    description="Batch service for digital signature and timestamping of files for Italian register submission",
    version=__version__,
)

# Add middleware (order matters - correlation ID should be first to capture all requests)
app.add_middleware(CorrelationIdMiddleware)

# Include routers
app.include_router(processing_routes.router, tags=["Processing"])
app.include_router(files_routes.router, tags=["Files"])
app.include_router(certificates_routes.router, tags=["Certificates"])


@app.get("/", response_model=dict)
async def root():
    """Root endpoint."""
    return {
        "service": settings.app_name,
        "version": __version__,
        "status": "running",
    }


@app.on_event("startup")
async def startup_event():
    """Application startup event."""
    logger.info(f"Starting {settings.app_name} v{__version__}")
    logger.info(f"Environment: {settings.aws_region}")
    logger.info(f"S3 Bucket: {settings.s3_bucket_name}")
    logger.info(f"InfoCert API: {settings.infocert_api_url}")


@app.on_event("shutdown")
async def shutdown_event():
    """Application shutdown event."""
    logger.info(f"Shutting down {settings.app_name}")


# Exception handler for all unhandled exceptions
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler."""
    log_exception(logger, exc, "Unhandled exception")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "error": str(exc)},
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level=settings.log_level.lower(),
    )
