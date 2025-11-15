"""Processing endpoints for file certification."""

from fastapi import APIRouter, HTTPException
from datetime import datetime, timezone
from typing import List
import os
import asyncio

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
from app.services.validation_service import ValidationService
from app.services.notification_service import NotificationService
from app.utils.logger import setup_logger, log_exception
from app.config import settings
from app.middleware.correlation_id import get_correlation_id
from app import __version__

logger = setup_logger(__name__)

# Initialize services
s3_service = S3Service()
hash_service = HashService()
signature_service = SignatureService()
dynamodb_service = DynamoDBService()
validation_service = ValidationService()
notification_service = NotificationService()

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
    3. Sends hash to InfoCert API for signature
    4. Creates P7M file with ORIGINAL FILE EMBEDDED (REQUIRED - fails if creation fails):
       - {filename}.p7m: PKCS#7/CAdES signature with original file content embedded
       - Example: abc.pdf becomes abc.pdf.p7m
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

    SMART PROCESSING (NEW): By default, skips files that have already been successfully
    processed. This prevents unnecessary reprocessing and API costs.
    - Default behavior (reprocess=False): Only process new/failed files
    - Set reprocess=True: Force reprocessing of all files (including already-signed)

    CONTINUE-ON-ERROR BEHAVIOR: Processes ALL files even if some fail. Failed files
    are saved to DynamoDB with status="failed" and error details. This allows you to:
    - Process entire monthly batch in one run
    - Review all failures at once
    - Retry only failed files using /recertify endpoint

    PREFIX HANDLING:
    - If prefix not provided: searches in "uploads/" folder
    - If prefix provided (e.g., "abc"): searches in "uploads/abc/" folder
    - This allows organizing files by environment/client while maintaining structure

    This endpoint:
    1. Fetches files from S3 based on upload date range and prefix
    2. Checks DynamoDB to identify already-processed files (unless reprocess=True)
    3. For each unprocessed file (in parallel):
       - Downloads and computes hash
       - Sends to InfoCert API for signature
       - Creates P7M with embedded original file
       - Uploads to S3 and saves to DynamoDB
       - If fails: Saves error to DynamoDB, continues with next file
    4. Returns results for ALL processed files (successful and failed)
    5. Sends SNS notification with batch statistics (if configured)

    Args:
        request: DateRangeRequest with:
            - start_date: Start of date range
            - end_date: End of date range
            - prefix: Optional S3 prefix/subfolder
            - reprocess: Whether to reprocess already-signed files (default: False)

    Returns:
        BatchProcessingResponse with complete results (both successful and failed files)
    """
    processing_start = datetime.now(timezone.utc)
    results: List[FileProcessingResult] = []

    try:
        # Build S3 prefix with "uploads" pattern
        # If no prefix given: use "uploads"
        # If prefix given (e.g., "abc"): use "uploads/abc/"
        if not request.prefix:
            s3_prefix = "uploads"
        else:
            # Remove trailing slash if present
            base_prefix = request.prefix.rstrip("/")
            s3_prefix = f"uploads/{base_prefix}/"

        logger.info(
            f"[BATCH START] Starting batch processing | "
            f"Date range: {request.start_date.isoformat()} to {request.end_date.isoformat()} | "
            f"Requested prefix: {request.prefix or 'None'} | "
            f"S3 prefix: {s3_prefix} | "
            f"Reprocess: {request.reprocess}"
        )

        # Step 1: List files from S3 by date range
        logger.debug("[BATCH STEP 1/3] Listing files from S3...")
        files = s3_service.list_files_by_date_range(
            start_date=request.start_date,
            end_date=request.end_date,
            prefix=s3_prefix,
        )

        total_files_found = len(files)
        logger.info(f"[BATCH STEP 1/3] Found {total_files_found} files in S3")

        if total_files_found == 0:
            processing_end = datetime.now(timezone.utc)
            duration = (processing_end - processing_start).total_seconds()
            logger.info(f"[BATCH COMPLETE] No files found in S3 | Duration: {duration:.2f}s")

            return BatchProcessingResponse(
                total_files=0,
                already_processed_count=0,
                processed_files=0,
                successful_files=0,
                failed_files=0,
                results=[],
                processing_start=processing_start,
                processing_end=processing_end,
                duration_seconds=duration,
                message="No files found in the specified date range and prefix."
            )

        # Step 2: Filter out already-processed files (unless reprocess=True)
        if not request.reprocess:
            logger.debug("[BATCH STEP 2/3] Checking which files have already been processed...")

            # Get file keys
            file_keys = [f.key for f in files]

            # Batch query DynamoDB to check which files are already processed
            certifications = dynamodb_service.batch_get_certifications(file_keys)

            # Filter out successfully completed files
            files_to_process = []
            already_processed = []

            for file_meta in files:
                cert_data = certifications.get(file_meta.key)

                # Skip if file has been successfully processed
                if cert_data and cert_data.get("status") == "completed":
                    already_processed.append(file_meta.key)
                else:
                    # Process if: no record OR failed OR pending
                    files_to_process.append(file_meta)

            files = files_to_process
            skipped_count = len(already_processed)

            logger.info(
                f"[BATCH STEP 2/3] Filtered files | "
                f"Total found: {total_files_found} | "
                f"Already processed (skipped): {skipped_count} | "
                f"To process: {len(files)}"
            )

            if skipped_count > 0:
                logger.debug(f"[BATCH STEP 2/3] Skipped files: {', '.join(already_processed[:5])}" +
                           (f" and {skipped_count - 5} more..." if skipped_count > 5 else ""))
        else:
            logger.info(
                f"[BATCH STEP 2/3] Reprocess flag enabled | "
                f"Processing all {total_files_found} files (including already-processed)"
            )

        total_files = len(files)

        if total_files == 0:
            processing_end = datetime.now(timezone.utc)
            duration = (processing_end - processing_start).total_seconds()
            logger.info(
                f"[BATCH COMPLETE] No files to process (all {total_files_found} files already processed) | "
                f"Duration: {duration:.2f}s"
            )

            return BatchProcessingResponse(
                total_files=total_files_found,
                already_processed_count=total_files_found,
                processed_files=0,
                successful_files=0,
                failed_files=0,
                results=[],
                processing_start=processing_start,
                processing_end=processing_end,
                duration_seconds=duration,
                message=f"All {total_files_found} files were already successfully processed. No new files to process."
            )

        # Step 3: Process files using batch signing API
        logger.info(
            f"[BATCH STEP 3/3] Processing {total_files} files using batch signing | "
            f"Batch size: {settings.batch_sign_size}"
        )

        # Process files in chunks using batch signing
        results = await process_files_in_batches(files)
        logger.info(f"[BATCH COMPLETE] All {total_files} files processed")

        # Calculate statistics
        successful_files = len(
            [r for r in results if r.status == ProcessingStatus.COMPLETED]
        )
        failed_files = len(
            [r for r in results if r.status == ProcessingStatus.FAILED]
        )

        # Calculate already processed count
        already_processed_count = total_files_found - total_files if not request.reprocess else 0

        processing_end = datetime.now(timezone.utc)
        duration = (processing_end - processing_start).total_seconds()
        avg_time_per_file = duration / total_files if total_files > 0 else 0

        logger.info(
            f"[BATCH COMPLETE] ✓ Batch processing finished | "
            f"Total found: {total_files_found} | "
            f"Already processed: {already_processed_count} | "
            f"Newly processed: {total_files} | "
            f"Successful: {successful_files} | "
            f"Failed: {failed_files} | "
            f"Duration: {duration:.2f}s | "
            f"Avg per file: {avg_time_per_file:.2f}s"
        )

        # Build user-friendly message
        message_parts = []
        if already_processed_count > 0:
            message_parts.append(f"{already_processed_count} files were already processed and skipped")
        if successful_files > 0:
            message_parts.append(f"{successful_files} files successfully processed")
        if failed_files > 0:
            message_parts.append(f"{failed_files} files failed")

        message = ". ".join(message_parts) + "."

        # Send SNS notification with batch completion statistics
        try:
            notification_service.send_batch_completion_notification(
                total_files=total_files,
                successful_files=successful_files,
                failed_files=failed_files,
                results=results,
                duration_seconds=duration,
                date_range={
                    "start": request.start_date.isoformat(),
                    "end": request.end_date.isoformat()
                },
                correlation_id=get_correlation_id()
            )
        except Exception as sns_error:
            # Don't fail batch if SNS notification fails
            log_exception(logger, sns_error, "[SNS] Failed to send completion notification (non-critical)")

        return BatchProcessingResponse(
            total_files=total_files_found,
            already_processed_count=already_processed_count,
            processed_files=len(results),
            successful_files=successful_files,
            failed_files=failed_files,
            results=results,
            processing_start=processing_start,
            processing_end=processing_end,
            duration_seconds=duration,
            message=message,
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


@router.get("/failed-files")
async def get_failed_files(date_partition: Optional[str] = None):
    """
    Get list of all failed file processing records.

    This endpoint allows you to review all files that failed processing,
    including error messages and failure timestamps. Use this to:
    - Review all failures after monthly batch processing
    - Investigate error patterns
    - Get file_keys for reprocessing

    Args:
        date_partition: Optional date partition filter (e.g., "2025-01")
                       If not provided, returns all failed files

    Returns:
        JSON response with list of failed files and error details

    Example Response:
        {
            "total": 3,
            "failed_files": [
                {
                    "file_key": "uploads/2025-01/invoice-123.pdf",
                    "filename": "invoice-123.pdf",
                    "error_message": "Connection timeout after 30s",
                    "error_type": "RequestException",
                    "failure_timestamp": "2025-01-31T23:45:12Z",
                    "correlation_id": "550e8400-..."
                }
            ]
        }
    """
    try:
        logger.info(f"[FAILED FILES] Querying failed files | Partition: {date_partition or 'ALL'}")

        # Query DynamoDB for failed files
        failed_records = dynamodb_service.get_failed_files(date_partition=date_partition)

        logger.info(f"[FAILED FILES] Found {len(failed_records)} failed files")

        return {
            "total": len(failed_records),
            "date_partition": date_partition,
            "failed_files": failed_records
        }

    except Exception as e:
        log_exception(logger, e, "[FAILED FILES] Failed to query failed files")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reprocess-failed", response_model=BatchProcessingResponse)
async def reprocess_failed_files(file_keys: Optional[List[str]] = None, date_partition: Optional[str] = None):
    """
    Reprocess failed files.

    This endpoint allows you to retry processing of files that previously failed.
    You can either:
    - Provide specific file_keys to reprocess
    - Provide date_partition to reprocess all failures from that month
    - Provide neither to reprocess ALL failed files (use with caution)

    Args:
        file_keys: Optional list of specific file_keys to reprocess
        date_partition: Optional date partition (e.g., "2025-01") to reprocess all failures from that month

    Returns:
        BatchProcessingResponse with reprocessing results

    Example Request (specific files):
        POST /reprocess-failed
        {
            "file_keys": ["uploads/invoice-123.pdf", "uploads/invoice-456.pdf"]
        }

    Example Request (all failures from January 2025):
        POST /reprocess-failed
        {
            "date_partition": "2025-01"
        }
    """
    processing_start = datetime.now(timezone.utc)
    results: List[FileProcessingResult] = []

    try:
        # Get list of failed files to reprocess
        if file_keys:
            # User provided specific file keys
            logger.info(f"[REPROCESS] Reprocessing {len(file_keys)} specific files")
            files_to_process = file_keys
        else:
            # Query failed files from DynamoDB
            logger.info(f"[REPROCESS] Querying failed files | Partition: {date_partition or 'ALL'}")
            failed_records = dynamodb_service.get_failed_files(date_partition=date_partition)
            files_to_process = [record["file_key"] for record in failed_records]
            logger.info(f"[REPROCESS] Found {len(files_to_process)} failed files to reprocess")

        if not files_to_process:
            logger.info("[REPROCESS] No failed files to reprocess")
            processing_end = datetime.now(timezone.utc)
            return BatchProcessingResponse(
                total_files=0,
                processed_files=0,
                successful_files=0,
                failed_files=0,
                results=[],
                processing_start=processing_start,
                processing_end=processing_end,
                duration_seconds=0.0
            )

        total_files = len(files_to_process)
        logger.info(f"[REPROCESS] Starting reprocessing of {total_files} files...")

        # Create semaphore for concurrency control
        semaphore = asyncio.Semaphore(settings.max_concurrent_requests)

        # Create async tasks for all files
        tasks = [
            process_single_file_with_semaphore(
                file_key,
                index + 1,
                total_files,
                semaphore
            )
            for index, file_key in enumerate(files_to_process)
        ]

        # Execute all tasks in parallel
        results = await asyncio.gather(*tasks)

        # Calculate statistics
        successful_files = len([r for r in results if r.status == ProcessingStatus.COMPLETED])
        failed_files = len([r for r in results if r.status == ProcessingStatus.FAILED])

        processing_end = datetime.now(timezone.utc)
        duration = (processing_end - processing_start).total_seconds()

        logger.info(
            f"[REPROCESS COMPLETE] ✓ Reprocessing finished | "
            f"Total: {total_files} | "
            f"Successful: {successful_files} | "
            f"Failed: {failed_files} | "
            f"Duration: {duration:.2f}s"
        )

        # Send SNS notification
        try:
            notification_service.send_batch_completion_notification(
                total_files=total_files,
                successful_files=successful_files,
                failed_files=failed_files,
                results=results,
                duration_seconds=duration,
                date_range={"type": "reprocess", "partition": date_partition} if date_partition else {"type": "reprocess"},
                correlation_id=get_correlation_id()
            )
        except Exception as sns_error:
            log_exception(logger, sns_error, "[SNS] Failed to send reprocess notification (non-critical)")

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
        log_exception(logger, e, f"[REPROCESS] Failed after {elapsed:.2f}s")
        raise HTTPException(status_code=500, detail=str(e))


async def process_files_in_batches(files: List) -> List[FileProcessingResult]:
    """
    Process files in batches using InfoCert batch signing API.

    This function:
    1. Downloads all files and computes hashes
    2. Chunks files into batches of size settings.batch_sign_size
    3. Sends each batch to InfoCert in a SINGLE API call
    4. Uploads P7M files and saves to DynamoDB

    Performance:
    - 100 files with batch_size=50: 2 API calls (vs 100 individual calls)
    - Reduces API overhead by 98%

    Args:
        files: List of S3 file metadata objects

    Returns:
        List of FileProcessingResult for all files
    """
    all_results = []
    total_files = len(files)

    logger.info(f"[BATCH PROCESS] Starting batch processing for {total_files} files")

    # Step 1: Download all files and compute hashes
    logger.info(f"[BATCH DOWNLOAD] Downloading and hashing {total_files} files...")
    download_start = datetime.now(timezone.utc)

    file_data_list = []  # List of (file_key, file_content, hash_info)

    for file_metadata in files:
        file_key = file_metadata.key
        try:
            # Download file
            file_content = s3_service.download_file(file_key)

            # Compute hash
            hash_info = hash_service.compute_hash(file_content, file_key)

            file_data_list.append((file_key, file_content, hash_info))

        except Exception as e:
            # Handle download/hash errors
            filename = os.path.basename(file_key)
            error_message = str(e)

            logger.error(f"[BATCH DOWNLOAD ERROR] Failed to download/hash {file_key}: {error_message}")

            # Save failed record
            try:
                dynamodb_service.save_certification(
                    file_key=file_key,
                    status="failed",
                    error_message=f"Download/hash failed: {error_message}",
                    error_type=type(e).__name__
                )
            except Exception as db_error:
                log_exception(logger, db_error, f"Failed to save error record for {file_key}")

            # Add to results as failed
            all_results.append(FileProcessingResult(
                file_key=file_key,
                filename=filename,
                status=ProcessingStatus.FAILED,
                error_message=error_message,
                processing_time=0,
                p7m_file_key=None,
                file_hash=None
            ))

    download_elapsed = (datetime.now(timezone.utc) - download_start).total_seconds()
    logger.info(
        f"[BATCH DOWNLOAD] Downloaded and hashed {len(file_data_list)}/{total_files} files | "
        f"Duration: {download_elapsed:.2f}s"
    )

    if not file_data_list:
        logger.warning("[BATCH PROCESS] No files to sign (all downloads failed)")
        return all_results

    # Step 2: Split into batches and process
    batch_size = settings.batch_sign_size
    num_batches = (len(file_data_list) + batch_size - 1) // batch_size  # Ceiling division

    logger.info(
        f"[BATCH SIGN] Splitting {len(file_data_list)} files into {num_batches} batches "
        f"of max {batch_size} files each"
    )

    for batch_num in range(num_batches):
        batch_start_idx = batch_num * batch_size
        batch_end_idx = min((batch_num + 1) * batch_size, len(file_data_list))
        batch_files = file_data_list[batch_start_idx:batch_end_idx]

        batch_start_time = datetime.now(timezone.utc)

        logger.info(
            f"[BATCH {batch_num + 1}/{num_batches}] Processing batch of {len(batch_files)} files "
            f"(files {batch_start_idx + 1}-{batch_end_idx} of {len(file_data_list)})"
        )

        # Prepare signature requests for this batch
        signature_requests = []
        for file_key, file_content, hash_info in batch_files:
            filename = os.path.basename(file_key)
            sig_request = SignatureRequest(
                file_hash=hash_info.hash_value,
                hash_algorithm=hash_info.hash_algorithm,
                filename=filename,
            )
            signature_requests.append((sig_request, file_content))

        # Call batch signing API
        logger.info(f"[BATCH {batch_num + 1}/{num_batches}] Sending {len(signature_requests)} files to InfoCert...")
        batch_results = signature_service.sign_file_hashes_batch(signature_requests)

        logger.info(f"[BATCH {batch_num + 1}/{num_batches}] Received {len(batch_results)} results from InfoCert")

        # Process results: upload P7M and save to DynamoDB
        for idx, (sig_request, sig_response, file_content, error) in enumerate(batch_results):
            file_key, _, hash_info = batch_files[idx]
            filename = os.path.basename(file_key)
            file_start = datetime.now(timezone.utc)

            if error:
                # Signature failed
                error_message = str(error)
                logger.error(f"[BATCH {batch_num + 1}/{num_batches}] Signature failed for {filename}: {error_message}")

                # Save failed record
                try:
                    dynamodb_service.save_certification(
                        file_key=file_key,
                        status="failed",
                        error_message=f"Signature failed: {error_message}",
                        error_type=type(error).__name__
                    )
                except Exception as db_error:
                    log_exception(logger, db_error, f"Failed to save error record for {file_key}")

                all_results.append(FileProcessingResult(
                    file_key=file_key,
                    filename=filename,
                    status=ProcessingStatus.FAILED,
                    error_message=error_message,
                    processing_time=0,
                    p7m_file_key=None,
                    file_hash=hash_info.hash_value
                ))
                continue

            try:
                # Upload P7M file
                original_filename = os.path.basename(file_key)
                p7m_file_key = f"signed/{original_filename}.p7m"

                s3_service.upload_file(sig_response.p7m_content, p7m_file_key)
                logger.debug(f"[BATCH {batch_num + 1}/{num_batches}] Uploaded P7M for {filename}")

                # Validate P7M
                is_valid, validation_message = validation_service.validate_p7m_structure(sig_response.p7m_content)

                # Calculate P7M file size
                p7m_file_size = len(sig_response.p7m_content)

                # Save to DynamoDB
                dynamodb_service.save_certification(
                    file_key=file_key,
                    signed_file_key=p7m_file_key,  # Fixed: was p7m_file_key
                    file_hash=hash_info.hash_value,
                    hash_algorithm=hash_info.hash_algorithm,
                    digital_signature=sig_response.signature,  # Fixed: was signature
                    vendor_timestamp=sig_response.timestamp,  # Fixed: was timestamp
                    file_size=len(file_content),
                    signed_file_size=p7m_file_size,
                    status="completed"
                )

                file_elapsed = (datetime.now(timezone.utc) - file_start).total_seconds()

                all_results.append(FileProcessingResult(
                    file_key=file_key,
                    filename=filename,
                    status=ProcessingStatus.COMPLETED,
                    error_message=None,
                    processing_time=file_elapsed,
                    p7m_file_key=p7m_file_key,
                    file_hash=hash_info.hash_value
                ))

                logger.debug(f"[BATCH {batch_num + 1}/{num_batches}] Completed {filename}")

            except Exception as e:
                # Upload/save failed
                error_message = str(e)
                logger.error(f"[BATCH {batch_num + 1}/{num_batches}] Post-signature processing failed for {filename}: {error_message}")

                # Save failed record
                try:
                    dynamodb_service.save_certification(
                        file_key=file_key,
                        status="failed",
                        error_message=f"Upload/save failed: {error_message}",
                        error_type=type(e).__name__
                    )
                except Exception as db_error:
                    log_exception(logger, db_error, f"Failed to save error record for {file_key}")

                all_results.append(FileProcessingResult(
                    file_key=file_key,
                    filename=filename,
                    status=ProcessingStatus.FAILED,
                    error_message=error_message,
                    processing_time=0,
                    p7m_file_key=None,
                    file_hash=hash_info.hash_value
                ))

        batch_elapsed = (datetime.now(timezone.utc) - batch_start_time).total_seconds()
        logger.info(
            f"[BATCH {batch_num + 1}/{num_batches}] Batch complete | "
            f"Duration: {batch_elapsed:.2f}s | "
            f"Avg per file: {batch_elapsed/len(batch_files):.2f}s"
        )

    return all_results


async def process_single_file_with_semaphore(
    file_key: str,
    file_index: int,
    total_files: int,
    semaphore: asyncio.Semaphore
) -> FileProcessingResult:
    """
    Process a single file with semaphore-based concurrency control.

    This wrapper function:
    1. Acquires semaphore before processing (blocks if limit reached)
    2. Logs progress with percentage
    3. Calls process_single_file to do actual work
    4. Catches errors and saves failed records to DynamoDB (continue-on-error)
    5. Releases semaphore when done

    Args:
        file_key: S3 file key
        file_index: File index in batch (1-based)
        total_files: Total files in batch
        semaphore: Asyncio semaphore for concurrency control

    Returns:
        FileProcessingResult with processing outcome (success or failure)

    Note:
        This function does NOT raise exceptions. Failures are captured as
        FileProcessingResult with status="failed" and stored in DynamoDB.
    """
    # Acquire semaphore (will block if max concurrent limit reached)
    async with semaphore:
        start_time = datetime.now(timezone.utc)
        logger.info(
            f"[BATCH PROGRESS] Processing file {file_index}/{total_files} ({(file_index/total_files*100):.1f}%) | "
            f"File: {file_key}"
        )

        try:
            # Process the file (may raise exception)
            result = await process_single_file(file_key)

            logger.debug(
                f"[BATCH PROGRESS] File {file_index}/{total_files} completed | "
                f"Status: {result.status.value} | "
                f"File: {file_key}"
            )

            return result

        except Exception as e:
            # Continue-on-error: Save failure to DynamoDB and continue batch
            elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
            error_message = str(e)
            error_type = type(e).__name__

            logger.error(
                f"[BATCH PROGRESS] File {file_index}/{total_files} FAILED | "
                f"File: {file_key} | "
                f"Error: {error_type}: {error_message} | "
                f"Duration: {elapsed:.2f}s"
            )

            # Save failed record to DynamoDB
            try:
                dynamodb_service.save_certification(
                    file_key=file_key,
                    status="failed",
                    error_message=error_message,
                    error_type=error_type
                )
                logger.debug(f"[BATCH PROGRESS] Failed record saved to DynamoDB for {file_key}")
            except Exception as db_error:
                log_exception(logger, db_error, f"Failed to save error record to DynamoDB for {file_key}")

            # Extract filename from file_key
            filename = os.path.basename(file_key)

            # Return failed result (don't raise exception - continue batch)
            return FileProcessingResult(
                file_key=file_key,
                filename=filename,
                status=ProcessingStatus.FAILED,
                error_message=error_message,
                processing_time=elapsed,
                p7m_file_key=None,
                file_hash=None
            )


async def process_single_file(file_key: str) -> FileProcessingResult:
    """
    Process a single file: download, hash, sign, create P7M with embedded content, upload.

    Creates a single P7M file with the ORIGINAL FILE EMBEDDED (ENVELOPED signature).

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

    # Step 3: Create signature request and send to InfoCert (pass original file content)
    filename = os.path.basename(file_key)
    sig_request = SignatureRequest(
        file_hash=hash_info.hash_value,
        hash_algorithm=hash_info.hash_algorithm,
        filename=filename,
    )

    logger.debug(f"[FILE STEP 3/5] Requesting digital signature from InfoCert...")
    sig_response = signature_service.sign_file_hash(sig_request, file_content)
    logger.info(
        f"[FILE STEP 3/5] Signature received | "
        f"Timestamp: {sig_response.timestamp.isoformat()}"
    )

    # P7M content is REQUIRED - fail if not available
    if not sig_response.p7m_content:
        error_msg = f"P7M creation failed for {file_key} - signature service did not return P7M file"
        logger.error(f"[FILE ERROR] {error_msg}")
        raise ValueError(error_msg)

    p7m_content = sig_response.p7m_content
    logger.debug(f"[FILE STEP 3/5] P7M ready | Size: {len(p7m_content)} bytes (includes embedded file)")

    # Validate P7M file with DTBS workflow
    logger.info("[VALIDATION] Validating P7M signature with DTBS workflow...")
    validation_result = validation_service.validate_signature(
        original_file_content=file_content,
        p7m_file=p7m_content
    )

    if not validation_result["valid"]:
        error_msg = f"P7M validation failed: {', '.join(validation_result['errors'])}"
        logger.error(f"[VALIDATION ERROR] {error_msg}")
        logger.error(f"[VALIDATION ERROR] Failed checks: {validation_result['checks']}")
        raise ValueError(error_msg)

    logger.info(f"[VALIDATION] ✓ P7M validation passed | Certificate: {validation_result['certificate_info'].get('subject', 'N/A')}")

    # Step 4: Upload P7M file to S3
    # Generate filename based on original file: abc.pdf -> abc.pdf.p7m
    original_filename = os.path.basename(file_key)

    p7m_file_key = f"signed/{original_filename}.p7m"

    logger.debug(f"[FILE STEP 4/5] Uploading P7M to S3: {p7m_file_key}")

    # Upload P7M file (ENVELOPED signature with original file embedded)
    s3_service.upload_file(
        file_content=p7m_content,
        destination_key=p7m_file_key,
        content_type="application/pkcs7-mime",
    )
    p7m_file_size = len(p7m_content)
    logger.info(f"[FILE STEP 4/5] P7M uploaded | {p7m_file_key} | Size: {p7m_file_size} bytes")

    # Step 5: Save certification metadata to DynamoDB
    logger.debug(f"[FILE STEP 5/5] Saving metadata to DynamoDB...")
    dynamodb_service.save_certification(
        file_key=file_key,
        file_hash=hash_info.hash_value,
        hash_algorithm=hash_info.hash_algorithm,
        digital_signature=sig_response.signature,
        vendor_timestamp=sig_response.timestamp,
        signed_file_key=p7m_file_key,  # Store P7M file reference
        file_size=hash_info.file_size,
        signed_file_size=p7m_file_size,
        status="completed",
    )
    logger.info(f"[FILE STEP 5/5] Metadata saved to DynamoDB")

    elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
    logger.info(
        f"[FILE COMPLETE] ✓ Processing complete | "
        f"File: {file_key} | "
        f"Duration: {elapsed:.2f}s | "
        f"Original: {hash_info.file_size} bytes | "
        f"P7M: {p7m_file_size} bytes (includes embedded file) | "
        f"Saved to: {p7m_file_key}"
    )

    return FileProcessingResult(
        file_key=file_key,
        filename=filename,
        status=ProcessingStatus.COMPLETED,
        file_hash=hash_info.hash_value,
        signature=sig_response.signature,
        timestamp=sig_response.timestamp,
        p7m_file_key=p7m_file_key,  # Store P7M file key
        error_message=None,
        processing_time=elapsed,
    )
