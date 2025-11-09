"""Processing endpoints for file certification."""

from fastapi import APIRouter, HTTPException
from datetime import datetime, timezone
from typing import List
import os

from app.models.schemas import (
    DateRangeRequest,
    SingleFileRequest,
    BatchProcessingResponse,
    FileProcessingResult,
    ProcessingStatus,
    HealthCheckResponse,
    SignatureRequest,
)
from app.services.s3_service import S3Service
from app.services.hash_service import HashService
from app.services.signature_service import SignatureService
from app.services.dynamodb_service import DynamoDBService
from app.utils.logger import setup_logger, log_exception
from app import __version__

logger = setup_logger(__name__)

# Initialize services
s3_service = S3Service()
hash_service = HashService()
signature_service = SignatureService()
dynamodb_service = DynamoDBService()

router = APIRouter()


@router.get("/health", response_model=HealthCheckResponse)
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
            timestamp=datetime.now(timezone.utc),
            version=__version__,
        )

    except Exception as e:
        log_exception(logger, e, "Health check failed")
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/recertify", response_model=FileProcessingResult)
async def recertify_single_file(request: SingleFileRequest):
    """
    Recertify a single file from S3.

    FAIL-FAST BEHAVIOR: If processing fails (including P7M creation), the operation
    will fail immediately with an error. P7M creation is REQUIRED.

    This endpoint allows you to process a single file by its S3 key, useful for:
    - Recertifying files that previously failed
    - Re-signing files that need updated timestamps
    - Processing individual files on demand

    The endpoint:
    1. Downloads the file from S3 using the provided key
    2. Computes the file hash
    3. Sends hash to vendor API for digital signature and timestamp
    4. Creates P7M file (REQUIRED - fails if P7M creation fails)
    5. Uploads P7M file back to S3 in signed/ folder
    6. Saves metadata to DynamoDB (REQUIRED - fails if save fails)

    Args:
        request: SingleFileRequest with file_key

    Returns:
        FileProcessingResult with processing outcome (only on success)

    Raises:
        HTTPException: If processing fails at any step (fail-fast behavior)
    """
    try:
        logger.info(f"Recertifying single file: {request.file_key}")

        # Process the single file - will raise exception if anything fails
        result = await process_single_file(request.file_key)

        logger.info(f"Successfully recertified file: {request.file_key}")
        return result

    except Exception as e:
        log_exception(logger, e, f"Recertification failed for: {request.file_key}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/process", response_model=BatchProcessingResponse)
async def process_files(request: DateRangeRequest):
    """
    Process files from S3 bucket within the specified date range.

    FAIL-FAST BEHAVIOR: If ANY single file fails processing (including P7M creation),
    the ENTIRE batch will fail immediately. This ensures data consistency and prevents
    partial processing.

    This endpoint:
    1. Fetches files from S3 based on upload date range
    2. Computes hash for each file
    3. Sends hash to vendor API for digital signature and timestamp
    4. Creates P7M files (REQUIRED - fails if P7M creation fails)
    5. Uploads P7M files back to S3 in signed/ folder
    6. Saves metadata to DynamoDB (REQUIRED - fails if save fails)

    Args:
        request: DateRangeRequest with start_date, end_date, and optional prefix

    Returns:
        BatchProcessingResponse with processing results (only if ALL files succeed)

    Raises:
        HTTPException: If any file fails processing (fail-fast behavior)
    """
    processing_start = datetime.now(timezone.utc)
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
            processing_end = datetime.now(timezone.utc)
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

        processing_end = datetime.now(timezone.utc)
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

    This function does NOT catch exceptions - failures will propagate to the caller,
    causing the entire batch to fail. This ensures fail-fast behavior.

    Args:
        file_key: S3 file key

    Returns:
        FileProcessingResult with processing outcome

    Raises:
        Exception: Any processing error will propagate and fail the batch
    """
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

    # P7M content is REQUIRED - fail if not available
    if not sig_response.p7m_content:
        error_msg = f"P7M content creation failed for {file_key} - signature service did not return P7M"
        logger.error(error_msg)
        raise ValueError(error_msg)

    p7m_content = sig_response.p7m_content

    # Upload P7M file to S3
    # Create P7M file key in signed/ folder
    original_filename = os.path.basename(file_key)
    p7m_file_key = f"signed/{original_filename}.p7m"
    s3_service.upload_file(
        file_content=p7m_content,
        destination_key=p7m_file_key,
        content_type="application/pkcs7-mime",
    )
    signed_file_size = len(p7m_content)

    # Save certification metadata to DynamoDB
    dynamodb_service.save_certification(
        file_key=file_key,
        file_hash=hash_info.hash_value,
        hash_algorithm=hash_info.hash_algorithm,
        digital_signature=sig_response.signature,
        vendor_timestamp=sig_response.timestamp,
        signed_file_key=p7m_file_key,
        file_size=hash_info.file_size,
        signed_file_size=signed_file_size,
        status="completed",
    )
    logger.info(f"Saved certification metadata to DynamoDB for: {file_key}")

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
