"""Unit tests for SignatureService."""

import pytest
import base64
import json
from datetime import datetime, timezone
from unittest.mock import patch, Mock, MagicMock
from requests.exceptions import RequestException, Timeout, SSLError

from app.services.signature_service import SignatureService
from app.models.schemas import SignatureRequest, SignatureResponse


@pytest.mark.unit
@pytest.mark.service
class TestSignatureService:
    """Test suite for SignatureService."""

    @pytest.fixture
    def mock_s3_cert_download(self, s3_bucket):
        """Mock S3 certificate downloads."""
        s3_mock, bucket_name = s3_bucket
        return s3_mock

    @pytest.fixture
    def mock_infocert_response(self):
        """Create a mock InfoCert API response."""
        return {
            "signatureValue": base64.b64encode(b"mock_signature_bytes").decode(),
            "signingCertificate": base64.b64encode(b"mock_certificate_bytes").decode(),
            "signingTime": "2024-01-01T12:00:00Z",
        }

    def test_init_success(self, test_settings, s3_bucket):
        """Test successful SignatureService initialization."""
        s3_mock, bucket_name = s3_bucket

        with patch("app.config.settings", test_settings):
            with patch("boto3.client", return_value=s3_mock):
                service = SignatureService()

                assert service.api_url == test_settings.vendor_api_url
                assert service.timeout == test_settings.request_timeout
                assert service.cert_path is not None
                assert service.key_path is not None

    def test_init_missing_cert(self, test_settings, s3_bucket):
        """Test initialization failure when certificate is missing."""
        s3_mock, bucket_name = s3_bucket

        # Delete the certificate file
        s3_mock.delete_object(Bucket=bucket_name, Key="certs/test_cert.pem")

        with patch("app.config.settings", test_settings):
            with patch("boto3.client", return_value=s3_mock):
                with pytest.raises(Exception):
                    SignatureService()

    def test_sign_file_hash_success(self, test_settings, s3_bucket, mock_infocert_response):
        """Test successful file hash signing."""
        s3_mock, bucket_name = s3_bucket

        with patch("app.config.settings", test_settings):
            with patch("boto3.client", return_value=s3_mock):
                service = SignatureService()

                # Mock the HTTP session
                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.json.return_value = mock_infocert_response

                with patch.object(service, '_create_session') as mock_session_creator:
                    mock_session = Mock()
                    mock_session.post.return_value = mock_response
                    mock_session_creator.return_value = mock_session

                    # Create test request
                    request = SignatureRequest(
                        file_hash="abc123def456",
                        hash_algorithm="sha256",
                        filename="test.pdf",
                    )

                    # Sign the file hash
                    response = service.sign_file_hash(request)

                    # Verify response
                    assert isinstance(response, SignatureResponse)
                    assert response.signature == mock_infocert_response["signatureValue"]
                    assert response.p7m_content is not None
                    assert len(response.p7m_content) > 0

    def test_sign_file_hash_api_timeout(self, test_settings, s3_bucket):
        """Test handling of API timeout."""
        s3_mock, bucket_name = s3_bucket

        with patch("app.config.settings", test_settings):
            with patch("boto3.client", return_value=s3_mock):
                service = SignatureService()

                # Mock session to raise timeout
                with patch.object(service, '_create_session') as mock_session_creator:
                    mock_session = Mock()
                    mock_session.post.side_effect = Timeout("Connection timed out")
                    mock_session_creator.return_value = mock_session

                    request = SignatureRequest(
                        file_hash="abc123",
                        hash_algorithm="sha256",
                        filename="test.pdf",
                    )

                    with pytest.raises(Timeout):
                        service.sign_file_hash(request)

    def test_sign_file_hash_ssl_error(self, test_settings, s3_bucket):
        """Test handling of SSL/mTLS errors."""
        s3_mock, bucket_name = s3_bucket

        with patch("app.config.settings", test_settings):
            with patch("boto3.client", return_value=s3_mock):
                service = SignatureService()

                # Mock session to raise SSL error
                with patch.object(service, '_create_session') as mock_session_creator:
                    mock_session = Mock()
                    mock_session.post.side_effect = SSLError("SSL certificate verification failed")
                    mock_session_creator.return_value = mock_session

                    request = SignatureRequest(
                        file_hash="abc123",
                        hash_algorithm="sha256",
                        filename="test.pdf",
                    )

                    with pytest.raises(SSLError):
                        service.sign_file_hash(request)

    def test_sign_file_hash_missing_signature_value(self, test_settings, s3_bucket):
        """Test handling when API doesn't return signature value."""
        s3_mock, bucket_name = s3_bucket

        with patch("app.config.settings", test_settings):
            with patch("boto3.client", return_value=s3_mock):
                service = SignatureService()

                # Mock response without signatureValue
                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.json.return_value = {
                    "signingCertificate": "cert_data",
                    "signingTime": "2024-01-01T12:00:00Z",
                }

                with patch.object(service, '_create_session') as mock_session_creator:
                    mock_session = Mock()
                    mock_session.post.return_value = mock_response
                    mock_session_creator.return_value = mock_session

                    request = SignatureRequest(
                        file_hash="abc123",
                        hash_algorithm="sha256",
                        filename="test.pdf",
                    )

                    with pytest.raises(ValueError, match="signature value"):
                        service.sign_file_hash(request)

    def test_sign_file_hash_missing_certificate(self, test_settings, s3_bucket):
        """Test handling when API doesn't return certificate."""
        s3_mock, bucket_name = s3_bucket

        with patch("app.config.settings", test_settings):
            with patch("boto3.client", return_value=s3_mock):
                service = SignatureService()

                # Mock response without signingCertificate
                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.json.return_value = {
                    "signatureValue": "signature_data",
                    "signingTime": "2024-01-01T12:00:00Z",
                }

                with patch.object(service, '_create_session') as mock_session_creator:
                    mock_session = Mock()
                    mock_session.post.return_value = mock_response
                    mock_session_creator.return_value = mock_session

                    request = SignatureRequest(
                        file_hash="abc123",
                        hash_algorithm="sha256",
                        filename="test.pdf",
                    )

                    with pytest.raises(ValueError, match="certificate"):
                        service.sign_file_hash(request)

    def test_manifest_creation(self, test_settings, s3_bucket, mock_infocert_response):
        """Test that manifest is created with correct structure."""
        s3_mock, bucket_name = s3_bucket

        with patch("app.config.settings", test_settings):
            with patch("boto3.client", return_value=s3_mock):
                service = SignatureService()

                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.json.return_value = mock_infocert_response

                captured_payload = None

                def capture_post(url, json=None, **kwargs):
                    nonlocal captured_payload
                    captured_payload = json
                    return mock_response

                with patch.object(service, '_create_session') as mock_session_creator:
                    mock_session = Mock()
                    mock_session.post = capture_post
                    mock_session_creator.return_value = mock_session

                    request = SignatureRequest(
                        file_hash="test_hash_value",
                        hash_algorithm="sha256",
                        filename="document.pdf",
                    )

                    service.sign_file_hash(request)

                    # Verify manifest was created correctly
                    assert captured_payload is not None
                    assert "signRequest" in captured_payload
                    assert "inputDocuments" in captured_payload["signRequest"]

                    # Decode the base64 manifest
                    manifest_b64 = captured_payload["signRequest"]["inputDocuments"][0]["content"]
                    manifest_json = base64.b64decode(manifest_b64).decode('utf-8')
                    manifest = json.loads(manifest_json)

                    assert manifest["fileName"] == "document.pdf"
                    assert manifest["hash"] == "test_hash_value"
                    assert manifest["algorithm"] == "SHA256"
                    assert "timestamp" in manifest

    def test_health_check_success(self, test_settings, s3_bucket):
        """Test successful health check."""
        s3_mock, bucket_name = s3_bucket

        with patch("app.config.settings", test_settings):
            with patch("boto3.client", return_value=s3_mock):
                service = SignatureService()

                # Mock successful health check response
                mock_response = Mock()
                mock_response.status_code = 200

                with patch.object(service, '_create_session') as mock_session_creator:
                    mock_session = Mock()
                    mock_session.get.return_value = mock_response
                    mock_session_creator.return_value = mock_session

                    result = service.health_check()
                    assert result is True

    def test_health_check_failure(self, test_settings, s3_bucket):
        """Test failed health check."""
        s3_mock, bucket_name = s3_bucket

        with patch("app.config.settings", test_settings):
            with patch("boto3.client", return_value=s3_mock):
                service = SignatureService()

                # Mock failed health check
                with patch.object(service, '_create_session') as mock_session_creator:
                    mock_session = Mock()
                    mock_session.get.side_effect = RequestException("Connection failed")
                    mock_session_creator.return_value = mock_session

                    result = service.health_check()
                    assert result is False

    def test_hash_algorithm_sha256(self, test_settings, s3_bucket):
        """Test hash algorithm handling for SHA256."""
        s3_mock, bucket_name = s3_bucket

        with patch("app.config.settings", test_settings):
            with patch("boto3.client", return_value=s3_mock):
                service = SignatureService()

                # SHA256 should work
                oid = service._get_hash_algorithm_oid("sha256")
                assert oid is not None

    def test_hash_algorithm_sha512(self, test_settings, s3_bucket):
        """Test hash algorithm handling for SHA512."""
        s3_mock, bucket_name = s3_bucket

        with patch("app.config.settings", test_settings):
            with patch("boto3.client", return_value=s3_mock):
                service = SignatureService()

                # SHA512 should work
                oid = service._get_hash_algorithm_oid("sha512")
                assert oid is not None

    def test_hash_algorithm_unsupported(self, test_settings, s3_bucket):
        """Test unsupported hash algorithm."""
        s3_mock, bucket_name = s3_bucket

        with patch("app.config.settings", test_settings):
            with patch("boto3.client", return_value=s3_mock):
                service = SignatureService()

                with pytest.raises(ValueError, match="Unsupported hash algorithm"):
                    service._get_hash_algorithm_oid("unsupported")

    def test_p7m_creation(self, test_settings, s3_bucket):
        """Test P7M file creation."""
        s3_mock, bucket_name = s3_bucket

        with patch("app.config.settings", test_settings):
            with patch("boto3.client", return_value=s3_mock):
                service = SignatureService()

                # Create test data
                content = b"Test manifest content"
                signature = b"mock_signature_bytes"
                certificate = b"mock_certificate_bytes"

                # Create P7M
                p7m_bytes = service._create_p7m_from_signature(
                    content,
                    signature,
                    certificate
                )

                # Verify P7M was created
                assert p7m_bytes is not None
                assert len(p7m_bytes) > 0
                assert isinstance(p7m_bytes, bytes)

    def test_session_creation(self, test_settings, s3_bucket):
        """Test mTLS session creation."""
        s3_mock, bucket_name = s3_bucket

        with patch("app.config.settings", test_settings):
            with patch("boto3.client", return_value=s3_mock):
                service = SignatureService()

                session = service._create_session()

                assert session is not None
                assert session.cert is not None
                # Should be tuple of (cert_path, key_path)
                assert len(session.cert) == 2
