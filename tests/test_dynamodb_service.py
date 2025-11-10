"""Unit tests for DynamoDBService."""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
from decimal import Decimal

from app.services.dynamodb_service import DynamoDBService


@pytest.mark.unit
@pytest.mark.service
class TestDynamoDBService:
    """Test suite for DynamoDBService."""

    def test_init(self, test_settings, dynamodb_mock):
        """Test DynamoDBService initialization."""
        with patch("app.config.settings", test_settings):
            with patch("boto3.resource", return_value=dynamodb_mock):
                service = DynamoDBService()
                assert service.table_name == test_settings.dynamodb_table_name
                assert service.table is not None

    def test_save_certification(self, test_settings, dynamodb_table):
        """Test saving certification metadata."""
        with patch("app.config.settings", test_settings):
            with patch("boto3.resource", return_value=dynamodb_table.meta.client._client_config):
                service = DynamoDBService()
                service.table = dynamodb_table

                file_key = "uploads/test.pdf"
                file_hash = "abc123"
                vendor_timestamp = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

                result = service.save_certification(
                    file_key=file_key,
                    file_hash=file_hash,
                    hash_algorithm="sha256",
                    digital_signature="signature123",
                    vendor_timestamp=vendor_timestamp,
                    signed_file_key="signed/test.pdf.p7m",
                    file_size=1024,
                    signed_file_size=2048,
                    status="completed",
                )

                assert result is True

                # Verify item was saved
                response = dynamodb_table.query(
                    KeyConditionExpression="file_key = :file_key",
                    ExpressionAttributeValues={":file_key": file_key},
                )
                assert len(response["Items"]) == 1
                item = response["Items"][0]
                assert item["file_key"] == file_key
                assert item["file_hash"] == file_hash
                assert item["hash_algorithm"] == "sha256"
                assert item["status"] == "completed"

    def test_save_certification_with_error(self, test_settings, dynamodb_table):
        """Test saving certification with error message."""
        with patch("app.config.settings", test_settings):
            service = DynamoDBService()
            service.table = dynamodb_table

            file_key = "uploads/failed.pdf"
            vendor_timestamp = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

            result = service.save_certification(
                file_key=file_key,
                file_hash="",
                hash_algorithm="sha256",
                digital_signature="",
                vendor_timestamp=vendor_timestamp,
                signed_file_key="",
                file_size=1024,
                signed_file_size=0,
                status="failed",
                error_message="Test error message",
            )

            assert result is True

                # Verify error message was saved
            cert = service.get_certification(file_key)
            assert cert is not None
            assert cert["status"] == "failed"
            assert cert["error_message"] == "Test error message"

    def test_get_certification(self, test_settings, dynamodb_table):
        """Test getting certification metadata."""
        with patch("app.config.settings", test_settings):
            service = DynamoDBService()
            service.table = dynamodb_table

            file_key = "uploads/test_get.pdf"
            vendor_timestamp = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

            # Save a certification
            service.save_certification(
                file_key=file_key,
                file_hash="hash123",
                hash_algorithm="sha256",
                digital_signature="sig123",
                vendor_timestamp=vendor_timestamp,
                signed_file_key="signed/test_get.pdf.p7m",
                file_size=1024,
                signed_file_size=2048,
            )

            # Get the certification
            cert = service.get_certification(file_key)

            assert cert is not None
            assert cert["file_key"] == file_key
            assert cert["file_hash"] == "hash123"
            assert cert["status"] == "completed"

    def test_get_certification_not_found(self, test_settings, dynamodb_table):
        """Test getting non-existent certification."""
        with patch("app.config.settings", test_settings):
            service = DynamoDBService()
            service.table = dynamodb_table

            cert = service.get_certification("uploads/nonexistent.pdf")
            assert cert is None

    def test_get_latest_certification(self, test_settings, dynamodb_table):
        """Test getting the latest certification when multiple exist."""
        with patch("app.config.settings", test_settings):
            service = DynamoDBService()
            service.table = dynamodb_table

            file_key = "uploads/multiple.pdf"

            # Save multiple certifications for same file
            for i in range(3):
                vendor_timestamp = datetime(2024, 1, 1, 12, i, 0, tzinfo=timezone.utc)
                service.save_certification(
                    file_key=file_key,
                    file_hash=f"hash{i}",
                    hash_algorithm="sha256",
                    digital_signature=f"sig{i}",
                    vendor_timestamp=vendor_timestamp,
                    signed_file_key=f"signed/multiple_{i}.pdf.p7m",
                    file_size=1024,
                    signed_file_size=2048,
                )

            # Get certification - should return the latest (i=2)
            cert = service.get_certification(file_key)

            assert cert is not None
            assert cert["file_hash"] == "hash2"  # Latest one

    def test_batch_get_certifications(self, test_settings, dynamodb_table):
        """Test batch getting certifications."""
        with patch("app.config.settings", test_settings):
            service = DynamoDBService()
            service.table = dynamodb_table

            # Save multiple certifications
            file_keys = [f"uploads/batch_{i}.pdf" for i in range(5)]
            vendor_timestamp = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

            for i, file_key in enumerate(file_keys):
                service.save_certification(
                    file_key=file_key,
                    file_hash=f"hash{i}",
                    hash_algorithm="sha256",
                    digital_signature=f"sig{i}",
                    vendor_timestamp=vendor_timestamp,
                    signed_file_key=f"signed/batch_{i}.pdf.p7m",
                    file_size=1024,
                    signed_file_size=2048,
                )

            # Batch get certifications
            results = service.batch_get_certifications(file_keys)

            assert len(results) == 5
            for file_key in file_keys:
                assert file_key in results
                assert results[file_key]["file_key"] == file_key

    def test_batch_get_certifications_empty(self, test_settings, dynamodb_table):
        """Test batch get with empty list."""
        with patch("app.config.settings", test_settings):
            service = DynamoDBService()
            service.table = dynamodb_table

            results = service.batch_get_certifications([])
            assert results == {}

    def test_batch_get_certifications_partial(self, test_settings, dynamodb_table):
        """Test batch get with some files not found."""
        with patch("app.config.settings", test_settings):
            service = DynamoDBService()
            service.table = dynamodb_table

            # Save only one certification
            vendor_timestamp = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
            service.save_certification(
                file_key="uploads/exists.pdf",
                file_hash="hash1",
                hash_algorithm="sha256",
                digital_signature="sig1",
                vendor_timestamp=vendor_timestamp,
                signed_file_key="signed/exists.pdf.p7m",
                file_size=1024,
                signed_file_size=2048,
            )

            # Request both existing and non-existing files
            file_keys = ["uploads/exists.pdf", "uploads/notexists.pdf"]
            results = service.batch_get_certifications(file_keys)

            assert len(results) == 1
            assert "uploads/exists.pdf" in results
            assert "uploads/notexists.pdf" not in results

    def test_convert_decimals(self, test_settings, dynamodb_table):
        """Test decimal conversion."""
        with patch("app.config.settings", test_settings):
            service = DynamoDBService()

            item = {
                "file_size": Decimal("1024"),
                "signed_file_size": Decimal("2048.5"),
                "nested": {
                    "value": Decimal("100"),
                },
                "list": [Decimal("1"), Decimal("2.5")],
            }

            result = service._convert_decimals(item)

            assert isinstance(result["file_size"], int)
            assert result["file_size"] == 1024
            assert isinstance(result["signed_file_size"], float)
            assert result["signed_file_size"] == 2048.5
            assert isinstance(result["nested"]["value"], int)

    def test_generate_month_partitions(self, test_settings, dynamodb_table):
        """Test month partition generation."""
        with patch("app.config.settings", test_settings):
            service = DynamoDBService()

            # Test within same month
            start = datetime(2024, 1, 15, tzinfo=timezone.utc)
            end = datetime(2024, 1, 20, tzinfo=timezone.utc)
            partitions = service._generate_month_partitions(start, end)
            assert partitions == ["2024-01"]

            # Test across 3 months
            start = datetime(2024, 1, 15, tzinfo=timezone.utc)
            end = datetime(2024, 3, 15, tzinfo=timezone.utc)
            partitions = service._generate_month_partitions(start, end)
            assert partitions == ["2024-01", "2024-02", "2024-03"]

            # Test across year boundary
            start = datetime(2023, 12, 15, tzinfo=timezone.utc)
            end = datetime(2024, 2, 15, tzinfo=timezone.utc)
            partitions = service._generate_month_partitions(start, end)
            assert partitions == ["2023-12", "2024-01", "2024-02"]

    def test_check_table_exists(self, test_settings, dynamodb_table):
        """Test checking if table exists."""
        with patch("app.config.settings", test_settings):
            service = DynamoDBService()
            service.table = dynamodb_table

            exists = service.check_table_exists()
            assert exists is True

    def test_filename_extraction(self, test_settings, dynamodb_table):
        """Test that filename is correctly extracted from file_key."""
        with patch("app.config.settings", test_settings):
            service = DynamoDBService()
            service.table = dynamodb_table

            file_key = "uploads/nested/path/document.pdf"
            vendor_timestamp = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

            service.save_certification(
                file_key=file_key,
                file_hash="hash123",
                hash_algorithm="sha256",
                digital_signature="sig123",
                vendor_timestamp=vendor_timestamp,
                signed_file_key="signed/document.pdf.p7m",
                file_size=1024,
                signed_file_size=2048,
            )

            cert = service.get_certification(file_key)
            assert cert["filename"] == "document.pdf"

    def test_date_partition_format(self, test_settings, dynamodb_table):
        """Test that date_partition is in correct format."""
        with patch("app.config.settings", test_settings):
            service = DynamoDBService()
            service.table = dynamodb_table

            file_key = "uploads/test.pdf"
            vendor_timestamp = datetime(2024, 3, 15, 12, 0, 0, tzinfo=timezone.utc)

            service.save_certification(
                file_key=file_key,
                file_hash="hash123",
                hash_algorithm="sha256",
                digital_signature="sig123",
                vendor_timestamp=vendor_timestamp,
                signed_file_key="signed/test.pdf.p7m",
                file_size=1024,
                signed_file_size=2048,
            )

            cert = service.get_certification(file_key)
            # date_partition should be YYYY-MM format
            assert cert["date_partition"].startswith("20")  # Starts with year
            assert len(cert["date_partition"]) == 7  # YYYY-MM
            assert "-" in cert["date_partition"]
