"""Signature service for InfoCert API integration with mTLS authentication.

This service implements a MANIFEST-BASED approach for qualified digital signatures,
compliant with Italian eIDAS and AgID standards. The workflow:

1. Compute SHA-256 hash of the original document
2. Create a manifest JSON file containing: fileName, hash, algorithm, timestamp
3. Base64 encode the manifest
4. Send manifest to InfoCert Sign API with mTLS authentication
5. InfoCert signs the manifest using qualified certificates
6. InfoCert returns a CAdES-BES/CAdES-BASELINE-B signature (P7M of manifest)
7. Store original file + signed manifest P7M for Italian register submission

The P7M file contains the SIGNED MANIFEST (not the original file).
The manifest's hash field proves the integrity of the original file.

Reference: https://developers.infocert.digital/e-signature-and-e-sealing/
"""

import base64
import json
import requests
from requests.exceptions import RequestException, Timeout, SSLError
from typing import Optional
from datetime import datetime, timezone
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

    def _get_hash_algorithm_oid(self, algorithm: str) -> str:
        """
        Get the OID (Object Identifier) for a hash algorithm.

        InfoCert API requires hash algorithms to be specified as OIDs.

        Args:
            algorithm: Hash algorithm name (e.g., 'sha256', 'sha512')

        Returns:
            OID string for the hash algorithm

        Raises:
            ValueError: If algorithm is not supported
        """
        oid_mapping = {
            "sha1": "1.3.14.3.2.26",
            "sha256": "2.16.840.1.101.3.4.2.1",
            "sha384": "2.16.840.1.101.3.4.2.2",
            "sha512": "2.16.840.1.101.3.4.2.3",
            "sha224": "2.16.840.1.101.3.4.2.4",
        }

        algorithm_lower = algorithm.lower().replace("-", "")

        if algorithm_lower not in oid_mapping:
            raise ValueError(
                f"Unsupported hash algorithm: {algorithm}. "
                f"Supported algorithms: {', '.join(oid_mapping.keys())}"
            )

        return oid_mapping[algorithm_lower]

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
        Create and sign a manifest file containing the file hash using InfoCert API.

        This implements the manifest-based approach where:
        1. Create a manifest JSON containing file hash and metadata
        2. Base64 encode the manifest
        3. Send manifest to InfoCert for CAdES signing
        4. Receive signed P7M of the manifest (not the original file)

        The original file stays unchanged. The P7M contains the signed manifest,
        which proves the integrity of the original file through its hash.

        Args:
            signature_request: SignatureRequest object with file hash details

        Returns:
            SignatureResponse with signed manifest (P7M) and timestamp

        Raises:
            RequestException: If API request fails
            SSLError: If mTLS authentication fails
            Timeout: If request times out
        """
        try:
            logger.info(
                f"Creating and signing manifest for file: {signature_request.filename}"
            )
            logger.debug(
                f"Hash: {signature_request.file_hash[:16]}... Algorithm: {signature_request.hash_algorithm}"
            )

            # Step 1: Create manifest JSON
            manifest = {
                "fileName": signature_request.filename,
                "algorithm": signature_request.hash_algorithm.upper(),
                "hash": signature_request.file_hash,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

            # Convert manifest to JSON string
            manifest_json = json.dumps(manifest, indent=2)
            logger.debug(f"Created manifest: {manifest_json}")

            # Step 2: Base64 encode the manifest
            manifest_b64 = base64.b64encode(manifest_json.encode('utf-8')).decode('ascii')

            # Step 3: Create session with mTLS
            session = self._create_session()

            # Step 4: Prepare request payload for InfoCert Sign API
            # We're signing the MANIFEST, not just the hash
            payload = {
                "credentialID": settings.infocert_credential_id,
                "signRequest": {
                    "signFormat": "CAdES",  # CAdES format for P7M
                    "signatureLevel": "CAdES_BASELINE_B",  # CAdES-BES
                    "inputDocuments": [{
                        "contentType": "BASE64",
                        "content": manifest_b64
                    }]
                }
            }

            # Make API request to InfoCert Sign API
            response = session.post(
                f"{self.api_url}/sign/v2",  # InfoCert sign endpoint
                json=payload,
                timeout=self.timeout,
            )

            # Check response status
            response.raise_for_status()

            # Parse InfoCert response
            response_data = response.json()

            # InfoCert returns the signed document (P7M of manifest) in base64
            signed_manifest_b64 = response_data.get("signedDocuments", [{}])[0].get("content")
            signing_time = response_data.get("signingTime", datetime.now(timezone.utc).isoformat())

            if not signed_manifest_b64:
                raise ValueError("InfoCert API did not return signed document")

            signature_response = SignatureResponse(
                signature=response_data.get("signatureValue", ""),
                timestamp=datetime.fromisoformat(signing_time.replace("Z", "+00:00")),
                p7m_content=signed_manifest_b64,  # Base64 encoded P7M of manifest
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
        Decode and return the signed manifest P7M file from InfoCert.

        Manifest-based approach for Italian register submission:
        - The P7M contains a signed MANIFEST (not the original file)
        - The manifest is a JSON file containing: fileName, hash, algorithm, timestamp
        - The original file remains unchanged in S3
        - The P7M proves the integrity of the original file through its hash

        This approach is compliant with eIDAS regulations and AgID standards.

        Workflow:
        1. Create manifest JSON with file metadata and hash
        2. InfoCert signs the manifest using qualified certificate
        3. InfoCert creates a CAdES-BES/CAdES-BASELINE-B signature container
        4. InfoCert returns the complete P7M of the manifest

        Storage structure:
        - Original file: s3://bucket/documents/file.pdf
        - Signed manifest: s3://bucket/signed/file.pdf.p7m (contains signed manifest)

        Args:
            original_content: Original file content (not used in manifest-based approach)
            signature: Base64-encoded P7M content from InfoCert API (signed manifest)
            timestamp: Signing timestamp from InfoCert (for logging/metadata)

        Returns:
            P7M file content as bytes (decoded from base64) - signed manifest

        Raises:
            ValueError: If signature content is invalid or empty
        """
        if not signature:
            logger.error("Cannot create P7M file: signature content is empty")
            raise ValueError("Signature content (signedDocument) is required from InfoCert API")

        try:
            # Decode base64-encoded P7M content from InfoCert
            p7m_content = base64.b64decode(signature)

            logger.info(
                f"Successfully created P7M file: {len(p7m_content)} bytes, "
                f"signed at {timestamp.isoformat()}"
            )

            # Validate P7M content has proper PKCS#7 header
            if not p7m_content.startswith(b'\x30'):  # PKCS#7 structures start with 0x30 (SEQUENCE)
                logger.warning("P7M content may not be valid PKCS#7 format")

            return p7m_content

        except Exception as e:
            log_exception(logger, e, "Failed to decode P7M content from InfoCert response")
            raise ValueError(f"Invalid P7M content from InfoCert API: {str(e)}")

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
