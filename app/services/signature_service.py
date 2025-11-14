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
from asn1crypto import cms, core

from app.config import settings
from app.models.schemas import SignatureRequest, SignatureResponse
from app.services.certificate_service import CertificateService
from app.services.p7m_service import P7MService
from app.utils.logger import setup_logger, log_exception
from app.utils.retry import retry_on_recoverable_errors

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

    @retry_on_recoverable_errors
    def _call_infocert_sign_api(
        self,
        session: requests.Session,
        endpoint_url: str,
        payload: dict,
        filename: str
    ) -> dict:
        """
        Call InfoCert hashSignatures API with retry on recoverable errors.

        This method is decorated with retry logic that handles:
        - Network timeouts
        - Connection errors
        - Rate limiting (HTTP 429)
        - Server overload (HTTP 502, 503, 504)

        Will NOT retry on:
        - Authentication errors (HTTP 401, 403)
        - Client errors (HTTP 400, 404)
        - Internal server errors (HTTP 500)

        Args:
            session: Configured requests.Session with mTLS
            endpoint_url: Full API endpoint URL
            payload: Request payload dictionary
            filename: File being processed (for logging)

        Returns:
            Response data dictionary from InfoCert API

        Raises:
            RequestException: If API request fails after all retries
            Timeout: If request times out after all retries
            SSLError: If mTLS authentication fails
        """
        logger.debug(f"[API CALL] Calling InfoCert API for {filename}")

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
        logger.debug(f"[API CALL] Received HTTP {response.status_code} for {filename}")

        return response.json()

    def sign_file_hash(self, signature_request: SignatureRequest, original_file_content: bytes) -> SignatureResponse:
        """
        Sign original file hash using InfoCert hashSignatures API and create P7M with embedded content.

        Workflow:
        1. Send original file hash to InfoCert hashSignatures API
        2. InfoCert returns RAW signature bytes + optional timestamp
        3. Fetch signing certificate from InfoCert
        4. Build complete P7M file with ORIGINAL FILE EMBEDDED

        The .p7m file contains:
        - Original file content (embedded)
        - Signature of original file hash
        - Certificate
        - Timestamp

        Result: Single P7M file (no separate manifest needed)

        Authentication: mTLS + Bearer SAT token + X-signer-id + PIN

        Args:
            signature_request: SignatureRequest object with file hash details
            original_file_content: Original file content as bytes (to be embedded in P7M)

        Returns:
            SignatureResponse with P7M file content and timestamp

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
                f"Algorithm: {signature_request.hash_algorithm} | "
                f"Size: {len(original_file_content)} bytes"
            )

            # Step 1: Build SignedAttributes (DTBS - Data To Be Signed)
            logger.debug(f"[STEP 1/5] Building SignedAttributes (DTBS) structure")

            file_hash_bytes = bytes.fromhex(signature_request.file_hash)

            # Build SignedAttributes according to ETSI EN 319 102-1
            signed_attrs = cms.CMSAttributes([
                cms.CMSAttribute({
                    'type': cms.CMSAttributeType('content_type'),
                    'values': [cms.ContentType('data')]
                }),
                cms.CMSAttribute({
                    'type': cms.CMSAttributeType('message_digest'),
                    'values': [core.OctetString(file_hash_bytes)]
                }),
                cms.CMSAttribute({
                    'type': cms.CMSAttributeType('signing_time'),
                    'values': [core.UTCTime(datetime.now(timezone.utc))]
                })
            ])

            logger.info(f"[STEP 1/5] SignedAttributes built with file hash: {signature_request.file_hash[:32]}...")

            # Step 2: Compute DTBS digest (hash of SignedAttributes)
            logger.debug(f"[STEP 2/5] Computing DTBS digest (hash of SignedAttributes)")

            # DER encode SignedAttributes for hashing
            signed_attrs_der = signed_attrs.dump()
            dtbs_digest = hashlib.sha256(signed_attrs_der).digest()
            dtbs_digest_b64 = base64.b64encode(dtbs_digest).decode('ascii')

            logger.info(f"[STEP 2/5] DTBS digest computed: {dtbs_digest_b64[:32]}...")

            # Step 3: Create session with mTLS
            logger.debug(f"[STEP 3/5] Creating mTLS session for InfoCert API")
            session = self.cert_service._create_session()
            logger.info(f"[STEP 3/5] mTLS session established")

            # Step 4: Send DTBS digest to InfoCert hashSignatures API
            logger.debug(f"[STEP 4/5] Preparing InfoCert hashSignatures API request")

            payload = {
                "applicationId": "ifcer-batch-service",
                "pin": settings.infocert_pin,
                "authorization": {
                    "sat": settings.infocert_sat
                },
                "hashSignatures": [{
                    "requestId": f"file-{signature_request.filename}",
                    "hash": dtbs_digest_b64,  # Send DTBS digest, not file hash!
                    "withTimestamp": True
                }]
            }

            endpoint_url = f"{self.api_url}/certificates/{settings.infocert_certificate_id}/sign"

            logger.info(f"[STEP 4/5] Sending DTBS digest to InfoCert for signing...")
            logger.debug(f"[STEP 4/5] API URL: {endpoint_url}")

            # Call InfoCert API with retry on recoverable errors
            response_data = self._call_infocert_sign_api(
                session=session,
                endpoint_url=endpoint_url,
                payload=payload,
                filename=signature_request.filename
            )

            logger.info(f"[STEP 4/5] Received response from InfoCert")

            # Parse response
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

            logger.info(f"[STEP 4/5] Received signature bytes ({len(raw_signature_b64)} chars base64)")

            raw_signature_bytes = base64.b64decode(raw_signature_b64)

            # Extract timestamp if present
            signed_timestamp = result.get("signedTimestamp", {})
            timestamp_bytes = None
            if signed_timestamp:
                timestamp_b64 = signed_timestamp.get("content", "")
                timestamp_bytes = base64.b64decode(timestamp_b64) if timestamp_b64 else None
                logger.debug(f"[STEP 4/5] Timestamp included: {len(timestamp_b64)} chars")

            # Step 5: Fetch signing certificate and build P7M with SignedAttributes
            logger.debug(f"[STEP 5/5] Fetching signing certificate from InfoCert")
            cert_der_bytes = self.cert_service.get_signing_certificate_bytes()
            logger.info(f"[STEP 5/5] Certificate fetched: {len(cert_der_bytes)} bytes")

            # Build complete P7M file with ORIGINAL FILE EMBEDDED and SignedAttributes
            logger.debug(f"[STEP 5/5] Building P7M file with SignedAttributes ({len(original_file_content)} bytes)")
            p7m_bytes = self.p7m_service.create_p7m_from_signature(
                file_content=original_file_content,  # Embed original file
                signature_bytes=raw_signature_bytes,  # Signature of DTBS
                cert_der_bytes=cert_der_bytes,
                signed_attributes=signed_attrs,  # Include SignedAttributes
                timestamp_bytes=timestamp_bytes  # Include timestamp if present
            )
            logger.info(f"[STEP 5/5] P7M file created: {len(p7m_bytes)} bytes (includes embedded file + SignedAttributes)")

            # Create response
            signing_time = datetime.now(timezone.utc)

            signature_response = SignatureResponse(
                signature=raw_signature_b64[:100],  # Store first 100 chars for reference
                timestamp=signing_time,
                manifest_content=None,  # No manifest - we embed original file instead
                p7m_content=p7m_bytes,  # The complete P7M file with embedded original content
            )

            elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
            logger.info(
                f"[SIGN COMPLETE] File: {signature_request.filename} | "
                f"P7M size: {len(p7m_bytes)} bytes | "
                f"Original file: {len(original_file_content)} bytes | "
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
