# Technical Documentation: InfoCert Digital Signature Service

## Table of Contents
1. [Overview](#overview)
2. [InfoCert DTBS Workflow](#infocert-dtbs-workflow)
3. [Technical Standards](#technical-standards)
4. [SignedAttributes (DTBS) Structure](#signedattributes-dtbs-structure)
5. [P7M/CAdES File Structure](#p7mcades-file-structure)
6. [Complete End-to-End Flow](#complete-end-to-end-flow)
7. [Signature Creation Process](#signature-creation-process)
8. [P7M Building Process](#p7m-building-process)
9. [Validation Process](#validation-process)
10. [Key Algorithms and OIDs](#key-algorithms-and-oids)
11. [Authentication and Security](#authentication-and-security)

---

## Overview

This service implements digital signature creation using InfoCert's Hash Signatures API. The implementation follows the **DTBS (Data To Be Signed)** workflow, which is compliant with European standards for CAdES-BES (CMS Advanced Electronic Signatures - Basic Electronic Signature).

**Key Concept**: Instead of sending the file hash directly to InfoCert for signing, we:
1. Build a **SignedAttributes** structure containing the file hash
2. Compute the **hash of SignedAttributes** (DTBS digest)
3. Send the **DTBS digest** to InfoCert for signing
4. Build a complete P7M file with the SignedAttributes included

This creates a cryptographically verifiable signature that regulatory authorities can validate.

---

## InfoCert DTBS Workflow

### What is DTBS?

**DTBS (Data To Be Signed)** is the cryptographic data structure that gets signed by InfoCert. In our implementation, DTBS = SignedAttributes.

### Why Not Sign the File Hash Directly?

**Problem with Direct Signing**:
```
File → Hash → Sign Hash ✗ (Not compliant with CAdES)
```

**CAdES-Compliant Approach**:
```
File → Hash → Build SignedAttributes → Hash SignedAttributes → Sign DTBS ✓
```

### The Complete DTBS Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│ CLIENT (Our Service)                                                │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│ 1. Hash Original File                                              │
│    SHA-256(file_content) → file_hash                               │
│                                                                     │
│ 2. Build SignedAttributes (DTBS)                                   │
│    ┌───────────────────────────────────────────────────────────┐  │
│    │ SignedAttributes:                                          │  │
│    │   - contentType: data (1.2.840.113549.1.7.1)              │  │
│    │   - messageDigest: file_hash                              │  │
│    │   - signingTime: 2025-11-13T20:20:16Z                     │  │
│    └───────────────────────────────────────────────────────────┘  │
│                                                                     │
│ 3. DER-Encode SignedAttributes                                     │
│    DER_ENCODE(SignedAttributes) → signed_attrs_der                 │
│                                                                     │
│ 4. Hash SignedAttributes (DTBS Digest)                             │
│    SHA-256(signed_attrs_der) → dtbs_digest                         │
│                                                                     │
│ 5. Base64 Encode DTBS Digest                                       │
│    BASE64(dtbs_digest) → dtbs_digest_b64                           │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              │ HTTPS POST /certificates/{id}/sign
                              │ { "hashSignatures": [{ "hash": dtbs_digest_b64 }] }
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│ INFOCERT API                                                        │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│ 6. Verify mTLS Authentication                                      │
│    - Client certificate validation                                 │
│    - SAT token verification                                        │
│    - Signer ID verification                                        │
│    - PIN verification                                              │
│                                                                     │
│ 7. Sign DTBS Digest                                                │
│    RSA_SIGN(dtbs_digest, private_key) → raw_signature              │
│                                                                     │
│ 8. Create Timestamp (if requested)                                 │
│    RFC 3161 timestamp → timestamp_token                            │
│                                                                     │
│ 9. Return Response                                                 │
│    {                                                               │
│      "signatureResult": [{                                         │
│        "isOk": true,                                               │
│        "signedDocument": {                                         │
│          "content": BASE64(raw_signature)                          │
│        },                                                          │
│        "signedTimestamp": {                                        │
│          "content": BASE64(timestamp_token)                        │
│        }                                                           │
│      }]                                                            │
│    }                                                               │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              │ Response
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│ CLIENT (Our Service)                                                │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│ 10. Decode Signature and Timestamp                                 │
│     BASE64_DECODE(signed_document) → raw_signature_bytes           │
│     BASE64_DECODE(signed_timestamp) → timestamp_bytes              │
│                                                                     │
│ 11. Fetch Signing Certificate                                      │
│     GET /certificates/{id} → cert_der_bytes                        │
│                                                                     │
│ 12. Build P7M File                                                 │
│     CREATE_P7M(                                                    │
│       file_content,                                                │
│       raw_signature_bytes,                                         │
│       cert_der_bytes,                                              │
│       signed_attributes,  ← Include the DTBS we built!             │
│       timestamp_bytes                                              │
│     ) → p7m_bytes                                                  │
│                                                                     │
│ 13. Upload P7M to S3                                               │
│     s3://bucket/signed/{basename}.p7m                              │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Technical Standards

### ETSI EN 319 102-1
**European Telecommunications Standards Institute - CAdES Digital Signatures**

This is the European standard for CMS Advanced Electronic Signatures. It defines:
- How to structure SignedAttributes (Section 4.2 - DTBS)
- Required and optional attributes
- Signature format and validation requirements

**Section 4.2: Data To Be Signed (DTBS)**
> "The DTBS consists of the DER-encoded SignedAttributes structure."

### RFC 5652 - Cryptographic Message Syntax (CMS)
**IETF Standard for PKCS#7 SignedData**

Defines the PKCS#7/CMS structure used in P7M files:
- ContentInfo wrapper
- SignedData structure
- SignerInfo with attributes
- Certificate storage

### RFC 3161 - Time-Stamp Protocol (TSP)
**IETF Standard for Trusted Timestamps**

InfoCert returns RFC 3161 timestamp tokens that prove when the signature was created.

### CAdES-BES (Basic Electronic Signature)
**The specific CAdES profile we implement**

CAdES-BES requires:
- SignedAttributes with at least:
  - contentType
  - messageDigest
  - signingTime
- Complete certificate chain
- Optional timestamp for non-repudiation

---

## SignedAttributes (DTBS) Structure

### What Are SignedAttributes?

SignedAttributes are a set of authenticated attributes that are cryptographically bound to the signature. They are **part of the data being signed**.

### ASN.1 Structure

```asn1
SignedAttributes ::= SET SIZE (1..MAX) OF Attribute

Attribute ::= SEQUENCE {
  type    OBJECT IDENTIFIER,
  values  SET SIZE (1..MAX) OF AttributeValue
}
```

### Our Implementation

```python
from asn1crypto import cms, core
from datetime import datetime, timezone

# Build SignedAttributes
signed_attrs = cms.CMSAttributes([
    # Attribute 1: Content Type
    cms.CMSAttribute({
        'type': cms.CMSAttributeType('content_type'),  # OID: 1.2.840.113549.1.9.3
        'values': [cms.ContentType('data')]            # OID: 1.2.840.113549.1.7.1
    }),

    # Attribute 2: Message Digest (File Hash)
    cms.CMSAttribute({
        'type': cms.CMSAttributeType('message_digest'),  # OID: 1.2.840.113549.1.9.4
        'values': [core.OctetString(file_hash_bytes)]    # SHA-256 hash of file
    }),

    # Attribute 3: Signing Time
    cms.CMSAttribute({
        'type': cms.CMSAttributeType('signing_time'),       # OID: 1.2.840.113549.1.9.5
        'values': [core.UTCTime(datetime.now(timezone.utc))]
    })
])
```

### DER Encoding

```python
# DER-encode SignedAttributes for hashing
signed_attrs_der = signed_attrs.dump()

# Compute DTBS digest (what InfoCert will sign)
dtbs_digest = hashlib.sha256(signed_attrs_der).digest()
dtbs_digest_b64 = base64.b64encode(dtbs_digest).decode('ascii')
```

### Why Hash the SignedAttributes?

**Security**: By signing the hash of SignedAttributes (which contains the file hash), InfoCert creates a cryptographic chain:

```
File → Hash → SignedAttributes → Hash → Sign → Signature
```

**Verification**: Anyone can:
1. Extract SignedAttributes from P7M
2. Hash the SignedAttributes
3. Decrypt the signature to get expected hash
4. Compare hashes to verify authenticity

---

## P7M/CAdES File Structure

### What is P7M?

**P7M** is a file extension for PKCS#7/CMS SignedData with **ENVELOPED** content (original file embedded inside).

### Complete P7M Structure

```
ContentInfo (Top-level wrapper)
├── contentType: signedData (1.2.840.113549.1.7.2)
└── content: SignedData
    ├── version: 1
    ├── digestAlgorithms: [SHA-256]
    │   └── algorithm: 2.16.840.1.101.3.4.2.1 (SHA-256 OID)
    │
    ├── encapContentInfo (The embedded file)
    │   ├── contentType: data (1.2.840.113549.1.7.1)
    │   └── content: OctetString(original_file_bytes) ← File embedded here!
    │
    ├── certificates (Certificate chain)
    │   └── [0]: X.509 Certificate (InfoCert signing cert)
    │       ├── subject: CN=InfoCert Firma Qualificata 2,...
    │       ├── issuer: CN=InfoCertCA,...
    │       ├── serialNumber: 0x1234567890ABCDEF
    │       ├── notBefore: 2024-01-01T00:00:00Z
    │       ├── notAfter: 2026-01-01T00:00:00Z
    │       └── publicKey: RSA 2048-bit
    │
    └── signerInfos
        └── [0]: SignerInfo
            ├── version: 1
            │
            ├── sid (Signer Identifier)
            │   └── issuerAndSerialNumber
            │       ├── issuer: CN=InfoCertCA,...
            │       └── serialNumber: 0x1234567890ABCDEF
            │
            ├── digestAlgorithm: SHA-256
            │   └── algorithm: 2.16.840.1.101.3.4.2.1
            │
            ├── signedAttrs (DTBS - What was signed!) ← Critical!
            │   ├── [0]: contentType = data
            │   ├── [1]: messageDigest = SHA256(file) ← File hash here!
            │   └── [2]: signingTime = 2025-11-13T20:20:16Z
            │
            ├── signatureAlgorithm: sha256WithRSAEncryption
            │   └── algorithm: 1.2.840.113549.1.1.11
            │
            ├── signature: OctetString(raw_signature_bytes) ← InfoCert's signature!
            │   └── This is RSA signature of SHA256(signedAttrs)
            │
            └── unsignedAttrs (Optional attributes)
                └── [0]: timeStampToken (id-aa-timeStampToken)
                    └── OID: 1.2.840.113549.1.9.16.2.14
                        └── value: RFC 3161 timestamp token
```

### Binary Structure

```
Offset | Length | Description
-------|--------|--------------------------------------------------
0x0000 | 4      | SEQUENCE tag + length (ContentInfo)
0x0004 | 11     | OID: 1.2.840.113549.1.7.2 (signedData)
0x000F | 4      | [0] EXPLICIT tag (signedData content)
0x0013 | 4      | SEQUENCE tag + length (SignedData)
0x0017 | 3      | INTEGER: version = 1
0x001A | ...    | SET OF DigestAlgorithm
...    | ...    | ContentInfo (with embedded file)
...    | ...    | SET OF Certificate
...    | ...    | SET OF SignerInfo
...    | EOF    | End of P7M
```

---

## Complete End-to-End Flow

### Step-by-Step Processing

#### 1. File Upload to S3
```
User uploads file → S3 bucket
  └── s3://ifcer-bucket/uploads/document.pdf
```

#### 2. Process Request Received
```python
POST /recertify
{
  "file_key": "uploads/document.pdf"
}
```

#### 3. Download File from S3
```python
# app/services/s3_service.py
file_content = s3_service.download_file("uploads/document.pdf")
# Returns: bytes (original file content)
```

#### 4. Compute File Hash
```python
# app/services/hash_service.py
hash_info = hash_service.compute_hash(file_content, "document.pdf")

# Returns:
# {
#   "hash_value": "a3f5...",  # SHA-256 hex
#   "hash_algorithm": "SHA-256",
#   "file_size": 89280
# }
```

#### 5. Build SignedAttributes (DTBS)
```python
# app/services/signature_service.py
file_hash_bytes = bytes.fromhex(hash_info.hash_value)

signed_attrs = cms.CMSAttributes([
    cms.CMSAttribute({
        'type': cms.CMSAttributeType('content_type'),
        'values': [cms.ContentType('data')]
    }),
    cms.CMSAttribute({
        'type': cms.CMSAttributeType('message_digest'),
        'values': [core.OctetString(file_hash_bytes)]  # File hash embedded
    }),
    cms.CMSAttribute({
        'type': cms.CMSAttributeType('signing_time'),
        'values': [core.UTCTime(datetime.now(timezone.utc))]
    })
])
```

#### 6. Compute DTBS Digest
```python
# DER-encode SignedAttributes
signed_attrs_der = signed_attrs.dump()

# Hash the SignedAttributes (this is what InfoCert signs!)
dtbs_digest = hashlib.sha256(signed_attrs_der).digest()
dtbs_digest_b64 = base64.b64encode(dtbs_digest).decode('ascii')
```

#### 7. Send to InfoCert API
```python
# Create mTLS session
session = requests.Session()
session.cert = (client_cert_path, client_key_path)
session.verify = ca_cert_path

# Build request payload
payload = {
    "applicationId": "ifcer-batch-service",
    "pin": settings.infocert_pin,
    "authorization": {
        "sat": settings.infocert_sat
    },
    "hashSignatures": [{
        "requestId": "file-document.pdf",
        "hash": dtbs_digest_b64,  # ← DTBS digest, not file hash!
        "withTimestamp": True
    }]
}

# Send request
response = session.post(
    f"{api_url}/certificates/{cert_id}/sign",
    json=payload,
    headers={
        "Authorization": f"Bearer {sat_token}",
        "X-signer-id": signer_id,
        "Content-Type": "application/json"
    },
    timeout=120
)
```

#### 8. Parse InfoCert Response
```python
response_data = response.json()
signature_result = response_data["signatureResult"][0]

# Extract signature bytes
raw_signature_b64 = signature_result["signedDocument"]["content"]
raw_signature_bytes = base64.b64decode(raw_signature_b64)

# Extract timestamp (if present)
timestamp_b64 = signature_result["signedTimestamp"]["content"]
timestamp_bytes = base64.b64decode(timestamp_b64)
```

#### 9. Fetch Signing Certificate
```python
# app/services/certificate_service.py
cert_der_bytes = cert_service.get_signing_certificate_bytes()

# This fetches the X.509 certificate from InfoCert API
# GET /certificates/{cert_id}
```

#### 10. Build P7M File
```python
# app/services/p7m_service.py
p7m_bytes = p7m_service.create_p7m_from_signature(
    file_content=file_content,           # Original file to embed
    signature_bytes=raw_signature_bytes,  # InfoCert's signature
    cert_der_bytes=cert_der_bytes,        # X.509 certificate
    signed_attributes=signed_attrs,       # SignedAttributes we built
    timestamp_bytes=timestamp_bytes       # RFC 3161 timestamp
)
```

#### 11. Validate P7M (Optional Testing)
```python
# app/services/validation_service.py
validation_result = validation_service.validate_signature(
    original_file_content=file_content,
    p7m_file=p7m_bytes
)

# Checks:
# ✓ P7M structure valid
# ✓ Embedded file matches original
# ✓ Signature verification (RSA + SHA256)
# ✓ Certificate validity
```

#### 12. Upload to S3
```python
# Upload P7M file
p7m_key = "signed/document.p7m"
s3_service.upload_file(
    file_content=p7m_bytes,
    destination_key=p7m_key,
    content_type="application/pkcs7-mime"
)
```

#### 13. Save Metadata to DynamoDB
```python
# app/services/dynamodb_service.py
dynamodb_service.save_certification(
    file_key="uploads/document.pdf",
    file_hash=hash_info.hash_value,
    hash_algorithm="SHA-256",
    digital_signature=raw_signature_b64[:100],
    vendor_timestamp=signing_time,
    signed_file_key=p7m_key,
    file_size=89280,
    signed_file_size=len(p7m_bytes),
    status="completed"
)
```

---

## Signature Creation Process

### Code Implementation: `app/services/signature_service.py`

```python
def sign_file_hash(
    self,
    signature_request: SignatureRequest,
    original_file_content: bytes
) -> SignatureResponse:
    """
    Sign file using InfoCert hashSignatures API with DTBS workflow.

    Returns P7M file with original content embedded.
    """

    # STEP 1: Build SignedAttributes (DTBS)
    file_hash_bytes = bytes.fromhex(signature_request.file_hash)

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

    # STEP 2: Compute DTBS digest (hash of SignedAttributes)
    signed_attrs_der = signed_attrs.dump()
    dtbs_digest = hashlib.sha256(signed_attrs_der).digest()
    dtbs_digest_b64 = base64.b64encode(dtbs_digest).decode('ascii')

    # STEP 3: Create mTLS session
    session = self.cert_service._create_session()

    # STEP 4: Send DTBS digest to InfoCert
    payload = {
        "applicationId": "ifcer-batch-service",
        "pin": settings.infocert_pin,
        "authorization": {"sat": settings.infocert_sat},
        "hashSignatures": [{
            "requestId": f"file-{signature_request.filename}",
            "hash": dtbs_digest_b64,  # ← DTBS digest!
            "withTimestamp": True
        }]
    }

    response = session.post(
        f"{self.api_url}/certificates/{settings.infocert_certificate_id}/sign",
        json=payload,
        headers={
            "Authorization": f"Bearer {settings.infocert_sat}",
            "X-signer-id": settings.infocert_credential_id,
            "Content-Type": "application/json"
        },
        timeout=self.timeout
    )

    # STEP 5: Extract signature and timestamp
    response_data = response.json()
    result = response_data["signatureResult"][0]

    raw_signature_b64 = result["signedDocument"]["content"]
    raw_signature_bytes = base64.b64decode(raw_signature_b64)

    timestamp_b64 = result.get("signedTimestamp", {}).get("content", "")
    timestamp_bytes = base64.b64decode(timestamp_b64) if timestamp_b64 else None

    # STEP 6: Fetch certificate
    cert_der_bytes = self.cert_service.get_signing_certificate_bytes()

    # STEP 7: Build P7M
    p7m_bytes = self.p7m_service.create_p7m_from_signature(
        file_content=original_file_content,
        signature_bytes=raw_signature_bytes,
        cert_der_bytes=cert_der_bytes,
        signed_attributes=signed_attrs,  # Include DTBS
        timestamp_bytes=timestamp_bytes
    )

    return SignatureResponse(
        signature=raw_signature_b64[:100],
        timestamp=datetime.now(timezone.utc),
        manifest_content=None,
        p7m_content=p7m_bytes
    )
```

---

## P7M Building Process

### Code Implementation: `app/services/p7m_service.py`

```python
def create_p7m_from_signature(
    self,
    file_content: bytes,
    signature_bytes: bytes,
    cert_der_bytes: bytes,
    signed_attributes: 'cms.CMSAttributes',
    timestamp_bytes: bytes = None
) -> bytes:
    """
    Build complete P7M/CAdES file with DTBS (SignedAttributes).

    Structure:
      ContentInfo
        └── SignedData
            ├── encapContentInfo (embedded file)
            ├── certificates (X.509 cert)
            └── signerInfos
                └── SignerInfo
                    ├── signedAttrs (DTBS)
                    ├── signature (from InfoCert)
                    └── unsignedAttrs (timestamp)
    """

    # Parse certificate
    cert = asn1_x509.Certificate.load(cert_der_bytes)

    # Build ContentInfo with EMBEDDED FILE
    encap_content_info = cms.ContentInfo({
        'content_type': cms.ContentType('data'),
        'content': core.OctetString(file_content)  # ← File embedded!
    })

    # Extract signer identifier from certificate
    issuer = cert['tbs_certificate']['issuer']
    serial_number = cert['tbs_certificate']['serial_number']

    signer_identifier = cms.SignerIdentifier(
        name='issuer_and_serial_number',
        value=cms.IssuerAndSerialNumber({
            'issuer': issuer,
            'serial_number': serial_number
        })
    )

    # Algorithms
    digest_algorithm = algos.DigestAlgorithm({
        'algorithm': '2.16.840.1.101.3.4.2.1'  # SHA-256
    })

    signature_algorithm = algos.SignedDigestAlgorithm({
        'algorithm': '1.2.840.113549.1.1.11'  # sha256WithRSAEncryption
    })

    # Build SignerInfo with SignedAttributes
    signer_info_dict = {
        'version': 'v1',
        'sid': signer_identifier,
        'digest_algorithm': digest_algorithm,
        'signed_attrs': signed_attributes,  # ← DTBS included!
        'signature_algorithm': signature_algorithm,
        'signature': core.OctetString(signature_bytes)
    }

    # Add timestamp token as unsigned attribute
    if timestamp_bytes:
        unsigned_attrs = cms.CMSAttributes([
            cms.CMSAttribute({
                'type': cms.CMSAttributeType('1.2.840.113549.1.9.16.2.14'),
                'values': [cms.ContentInfo.load(timestamp_bytes)]
            })
        ])
        signer_info_dict['unsigned_attrs'] = unsigned_attrs

    signer_info = cms.SignerInfo(signer_info_dict)

    # Build SignedData
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

    # DER-encode to create P7M file
    p7m_bytes = content_info.dump()

    return p7m_bytes
```

---

## Validation Process

### What Gets Validated?

The validation service performs the same checks that Italian regulatory authorities would perform:

1. **P7M Structure Validation**
   - Parse PKCS#7/CMS structure
   - Verify contentType is signedData
   - Count certificates and signers

2. **Embedded File Extraction**
   - Extract file from encapContentInfo
   - Verify content exists (ENVELOPED signature)

3. **File Integrity Check**
   - Compare extracted file with original
   - Byte-for-byte comparison

4. **Cryptographic Signature Verification**
   - Extract SignedAttributes (DTBS)
   - Extract signature bytes
   - Extract public key from certificate
   - Verify: RSA_VERIFY(signature, SignedAttributes, public_key)

5. **File Hash Verification**
   - Extract messageDigest from SignedAttributes
   - Compute SHA-256 of extracted file
   - Compare hashes

6. **Certificate Validation**
   - Check validity dates (notBefore, notAfter)
   - Verify certificate is not expired

### Code Implementation: `app/services/validation_service.py`

```python
def validate_signature(
    self,
    original_file_content: bytes,
    p7m_file: bytes
) -> Dict[str, Any]:
    """
    Comprehensive P7M validation with DTBS workflow.
    """

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
        "errors": []
    }

    # CHECK 1: Verify P7M structure
    structure_valid, p7m_data = self._verify_p7m_structure(p7m_file)
    result["checks"]["signature_structure"] = structure_valid

    if not structure_valid:
        result["errors"].append("Invalid P7M structure")
        return result

    # CHECK 2: Extract embedded file
    extracted_file, extracted_ok = self._extract_embedded_file(p7m_file)
    result["checks"]["embedded_file_extracted"] = extracted_ok

    if not extracted_ok:
        result["errors"].append("Failed to extract embedded file")
        return result

    # CHECK 3: Verify file match
    file_match = (extracted_file == original_file_content)
    result["checks"]["embedded_file_match"] = file_match

    if not file_match:
        result["errors"].append("Embedded file does not match original")
        return result

    # CHECK 4: Verify signature cryptographically
    sig_verified, cert_info = self._verify_signature_cryptographic(
        extracted_file,
        p7m_file
    )
    result["checks"]["signature_verified"] = sig_verified
    result["certificate_info"] = cert_info

    if not sig_verified:
        result["errors"].append("Cryptographic signature verification failed")
        return result

    # CHECK 5: Validate certificate
    cert_valid, cert_details = self._validate_certificate(cert_info)
    result["checks"]["certificate_valid"] = cert_valid

    if not cert_valid:
        result["errors"].append("Certificate validation failed")
        return result

    # All checks passed!
    result["valid"] = True
    return result
```

### Cryptographic Verification Details

```python
def _verify_signature_cryptographic(
    self,
    file_content: bytes,
    p7m_file: bytes
) -> Tuple[bool, Dict]:
    """
    Verify signature against SignedAttributes (DTBS).
    """

    # Parse P7M
    content_info = cms.ContentInfo.load(p7m_file)
    signed_data = content_info['content']

    # Extract certificate
    cert_asn1 = signed_data['certificates'][0].chosen
    cert_der = cert_asn1.dump()
    cert = x509.load_der_x509_certificate(cert_der, default_backend())

    # Extract signer info
    signer_info = signed_data['signer_infos'][0]
    signature = signer_info['signature'].native

    # Extract SignedAttributes (DTBS)
    signed_attrs = signer_info['signed_attrs']

    # DER-encode SignedAttributes with SET OF tag
    # Note: SignedAttributes are stored with implicit [0] tag,
    # but signature was computed over SET OF (0x31) tag
    signed_attrs_der = signed_attrs.dump()
    signed_attrs_der = b'\x31' + signed_attrs_der[1:]  # Replace tag

    # Verify signature
    public_key = cert.public_key()

    try:
        # The verify() method expects the original data (SignedAttributes)
        # It will hash it internally with SHA256 and verify
        public_key.verify(
            signature,
            signed_attrs_der,  # ← Pass SignedAttributes bytes
            padding.PKCS1v15(),
            hashes.SHA256()
        )

        # Verify file hash in SignedAttributes
        message_digest = None
        for attr in signed_attrs:
            if attr['type'].native == 'message_digest':
                message_digest = attr['values'][0].native
                break

        actual_file_hash = hashlib.sha256(file_content).digest()

        if message_digest != actual_file_hash:
            return False, {}

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

    except Exception:
        return False, {}
```

### Why Replace the Tag?

**Critical Detail**: SignedAttributes tag manipulation

When stored in SignerInfo, SignedAttributes use an **implicit tag [0]** (0xA0):
```
SignerInfo ::= SEQUENCE {
  ...
  signedAttrs [0] IMPLICIT SignedAttributes OPTIONAL,
  ...
}
```

But when computing the signature, RFC 5652 specifies:
> "A separate encoding of the signedAttrs field is performed for message digest calculation. The IMPLICIT [0] tag in the signedAttrs is not used for the DER encoding, rather an explicit SET OF tag is used."

So we replace:
- **0xA0** (CONTEXT tag, class 2, constructed, tag 0)
- with **0x31** (UNIVERSAL SET OF tag)

```python
signed_attrs_der = signed_attrs.dump()           # Has 0xA0 tag
signed_attrs_der = b'\x31' + signed_attrs_der[1:]  # Replace with 0x31
```

---

## Key Algorithms and OIDs

### Object Identifiers (OIDs)

```
Content Types:
  data                 = 1.2.840.113549.1.7.1
  signedData           = 1.2.840.113549.1.7.2
  envelopedData        = 1.2.840.113549.1.7.3
  timestampedData      = 1.2.840.113549.1.9.16.1.31

Hash Algorithms:
  SHA-256              = 2.16.840.1.101.3.4.2.1
  SHA-384              = 2.16.840.1.101.3.4.2.2
  SHA-512              = 2.16.840.1.101.3.4.2.3

Signature Algorithms:
  sha256WithRSAEncryption = 1.2.840.113549.1.1.11
  sha384WithRSAEncryption = 1.2.840.113549.1.1.12
  sha512WithRSAEncryption = 1.2.840.113549.1.1.13

CMS Attributes:
  contentType          = 1.2.840.113549.1.9.3
  messageDigest        = 1.2.840.113549.1.9.4
  signingTime          = 1.2.840.113549.1.9.5
  timeStampToken       = 1.2.840.113549.1.9.16.2.14

CAdES Attributes:
  signingCertificate   = 1.2.840.113549.1.9.16.2.12
  signingCertificateV2 = 1.2.840.113549.1.9.16.2.47
```

### Cryptographic Parameters

**Hash Algorithm**: SHA-256
- Output: 256 bits (32 bytes)
- Hex: 64 characters
- Base64: 44 characters (with padding)

**Signature Algorithm**: RSA with SHA-256 (sha256WithRSAEncryption)
- Key size: 2048 bits (256 bytes)
- Signature size: 256 bytes (2048 bits)
- Padding: PKCS#1 v1.5

**Certificate**: X.509 v3
- Format: DER-encoded
- Typical size: 1-2 KB

**Timestamp Token**: RFC 3161 TimeStampToken
- Format: ContentInfo with signedData
- Typical size: 3-5 KB

---

## Authentication and Security

### Multi-Factor Authentication to InfoCert

InfoCert API requires **4 layers of authentication**:

#### 1. mTLS (Mutual TLS)
```python
session = requests.Session()
session.cert = (
    '/path/to/client_cert.pem',  # Client certificate
    '/path/to/client_key.pem'    # Client private key
)
session.verify = '/path/to/ca_cert.pem'  # InfoCert CA certificate
```

**Purpose**: Cryptographically prove client identity via X.509 certificates

#### 2. SAT Token (Bearer Token)
```python
headers = {
    "Authorization": f"Bearer {settings.infocert_sat}"
}
```

**Purpose**: Application-level authorization token

#### 3. X-Signer-ID Header
```python
headers = {
    "X-signer-id": settings.infocert_credential_id
}
```

**Purpose**: Identify which signing credential to use

#### 4. PIN in Request Body
```python
payload = {
    "pin": settings.infocert_pin,
    ...
}
```

**Purpose**: User authentication (like ATM PIN for signing)

### Security Best Practices

1. **Never log sensitive data**
   - PINs
   - SAT tokens
   - Private keys

2. **Use environment variables**
   ```bash
   INFOCERT_PIN=********
   INFOCERT_SAT=********
   ```

3. **Secure certificate storage**
   ```bash
   chmod 600 client_key.pem
   chmod 644 client_cert.pem
   ```

4. **Validate all inputs**
   - File size limits
   - Hash format validation
   - Certificate expiration checks

5. **Log all operations**
   - Audit trail for compliance
   - Error tracking
   - Performance monitoring

---

## Summary

### What We Built

A complete digital signature service implementing:

✅ **DTBS (Data To Be Signed) Workflow**
- Build SignedAttributes with file hash
- Compute DTBS digest
- Send to InfoCert for signing

✅ **CAdES-BES Compliant P7M Files**
- PKCS#7/CMS SignedData structure
- Original file embedded (ENVELOPED)
- SignedAttributes included
- Certificate chain
- RFC 3161 timestamps

✅ **Cryptographic Validation**
- Signature verification
- Certificate validation
- File integrity checks
- Regulatory-compliant verification

### Key Takeaways

1. **SignedAttributes are critical**: They're what gets signed, not the file hash directly

2. **DTBS = SignedAttributes**: The Data To Be Signed is the DER-encoded SignedAttributes structure

3. **Tag replacement is necessary**: Change 0xA0 to 0x31 for signature verification

4. **InfoCert signs the DTBS digest**: We hash the SignedAttributes and send that hash

5. **Validation must verify SignedAttributes**: Not just the file, but the complete cryptographic chain

### Standards Compliance

- ✅ ETSI EN 319 102-1 (CAdES)
- ✅ RFC 5652 (CMS/PKCS#7)
- ✅ RFC 3161 (Timestamps)
- ✅ Italian AgID regulations for digital signatures

---

## Files Reference

### Service Files
- `app/services/signature_service.py` - InfoCert API integration, DTBS building
- `app/services/p7m_service.py` - P7M/CAdES file creation
- `app/services/validation_service.py` - Signature validation
- `app/services/certificate_service.py` - Certificate management, mTLS
- `app/services/hash_service.py` - File hashing (SHA-256)
- `app/services/s3_service.py` - AWS S3 operations
- `app/services/dynamodb_service.py` - Metadata persistence

### Router Files
- `app/routers/processing_routes.py` - Processing endpoints (/process, /recertify)
- `app/routers/files_routes.py` - File query and download endpoints

### Configuration
- `app/config.py` - Settings and environment variables
- `.env` - Secrets (PIN, SAT, credentials)

---

## Glossary

**CAdES**: CMS Advanced Electronic Signatures
**CMS**: Cryptographic Message Syntax (same as PKCS#7)
**DTBS**: Data To Be Signed (SignedAttributes in our case)
**P7M**: File extension for PKCS#7 SignedData with embedded content
**P7S**: File extension for PKCS#7 SignedData detached signature
**PKCS#7**: Public-Key Cryptography Standards #7 (signature format)
**mTLS**: Mutual TLS (both client and server authenticate)
**SAT**: Service Access Token (InfoCert bearer token)
**OID**: Object Identifier (unique ID for algorithms/attributes)
**DER**: Distinguished Encoding Rules (binary ASN.1 encoding)
**ASN.1**: Abstract Syntax Notation One (data structure definition language)
**RFC 3161**: Time-Stamp Protocol
**RFC 5652**: Cryptographic Message Syntax
**ETSI**: European Telecommunications Standards Institute
**AgID**: Agenzia per l'Italia Digitale (Italian Digital Agency)

---

**Document Version**: 1.0
**Last Updated**: 2025-11-14
**Author**: InfoCert Batch Service Team
