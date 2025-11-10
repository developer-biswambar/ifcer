"""S3 service for file operations."""

import boto3
from botocore.exceptions import ClientError, BotoCoreError
from datetime import datetime, timezone
from typing import List, Optional, BinaryIO
from app.config import settings
from app.models.schemas import S3FileMetadata
from app.utils.logger import setup_logger, log_exception

logger = setup_logger(__name__)


class S3Service:
    """Service for interacting with AWS S3."""

    def __init__(self):
        """Initialize S3 client with configuration."""
        try:
            # Prepare boto3 client configuration
            client_config = {
                "region_name": settings.aws_region
            }

            # Add endpoint_url for moto/LocalStack testing
            if settings.aws_endpoint_url:
                client_config["endpoint_url"] = settings.aws_endpoint_url
                logger.info(f"Using custom AWS endpoint: {settings.aws_endpoint_url}")

            # Add explicit credentials if provided (for moto/LocalStack)
            if settings.aws_access_key_id and settings.aws_secret_access_key:
                client_config["aws_access_key_id"] = settings.aws_access_key_id
                client_config["aws_secret_access_key"] = settings.aws_secret_access_key
                logger.debug("Using explicit AWS credentials from configuration")

            # Create S3 client - uses IAM role credentials automatically in ECS
            # unless explicit credentials are provided
            self.s3_client = boto3.client("s3", **client_config)
            self.bucket_name = settings.s3_bucket_name

            endpoint_info = f" | Endpoint: {settings.aws_endpoint_url}" if settings.aws_endpoint_url else ""
            logger.info(f"S3 client initialized for bucket: {self.bucket_name} in region: {settings.aws_region}{endpoint_info}")

        except Exception as e:
            log_exception(logger, e, "Failed to initialize S3 client")
            raise

    def list_files_by_date_range(
        self,
        start_date: datetime,
        end_date: datetime,
        prefix: Optional[str] = None,
    ) -> List[S3FileMetadata]:
        """
        List all files in S3 bucket filtered by upload date range.

        Args:
            start_date: Start date for filtering (inclusive)
            end_date: End date for filtering (inclusive)
            prefix: Optional prefix to filter files

        Returns:
            List of S3FileMetadata objects

        Raises:
            ClientError: If S3 operation fails
        """
        start_time = datetime.now(timezone.utc)
        try:
            logger.info(
                f"[S3 LIST] Starting file listing | "
                f"Bucket: {self.bucket_name} | "
                f"Date range: {start_date.isoformat()} to {end_date.isoformat()} | "
                f"Prefix: {prefix or 'None'}"
            )

            files = []
            total_objects_scanned = 0
            page_count = 0
            paginator = self.s3_client.get_paginator("list_objects_v2")

            pagination_config = {
                "Bucket": self.bucket_name,
            }

            if prefix:
                pagination_config["Prefix"] = prefix

            page_iterator = paginator.paginate(**pagination_config)

            for page in page_iterator:
                page_count += 1
                if "Contents" not in page:
                    logger.debug(f"[S3 LIST] Page {page_count} contains no objects")
                    continue

                page_objects = len(page["Contents"])
                total_objects_scanned += page_objects
                logger.debug(f"[S3 LIST] Processing page {page_count} | Objects: {page_objects}")

                for obj in page["Contents"]:
                    last_modified = obj["LastModified"]

                    # Filter by date range (comparing datetime objects)
                    if start_date <= last_modified <= end_date:
                        file_metadata = S3FileMetadata(
                            key=obj["Key"],
                            size=obj["Size"],
                            last_modified=last_modified,
                            etag=obj["ETag"].strip('"'),
                        )
                        files.append(file_metadata)

            elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
            total_size = sum(f.size for f in files)
            logger.info(
                f"[S3 LIST] ✓ File listing complete | "
                f"Found: {len(files)} files | "
                f"Scanned: {total_objects_scanned} objects | "
                f"Pages: {page_count} | "
                f"Total size: {total_size:,} bytes | "
                f"Duration: {elapsed:.2f}s"
            )
            return files

        except ClientError as e:
            elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
            log_exception(logger, e, f"[S3 LIST] Failed to list S3 files after {elapsed:.2f}s")
            raise
        except Exception as e:
            elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
            log_exception(logger, e, f"[S3 LIST] Unexpected error listing S3 files after {elapsed:.2f}s")
            raise

    def download_file(self, file_key: str) -> bytes:
        """
        Download file content from S3.

        Args:
            file_key: S3 object key

        Returns:
            File content as bytes

        Raises:
            ClientError: If S3 operation fails
        """
        start_time = datetime.now(timezone.utc)
        try:
            logger.debug(f"[S3 DOWNLOAD] Starting download | File: {file_key}")

            response = self.s3_client.get_object(
                Bucket=self.bucket_name, Key=file_key
            )

            file_content = response["Body"].read()
            elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()

            # Calculate download speed
            size_mb = len(file_content) / (1024 * 1024)
            speed_mbps = (size_mb / elapsed) if elapsed > 0 else 0

            logger.info(
                f"[S3 DOWNLOAD] ✓ Download complete | "
                f"File: {file_key} | "
                f"Size: {len(file_content):,} bytes ({size_mb:.2f} MB) | "
                f"Duration: {elapsed:.2f}s | "
                f"Speed: {speed_mbps:.2f} MB/s"
            )

            return file_content

        except ClientError as e:
            elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
            log_exception(logger, e, f"[S3 DOWNLOAD] Failed to download file: {file_key} after {elapsed:.2f}s")
            raise
        except Exception as e:
            elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
            log_exception(logger, e, f"[S3 DOWNLOAD] Unexpected error downloading file: {file_key} after {elapsed:.2f}s")
            raise

    def upload_file(
        self, file_content: bytes, destination_key: str, content_type: str = "application/pkcs7-mime"
    ) -> bool:
        """
        Upload file to S3.

        Args:
            file_content: File content as bytes
            destination_key: S3 destination key
            content_type: MIME type of the file

        Returns:
            True if successful

        Raises:
            ClientError: If S3 operation fails
        """
        start_time = datetime.now(timezone.utc)
        try:
            logger.debug(
                f"[S3 UPLOAD] Starting upload | "
                f"Destination: {destination_key} | "
                f"Size: {len(file_content):,} bytes | "
                f"Content-Type: {content_type}"
            )

            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=destination_key,
                Body=file_content,
                ContentType=content_type,
            )

            elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()

            # Calculate upload speed
            size_mb = len(file_content) / (1024 * 1024)
            speed_mbps = (size_mb / elapsed) if elapsed > 0 else 0

            logger.info(
                f"[S3 UPLOAD] ✓ Upload complete | "
                f"Destination: {destination_key} | "
                f"Size: {len(file_content):,} bytes ({size_mb:.2f} MB) | "
                f"Duration: {elapsed:.2f}s | "
                f"Speed: {speed_mbps:.2f} MB/s"
            )
            return True

        except ClientError as e:
            elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
            log_exception(logger, e, f"[S3 UPLOAD] Failed to upload file: {destination_key} after {elapsed:.2f}s")
            raise
        except Exception as e:
            elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
            log_exception(logger, e, f"[S3 UPLOAD] Unexpected error uploading file: {destination_key} after {elapsed:.2f}s")
            raise

    def check_bucket_access(self) -> bool:
        """
        Check if bucket is accessible.

        Returns:
            True if bucket is accessible

        Raises:
            ClientError: If bucket is not accessible
        """
        start_time = datetime.now(timezone.utc)
        try:
            logger.debug(f"[S3 CHECK] Checking bucket access | Bucket: {self.bucket_name}")
            self.s3_client.head_bucket(Bucket=self.bucket_name)
            elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
            logger.info(
                f"[S3 CHECK] ✓ Bucket accessible | "
                f"Bucket: {self.bucket_name} | "
                f"Duration: {elapsed:.2f}s"
            )
            return True
        except ClientError as e:
            elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
            log_exception(
                logger,
                e,
                f"[S3 CHECK] ✗ Cannot access bucket: {self.bucket_name} | Duration: {elapsed:.2f}s"
            )
            raise

    def file_exists(self, file_key: str) -> bool:
        """
        Check if a file exists in S3.

        Args:
            file_key: S3 object key

        Returns:
            True if file exists, False otherwise
        """
        try:
            self.s3_client.head_object(Bucket=self.bucket_name, Key=file_key)
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                return False
            log_exception(logger, e, f"Error checking file existence: {file_key}")
            raise

    def get_file_metadata(self, file_key: str) -> Optional[S3FileMetadata]:
        """
        Get metadata for a specific file.

        Args:
            file_key: S3 object key

        Returns:
            S3FileMetadata object if file exists, None otherwise
        """
        try:
            response = self.s3_client.head_object(Bucket=self.bucket_name, Key=file_key)

            return S3FileMetadata(
                key=file_key,
                size=response["ContentLength"],
                last_modified=response["LastModified"],
                etag=response["ETag"].strip('"'),
            )
        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                return None
            log_exception(logger, e, f"Error getting file metadata: {file_key}")
            raise

    def search_files_by_name(self, filename: str, prefix: Optional[str] = None) -> List[S3FileMetadata]:
        """
        Search for files by filename across the bucket.

        Args:
            filename: Filename to search for (will match files ending with this name)
            prefix: Optional prefix to narrow search

        Returns:
            List of S3FileMetadata objects matching the filename
        """
        try:
            logger.info(f"Searching for files matching: {filename}")

            files = []
            paginator = self.s3_client.get_paginator("list_objects_v2")

            pagination_config = {
                "Bucket": self.bucket_name,
            }

            if prefix:
                pagination_config["Prefix"] = prefix

            page_iterator = paginator.paginate(**pagination_config)

            for page in page_iterator:
                if "Contents" not in page:
                    continue

                for obj in page["Contents"]:
                    # Match files ending with the filename or containing it
                    if obj["Key"].endswith(filename) or filename in obj["Key"]:
                        file_metadata = S3FileMetadata(
                            key=obj["Key"],
                            size=obj["Size"],
                            last_modified=obj["LastModified"],
                            etag=obj["ETag"].strip('"'),
                        )
                        files.append(file_metadata)

            logger.info(f"Found {len(files)} files matching '{filename}'")
            return files

        except ClientError as e:
            log_exception(logger, e, f"Failed to search for files: {filename}")
            raise
        except Exception as e:
            log_exception(logger, e, f"Unexpected error searching for files: {filename}")
            raise
