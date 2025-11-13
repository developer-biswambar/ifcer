"""P7M (PKCS#7/CAdES) file building service.

This service handles the creation of P7M/CAdES signature files from:
- Document content (manifest)
- Raw signature bytes
- Signing certificate

Reference: RFC 5652 (CMS), ETSI TS 101 733 (CAdES)
"""

from asn1crypto import cms, core, x509 as asn1_x509, algos

from app.utils.logger import setup_logger, log_exception

logger = setup_logger(__name__)


class P7MService:
    """Service for building P7M (PKCS#7/CAdES) signature files."""

    def create_p7m_from_signature(
        self,
        file_content: bytes,
        signature_bytes: bytes,
        cert_der_bytes: bytes,
        signed_attributes: 'cms.CMSAttributes',
        timestamp_bytes: bytes = None
    ) -> bytes:
        """
        Create a P7M (PKCS#7/CAdES ENVELOPED) file with original file embedded and SignedAttributes.

        This is used with InfoCert hashSignatures API workflow:
        1. Build SignedAttributes (DTBS) with file hash
        2. Compute DTBS digest (hash of SignedAttributes)
        3. Send DTBS digest to InfoCert
        4. InfoCert returns signature of DTBS
        5. We build complete P7M with file + SignedAttributes + signature

        This creates a CAdES-BES (Basic Electronic Signature) structure which is
        a PKCS#7 SignedData with ENVELOPED content (file embedded inside).

        Args:
            file_content: The ORIGINAL FILE content as bytes (to be embedded in P7M)
            signature_bytes: The signature bytes from InfoCert (signature of DTBS)
            cert_der_bytes: The DER-encoded signing certificate fetched from InfoCert
            signed_attributes: The SignedAttributes (DTBS) structure
            timestamp_bytes: Optional RFC 3161 timestamp token bytes

        Returns:
            Complete P7M file as bytes (DER-encoded PKCS#7 SignedData with embedded file)

        Raises:
            ValueError: If P7M creation fails
        """
        try:
            logger.debug(
                f"[P7M CREATE] Starting P7M creation | "
                f"File content: {len(file_content)} bytes | "
                f"Signature: {len(signature_bytes)} bytes | "
                f"Certificate: {len(cert_der_bytes)} bytes"
            )

            # Parse the certificate
            logger.debug("[P7M CREATE] Parsing signing certificate...")
            cert = asn1_x509.Certificate.load(cert_der_bytes)
            logger.debug(f"[P7M CREATE] Certificate parsed successfully")

            # Create ContentInfo with ORIGINAL FILE embedded (ENVELOPED signature)
            logger.debug("[P7M CREATE] Building ContentInfo with ORIGINAL FILE embedded...")
            encap_content_info = cms.ContentInfo({
                'content_type': cms.ContentType('data'),
                'content': core.OctetString(file_content)  # Embed original file content
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

            # Create SignerInfo with SignedAttributes
            logger.debug("[P7M CREATE] Building SignerInfo structure with SignedAttributes...")
            signer_info_dict = {
                'version': 'v1',
                'sid': signer_identifier,
                'digest_algorithm': digest_algorithm,
                'signed_attrs': signed_attributes,  # Include SignedAttributes (DTBS)
                'signature_algorithm': signature_algorithm,
                'signature': core.OctetString(signature_bytes)
            }

            # Add timestamp token as unsigned attribute if present
            if timestamp_bytes:
                logger.debug("[P7M CREATE] Adding timestamp token as unsigned attribute...")
                unsigned_attrs = cms.CMSAttributes([
                    cms.CMSAttribute({
                        'type': cms.CMSAttributeType('1.2.840.113549.1.9.16.2.14'),  # id-aa-timeStampToken
                        'values': [cms.ContentInfo.load(timestamp_bytes)]
                    })
                ])
                signer_info_dict['unsigned_attrs'] = unsigned_attrs
                logger.debug(f"[P7M CREATE] Timestamp token added: {len(timestamp_bytes)} bytes")

            signer_info = cms.SignerInfo(signer_info_dict)

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
