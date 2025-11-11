# Email to InfoCert Technical Support

**Subject:** Technical Implementation Details Required for mTLS Hash Signing Integration

---

Dear InfoCert Team,

Following up on our ongoing discussion regarding mTLS hash signing implementation, we're now at the development stage and need specific technical details to complete our integration.

## Required Information and Clarifications

### 1. Missing Credentials/Identifiers

Please provide the following values for our account:
- **X-signer-id** (Credential ID) - We don't have this value yet
- **Certificate ID** - Is this the same as X-signer-id, or different? If different, please provide the value

### 2. API Endpoint Confirmation

**Which specific API endpoint should we use for hash-only signing with mTLS?**

Based on your OpenAPI spec v1.9.3, we see these options:
- `POST /certificates/{certificateId}/sign` with `cadesSignatures` array (using digest field)
- `POST /certificates/{certificateId}/sign` with `hashSignatures` array
- `POST /multi/sign` (appears to be PAdES/PDF only)

Please confirm the correct endpoint and approach for our CAdES hash signing use case.

### 3. Authentication Requirements

For mTLS hash signing in automated batch processing:
- Is the P12 client certificate sufficient, or do we also need a PIN in the request body?
- Do we need to perform challenge/authorize flow (SAT/OTP/transactionId) before signing?
- Can we sign directly without interactive 2FA/OTP?

### 4. Complete Request Example

Please provide a complete working request example for hash signing, including:
- Full endpoint URL with path parameters
- All required headers (X-signer-id, etc.)
- Complete request body JSON with all required fields
- Clarification on which fields are required vs optional

Example for CAdES digest signing:
```json
POST /certificates/{certificateId}/sign
Headers:
  X-signer-id: ?
  Content-Type: application/json

Body:
{
  "applicationId": "?",
  "pin": "REQUIRED?",
  "cadesSignatures": [{
    "signatureLevel": "BASELINE-B",
    "requestId": "unique-id",
    "document": {
      "digest": {
        "content": "base64-sha256-hash",
        "algo": "SHA-256"
      }
    },
    "packaging": "ENVELOPED"
  }]
}
```

### 5. Response Structure

What exactly is returned in the response?
- Does `signedDocument.content` contain a complete CAdES P7M file, or only raw signature bytes?
- What is the `contentType` value?
- Is the signing certificate embedded in the response, or do we need to fetch it separately via `/certificates/{certificateId}`?

Example response clarification:
```json
{
  "applicationId": "...",
  "signatureResult": [{
    "requestId": "...",
    "isOk": true,
    "signedDocument": {
      "content": "WHAT_IS_THIS_EXACTLY?",
      "contentType": "WHAT_VALUE?"
    }
  }]
}
```

### 6. Difference Between Endpoints

What is the functional difference between:
- `cadesSignatures` with `document.digest` field
- `hashSignatures` with `hash` field

Which one returns a complete P7M file vs raw signature bytes?

### 7. Production vs Staging Configuration

Please confirm:
- **Staging X-signer-id**: [PLEASE PROVIDE]
- **Production X-signer-id**: Will this be different from staging?
- **Production P12 certificate**: Do we need a separate certificate for production, or same as staging?

### 8. Testing

- Can you provide a sample hash and expected signature response for testing?
- Is there a validation endpoint we can use to verify our signed P7M files?

## Summary

To complete our implementation, we specifically need:

1. ✅ **X-signer-id value** (currently missing)
2. ✅ **Certificate ID value** (or confirmation it's same as X-signer-id)
3. ✅ **Correct API endpoint** for hash signing
4. ✅ **Complete working request example** with all required fields
5. ✅ **Response structure clarification** (complete P7M vs raw signature)
6. ✅ **PIN requirement** (required or optional)
7. ✅ **Authorization flow** (if needed beyond mTLS)
8. ✅ **Production credentials** (if different from staging)

Thank you for your assistance.

Best regards,

---

**Current Setup:**
- P12 certificate: ✅ Received
- P12 password: ✅ Received
- X-signer-id: ❌ Missing
- Certificate ID: ❌ Missing
- API endpoint: ❌ Need confirmation
