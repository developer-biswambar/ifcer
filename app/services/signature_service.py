"""Signature service for vendor API integration with mTLS authentication."""

import requests
from requests.exceptions import RequestException, Timeout, SSLError
from typing import Optional
from datetime import datetime
import tempfile
import os
import boto3
from app.config import settings
from app.models.schemas import SignatureRequest, SignatureResponse
from app.utils.logger import setup_logger, log_exception

logger = setup_logger(__name__)


class SignatureService:
    """Service for interacting with vendor API using mTLS authentication."""

    def __init__(self):
        """Initialize signature service with mTLS configuration loaded from S3."""
        self.api_url = settings.vendor_api_url
        self.timeout = settings.request_timeout

        # Download mTLS certificates from S3 and store as temporary files
        logger.info(f"Loading mTLS certificates from S3 bucket: {settings.s3_bucket_name}")

        try:
            s3_client = boto3.client("s3", region_name=settings.aws_region)

            # Download client certificate
            cert_content = self._download_from_s3(s3_client, settings.vendor_mtls_cert_s3_key)
            self.cert_path = self._write_temp_file(cert_content, suffix=".pem", prefix="client_cert_")
            logger.info(f"Client certificate downloaded from s3://{settings.s3_bucket_name}/{settings.vendor_mtls_cert_s3_key}")

            # Download client key
            key_content = self._download_from_s3(s3_client, settings.vendor_mtls_key_s3_key)
            self.key_path = self._write_temp_file(key_content, suffix=".pem", prefix="client_key_")
            logger.info(f"Client key downloaded from s3://{settings.s3_bucket_name}/{settings.vendor_mtls_key_s3_key}")

            # Download CA bundle (optional)
            if settings.vendor_mtls_ca_s3_key:
                ca_content = self._download_from_s3(s3_client, settings.vendor_mtls_ca_s3_key)
                self.ca_path = self._write_temp_file(ca_content, suffix=".pem", prefix="ca_bundle_")
                logger.info(f"CA bundle downloaded from s3://{settings.s3_bucket_name}/{settings.vendor_mtls_ca_s3_key}")
            else:
                self.ca_path = None
                logger.info("No CA bundle configured, using default SSL verification")

            logger.info(f"Signature service initialized for API: {self.api_url}")

        except Exception as e:
            log_exception(logger, e, "Failed to initialize signature service with S3 certificates")
            raise

    def _download_from_s3(self, s3_client, s3_key: str) -> bytes:
        """Download file content from S3."""
        try:
            response = s3_client.get_object(Bucket=settings.s3_bucket_name, Key=s3_key)
            return response["Body"].read()
        except Exception as e:
            log_exception(logger, e, f"Failed to download {s3_key} from S3")
            raise

    def _write_temp_file(self, content: bytes, suffix: str, prefix: str) -> str:
        """Write content to a temporary file and return the path."""
        try:
            # Create a temporary file that persists (delete=False)
            temp_file = tempfile.NamedTemporaryFile(mode='wb', suffix=suffix, prefix=prefix, delete=False)
            temp_file.write(content)
            temp_file.close()

            # Set file permissions to read-only for security
            os.chmod(temp_file.name, 0o400)

            logger.debug(f"Created temporary file: {temp_file.name}")
            return temp_file.name
        except Exception as e:
            log_exception(logger, e, "Failed to create temporary file")
            raise

    def _create_session(self) -> requests.Session:
        """
        Create requests session with mTLS configuration.

        Returns:
            Configured requests.Session object
        """
        session = requests.Session()

        # Configure mTLS authentication
        session.cert = (self.cert_path, self.key_path)

        # Configure CA bundle if provided
        if self.ca_path:
            session.verify = self.ca_path
        else:
            # Use default SSL verification
            session.verify = True

        return session

    def sign_file_hash(self, signature_request: SignatureRequest) -> SignatureResponse:
        """
        Send file hash to vendor API for digital signature and timestamp.

        Args:
            signature_request: SignatureRequest object with file hash details

        Returns:
            SignatureResponse with signature and timestamp

        Raises:
            RequestException: If API request fails
            SSLError: If mTLS authentication fails
            Timeout: If request times out
        """
        try:
            logger.info(
                f"Requesting signature for file: {signature_request.filename}"
            )
            logger.debug(
                f"Hash: {signature_request.file_hash[:16]}... Algorithm: {signature_request.hash_algorithm}"
            )

            # Create session with mTLS
            session = self._create_session()

            # Prepare request payload
            # Note: This is a placeholder structure. Adjust based on actual vendor API specification
            payload = {
                "file_hash": signature_request.file_hash,
                "hash_algorithm": signature_request.hash_algorithm,
                "filename": signature_request.filename,
            }

            # Make API request
            response = session.post(
                f"{self.api_url}/sign",  # Adjust endpoint as per vendor specification
                json=payload,
                timeout=self.timeout,
            )

            # Check response status
            response.raise_for_status()

            # Parse response
            # Note: This is a placeholder structure. Adjust based on actual vendor API response format
            response_data = response.json()

            signature_response = SignatureResponse(
                signature=response_data.get("signature"),
                timestamp=response_data.get("timestamp", datetime.utcnow()),
                p7m_content=response_data.get("p7m_content"),  # May be base64 encoded
            )

            logger.info(
                f"Successfully received signature for: {signature_request.filename}"
            )
            logger.debug(f"Signature timestamp: {signature_response.timestamp}")

            return signature_response

        except SSLError as e:
            log_exception(
                logger,
                e,
                f"mTLS authentication failed for: {signature_request.filename}",
            )
            raise
        except Timeout as e:
            log_exception(
                logger,
                e,
                f"Request timeout for: {signature_request.filename}",
            )
            raise
        except RequestException as e:
            log_exception(
                logger,
                e,
                f"API request failed for: {signature_request.filename}",
            )
            raise
        except Exception as e:
            log_exception(
                logger,
                e,
                f"Unexpected error signing file: {signature_request.filename}",
            )
            raise

    def create_p7m_file(
        self, original_content: bytes, signature: str, timestamp: datetime
    ) -> bytes:
        """
        Create P7M (PKCS#7) file for Italian register submission.

        Note: This is a placeholder implementation. The actual P7M file creation
        may be done by the vendor API and returned in the response, or you may need
        to use a library like pyOpenSSL or cryptography to create it locally.

        Args:
            original_content: Original file content
            signature: Digital signature from vendor
            timestamp: Timestamp from vendor

        Returns:
            P7M file content as bytes

        Raises:
            NotImplementedError: If P7M creation logic is not yet implemented
        """
        # TODO: Implement actual P7M file creation based on vendor specifications
        # This may involve:
        # 1. Using the signature and timestamp from the vendor
        # 2. Creating a PKCS#7 container with the signature
        # 3. Formatting it according to Italian register requirements

        logger.warning("P7M file creation is not yet fully implemented")
        raise NotImplementedError(
            "P7M file creation logic needs to be implemented based on vendor specifications"
        )

    def health_check(self) -> bool:
        """
        Check if vendor API is accessible with mTLS authentication.

        Returns:
            True if API is accessible

        Raises:
            RequestException: If health check fails
        """
        try:
            logger.info("Performing vendor API health check")

            session = self._create_session()

            # Adjust endpoint as per vendor specification
            response = session.get(
                f"{self.api_url}/health",
                timeout=self.timeout,
            )

            response.raise_for_status()

            logger.info("Vendor API health check successful")
            return True

        except Exception as e:
            log_exception(logger, e, "Vendor API health check failed")
            raise
