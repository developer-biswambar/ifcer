# CAdES Packaging Analysis: Digest vs Content

## From Web Search Results

### Key Finding: Digest-based signing is for DETACHED signatures

**DETACHED Signatures:**
- Signature and document are in **separate files**
- CAdES uses `.p7s` extension
- DigestDocument (hash only) is specifically designed for **detached signatures**
- Allows users to avoid sending full document content

**ENVELOPED/ENVELOPING Signatures:**
- Original document is **incorporated IN the signature file**
- CAdES uses `.p7m` extension
- Requires the full document content to embed it

## The Critical Issue

### Our Current Request:
```json
{
  "cadesSignatures": [{
    "document": {
      "digest": {
        "content": "hash-only",
        "algo": "SHA-256"
      }
    },
    "packaging": "ENVELOPED"  // ← CONTRADICTION!
  }]
}
```

### The Contradiction:
- We specify `packaging: "ENVELOPED"` (embed content in P7M)
- But we only provide `digest` (hash), no content to embed!

**What InfoCert will likely do:**
1. **Option A:** Ignore ENVELOPED request, return DETACHED signature (.p7s)
2. **Option B:** Return error (can't envelop without content)
3. **Option C:** Return signature with hash in signed attributes (not standard enveloped)

## Correct Approaches

### Approach 1: Detached Signature (Hash Only)
```json
{
  "cadesSignatures": [{
    "document": {
      "digest": {
        "content": "base64-hash",
        "algo": "SHA-256"
      }
    },
    "packaging": "DETACHED"  // ← Correct for hash-only
  }]
}
```

**Result:**
- InfoCert returns `.p7s` file (detached signature)
- We store TWO files:
  - `manifest.json` (original)
  - `manifest.p7s` (detached signature)
- Verification needs both files

### Approach 2: Enveloped Signature (Full Content)
```json
{
  "cadesSignatures": [{
    "document": {
      "content": "base64-encoded-full-manifest",  // ← Full content
      "contentType": "application/json"
    },
    "packaging": "ENVELOPED"  // ← Correct for full content
  }]
}
```

**Result:**
- InfoCert returns `.p7m` file (enveloped signature with content)
- We store ONE file: `manifest.p7m` (contains manifest + signature)
- Verification needs only one file

**Problem:** Conflicts with compliance requirement (can't send content to InfoCert)

## Questions for InfoCert

1. **When using `cadesSignatures` with `digest` only + `packaging: "ENVELOPED"`:**
   - What does InfoCert return?
   - Is it an error, or does it fallback to DETACHED?

2. **For Italian Business Register compliance:**
   - Do they accept DETACHED signatures (two separate files)?
   - Or do they require ENVELOPED signatures (single file)?

3. **If DETACHED is acceptable:**
   - Should we use `.p7s` extension or `.p7m`?
   - What exactly is in the returned `signedDocument.content`?

4. **Alternative approach:**
   - Can we use `hashSignatures` endpoint instead?
   - Does it support Italian compliance requirements?

## Implementation ✅

**We implemented `packaging: "DETACHED"`:**

```json
{
  "applicationId": "ifcer-batch-service",
  "cadesSignatures": [{
    "signatureLevel": "BASELINE-B",
    "requestId": "manifest-001",
    "document": {
      "digest": {
        "content": "base64-sha256-hash",
        "algo": "SHA-256"
      }
    },
    "packaging": "DETACHED"  // ← Correct for hash-only signing
  }]
}
```

**File Naming:** Based on original filename
- Input: `uploads/abc.txt`
- Output: `signed/abc.json` + `signed/abc.p7s`

**Confirmed with InfoCert:** ✅ Italian authorities accept two-file submissions
