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
from asn1crypto import cms, core, x509 as asn1_x509, algos

from app.config import settings
from app.models.schemas import SignatureRequest, SignatureResponse
from app.services.certificate_service import CertificateService
from app.services.p7m_service import P7MService
from app.utils.logger import setup_logger, log_exception
from app.utils.retry import retry_on_recoverable_errors
from typing import List, Dict, Tuple

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
        logger.debug(f"[API CALL] Endpoint: {endpoint_url}")
        logger.debug(f"[API CALL] SSL verify: {session.verify}")
        logger.debug(f"[API CALL] Client cert: {session.cert is not None}")

        try:
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

            logger.debug(f"[API CALL] Received HTTP {response.status_code} for {filename}")

            # Check for authentication errors
            if response.status_code == 401:
                logger.error(
                    f"[API CALL] UNAUTHORIZED (401) - InfoCert rejected authentication for {filename}\n"
                    f"  Response: {response.text}\n"
                    f"  SSL verify enabled: {settings.ssl_verify_enabled}\n"
                    f"  Session verify: {session.verify}\n"
                    f"  Client cert configured: {session.cert is not None}\n"
                    f"  X-signer-id: {settings.infocert_credential_id}\n"
                    f"  SAT token length: {len(settings.infocert_sat) if settings.infocert_sat else 0}"
                )

            response.raise_for_status()
            return response.json()

        except Exception as e:
            logger.error(
                f"[API CALL] Request failed for {filename}: {str(e)}\n"
                f"  SSL verify enabled: {settings.ssl_verify_enabled}\n"
                f"  Session verify: {session.verify}\n"
                f"  Client cert: {session.cert}"
            )
            raise

    def sign_file_hash(self, signature_request: SignatureRequest, original_file_content: bytes) -> SignatureResponse:
        """
        Sign original file hash using InfoCert hashSignatures API and create CAdES-compliant P7M.

        Workflow (ETSI EN 319 122-1 compliant):
        1. Fetch signing certificate from InfoCert
        2. Build SignedAttributes (DTBS) with:
           - content_type
           - message_digest (file hash)
           - signing_time
           - signing-certificate-v2 (REQUIRED for CAdES compliance)
        3. Compute DTBS digest (hash of SignedAttributes)
        4. Send DTBS digest to InfoCert hashSignatures API
        5. InfoCert returns RAW signature bytes + optional timestamp
        6. Build complete P7M file with ORIGINAL FILE EMBEDDED

        The .p7m file contains:
        - Original file content (embedded)
        - SignedAttributes with signing-certificate-v2
        - Signature of DTBS (SignedAttributes)
        - Certificate
        - Timestamp (optional)

        Result: CAdES-BES compliant P7M file

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

            # Step 1: Fetch signing certificate (needed for signing-certificate-v2 attribute)
            logger.debug(f"[STEP 1/5] Fetching signing certificate from InfoCert")
            cert_der_bytes = self.cert_service.get_signing_certificate_bytes()
            cert = asn1_x509.Certificate.load(cert_der_bytes)
            logger.info(f"[STEP 1/5] Certificate fetched: {len(cert_der_bytes)} bytes")

            # Compute certificate hash for signing-certificate-v2 attribute (CAdES requirement)
            cert_hash = hashlib.sha256(cert_der_bytes).digest()
            logger.debug(f"[STEP 1/5] Certificate hash computed: {cert_hash.hex()[:32]}...")

            # Build SigningCertificateV2 manually as DER bytes (RFC 5035)
            # SigningCertificateV2 ::= SEQUENCE {
            #     certs SEQUENCE OF ESSCertIDv2
            # }
            # ESSCertIDv2 ::= SEQUENCE {
            #     hashAlgorithm AlgorithmIdentifier DEFAULT {algorithm id-sha256},
            #     certHash Hash (OCTET STRING)
            # }

            # Build AlgorithmIdentifier for SHA-256: SEQUENCE { OID, NULL }
            hash_alg = bytes.fromhex('300d06096086480165030402010500')  # SHA-256 AlgorithmIdentifier

            # Build certHash: OCTET STRING containing SHA-256 hash (32 bytes)
            cert_hash_octet = bytes.fromhex('0420') + cert_hash  # 0x04 = OCTET STRING, 0x20 = 32 bytes

            # Build ESSCertIDv2: SEQUENCE { hashAlgorithm, certHash }
            ess_cert_id_v2_content = hash_alg + cert_hash_octet
            ess_cert_id_v2 = bytes.fromhex('30') + bytes([len(ess_cert_id_v2_content)]) + ess_cert_id_v2_content

            # Build SEQUENCE OF ESSCertIDv2
            certs_seq = bytes.fromhex('30') + bytes([len(ess_cert_id_v2)]) + ess_cert_id_v2

            # Build SigningCertificateV2: SEQUENCE { certs }
            signing_cert_v2_der = bytes.fromhex('30') + bytes([len(certs_seq)]) + certs_seq

            logger.debug(f"[STEP 1/5] SigningCertificateV2 (SHA-256) DER built: {signing_cert_v2_der.hex()[:64]}...")

            # Step 2: Build SignedAttributes (DTBS - Data To Be Signed)
            logger.debug(f"[STEP 2/5] Building SignedAttributes (DTBS) structure with signing-certificate-v2")

            file_hash_bytes = bytes.fromhex(signature_request.file_hash)

            # Build SignedAttributes according to ETSI EN 319 122-1 (CAdES)
            # REQUIRED attributes for CAdES-BES:
            # - content_type
            # - message_digest (file hash)
            # - signing_time
            # - signing-certificate-v2 (MANDATORY for CAdES compliance!)
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
                }),
                cms.CMSAttribute({
                    'type': cms.CMSAttributeType('1.2.840.113549.1.9.16.2.47'),  # id-aa-signingCertificateV2
                    'values': [core.Any.load(signing_cert_v2_der)]  # Load DER bytes as Any type
                })
            ])

            logger.info(
                f"[STEP 2/5] SignedAttributes built with file hash and signing-certificate-v2 | "
                f"File hash: {signature_request.file_hash[:32]}... | "
                f"Cert hash (SHA-256): {cert_hash.hex()[:32]}..."
            )

            # Step 3: Compute DTBS digest (hash of SignedAttributes)
            logger.debug(f"[STEP 3/5] Computing DTBS digest (hash of SignedAttributes)")

            # DER encode SignedAttributes for hashing
            signed_attrs_der = signed_attrs.dump()
            dtbs_digest = hashlib.sha256(signed_attrs_der).digest()
            dtbs_digest_b64 = base64.b64encode(dtbs_digest).decode('ascii')

            logger.info(f"[STEP 3/5] DTBS digest computed: {dtbs_digest_b64[:32]}...")

            # Step 4: Create session with mTLS and send to InfoCert
            logger.debug(f"[STEP 4/5] Creating mTLS session for InfoCert API")
            session = self.cert_service._create_session()
            logger.info(f"[STEP 4/5] mTLS session established")

            # Prepare InfoCert hashSignatures API request
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

            # Step 5: Build P7M file with SignedAttributes (certificate already fetched in step 1)
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

    def sign_file_hashes_batch(
        self,
        signature_requests: List[Tuple[SignatureRequest, bytes]]
    ) -> List[Tuple[SignatureRequest, SignatureResponse, bytes, Exception]]:
        """
        Sign multiple file hashes using InfoCert hashSignatures API in a SINGLE batch request.

        This is a performance optimization that reduces API calls from N (one per file) to 1.
        For 100 files: 100 API calls → 1 API call (99% reduction).

        Workflow:
        1. Fetch signing certificate ONCE (shared for all files)
        2. Build SignedAttributes for EACH file (with signing-certificate-v2)
        3. Compute DTBS digest for EACH file
        4. Send ALL DTBS digests to InfoCert in SINGLE API call
        5. Build P7M for EACH file with corresponding signature

        Args:
            signature_requests: List of tuples (SignatureRequest, original_file_content)

        Returns:
            List of tuples (SignatureRequest, SignatureResponse, original_file_content, error)
            - If successful: error is None
            - If failed: SignatureResponse is None, error contains exception

        Note:
            - Individual file failures do NOT fail the entire batch
            - Each result tuple maps back to the corresponding request by index
            - Certificate is fetched ONCE and shared across all signatures
        """
        start_time = datetime.now(timezone.utc)
        batch_size = len(signature_requests)

        logger.info(f"[BATCH SIGN START] Processing {batch_size} files in single API call")

        try:
            # Step 1: Fetch signing certificate ONCE (shared for all files)
            logger.debug(f"[BATCH STEP 1/5] Fetching signing certificate from InfoCert")
            cert_der_bytes = self.cert_service.get_signing_certificate_bytes()
            cert = asn1_x509.Certificate.load(cert_der_bytes)
            logger.info(f"[BATCH STEP 1/5] Certificate fetched: {len(cert_der_bytes)} bytes")

            # Compute certificate hash for signing-certificate-v2 attribute (shared)
            cert_hash = hashlib.sha256(cert_der_bytes).digest()
            logger.debug(f"[BATCH STEP 1/5] Certificate hash computed: {cert_hash.hex()[:32]}...")

            # Build SigningCertificateV2 DER bytes (shared for all files)
            hash_alg = bytes.fromhex('300d06096086480165030402010500')
            cert_hash_octet = bytes.fromhex('0420') + cert_hash
            ess_cert_id_v2_content = hash_alg + cert_hash_octet
            ess_cert_id_v2 = bytes.fromhex('30') + bytes([len(ess_cert_id_v2_content)]) + ess_cert_id_v2_content
            certs_seq = bytes.fromhex('30') + bytes([len(ess_cert_id_v2)]) + ess_cert_id_v2
            signing_cert_v2_der = bytes.fromhex('30') + bytes([len(certs_seq)]) + certs_seq

            logger.debug(f"[BATCH STEP 1/5] SigningCertificateV2 DER built (shared for all)")

            # Step 2: Build SignedAttributes and compute DTBS for EACH file
            logger.debug(f"[BATCH STEP 2/5] Building SignedAttributes for {batch_size} files")
            dtbs_list = []  # List of (index, dtbs_digest_b64, signed_attrs, request, file_content)

            for index, (sig_request, file_content) in enumerate(signature_requests):
                file_hash_bytes = bytes.fromhex(sig_request.file_hash)

                # Build SignedAttributes for this file
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
                    }),
                    cms.CMSAttribute({
                        'type': cms.CMSAttributeType('1.2.840.113549.1.9.16.2.47'),
                        'values': [core.Any.load(signing_cert_v2_der)]
                    })
                ])

                # Compute DTBS digest for this file
                signed_attrs_der = signed_attrs.dump()
                dtbs_digest = hashlib.sha256(signed_attrs_der).digest()
                dtbs_digest_b64 = base64.b64encode(dtbs_digest).decode('ascii')

                dtbs_list.append((index, dtbs_digest_b64, signed_attrs, sig_request, file_content))

            logger.info(f"[BATCH STEP 2/5] SignedAttributes built for {batch_size} files")

            # Step 3: Create session with mTLS
            logger.debug(f"[BATCH STEP 3/5] Creating mTLS session for InfoCert API")
            session = self.cert_service._create_session()
            logger.info(f"[BATCH STEP 3/5] mTLS session established")

            # Step 4: Send ALL DTBS digests to InfoCert in SINGLE batch request
            logger.debug(f"[BATCH STEP 4/5] Preparing InfoCert batch API request with {batch_size} hashes")

            # Build hashSignatures array
            hash_signatures = []
            for index, dtbs_digest_b64, signed_attrs, sig_request, file_content in dtbs_list:
                hash_signatures.append({
                    "requestId": f"batch-{index}-{sig_request.filename}",
                    "hash": dtbs_digest_b64,
                    "withTimestamp": True
                })

            payload = {
                "applicationId": "ifcer-batch-service",
                "pin": settings.infocert_pin,
                "authorization": {
                    "sat": settings.infocert_sat
                },
                "hashSignatures": hash_signatures
            }

            endpoint_url = f"{self.api_url}/certificates/{settings.infocert_certificate_id}/sign"

            logger.info(f"[BATCH STEP 4/5] Sending {batch_size} DTBS digests to InfoCert in single batch request...")

            # Call InfoCert API with retry on recoverable errors
            response_data = self._call_infocert_sign_api(
                session=session,
                endpoint_url=endpoint_url,
                payload=payload,
                filename=f"batch-{batch_size}-files"
            )

            logger.info(f"[BATCH STEP 4/5] Received batch response from InfoCert")

            # Step 5: Parse response and build P7M for each file
            logger.debug(f"[BATCH STEP 5/5] Building P7M files for {batch_size} signatures")

            signature_results = response_data.get("signatureResult", [])

            if len(signature_results) != batch_size:
                logger.warning(
                    f"[BATCH WARNING] Expected {batch_size} results, got {len(signature_results)}"
                )

            # Build result list
            results = []

            for index, dtbs_digest_b64, signed_attrs, sig_request, file_content in dtbs_list:
                try:
                    # Find corresponding result by requestId
                    request_id = f"batch-{index}-{sig_request.filename}"
                    result = next(
                        (r for r in signature_results if r.get("requestId") == request_id),
                        None
                    )

                    if not result:
                        error_msg = f"No result returned for {sig_request.filename}"
                        logger.error(f"[BATCH FILE ERROR] {error_msg}")
                        results.append((sig_request, None, file_content, ValueError(error_msg)))
                        continue

                    is_ok = result.get("isOk", False)

                    if not is_ok:
                        signature_error = result.get("signatureError", {})
                        error_detail = signature_error.get("detail", "Unknown error")
                        error_code = signature_error.get("code", "UNKNOWN")
                        error_msg = f"InfoCert signature failed: {error_code} - {error_detail}"
                        logger.error(f"[BATCH FILE ERROR] {sig_request.filename}: {error_msg}")
                        results.append((sig_request, None, file_content, ValueError(error_msg)))
                        continue

                    # Extract signature bytes
                    signed_document = result.get("signedDocument", {})
                    raw_signature_b64 = signed_document.get("content", "")

                    if not raw_signature_b64:
                        error_msg = "InfoCert API did not return signed document content"
                        logger.error(f"[BATCH FILE ERROR] {sig_request.filename}: {error_msg}")
                        results.append((sig_request, None, file_content, ValueError(error_msg)))
                        continue

                    raw_signature_bytes = base64.b64decode(raw_signature_b64)

                    # Extract timestamp if present
                    signed_timestamp = result.get("signedTimestamp", {})
                    timestamp_bytes = None
                    if signed_timestamp:
                        timestamp_b64 = signed_timestamp.get("content", "")
                        timestamp_bytes = base64.b64decode(timestamp_b64) if timestamp_b64 else None

                    # Build P7M file
                    p7m_bytes = self.p7m_service.create_p7m_from_signature(
                        file_content=file_content,
                        signature_bytes=raw_signature_bytes,
                        cert_der_bytes=cert_der_bytes,
                        signed_attributes=signed_attrs,
                        timestamp_bytes=timestamp_bytes
                    )

                    # Create response
                    signing_time = datetime.now(timezone.utc)
                    signature_response = SignatureResponse(
                        signature=raw_signature_b64[:100],
                        timestamp=signing_time,
                        manifest_content=None,
                        p7m_content=p7m_bytes,
                    )

                    logger.debug(
                        f"[BATCH FILE SUCCESS] {sig_request.filename}: P7M created ({len(p7m_bytes)} bytes)"
                    )
                    results.append((sig_request, signature_response, file_content, None))

                except Exception as e:
                    logger.error(f"[BATCH FILE ERROR] {sig_request.filename}: {str(e)}")
                    results.append((sig_request, None, file_content, e))

            logger.info(f"[BATCH STEP 5/5] P7M files built for {len(results)} files")

            elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
            successful = len([r for r in results if r[3] is None])
            failed = len([r for r in results if r[3] is not None])

            logger.info(
                f"[BATCH SIGN COMPLETE] Batch processing finished | "
                f"Total: {batch_size} | "
                f"Successful: {successful} | "
                f"Failed: {failed} | "
                f"Duration: {elapsed:.2f}s | "
                f"Avg per file: {elapsed/batch_size:.2f}s"
            )

            return results

        except SSLError as e:
            log_exception(logger, e, f"mTLS authentication failed for batch")
            # Return all as failed with same error
            return [(req, None, content, e) for req, content in signature_requests]
        except Timeout as e:
            log_exception(logger, e, f"Request timeout for batch")
            return [(req, None, content, e) for req, content in signature_requests]
        except RequestException as e:
            log_exception(logger, e, f"API request failed for batch")
            return [(req, None, content, e) for req, content in signature_requests]
        except Exception as e:
            log_exception(logger, e, f"Unexpected error signing batch")
            return [(req, None, content, e) for req, content in signature_requests]
