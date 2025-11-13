"""Validation service for verifying signed files against original files.

This service mimics regulatory authority validation processes:
1. Verify manifest contains correct original file hash
2. Verify manifest signature is valid
3. Verify P7M structure integrity
4. Extract and validate certificate information

Can be used independently or integrated into signing workflows.
"""

import base64
import hashlib
import json
from typing import Dict, Any, Tuple, Optional
from datetime import datetime

from asn1crypto import cms, x509 as asn1_x509
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.backends import default_backend

from app.utils.logger import setup_logger, log_exception

logger = setup_logger(__name__)


class ValidationService:
    """Service for validating signed files against originals (regulatory-style verification)."""

    def validate_signature(
        self,
        original_file_content: bytes,
        p7m_file: bytes
    ) -> Dict[str, Any]:
        """
        Comprehensive validation of P7M file with embedded content (regulatory validation).

        This performs the same validation that Italian regulatory authorities would perform:
        1. Verify P7M signature structure
        2. Extract embedded file from P7M
        3. Verify extracted file matches original file
        4. Verify signature cryptographically
        5. Extract and validate certificate information

        Args:
            original_file_content: Original file bytes (for verification)
            p7m_file: P7M file bytes (ENVELOPED signature with embedded file)

        Returns:
            Validation result dictionary:
            {
                "valid": bool,
                "checks": {
                    "signature_structure": bool,
                    "embedded_file_match": bool,
                    "signature_verified": bool,
                    "certificate_valid": bool
                },
                "certificate_info": {...},
                "errors": [...]
            }
        """
        start_time = datetime.now()
        result = {
            "valid": False,
            "checks": {
                "signature_structure": False,
                "embedded_file_extracted": False,
                "embedded_file_match": False,
                "signature_verified": False,
                "certificate_valid": False
            },
            "certificate_info": {},
            "errors": [],
            "validation_timestamp": start_time.isoformat()
        }

        try:
            logger.info("[VALIDATION] Starting comprehensive P7M validation")

            # Step 1: Verify P7M signature structure
            logger.debug("[VALIDATION] Step 1: Verifying P7M signature structure")
            structure_valid, p7m_data = self._verify_p7m_structure(p7m_file)
            result["checks"]["signature_structure"] = structure_valid
            result["p7m_data"] = p7m_data

            if not structure_valid:
                result["errors"].append("Invalid P7M signature structure")
                logger.error("[VALIDATION] × P7M structure invalid")
                return result

            # Step 2: Extract embedded file from P7M
            logger.debug("[VALIDATION] Step 2: Extracting embedded file from P7M")
            extracted_file, extracted_ok = self._extract_embedded_file(p7m_file)
            result["checks"]["embedded_file_extracted"] = extracted_ok

            if not extracted_ok or extracted_file is None:
                result["errors"].append("Failed to extract embedded file from P7M")
                logger.error("[VALIDATION] × Failed to extract embedded file")
                return result

            logger.info(f"[VALIDATION] Step 2: Extracted {len(extracted_file)} bytes from P7M")

            # Step 3: Verify extracted file matches original file
            logger.debug("[VALIDATION] Step 3: Verifying extracted file matches original")
            file_match = extracted_file == original_file_content
            result["checks"]["embedded_file_match"] = file_match

            if not file_match:
                result["errors"].append(
                    f"Embedded file mismatch. Original: {len(original_file_content)} bytes, "
                    f"Extracted: {len(extracted_file)} bytes"
                )
                logger.error("[VALIDATION] × Embedded file does not match original")
                return result

            logger.info("[VALIDATION] Step 3: ✓ Embedded file matches original")

            # Step 4: Verify signature cryptographically
            logger.debug("[VALIDATION] Step 4: Verifying signature cryptographically")
            sig_verified, cert_info = self._verify_signature_cryptographic(
                extracted_file,  # Verify signature against extracted file
                p7m_file
            )
            result["checks"]["signature_verified"] = sig_verified
            result["certificate_info"] = cert_info

            if not sig_verified:
                result["errors"].append("Cryptographic signature verification failed")
                logger.error("[VALIDATION] × Signature verification failed")
                return result

            # Step 5: Validate certificate
            logger.debug("[VALIDATION] Step 5: Validating certificate")
            cert_valid, cert_details = self._validate_certificate(cert_info)
            result["checks"]["certificate_valid"] = cert_valid
            result["certificate_details"] = cert_details

            if not cert_valid:
                result["errors"].append("Certificate validation failed")
                logger.error("[VALIDATION] × Certificate invalid")
                return result

            # All checks passed
            result["valid"] = True
            elapsed = (datetime.now() - start_time).total_seconds()
            logger.info(f"[VALIDATION] ✓ All validation checks passed ({elapsed:.2f}s)")

            return result

        except Exception as e:
            log_exception(logger, e, "Validation failed with exception")
            result["errors"].append(f"Validation exception: {str(e)}")
            return result

    def _extract_embedded_file(self, p7m_file: bytes) -> Tuple[Optional[bytes], bool]:
        """Extract embedded file content from P7M (ENVELOPED signature)."""
        try:
            # Parse P7M structure
            content_info = cms.ContentInfo.load(p7m_file)

            if content_info['content_type'].native != 'signed_data':
                logger.error("[VALIDATION] P7M content type is not signed_data")
                return None, False

            signed_data = content_info['content']

            # Extract encapsulated content info
            encap_content_info = signed_data['encap_content_info']

            # Check if content is present (ENVELOPED)
            if 'content' not in encap_content_info or encap_content_info['content'] is None:
                logger.error("[VALIDATION] P7M does not contain embedded content (DETACHED signature)")
                return None, False

            # Extract the embedded file content
            embedded_content = encap_content_info['content'].native

            if not isinstance(embedded_content, bytes):
                logger.error(f"[VALIDATION] Unexpected content type: {type(embedded_content)}")
                return None, False

            logger.debug(f"[VALIDATION] ✓ Extracted {len(embedded_content)} bytes from P7M")
            return embedded_content, True

        except Exception as e:
            logger.error(f"[VALIDATION] Error extracting embedded file: {str(e)}")
            return None, False


    def _verify_p7m_structure(self, p7s_content: bytes) -> Tuple[bool, Dict]:
        """Verify P7M/PKCS#7 structure integrity."""
        try:
            # Parse P7M structure
            content_info = cms.ContentInfo.load(p7s_content)

            if content_info['content_type'].native != 'signed_data':
                logger.error("[VALIDATION] P7M content type is not signed_data")
                return False, {}

            signed_data = content_info['content']

            p7m_data = {
                "version": signed_data['version'].native,
                "digest_algorithms": [algo['algorithm'].native for algo in signed_data['digest_algorithms']],
                "certificate_count": len(signed_data.get('certificates', [])),
                "signer_count": len(signed_data.get('signer_infos', []))
            }

            logger.debug(f"[VALIDATION] ✓ P7M structure valid: {p7m_data}")
            return True, p7m_data

        except Exception as e:
            logger.error(f"[VALIDATION] Error parsing P7M structure: {str(e)}")
            return False, {}

    def _verify_signature_cryptographic(self, file_content: bytes, p7m_file: bytes) -> Tuple[bool, Dict]:
        """Verify signature cryptographically using certificate.

        Args:
            file_content: The original file content (or extracted embedded content from P7M)
            p7m_file: The complete P7M file bytes

        Returns:
            Tuple of (verification_success, certificate_info)
        """
        try:
            # Parse P7M
            content_info = cms.ContentInfo.load(p7m_file)
            signed_data = content_info['content']

            # Extract certificate
            if not signed_data.get('certificates') or len(signed_data['certificates']) == 0:
                logger.error("[VALIDATION] No certificates found in P7M")
                return False, {}

            cert_choice = signed_data['certificates'][0]
            cert_asn1 = cert_choice.chosen

            # Convert to cryptography certificate
            cert_der = cert_asn1.dump()
            cert = x509.load_der_x509_certificate(cert_der, default_backend())

            # Extract signer info
            if not signed_data.get('signer_infos') or len(signed_data['signer_infos']) == 0:
                logger.error("[VALIDATION] No signer info found in P7M")
                return False, {}

            signer_info = signed_data['signer_infos'][0]
            signature = signer_info['signature'].native

            # Verify signature
            public_key = cert.public_key()

            try:
                # Compute file hash (what was signed by InfoCert)
                file_hash = hashlib.sha256(file_content).digest()

                # Verify signature
                public_key.verify(
                    signature,
                    file_hash,
                    padding.PKCS1v15(),
                    hashes.SHA256()
                )

                logger.debug("[VALIDATION] ✓ Signature cryptographically verified")

                # Extract certificate info
                cert_info = {
                    "subject": cert.subject.rfc4514_string(),
                    "issuer": cert.issuer.rfc4514_string(),
                    "serial_number": str(cert.serial_number),
                    "not_valid_before": cert.not_valid_before_utc.isoformat(),
                    "not_valid_after": cert.not_valid_after_utc.isoformat(),
                    "signature_algorithm": cert.signature_algorithm_oid._name
                }

                return True, cert_info

            except Exception as e:
                logger.error(f"[VALIDATION] Signature verification failed: {str(e)}")
                return False, {}

        except Exception as e:
            logger.error(f"[VALIDATION] Error in cryptographic verification: {str(e)}")
            return False, {}

    def _validate_certificate(self, cert_info: Dict) -> Tuple[bool, Dict]:
        """Validate certificate details (expiration, etc.)."""
        try:
            if not cert_info:
                return False, {}

            cert_details = {
                "expired": False,
                "not_yet_valid": False,
                "valid": True
            }

            # Check validity dates
            if "not_valid_before" in cert_info and "not_valid_after" in cert_info:
                now = datetime.now()
                not_before = datetime.fromisoformat(cert_info["not_valid_before"])
                not_after = datetime.fromisoformat(cert_info["not_valid_after"])

                if now < not_before:
                    cert_details["not_yet_valid"] = True
                    cert_details["valid"] = False
                    logger.error(f"[VALIDATION] Certificate not yet valid")

                if now > not_after:
                    cert_details["expired"] = True
                    cert_details["valid"] = False
                    logger.error(f"[VALIDATION] Certificate expired")

            if cert_details["valid"]:
                logger.debug("[VALIDATION] ✓ Certificate valid")

            return cert_details["valid"], cert_details

        except Exception as e:
            logger.error(f"[VALIDATION] Error validating certificate: {str(e)}")
            return False, {}

    def quick_validate(self, original_file_content: bytes, p7m_file: bytes) -> bool:
        """
        Quick validation - just verify embedded file matches original.

        Useful for fast integrity checks without full cryptographic verification.

        Args:
            original_file_content: Original file bytes
            p7m_file: P7M file bytes

        Returns:
            True if embedded file matches original, False otherwise
        """
        try:
            # Extract embedded file from P7M
            extracted_file, ok = self._extract_embedded_file(p7m_file)

            if not ok or extracted_file is None:
                logger.error("[VALIDATION] Quick validation failed: could not extract embedded file")
                return False

            # Compare bytes
            match = extracted_file == original_file_content

            if match:
                logger.debug("[VALIDATION] ✓ Quick validation passed: embedded file matches original")
            else:
                logger.error("[VALIDATION] × Quick validation failed: embedded file does not match original")

            return match

        except Exception as e:
            logger.error(f"[VALIDATION] Quick validation failed: {str(e)}")
            return False
