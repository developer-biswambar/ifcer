"""S3 service for file operations."""

import boto3
from botocore.exceptions import ClientError, BotoCoreError
from datetime import datetime
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
            # Create S3 client with credentials from environment
            session_kwargs = {
                "region_name": settings.aws_region,
            }

            if settings.aws_access_key_id and settings.aws_secret_access_key:
                session_kwargs["aws_access_key_id"] = settings.aws_access_key_id
                session_kwargs["aws_secret_access_key"] = settings.aws_secret_access_key

            self.s3_client = boto3.client("s3", **session_kwargs)
            self.bucket_name = settings.s3_bucket_name

            logger.info(f"S3 client initialized for bucket: {self.bucket_name}")

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
        try:
            logger.info(
                f"Listing files from {start_date} to {end_date} with prefix: {prefix or 'None'}"
            )

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

            logger.info(f"Found {len(files)} files matching criteria")
            return files

        except ClientError as e:
            log_exception(logger, e, "Failed to list S3 files")
            raise
        except Exception as e:
            log_exception(logger, e, "Unexpected error listing S3 files")
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
        try:
            logger.debug(f"Downloading file: {file_key}")

            response = self.s3_client.get_object(
                Bucket=self.bucket_name, Key=file_key
            )

            file_content = response["Body"].read()
            logger.debug(f"Downloaded {len(file_content)} bytes from {file_key}")

            return file_content

        except ClientError as e:
            log_exception(logger, e, f"Failed to download file: {file_key}")
            raise
        except Exception as e:
            log_exception(logger, e, f"Unexpected error downloading file: {file_key}")
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
        try:
            logger.info(f"Uploading file to: {destination_key}")

            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=destination_key,
                Body=file_content,
                ContentType=content_type,
            )

            logger.info(f"Successfully uploaded file: {destination_key}")
            return True

        except ClientError as e:
            log_exception(logger, e, f"Failed to upload file: {destination_key}")
            raise
        except Exception as e:
            log_exception(logger, e, f"Unexpected error uploading file: {destination_key}")
            raise

    def check_bucket_access(self) -> bool:
        """
        Check if bucket is accessible.

        Returns:
            True if bucket is accessible

        Raises:
            ClientError: If bucket is not accessible
        """
        try:
            self.s3_client.head_bucket(Bucket=self.bucket_name)
            logger.info(f"Successfully accessed bucket: {self.bucket_name}")
            return True
        except ClientError as e:
            log_exception(logger, e, f"Cannot access bucket: {self.bucket_name}")
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
