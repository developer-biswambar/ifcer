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

# OpenAPI documentation configuration
DESCRIPTION = """
## IFCER Batch Service API

Batch service for **digital signature** and **timestamping** of files for Italian register submission.

This service integrates with InfoCert's Remote Signature API to provide CAdES-BES compliant digital signatures
with RFC 3161 timestamps for regulatory compliance.

### Key Features

* **Batch Processing**: Process multiple files efficiently using batch signing API
* **Smart Processing**: Skip already-processed files to avoid unnecessary API costs
* **Fail-Safe**: Continue-on-error behavior with detailed error tracking
* **CAdES-BES Compliance**: ETSI EN 319 122-1 compliant signatures
* **Timestamping**: RFC 3161 compliant timestamps from InfoCert TSA
* **S3 Integration**: Seamless file upload/download from AWS S3
* **DynamoDB Tracking**: Persistent certification records with optional TTL
* **mTLS Security**: Mutual TLS authentication with InfoCert API

### Processing Workflow

1. **Upload files** to S3 `uploads/` folder
2. **Call /process** endpoint with date range
3. Service downloads files, computes hashes, and sends to InfoCert
4. InfoCert returns digital signatures and timestamps
5. Service creates P7M files (PKCS#7 with embedded original file)
6. P7M files uploaded to S3 `signed/` folder
7. Metadata saved to DynamoDB

### API Endpoints Overview

* **Processing**: Batch processing, recertification, and reprocessing
* **Files**: File verification and download operations
* **Certificates**: Certificate management and verification

### Authentication

All InfoCert API calls use:
- **mTLS**: Mutual TLS with client certificate
- **Bearer Token**: SAT (Signature Activation Token)
- **X-signer-id**: Credential ID header
- **PIN**: Signature PIN in request body

### Support

For issues or questions, contact the platform team.
"""

# API tags metadata for better organization
tags_metadata = [
    {
        "name": "Processing",
        "description": "**Core processing endpoints** for batch file certification, recertification, and reprocessing. "
                       "These endpoints handle the main workflow of signing files with InfoCert.",
    },
    {
        "name": "Files",
        "description": "**File management endpoints** for verifying P7M signatures, downloading signed files, "
                       "and querying certification records from DynamoDB.",
    },
    {
        "name": "Certificates",
        "description": "**Certificate management endpoints** for fetching and verifying InfoCert signing certificates. "
                       "Used for certificate validation and troubleshooting.",
    },
]

# Initialize FastAPI app with enhanced configuration
app = FastAPI(
    title=settings.app_name,
    description=DESCRIPTION,
    version=__version__,
    openapi_tags=tags_metadata,
    root_path=settings.root_path,  # For ALB path rewriting (e.g., "/infocert")
    docs_url="/docs",
    redoc_url=None,  # ReDoc disabled - use Swagger UI only
    openapi_url="/openapi.json",
    contact={
        "name": "IFCER Platform Team",
        "email": "support@example.com",
    },
    license_info={
        "name": "Proprietary",
    },
    terms_of_service="https://example.com/terms",
    swagger_ui_parameters={
        "defaultModelsExpandDepth": -1,  # Hide schemas section by default
        "docExpansion": "list",  # Expand only tags by default
        "filter": True,  # Enable search/filter
        "syntaxHighlight.theme": "monokai",  # Code syntax highlighting theme
        "tryItOutEnabled": True,  # Enable "Try it out" by default
        "persistAuthorization": True,  # Persist authorization between page refreshes
    },
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
        "root_path": settings.root_path or "/",
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
