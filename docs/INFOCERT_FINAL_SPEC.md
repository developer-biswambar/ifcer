# InfoCert hashSignatures API - Complete Specification

## ✅ CONFIRMED: API Details from InfoCert

### 1. API Endpoint
```
POST https://apitest.infocert.digital/signature/v1/certificates/{certificate-id}/sign
```

**IMPORTANT:** Use `apitest.infocert.digital`, NOT `mtlsapitest.infocert.digital`!

### 2. Required Headers
```bash
Authorization: Bearer {SAT_TOKEN}  # SAT as Bearer token!
Content-Type: application/json
X-signer-id: MA556902
```

**NOT Required:**
- ❌ Otp (confirmed by InfoCert)
- ❌ Transaction-Id (confirmed by InfoCert)

### 3. Request Body
```json
{
  "applicationId": "ifcer-batch-service",
  "pin": "11223344",
  "hashSignatures": [
    {
      "requestId": "unique-id",
      "hash": "base64-sha256-hash",
      "withTimestamp": "true"  // ← STRING "true", not boolean!
    }
  ]
}
```

**CRITICAL:** `withTimestamp` is a STRING `"true"`, not boolean `true`!

### 4. Response Structure
```json
{
  "applicationId": "ifcer-batch-service",
  "signatureResult": [
    {
      "requestId": "unique-id",
      "isOk": true,
      "signedDocument": {
        "content": "base64-RAW-SIGNATURE-BYTES",  // ← NOT complete P7M!
        "contentType": "application/octet-stream"
      },
      "signedTimestamp": {
        "content": "base64-timestamp-token",
        "contentType": "application/timestamp-reply"
      }
    }
  ]
}
```

**CRITICAL FINDING:**
- `signedDocument.content` = **RAW SIGNATURE BYTES** (not complete P7M!)
- We MUST build P7M ourselves using `_create_p7m_from_signature()`!

### 5. Our Configuration

```bash
# API URL (staging/test environment)
INFOCERT_API_URL=https://apitest.infocert.digital/signature/v1

# Credentials
INFOCERT_CREDENTIAL_ID=MA556902  # X-signer-id
INFOCERT_CERTIFICATE_ID=CD6972A8922C0230B45C3F97B26891E3  # Path parameter
INFOCERT_PIN=11223344  # Request body
INFOCERT_SAT=eyJ4NXUiOiJodHRwczovL3RyaWFsLmV1LXNvdXRoLTEuY2xhdXMuaW5mb2NlcnQuaXQvY2VydGlmaWNhdGUiLCJhbGciOiJSUzI1NiJ9...  # Bearer token
```

### 6. Multiple Hash Support ✅

InfoCert confirmed we can send multiple hashes in a single request:
```json
{
  "applicationId": "ifcer-batch-service",
  "pin": "11223344",
  "hashSignatures": [
    {
      "requestId": "file1",
      "hash": "hash1..."
    },
    {
      "requestId": "file2",
      "hash": "hash2..."
    }
  ]
}
```

Response returns array with results for each hash.

## Changes Required in Code

### 1. Configuration (app/config.py)
- ✅ Update API URL: `https://apitest.infocert.digital/signature/v1`
- ✅ Add PIN field: `infocert_pin`
- ✅ Add SAT field: `infocert_sat`
- ✅ Add Certificate ID field: `infocert_certificate_id`

### 2. Signature Service (app/services/signature_service.py)
- ✅ Change from `cadesSignatures` to `hashSignatures`
- ✅ Add Authorization header: `Bearer {SAT}`
- ✅ Add PIN to request body
- ✅ Set `withTimestamp: "true"` (string!)
- ✅ Parse raw signature bytes from response
- ✅ KEEP `_create_p7m_from_signature()` method - WE NEED IT!
- ✅ Fetch signing certificate separately
- ✅ Build P7M from: manifest + signature + certificate

### 3. Response Parsing
```python
# Extract raw signature bytes
signature_bytes = base64.b64decode(result["signedDocument"]["content"])

# Get timestamp if available
timestamp_bytes = base64.b64decode(result["signedTimestamp"]["content"])

# Fetch signing certificate
cert_bytes = get_certificate()  # Need to call /certificates/{certificateId}

# Build P7M
p7m_bytes = _create_p7m_from_signature(manifest_bytes, signature_bytes, cert_bytes)
```

### 4. Certificate Retrieval
Need to call:
```
GET /certificates/{certificateId}
Headers:
  X-signer-id: MA556902
  Authorization: Bearer {SAT}
```

To get the signing certificate for P7M construction.

## Summary

**What Changed:**
1. ❌ NOT using mTLS API URL (mtlsapitest)
2. ✅ Using regular API URL (apitest) with Bearer auth
3. ❌ NOT using cadesSignatures
4. ✅ Using hashSignatures
5. ❌ Response is NOT complete P7M
6. ✅ Response is raw signature bytes - we build P7M ourselves
7. ✅ SAT token goes in Authorization header (Bearer)
8. ✅ PIN goes in request body
9. ✅ withTimestamp is STRING "true"

**Good News:**
- We kept `_create_p7m_from_signature()` - we need it!
- Supports multiple hashes per request (batch optimization)
- No OTP/Transaction-Id needed (automated signing works!)
