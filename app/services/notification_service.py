"""Notification service for batch completion notifications via AWS SNS.

This service sends notifications when batch processing completes, including:
- Total files processed
- Successful files count
- Failed files count and details
- Processing duration
- Correlation ID for tracing
"""

import json
from datetime import datetime
from typing import List, Optional, Dict, Any
import boto3
from botocore.exceptions import ClientError

from app.config import settings
from app.models.schemas import FileProcessingResult, ProcessingStatus
from app.utils.logger import setup_logger, log_exception

logger = setup_logger(__name__)


class NotificationService:
    """Service for sending SNS notifications on batch completion."""

    def __init__(self):
        """Initialize SNS client."""
        try:
            # Prepare boto3 client configuration
            client_config = {
                "region_name": settings.aws_region
            }

            # Add endpoint_url for moto/LocalStack testing
            if settings.aws_endpoint_url:
                client_config["endpoint_url"] = settings.aws_endpoint_url
                logger.info(f"Using custom AWS endpoint for SNS: {settings.aws_endpoint_url}")

            # Add explicit credentials if provided (for moto/LocalStack)
            if settings.aws_access_key_id and settings.aws_secret_access_key:
                client_config["aws_access_key_id"] = settings.aws_access_key_id
                client_config["aws_secret_access_key"] = settings.aws_secret_access_key
                logger.debug("Using explicit AWS credentials for SNS")

            # Create SNS client
            self.sns_client = boto3.client("sns", **client_config)
            self.topic_arn = settings.notification_sns_topic_arn

            if self.topic_arn:
                logger.info(f"SNS notification service initialized | Topic: {self.topic_arn}")
            else:
                logger.info("SNS notifications disabled (NOTIFICATION_SNS_TOPIC_ARN not set)")

        except Exception as e:
            log_exception(logger, e, "Failed to initialize SNS notification service")
            # Don't raise - notifications are optional, service should continue
            self.sns_client = None
            self.topic_arn = None

    def send_batch_completion_notification(
        self,
        total_files: int,
        successful_files: int,
        failed_files: int,
        results: List[FileProcessingResult],
        duration_seconds: float,
        date_range: Optional[Dict[str, str]] = None,
        correlation_id: Optional[str] = None,
    ) -> bool:
        """
        Send SNS notification on batch processing completion.

        Args:
            total_files: Total number of files in batch
            successful_files: Number of successfully processed files
            failed_files: Number of failed files
            results: List of FileProcessingResult objects
            duration_seconds: Total processing duration in seconds
            date_range: Optional date range dict with 'start' and 'end' keys
            correlation_id: Request correlation ID for tracing

        Returns:
            True if notification sent successfully, False otherwise
        """
        # Check if notifications are enabled
        if not self.topic_arn or not self.sns_client:
            logger.debug("SNS notifications disabled, skipping notification")
            return False

        try:
            logger.info(
                f"[SNS NOTIFY] Sending batch completion notification | "
                f"Total: {total_files} | Success: {successful_files} | Failed: {failed_files}"
            )

            # Extract failed file details
            failed_file_details = []
            for result in results:
                if result.status == ProcessingStatus.FAILED:
                    failed_file_details.append({
                        "file_key": result.file_key,
                        "filename": result.filename,
                        "error_message": result.error_message,
                        "processing_time": f"{result.processing_time:.2f}s" if result.processing_time else "N/A"
                    })

            # Build notification message
            subject = self._build_subject(total_files, successful_files, failed_files)
            message = self._build_message(
                total_files=total_files,
                successful_files=successful_files,
                failed_files=failed_files,
                failed_file_details=failed_file_details,
                duration_seconds=duration_seconds,
                date_range=date_range,
                correlation_id=correlation_id
            )

            # Send SNS notification
            response = self.sns_client.publish(
                TopicArn=self.topic_arn,
                Subject=subject,
                Message=message,
                MessageAttributes={
                    "correlation_id": {
                        "DataType": "String",
                        "StringValue": correlation_id or "N/A"
                    },
                    "total_files": {
                        "DataType": "Number",
                        "StringValue": str(total_files)
                    },
                    "successful_files": {
                        "DataType": "Number",
                        "StringValue": str(successful_files)
                    },
                    "failed_files": {
                        "DataType": "Number",
                        "StringValue": str(failed_files)
                    }
                }
            )

            message_id = response.get("MessageId", "unknown")
            logger.info(
                f"[SNS NOTIFY] ✓ Notification sent successfully | "
                f"MessageId: {message_id} | "
                f"Topic: {self.topic_arn}"
            )

            return True

        except ClientError as e:
            log_exception(logger, e, "[SNS NOTIFY] Failed to send SNS notification")
            # Don't raise - notification failure shouldn't fail the batch
            return False
        except Exception as e:
            log_exception(logger, e, "[SNS NOTIFY] Unexpected error sending notification")
            return False

    def _build_subject(self, total_files: int, successful_files: int, failed_files: int) -> str:
        """
        Build SNS notification subject line.

        Args:
            total_files: Total number of files
            successful_files: Number of successful files
            failed_files: Number of failed files

        Returns:
            Subject line string
        """
        if failed_files == 0:
            return f"✓ IFCER Batch Complete: {total_files}/{total_files} files processed successfully"
        else:
            return f"⚠ IFCER Batch Complete: {successful_files}/{total_files} files successful, {failed_files} failed"

    def _build_message(
        self,
        total_files: int,
        successful_files: int,
        failed_files: int,
        failed_file_details: List[Dict[str, Any]],
        duration_seconds: float,
        date_range: Optional[Dict[str, str]] = None,
        correlation_id: Optional[str] = None
    ) -> str:
        """
        Build detailed SNS notification message.

        Args:
            total_files: Total number of files
            successful_files: Number of successful files
            failed_files: Number of failed files
            failed_file_details: List of failed file details
            duration_seconds: Processing duration
            date_range: Optional date range
            correlation_id: Request correlation ID

        Returns:
            Formatted message string
        """
        # Build message parts
        lines = [
            "=" * 60,
            "IFCER BATCH PROCESSING COMPLETE",
            "=" * 60,
            ""
        ]

        # Date range if provided
        if date_range:
            lines.append(f"Date Range: {date_range.get('start')} to {date_range.get('end')}")
            lines.append("")

        # Summary statistics
        lines.append("SUMMARY:")
        lines.append(f"  Total Files:      {total_files}")
        lines.append(f"  ✓ Successful:     {successful_files}")
        lines.append(f"  ✗ Failed:         {failed_files}")
        lines.append(f"  Success Rate:     {(successful_files/total_files*100):.1f}%" if total_files > 0 else "  Success Rate:     N/A")
        lines.append(f"  Duration:         {duration_seconds:.2f}s ({duration_seconds/60:.1f} minutes)")
        lines.append(f"  Avg per file:     {duration_seconds/total_files:.2f}s" if total_files > 0 else "  Avg per file:     N/A")
        lines.append("")

        # Correlation ID
        if correlation_id:
            lines.append(f"Correlation ID: {correlation_id}")
            lines.append("")

        # Failed files details (if any)
        if failed_files > 0:
            lines.append("=" * 60)
            lines.append(f"FAILED FILES ({failed_files}):")
            lines.append("=" * 60)
            lines.append("")

            for idx, failed_file in enumerate(failed_file_details, 1):
                lines.append(f"{idx}. {failed_file['filename']}")
                lines.append(f"   File Key: {failed_file['file_key']}")
                lines.append(f"   Error: {failed_file['error_message']}")
                lines.append(f"   Processing Time: {failed_file['processing_time']}")
                lines.append("")

            lines.append("=" * 60)
            lines.append("ACTION REQUIRED:")
            lines.append("=" * 60)
            lines.append("")
            lines.append("To retry failed files, use the /recertify endpoint:")
            lines.append("")

            for failed_file in failed_file_details:
                lines.append(f"POST /recertify")
                lines.append(f"{{")
                lines.append(f'  "file_key": "{failed_file["file_key"]}"')
                lines.append(f"}}")
                lines.append("")

        else:
            lines.append("=" * 60)
            lines.append("✓ ALL FILES PROCESSED SUCCESSFULLY!")
            lines.append("=" * 60)

        return "\n".join(lines)
