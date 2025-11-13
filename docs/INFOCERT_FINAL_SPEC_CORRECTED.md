# InfoCert hashSignatures API - CORRECTED Specification

## ✅ CORRECTED: Still Using mTLS!

### Authentication Method
- ✅ **mTLS** with P12 certificate (for connection security)
- ✅ **SAT token** - WHERE DOES IT GO?
- ✅ **PIN** in request body

### Questions About SAT Token Placement:

The cURL example shows:
```bash
--header 'Authorization: Bearer eyJhbGciOiJSUzI...'
```

But user confirms it's still mTLS.

**Question:** Where does the SAT token go?

**Option A:** Authorization header alongside mTLS
```bash
# mTLS connection with P12 certificate
# PLUS Authorization header:
Authorization: Bearer {SAT_TOKEN}
X-signer-id: MA556902
```

**Option B:** In request body
```json
{
  "applicationId": "ifcer-batch-service",
  "pin": "11223344",
  "authorization": {
    "sat": "{SAT_TOKEN}"
  },
  "hashSignatures": [...]
}
```

**Option C:** Some other way?

## What We Know For Sure

### 1. API URL
```
POST https://apitest.infocert.digital/signature/v1/certificates/{certificate-id}/sign
```
(Note: Not `mtlsapitest` but still uses mTLS connection)

### 2. mTLS Connection
- P12 certificate for mTLS handshake
- P12 password

### 3. Required Headers
```bash
X-signer-id: MA556902
Content-Type: application/json
# SAT token location: ???
```

### 4. Request Body
```json
{
  "applicationId": "ifcer-batch-service",
  "pin": "11223344",
  "hashSignatures": [{
    "requestId": "unique-id",
    "hash": "base64-sha256-hash",
    "withTimestamp": "true"
  }]
}
```

### 5. Response (Confirmed)
```json
{
  "signatureResult": [{
    "requestId": "unique-id",
    "isOk": true,
    "signedDocument": {
      "content": "base64-RAW-SIGNATURE-BYTES",
      "contentType": "application/octet-stream"
    },
    "signedTimestamp": {
      "content": "base64-timestamp-token",
      "contentType": "application/timestamp-reply"
    }
  }]
}
```

## NEED CLARIFICATION

**User: Please clarify where the SAT token goes:**

1. ✅ Authorization header: `Authorization: Bearer {SAT}`?
2. ✅ Request body in `authorization.sat` field?
3. ✅ Somewhere else?

**And confirm:**
- Is the P12 certificate associated with MA556902?
- Do we use `apitest.infocert.digital` with mTLS connection?
