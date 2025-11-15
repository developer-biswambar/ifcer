"""Certificate service for InfoCert API integration.

This service handles certificate-related operations including:
- Fetching certificates from InfoCert
- Retrieving active certificates
- Decoding certificate data
- Caching signing certificates to reduce API calls
"""

import base64
import tempfile
import os
import urllib3
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional

import boto3
import requests
from requests.exceptions import RequestException

from app.config import settings
from app.utils.logger import setup_logger, log_exception
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.serialization import pkcs12

logger = setup_logger(__name__)


class CertificateService:
    """Service for certificate operations with InfoCert API."""

    def __init__(self):
        """Initialize certificate service with mTLS configuration."""
        self.api_url = settings.infocert_api_url
        self.timeout = settings.request_timeout

        # Certificate caching
        self._cached_certificate_bytes: Optional[bytes] = None
        self._cache_expiry: Optional[datetime] = None
        self._cache_ttl_seconds = settings.certificate_cache_ttl_seconds

        # Download and setup mTLS certificates
        logger.info(f"Loading mTLS certificates from S3 bucket: {settings.s3_bucket_name}")
        self._setup_mtls_certificates()

        # Log cache configuration
        if self._cache_ttl_seconds > 0:
            logger.info(f"Certificate caching enabled with TTL: {self._cache_ttl_seconds}s ({self._cache_ttl_seconds/60:.1f} minutes)")
        else:
            logger.info("Certificate caching disabled (TTL=0)")

    def _setup_mtls_certificates(self):
        """Download mTLS certificates from S3 and store as temporary files."""
        try:
            logger.info(f"[MTLS SETUP] Starting mTLS certificate setup from S3")
            logger.info(f"[MTLS SETUP] S3 Bucket: {settings.s3_bucket_name}")
            logger.info(f"[MTLS SETUP] AWS Region: {settings.aws_region}")

            # Prepare boto3 client configuration
            client_config = {"region_name": settings.aws_region}

            if settings.aws_endpoint_url:
                client_config["endpoint_url"] = settings.aws_endpoint_url
                logger.info(f"[MTLS SETUP] Using custom endpoint: {settings.aws_endpoint_url}")

            if settings.aws_access_key_id and settings.aws_secret_access_key:
                client_config["aws_access_key_id"] = settings.aws_access_key_id
                client_config["aws_secret_access_key"] = settings.aws_secret_access_key
                logger.info("[MTLS SETUP] Using explicit AWS credentials from config")
            else:
                logger.info("[MTLS SETUP] Using IAM role credentials (ECS/EC2)")

            s3_client = boto3.client("s3", **client_config)

            # Use P12 certificate if configured
            if settings.vendor_mtls_p12_s3_key and settings.vendor_mtls_p12_password:
                logger.info(f"[MTLS SETUP] Using P12 certificate for mTLS authentication")
                logger.info(f"[MTLS SETUP] P12 S3 Key: {settings.vendor_mtls_p12_s3_key}")
                self._load_p12_certificate(s3_client)
            # Fallback to PEM certificates
            elif settings.vendor_mtls_cert_s3_key and settings.vendor_mtls_key_s3_key:
                logger.info(f"[MTLS SETUP] Using PEM certificates for mTLS authentication")
                logger.info(f"[MTLS SETUP] Cert S3 Key: {settings.vendor_mtls_cert_s3_key}")
                logger.info(f"[MTLS SETUP] Key S3 Key: {settings.vendor_mtls_key_s3_key}")
                if settings.vendor_mtls_ca_s3_key:
                    logger.info(f"[MTLS SETUP] CA Bundle S3 Key: {settings.vendor_mtls_ca_s3_key}")
                self._load_pem_certificates(s3_client)
            else:
                error_msg = (
                    "No valid mTLS certificate configuration found. "
                    "Please set either P12 (VENDOR_MTLS_P12_S3_KEY + VENDOR_MTLS_P12_PASSWORD) "
                    "or PEM (VENDOR_MTLS_CERT_S3_KEY + VENDOR_MTLS_KEY_S3_KEY) environment variables."
                )
                logger.error(f"[MTLS SETUP] {error_msg}")
                raise ValueError(error_msg)

            logger.info("[MTLS SETUP] ✓ Certificate service initialized successfully")
            logger.info(f"[MTLS SETUP] ✓ Client cert path: {self.cert_path}")
            logger.info(f"[MTLS SETUP] ✓ Client key path: {self.key_path}")
            if hasattr(self, 'ca_path') and self.ca_path:
                logger.info(f"[MTLS SETUP] ✓ CA bundle path: {self.ca_path}")

        except Exception as e:
            log_exception(logger, e, "[MTLS SETUP] Failed to setup mTLS certificates")
            raise

    def _load_p12_certificate(self, s3_client):
        """Load P12 certificate from S3 and extract cert/key."""
        try:
            logger.info(f"[MTLS P12] Downloading P12 certificate from S3...")
            logger.info(f"[MTLS P12] Bucket: {settings.s3_bucket_name}, Key: {settings.vendor_mtls_p12_s3_key}")

            # Download P12 file
            try:
                response = s3_client.get_object(
                    Bucket=settings.s3_bucket_name,
                    Key=settings.vendor_mtls_p12_s3_key
                )
                p12_content = response["Body"].read()
                logger.info(f"[MTLS P12] ✓ Downloaded P12 file ({len(p12_content)} bytes)")
            except s3_client.exceptions.NoSuchKey:
                error_msg = (
                    f"P12 certificate not found in S3: s3://{settings.s3_bucket_name}/{settings.vendor_mtls_p12_s3_key}. "
                    "Please upload the certificate file to S3."
                )
                logger.error(f"[MTLS P12] {error_msg}")
                raise FileNotFoundError(error_msg)
            except s3_client.exceptions.NoSuchBucket:
                error_msg = f"S3 bucket not found: {settings.s3_bucket_name}"
                logger.error(f"[MTLS P12] {error_msg}")
                raise FileNotFoundError(error_msg)
            except Exception as s3_error:
                if "AccessDenied" in str(s3_error) or "403" in str(s3_error):
                    error_msg = (
                        f"Access denied to S3: s3://{settings.s3_bucket_name}/{settings.vendor_mtls_p12_s3_key}. "
                        "Check IAM permissions: ECS task role or EC2 instance role needs s3:GetObject permission."
                    )
                    logger.error(f"[MTLS P12] {error_msg}")
                    raise PermissionError(error_msg)
                raise

            # Extract private key and certificate
            private_key, certificate, ca_certs = pkcs12.load_key_and_certificates(
                p12_content,
                settings.vendor_mtls_p12_password.encode('utf-8') if settings.vendor_mtls_p12_password else None
            )

            if not private_key or not certificate:
                raise ValueError("P12 file does not contain valid private key or certificate")

            # Convert to PEM format
            key_pem = private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption()
            )
            cert_pem = certificate.public_bytes(serialization.Encoding.PEM)

            # Write to temporary files
            self.cert_path = self._write_temp_file(cert_pem, suffix=".pem", prefix="client_cert_")
            self.key_path = self._write_temp_file(key_pem, suffix=".pem", prefix="client_key_")

            # Handle CA certificates
            if ca_certs:
                ca_bundle = b''.join(ca_cert.public_bytes(serialization.Encoding.PEM) for ca_cert in ca_certs)
                self.ca_path = self._write_temp_file(ca_bundle, suffix=".pem", prefix="ca_bundle_")
            else:
                self.ca_path = None

        except Exception as e:
            log_exception(logger, e, "Failed to load P12 certificate")
            raise

    def _load_pem_certificates(self, s3_client):
        """Load PEM certificates from S3."""
        try:
            # Download client certificate
            cert_response = s3_client.get_object(
                Bucket=settings.s3_bucket_name,
                Key=settings.vendor_mtls_cert_s3_key
            )
            cert_content = cert_response["Body"].read()
            self.cert_path = self._write_temp_file(cert_content, suffix=".pem", prefix="client_cert_")

            # Download client key
            key_response = s3_client.get_object(
                Bucket=settings.s3_bucket_name,
                Key=settings.vendor_mtls_key_s3_key
            )
            key_content = key_response["Body"].read()
            self.key_path = self._write_temp_file(key_content, suffix=".pem", prefix="client_key_")

            # Download CA bundle (optional)
            if settings.vendor_mtls_ca_s3_key:
                ca_response = s3_client.get_object(
                    Bucket=settings.s3_bucket_name,
                    Key=settings.vendor_mtls_ca_s3_key
                )
                ca_content = ca_response["Body"].read()
                self.ca_path = self._write_temp_file(ca_content, suffix=".pem", prefix="ca_bundle_")
            else:
                self.ca_path = None

        except Exception as e:
            log_exception(logger, e, "Failed to load PEM certificates")
            raise

    def _write_temp_file(self, content: bytes, suffix: str, prefix: str) -> str:
        """Write content to a temporary file and return the path."""
        try:
            temp_file = tempfile.NamedTemporaryFile(mode='wb', suffix=suffix, prefix=prefix, delete=False)
            temp_file.write(content)
            temp_file.close()
            os.chmod(temp_file.name, 0o400)
            return temp_file.name
        except Exception as e:
            log_exception(logger, e, "Failed to create temporary file")
            raise

    def _create_session(self) -> requests.Session:
        """Create requests session with mTLS configuration."""
        session = requests.Session()
        session.cert = (self.cert_path, self.key_path)

        # Configure SSL verification based on settings
        if not settings.ssl_verify_enabled:
            # Disable SSL verification for staging environments with self-signed certs
            session.verify = False

            # Suppress urllib3 InsecureRequestWarning to avoid log spam
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

            logger.warning(
                "[SSL WARNING] SSL certificate verification is DISABLED. "
                "This should ONLY be used in staging/dev environments with self-signed certificates. "
                "NEVER disable SSL verification in production!"
            )
        elif self.ca_path:
            # Use custom CA bundle if provided
            session.verify = self.ca_path
            logger.debug(f"[SSL] Using custom CA bundle: {self.ca_path}")
        else:
            # Use system default CA bundle
            session.verify = True
            logger.debug("[SSL] Using system default CA bundle for verification")

        return session

    def get_certificates(self) -> List[Dict[str, Any]]:
        """
        Get all certificates from InfoCert API.

        Returns structured certificate data including subject, issuer, status, and expiration.

        Returns:
            List of certificate dictionaries with structure:
            {
                "certificate": "base64-encoded-cert",
                "ids": ["cert-id-1", "cert-id-2"],
                "subject": "CN=...",
                "issuer": "CN=...",
                "status": "active",
                "expiration_date": "2025-11-13T..."
            }

        Raises:
            RequestException: If API request fails
            ValueError: If response format is invalid
        """
        try:
            logger.info("[GET CERTIFICATES] Fetching certificates from InfoCert")

            # Create session with mTLS
            session = self._create_session()

            endpoint_url = f"{self.api_url}/certificates"
            logger.debug(f"[GET CERTIFICATES] Request URL: {endpoint_url}")

            response = session.get(
                endpoint_url,
                headers={
                    "Authorization": f"Bearer {settings.infocert_sat}",
                    "Content-Type": "application/json",
                    "X-signer-id": settings.infocert_credential_id
                },
                timeout=self.timeout
            )

            response.raise_for_status()
            cert_data = response.json()

            # Response is a list of certificates
            if not isinstance(cert_data, list):
                logger.error(f"[GET CERTIFICATES] Expected list, got: {type(cert_data)}")
                raise ValueError("InfoCert API returned invalid certificate format")

            logger.info(f"[GET CERTIFICATES] ✓ Retrieved {len(cert_data)} certificate(s)")

            # Return structured certificate data
            certificates = []
            for cert in cert_data:
                certificates.append({
                    "certificate": cert.get("certificate", ""),
                    "ids": cert.get("ids", []),
                    "subject": cert.get("subject", ""),
                    "issuer": cert.get("issuer", ""),
                    "status": cert.get("status", "unknown"),
                    "expiration_date": cert.get("expirationDate", "")
                })

            return certificates

        except Exception as e:
            log_exception(logger, e, "Failed to fetch certificates from InfoCert")
            raise

    def get_signing_certificate_bytes(self) -> bytes:
        """
        Fetch the signing certificate as DER-encoded bytes with caching.

        This retrieves the first active certificate from InfoCert and returns
        it as DER-encoded bytes for use in P7M building.

        Caching behavior:
        - Cache is enabled if CERTIFICATE_CACHE_TTL_SECONDS > 0
        - Cached certificate is returned if not expired
        - Cache is refreshed when expired or on first fetch
        - Cache hit/miss is logged for monitoring

        Returns:
            DER-encoded certificate bytes

        Raises:
            RequestException: If API request fails
            ValueError: If certificate cannot be retrieved
        """
        try:
            # Check cache if enabled (TTL > 0)
            if self._cache_ttl_seconds > 0:
                now = datetime.now(timezone.utc)

                # Return cached certificate if valid
                if self._cached_certificate_bytes and self._cache_expiry:
                    if now < self._cache_expiry:
                        time_remaining = (self._cache_expiry - now).total_seconds()
                        logger.debug(
                            f"[CERT CACHE HIT] Using cached certificate | "
                            f"Expires in: {time_remaining:.0f}s ({time_remaining/60:.1f} minutes)"
                        )
                        return self._cached_certificate_bytes
                    else:
                        logger.debug("[CERT CACHE EXPIRED] Cache expired, refreshing certificate")
                else:
                    logger.debug("[CERT CACHE MISS] No cached certificate, fetching from InfoCert")
            else:
                logger.debug("[CERT CACHE DISABLED] Fetching certificate from InfoCert (caching disabled)")

            # Fetch certificate from InfoCert API
            logger.debug("[CERT FETCH] Fetching signing certificate from InfoCert")

            # Create session with mTLS
            session = self._create_session()

            endpoint_url = f"{self.api_url}/certificates"

            response = session.get(
                endpoint_url,
                headers={
                    "Authorization": f"Bearer {settings.infocert_sat}",
                    "Content-Type": "application/json",
                    "X-signer-id": settings.infocert_credential_id
                },
                timeout=self.timeout
            )

            response.raise_for_status()
            cert_data = response.json()

            # Response is a list of certificates
            if not isinstance(cert_data, list) or len(cert_data) == 0:
                logger.error(f"[CERT FETCH] Expected list of certificates, got: {type(cert_data)}")
                raise ValueError("InfoCert API returned invalid certificate list")

            # Get first active certificate
            active_cert = None
            for cert in cert_data:
                if cert.get("status") == "active":
                    active_cert = cert
                    break

            # If no active certificate found, use the first one
            if not active_cert:
                logger.warning("[CERT FETCH] No active certificate found, using first certificate")
                active_cert = cert_data[0]

            logger.debug(f"[CERT FETCH] Using certificate - Subject: {active_cert.get('subject')}, Status: {active_cert.get('status')}")

            # Extract certificate content (base64 encoded string)
            cert_b64 = active_cert.get("certificate")
            if not cert_b64:
                logger.error(f"[CERT FETCH] Certificate object missing 'certificate' field: {list(active_cert.keys())}")
                raise ValueError("Certificate object does not contain 'certificate' field")

            # Decode base64 certificate
            cert_bytes = base64.b64decode(cert_b64)
            logger.info(f"[CERT FETCH] ✓ Certificate fetched from InfoCert | Size: {len(cert_bytes)} bytes")

            # Update cache if enabled
            if self._cache_ttl_seconds > 0:
                self._cached_certificate_bytes = cert_bytes
                self._cache_expiry = datetime.now(timezone.utc) + timedelta(seconds=self._cache_ttl_seconds)
                logger.info(
                    f"[CERT CACHE UPDATED] Certificate cached | "
                    f"TTL: {self._cache_ttl_seconds}s | "
                    f"Expires at: {self._cache_expiry.strftime('%Y-%m-%d %H:%M:%S UTC')}"
                )

            return cert_bytes

        except Exception as e:
            log_exception(logger, e, "Failed to fetch signing certificate from InfoCert")
            raise
