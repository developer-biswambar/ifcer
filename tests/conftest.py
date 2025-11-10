"""Shared test fixtures for IFCER Batch Service tests."""

import pytest
from datetime import datetime, timezone
from unittest.mock import Mock, MagicMock, patch
from typing import Generator, Dict, Any
import boto3
from moto import mock_s3, mock_dynamodb
from fastapi.testclient import TestClient

from app.config import Settings
from app.models.schemas import SignatureResponse


# ============================================================================
# Configuration Fixtures
# ============================================================================

@pytest.fixture
def test_settings() -> Settings:
    """Create test settings with safe defaults."""
    return Settings(
        app_name="IFCER Batch Service Test",
        aws_region="eu-south-1",
        s3_bucket_name="test-bucket",
        dynamodb_table_name="test-certifications",
        vendor_api_url="https://test.infocert.it/api",
        infocert_credential_id="test-credential-id",
        vendor_mtls_cert_s3_key="certs/test_cert.pem",
        vendor_mtls_key_s3_key="certs/test_key.pem",
        vendor_mtls_ca_s3_key="certs/test_ca.pem",
        hash_algorithm="sha256",
        batch_size=10,
        request_timeout=30,
        log_level="INFO",
        aws_endpoint_url=None,
        aws_access_key_id=None,
        aws_secret_access_key=None,
    )


@pytest.fixture
def mock_settings(test_settings: Settings) -> Generator[Settings, None, None]:
    """Mock the settings module to use test settings."""
    with patch("app.config.settings", test_settings):
        yield test_settings


# ============================================================================
# AWS Mocking Fixtures
# ============================================================================

@pytest.fixture
def aws_credentials():
    """Mocked AWS Credentials for moto."""
    import os
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_SECURITY_TOKEN"] = "testing"
    os.environ["AWS_SESSION_TOKEN"] = "testing"
    os.environ["AWS_DEFAULT_REGION"] = "eu-south-1"


@pytest.fixture
def s3_mock(aws_credentials):
    """Create a mocked S3 service."""
    with mock_s3():
        yield boto3.client("s3", region_name="eu-south-1")


@pytest.fixture
def dynamodb_mock(aws_credentials):
    """Create a mocked DynamoDB service."""
    with mock_dynamodb():
        yield boto3.resource("dynamodb", region_name="eu-south-1")


@pytest.fixture
def s3_bucket(s3_mock, test_settings: Settings):
    """Create a test S3 bucket with sample files."""
    bucket_name = test_settings.s3_bucket_name

    # Create bucket
    s3_mock.create_bucket(
        Bucket=bucket_name,
        CreateBucketConfiguration={"LocationConstraint": "eu-south-1"}
    )

    # Upload test files
    test_files = {
        "uploads/test_file_1.pdf": b"Test PDF content 1",
        "uploads/test_file_2.pdf": b"Test PDF content 2",
        "uploads/test_file_3.xml": b"<xml>Test XML content</xml>",
        "certs/test_cert.pem": b"-----BEGIN CERTIFICATE-----\ntest\n-----END CERTIFICATE-----",
        "certs/test_key.pem": b"-----BEGIN PRIVATE KEY-----\ntest\n-----END PRIVATE KEY-----",
        "certs/test_ca.pem": b"-----BEGIN CERTIFICATE-----\ntest_ca\n-----END CERTIFICATE-----",
    }

    for key, content in test_files.items():
        s3_mock.put_object(
            Bucket=bucket_name,
            Key=key,
            Body=content
        )

    yield s3_mock, bucket_name


@pytest.fixture
def dynamodb_table(dynamodb_mock, test_settings: Settings):
    """Create a test DynamoDB table with GSI indexes."""
    table_name = test_settings.dynamodb_table_name

    # Create table with sort key and GSI indexes
    table = dynamodb_mock.create_table(
        TableName=table_name,
        KeySchema=[
            {"AttributeName": "file_key", "KeyType": "HASH"},
            {"AttributeName": "processing_timestamp", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "file_key", "AttributeType": "S"},
            {"AttributeName": "processing_timestamp", "AttributeType": "S"},
            {"AttributeName": "filename", "AttributeType": "S"},
            {"AttributeName": "date_partition", "AttributeType": "S"},
        ],
        GlobalSecondaryIndexes=[
            {
                "IndexName": "filename-index",
                "KeySchema": [
                    {"AttributeName": "filename", "KeyType": "HASH"},
                    {"AttributeName": "processing_timestamp", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            },
            {
                "IndexName": "date-index",
                "KeySchema": [
                    {"AttributeName": "date_partition", "KeyType": "HASH"},
                    {"AttributeName": "processing_timestamp", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            },
        ],
        BillingMode="PAY_PER_REQUEST",
    )

    # Wait for table to be created
    table.meta.client.get_waiter("table_exists").wait(TableName=table_name)

    yield table


# ============================================================================
# Service Mocking Fixtures
# ============================================================================

@pytest.fixture
def mock_signature_service():
    """Create a mocked SignatureService."""
    mock_service = Mock()

    # Default successful signature response
    mock_service.sign_file_hash.return_value = SignatureResponse(
        signature="mock_signature_base64",
        timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        p7m_content=b"mock_p7m_content",
    )

    # Default successful health check
    mock_service.health_check.return_value = True

    return mock_service


@pytest.fixture
def mock_s3_service():
    """Create a mocked S3Service."""
    mock_service = Mock()

    # Default successful operations
    mock_service.check_bucket_access.return_value = True
    mock_service.download_file.return_value = b"test_file_content"
    mock_service.upload_file.return_value = None
    mock_service.list_files_by_date_range.return_value = []

    return mock_service


@pytest.fixture
def mock_dynamodb_service():
    """Create a mocked DynamoDBService."""
    mock_service = Mock()

    # Default successful operations
    mock_service.save_certification.return_value = None
    mock_service.get_certification.return_value = {
        "file_key": "test.pdf",
        "file_hash": "mock_hash",
        "hash_algorithm": "sha256",
        "digital_signature": "mock_signature",
        "vendor_timestamp": "2024-01-01T12:00:00+00:00",
        "processing_timestamp": "2024-01-01T12:00:01+00:00",
        "signed_file_key": "signed/test.pdf.p7m",
        "file_size": 1024,
        "signed_file_size": 2048,
        "status": "completed",
    }

    return mock_service


@pytest.fixture
def mock_hash_service():
    """Create a mocked HashService."""
    from app.models.schemas import HashInfo

    mock_service = Mock()
    mock_service.compute_hash.return_value = HashInfo(
        hash_value="mock_hash_value_1234567890abcdef",
        hash_algorithm="sha256",
        file_key="test.pdf",
        file_size=1024,
    )

    return mock_service


# ============================================================================
# HTTP Mocking Fixtures
# ============================================================================

@pytest.fixture
def mock_requests():
    """Create a mocked requests library for InfoCert API calls."""
    with patch("requests.post") as mock_post:
        # Default successful response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "signature": "mock_signature_base64",
            "timestamp": "2024-01-01T12:00:00Z",
            "status": "success",
        }
        mock_response.content = b"mock_p7m_content"

        mock_post.return_value = mock_response
        yield mock_post


# ============================================================================
# FastAPI Test Client Fixtures
# ============================================================================

@pytest.fixture
def test_client(mock_settings: Settings) -> TestClient:
    """Create a test client for the FastAPI app."""
    from app.main import app
    return TestClient(app)


@pytest.fixture
def authenticated_client(test_client: TestClient) -> TestClient:
    """Create an authenticated test client (if auth is added later)."""
    # For now, returns the same client
    # In future, can add authentication headers
    return test_client


# ============================================================================
# Test Data Fixtures
# ============================================================================

@pytest.fixture
def sample_file_content() -> bytes:
    """Sample file content for testing."""
    return b"Sample PDF file content for testing"


@pytest.fixture
def sample_hash() -> str:
    """Sample hash value for testing."""
    return "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


@pytest.fixture
def sample_signature_response() -> SignatureResponse:
    """Sample signature response from InfoCert."""
    return SignatureResponse(
        signature="bW9ja19zaWduYXR1cmVfYmFzZTY0X2VuY29kZWQ=",
        timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        p7m_content=b"mock_p7m_file_content_with_signature",
    )


@pytest.fixture
def sample_certification_data() -> Dict[str, Any]:
    """Sample certification data for DynamoDB."""
    return {
        "file_key": "uploads/test_document.pdf",
        "file_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "hash_algorithm": "sha256",
        "digital_signature": "bW9ja19zaWduYXR1cmU=",
        "vendor_timestamp": "2024-01-01T12:00:00+00:00",
        "processing_timestamp": "2024-01-01T12:00:01+00:00",
        "signed_file_key": "signed/test_document.pdf.p7m",
        "file_size": 10240,
        "signed_file_size": 15360,
        "status": "completed",
    }


# ============================================================================
# Helper Functions
# ============================================================================

@pytest.fixture
def freeze_time():
    """Fixture to freeze time for consistent testing."""
    frozen_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    with patch("app.routers.processing.datetime") as mock_datetime:
        mock_datetime.now.return_value = frozen_time
        mock_datetime.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)
        yield frozen_time
