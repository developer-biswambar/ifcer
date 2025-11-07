"""Pydantic models for request/response validation."""

from pydantic import BaseModel, Field
from datetime import datetime
from typing import List, Optional
from enum import Enum


class ProcessingStatus(str, Enum):
    """Status of file processing."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class DateRangeRequest(BaseModel):
    """Request model for batch processing with date range."""

    start_date: datetime = Field(
        ..., description="Start date for S3 file filtering (upload date)"
    )
    end_date: datetime = Field(
        ..., description="End date for S3 file filtering (upload date)"
    )
    prefix: Optional[str] = Field(
        None, description="Optional S3 prefix to filter files"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "start_date": "2025-01-01T00:00:00Z",
                "end_date": "2025-01-31T23:59:59Z",
                "prefix": "documents/",
            }
        }


class SingleFileRequest(BaseModel):
    """Request model for processing a single file."""

    file_key: str = Field(
        ..., description="S3 object key of the file to recertify"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "file_key": "documents/2025/invoice_001.pdf",
            }
        }


class S3FileMetadata(BaseModel):
    """Metadata for an S3 file."""

    key: str = Field(..., description="S3 object key")
    size: int = Field(..., description="File size in bytes")
    last_modified: datetime = Field(..., description="Last modified timestamp")
    etag: str = Field(..., description="S3 ETag")


class FileHashInfo(BaseModel):
    """File hash information."""

    file_key: str = Field(..., description="S3 file key")
    hash_value: str = Field(..., description="Computed hash of the file")
    hash_algorithm: str = Field(..., description="Hash algorithm used")
    file_size: int = Field(..., description="File size in bytes")


class SignatureRequest(BaseModel):
    """Request to vendor API for digital signature."""

    file_hash: str = Field(..., description="Hash of the file to be signed")
    hash_algorithm: str = Field(..., description="Hash algorithm used")
    filename: str = Field(..., description="Original filename")


class SignatureResponse(BaseModel):
    """Response from vendor API after signing."""

    signature: str = Field(..., description="Digital signature")
    timestamp: datetime = Field(..., description="Timestamp of signature")
    p7m_content: Optional[bytes] = Field(
        None, description="P7M file content (base64 encoded)"
    )


class FileProcessingResult(BaseModel):
    """Result of processing a single file."""

    file_key: str = Field(..., description="S3 file key")
    status: ProcessingStatus = Field(..., description="Processing status")
    file_hash: Optional[str] = Field(None, description="File hash")
    signature: Optional[str] = Field(None, description="Digital signature")
    timestamp: Optional[datetime] = Field(None, description="Timestamp")
    p7m_file_key: Optional[str] = Field(None, description="S3 key for P7M file")
    error_message: Optional[str] = Field(None, description="Error message if failed")


class BatchProcessingResponse(BaseModel):
    """Response for batch processing request."""

    total_files: int = Field(..., description="Total number of files found")
    processed_files: int = Field(..., description="Number of files processed")
    successful_files: int = Field(..., description="Number of successful files")
    failed_files: int = Field(..., description="Number of failed files")
    results: List[FileProcessingResult] = Field(..., description="Processing results")
    processing_start: datetime = Field(..., description="Processing start time")
    processing_end: datetime = Field(..., description="Processing end time")
    duration_seconds: float = Field(..., description="Total processing duration")


class HealthCheckResponse(BaseModel):
    """Health check response."""

    status: str = Field(..., description="Service status")
    timestamp: datetime = Field(..., description="Current timestamp")
    version: str = Field(..., description="Service version")


class FileDetailsRequest(BaseModel):
    """Request model for getting file details."""

    filename: str = Field(
        ..., description="Filename to search for (can be just the filename or full S3 key)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "filename": "invoice_001.pdf",
            }
        }


class FileSigningInfo(BaseModel):
    """Information about file signing status."""

    original_file_key: str = Field(..., description="Original file S3 key")
    original_file_size: int = Field(..., description="Original file size in bytes")
    original_upload_date: datetime = Field(..., description="Original file upload date")
    is_signed: bool = Field(..., description="Whether file has been signed")
    signed_file_key: Optional[str] = Field(None, description="Signed P7M file S3 key")
    signed_file_size: Optional[int] = Field(None, description="Signed file size in bytes")
    signing_timestamp: Optional[datetime] = Field(None, description="When the file was signed")
    file_hash: Optional[str] = Field(None, description="File hash")
    signature: Optional[str] = Field(None, description="Digital signature")


class FileDetailsResponse(BaseModel):
    """Response with file details and signing information."""

    found: bool = Field(..., description="Whether the file was found")
    files: List[FileSigningInfo] = Field(..., description="List of matching files with signing info")
    total_matches: int = Field(..., description="Total number of matches found")


class FileListRequest(BaseModel):
    """Request model for getting file list with signing info."""

    start_date: datetime = Field(
        ..., description="Start date for filtering files (upload date)"
    )
    end_date: datetime = Field(
        ..., description="End date for filtering files (upload date)"
    )
    prefix: Optional[str] = Field(
        None, description="Optional S3 prefix to filter files"
    )
    signed_only: bool = Field(
        False, description="Only return files that have been signed"
    )
    page: int = Field(
        1, ge=1, description="Page number (starting from 1)"
    )
    page_size: int = Field(
        50, ge=1, le=1000, description="Number of items per page (max 1000)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "start_date": "2025-01-01T00:00:00Z",
                "end_date": "2025-01-31T23:59:59Z",
                "prefix": "documents/",
                "signed_only": False,
                "page": 1,
                "page_size": 50,
            }
        }


class FileListResponse(BaseModel):
    """Response with list of files and their signing information."""

    total_files: int = Field(..., description="Total number of files matching criteria")
    signed_files: int = Field(..., description="Total number of signed files")
    unsigned_files: int = Field(..., description="Total number of unsigned files")
    page: int = Field(..., description="Current page number")
    page_size: int = Field(..., description="Number of items per page")
    total_pages: int = Field(..., description="Total number of pages")
    has_next: bool = Field(..., description="Whether there is a next page")
    has_previous: bool = Field(..., description="Whether there is a previous page")
    files: List[FileSigningInfo] = Field(..., description="List of files with signing info for current page")
