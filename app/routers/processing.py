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
    Verifies connectivity to S3.

    Note: InfoCert does not provide a health check endpoint, so we only verify S3 access.
    """
    start_time = datetime.now(timezone.utc)
    try:
        logger.info("[HEALTH CHECK] Starting health check")

        # Check S3 access
        logger.debug("[HEALTH CHECK] Checking S3 bucket access...")
        s3_accessible = s3_service.check_bucket_access()
        logger.info(f"[HEALTH CHECK] S3 bucket access: {'✓ OK' if s3_accessible else '✗ FAILED'}")

        if not s3_accessible:
            logger.error("[HEALTH CHECK] ✗ Health check FAILED - S3 bucket not accessible")
            raise HTTPException(
                status_code=503,
                detail="S3 bucket is not accessible",
            )

        elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
        logger.info(f"[HEALTH CHECK] ✓ Health check PASSED | Duration: {elapsed:.2f}s")

        return HealthCheckResponse(
            status="healthy",
            timestamp=datetime.now(timezone.utc),
            version=__version__,
        )

    except Exception as e:
        elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
        log_exception(logger, e, f"[HEALTH CHECK] Health check failed after {elapsed:.2f}s")
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
    start_time = datetime.now(timezone.utc)
    try:
        logger.info(f"[RECERTIFY] Starting recertification | File: {request.file_key}")

        # Process the single file - will raise exception if anything fails
        result = await process_single_file(request.file_key)

        elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
        logger.info(
            f"[RECERTIFY] ✓ Recertification complete | "
            f"File: {request.file_key} | "
            f"Duration: {elapsed:.2f}s | "
            f"P7M: {result.p7m_file_key}"
        )
        return result

    except Exception as e:
        elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
        log_exception(
            logger,
            e,
            f"[RECERTIFY] ✗ Recertification failed | File: {request.file_key} | Duration: {elapsed:.2f}s"
        )
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
            f"[BATCH START] Starting batch processing | "
            f"Date range: {request.start_date.isoformat()} to {request.end_date.isoformat()} | "
            f"Prefix: {request.prefix or 'None'}"
        )

        # Step 1: List files from S3 by date range
        logger.debug("[BATCH STEP 1/2] Listing files from S3...")
        files = s3_service.list_files_by_date_range(
            start_date=request.start_date,
            end_date=request.end_date,
            prefix=request.prefix,
        )

        total_files = len(files)
        logger.info(f"[BATCH STEP 1/2] Found {total_files} files to process")

        if total_files == 0:
            processing_end = datetime.now(timezone.utc)
            duration = (processing_end - processing_start).total_seconds()
            logger.info(f"[BATCH COMPLETE] No files to process | Duration: {duration:.2f}s")

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
        logger.info(f"[BATCH STEP 2/2] Processing {total_files} files...")
        for index, file_metadata in enumerate(files, 1):
            logger.info(
                f"[BATCH PROGRESS] Processing file {index}/{total_files} ({(index/total_files*100):.1f}%) | "
                f"File: {file_metadata.key}"
            )
            result = await process_single_file(file_metadata.key)
            results.append(result)
            logger.debug(
                f"[BATCH PROGRESS] File {index}/{total_files} completed | "
                f"Status: {result.status.value}"
            )

        # Calculate statistics
        successful_files = len(
            [r for r in results if r.status == ProcessingStatus.COMPLETED]
        )
        failed_files = len(
            [r for r in results if r.status == ProcessingStatus.FAILED]
        )

        processing_end = datetime.now(timezone.utc)
        duration = (processing_end - processing_start).total_seconds()
        avg_time_per_file = duration / total_files if total_files > 0 else 0

        logger.info(
            f"[BATCH COMPLETE] ✓ Batch processing finished | "
            f"Total: {total_files} | "
            f"Successful: {successful_files} | "
            f"Failed: {failed_files} | "
            f"Duration: {duration:.2f}s | "
            f"Avg per file: {avg_time_per_file:.2f}s"
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
        elapsed = (datetime.now(timezone.utc) - processing_start).total_seconds()
        processed_count = len(results)
        log_exception(
            logger,
            e,
            f"[BATCH FAILED] ✗ Batch processing failed after {processed_count} files | Duration: {elapsed:.2f}s"
        )
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
    start_time = datetime.now(timezone.utc)
    logger.info(f"[FILE PROCESS] Starting processing | File: {file_key}")

    # Step 1: Download file from S3
    logger.debug(f"[FILE STEP 1/5] Downloading from S3 | File: {file_key}")
    file_content = s3_service.download_file(file_key)
    logger.info(f"[FILE STEP 1/5] Downloaded {len(file_content)} bytes from S3")

    # Step 2: Compute hash
    logger.debug(f"[FILE STEP 2/5] Computing file hash...")
    hash_info = hash_service.compute_hash(file_content, file_key)
    logger.info(
        f"[FILE STEP 2/5] Hash computed | "
        f"Algorithm: {hash_info.hash_algorithm} | "
        f"Hash: {hash_info.hash_value[:16]}..."
    )

    # Step 3: Create signature request and send to InfoCert
    filename = os.path.basename(file_key)
    sig_request = SignatureRequest(
        file_hash=hash_info.hash_value,
        hash_algorithm=hash_info.hash_algorithm,
        filename=filename,
    )

    logger.debug(f"[FILE STEP 3/5] Requesting digital signature from InfoCert...")
    sig_response = signature_service.sign_file_hash(sig_request)
    logger.info(
        f"[FILE STEP 3/5] Signature received | "
        f"Timestamp: {sig_response.timestamp.isoformat()}"
    )

    # P7M content is REQUIRED - fail if not available
    if not sig_response.p7m_content:
        error_msg = f"P7M content creation failed for {file_key} - signature service did not return P7M"
        logger.error(f"[FILE ERROR] {error_msg}")
        raise ValueError(error_msg)

    p7m_content = sig_response.p7m_content
    logger.debug(f"[FILE STEP 3/5] P7M file ready | Size: {len(p7m_content)} bytes")

    # Step 4: Upload P7M file to S3
    original_filename = os.path.basename(file_key)
    p7m_file_key = f"signed/{original_filename}.p7m"
    logger.debug(f"[FILE STEP 4/5] Uploading P7M to S3 | Destination: {p7m_file_key}")
    s3_service.upload_file(
        file_content=p7m_content,
        destination_key=p7m_file_key,
        content_type="application/pkcs7-mime",
    )
    signed_file_size = len(p7m_content)
    logger.info(f"[FILE STEP 4/5] P7M uploaded to S3 | Size: {signed_file_size} bytes")

    # Step 5: Save certification metadata to DynamoDB
    logger.debug(f"[FILE STEP 5/5] Saving metadata to DynamoDB...")
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
    logger.info(f"[FILE STEP 5/5] Metadata saved to DynamoDB")

    elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
    logger.info(
        f"[FILE COMPLETE] ✓ Processing complete | "
        f"File: {file_key} | "
        f"Duration: {elapsed:.2f}s | "
        f"Original: {hash_info.file_size} bytes | "
        f"P7M: {signed_file_size} bytes | "
        f"P7M location: {p7m_file_key}"
    )

    return FileProcessingResult(
        file_key=file_key,
        status=ProcessingStatus.COMPLETED,
        file_hash=hash_info.hash_value,
        signature=sig_response.signature,
        timestamp=sig_response.timestamp,
        p7m_file_key=p7m_file_key,
        error_message=None,
    )
