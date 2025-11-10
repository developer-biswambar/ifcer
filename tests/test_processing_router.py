"""Unit tests for processing router endpoints."""

import pytest
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from unittest.mock import patch, Mock

from app.main import app
from app.models.schemas import (
    ProcessingStatus,
    FileProcessingResult,
    SignatureResponse,
    FileHashInfo,
)


@pytest.mark.unit
@pytest.mark.router
class TestProcessingRouter:
    """Test suite for processing router endpoints."""

    @pytest.fixture
    def client(self):
        """Create a test client."""
        return TestClient(app)

    @pytest.fixture
    def mock_all_services(
        self, mock_s3_service, mock_dynamodb_service, mock_hash_service, mock_signature_service
    ):
        """Patch all services at once."""
        with patch("app.routers.processing.s3_service", mock_s3_service), \
             patch("app.routers.processing.dynamodb_service", mock_dynamodb_service), \
             patch("app.routers.processing.hash_service", mock_hash_service), \
             patch("app.routers.processing.signature_service", mock_signature_service):
            yield {
                "s3": mock_s3_service,
                "dynamodb": mock_dynamodb_service,
                "hash": mock_hash_service,
                "signature": mock_signature_service,
            }

    def test_health_check_success(self, client, mock_all_services):
        """Test successful health check."""
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data
        assert "timestamp" in data

    def test_health_check_s3_failure(self, client, mock_all_services):
        """Test health check with S3 failure."""
        mock_all_services["s3"].check_bucket_access.return_value = False

        response = client.get("/health")

        assert response.status_code == 503
        assert "Service dependencies" in response.json()["detail"]

    def test_health_check_vendor_api_failure(self, client, mock_all_services):
        """Test health check with vendor API failure."""
        mock_all_services["signature"].health_check.return_value = False

        response = client.get("/health")

        assert response.status_code == 503

    def test_recertify_single_file_success(self, client, mock_all_services):
        """Test successful single file recertification."""
        # Set up mocks
        mock_all_services["s3"].download_file.return_value = b"test file content"

        response = client.post(
            "/recertify",
            json={"file_key": "uploads/test.pdf"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["file_key"] == "uploads/test.pdf"
        assert data["status"] == "completed"
        assert "signature" in data
        assert "timestamp" in data
        assert "p7m_file_key" in data

    def test_recertify_file_not_found(self, client, mock_all_services):
        """Test recertification with non-existent file."""
        from botocore.exceptions import ClientError

        # Mock S3 to raise NoSuchKey error
        error_response = {"Error": {"Code": "NoSuchKey", "Message": "The specified key does not exist."}}
        mock_all_services["s3"].download_file.side_effect = ClientError(error_response, "GetObject")

        response = client.post(
            "/recertify",
            json={"file_key": "uploads/nonexistent.pdf"}
        )

        assert response.status_code == 500

    def test_recertify_signature_service_failure(self, client, mock_all_services):
        """Test recertification with signature service failure."""
        mock_all_services["s3"].download_file.return_value = b"test file content"
        mock_all_services["signature"].sign_file_hash.side_effect = Exception("Signature service error")

        response = client.post(
            "/recertify",
            json={"file_key": "uploads/test.pdf"}
        )

        assert response.status_code == 500

    def test_process_files_empty_date_range(self, client, mock_all_services):
        """Test processing with date range that has no files."""
        # Mock S3 to return empty list
        mock_all_services["s3"].list_files_by_date_range.return_value = []

        start_date = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end_date = datetime(2024, 1, 2, tzinfo=timezone.utc)

        response = client.post(
            "/process",
            json={
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total_files"] == 0
        assert data["processed_files"] == 0
        assert len(data["results"]) == 0

    def test_process_files_success(self, client, mock_all_services):
        """Test successful batch processing."""
        from app.models.schemas import S3FileMetadata

        # Mock S3 to return some files
        mock_files = [
            S3FileMetadata(
                key="uploads/file1.pdf",
                size=1024,
                last_modified=datetime.now(timezone.utc),
                etag="abc123"
            ),
            S3FileMetadata(
                key="uploads/file2.pdf",
                size=2048,
                last_modified=datetime.now(timezone.utc),
                etag="def456"
            ),
        ]
        mock_all_services["s3"].list_files_by_date_range.return_value = mock_files
        mock_all_services["s3"].download_file.return_value = b"test content"

        start_date = datetime.now(timezone.utc) - timedelta(days=1)
        end_date = datetime.now(timezone.utc)

        response = client.post(
            "/process",
            json={
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total_files"] == 2
        assert data["processed_files"] == 2
        assert data["successful_files"] == 2
        assert data["failed_files"] == 0
        assert len(data["results"]) == 2

    def test_process_files_with_prefix(self, client, mock_all_services):
        """Test batch processing with prefix filter."""
        from app.models.schemas import S3FileMetadata

        mock_files = [
            S3FileMetadata(
                key="specific_folder/file1.pdf",
                size=1024,
                last_modified=datetime.now(timezone.utc),
                etag="abc123"
            ),
        ]
        mock_all_services["s3"].list_files_by_date_range.return_value = mock_files
        mock_all_services["s3"].download_file.return_value = b"test content"

        start_date = datetime.now(timezone.utc) - timedelta(days=1)
        end_date = datetime.now(timezone.utc)

        response = client.post(
            "/process",
            json={
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "prefix": "specific_folder/"
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total_files"] == 1

        # Verify prefix was passed to S3 service
        mock_all_services["s3"].list_files_by_date_range.assert_called_once()
        call_args = mock_all_services["s3"].list_files_by_date_range.call_args
        assert call_args.kwargs.get("prefix") == "specific_folder/"

    def test_process_files_partial_failure(self, client, mock_all_services):
        """Test batch processing with fail-fast on first error."""
        from app.models.schemas import S3FileMetadata

        # Mock S3 to return multiple files
        mock_files = [
            S3FileMetadata(
                key="uploads/file1.pdf",
                size=1024,
                last_modified=datetime.now(timezone.utc),
                etag="abc123"
            ),
            S3FileMetadata(
                key="uploads/file2.pdf",
                size=2048,
                last_modified=datetime.now(timezone.utc),
                etag="def456"
            ),
        ]
        mock_all_services["s3"].list_files_by_date_range.return_value = mock_files

        # First call succeeds, second call fails
        mock_all_services["s3"].download_file.side_effect = [
            b"test content 1",
            Exception("Download failed for file 2")
        ]

        start_date = datetime.now(timezone.utc) - timedelta(days=1)
        end_date = datetime.now(timezone.utc)

        response = client.post(
            "/process",
            json={
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            }
        )

        # Should fail with 500 due to fail-fast behavior
        assert response.status_code == 500

    def test_process_files_p7m_creation_failure(self, client, mock_all_services):
        """Test batch processing fails when P7M creation fails."""
        from app.models.schemas import S3FileMetadata

        mock_files = [
            S3FileMetadata(
                key="uploads/file1.pdf",
                size=1024,
                last_modified=datetime.now(timezone.utc),
                etag="abc123"
            ),
        ]
        mock_all_services["s3"].list_files_by_date_range.return_value = mock_files
        mock_all_services["s3"].download_file.return_value = b"test content"

        # Mock signature service to return response without P7M content
        mock_response = SignatureResponse(
            signature="test_signature",
            timestamp=datetime.now(timezone.utc),
            p7m_content=None  # Missing P7M content
        )
        mock_all_services["signature"].sign_file_hash.return_value = mock_response

        start_date = datetime.now(timezone.utc) - timedelta(days=1)
        end_date = datetime.now(timezone.utc)

        response = client.post(
            "/process",
            json={
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            }
        )

        # Should fail because P7M content is required
        assert response.status_code == 500

    def test_invalid_date_range(self, client, mock_all_services):
        """Test batch processing with invalid date format."""
        response = client.post(
            "/process",
            json={
                "start_date": "invalid-date",
                "end_date": "2024-01-01T00:00:00Z",
            }
        )

        assert response.status_code == 422  # Validation error

    def test_root_endpoint(self, client):
        """Test root endpoint."""
        response = client.get("/")

        assert response.status_code == 200
        data = response.json()
        assert "service" in data
        assert "version" in data
        assert "status" in data
        assert data["status"] == "running"

    def test_p7m_file_naming(self, client, mock_all_services):
        """Test that P7M files are named correctly."""
        mock_all_services["s3"].download_file.return_value = b"test file content"

        response = client.post(
            "/recertify",
            json={"file_key": "uploads/important_document.pdf"}
        )

        assert response.status_code == 200
        data = response.json()

        # P7M file should be in signed/ folder with .p7m extension
        assert data["p7m_file_key"].startswith("signed/")
        assert data["p7m_file_key"].endswith(".p7m")
        assert "important_document.pdf" in data["p7m_file_key"]

    def test_dynamodb_save_called(self, client, mock_all_services):
        """Test that certification metadata is saved to DynamoDB."""
        mock_all_services["s3"].download_file.return_value = b"test file content"

        response = client.post(
            "/recertify",
            json={"file_key": "uploads/test.pdf"}
        )

        assert response.status_code == 200

        # Verify DynamoDB save was called
        mock_all_services["dynamodb"].save_certification.assert_called_once()

        # Verify the call had correct parameters
        call_args = mock_all_services["dynamodb"].save_certification.call_args
        assert call_args.kwargs["file_key"] == "uploads/test.pdf"
        assert call_args.kwargs["status"] == "completed"
