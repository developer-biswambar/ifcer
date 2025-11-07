"""DynamoDB service for certification metadata storage."""

import boto3
from botocore.exceptions import ClientError
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from decimal import Decimal

from app.config import settings
from app.utils.logger import setup_logger, log_exception

logger = setup_logger(__name__)


class DynamoDBService:
    """Service for storing and retrieving certification metadata in DynamoDB."""

    def __init__(self):
        """Initialize DynamoDB client with configuration."""
        try:
            # Create DynamoDB resource - uses IAM role credentials automatically in ECS
            self.dynamodb = boto3.resource("dynamodb", region_name=settings.aws_region)
            self.table_name = settings.dynamodb_table_name
            self.table = self.dynamodb.Table(self.table_name)

            logger.info(f"DynamoDB service initialized for table: {self.table_name} in region: {settings.aws_region}")

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

        Returns:
            True if successful
        """
        try:
            processing_timestamp = datetime.utcnow().isoformat()

            # Extract filename for GSI
            filename = file_key.split("/")[-1]

            # Extract date partition for GSI (YYYY-MM format)
            date_partition = processing_timestamp[:7]  # "2025-01"

            item = {
                "file_key": file_key,
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

            if error_message:
                item["error_message"] = error_message

            if vendor_response:
                item["vendor_response"] = vendor_response

            # Add TTL if configured
            if settings.dynamodb_ttl_days:
                ttl = datetime.utcnow() + timedelta(days=settings.dynamodb_ttl_days)
                item["ttl"] = int(ttl.timestamp())

            self.table.put_item(Item=item)

            logger.info(f"Saved certification metadata for: {file_key}")
            return True

        except ClientError as e:
            log_exception(logger, e, f"Failed to save certification: {file_key}")
            raise
        except Exception as e:
            log_exception(logger, e, f"Unexpected error saving certification: {file_key}")
            raise

    def get_certification(self, file_key: str) -> Optional[Dict[str, Any]]:
        """
        Get the most recent certification for a file.

        Args:
            file_key: Original S3 file key

        Returns:
            Certification metadata dict or None if not found
        """
        try:
            response = self.table.query(
                KeyConditionExpression="file_key = :file_key",
                ExpressionAttributeValues={":file_key": file_key},
                ScanIndexForward=False,  # Sort descending (most recent first)
                Limit=1,
            )

            items = response.get("Items", [])
            if items:
                logger.debug(f"Found certification for: {file_key}")
                return self._convert_decimals(items[0])

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
