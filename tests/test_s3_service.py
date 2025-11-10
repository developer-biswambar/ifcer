"""Unit tests for S3Service."""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
from botocore.exceptions import ClientError

from app.services.s3_service import S3Service
from app.models.schemas import S3FileMetadata


@pytest.mark.unit
@pytest.mark.service
class TestS3Service:
    """Test suite for S3Service."""

    def test_init(self, test_settings, s3_mock):
        """Test S3Service initialization."""
        with patch("app.config.settings", test_settings):
            with patch("boto3.client", return_value=s3_mock):
                service = S3Service()
                assert service.bucket_name == test_settings.s3_bucket_name
                assert service.s3_client is not None

    def test_check_bucket_access_success(self, test_settings, s3_bucket):
        """Test successful bucket access check."""
        s3_mock, bucket_name = s3_bucket

        with patch("app.config.settings", test_settings):
            with patch("boto3.client", return_value=s3_mock):
                service = S3Service()
                result = service.check_bucket_access()
                assert result is True

    def test_check_bucket_access_failure(self, test_settings, s3_mock):
        """Test bucket access check failure."""
        with patch("app.config.settings", test_settings):
            with patch("boto3.client", return_value=s3_mock):
                service = S3Service()
                with pytest.raises(ClientError):
                    service.check_bucket_access()

    def test_download_file(self, test_settings, s3_bucket):
        """Test file download from S3."""
        s3_mock, bucket_name = s3_bucket

        with patch("app.config.settings", test_settings):
            with patch("boto3.client", return_value=s3_mock):
                service = S3Service()
                content = service.download_file("uploads/test_file_1.pdf")

                assert content == b"Test PDF content 1"

    def test_download_file_not_found(self, test_settings, s3_bucket):
        """Test download of non-existent file."""
        s3_mock, bucket_name = s3_bucket

        with patch("app.config.settings", test_settings):
            with patch("boto3.client", return_value=s3_mock):
                service = S3Service()
                with pytest.raises(ClientError):
                    service.download_file("uploads/nonexistent.pdf")

    def test_upload_file(self, test_settings, s3_bucket):
        """Test file upload to S3."""
        s3_mock, bucket_name = s3_bucket

        with patch("app.config.settings", test_settings):
            with patch("boto3.client", return_value=s3_mock):
                service = S3Service()
                test_content = b"New file content"
                destination_key = "signed/new_file.p7m"

                result = service.upload_file(
                    test_content,
                    destination_key,
                    content_type="application/pkcs7-mime"
                )

                assert result is True

                # Verify file was uploaded
                uploaded_content = service.download_file(destination_key)
                assert uploaded_content == test_content

    def test_file_exists_true(self, test_settings, s3_bucket):
        """Test file_exists for existing file."""
        s3_mock, bucket_name = s3_bucket

        with patch("app.config.settings", test_settings):
            with patch("boto3.client", return_value=s3_mock):
                service = S3Service()
                exists = service.file_exists("uploads/test_file_1.pdf")
                assert exists is True

    def test_file_exists_false(self, test_settings, s3_bucket):
        """Test file_exists for non-existent file."""
        s3_mock, bucket_name = s3_bucket

        with patch("app.config.settings", test_settings):
            with patch("boto3.client", return_value=s3_mock):
                service = S3Service()
                exists = service.file_exists("uploads/nonexistent.pdf")
                assert exists is False

    def test_get_file_metadata_success(self, test_settings, s3_bucket):
        """Test getting file metadata."""
        s3_mock, bucket_name = s3_bucket

        with patch("app.config.settings", test_settings):
            with patch("boto3.client", return_value=s3_mock):
                service = S3Service()
                metadata = service.get_file_metadata("uploads/test_file_1.pdf")

                assert metadata is not None
                assert isinstance(metadata, S3FileMetadata)
                assert metadata.key == "uploads/test_file_1.pdf"
                assert metadata.size > 0

    def test_get_file_metadata_not_found(self, test_settings, s3_bucket):
        """Test getting metadata for non-existent file."""
        s3_mock, bucket_name = s3_bucket

        with patch("app.config.settings", test_settings):
            with patch("boto3.client", return_value=s3_mock):
                service = S3Service()
                metadata = service.get_file_metadata("uploads/nonexistent.pdf")
                assert metadata is None

    def test_search_files_by_name(self, test_settings, s3_bucket):
        """Test searching files by name."""
        s3_mock, bucket_name = s3_bucket

        with patch("app.config.settings", test_settings):
            with patch("boto3.client", return_value=s3_mock):
                service = S3Service()
                results = service.search_files_by_name("test_file_1.pdf")

                assert len(results) == 1
                assert results[0].key == "uploads/test_file_1.pdf"

    def test_search_files_by_name_multiple_matches(self, test_settings, s3_bucket):
        """Test searching files by name with multiple matches."""
        s3_mock, bucket_name = s3_bucket

        with patch("app.config.settings", test_settings):
            with patch("boto3.client", return_value=s3_mock):
                service = S3Service()
                # Search for partial name that matches multiple files
                results = service.search_files_by_name("test_file")

                assert len(results) >= 2  # Should match test_file_1 and test_file_2

    def test_search_files_by_name_no_matches(self, test_settings, s3_bucket):
        """Test searching files by name with no matches."""
        s3_mock, bucket_name = s3_bucket

        with patch("app.config.settings", test_settings):
            with patch("boto3.client", return_value=s3_mock):
                service = S3Service()
                results = service.search_files_by_name("nonexistent_file.pdf")

                assert len(results) == 0

    def test_search_files_by_name_with_prefix(self, test_settings, s3_bucket):
        """Test searching files by name with prefix filter."""
        s3_mock, bucket_name = s3_bucket

        with patch("app.config.settings", test_settings):
            with patch("boto3.client", return_value=s3_mock):
                service = S3Service()
                results = service.search_files_by_name("test_file", prefix="uploads/")

                # Should only find files in uploads/ prefix
                assert all(r.key.startswith("uploads/") for r in results)

    def test_list_files_by_date_range(self, test_settings, s3_bucket):
        """Test listing files by date range."""
        s3_mock, bucket_name = s3_bucket

        with patch("app.config.settings", test_settings):
            with patch("boto3.client", return_value=s3_mock):
                service = S3Service()

                # Test with wide date range that includes all files
                start_date = datetime.now(timezone.utc) - timedelta(days=1)
                end_date = datetime.now(timezone.utc) + timedelta(days=1)

                files = service.list_files_by_date_range(start_date, end_date)

                assert len(files) > 0
                assert all(isinstance(f, S3FileMetadata) for f in files)

    def test_list_files_by_date_range_with_prefix(self, test_settings, s3_bucket):
        """Test listing files by date range with prefix filter."""
        s3_mock, bucket_name = s3_bucket

        with patch("app.config.settings", test_settings):
            with patch("boto3.client", return_value=s3_mock):
                service = S3Service()

                start_date = datetime.now(timezone.utc) - timedelta(days=1)
                end_date = datetime.now(timezone.utc) + timedelta(days=1)

                files = service.list_files_by_date_range(
                    start_date, end_date, prefix="uploads/"
                )

                # All returned files should have the prefix
                assert all(f.key.startswith("uploads/") for f in files)

    def test_list_files_by_date_range_no_matches(self, test_settings, s3_bucket):
        """Test listing files by date range with no matches."""
        s3_mock, bucket_name = s3_bucket

        with patch("app.config.settings", test_settings):
            with patch("boto3.client", return_value=s3_mock):
                service = S3Service()

                # Use date range in the past that won't match any files
                start_date = datetime(2020, 1, 1, tzinfo=timezone.utc)
                end_date = datetime(2020, 1, 2, tzinfo=timezone.utc)

                files = service.list_files_by_date_range(start_date, end_date)

                assert len(files) == 0

    def test_upload_and_download_round_trip(self, test_settings, s3_bucket):
        """Test upload and download round trip."""
        s3_mock, bucket_name = s3_bucket

        with patch("app.config.settings", test_settings):
            with patch("boto3.client", return_value=s3_mock):
                service = S3Service()

                # Upload a file
                original_content = b"Test round trip content"
                file_key = "test_round_trip.bin"

                service.upload_file(original_content, file_key)

                # Download the same file
                downloaded_content = service.download_file(file_key)

                # Verify content matches
                assert downloaded_content == original_content

    def test_large_file_upload_download(self, test_settings, s3_bucket):
        """Test uploading and downloading a large file."""
        s3_mock, bucket_name = s3_bucket

        with patch("app.config.settings", test_settings):
            with patch("boto3.client", return_value=s3_mock):
                service = S3Service()

                # Create 5MB test file
                large_content = b"X" * (5 * 1024 * 1024)
                file_key = "large_file.bin"

                service.upload_file(large_content, file_key)
                downloaded_content = service.download_file(file_key)

                assert len(downloaded_content) == len(large_content)
                assert downloaded_content == large_content

    def test_upload_with_custom_content_type(self, test_settings, s3_bucket):
        """Test upload with custom content type."""
        s3_mock, bucket_name = s3_bucket

        with patch("app.config.settings", test_settings):
            with patch("boto3.client", return_value=s3_mock):
                service = S3Service()

                content = b"PDF content"
                file_key = "test.pdf"

                result = service.upload_file(
                    content,
                    file_key,
                    content_type="application/pdf"
                )

                assert result is True

                # Verify file exists
                assert service.file_exists(file_key)
