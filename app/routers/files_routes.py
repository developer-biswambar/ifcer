"""File query, upload, download and management endpoints."""

from fastapi import APIRouter, HTTPException, Query, UploadFile, File, Form
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


@router.post("/upload")
async def upload_file(
    file: UploadFile = File(..., description="File to upload"),
    prefix: Optional[str] = Form(None, description="Optional subfolder under uploads/ (e.g., 'invoices', 'contracts')")
):
    """
    Upload a single file to S3 for certification.

    This endpoint uploads a file to the S3 bucket in the "uploads/" folder.
    After upload, you can process the file using the /process endpoint.

    **File Organization:**
    - Without prefix: uploads to `uploads/{filename}`
    - With prefix: uploads to `uploads/{prefix}/{filename}`
    - This allows organizing files by type, client, or date

    **Workflow:**
    1. Upload file(s) using this endpoint
    2. Call /process endpoint to certify and sign uploaded files
    3. Download signed P7M files using /download/signed endpoint

    Args:
        file: File to upload (multipart/form-data)
        prefix: Optional subfolder (e.g., "2025-01" or "client-abc")

    Returns:
        Upload confirmation with S3 file key and metadata

    Example:
        ```bash
        # Upload without prefix
        curl -X POST "http://localhost:8000/upload" \\
             -F "file=@invoice.pdf"

        # Upload with prefix
        curl -X POST "http://localhost:8000/upload" \\
             -F "file=@invoice.pdf" \\
             -F "prefix=invoices/2025-01"
        ```
    """
    try:
        # Validate filename
        if not file.filename:
            raise HTTPException(status_code=400, detail="Filename is required")

        # Build S3 key
        if prefix:
            # Remove leading/trailing slashes from prefix
            clean_prefix = prefix.strip("/")
            s3_key = f"uploads/{clean_prefix}/{file.filename}"
        else:
            s3_key = f"uploads/{file.filename}"

        logger.info(f"[UPLOAD] Starting file upload | Filename: {file.filename} | S3 key: {s3_key}")

        # Read file content
        file_content = await file.read()
        file_size = len(file_content)

        if file_size == 0:
            raise HTTPException(status_code=400, detail="File is empty")

        logger.debug(f"[UPLOAD] File read successfully | Size: {file_size:,} bytes")

        # Determine content type
        content_type = file.content_type or "application/octet-stream"

        # Upload to S3
        upload_start = datetime.now(timezone.utc)
        s3_service.upload_file(
            file_content=file_content,
            destination_key=s3_key,
            content_type=content_type
        )
        upload_elapsed = (datetime.now(timezone.utc) - upload_start).total_seconds()

        logger.info(
            f"[UPLOAD] ✓ File uploaded successfully | "
            f"File: {file.filename} | "
            f"S3 key: {s3_key} | "
            f"Size: {file_size:,} bytes ({file_size / (1024*1024):.2f} MB) | "
            f"Duration: {upload_elapsed:.2f}s"
        )

        return {
            "message": "File uploaded successfully",
            "file_key": s3_key,
            "filename": file.filename,
            "size_bytes": file_size,
            "size_mb": round(file_size / (1024 * 1024), 2),
            "content_type": content_type,
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
            "next_steps": {
                "description": "Use the /process endpoint to certify and sign this file",
                "process_endpoint": "/process",
                "example_request": {
                    "start_date": datetime.now(timezone.utc).isoformat(),
                    "end_date": datetime.now(timezone.utc).isoformat(),
                    "prefix": prefix
                }
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        log_exception(logger, e, f"Failed to upload file: {file.filename if file else 'unknown'}")
        raise HTTPException(status_code=500, detail=f"Failed to upload file: {str(e)}")


@router.post("/upload-multiple")
async def upload_multiple_files(
    files: List[UploadFile] = File(..., description="Multiple files to upload"),
    prefix: Optional[str] = Form(None, description="Optional subfolder under uploads/")
):
    """
    Upload multiple files to S3 for certification in batch.

    This endpoint uploads multiple files to the S3 bucket in the "uploads/" folder.
    All files are uploaded to the same prefix (subfolder).

    **Benefits:**
    - Upload many files at once
    - All files go to the same location for easy batch processing
    - Reduces number of API calls compared to single uploads

    **Limits:**
    - Maximum file size: depends on your FastAPI configuration (default: unlimited)
    - Maximum number of files: depends on your client configuration
    - Total request size: depends on your server configuration

    Args:
        files: List of files to upload (multipart/form-data)
        prefix: Optional subfolder for all files (e.g., "2025-01" or "client-abc")

    Returns:
        Upload summary with details for each file

    Example:
        ```bash
        curl -X POST "http://localhost:8000/upload-multiple" \\
             -F "files=@invoice1.pdf" \\
             -F "files=@invoice2.pdf" \\
             -F "files=@contract.docx" \\
             -F "prefix=invoices/2025-01"
        ```
    """
    try:
        batch_start = datetime.now(timezone.utc)

        if not files:
            raise HTTPException(status_code=400, detail="No files provided")

        logger.info(f"[UPLOAD BATCH] Starting batch upload | File count: {len(files)} | Prefix: {prefix or 'None'}")

        upload_results = []
        total_size = 0
        successful_uploads = 0
        failed_uploads = 0

        for file in files:
            try:
                # Validate filename
                if not file.filename:
                    logger.warning("[UPLOAD BATCH] Skipping file with no filename")
                    upload_results.append({
                        "filename": "unknown",
                        "status": "failed",
                        "error": "Filename is required"
                    })
                    failed_uploads += 1
                    continue

                # Build S3 key
                if prefix:
                    clean_prefix = prefix.strip("/")
                    s3_key = f"uploads/{clean_prefix}/{file.filename}"
                else:
                    s3_key = f"uploads/{file.filename}"

                # Read file content
                file_content = await file.read()
                file_size = len(file_content)

                if file_size == 0:
                    logger.warning(f"[UPLOAD BATCH] Skipping empty file: {file.filename}")
                    upload_results.append({
                        "filename": file.filename,
                        "status": "failed",
                        "error": "File is empty"
                    })
                    failed_uploads += 1
                    continue

                # Determine content type
                content_type = file.content_type or "application/octet-stream"

                # Upload to S3
                s3_service.upload_file(
                    file_content=file_content,
                    destination_key=s3_key,
                    content_type=content_type
                )

                total_size += file_size
                successful_uploads += 1

                upload_results.append({
                    "filename": file.filename,
                    "file_key": s3_key,
                    "size_bytes": file_size,
                    "size_mb": round(file_size / (1024 * 1024), 2),
                    "content_type": content_type,
                    "status": "success"
                })

                logger.debug(f"[UPLOAD BATCH] ✓ Uploaded: {file.filename} ({file_size:,} bytes)")

            except Exception as e:
                failed_uploads += 1
                error_msg = str(e)
                logger.error(f"[UPLOAD BATCH] ✗ Failed to upload {file.filename}: {error_msg}")

                upload_results.append({
                    "filename": file.filename,
                    "status": "failed",
                    "error": error_msg
                })

        batch_elapsed = (datetime.now(timezone.utc) - batch_start).total_seconds()

        logger.info(
            f"[UPLOAD BATCH] ✓ Batch upload complete | "
            f"Total: {len(files)} | "
            f"Successful: {successful_uploads} | "
            f"Failed: {failed_uploads} | "
            f"Total size: {total_size:,} bytes ({total_size / (1024*1024):.2f} MB) | "
            f"Duration: {batch_elapsed:.2f}s"
        )

        return {
            "message": "Batch upload complete",
            "summary": {
                "total_files": len(files),
                "successful": successful_uploads,
                "failed": failed_uploads,
                "total_size_bytes": total_size,
                "total_size_mb": round(total_size / (1024 * 1024), 2),
                "duration_seconds": round(batch_elapsed, 2)
            },
            "files": upload_results,
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
            "next_steps": {
                "description": "Use the /process endpoint to certify and sign these files",
                "process_endpoint": "/process",
                "example_request": {
                    "start_date": datetime.now(timezone.utc).isoformat(),
                    "end_date": datetime.now(timezone.utc).isoformat(),
                    "prefix": prefix
                }
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        log_exception(logger, e, "Failed to process batch upload")
        raise HTTPException(status_code=500, detail=f"Failed to process batch upload: {str(e)}")


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
            # Skip if this is in signed/ or certs/ folder
            if file_meta.key.startswith("signed/") or file_meta.key.startswith("certs/"):
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

        # Sort by last modified date (newest first)
        file_info_list.sort(key=lambda x: x.original_upload_date, reverse=True)

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

        # Filter out files in signed/ and certs/ folders
        original_files = [
            f for f in files
            if not f.key.startswith("signed/") and not f.key.startswith("certs/")
        ]

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

        # Sort by last modified date (newest first)
        file_info_list.sort(key=lambda x: x.original_upload_date, reverse=True)

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
    Download the P7M signed file from S3.

    You can provide either:
    - original_file_key: The key of the original file (will look up P7M file in DynamoDB)
    - signed_file_key: The direct key of the P7M file in S3

    The P7M files are stored in the "signed/" folder with .p7m extension.

    Args:
        original_file_key: Original file S3 key (e.g., "uploads/document.pdf")
        signed_file_key: P7M file S3 key (e.g., "signed/document.pdf.p7m")

    Returns:
        StreamingResponse: P7M file content with appropriate headers

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
        elif filename.endswith(".p7m"):
            media_type = "application/pkcs7-mime"  # ENVELOPED signature with embedded content
        elif filename.endswith(".p7s"):
            media_type = "application/pkcs7-signature"  # DETACHED signature
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


@router.delete("/original")
async def delete_original_file(
    file_key: str = Query(..., description="S3 key of the original file to delete")
):
    """
    Delete an original file from S3.

    This endpoint deletes the original file from the S3 bucket.
    Note: This does NOT delete the signed P7M file or the DynamoDB record.

    Use cases:
    - Clean up original files after successful signing
    - Remove files that are no longer needed
    - Free up S3 storage space

    Args:
        file_key: S3 object key of the original file (e.g., "uploads/abc/invoice.pdf")

    Returns:
        Success message with deleted file key

    Raises:
        HTTPException: If file deletion fails

    Example:
        DELETE /original?file_key=uploads/abc/invoice.pdf
    """
    try:
        logger.info(f"[DELETE ORIGINAL] Deleting original file: {file_key}")

        # Delete file from S3
        s3_service.delete_file(file_key)

        logger.info(f"[DELETE ORIGINAL] ✓ Original file deleted successfully: {file_key}")

        return {
            "message": "Original file deleted successfully",
            "file_key": file_key,
            "deleted_at": datetime.now().isoformat()
        }

    except Exception as e:
        log_exception(logger, e, f"[DELETE ORIGINAL] Failed to delete original file: {file_key}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete original file: {str(e)}"
        )


@router.delete("/signed")
async def delete_signed_file(
    file_key: str = Query(..., description="S3 key of the signed P7M file to delete")
):
    """
    Delete a signed P7M file from S3.

    This endpoint deletes the signed P7M file from the S3 bucket.
    Note: This does NOT delete the original file or the DynamoDB record.

    Use cases:
    - Remove signed files that need to be re-signed
    - Clean up signed files after they've been downloaded/archived
    - Free up S3 storage space

    Args:
        file_key: S3 object key of the signed file (e.g., "signed/invoice.pdf.p7m")

    Returns:
        Success message with deleted file key

    Raises:
        HTTPException: If file deletion fails

    Example:
        DELETE /signed?file_key=signed/invoice.pdf.p7m
    """
    try:
        logger.info(f"[DELETE SIGNED] Deleting signed file: {file_key}")

        # Delete file from S3
        s3_service.delete_file(file_key)

        logger.info(f"[DELETE SIGNED] ✓ Signed file deleted successfully: {file_key}")

        return {
            "message": "Signed file deleted successfully",
            "file_key": file_key,
            "deleted_at": datetime.now().isoformat()
        }

    except Exception as e:
        log_exception(logger, e, f"[DELETE SIGNED] Failed to delete signed file: {file_key}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete signed file: {str(e)}"
        )
