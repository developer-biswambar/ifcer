"""Main FastAPI application for IFCER Batch Service."""

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from datetime import datetime
import time
from typing import List
import os

from app.config import settings
from app.models.schemas import (
    DateRangeRequest,
    BatchProcessingResponse,
    FileProcessingResult,
    ProcessingStatus,
    HealthCheckResponse,
    SignatureRequest,
)
from app.services.s3_service import S3Service
from app.services.hash_service import HashService
from app.services.signature_service import SignatureService
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

# Initialize services
s3_service = S3Service()
hash_service = HashService()
signature_service = SignatureService()


@app.get("/", response_model=dict)
async def root():
    """Root endpoint."""
    return {
        "service": settings.app_name,
        "version": __version__,
        "status": "running",
    }


@app.get("/health", response_model=HealthCheckResponse)
async def health_check():
    """
    Health check endpoint.
    Verifies connectivity to S3 and vendor API.
    """
    try:
        logger.info("Performing health check")

        # Check S3 access
        s3_accessible = s3_service.check_bucket_access()

        # Check vendor API access
        vendor_accessible = signature_service.health_check()

        if not s3_accessible or not vendor_accessible:
            raise HTTPException(
                status_code=503,
                detail="Service dependencies are not accessible",
            )

        return HealthCheckResponse(
            status="healthy",
            timestamp=datetime.utcnow(),
            version=__version__,
        )

    except Exception as e:
        log_exception(logger, e, "Health check failed")
        raise HTTPException(status_code=503, detail=str(e))


@app.post("/process", response_model=BatchProcessingResponse)
async def process_files(request: DateRangeRequest):
    """
    Process files from S3 bucket within the specified date range.

    This endpoint:
    1. Fetches files from S3 based on upload date range
    2. Computes hash for each file
    3. Sends hash to vendor API for digital signature and timestamp
    4. Creates P7M files for Italian register submission
    5. Uploads P7M files back to S3

    Args:
        request: DateRangeRequest with start_date, end_date, and optional prefix

    Returns:
        BatchProcessingResponse with processing results
    """
    processing_start = datetime.utcnow()
    results: List[FileProcessingResult] = []

    try:
        logger.info(
            f"Starting batch processing from {request.start_date} to {request.end_date}"
        )

        # Step 1: List files from S3 by date range
        files = s3_service.list_files_by_date_range(
            start_date=request.start_date,
            end_date=request.end_date,
            prefix=request.prefix,
        )

        total_files = len(files)
        logger.info(f"Found {total_files} files to process")

        if total_files == 0:
            processing_end = datetime.utcnow()
            duration = (processing_end - processing_start).total_seconds()

            return BatchProcessingResponse(
                total_files=0,
                processed_files=0,
                successful_files=0,
                failed_files=0,
                results=[],
                processing_start=processing_start,
                processing_end=processing_end,
                duration_seconds=duration,
            )

        # Step 2: Process each file
        for file_metadata in files:
            result = await process_single_file(file_metadata.key)
            results.append(result)

        # Calculate statistics
        successful_files = len(
            [r for r in results if r.status == ProcessingStatus.COMPLETED]
        )
        failed_files = len(
            [r for r in results if r.status == ProcessingStatus.FAILED]
        )

        processing_end = datetime.utcnow()
        duration = (processing_end - processing_start).total_seconds()

        logger.info(
            f"Batch processing completed: {successful_files} successful, {failed_files} failed"
        )

        return BatchProcessingResponse(
            total_files=total_files,
            processed_files=len(results),
            successful_files=successful_files,
            failed_files=failed_files,
            results=results,
            processing_start=processing_start,
            processing_end=processing_end,
            duration_seconds=duration,
        )

    except Exception as e:
        log_exception(logger, e, "Batch processing failed")
        raise HTTPException(status_code=500, detail=str(e))


async def process_single_file(file_key: str) -> FileProcessingResult:
    """
    Process a single file: download, hash, sign, create P7M, upload.

    Args:
        file_key: S3 file key

    Returns:
        FileProcessingResult with processing outcome
    """
    try:
        logger.info(f"Processing file: {file_key}")

        # Download file from S3
        file_content = s3_service.download_file(file_key)

        # Compute hash
        hash_info = hash_service.compute_hash(file_content, file_key)

        # Create signature request
        filename = os.path.basename(file_key)
        sig_request = SignatureRequest(
            file_hash=hash_info.hash_value,
            hash_algorithm=hash_info.hash_algorithm,
            filename=filename,
        )

        # Request signature from vendor API
        sig_response = signature_service.sign_file_hash(sig_request)

        # Create P7M file (if not provided by vendor)
        # Note: If vendor returns P7M content, use that directly
        if sig_response.p7m_content:
            p7m_content = sig_response.p7m_content
        else:
            # TODO: Implement P7M creation if vendor doesn't provide it
            logger.warning(
                f"P7M content not provided by vendor for {file_key}, skipping P7M upload"
            )
            p7m_content = None

        # Upload P7M file to S3 (if available)
        p7m_file_key = None
        if p7m_content:
            # Create P7M file key (same path, .p7m extension)
            p7m_file_key = f"{file_key}.p7m"
            s3_service.upload_file(
                file_content=p7m_content,
                destination_key=p7m_file_key,
                content_type="application/pkcs7-mime",
            )

        logger.info(f"Successfully processed file: {file_key}")

        return FileProcessingResult(
            file_key=file_key,
            status=ProcessingStatus.COMPLETED,
            file_hash=hash_info.hash_value,
            signature=sig_response.signature,
            timestamp=sig_response.timestamp,
            p7m_file_key=p7m_file_key,
            error_message=None,
        )

    except Exception as e:
        log_exception(logger, e, f"Failed to process file: {file_key}")

        return FileProcessingResult(
            file_key=file_key,
            status=ProcessingStatus.FAILED,
            file_hash=None,
            signature=None,
            timestamp=None,
            p7m_file_key=None,
            error_message=str(e),
        )


@app.on_event("startup")
async def startup_event():
    """Application startup event."""
    logger.info(f"Starting {settings.app_name} v{__version__}")
    logger.info(f"Environment: {settings.aws_region}")
    logger.info(f"S3 Bucket: {settings.s3_bucket_name}")
    logger.info(f"Vendor API: {settings.vendor_api_url}")


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
