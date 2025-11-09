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
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from asn1crypto import cms, core, algos, x509 as asn1_x509
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

            # InfoCert returns signature and certificate (not complete P7M)
            # We need to create the P7M ourselves
            signature_value_b64 = response_data.get("signatureValue", "")
            signing_cert_b64 = response_data.get("signingCertificate", "")
            signing_time = response_data.get("signingTime", datetime.now(timezone.utc).isoformat())

            if not signature_value_b64:
                raise ValueError("InfoCert API did not return signature value")

            if not signing_cert_b64:
                raise ValueError("InfoCert API did not return signing certificate")

            # Decode signature and certificate
            signature_bytes = base64.b64decode(signature_value_b64)
            cert_bytes = base64.b64decode(signing_cert_b64)

            # Create P7M file from manifest, signature, and certificate
            p7m_bytes = self._create_p7m_from_signature(
                manifest_json.encode('utf-8'),
                signature_bytes,
                cert_bytes
            )

            # Encode P7M to base64 for consistent handling
            p7m_content_b64 = base64.b64encode(p7m_bytes).decode('ascii')

            signature_response = SignatureResponse(
                signature=signature_value_b64,
                timestamp=datetime.fromisoformat(signing_time.replace("Z", "+00:00")),
                p7m_content=p7m_content_b64,  # Base64 encoded P7M we created
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

    def _create_p7m_from_signature(
        self, manifest_content: bytes, signature_bytes: bytes, cert_der_bytes: bytes
    ) -> bytes:
        """
        Create a P7M (PKCS#7/CAdES) file from manifest content, signature, and certificate.

        This creates a CAdES-BES (Basic Electronic Signature) structure which is
        a PKCS#7 SignedData containing the signed manifest.

        Args:
            manifest_content: The manifest JSON as bytes
            signature_bytes: The signature bytes from InfoCert
            cert_der_bytes: The DER-encoded signing certificate from InfoCert

        Returns:
            Complete P7M file as bytes (DER-encoded PKCS#7 SignedData)

        Raises:
            ValueError: If P7M creation fails
        """
        try:
            logger.debug("Creating P7M/CAdES structure from signature")

            # Parse the certificate
            cert = asn1_x509.Certificate.load(cert_der_bytes)

            # Create ContentInfo for the manifest (encapContentInfo)
            content_type = cms.ContentType('data')
            encap_content_info = cms.ContentInfo({
                'content_type': content_type,
                'content': core.PrimitiveBitString(manifest_content)
            })

            # Get certificate hash for signer identifier
            # For CAdES, we use IssuerAndSerialNumber
            issuer = cert['tbs_certificate']['issuer']
            serial_number = cert['tbs_certificate']['serial_number']

            signer_identifier = cms.SignerIdentifier(
                name='issuer_and_serial_number',
                value=cms.IssuerAndSerialNumber({
                    'issuer': issuer,
                    'serial_number': serial_number
                })
            )

            # SHA-256 digest algorithm (used for hashing the manifest)
            digest_algorithm = algos.DigestAlgorithm({
                'algorithm': '2.16.840.1.101.3.4.2.1'  # SHA-256 OID
            })

            # RSA with SHA-256 signature algorithm (typical for InfoCert)
            signature_algorithm = algos.SignedDigestAlgorithm({
                'algorithm': '1.2.840.113549.1.1.11'  # sha256WithRSAEncryption OID
            })

            # Create SignerInfo
            signer_info = cms.SignerInfo({
                'version': 'v1',
                'sid': signer_identifier,
                'digest_algorithm': digest_algorithm,
                'signature_algorithm': signature_algorithm,
                'signature': core.OctetString(signature_bytes)
            })

            # Create SignedData
            signed_data = cms.SignedData({
                'version': 'v1',
                'digest_algorithms': cms.DigestAlgorithms([digest_algorithm]),
                'encap_content_info': encap_content_info,
                'certificates': cms.CertificateSet([
                    cms.CertificateChoices(name='certificate', value=cert)
                ]),
                'signer_infos': cms.SignerInfos([signer_info])
            })

            # Wrap in ContentInfo
            content_info = cms.ContentInfo({
                'content_type': cms.ContentType('signed_data'),
                'content': signed_data
            })

            # Encode to DER (this is the P7M file)
            p7m_bytes = content_info.dump()

            logger.info(f"Successfully created P7M file: {len(p7m_bytes)} bytes")
            return p7m_bytes

        except Exception as e:
            log_exception(logger, e, "Failed to create P7M file from signature")
            raise ValueError(f"P7M creation failed: {str(e)}")

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
