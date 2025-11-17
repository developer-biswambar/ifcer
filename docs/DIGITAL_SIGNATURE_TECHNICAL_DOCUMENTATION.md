# Digital Signature and P7M File Creation - Technical Documentation

**Document Version**: 1.0
**Last Updated**: 2025-11-17
**Audience**: New developers, security engineers, technical architects

---

## Table of Contents

1. [Digital Signatures Fundamentals](#1-digital-signatures-fundamentals)
2. [CAdES Standard Overview](#2-cades-standard-overview)
3. [P7M/PKCS#7 File Structure](#3-p7mpkcs7-file-structure)
4. [Implementation Architecture](#4-implementation-architecture)
5. [File Signing Workflow](#5-file-signing-workflow)
6. [P7M File Creation Process](#6-p7m-file-creation-process)
7. [Signature Verification Process](#7-signature-verification-process)
8. [Code Examples and Implementation Details](#8-code-examples-and-implementation-details)
9. [Troubleshooting and Debugging](#9-troubleshooting-and-debugging)

---

## 1. Digital Signatures Fundamentals

### 1.1 What is a Digital Signature?

A digital signature is a cryptographic mechanism that provides:
- **Authentication**: Verifies the identity of the signer
- **Integrity**: Ensures the document hasn't been modified
- **Non-repudiation**: Signer cannot deny having signed the document

### 1.2 How Digital Signatures Work

```
┌─────────────────────────────────────────────────────────────┐
│                    SIGNING PROCESS                           │
└─────────────────────────────────────────────────────────────┘

Original Document
      ↓
   [Hash Function (SHA-256)]
      ↓
Document Hash (32 bytes)
      ↓
   [Sign with Private Key]
      ↓
Digital Signature
      ↓
Attach to Document
      ↓
Signed Document (.p7m file)
```

### 1.3 Key Cryptographic Components

**Hash Function (SHA-256)**:
- Input: Document of any size
- Output: Fixed 256-bit (32-byte) hash
- Properties: One-way, collision-resistant, deterministic
- Example: `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`

**Asymmetric Cryptography (RSA)**:
- **Private Key**: Used to create signature (kept secret)
- **Public Key**: Used to verify signature (shared publicly)
- **Key Size**: 2048-bit minimum (256 bytes)
- **Algorithm**: RSA with PKCS#1 v1.5 padding

**Digital Certificate (X.509)**:
- Contains: Public key + Identity information
- Issued by: Certificate Authority (CA)
- Purpose: Binds public key to an identity
- Format: DER-encoded ASN.1 structure

---

## 2. CAdES Standard Overview

### 2.1 What is CAdES?

**CAdES** = **C**MS **Ad**vanced **E**lectronic **S**ignatures

- **Standard**: ETSI EN 319 122-1
- **Purpose**: EU-recognized digital signatures with legal validity
- **Based on**: CMS (Cryptographic Message Syntax) - RFC 5652
- **Compliance**: eIDAS Regulation (EU 910/2014)

### 2.2 CAdES Signature Levels

| Level | Name | Description | Our Implementation |
|-------|------|-------------|-------------------|
| **CAdES-B** | Basic | Minimum required attributes | ❌ Not used |
| **CAdES-BES** | Basic Electronic Signature | Adds signing-certificate-v2 | ✅ **Used** |
| **CAdES-T** | with Timestamp | Adds trusted timestamp | ✅ Optional |
| **CAdES-LT** | Long Term | Adds validation data | ❌ Not used |
| **CAdES-LTA** | Long Term Archive | Adds archive timestamp | ❌ Not used |

**We implement CAdES-BES** (Basic Electronic Signature with signing-certificate-v2 attribute).

### 2.3 CAdES-BES Required Attributes

CAdES-BES requires these **SignedAttributes** (part of DTBS):

1. **content-type** (OID: 1.2.840.113549.1.9.3)
   - Identifies the type of content being signed
   - Value: `data` (OID 1.2.840.113549.1.7.1)

2. **message-digest** (OID: 1.2.840.113549.1.9.4)
   - Hash of the original document
   - Value: SHA-256 hash (32 bytes)

3. **signing-time** (OID: 1.2.840.113549.1.9.5)
   - Time when signature was created
   - Value: UTC timestamp

4. **signing-certificate-v2** (OID: 1.2.840.113549.1.9.16.2.47) ⭐ **MANDATORY for CAdES**
   - Hash of the signing certificate
   - Value: SHA-256 hash of signer's certificate
   - Purpose: Prevents certificate substitution attacks

---

## 3. P7M/PKCS#7 File Structure

### 3.1 What is P7M?

**P7M** is a file extension for **PKCS#7** (Public Key Cryptography Standards #7) signed data.

- **Format**: ASN.1 DER-encoded binary
- **Container**: Stores document + signature + certificate
- **Standard**: RFC 5652 (CMS), RFC 2315 (PKCS#7)
- **File Extension**: `.p7m`

### 3.2 P7M vs P7S

| Aspect | P7M (Enveloped) | P7S (Detached) |
|--------|----------------|----------------|
| **Content** | Document embedded inside | Signature only, document separate |
| **File Size** | Larger (includes document) | Smaller (signature metadata only) |
| **Usage** | Italian PA, InfoCert | Email S/MIME, PDF signatures |
| **Verification** | Self-contained | Requires original document |
| **Our Implementation** | ✅ Used | ❌ Not used |

**Why we use P7M (enveloped)**:
- InfoCert API requires CAdES-BES with embedded content
- Italian regulations require self-contained signature files
- Simplifies verification (no need to manage separate files)

### 3.3 P7M File Structure (ASN.1)

```
ContentInfo ::= SEQUENCE {
  contentType ContentType,        -- signed-data (OID 1.2.840.113549.1.7.2)
  content [0] EXPLICIT SignedData OPTIONAL
}

SignedData ::= SEQUENCE {
  version CMSVersion,              -- v1
  digestAlgorithms DigestAlgorithmIdentifiers,  -- SHA-256
  encapContentInfo EncapsulatedContentInfo,     -- ORIGINAL FILE EMBEDDED HERE
  certificates [0] IMPLICIT CertificateSet OPTIONAL,  -- Signer's certificate
  crls [1] IMPLICIT RevocationInfoChoices OPTIONAL,   -- Not used
  signerInfos SignerInfos           -- Signature + SignedAttributes
}

EncapsulatedContentInfo ::= SEQUENCE {
  eContentType ContentType,        -- data (OID 1.2.840.113549.1.7.1)
  eContent [0] EXPLICIT OCTET STRING OPTIONAL  -- ⭐ ORIGINAL FILE BYTES HERE
}

SignerInfo ::= SEQUENCE {
  version CMSVersion,              -- v1
  sid SignerIdentifier,            -- Issuer + Serial Number
  digestAlgorithm DigestAlgorithmIdentifier,  -- SHA-256
  signedAttrs [0] IMPLICIT SignedAttributes,  -- ⭐ DTBS (Data To Be Signed)
  signatureAlgorithm SignatureAlgorithmIdentifier,  -- sha256WithRSAEncryption
  signature SignatureValue,        -- ⭐ SIGNATURE BYTES FROM INFOCERT
  unsignedAttrs [1] IMPLICIT UnsignedAttributes OPTIONAL  -- Timestamp token
}
```

### 3.4 Key Components Explained

**EncapsulatedContentInfo (eContent)**:
- Contains the **original file bytes** embedded inside the P7M
- Allows verification without needing the original file separately
- Example: A 1MB PDF becomes a ~1MB P7M file (plus signature overhead)

**SignedAttributes (signedAttrs)**:
- This is the **DTBS** (Data To Be Signed)
- Contains: content-type, message-digest, signing-time, signing-certificate-v2
- **The signature signs the DTBS**, not the file directly!
- Must be DER-encoded before hashing

**SignatureValue (signature)**:
- The actual **cryptographic signature bytes**
- Created by: `RSA_Sign(PrivateKey, SHA256(SignedAttributes))`
- Received from InfoCert API
- Typically 256 bytes for RSA 2048-bit

---

## 4. Implementation Architecture

### 4.1 Service Overview

Our implementation uses a **layered service architecture**:

```
┌──────────────────────────────────────────────────────────┐
│                  SignatureService                         │
│  • Orchestrates the signing workflow                     │
│  • Calls InfoCert API                                    │
│  • Coordinates certificate and P7M services              │
└──────────────────────────────────────────────────────────┘
           ↓                                    ↓
┌─────────────────────────┐      ┌──────────────────────────┐
│   CertificateService    │      │      P7MService          │
│  • Loads mTLS certs     │      │  • Builds P7M structure  │
│  • Creates mTLS session │      │  • Encodes ASN.1/DER     │
│  • Fetches signing cert│      │  • Adds timestamp token  │
└─────────────────────────┘      └──────────────────────────┘
```

### 4.2 File Locations

- **SignatureService**: `app/services/signature_service.py`
- **P7MService**: `app/services/p7m_service.py`
- **CertificateService**: `app/services/certificate_service.py`
- **ValidationService**: `app/services/validation_service.py`

### 4.3 Dependencies

```python
# ASN.1 encoding/decoding
from asn1crypto import cms, x509, core, algos

# Cryptography
import hashlib  # SHA-256 hashing
import base64   # Base64 encoding

# HTTP client
import requests  # InfoCert API calls with mTLS
```

---

## 5. File Signing Workflow

### 5.1 High-Level Workflow

```
┌─────────────────────────────────────────────────────────────────────┐
│                    INFOCERT HASHSIGNATURES WORKFLOW                  │
└─────────────────────────────────────────────────────────────────────┘

[1] Fetch Signing Certificate
    ↓
    Get InfoCert's public certificate
    Extract certificate bytes (DER format)
    Compute certificate hash (SHA-256)

[2] Build SignedAttributes (DTBS)
    ↓
    Create content-type attribute
    Create message-digest attribute (hash of ORIGINAL FILE)
    Create signing-time attribute
    Create signing-certificate-v2 attribute (hash of certificate)
    Combine into CMSAttributes structure

[3] Compute DTBS Digest
    ↓
    DER-encode SignedAttributes
    Compute SHA-256 hash of DER bytes
    Base64-encode the hash

[4] Send to InfoCert API
    ↓
    Establish mTLS connection (client certificate authentication)
    Send DTBS digest (NOT file hash!) to InfoCert
    InfoCert signs the DTBS digest with their HSM
    Receive: signature bytes + optional timestamp token

[5] Build P7M File
    ↓
    Create EncapsulatedContentInfo (embed original file)
    Create SignerInfo (signature + SignedAttributes)
    Add certificate to CertificateSet
    Add timestamp token (if present)
    Encode entire structure as DER
    Return .p7m file
```

### 5.2 Detailed Step-by-Step Process

#### Step 1: Fetch Signing Certificate

**Code**: `signature_service.py:172-180`

```python
# Fetch the certificate that will sign the document
cert_der_bytes = self.cert_service.get_signing_certificate_bytes()
cert = asn1_x509.Certificate.load(cert_der_bytes)

# Compute certificate hash for signing-certificate-v2 attribute
cert_hash = hashlib.sha256(cert_der_bytes).digest()
```

**Purpose**:
- Get InfoCert's public certificate (contains their public key)
- This certificate will be embedded in the P7M file
- Certificate hash is included in SignedAttributes (CAdES requirement)

**Certificate Caching**:
- Certificates are cached for 1 hour (configurable via `CERTIFICATE_CACHE_TTL_SECONDS`)
- Reduces API calls: 100 files = 1 certificate fetch instead of 100

#### Step 2: Build SigningCertificateV2 (ASN.1 Manual Construction)

**Code**: `signature_service.py:182-207`

```python
# Build SigningCertificateV2 manually as DER bytes (RFC 5035)
# SigningCertificateV2 ::= SEQUENCE {
#     certs SEQUENCE OF ESSCertIDv2
# }
# ESSCertIDv2 ::= SEQUENCE {
#     hashAlgorithm AlgorithmIdentifier DEFAULT {algorithm id-sha256},
#     certHash Hash (OCTET STRING)
# }

# Build AlgorithmIdentifier for SHA-256: SEQUENCE { OID, NULL }
hash_alg = bytes.fromhex('300d06096086480165030402010500')

# Build certHash: OCTET STRING containing SHA-256 hash (32 bytes)
cert_hash_octet = bytes.fromhex('0420') + cert_hash  # 0x04 = OCTET STRING, 0x20 = 32 bytes

# Build ESSCertIDv2: SEQUENCE { hashAlgorithm, certHash }
ess_cert_id_v2_content = hash_alg + cert_hash_octet
ess_cert_id_v2 = bytes.fromhex('30') + bytes([len(ess_cert_id_v2_content)]) + ess_cert_id_v2_content

# Build SEQUENCE OF ESSCertIDv2
certs_seq = bytes.fromhex('30') + bytes([len(ess_cert_id_v2)]) + ess_cert_id_v2

# Build SigningCertificateV2: SEQUENCE { certs }
signing_cert_v2_der = bytes.fromhex('30') + bytes([len(certs_seq)]) + certs_seq
```

**Why Manual Construction?**:
- `asn1crypto` library doesn't have native support for `SigningCertificateV2`
- We manually build the DER bytes according to RFC 5035 specification
- Result: DER-encoded `SigningCertificateV2` structure

**ASN.1 Tags**:
- `0x30`: SEQUENCE tag
- `0x04`: OCTET STRING tag
- `0x20`: Length 32 (for SHA-256 hash)

#### Step 3: Build SignedAttributes (DTBS)

**Code**: `signature_service.py:209-237`

```python
file_hash_bytes = bytes.fromhex(signature_request.file_hash)

# Build SignedAttributes according to ETSI EN 319 122-1 (CAdES)
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
        'values': [core.Any.load(signing_cert_v2_der)]
    })
])
```

**Attributes Breakdown**:

1. **content-type**: `data` (OID 1.2.840.113549.1.7.1)
   - Indicates we're signing data (not encrypted data or other types)

2. **message-digest**: Hash of the **original file**
   - NOT the hash we send to InfoCert!
   - This is the hash of the actual document content
   - Used during verification to ensure file integrity

3. **signing-time**: Current UTC timestamp
   - When the signature was created
   - Format: UTCTime (YYMMDDHHMMSSZ)

4. **signing-certificate-v2**: Hash of the signer's certificate
   - Prevents attacker from substituting a different certificate
   - Mandatory for CAdES-BES compliance

#### Step 4: Compute DTBS Digest

**Code**: `signature_service.py:245-253`

```python
# DER encode SignedAttributes for hashing
signed_attrs_der = signed_attrs.dump()

# Compute SHA-256 hash of SignedAttributes
dtbs_digest = hashlib.sha256(signed_attrs_der).digest()

# Base64 encode for InfoCert API
dtbs_digest_b64 = base64.b64encode(dtbs_digest).decode('ascii')
```

**Critical Understanding**:
- ⚠️ **We DO NOT sign the original file directly!**
- ⚠️ **We sign the SignedAttributes (DTBS)!**
- The SignedAttributes contains the file hash (message-digest attribute)
- This is the **hashSignatures** workflow

**Why This Approach?**:
- InfoCert API operates in **HSM (Hardware Security Module)** mode
- HSM never receives the actual document (security best practice)
- HSM only signs the DTBS digest
- Prevents InfoCert from accessing sensitive document content

#### Step 5: Call InfoCert API

**Code**: `signature_service.py:256-287`

```python
# Create mTLS session
session = self.cert_service._create_session()

# Prepare API request payload
payload = {
    "applicationId": "ifcer-batch-service",
    "pin": settings.infocert_pin,
    "authorization": {
        "sat": settings.infocert_sat
    },
    "hashSignatures": [{
        "requestId": f"file-{signature_request.filename}",
        "hash": dtbs_digest_b64,  # ⭐ Send DTBS digest, NOT file hash!
        "withTimestamp": True
    }]
}

endpoint_url = f"{self.api_url}/certificates/{settings.infocert_certificate_id}/sign"

# Call API with mTLS + Bearer token + X-signer-id header
response_data = self._call_infocert_sign_api(
    session=session,
    endpoint_url=endpoint_url,
    payload=payload,
    filename=signature_request.filename
)
```

**Authentication (3-Factor)**:
1. **mTLS**: Client certificate authentication (session.cert)
2. **Bearer Token**: SAT (Signature Activation Token) in Authorization header
3. **X-signer-id**: Credential ID in custom header

**API Response**:
```json
{
  "signatureResult": [{
    "requestId": "file-example.pdf",
    "isOk": true,
    "signedDocument": {
      "content": "Base64-encoded signature bytes"
    },
    "signedTimestamp": {
      "content": "Base64-encoded RFC 3161 timestamp token"
    }
  }]
}
```

#### Step 6: Build P7M File

**Code**: `signature_service.py:326-335` → calls `p7m_service.py:21-154`

```python
p7m_bytes = self.p7m_service.create_p7m_from_signature(
    file_content=original_file_content,  # Embed original file
    signature_bytes=raw_signature_bytes,  # Signature of DTBS
    cert_der_bytes=cert_der_bytes,
    signed_attributes=signed_attrs,      # Include SignedAttributes
    timestamp_bytes=timestamp_bytes      # Include timestamp if present
)
```

See [Section 6: P7M File Creation Process](#6-p7m-file-creation-process) for detailed breakdown.

---

## 6. P7M File Creation Process

### 6.1 P7MService.create_p7m_from_signature()

**Code**: `app/services/p7m_service.py:21-154`

This method constructs the complete P7M file structure.

#### Step 1: Parse Certificate

```python
cert = asn1_x509.Certificate.load(cert_der_bytes)
```

- Load the DER-encoded certificate
- Extract issuer and serial number for SignerIdentifier

#### Step 2: Create EncapsulatedContentInfo (Embed Original File)

```python
encap_content_info = cms.ContentInfo({
    'content_type': cms.ContentType('data'),
    'content': core.OctetString(file_content)  # ⭐ Embed original file content
})
```

**This is where the original file is embedded!**
- The entire file content is wrapped in an OCTET STRING
- This makes the P7M file "enveloped" (self-contained)

#### Step 3: Build SignerIdentifier

```python
issuer = cert['tbs_certificate']['issuer']
serial_number = cert['tbs_certificate']['serial_number']

signer_identifier = cms.SignerIdentifier(
    name='issuer_and_serial_number',
    value=cms.IssuerAndSerialNumber({
        'issuer': issuer,
        'serial_number': serial_number
    })
)
```

**Purpose**:
- Links the signature to the specific certificate
- Verifier uses this to find the correct certificate in the CertificateSet

#### Step 4: Set Algorithms

```python
# SHA-256 digest algorithm
digest_algorithm = algos.DigestAlgorithm({
    'algorithm': '2.16.840.1.101.3.4.2.1'  # SHA-256 OID
})

# RSA with SHA-256 signature algorithm
signature_algorithm = algos.SignedDigestAlgorithm({
    'algorithm': '1.2.840.113549.1.1.11'  # sha256WithRSAEncryption OID
})
```

**OIDs (Object Identifiers)**:
- `2.16.840.1.101.3.4.2.1`: SHA-256
- `1.2.840.113549.1.1.11`: sha256WithRSAEncryption

#### Step 5: Build SignerInfo

```python
signer_info_dict = {
    'version': 'v1',
    'sid': signer_identifier,
    'digest_algorithm': digest_algorithm,
    'signed_attrs': signed_attributes,        # ⭐ The DTBS we built earlier
    'signature_algorithm': signature_algorithm,
    'signature': core.OctetString(signature_bytes)  # ⭐ Signature from InfoCert
}

# Add timestamp token as unsigned attribute if present
if timestamp_bytes:
    unsigned_attrs = cms.CMSAttributes([
        cms.CMSAttribute({
            'type': cms.CMSAttributeType('1.2.840.113549.1.9.16.2.14'),  # id-aa-timeStampToken
            'values': [cms.ContentInfo.load(timestamp_bytes)]
        })
    ])
    signer_info_dict['unsigned_attrs'] = unsigned_attrs

signer_info = cms.SignerInfo(signer_info_dict)
```

**Components**:
- **signed_attrs**: The SignedAttributes (DTBS) we created earlier
- **signature**: The signature bytes from InfoCert (signature of DTBS)
- **unsigned_attrs**: Timestamp token (RFC 3161) if provided

**Unsigned Attributes**:
- Not part of the signature (added after signing)
- Timestamp proves when the signature was created
- Helps with long-term validity (CAdES-T)

#### Step 6: Build SignedData Structure

```python
signed_data = cms.SignedData({
    'version': 'v1',
    'digest_algorithms': cms.DigestAlgorithms([digest_algorithm]),
    'encap_content_info': encap_content_info,  # ⭐ Original file embedded here
    'certificates': cms.CertificateSet([
        cms.CertificateChoices(name='certificate', value=cert)
    ]),
    'signer_infos': cms.SignerInfos([signer_info])
})
```

**Structure Summary**:
```
SignedData {
  version: v1
  digestAlgorithms: [SHA-256]
  encapContentInfo: {
    contentType: data
    content: [ORIGINAL FILE BYTES] ← The actual file is here!
  }
  certificates: [InfoCert's certificate]
  signerInfos: [{
    signedAttrs: [DTBS with file hash, signing-cert-v2, etc.]
    signature: [SIGNATURE BYTES FROM INFOCERT]
    unsignedAttrs: [Timestamp token]
  }]
}
```

#### Step 7: Wrap in ContentInfo and Encode

```python
# Wrap in ContentInfo
content_info = cms.ContentInfo({
    'content_type': cms.ContentType('signed_data'),
    'content': signed_data
})

# Encode to DER (this is the P7M file)
p7m_bytes = content_info.dump()
```

**Final Result**:
- DER-encoded binary data
- This is the `.p7m` file
- Can be saved directly to S3

### 6.2 P7M File Size

**Example**:
- Original file: 100 KB
- P7M overhead: ~6-8 KB
  - Certificate: ~2 KB
  - Signature: ~256 bytes
  - SignedAttributes: ~200 bytes
  - Timestamp: ~3-4 KB
  - ASN.1 structure: ~500 bytes
- **Total P7M**: ~106-108 KB

---

## 7. Signature Verification Process

### 7.1 Verification Workflow

**Code**: `app/services/validation_service.py`

```
┌─────────────────────────────────────────────────────────────┐
│                 P7M VERIFICATION WORKFLOW                    │
└─────────────────────────────────────────────────────────────┘

[1] Verify P7M Structure
    ↓
    Parse P7M as ASN.1/DER
    Check ContentInfo → SignedData structure
    Validate all required fields present

[2] Extract Embedded File
    ↓
    Navigate to encapContentInfo.eContent
    Extract OCTET STRING content
    This is the original file

[3] Verify Embedded File Matches Original
    ↓
    Compare extracted bytes with original file
    Byte-by-byte comparison
    If mismatch → INVALID

[4] Cryptographic Signature Verification
    ↓
    Extract signer certificate from P7M
    Extract SignedAttributes (DTBS)
    Extract signature bytes
    Compute: Hash(SignedAttributes)
    Verify: RSA_Verify(PublicKey, Hash, Signature)
    Check message-digest attribute matches file hash

[5] Certificate Validation
    ↓
    Check certificate not expired
    Check certificate chain (if available)
    Validate signing-certificate-v2 attribute

[6] All Checks Passed
    ↓
    Signature is VALID
```

### 7.2 Detailed Verification Steps

#### Step 1: Verify P7M Structure

**Code**: `validation_service.py:84-92`

```python
structure_valid, p7m_data = self._verify_p7m_structure(p7m_file)
```

**Checks**:
- ContentInfo has `signed_data` content type
- SignedData version is v1
- Has at least one SignerInfo
- Has encapContentInfo with embedded content

#### Step 2: Extract Embedded File

**Code**: `validation_service.py:94-104`

```python
def _extract_embedded_file(self, p7m_file: bytes) -> Tuple[Optional[bytes], bool]:
    try:
        content_info = cms.ContentInfo.load(p7m_file)
        signed_data = content_info['content']

        # Get embedded file from encapContentInfo
        encap_content = signed_data['encap_content_info']['content']

        if encap_content is None:
            return None, False

        # Extract bytes from OCTET STRING
        embedded_file = bytes(encap_content)
        return embedded_file, True
    except Exception as e:
        return None, False
```

#### Step 3: Verify File Match

**Code**: `validation_service.py:106-119`

```python
file_match = extracted_file == original_file_content
```

**Simple byte-by-byte comparison**:
- If files match → Continue
- If files don't match → INVALID (file was tampered with)

#### Step 4: Cryptographic Verification

**Code**: `validation_service.py:121-133`

This is the **most important step** - cryptographic validation.

```python
def _verify_signature_cryptographic(
    self,
    file_content: bytes,
    p7m_file: bytes
) -> Tuple[bool, Dict]:
    try:
        # Parse P7M
        content_info = cms.ContentInfo.load(p7m_file)
        signed_data = content_info['content']
        signer_info = signed_data['signer_infos'][0]

        # Extract certificate
        cert_der = signed_data['certificates'][0].chosen.dump()
        cert = x509.load_der_x509_certificate(cert_der, default_backend())

        # Extract SignedAttributes (DTBS)
        signed_attrs = signer_info['signed_attrs']
        signed_attrs_der = signed_attrs.dump()

        # Extract signature bytes
        signature_bytes = bytes(signer_info['signature'])

        # Verify signature
        public_key = cert.public_key()
        public_key.verify(
            signature_bytes,
            signed_attrs_der,
            padding.PKCS1v15(),
            hashes.SHA256()
        )

        # Verify message-digest attribute matches file hash
        message_digest_attr = self._get_attribute(signed_attrs, 'message_digest')
        expected_hash = bytes(message_digest_attr[0])
        actual_hash = hashlib.sha256(file_content).digest()

        if expected_hash != actual_hash:
            return False, {}

        return True, cert_info
    except Exception as e:
        return False, {}
```

**Verification Logic**:

1. **Extract Public Key** from certificate
2. **Extract SignedAttributes** (DTBS) as DER bytes
3. **Extract Signature Bytes** from signature field
4. **RSA Verify**: `RSA_Verify(PublicKey, SignedAttributes, Signature)`
   - If verification succeeds → Signature is cryptographically valid
   - If verification fails → Signature is INVALID

5. **Verify message-digest**:
   - Extract `message-digest` attribute from SignedAttributes
   - Compute actual hash of the file
   - Compare: If they match → File hasn't been modified

#### Step 5: Certificate Validation

**Code**: `validation_service.py:136-145`

```python
def _validate_certificate(self, cert_info: Dict) -> Tuple[bool, Dict]:
    try:
        # Check certificate expiration
        not_before = cert_info.get('not_before')
        not_after = cert_info.get('not_after')
        now = datetime.now(timezone.utc)

        if now < not_before or now > not_after:
            return False, {"error": "Certificate expired or not yet valid"}

        return True, {"status": "valid"}
    except Exception as e:
        return False, {"error": str(e)}
```

---

## 8. Code Examples and Implementation Details

### 8.1 Single File Signing

**Code**: `signature_service.py:124-369`

```python
# Create signature service
signature_service = SignatureService()

# Prepare signature request
signature_request = SignatureRequest(
    filename="example.pdf",
    file_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    hash_algorithm="sha256"
)

# Load original file content
with open("example.pdf", "rb") as f:
    original_file_content = f.read()

# Sign the file
signature_response = signature_service.sign_file_hash(
    signature_request,
    original_file_content
)

# Save P7M file
with open("example.pdf.p7m", "wb") as f:
    f.write(signature_response.p7m_content)
```

### 8.2 Batch Signing

**Code**: `signature_service.py:371-617`

**Performance Optimization**:
- Single file: 100 files = 100 API calls
- Batch: 100 files = 1 API call
- **99% reduction in API calls!**

```python
signature_service = SignatureService()

# Prepare batch requests
batch_requests = []
for file_path in file_paths:
    with open(file_path, "rb") as f:
        file_content = f.read()

    file_hash = hashlib.sha256(file_content).hexdigest()

    sig_request = SignatureRequest(
        filename=os.path.basename(file_path),
        file_hash=file_hash,
        hash_algorithm="sha256"
    )

    batch_requests.append((sig_request, file_content))

# Sign all files in single API call
results = signature_service.sign_file_hashes_batch(batch_requests)

# Process results
for sig_request, sig_response, file_content, error in results:
    if error is None:
        # Success - save P7M
        p7m_path = f"{sig_request.filename}.p7m"
        with open(p7m_path, "wb") as f:
            f.write(sig_response.p7m_content)
    else:
        # Error - log failure
        print(f"Failed: {sig_request.filename} - {error}")
```

**Batch Request Mapping**:
```python
# Each file gets a unique requestId
requestId = f"batch-{index}-{filename}"

# InfoCert response includes same requestId
# We match by requestId to map responses back to requests
result = next(
    (r for r in signature_results if r.get("requestId") == request_id),
    None
)
```

### 8.3 Verifying a P7M File

```python
validation_service = ValidationService()

# Load original file
with open("example.pdf", "rb") as f:
    original_file = f.read()

# Load P7M file
with open("example.pdf.p7m", "rb") as f:
    p7m_file = f.read()

# Validate
result = validation_service.validate_signature(
    original_file_content=original_file,
    p7m_file=p7m_file
)

if result["valid"]:
    print("✓ Signature is VALID")
    print(f"Signer: {result['certificate_info']['subject']}")
    print(f"Signed at: {result['certificate_info']['not_before']}")
else:
    print("✗ Signature is INVALID")
    print(f"Errors: {result['errors']}")
```

---

## 9. Troubleshooting and Debugging

### 9.1 Common Issues

#### Issue 1: "Invalid P7M structure"

**Cause**: P7M file is corrupted or not properly formatted

**Debug**:
```python
# Try to parse P7M
from asn1crypto import cms

try:
    content_info = cms.ContentInfo.load(p7m_file)
    print("ContentType:", content_info['content_type'])

    signed_data = content_info['content']
    print("SignedData version:", signed_data['version'])
    print("Number of signers:", len(signed_data['signer_infos']))
except Exception as e:
    print(f"Parse error: {e}")
```

#### Issue 2: "Embedded file mismatch"

**Cause**: The file embedded in P7M doesn't match the original

**Debug**:
```python
# Extract and compare
content_info = cms.ContentInfo.load(p7m_file)
signed_data = content_info['content']
embedded = bytes(signed_data['encap_content_info']['content'])

print(f"Original size: {len(original_file)}")
print(f"Embedded size: {len(embedded)}")
print(f"Match: {original_file == embedded}")

# Check first/last bytes
print(f"Original first 32 bytes: {original_file[:32].hex()}")
print(f"Embedded first 32 bytes: {embedded[:32].hex()}")
```

#### Issue 3: "Signature verification failed"

**Cause**: Signature doesn't match SignedAttributes

**Debug**:
```python
# Check SignedAttributes hash
from asn1crypto import cms
import hashlib

content_info = cms.ContentInfo.load(p7m_file)
signed_data = content_info['content']
signer_info = signed_data['signer_infos'][0]

signed_attrs = signer_info['signed_attrs']
signed_attrs_der = signed_attrs.dump()

# This is what should have been signed
dtbs_hash = hashlib.sha256(signed_attrs_der).digest()
print(f"DTBS hash: {dtbs_hash.hex()}")

# Check message-digest attribute
for attr in signed_attrs:
    if attr['type'].dotted == '1.2.840.113549.1.9.4':  # message-digest
        msg_digest = bytes(attr['values'][0])
        print(f"message-digest attribute: {msg_digest.hex()}")

        # Verify against file
        file_hash = hashlib.sha256(original_file).digest()
        print(f"Actual file hash: {file_hash.hex()}")
        print(f"Match: {msg_digest == file_hash}")
```

#### Issue 4: "InfoCert API returns 401 Unauthorized"

**Cause**: Authentication failure (mTLS, SAT token, or X-signer-id)

**Debug**:
- Check logs for `[API CALL] UNAUTHORIZED` message
- Verify mTLS certificate is loaded: `[MTLS SETUP] ✓ Client cert path`
- Verify SSL verification is enabled: `SSL_VERIFY_ENABLED=true`
- Check SAT token is not expired
- Verify X-signer-id matches InfoCert credential

See: `docs/INFOCERT_MTLS_SECURITY_EVIDENCE.md`

### 9.2 Debugging Tools

#### ASN.1 Parser

```bash
# Dump P7M structure
openssl asn1parse -in example.pdf.p7m -inform DER

# Extract SignedData
openssl pkcs7 -in example.pdf.p7m -inform DER -print_certs -text
```

#### Extract Embedded File

```bash
# Extract original file from P7M
openssl smime -verify -in example.pdf.p7m -inform DER -noverify -out extracted.pdf
```

#### Verify Signature

```bash
# Verify P7M signature
openssl smime -verify -in example.pdf.p7m -inform DER -CAfile infocert_ca.pem
```

### 9.3 Logging

Our implementation logs at multiple levels:

**INFO**: High-level workflow steps
```
[SIGN START] File: example.pdf | Hash: e3b0c44298fc1c14... | Algorithm: sha256
[STEP 1/5] Certificate fetched: 1234 bytes
[STEP 2/5] SignedAttributes built with file hash and signing-certificate-v2
[STEP 3/5] DTBS digest computed: dGVzdA==...
[STEP 4/5] Sending DTBS digest to InfoCert for signing...
[STEP 5/5] P7M file created: 106000 bytes
[SIGN COMPLETE] File: example.pdf | Duration: 2.34s
```

**DEBUG**: Detailed technical information
```
[STEP 1/5] Certificate hash computed: a1b2c3d4...
[STEP 1/5] SigningCertificateV2 (SHA-256) DER built: 3030...
[STEP 2/5] Building SignedAttributes (DTBS) structure
[STEP 4/5] API URL: https://mtlsapistage.infocert.digital/signature/v1/...
[P7M CREATE] Building ContentInfo with ORIGINAL FILE embedded...
```

**ERROR**: Failures and exceptions
```
[API CALL] UNAUTHORIZED (401) - InfoCert rejected authentication
[ERROR] InfoCert signature failed: INVALID_PIN - PIN is incorrect
[VALIDATION] × Signature verification failed
```

---

## Summary

### Key Takeaways

1. **Digital Signatures** provide authentication, integrity, and non-repudiation

2. **CAdES-BES** is the EU-standard for qualified electronic signatures
   - Requires: content-type, message-digest, signing-time, signing-certificate-v2

3. **P7M Files** are PKCS#7 containers with:
   - Original file embedded (enveloped signature)
   - Signer's certificate
   - SignedAttributes (DTBS)
   - Cryptographic signature
   - Optional timestamp token

4. **hashSignatures Workflow**:
   - We DON'T sign the file directly
   - We sign the SignedAttributes (DTBS)
   - InfoCert never sees the actual document
   - InfoCert only signs the DTBS digest

5. **Verification** requires:
   - Extracting embedded file
   - Cryptographic signature verification
   - Certificate validation
   - File hash matching

### Further Reading

- **ETSI EN 319 122-1**: CAdES Digital Signatures
- **RFC 5652**: Cryptographic Message Syntax (CMS)
- **RFC 5035**: Enhanced Security Services (ESS) - SigningCertificateV2
- **RFC 3161**: Time-Stamp Protocol (TSP)
- **eIDAS Regulation**: EU 910/2014 - Electronic Identification

---

**Document Version**: 1.0
**Last Updated**: 2025-11-17
**Maintained By**: Development Team
