# P7M Implementation - Original File Embedded

## Overview

This implementation creates **P7M (PKCS#7/CAdES ENVELOPED)** signature files with the **ORIGINAL FILE EMBEDDED**.

## Architecture

### Workflow

```
1. Original File (e.g., document.txt)
   ↓
2. Compute SHA-256 hash → send to InfoCert
   ↓
3. InfoCert returns: RAW signature of hash + timestamp
   ↓
4. Fetch signing certificate from InfoCert
   ↓
5. Build P7M with:
   - Embedded content: ORIGINAL FILE
   - Signature: InfoCert's signature (signed the file hash)
   - Certificate: From InfoCert
   ↓
6. Save single file: document.p7m
```

### Result

**Single P7M file** containing everything:
- Original file content (embedded)
- Digital signature
- Signing certificate
- Timestamp

```
S3 Structure:
uploads/
└── document.txt         (original file)

signed/
└── document.p7m         (P7M with embedded document.txt)
```

## Key Components

### 1. SignatureService (`app/services/signature_service.py`)

**Method**: `sign_file_hash(signature_request, original_file_content)`

**Flow**:
1. Convert file hash to base64
2. Send original file hash to InfoCert `/certificates/{id}/sign`
3. Receive RAW signature bytes
4. Fetch certificate
5. Build P7M with original file embedded

**Key Change**: No manifest creation - signs original file hash directly

### 2. P7MService (`app/services/p7m_service.py`)

**Method**: `create_p7m_from_signature(file_content, signature_bytes, cert_der_bytes)`

**Creates**: PKCS#7 SignedData with ENVELOPED content

```python
encap_content_info = cms.ContentInfo({
    'content_type': cms.ContentType('data'),
    'content': core.OctetString(file_content)  # ← Original file embedded
})
```

### 3. ProcessingRoutes (`app/routers/processing_routes.py`)

**Endpoint**: `/recertify`, `/process`

**Flow**:
1. Download original file from S3
2. Compute hash
3. Call `signature_service.sign_file_hash(request, file_content)`
4. Upload single P7M file to `signed/{basename}.p7m`
5. Save metadata to DynamoDB

## Comparison: P7M vs P7S

| Aspect | P7M (ENVELOPED) ✅ Current | P7S (DETACHED) ❌ Not Used |
|--------|---------------------------|---------------------------|
| **Files** | 1 file (signature with embedded content) | 2 files (content + separate signature) |
| **Content** | Embedded in P7M | Separate from signature |
| **Storage** | `document.p7m` | `document.json` + `document.p7s` |
| **Verification** | Extract embedded file, verify signature | Load both files, verify signature |
| **Use Case** | Complete package in one file | Content and signature separate |

## InfoCert API Integration

**Endpoint**: `POST /certificates/{certificateId}/sign`

**Request**:
```json
{
  "applicationId": "ifcer-batch-service",
  "pin": "...",
  "authorization": {
    "sat": "..."
  },
  "hashSignatures": [{
    "requestId": "file-document.txt",
    "hash": "base64-encoded-file-hash",  ← ORIGINAL FILE HASH (not manifest)
    "withTimestamp": true
  }]
}
```

**Response**:
```json
{
  "signatureResult": [{
    "isOk": true,
    "signedDocument": {
      "content": "base64-RAW-SIGNATURE",  ← RAW signature bytes
      "contentType": "application/octet-stream"
    },
    "signedTimestamp": { ... }
  }]
}
```

## Verification Process

To verify a P7M file:

1. **Parse P7M** structure (PKCS#7 SignedData)
2. **Extract embedded file** from `encap_content_info.content`
3. **Compute hash** of extracted file (SHA-256)
4. **Extract signature** from `signer_infos[0].signature`
5. **Extract certificate** from `certificates[0]`
6. **Verify** signature matches computed hash using certificate public key

## DynamoDB Schema

```json
{
  "Id": "uploads/document.txt",              // Primary key
  "file_key": "uploads/document.txt",
  "file_hash": "abc123...",
  "hash_algorithm": "SHA256",
  "digital_signature": "def456...",
  "vendor_timestamp": "2025-11-14T...",
  "signed_file_key": "signed/document.p7m", // P7M file location
  "file_size": 1024,
  "signed_file_size": 2048,
  "status": "completed"
}
```

## File Downloads

### Download Original File
```
GET /download/original?file_key=uploads/document.txt
```

### Download P7M File
```
GET /download/signed?original_file_key=uploads/document.txt
GET /download/signed?signed_file_key=signed/document.p7m
```

## Security

- **Authentication**: Dual SAT token (header + body) + mTLS + PIN
- **Signature Algorithm**: SHA256withRSA
- **Certificate**: Fetched from InfoCert
- **Timestamp**: Included from InfoCert response

## Benefits of P7M (ENVELOPED)

1. **Single File**: Complete package in one file
2. **Self-Contained**: No need to manage separate manifest
3. **Standard Format**: PKCS#7 is widely supported
4. **Italian Compliance**: CAdES-BES format for Italian regulations

## Notes

- **No Manifest File**: We don't create a separate manifest.json
- **Direct Hash Signing**: InfoCert signs the original file's hash directly
- **Embedded Content**: Original file is embedded in P7M structure
- **Validation Service**: Needs update to validate embedded content (TODO)

## Example

**Original File**: `contracts/agreement.pdf` (50 KB)

**After Processing**:
- S3: `signed/agreement.p7m` (52 KB) - includes PDF + signature
- DynamoDB: Metadata with `signed_file_key: "signed/agreement.p7m"`

**To Extract**: Parse P7M → extract embedded PDF from `encapContentInfo`
