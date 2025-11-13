"""File query endpoints for certification status."""

from fastapi import APIRouter, HTTPException
from typing import List
import os

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
