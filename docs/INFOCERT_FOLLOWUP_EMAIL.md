# Follow-up Email to InfoCert Technical Support

**Subject:** Follow-up: Remaining Technical Details for mTLS Hash Signing Implementation

---

Dear InfoCert Team,

Thank you for providing the account credentials:
- **Staging X-signer-id:** MA678944
- **Production X-signer-id:** MOI56167

We now need the remaining technical details to complete our implementation.

## Remaining Questions

### 1. Certificate ID
**Is the Certificate ID the same as the X-signer-id?**

For example:
- Should we use `MA678944` as the certificate ID for staging?
- Or do we need to call `GET /certificates` with the X-signer-id header to retrieve a different certificate ID?

If we need to retrieve it, which value from the `/certificates` response should we use for the `{certificateId}` path parameter?

### 2. API Endpoint for Hash Signing
**Which specific endpoint should we use for signing document hashes (not full documents)?**

Please confirm the correct approach:

**Option A: CAdES with digest**
```
POST /certificates/{certificateId}/sign
```
With request body:
```json
{
  "applicationId": "ifcer-batch-service",
  "cadesSignatures": [{
    "signatureLevel": "BASELINE-B",
    "requestId": "req-001",
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

**Option B: Hash signatures**
```
POST /certificates/{certificateId}/sign
```
With request body:
```json
{
  "applicationId": "ifcer-batch-service",
  "hashSignatures": [{
    "requestId": "req-001",
    "hash": "base64-sha256-hash",
    "withTimestamp": true
  }]
}
```

**Please confirm which option we should use and whether the request structure above is correct.**

### 3. Authentication Requirements
**Is a PIN required for automated batch signing?**

- Do we need to include a `"pin": "value"` field in the request body?
- Or is mTLS authentication (P12 certificate) sufficient?
- Do we need to perform a challenge/authorize flow before signing?

For our automated batch processing use case, we need signing to work without manual 2FA/OTP intervention.

### 4. Response Structure
**What exactly is returned in the `signedDocument.content` field?**

For the endpoint we should use:
- Does it return a **complete CAdES P7M file** (ready to use)?
- Or does it return **only raw signature bytes** (requiring us to build the P7M)?
- What is the `contentType` value in the response?
- Is the signing certificate embedded in the response, or do we need to fetch it separately?

### 5. Complete Working Example
**Can you provide a complete working example request for staging?**

Please include:
- Full URL: `https://mtlsapistage.infocert.digital/signature/v1/...`
- All required headers
- Complete request body JSON
- Example response

This will help us ensure our implementation is 100% correct before testing.

## Summary of What We Need

1. ✅ **Certificate ID** - Is it same as X-signer-id (MA678944/MOI56167)?
2. ✅ **Correct endpoint** - Which option (A or B) for hash signing?
3. ✅ **PIN requirement** - Required or optional?
4. ✅ **Response content** - Complete P7M or raw signature?
5. ✅ **Working example** - Full request/response for staging

Once we have these details, we can complete the implementation and begin testing immediately.

Thank you for your continued assistance.

Best regards,

---

**What We Have:**
- ✅ P12 certificates (staging + production)
- ✅ P12 passwords
- ✅ X-signer-id values (MA678944 / MOI56167)
- ✅ API URLs
- ✅ Unlimited timestamps enabled

**What We're Missing:**
- ❌ Certificate ID confirmation
- ❌ Correct endpoint for hash signing
- ❌ PIN requirement clarification
- ❌ Response structure details
- ❌ Complete working example
