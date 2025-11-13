"""File query and download endpoints for certification status."""

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from typing import List, Optional
import os
import io

from app.models.schemas import (
    FileDetailsRequest,
    FileDetailsResponse,
    FileListRequest,
    FileListResponse,
    FileSigningInfo,
)
from app.services.s3_service import S3Service
from app.services.dynamodb_service import DynamoDBService
from app.utils.logger import setup_logger, log_exception
from datetime import datetime

logger = setup_logger(__name__)

# Initialize services
s3_service = S3Service()
dynamodb_service = DynamoDBService()

router = APIRouter()


@router.post("/file-details", response_model=FileDetailsResponse)
async def get_file_details(request: FileDetailsRequest):
    """
    Get file details and signing status by filename.

    This endpoint searches for files matching the given filename and returns
    information about whether they have been signed, including:
    - Original file location and metadata
    - Signed file location (if exists)
    - Signing timestamp
    - File hash and signature details

    Args:
        request: FileDetailsRequest with filename to search

    Returns:
        FileDetailsResponse with list of matching files and their signing info
    """
    try:
        logger.info(f"Getting file details for: {request.filename}")

        # Search for files matching the filename
        matching_files = s3_service.search_files_by_name(request.filename)

        if not matching_files:
            logger.info(f"No files found matching: {request.filename}")
            return FileDetailsResponse(
                found=False,
                files=[],
                total_matches=0,
            )

        file_info_list: List[FileSigningInfo] = []

        for file_meta in matching_files:
            # Skip if this is already a signed file (in signed/ folder)
            if file_meta.key.startswith("signed/"):
                continue

            # Get certification metadata from DynamoDB
            cert_data = dynamodb_service.get_certification(file_meta.key)

            if cert_data:
                # File has been certified - use DynamoDB data
                file_info = FileSigningInfo(
                    original_file_key=file_meta.key,
                    original_file_size=file_meta.size,
                    original_upload_date=file_meta.last_modified,
                    is_signed=cert_data.get("status") == "completed",
                    signed_file_key=cert_data.get("signed_file_key"),
                    signed_file_size=cert_data.get("signed_file_size"),
                    signing_timestamp=datetime.fromisoformat(cert_data["vendor_timestamp"]) if cert_data.get("vendor_timestamp") else None,
                    processing_timestamp=datetime.fromisoformat(cert_data["processing_timestamp"]) if cert_data.get("processing_timestamp") else None,
                    file_hash=cert_data.get("file_hash"),
                    hash_algorithm=cert_data.get("hash_algorithm"),
                    signature=cert_data.get("digital_signature"),
                    status=cert_data.get("status"),
                )
            else:
                # No certification record - file not yet processed
                file_info = FileSigningInfo(
                    original_file_key=file_meta.key,
                    original_file_size=file_meta.size,
                    original_upload_date=file_meta.last_modified,
                    is_signed=False,
                    signed_file_key=None,
                    signed_file_size=None,
                    signing_timestamp=None,
                    processing_timestamp=None,
                    file_hash=None,
                    hash_algorithm=None,
                    signature=None,
                    status=None,
                )

            file_info_list.append(file_info)

        logger.info(f"Found {len(file_info_list)} matching files")

        return FileDetailsResponse(
            found=len(file_info_list) > 0,
            files=file_info_list,
            total_matches=len(file_info_list),
        )

    except Exception as e:
        log_exception(logger, e, f"Failed to get file details for: {request.filename}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/files-list", response_model=FileListResponse)
async def get_files_list(request: FileListRequest):
    """
    Get list of files with signing information by date range.

    This endpoint returns files uploaded in the specified date range along with
    their signing status, including:
    - Original file metadata
    - Whether file has been signed
    - Signed file location and metadata
    - Signing timestamp
    - Pagination support for large result sets

    Useful for:
    - Auditing which files have been certified
    - Finding files that need recertification
    - Reporting on certification status

    Args:
        request: FileListRequest with date range, filters, and pagination params

    Returns:
        FileListResponse with paginated files and their signing information
    """
    try:
        logger.info(
            f"Getting files list from {request.start_date} to {request.end_date} "
            f"(page {request.page}, page_size {request.page_size})"
        )

        # Get all files in the date range
        files = s3_service.list_files_by_date_range(
            start_date=request.start_date,
            end_date=request.end_date,
            prefix=request.prefix,
        )

        # Filter out files in signed/ folder
        original_files = [f for f in files if not f.key.startswith("signed/")]

        # Batch get certification data from DynamoDB for better performance
        file_keys = [f.key for f in original_files]
        certifications = dynamodb_service.batch_get_certifications(file_keys)

        file_info_list: List[FileSigningInfo] = []
        signed_count = 0
        unsigned_count = 0

        for file_meta in original_files:
            # Get certification data if available
            cert_data = certifications.get(file_meta.key)

            if cert_data:
                # File has certification data
                is_signed = cert_data.get("status") == "completed"

                # If signed_only filter is enabled, skip non-completed files
                if request.signed_only and not is_signed:
                    continue

                if is_signed:
                    signed_count += 1
                else:
                    unsigned_count += 1

                file_info = FileSigningInfo(
                    original_file_key=file_meta.key,
                    original_file_size=file_meta.size,
                    original_upload_date=file_meta.last_modified,
                    is_signed=is_signed,
                    signed_file_key=cert_data.get("signed_file_key"),
                    signed_file_size=cert_data.get("signed_file_size"),
                    signing_timestamp=datetime.fromisoformat(cert_data["vendor_timestamp"]) if cert_data.get("vendor_timestamp") else None,
                    processing_timestamp=datetime.fromisoformat(cert_data["processing_timestamp"]) if cert_data.get("processing_timestamp") else None,
                    file_hash=cert_data.get("file_hash"),
                    hash_algorithm=cert_data.get("hash_algorithm"),
                    signature=cert_data.get("digital_signature"),
                    status=cert_data.get("status"),
                )
            else:
                # No certification record - file not yet processed
                # If signed_only filter is enabled, skip unsigned files
                if request.signed_only:
                    continue

                unsigned_count += 1

                file_info = FileSigningInfo(
                    original_file_key=file_meta.key,
                    original_file_size=file_meta.size,
                    original_upload_date=file_meta.last_modified,
                    is_signed=False,
                    signed_file_key=None,
                    signed_file_size=None,
                    signing_timestamp=None,
                    processing_timestamp=None,
                    file_hash=None,
                    hash_algorithm=None,
                    signature=None,
                    status=None,
                )

            file_info_list.append(file_info)

        # Calculate pagination
        total_files = len(file_info_list)
        total_pages = (total_files + request.page_size - 1) // request.page_size  # Ceiling division

        # Validate page number
        if request.page > total_pages and total_files > 0:
            raise HTTPException(
                status_code=400,
                detail=f"Page {request.page} exceeds total pages {total_pages}"
            )

        # Calculate slice indices for pagination
        start_idx = (request.page - 1) * request.page_size
        end_idx = start_idx + request.page_size

        # Slice the list to get current page
        paginated_files = file_info_list[start_idx:end_idx]

        logger.info(
            f"Found {total_files} files total: {signed_count} signed, {unsigned_count} unsigned. "
            f"Returning page {request.page} of {total_pages} ({len(paginated_files)} items)"
        )

        return FileListResponse(
            total_files=total_files,
            signed_files=signed_count,
            unsigned_files=unsigned_count,
            page=request.page,
            page_size=request.page_size,
            total_pages=total_pages if total_files > 0 else 0,
            has_next=request.page < total_pages,
            has_previous=request.page > 1,
            files=paginated_files,
        )

    except HTTPException:
        raise
    except Exception as e:
        log_exception(logger, e, "Failed to get files list")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/download/original")
async def download_original_file(
    file_key: str = Query(..., description="Original file S3 key (e.g., uploads/document.txt)")
):
    """
    Download the original file from S3.

    This endpoint allows you to download the original file using its S3 key.
    The file is streamed directly from S3 to the client.

    Args:
        file_key: S3 key of the original file (e.g., "uploads/document.txt")

    Returns:
        StreamingResponse: File content with appropriate headers for download

    Raises:
        HTTPException: If file not found or download fails
    """
    try:
        logger.info(f"[DOWNLOAD ORIGINAL] Downloading file: {file_key}")

        # Check if file exists
        if not s3_service.file_exists(file_key):
            logger.warning(f"[DOWNLOAD ORIGINAL] File not found: {file_key}")
            raise HTTPException(status_code=404, detail=f"File not found: {file_key}")

        # Download file from S3
        file_content = s3_service.download_file(file_key)

        # Extract filename from key
        filename = os.path.basename(file_key)

        logger.info(f"[DOWNLOAD ORIGINAL] ✓ Downloaded file: {file_key} ({len(file_content)} bytes)")

        # Return file as streaming response
        return StreamingResponse(
            io.BytesIO(file_content),
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        log_exception(logger, e, f"Failed to download original file: {file_key}")
        raise HTTPException(status_code=500, detail=f"Failed to download file: {str(e)}")


@router.get("/download/signed")
async def download_signed_file(
    original_file_key: Optional[str] = Query(None, description="Original file S3 key"),
    signed_file_key: Optional[str] = Query(None, description="Signed file S3 key")
):
    """
    Download the signed file (manifest.json or manifest.p7s) from S3.

    You can provide either:
    - original_file_key: The key of the original file (will look up signed file in DynamoDB)
    - signed_file_key: The direct key of the signed file in S3

    The signed files are typically stored in the "signed/" folder.

    Args:
        original_file_key: Original file S3 key (e.g., "uploads/document.txt")
        signed_file_key: Signed file S3 key (e.g., "signed/document.json" or "signed/document.p7s")

    Returns:
        StreamingResponse: Signed file content with appropriate headers

    Raises:
        HTTPException: If file not found, not signed, or download fails
    """
    try:
        # Validate that at least one key is provided
        if not original_file_key and not signed_file_key:
            raise HTTPException(
                status_code=400,
                detail="Must provide either 'original_file_key' or 'signed_file_key'"
            )

        # If original_file_key is provided, look up signed file in DynamoDB
        if original_file_key:
            logger.info(f"[DOWNLOAD SIGNED] Looking up signed file for: {original_file_key}")

            cert_data = dynamodb_service.get_certification(original_file_key)

            if not cert_data:
                logger.warning(f"[DOWNLOAD SIGNED] No certification record found: {original_file_key}")
                raise HTTPException(
                    status_code=404,
                    detail=f"No certification record found for: {original_file_key}"
                )

            if cert_data.get("status") != "completed":
                status = cert_data.get("status", "unknown")
                logger.warning(f"[DOWNLOAD SIGNED] File not signed (status: {status}): {original_file_key}")
                raise HTTPException(
                    status_code=400,
                    detail=f"File has not been successfully signed. Status: {status}"
                )

            signed_file_key = cert_data.get("signed_file_key")

            if not signed_file_key:
                logger.error(f"[DOWNLOAD SIGNED] Certification record missing signed_file_key: {original_file_key}")
                raise HTTPException(
                    status_code=500,
                    detail="Certification record is missing signed file key"
                )

        logger.info(f"[DOWNLOAD SIGNED] Downloading signed file: {signed_file_key}")

        # Check if signed file exists
        if not s3_service.file_exists(signed_file_key):
            logger.warning(f"[DOWNLOAD SIGNED] Signed file not found in S3: {signed_file_key}")
            raise HTTPException(
                status_code=404,
                detail=f"Signed file not found in S3: {signed_file_key}"
            )

        # Download signed file from S3
        file_content = s3_service.download_file(signed_file_key)

        # Extract filename from key
        filename = os.path.basename(signed_file_key)

        # Determine media type based on file extension
        if filename.endswith(".json"):
            media_type = "application/json"
        elif filename.endswith(".p7s") or filename.endswith(".p7m"):
            media_type = "application/pkcs7-signature"
        else:
            media_type = "application/octet-stream"

        logger.info(f"[DOWNLOAD SIGNED] ✓ Downloaded signed file: {signed_file_key} ({len(file_content)} bytes)")

        # Return file as streaming response
        return StreamingResponse(
            io.BytesIO(file_content),
            media_type=media_type,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        log_exception(logger, e, f"Failed to download signed file")
        raise HTTPException(status_code=500, detail=f"Failed to download signed file: {str(e)}")
