"""Signature service for InfoCert API integration.

This service handles the signature request/response cycle with InfoCert's hashSignatures API.
Certificate management is handled by CertificateService.
P7M file building is handled by P7MService.
"""

import base64
import hashlib
import json
from datetime import datetime, timezone

import requests
from requests.exceptions import RequestException, Timeout, SSLError

from app.config import settings
from app.models.schemas import SignatureRequest, SignatureResponse
from app.services.certificate_service import CertificateService
from app.services.p7m_service import P7MService
from app.utils.logger import setup_logger, log_exception

logger = setup_logger(__name__)


class SignatureService:
    """Service for InfoCert signature operations."""

    def __init__(self):
        """Initialize signature service."""
        self.api_url = settings.infocert_api_url
        self.timeout = settings.request_timeout

        # Initialize certificate service for mTLS
        logger.info("Initializing certificate service for mTLS")
        self.cert_service = CertificateService()

        # Initialize P7M service for signature building
        self.p7m_service = P7MService()

        logger.info(f"Signature service initialized | API: {self.api_url}")

    def sign_file_hash(self, signature_request: SignatureRequest) -> SignatureResponse:
        """
        Create and sign a manifest file containing the file hash using InfoCert hashSignatures API.

        Workflow:
        1. Create manifest JSON containing file hash and metadata
        2. Compute SHA-256 hash of the manifest
        3. Send manifest hash to InfoCert hashSignatures API
        4. InfoCert returns RAW signature bytes + optional timestamp
        5. Fetch signing certificate from InfoCert
        6. Build complete P7M file from: manifest + raw signature + certificate

        The .p7s file contains the DETACHED signature of the manifest hash.
        Verification requires TWO files:
        - manifest.json (original manifest)
        - manifest.p7s (detached signature)

        Authentication: mTLS + Bearer SAT token + X-signer-id + PIN

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

            manifest_json = json.dumps(manifest, indent=2)
            manifest_bytes = manifest_json.encode('utf-8')
            logger.info(f"[STEP 1/5] Created manifest: {len(manifest_bytes)} bytes")
            logger.debug(f"Manifest content:\n{manifest_json}")

            # Step 2: Compute SHA-256 hash of the manifest
            logger.debug(f"[STEP 2/5] Computing SHA-256 hash of manifest")
            manifest_hash = hashlib.sha256(manifest_bytes).digest()
            manifest_hash_b64 = base64.b64encode(manifest_hash).decode('ascii')
            logger.info(f"[STEP 2/5] Manifest hash: {manifest_hash_b64[:32]}...")

            # Step 3: Create session with mTLS
            logger.debug(f"[STEP 3/5] Creating mTLS session for InfoCert API")
            session = self.cert_service._create_session()
            logger.info(f"[STEP 3/5] mTLS session established")

            # Step 4: Send hash to InfoCert hashSignatures API
            logger.debug(f"[STEP 4/5] Preparing InfoCert hashSignatures API request")

            payload = {
                "applicationId": "ifcer-batch-service",
                "pin": settings.infocert_pin,
                "authorization": {
                    "sat": settings.infocert_sat
                },
                "hashSignatures": [{
                    "requestId": f"manifest-{signature_request.filename}",
                    "hash": manifest_hash_b64,
                    "withTimestamp": True
                }]
            }

            endpoint_url = f"{self.api_url}/certificates/{settings.infocert_certificate_id}/sign"

            logger.info(f"[STEP 4/5] Sending manifest hash to InfoCert for signing...")
            logger.debug(f"[STEP 4/5] API URL: {endpoint_url}")

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

            response.raise_for_status()
            logger.info(f"[STEP 4/5] Received response from InfoCert (HTTP {response.status_code})")

            # Parse response
            response_data = response.json()
            signature_results = response_data.get("signatureResult", [])

            if not signature_results:
                raise ValueError("InfoCert API did not return signature results")

            result = signature_results[0]
            is_ok = result.get("isOk", False)

            if not is_ok:
                signature_error = result.get("signatureError", {})
                error_detail = signature_error.get("detail", "Unknown error")
                error_code = signature_error.get("code", "UNKNOWN")
                logger.error(f"[ERROR] InfoCert signature failed: {error_code} - {error_detail}")
                raise ValueError(f"InfoCert signature failed: {error_code} - {error_detail}")

            # Extract RAW signature bytes
            signed_document = result.get("signedDocument", {})
            raw_signature_b64 = signed_document.get("content", "")

            if not raw_signature_b64:
                raise ValueError("InfoCert API did not return signed document content")

            logger.info(f"[STEP 4/5] Received RAW signature bytes ({len(raw_signature_b64)} chars base64)")

            raw_signature_bytes = base64.b64decode(raw_signature_b64)

            # Extract timestamp if present
            signed_timestamp = result.get("signedTimestamp", {})
            if signed_timestamp:
                timestamp_b64 = signed_timestamp.get("content", "")
                logger.debug(f"[STEP 4/5] Timestamp included: {len(timestamp_b64)} chars")

            # Step 5: Fetch signing certificate and build P7M
            logger.debug(f"[STEP 5/5] Fetching signing certificate from InfoCert")
            cert_der_bytes = self.cert_service.get_signing_certificate_bytes()
            logger.info(f"[STEP 5/5] Certificate fetched: {len(cert_der_bytes)} bytes")

            # Build complete P7M file
            logger.debug(f"[STEP 5/5] Building P7M file from raw signature and certificate")
            p7s_bytes = self.p7m_service.create_p7m_from_signature(
                manifest_content=manifest_bytes,
                signature_bytes=raw_signature_bytes,
                cert_der_bytes=cert_der_bytes
            )
            logger.info(f"[STEP 5/5] P7M file created: {len(p7s_bytes)} bytes")

            # Create response
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
            log_exception(logger, e, f"mTLS authentication failed for: {signature_request.filename}")
            raise
        except Timeout as e:
            log_exception(logger, e, f"Request timeout for: {signature_request.filename}")
            raise
        except RequestException as e:
            log_exception(logger, e, f"API request failed for: {signature_request.filename}")
            raise
        except Exception as e:
            log_exception(logger, e, f"Unexpected error signing file: {signature_request.filename}")
            raise
