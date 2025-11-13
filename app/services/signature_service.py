"""Signature service for InfoCert API integration with mTLS authentication.

This service implements a MANIFEST-BASED approach for qualified digital signatures,
compliant with Italian eIDAS and AgID standards. The workflow:

1. Compute SHA-256 hash of the original document
2. Create a manifest JSON file containing: fileName, hash, algorithm, timestamp
3. Compute SHA-256 hash of the manifest
4. Send manifest hash to InfoCert hashSignatures API (/certificates/{id}/sign)
5. InfoCert signs the hash and returns RAW signature bytes + timestamp
6. Fetch signing certificate from InfoCert API
7. Build complete P7M file from: manifest + raw signature + certificate
8. Store TWO files for Italian register submission:
   - manifest.json (original manifest)
   - manifest.p7s (detached CAdES signature)

The .p7s file contains the DETACHED SIGNATURE of the manifest hash.
Verification requires both files: authorities compute hash of manifest.json
and verify it against the signature in manifest.p7s.

Authentication: mTLS (P12 certificate) + Bearer SAT token + X-signer-id + PIN

Reference: https://developers.infocert.digital/e-signature-and-e-sealing/
"""

import base64
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone

import boto3
import requests
from requests.exceptions import RequestException, Timeout, SSLError
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.serialization import pkcs12
from asn1crypto import cms, core, x509 as asn1_x509, algos

from app.config import settings
from app.models.schemas import SignatureRequest, SignatureResponse
from app.utils.logger import setup_logger, log_exception

logger = setup_logger(__name__)


class SignatureService:
    """Service for interacting with vendor API using mTLS authentication."""

    def __init__(self):
        """Initialize signature service with mTLS configuration loaded from S3."""
        # InfoCert uses a single mTLS API endpoint for all operations
        self.api_url = settings.infocert_api_url
        self.timeout = settings.request_timeout

        # Download mTLS certificates from S3 and store as temporary files
        logger.info(f"Loading mTLS certificates from S3 bucket: {settings.s3_bucket_name}")
        logger.info(f"InfoCert API: {self.api_url}")

        try:
            # Prepare boto3 client configuration
            client_config = {
                "region_name": settings.aws_region
            }

            # Add endpoint_url for moto/LocalStack testing
            if settings.aws_endpoint_url:
                client_config["endpoint_url"] = settings.aws_endpoint_url
                logger.info(f"Using custom AWS endpoint for certificates: {settings.aws_endpoint_url}")

            # Add explicit credentials if provided (for moto/LocalStack)
            if settings.aws_access_key_id and settings.aws_secret_access_key:
                client_config["aws_access_key_id"] = settings.aws_access_key_id
                client_config["aws_secret_access_key"] = settings.aws_secret_access_key
                logger.debug("Using explicit AWS credentials for certificate download")

            s3_client = boto3.client("s3", **client_config)

            # OPTION 1: Use P12 certificate (recommended)
            if settings.vendor_mtls_p12_s3_key and settings.vendor_mtls_p12_password:
                logger.info("Using P12 certificate for mTLS authentication")
                self._load_p12_certificate(s3_client)
            # OPTION 2: Use PEM certificates (fallback)
            elif settings.vendor_mtls_cert_s3_key and settings.vendor_mtls_key_s3_key:
                logger.info("Using PEM certificates for mTLS authentication")
                self._load_pem_certificates(s3_client)
            else:
                raise ValueError(
                    "No valid mTLS certificate configuration found. "
                    "Either provide P12 (VENDOR_MTLS_P12_S3_KEY + VENDOR_MTLS_P12_PASSWORD) "
                    "or PEM files (VENDOR_MTLS_CERT_S3_KEY + VENDOR_MTLS_KEY_S3_KEY)"
                )

            logger.info(f"Signature service initialized successfully")

        except Exception as e:
            log_exception(logger, e, "Failed to initialize signature service with S3 certificates")
            raise

    def _load_p12_certificate(self, s3_client):
        """Load P12 certificate from S3 and extract cert/key."""
        try:
            # Download P12 file
            p12_content = self._download_from_s3(s3_client, settings.vendor_mtls_p12_s3_key)
            logger.info(f"P12 file downloaded from s3://{settings.s3_bucket_name}/{settings.vendor_mtls_p12_s3_key}")

            # Load P12 and extract private key, certificate, and CA certificates
            private_key, certificate, ca_certs = pkcs12.load_key_and_certificates(
                p12_content,
                settings.vendor_mtls_p12_password.encode('utf-8') if settings.vendor_mtls_p12_password else None
            )

            if not private_key or not certificate:
                raise ValueError("P12 file does not contain valid private key or certificate")

            # Convert private key to PEM format
            key_pem = private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption()
            )

            # Convert certificate to PEM format
            cert_pem = certificate.public_bytes(serialization.Encoding.PEM)

            # Write to temporary files
            self.cert_path = self._write_temp_file(cert_pem, suffix=".pem", prefix="client_cert_")
            self.key_path = self._write_temp_file(key_pem, suffix=".pem", prefix="client_key_")
            logger.info("✓ P12 certificate extracted and converted to PEM format")

            # Handle CA certificates (optional)
            if ca_certs:
                ca_bundle = b''.join(ca_cert.public_bytes(serialization.Encoding.PEM) for ca_cert in ca_certs)
                self.ca_path = self._write_temp_file(ca_bundle, suffix=".pem", prefix="ca_bundle_")
                logger.info(f"✓ Extracted {len(ca_certs)} CA certificate(s) from P12")
            else:
                self.ca_path = None
                logger.info("No CA certificates in P12, using default SSL verification")

        except Exception as e:
            log_exception(logger, e, f"Failed to load P12 certificate from {settings.vendor_mtls_p12_s3_key}")
            raise

    def _load_pem_certificates(self, s3_client):
        """Load PEM certificates from S3 (legacy method)."""
        try:
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

        except Exception as e:
            log_exception(logger, e, "Failed to load PEM certificates")
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

    def _fetch_signing_certificate(self, session: requests.Session) -> bytes:
        """
        Fetch the signing certificate from InfoCert API.

        This retrieves the DER-encoded X.509 certificate that was used to create
        the signature. The certificate is needed to build the complete P7M file.

        Args:
            session: Configured requests.Session with mTLS

        Returns:
            DER-encoded certificate bytes

        Raises:
            RequestException: If API request fails
            ValueError: If certificate cannot be retrieved
        """
        try:
            endpoint_url = f"{self.api_url}/certificates"
            logger.debug(f"[CERT FETCH] Fetching certificate from: {endpoint_url}")

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
            logger.debug(f"[CERT FETCH] Certificate decoded from base64: {len(cert_bytes)} bytes")
            return cert_bytes

        except Exception as e:
            log_exception(logger, e, "Failed to fetch signing certificate from InfoCert")
            raise

    def sign_file_hash(self, signature_request: SignatureRequest) -> SignatureResponse:
        """
        Create and sign a manifest file containing the file hash using InfoCert hashSignatures API.

        This implements the manifest-based approach with DETACHED signature where:
        1. Create a manifest JSON containing file hash and metadata
        2. Compute SHA-256 hash of the manifest
        3. Send manifest hash to InfoCert hashSignatures API (/certificates/{id}/sign)
        4. InfoCert returns RAW signature bytes (not complete P7M)
        5. Fetch signing certificate from InfoCert
        6. Build complete P7M from: manifest + raw signature + certificate

        The original file stays unchanged. The .p7s file contains the DETACHED signature
        of the manifest hash. Verification requires TWO files:
        - manifest.json (original manifest)
        - manifest.p7s (detached signature)

        Authentication uses: mTLS + Bearer SAT token + X-signer-id + PIN

        Args:
            signature_request: SignatureRequest object with file hash details

        Returns:
            SignatureResponse with detached signature (.p7s) and timestamp

        Raises:
            RequestException: If API request fails
            SSLError: If mTLS authentication fails
            Timeout: If request times out
        """
        start_time = datetime.now(timezone.utc)
        try:
            logger.info(
                f"[SIGN START] File: {signature_request.filename} | "
                f"Hash: {signature_request.file_hash[:16]}... | "
                f"Algorithm: {signature_request.hash_algorithm}"
            )

            # Step 1: Create manifest JSON
            logger.debug(f"[STEP 1/5] Creating manifest JSON for {signature_request.filename}")
            manifest = {
                "fileName": signature_request.filename,
                "algorithm": signature_request.hash_algorithm.upper(),
                "hash": signature_request.file_hash,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

            # Convert manifest to JSON string
            manifest_json = json.dumps(manifest, indent=2)
            manifest_size = len(manifest_json.encode('utf-8'))
            logger.info(f"[STEP 1/5] Created manifest: {manifest_size} bytes")
            logger.debug(f"Manifest content:\n{manifest_json}")

            # Step 2: Compute SHA-256 hash of the manifest
            logger.debug(f"[STEP 2/5] Computing SHA-256 hash of manifest")
            manifest_bytes = manifest_json.encode('utf-8')
            manifest_hash = hashlib.sha256(manifest_bytes).digest()
            manifest_hash_b64 = base64.b64encode(manifest_hash).decode('ascii')
            logger.info(f"[STEP 2/5] Manifest hash: {manifest_hash_b64[:32]}...")
            logger.debug(f"[STEP 2/5] Manifest hash (full): {manifest_hash_b64}")

            # Step 3: Create session with mTLS
            logger.debug(f"[STEP 3/5] Creating mTLS session for InfoCert API")
            session = self._create_session()
            logger.info(f"[STEP 3/5] mTLS session established")

            # Step 4: Prepare request payload for InfoCert hashSignatures API
            logger.debug(f"[STEP 4/5] Preparing InfoCert hashSignatures API request")

            # Use certificate ID from settings
            certificate_id = settings.infocert_certificate_id

            payload = {
                "applicationId": "ifcer-batch-service",
                "pin": settings.infocert_pin,
                "authorization": {
                    "sat": settings.infocert_sat
                },
                "hashSignatures": [{
                    "requestId": f"manifest-{signature_request.filename}",
                    "hash": manifest_hash_b64,
                    "withTimestamp": True  # boolean true
                }]
            }

            # Build endpoint URL with certificate ID
            endpoint_url = f"{self.api_url}/certificates/{certificate_id}/sign"

            logger.info(f"[STEP 4/5] Sending manifest hash to InfoCert API for hash signing...")
            logger.debug(f"[STEP 4/5] API URL: {endpoint_url}")
            logger.debug(f"[STEP 4/5] Certificate ID: {certificate_id}")
            logger.debug(f"[STEP 4/5] With Timestamp: true")
            logger.debug(f"[STEP 4/5] Request ID: manifest-{signature_request.filename}")

            # Make API request to InfoCert API with mTLS, SAT Bearer token, and X-signer-id header
            # SAT is sent in BOTH Authorization header AND request body (authorization.sat)
            response = session.post(
                endpoint_url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {settings.infocert_sat}",
                    "X-signer-id": settings.infocert_credential_id,
                    "Content-Type": "application/json"
                },
                timeout=self.timeout,
            )

            # Check response status
            response.raise_for_status()
            logger.info(f"[STEP 4/5] Received response from InfoCert (HTTP {response.status_code})")

            # Parse InfoCert hashSignatures response
            response_data = response.json()
            logger.debug(f"[STEP 4/5] Response keys: {list(response_data.keys())}")

            # Extract signature results from hashSignatures response
            signature_results = response_data.get("signatureResult", [])

            if not signature_results:
                logger.error("[ERROR] InfoCert API did not return signatureResult array")
                raise ValueError("InfoCert API did not return signature results")

            # Get first signature result (we only send one hash)
            result = signature_results[0]
            request_id = result.get("requestId", "")
            is_ok = result.get("isOk", False)

            logger.debug(f"[STEP 4/5] Request ID: {request_id}, isOk: {is_ok}")

            # Check if signature was successful
            if not is_ok:
                signature_error = result.get("signatureError", {})
                error_detail = signature_error.get("detail", "Unknown error")
                error_code = signature_error.get("code", "UNKNOWN")
                logger.error(f"[ERROR] InfoCert signature failed: {error_code} - {error_detail}")
                raise ValueError(f"InfoCert signature failed: {error_code} - {error_detail}")

            # Extract RAW signature bytes from response
            signed_document = result.get("signedDocument", {})
            raw_signature_b64 = signed_document.get("content", "")
            content_type = signed_document.get("contentType", "")

            if not raw_signature_b64:
                logger.error("[ERROR] InfoCert API did not return signedDocument.content")
                raise ValueError("InfoCert API did not return signed document content")

            logger.info(
                f"[STEP 4/5] Received RAW signature bytes "
                f"({len(raw_signature_b64)} chars base64, type: {content_type})"
            )

            # Decode raw signature bytes
            raw_signature_bytes = base64.b64decode(raw_signature_b64)
            logger.debug(f"[STEP 4/5] Raw signature decoded: {len(raw_signature_bytes)} bytes")

            # Extract timestamp if present
            signed_timestamp = result.get("signedTimestamp", {})
            if signed_timestamp:
                timestamp_b64 = signed_timestamp.get("content", "")
                timestamp_type = signed_timestamp.get("contentType", "")
                logger.debug(f"[STEP 4/5] Timestamp included: {len(timestamp_b64)} chars, type: {timestamp_type}")

            # Step 5: Fetch signing certificate and build P7M
            logger.debug(f"[STEP 5/5] Fetching signing certificate from InfoCert")
            cert_der_bytes = self._fetch_signing_certificate(session)
            logger.info(f"[STEP 5/5] Certificate fetched: {len(cert_der_bytes)} bytes")

            # Build complete P7M file from raw signature + certificate + manifest
            logger.debug(f"[STEP 5/5] Building P7M file from raw signature and certificate")
            p7s_bytes = self._create_p7m_from_signature(
                manifest_content=manifest_bytes,
                signature_bytes=raw_signature_bytes,
                cert_der_bytes=cert_der_bytes
            )
            logger.info(f"[STEP 5/5] P7M file created: {len(p7s_bytes)} bytes")

            # Use current timestamp since InfoCert may not provide it in CAdES response
            signing_time = datetime.now(timezone.utc)

            signature_response = SignatureResponse(
                signature=raw_signature_b64[:100],  # Store first 100 chars for reference
                timestamp=signing_time,
                manifest_content=manifest_bytes,  # The manifest JSON as bytes
                p7m_content=p7s_bytes,  # The complete P7M file built from raw signature
            )

            elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
            logger.info(
                f"[SIGN COMPLETE] File: {signature_request.filename} | "
                f"Signature size (.p7s): {len(p7s_bytes)} bytes | "
                f"Duration: {elapsed:.2f}s | "
                f"Timestamp: {signature_response.timestamp.isoformat()}"
            )

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

        This is ACTIVELY USED with InfoCert hashSignatures API, which returns:
        - RAW signature bytes (not complete P7M)
        - We fetch the certificate separately
        - We build the complete P7M ourselves

        This creates a CAdES-BES (Basic Electronic Signature) structure which is
        a PKCS#7 SignedData containing the signed manifest.

        Args:
            manifest_content: The manifest JSON as bytes
            signature_bytes: The RAW signature bytes from InfoCert hashSignatures response
            cert_der_bytes: The DER-encoded signing certificate fetched from InfoCert

        Returns:
            Complete P7M file as bytes (DER-encoded PKCS#7 SignedData)

        Raises:
            ValueError: If P7M creation fails
        """
        try:
            logger.debug(
                f"[P7M CREATE] Starting P7M creation | "
                f"Manifest: {len(manifest_content)} bytes | "
                f"Signature: {len(signature_bytes)} bytes | "
                f"Certificate: {len(cert_der_bytes)} bytes"
            )

            # Parse the certificate
            logger.debug("[P7M CREATE] Parsing signing certificate...")
            cert = asn1_x509.Certificate.load(cert_der_bytes)
            logger.debug(f"[P7M CREATE] Certificate parsed successfully")

            # Create ContentInfo for the manifest (encapContentInfo)
            logger.debug("[P7M CREATE] Building ContentInfo with manifest data...")
            encap_content_info = cms.ContentInfo({
                'content_type': cms.ContentType('data'),
                'content': core.OctetString(manifest_content)
            })

            # Get certificate hash for signer identifier
            logger.debug("[P7M CREATE] Extracting signer info from certificate...")
            issuer = cert['tbs_certificate']['issuer']
            serial_number = cert['tbs_certificate']['serial_number']

            signer_identifier = cms.SignerIdentifier(
                name='issuer_and_serial_number',
                value=cms.IssuerAndSerialNumber({
                    'issuer': issuer,
                    'serial_number': serial_number
                })
            )
            logger.debug(f"[P7M CREATE] Signer serial number: {serial_number}")

            # SHA-256 digest algorithm (used for hashing the manifest)
            logger.debug("[P7M CREATE] Setting digest algorithm: SHA-256")
            digest_algorithm = algos.DigestAlgorithm({
                'algorithm': '2.16.840.1.101.3.4.2.1'  # SHA-256 OID
            })

            # RSA with SHA-256 signature algorithm (typical for InfoCert)
            logger.debug("[P7M CREATE] Setting signature algorithm: sha256WithRSAEncryption")
            signature_algorithm = algos.SignedDigestAlgorithm({
                'algorithm': '1.2.840.113549.1.1.11'  # sha256WithRSAEncryption OID
            })

            # Create SignerInfo
            logger.debug("[P7M CREATE] Building SignerInfo structure...")
            signer_info = cms.SignerInfo({
                'version': 'v1',
                'sid': signer_identifier,
                'digest_algorithm': digest_algorithm,
                'signature_algorithm': signature_algorithm,
                'signature': core.OctetString(signature_bytes)
            })

            # Create SignedData
            logger.debug("[P7M CREATE] Building CAdES SignedData structure...")
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
            logger.debug("[P7M CREATE] Wrapping in PKCS#7 ContentInfo...")
            content_info = cms.ContentInfo({
                'content_type': cms.ContentType('signed_data'),
                'content': signed_data
            })

            # Encode to DER (this is the P7M file)
            logger.debug("[P7M CREATE] Encoding to DER format...")
            p7m_bytes = content_info.dump()

            logger.info(
                f"[P7M CREATE] ✓ P7M file created successfully | "
                f"Size: {len(p7m_bytes)} bytes | "
                f"Format: PKCS#7/CAdES-BES"
            )
            return p7m_bytes

        except Exception as e:
            log_exception(logger, e, "Failed to create P7M file from signature")
            raise ValueError(f"P7M creation failed: {str(e)}")

