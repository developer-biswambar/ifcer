# Follow-up Email to InfoCert - hashSignatures Implementation

**Subject:** Follow-up: Additional Details Needed for hashSignatures API Implementation

---

Dear InfoCert Team,

Thank you for clarifying that we should use the `hashSignatures` endpoint! We understand the basic request format from your example, but need a few additional details to complete our implementation.

## Request Format Confirmed ✅

We understand the basic structure:
```json
POST /certificates/{certificateId}/sign

{
  "applicationId": "ifcer-batch-service",
  "pin": "{{pin}}",
  "hashSignatures": [{
    "requestId": "request1",
    "hash": "base64-encoded-sha256-hash"
  }]
}
```

## Missing Information We Need

### 1. PIN Credentials
**Question:** What is the PIN for our automatic signature certificates?

**Our Certificates:**
- **Staging:** MA678944 (JPMorgan_COLL.MT)
- **Production:** MOI56167 (JPMorgan_PROD.MT)

Please provide the PIN for each environment.

### 2. SAT (Signature Activation Token)
You mentioned SAT is required along with PIN, but your example doesn't show it.

**Questions:**
- Is SAT required for automated batch signing, or optional?
- If required, how do we obtain SAT for automated signatures?
  - Do we call `/authenticators/{authType}/authorize` first?
  - What `authType` should we use for automatic signatures?
  - Is SAT token long-lived or must we get it per request?
- Does the request body need an `authorization` object with SAT?

**Example with authorization:**
```json
{
  "applicationId": "ifcer-batch-service",
  "pin": "{{pin}}",
  "authorization": {
    "sat": "{{SAT_TOKEN}}"
  },
  "hashSignatures": [...]
}
```

Is this structure correct for automated signing?

### 3. withTimestamp Field
**Question:** Should we include `withTimestamp: true` in the hashSignatures array?

Your example doesn't show this field, but the OpenAPI spec shows it as optional.
Since we have unlimited timestamps, should we use it?

```json
"hashSignatures": [{
  "requestId": "request1",
  "hash": "base64-hash",
  "withTimestamp": true  // Should we include this?
}]
```

### 4. Response Structure
**Question:** What exactly is returned in `signedDocument.content` for hashSignatures?

- Does it contain a complete CAdES P7M/P7S file ready to use?
- Or does it contain raw signature bytes requiring us to build P7M ourselves?
- What is the `contentType` value?
- Is the signing certificate embedded in the response?

**Example response clarification:**
```json
{
  "signatureResult": [{
    "requestId": "request1",
    "isOk": true,
    "signedDocument": {
      "content": "WHAT FORMAT IS THIS?",
      "contentType": "WHAT VALUE?"
    }
  }]
}
```

### 5. Complete Working Example
**Request:** Could you provide a complete working example for automated hash signing including:

**Request:**
- Full endpoint URL: `https://mtlsapistage.infocert.digital/signature/v1/certificates/{certificateId}/sign`
- All required headers (X-signer-id, Content-Type, etc.)
- Complete request body with all required fields (including authorization if needed)
- Sample hash value

**Response:**
- Example successful response showing actual field values
- Clarification of what's in signedDocument.content

### 6. Postman Collection
You mentioned a Postman collection is attached with working examples. This would be extremely helpful!

**Could you please share:**
- The Postman collection file
- Or export the specific hashSignatures request as a cURL command

This would help us ensure our implementation matches exactly.

## Summary of What We Need

| Item | Staging (MA678944) | Production (MOI56167) | Status |
|------|-------------------|----------------------|---------|
| **Certificate ID** | MA678944 | MOI56167 | ✅ Have |
| **P12 Certificate** | ✅ Have | ✅ Have | ✅ Have |
| **P12 Password** | ✅ Have | ✅ Have | ✅ Have |
| **PIN** | ❓ NEED | ❓ NEED | ❌ **NEED** |
| **SAT Token** | ❓ NEED | ❓ NEED | ❌ **NEED** |
| **X-signer-id** | MA678944 | MOI56167 | ✅ Have |

## Our Use Case Reminder

We're implementing automated batch signing for Italian Business Register submissions:
- Process: Document → Compute hash → Create manifest JSON → Sign manifest hash → Store manifest.json + signature.p7s
- Volume: Batch processing of multiple files
- No manual interaction: Fully automated (no OTP/2FA)
- mTLS authentication with P12 certificate

Thank you for your continued support. Once we have the PIN, SAT details, and response format clarification, we can complete our implementation and begin testing immediately.

Best regards,

---

**What We're Waiting For:**
1. ✅ PIN for MA678944 (staging)
2. ✅ PIN for MOI56167 (production)
3. ✅ SAT token or instructions to obtain it
4. ✅ Clarification on withTimestamp usage
5. ✅ Response structure details
6. ✅ Complete working example or Postman collection
