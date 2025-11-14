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
        file_hash: Optional[str] = None,
        hash_algorithm: Optional[str] = None,
        digital_signature: Optional[str] = None,
        vendor_timestamp: Optional[datetime] = None,
        signed_file_key: Optional[str] = None,
        file_size: Optional[int] = None,
        signed_file_size: Optional[int] = None,
        status: str = "completed",
        error_message: Optional[str] = None,
        error_type: Optional[str] = None,
        vendor_response: Optional[Dict[str, Any]] = None,
        correlation_id: Optional[str] = None,
    ) -> bool:
        """
        Save certification metadata to DynamoDB.

        For successful processing (status="completed"), all fields should be provided.
        For failed processing (status="failed"), only file_key, status, error_message,
        and error_type are required.

        Args:
            file_key: Original S3 file key (REQUIRED)
            file_hash: File hash value (optional for failed records)
            hash_algorithm: Hash algorithm used (optional for failed records)
            digital_signature: Digital signature from vendor (optional for failed records)
            vendor_timestamp: Timestamp from vendor (optional for failed records)
            signed_file_key: S3 key of signed P7M file (optional for failed records)
            file_size: Original file size (optional for failed records)
            signed_file_size: Signed file size (optional for failed records)
            status: Processing status (completed/failed, default: completed)
            error_message: Error message if failed
            error_type: Error type/exception class if failed
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
                f"Status: {status}"
            )

            # Get correlation ID from context if not explicitly provided
            if correlation_id is None:
                correlation_id = get_correlation_id()

            # Build item with required fields
            item = {
                "Id": file_key,  # Primary key - using file_key as unique identifier
                "file_key": file_key,  # Keep for reference
                "processing_timestamp": processing_timestamp,
                "filename": filename,
                "date_partition": date_partition,
                "status": status,
            }

            # Add optional fields only if provided (for successful records)
            if file_hash:
                item["file_hash"] = file_hash
            if hash_algorithm:
                item["hash_algorithm"] = hash_algorithm
            if digital_signature:
                item["digital_signature"] = digital_signature
            if vendor_timestamp:
                item["vendor_timestamp"] = vendor_timestamp.isoformat()
            if signed_file_key:
                item["signed_file_key"] = signed_file_key
            if file_size is not None:
                item["file_size"] = file_size
            if signed_file_size is not None:
                item["signed_file_size"] = signed_file_size

            # Add correlation_id if available
            if correlation_id:
                item["correlation_id"] = correlation_id

            # Add error details if failed
            if error_message:
                item["error_message"] = error_message
                item["failure_timestamp"] = processing_timestamp
            if error_type:
                item["error_type"] = error_type

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

            # Build log message based on status
            if status == "failed":
                logger.info(
                    f"[DYNAMODB SAVE] ✓ Failed record saved | "
                    f"Table: {self.table_name} | "
                    f"File: {file_key} | "
                    f"Status: {status} | "
                    f"Error: {error_message} | "
                    f"Duration: {elapsed:.2f}s{ttl_info}"
                )
            else:
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

    def get_failed_files(self, date_partition: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get all failed file processing records.

        Args:
            date_partition: Optional date partition to filter (e.g., "2025-01")
                          If None, scans entire table for failed records

        Returns:
            List of failed file records with error details
        """
        try:
            logger.info(f"[DYNAMODB QUERY] Querying failed files | Partition: {date_partition or 'ALL'}")

            if date_partition:
                # Query specific month partition
                response = self.table.query(
                    IndexName="date-index",
                    KeyConditionExpression="date_partition = :partition",
                    FilterExpression="#status = :failed",
                    ExpressionAttributeNames={
                        "#status": "status"
                    },
                    ExpressionAttributeValues={
                        ":partition": date_partition,
                        ":failed": "failed"
                    },
                    ScanIndexForward=False  # Most recent first
                )
                items = response.get("Items", [])
            else:
                # Scan entire table for failed records (use with caution for large tables)
                response = self.table.scan(
                    FilterExpression="#status = :failed",
                    ExpressionAttributeNames={
                        "#status": "status"
                    },
                    ExpressionAttributeValues={
                        ":failed": "failed"
                    }
                )
                items = response.get("Items", [])

                # Handle pagination for scan
                while "LastEvaluatedKey" in response:
                    response = self.table.scan(
                        FilterExpression="#status = :failed",
                        ExpressionAttributeNames={
                            "#status": "status"
                        },
                        ExpressionAttributeValues={
                            ":failed": "failed"
                        },
                        ExclusiveStartKey=response["LastEvaluatedKey"]
                    )
                    items.extend(response.get("Items", []))

            logger.info(f"[DYNAMODB QUERY] Found {len(items)} failed files")
            return [self._convert_decimals(item) for item in items]

        except ClientError as e:
            log_exception(logger, e, "Failed to query failed files")
            raise
        except Exception as e:
            log_exception(logger, e, "Unexpected error querying failed files")
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
