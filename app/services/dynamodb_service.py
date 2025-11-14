"""DynamoDB service for certification metadata storage."""

import boto3
from botocore.exceptions import ClientError
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any
from decimal import Decimal

from app.config import settings
from app.utils.logger import setup_logger, log_exception
from app.middleware.correlation_id import get_correlation_id

logger = setup_logger(__name__)


class DynamoDBService:
    """Service for storing and retrieving certification metadata in DynamoDB."""

    def __init__(self):
        """Initialize DynamoDB client with configuration."""
        try:
            # Prepare boto3 resource configuration
            resource_config = {
                "region_name": settings.aws_region
            }

            # Add endpoint_url for moto/LocalStack testing
            if settings.aws_endpoint_url:
                resource_config["endpoint_url"] = settings.aws_endpoint_url
                logger.info(f"Using custom AWS endpoint: {settings.aws_endpoint_url}")

            # Add explicit credentials if provided (for moto/LocalStack)
            if settings.aws_access_key_id and settings.aws_secret_access_key:
                resource_config["aws_access_key_id"] = settings.aws_access_key_id
                resource_config["aws_secret_access_key"] = settings.aws_secret_access_key
                logger.debug("Using explicit AWS credentials from configuration")

            # Create DynamoDB resource - uses IAM role credentials automatically in ECS
            # unless explicit credentials are provided
            self.dynamodb = boto3.resource("dynamodb", **resource_config)
            self.table_name = settings.dynamodb_table_name
            self.table = self.dynamodb.Table(self.table_name)

            endpoint_info = f" | Endpoint: {settings.aws_endpoint_url}" if settings.aws_endpoint_url else ""
            logger.info(f"DynamoDB service initialized for table: {self.table_name} in region: {settings.aws_region}{endpoint_info}")

        except Exception as e:
            log_exception(logger, e, "Failed to initialize DynamoDB service")
            raise

    def save_certification(
        self,
        file_key: str,
        file_hash: str,
        hash_algorithm: str,
        digital_signature: str,
        vendor_timestamp: datetime,
        signed_file_key: str,
        file_size: int,
        signed_file_size: int,
        status: str = "completed",
        error_message: Optional[str] = None,
        vendor_response: Optional[Dict[str, Any]] = None,
        correlation_id: Optional[str] = None,
    ) -> bool:
        """
        Save certification metadata to DynamoDB.

        Args:
            file_key: Original S3 file key
            file_hash: File hash value
            hash_algorithm: Hash algorithm used
            digital_signature: Digital signature from vendor
            vendor_timestamp: Timestamp from vendor
            signed_file_key: S3 key of signed P7M file
            file_size: Original file size
            signed_file_size: Signed file size
            status: Processing status (completed/failed)
            error_message: Error message if failed
            vendor_response: Full vendor API response
            correlation_id: Request correlation ID for tracing

        Returns:
            True if successful
        """
        start_time = datetime.now(timezone.utc)
        try:
            processing_timestamp = datetime.now(timezone.utc).isoformat()

            # Extract filename for GSI
            filename = file_key.split("/")[-1]

            # Extract date partition for GSI (YYYY-MM format)
            date_partition = processing_timestamp[:7]  # "2025-01"

            logger.debug(
                f"[DYNAMODB SAVE] Preparing certification record | "
                f"File: {file_key} | "
                f"Status: {status} | "
                f"Hash: {file_hash[:16]}..."
            )

            # Get correlation ID from context if not explicitly provided
            if correlation_id is None:
                correlation_id = get_correlation_id()

            item = {
                "Id": file_key,  # Primary key - using file_key as unique identifier
                "file_key": file_key,  # Keep for reference
                "processing_timestamp": processing_timestamp,
                "filename": filename,
                "date_partition": date_partition,
                "file_hash": file_hash,
                "hash_algorithm": hash_algorithm,
                "digital_signature": digital_signature,
                "vendor_timestamp": vendor_timestamp.isoformat(),
                "signed_file_key": signed_file_key,
                "file_size": file_size,
                "signed_file_size": signed_file_size,
                "status": status,
            }

            # Add correlation_id if available
            if correlation_id:
                item["correlation_id"] = correlation_id

            if error_message:
                item["error_message"] = error_message

            if vendor_response:
                item["vendor_response"] = vendor_response

            # Add TTL if configured
            ttl_info = ""
            if settings.dynamodb_ttl_days:
                ttl = datetime.now(timezone.utc) + timedelta(days=settings.dynamodb_ttl_days)
                item["ttl"] = int(ttl.timestamp())
                ttl_info = f" | TTL: {settings.dynamodb_ttl_days} days"

            logger.debug(f"[DYNAMODB SAVE] Writing item to table: {self.table_name}")
            self.table.put_item(Item=item)

            elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
            logger.info(
                f"[DYNAMODB SAVE] ✓ Certification saved | "
                f"Table: {self.table_name} | "
                f"File: {file_key} | "
                f"Status: {status} | "
                f"Original size: {file_size:,} bytes | "
                f"P7M size: {signed_file_size:,} bytes | "
                f"Duration: {elapsed:.2f}s{ttl_info}"
            )
            return True

        except ClientError as e:
            elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
            log_exception(logger, e, f"[DYNAMODB SAVE] Failed to save certification: {file_key} after {elapsed:.2f}s")
            raise
        except Exception as e:
            elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
            log_exception(logger, e, f"[DYNAMODB SAVE] Unexpected error saving certification: {file_key} after {elapsed:.2f}s")
            raise

    def get_certification(self, file_key: str) -> Optional[Dict[str, Any]]:
        """
        Get the certification for a file.

        Args:
            file_key: Original S3 file key (used as Id)

        Returns:
            Certification metadata dict or None if not found
        """
        try:
            response = self.table.get_item(
                Key={"Id": file_key}
            )

            item = response.get("Item")
            if item:
                logger.debug(f"Found certification for: {file_key}")
                return self._convert_decimals(item)

            logger.debug(f"No certification found for: {file_key}")
            return None

        except ClientError as e:
            log_exception(logger, e, f"Failed to get certification: {file_key}")
            raise
        except Exception as e:
            log_exception(logger, e, f"Unexpected error getting certification: {file_key}")
            raise

    def get_certifications_by_filename(self, filename: str) -> List[Dict[str, Any]]:
        """
        Get all certifications for files matching a filename.

        Args:
            filename: Filename to search for

        Returns:
            List of certification metadata dicts
        """
        try:
            response = self.table.query(
                IndexName="filename-index",
                KeyConditionExpression="filename = :filename",
                ExpressionAttributeValues={":filename": filename},
                ScanIndexForward=False,  # Most recent first
            )

            items = response.get("Items", [])
            logger.info(f"Found {len(items)} certifications for filename: {filename}")

            return [self._convert_decimals(item) for item in items]

        except ClientError as e:
            log_exception(logger, e, f"Failed to query by filename: {filename}")
            raise
        except Exception as e:
            log_exception(logger, e, f"Unexpected error querying filename: {filename}")
            raise

    def get_certifications_by_date_range(
        self, start_date: datetime, end_date: datetime
    ) -> List[Dict[str, Any]]:
        """
        Get all certifications within a date range.

        Args:
            start_date: Start date for filtering
            end_date: End date for filtering

        Returns:
            List of certification metadata dicts
        """
        try:
            # Generate all month partitions in the range
            partitions = self._generate_month_partitions(start_date, end_date)

            all_items = []
            start_iso = start_date.isoformat()
            end_iso = end_date.isoformat()

            for partition in partitions:
                response = self.table.query(
                    IndexName="date-index",
                    KeyConditionExpression="date_partition = :partition AND processing_timestamp BETWEEN :start AND :end",
                    ExpressionAttributeValues={
                        ":partition": partition,
                        ":start": start_iso,
                        ":end": end_iso,
                    },
                )

                all_items.extend(response.get("Items", []))

            logger.info(
                f"Found {len(all_items)} certifications from {start_date} to {end_date}"
            )

            return [self._convert_decimals(item) for item in all_items]

        except ClientError as e:
            log_exception(logger, e, "Failed to query by date range")
            raise
        except Exception as e:
            log_exception(logger, e, "Unexpected error querying date range")
            raise

    def batch_get_certifications(self, file_keys: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Get certifications for multiple files in a single batch request.

        Args:
            file_keys: List of file keys to retrieve

        Returns:
            Dict mapping file_key to certification metadata
        """
        try:
            if not file_keys:
                return {}

            # DynamoDB batch_get_item has a limit of 100 items
            results = {}

            for i in range(0, len(file_keys), 100):
                batch_keys = file_keys[i:i + 100]

                # For each file, we need to query to get the latest certification
                # batch_get_item doesn't support sort key conditions, so we'll use individual queries
                for file_key in batch_keys:
                    cert = self.get_certification(file_key)
                    if cert:
                        results[file_key] = cert

            logger.info(f"Retrieved {len(results)} certifications from {len(file_keys)} requests")
            return results

        except Exception as e:
            log_exception(logger, e, "Failed to batch get certifications")
            raise

    def _convert_decimals(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert DynamoDB Decimal types to int/float for JSON serialization.

        Args:
            item: DynamoDB item with potential Decimal values

        Returns:
            Item with Decimals converted to int/float
        """
        for key, value in item.items():
            if isinstance(value, Decimal):
                if value % 1 == 0:
                    item[key] = int(value)
                else:
                    item[key] = float(value)
            elif isinstance(value, dict):
                item[key] = self._convert_decimals(value)
            elif isinstance(value, list):
                item[key] = [
                    self._convert_decimals(v) if isinstance(v, dict) else v
                    for v in value
                ]
        return item

    def _generate_month_partitions(
        self, start_date: datetime, end_date: datetime
    ) -> List[str]:
        """
        Generate list of month partitions (YYYY-MM) between two dates.

        Args:
            start_date: Start date
            end_date: End date

        Returns:
            List of month partition strings
        """
        partitions = []
        current = start_date.replace(day=1)
        end = end_date.replace(day=1)

        while current <= end:
            partitions.append(current.strftime("%Y-%m"))
            # Move to next month
            if current.month == 12:
                current = current.replace(year=current.year + 1, month=1)
            else:
                current = current.replace(month=current.month + 1)

        return partitions

    def check_table_exists(self) -> bool:
        """
        Check if DynamoDB table exists.

        Returns:
            True if table exists and is active
        """
        try:
            status = self.table.table_status
            logger.info(f"DynamoDB table {self.table_name} status: {status}")
            return status == "ACTIVE"
        except ClientError as e:
            if e.response["Error"]["Code"] == "ResourceNotFoundException":
                logger.warning(f"DynamoDB table {self.table_name} does not exist")
                return False
            log_exception(logger, e, "Error checking table existence")
            raise
