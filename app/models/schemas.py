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
