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
        manifest_content: bytes,
        p7s_signature: bytes,
        expected_filename: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Comprehensive validation of signed file against original (regulatory validation).

        This performs the same validation that Italian regulatory authorities would perform:
        1. Verify original file hash matches manifest
        2. Verify manifest structure and content
        3. Verify P7M signature structure
        4. Verify signature cryptographically
        5. Extract and validate certificate information

        Args:
            original_file_content: Original file bytes
            manifest_content: Manifest JSON bytes
            p7s_signature: P7M/P7S signature file bytes
            expected_filename: Optional filename to verify in manifest

        Returns:
            Validation result dictionary:
            {
                "valid": bool,
                "checks": {
                    "manifest_structure": bool,
                    "file_hash_match": bool,
                    "signature_structure": bool,
                    "signature_verified": bool,
                    "certificate_valid": bool
                },
                "manifest_data": {...},
                "certificate_info": {...},
                "errors": [...]
            }
        """
        start_time = datetime.now()
        result = {
            "valid": False,
            "checks": {
                "manifest_structure": False,
                "file_hash_match": False,
                "signature_structure": False,
                "signature_verified": False,
                "certificate_valid": False
            },
            "manifest_data": {},
            "certificate_info": {},
            "errors": [],
            "validation_timestamp": start_time.isoformat()
        }

        try:
            logger.info("[VALIDATION] Starting comprehensive signature validation")

            # Step 1: Validate manifest structure
            logger.debug("[VALIDATION] Step 1: Validating manifest structure")
            manifest_valid, manifest_data = self._validate_manifest_structure(manifest_content, expected_filename)
            result["checks"]["manifest_structure"] = manifest_valid
            result["manifest_data"] = manifest_data

            if not manifest_valid:
                result["errors"].append("Invalid manifest structure")
                logger.error("[VALIDATION] × Manifest structure invalid")
                return result

            # Step 2: Verify original file hash matches manifest
            logger.debug("[VALIDATION] Step 2: Verifying file hash matches manifest")
            hash_match, computed_hash = self._verify_file_hash(
                original_file_content,
                manifest_data.get("hash", ""),
                manifest_data.get("algorithm", "SHA256")
            )
            result["checks"]["file_hash_match"] = hash_match
            result["computed_file_hash"] = computed_hash

            if not hash_match:
                result["errors"].append(f"File hash mismatch. Computed: {computed_hash}, Expected: {manifest_data.get('hash')}")
                logger.error(f"[VALIDATION] × File hash mismatch")
                return result

            # Step 3: Verify P7M signature structure
            logger.debug("[VALIDATION] Step 3: Verifying P7M signature structure")
            structure_valid, p7m_data = self._verify_p7m_structure(p7s_signature)
            result["checks"]["signature_structure"] = structure_valid
            result["p7m_data"] = p7m_data

            if not structure_valid:
                result["errors"].append("Invalid P7M signature structure")
                logger.error("[VALIDATION] × P7M structure invalid")
                return result

            # Step 4: Verify signature cryptographically
            logger.debug("[VALIDATION] Step 4: Verifying signature cryptographically")
            sig_verified, cert_info = self._verify_signature_cryptographic(
                manifest_content,
                p7s_signature
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

    def _validate_manifest_structure(self, manifest_content: bytes, expected_filename: Optional[str]) -> Tuple[bool, Dict]:
        """Validate manifest JSON structure and required fields."""
        try:
            manifest_str = manifest_content.decode('utf-8')
            manifest = json.loads(manifest_str)

            # Check required fields
            required_fields = ["fileName", "hash", "algorithm", "timestamp"]
            missing_fields = [field for field in required_fields if field not in manifest]

            if missing_fields:
                logger.error(f"[VALIDATION] Manifest missing required fields: {missing_fields}")
                return False, {}

            # Verify filename if expected
            if expected_filename and manifest.get("fileName") != expected_filename:
                logger.error(f"[VALIDATION] Filename mismatch: {manifest.get('fileName')} != {expected_filename}")
                return False, manifest

            logger.debug(f"[VALIDATION] ✓ Manifest structure valid")
            return True, manifest

        except json.JSONDecodeError as e:
            logger.error(f"[VALIDATION] Invalid JSON in manifest: {str(e)}")
            return False, {}
        except Exception as e:
            logger.error(f"[VALIDATION] Error validating manifest structure: {str(e)}")
            return False, {}

    def _verify_file_hash(self, file_content: bytes, expected_hash: str, algorithm: str) -> Tuple[bool, str]:
        """Verify original file hash matches manifest hash."""
        try:
            # Compute hash based on algorithm
            algo_upper = algorithm.upper().replace("-", "")

            if algo_upper == "SHA256":
                computed = hashlib.sha256(file_content).hexdigest()
            elif algo_upper == "SHA512":
                computed = hashlib.sha512(file_content).hexdigest()
            elif algo_upper == "SHA1":
                computed = hashlib.sha1(file_content).hexdigest()
            else:
                logger.error(f"[VALIDATION] Unsupported hash algorithm: {algorithm}")
                return False, ""

            computed_upper = computed.upper()
            expected_upper = expected_hash.upper()

            match = computed_upper == expected_upper

            if match:
                logger.debug(f"[VALIDATION] ✓ File hash match: {computed_upper}")
            else:
                logger.error(f"[VALIDATION] × Hash mismatch. Computed: {computed_upper}, Expected: {expected_upper}")

            return match, computed_upper

        except Exception as e:
            logger.error(f"[VALIDATION] Error computing file hash: {str(e)}")
            return False, ""

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

    def _verify_signature_cryptographic(self, manifest_content: bytes, p7s_content: bytes) -> Tuple[bool, Dict]:
        """Verify signature cryptographically using certificate."""
        try:
            # Parse P7M
            content_info = cms.ContentInfo.load(p7s_content)
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
                # Compute manifest hash (what was signed)
                manifest_hash = hashlib.sha256(manifest_content).digest()

                # Verify signature
                public_key.verify(
                    signature,
                    manifest_hash,
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

    def quick_validate(self, original_file_content: bytes, manifest_content: bytes) -> bool:
        """
        Quick validation - just verify file hash matches manifest.

        Useful for fast integrity checks without full cryptographic verification.

        Args:
            original_file_content: Original file bytes
            manifest_content: Manifest JSON bytes

        Returns:
            True if hash matches, False otherwise
        """
        try:
            manifest = json.loads(manifest_content.decode('utf-8'))
            expected_hash = manifest.get("hash", "")
            algorithm = manifest.get("algorithm", "SHA256")

            match, _ = self._verify_file_hash(original_file_content, expected_hash, algorithm)
            return match

        except Exception as e:
            logger.error(f"[VALIDATION] Quick validation failed: {str(e)}")
            return False
