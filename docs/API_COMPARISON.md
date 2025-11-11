# InfoCert Hash Signing API Comparison

## Two Options for Hash Signing

Based on the InfoCert Sign API OpenAPI spec v1.9.3, we have two options for signing document hashes:

---

## Option 1: CAdES Signatures with Digest

**Endpoint:** `POST /certificates/{certificateId}/sign`

**Request Body:**
```json
{
  "applicationId": "ifcer-batch-service",
  "cadesSignatures": [{
    "signatureLevel": "BASELINE-B",  // or BASELINE-T, BASELINE-LT, BASELINE-LTV
    "requestId": "unique-request-id",
    "document": {
      "digest": {
        "content": "base64-encoded-sha256-hash",
        "algo": "SHA-256"  // Also supports SHA-384, SHA-512
      }
    },
    "packaging": "ENVELOPED"  // or ENVELOPING, DETACHED, COUNTERSIG
  }]
}
```

**Schema Reference:**
```typescript
CadesSignature {
  signatureLevel: "BASELINE-B" | "BASELINE-T" | "BASELINE-LT" | "BASELINE-LTV"
  requestId: string (REQUIRED)
  document: Document (REQUIRED)
  packaging: "ENVELOPED" | "ENVELOPING" | "DETACHED" | "COUNTERSIG" (REQUIRED)
  counterSignCertificate?: string (base64)
  parallelSign?: boolean
}

Document {
  content?: string (base64) - NOT USED for hash signing
  contentType?: string
  attachName?: string
  digest?: DigestDocument {
    content: string (base64) - THE HASH
    algo: "SHA-256" | "SHA-384" | "SHA-512"
  }
}
```

### Pros:
- ✅ Returns **complete CAdES P7M structure**
- ✅ InfoCert builds the entire signature container
- ✅ Supports multiple signature levels (B, T, LT, LTV)
- ✅ Supports timestamping (BASELINE-T level)
- ✅ Fully compliant with eIDAS and Italian standards
- ✅ Certificate chain embedded automatically
- ✅ Can specify packaging format (ENVELOPED recommended)
- ✅ Purpose-built for CAdES signatures

### Cons:
- ❓ Need to confirm response contains complete P7M
- ❓ More complex request structure

### Expected Response:
```json
{
  "applicationId": "ifcer-batch-service",
  "signatureResult": [{
    "requestId": "unique-request-id",
    "isOk": true,
    "signedDocument": {
      "content": "base64-encoded-COMPLETE-P7M-FILE",
      "contentType": "application/pkcs7-signature"
    }
  }]
}
```

---

## Option 2: Hash Signatures

**Endpoint:** `POST /certificates/{certificateId}/sign`

**Request Body:**
```json
{
  "applicationId": "ifcer-batch-service",
  "hashSignatures": [{
    "requestId": "unique-request-id",
    "hash": "base64-encoded-sha256-hash",
    "withTimestamp": true
  }]
}
```

**Schema Reference:**
```typescript
HashSignature {
  requestId: string (REQUIRED)
  hash: string (base64, REQUIRED) - SHA-256 hash
  withTimestamp?: boolean - If true, timestamp is applied to hash
}
```

### Pros:
- ✅ Simpler request structure
- ✅ Can request timestamp with `withTimestamp: true`
- ✅ Straightforward hash-only signing

### Cons:
- ❌ Likely returns **only raw signature bytes**, not complete P7M
- ❌ We'd need to fetch signing certificate separately (`GET /certificates/{certificateId}`)
- ❌ We'd need to build the P7M structure ourselves
- ❌ More complex implementation on our side
- ❌ Risk of incorrect P7M construction
- ❌ No signature level specification
- ❌ Limited control over signature format

### Expected Response:
```json
{
  "applicationId": "ifcer-batch-service",
  "signatureResult": [{
    "requestId": "unique-request-id",
    "isOk": true,
    "signedDocument": {
      "content": "base64-encoded-RAW-SIGNATURE-BYTES",
      "contentType": "application/octet-stream"
    },
    "signedTimestamp": {  // Only if withTimestamp: true
      "content": "base64-encoded-timestamp",
      "contentType": "application/octet-stream"
    }
  }]
}
```

---

## Side-by-Side Comparison

| Feature | CAdES with Digest | Hash Signatures |
|---------|------------------|-----------------|
| **Request Complexity** | Medium | Simple |
| **Returns Complete P7M** | ✅ Yes (likely) | ❌ No (likely raw signature) |
| **Certificate Embedded** | ✅ Yes | ❌ Need to fetch separately |
| **Signature Level Control** | ✅ Yes (B/T/LT/LTV) | ❌ No |
| **Timestamping** | ✅ Via signature level | ✅ Via withTimestamp flag |
| **Packaging Control** | ✅ Yes | ❌ No |
| **eIDAS Compliance** | ✅ Explicit | ⚠️ Depends on implementation |
| **Italian AgID Standards** | ✅ Yes | ⚠️ Manual validation needed |
| **Implementation Effort** | ✅ Low (InfoCert does it) | ❌ High (we build P7M) |
| **Risk of Errors** | ✅ Low | ❌ High (manual ASN.1) |
| **Hash Algorithm Support** | ✅ SHA-256/384/512 | ⚠️ SHA-256 only (implied) |

---

## Recommendation: **Option 1 - CAdES with Digest**

### Reasons:

1. **Complete P7M Output**: InfoCert builds the entire CAdES structure for us
2. **eIDAS Compliance**: Explicit signature levels (BASELINE-B) ensure compliance
3. **Italian Standards**: Purpose-built for Italian qualified signatures
4. **Lower Risk**: InfoCert handles all ASN.1/P7M construction correctly
5. **Unlimited Timestamps**: We have unlimited timestamps, can use BASELINE-T level
6. **Less Code**: No need to manually build P7M structure
7. **Certificate Chain**: Automatically embedded by InfoCert
8. **Future-Proof**: Can easily upgrade to LT or LTV levels if needed

### Configuration:

```json
POST https://mtlsapistage.infocert.digital/signature/v1/certificates/MA678944/sign
Headers:
  X-signer-id: MA678944
  Content-Type: application/json

Body:
{
  "applicationId": "ifcer-batch-service",
  "cadesSignatures": [{
    "signatureLevel": "BASELINE-B",  // Or BASELINE-T with timestamp
    "requestId": "manifest-{uuid}",
    "document": {
      "digest": {
        "content": "{base64-sha256-hash}",
        "algo": "SHA-256"
      }
    },
    "packaging": "ENVELOPED"
  }]
}
```

---

## Next Steps

1. ✅ Update code to use **Option 1: CAdES with digest**
2. ✅ Set endpoint to `/certificates/{certificateId}/sign`
3. ✅ Use `cadesSignatures` array with digest field
4. ✅ Set `signatureLevel: "BASELINE-B"` (or "BASELINE-T" for timestamps)
5. ✅ Set `packaging: "ENVELOPED"`
6. ❓ Test with InfoCert staging to confirm complete P7M is returned
7. ❓ Validate P7M structure with Italian standards

---

## Questions to Confirm with InfoCert

1. Does `cadesSignatures` with digest return a **complete CAdES P7M file** in `signedDocument.content`?
2. What is the `contentType` value? (`application/pkcs7-signature` or `application/x-pkcs7-signature`?)
3. Is the signing certificate chain embedded in the P7M?
4. Should we use `BASELINE-B` or `BASELINE-T` for Italian compliance?
5. Is `packaging: "ENVELOPED"` correct for signing manifest hashes?
