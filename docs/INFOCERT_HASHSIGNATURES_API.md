# InfoCert hashSignatures API - Complete Requirements

## What InfoCert Told Us

### 1. ✅ Correct Endpoint
```
POST https://mtlsapistage.infocert.digital/signature/v1/certificates/{certificateId}/sign
```

Use **`hashSignatures` array**, NOT `cadesSignatures`!

### 2. ✅ Example Request Body (from InfoCert)
```json
{
  "applicationId": "desktop-signer",
  "pin": "{{pin}}",
  "hashSignatures": [
    {
      "requestId": "request1",
      "hash": "MTIzNDU2Nzg5MDEyMzQ1Njc4OTAxMjM0NTY3ODkwMTI="
    }
  ]
}
```

### 3. ✅ Authentication Requirements (from InfoCert)
InfoCert said we need:
- ✅ **P12 certificate** (for mTLS connection) - WE HAVE
- ✅ **X-signer-id** (MA678944 staging / MOI56167 production) - WE HAVE
- ✅ **Certificate-id** (same as X-signer-id) - WE HAVE
- ❌ **PIN** - NEED TO GET FROM INFOCERT
- ❌ **SAT** (Signature Activation Token) - NEED TO UNDERSTAND

## From OpenAPI Spec

### HashSignature Schema:
```typescript
{
  requestId: string (REQUIRED)
  hash: string (base64, REQUIRED) - SHA-256 hash
  withTimestamp?: boolean - If true, timestamp is applied to hash
}
```

### SignatureRequest Schema (with authorization):
```json
{
  "applicationId": "string",
  "pin": "string",
  "authorization": {
    "sat": "string",
    "sac": "string",
    "sacSchema": "string",
    "transactionId": "string",
    "otp": "string",
    "authorizedSignatures": 0,
    "authorizedDigests": {...}
  },
  "hashSignatures": [...]
}
```

## Critical Questions for InfoCert

### 1. PIN Requirement ❓
**Question:** What is the PIN for our automatic signature certificate?
- Is it provided with the P12 certificate?
- Is it a separate credential?
- Where do we get it?

**Staging:** MA678944
**Production:** MOI56167

### 2. SAT (Signature Activation Token) ❓

InfoCert mentioned SAT is required, but the example doesn't show it.

**Questions:**
- Is SAT required for automated signing, or optional?
- If required, how do we get SAT?
  - Do we call `/authenticators/{authType}/authorize` first?
  - What is the `authType` for automatic signatures?
  - Is SAT long-lived or per-request?
- Can we skip SAT if we provide PIN?

**OpenAPI shows authorization flow:**
```
1. POST /authenticators/{authType}/challenge → get transactionId
2. POST /authenticators/{certificateId}/{authType}/authorize → get SAT
3. Use SAT in signing request
```

### 3. withTimestamp Field ❓
**Question:** Should we include `withTimestamp: true` in hashSignatures?

InfoCert's example doesn't show it, but OpenAPI spec says it's optional.
Since we have unlimited timestamps, should we use it?

### 4. Complete Request Example ❓
**Request:** Can InfoCert provide a complete working example for automated hash signing including:
- All required headers (X-signer-id, etc.)
- Complete request body with all fields
- How to handle authorization (SAT/PIN)
- Example response

### 5. Response Format ❓
**Question:** What does `signedDocument.content` contain for `hashSignatures`?

According to our analysis:
- **cadesSignatures with digest**: Returns complete P7M/P7S structure
- **hashSignatures**: Returns what exactly?
  - Complete P7M/P7S file?
  - Raw signature bytes?
  - We need to build P7M ourselves?

### 6. Packaging for hashSignatures ❓
**Question:** There's no `packaging` field in hashSignatures (unlike cadesSignatures).

- Does InfoCert return ENVELOPED or DETACHED signature?
- Do we get one file or need two files?

## What We Need from InfoCert

### Immediate Needs:
1. ✅ **PIN** for certificates MA678944 (staging) and MOI56167 (production)
2. ✅ **SAT token** - How to get it? Is it required?
3. ✅ **Complete working request example** for automated hash signing
4. ✅ **Response structure** - What's in signedDocument.content?
5. ✅ **Postman collection** (they mentioned it's attached - can you share it?)

### Configuration Values Needed:
```bash
# Staging
INFOCERT_CREDENTIAL_ID=MA678944
INFOCERT_PIN=???  # NEED THIS
INFOCERT_SAT=???  # NEED THIS (or instructions to get it)

# Production
INFOCERT_CREDENTIAL_ID=MOI56167
INFOCERT_PIN=???  # NEED THIS
INFOCERT_SAT=???  # NEED THIS (or instructions to get it)
```

## Comparison: Our Implementation vs InfoCert

### What We Implemented (WRONG):
```json
{
  "applicationId": "ifcer-batch-service",
  "cadesSignatures": [{
    "signatureLevel": "BASELINE-B",
    "requestId": "manifest-abc.txt",
    "document": {
      "digest": {
        "content": "base64-hash",
        "algo": "SHA-256"
      }
    },
    "packaging": "DETACHED"
  }]
}
```

### What InfoCert Wants (CORRECT):
```json
{
  "applicationId": "ifcer-batch-service",
  "pin": "{{PIN_FROM_INFOCERT}}",
  "authorization": {
    "sat": "{{SAT_TOKEN_IF_REQUIRED}}"
  },
  "hashSignatures": [{
    "requestId": "manifest-abc.txt",
    "hash": "base64-hash",
    "withTimestamp": true  // Optional - should we use?
  }]
}
```

## Next Steps

1. ✅ Get PIN from InfoCert for both environments
2. ✅ Clarify SAT token requirement and how to obtain it
3. ✅ Get Postman collection attachment
4. ✅ Update code to use hashSignatures instead of cadesSignatures
5. ✅ Add PIN and SAT to configuration
6. ✅ Test with InfoCert staging environment
