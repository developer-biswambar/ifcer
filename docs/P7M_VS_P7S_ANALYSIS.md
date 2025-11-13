# Critical Analysis: P7M vs P7S Implementation

## The Problem

We're currently creating **P7M (ENVELOPED)** signatures, but Italian authorities require **P7S (DETACHED)** signatures.

---

## P7S vs P7M: Key Differences

### P7S (DETACHED Signature) ✅ What We Need

```
Files Required:
- manifest.json         (original manifest)
- manifest.p7s          (detached signature)

Structure:
┌─────────────────────────────┐
│  manifest.p7s               │
│  ┌───────────────────────┐  │
│  │ SignedData            │  │
│  │ ├─ version            │  │
│  │ ├─ digestAlgorithms   │  │
│  │ ├─ contentInfo        │  │
│  │ │   ├─ contentType: data│ │
│  │ │   └─ content: NONE!  │  │  <-- NO EMBEDDED DATA
│  │ ├─ certificates       │  │
│  │ └─ signerInfos        │  │
│  │     └─ signature      │  │
│  └───────────────────────┘  │
└─────────────────────────────┘

Verification Process:
1. Read manifest.json
2. Compute SHA-256 hash of manifest.json
3. Extract public key from manifest.p7s
4. Verify signature in manifest.p7s matches computed hash
```

**Italian Authority Workflow:**
- Receives TWO separate files
- Computes hash of manifest.json
- Verifies signature in manifest.p7s

---

### P7M (ENVELOPED Signature) ❌ What We're Currently Creating

```
Files Required:
- manifest.p7m          (signature + embedded manifest)

Structure:
┌─────────────────────────────┐
│  manifest.p7m               │
│  ┌───────────────────────┐  │
│  │ SignedData            │  │
│  │ ├─ version            │  │
│  │ ├─ digestAlgorithms   │  │
│  │ ├─ contentInfo        │  │
│  │ │   ├─ contentType: data│ │
│  │ │   └─ content: {...} │  │  <-- MANIFEST EMBEDDED!
│  │ │       "fileName": "..."  │
│  │ │       "hash": "..."      │
│  │ │       "algorithm": "..." │
│  │ ├─ certificates       │  │
│  │ └─ signerInfos        │  │
│  │     └─ signature      │  │
│  └───────────────────────┘  │
└─────────────────────────────┘

Verification Process:
1. Read manifest.p7m (single file)
2. Extract embedded manifest from contentInfo
3. Verify signature matches embedded content
```

**Problem:** Italian authorities expect TWO files, not one!

---

## Current Implementation Issue

**File: `app/services/p7m_service.py` (Lines 59-64)**

```python
# ❌ WRONG - This creates ENVELOPED signature
encap_content_info = cms.ContentInfo({
    'content_type': cms.ContentType('data'),
    'content': core.OctetString(manifest_content)  # <-- Embedding manifest!
})
```

This embeds the manifest content inside the P7M structure.

---

## What Needs to Change

### Option 1: Create DETACHED Signature (P7S) ✅ RECOMMENDED

```python
# ✅ CORRECT - Creates DETACHED signature
encap_content_info = cms.EncapsulatedContentInfo({
    'content_type': cms.ContentType('data')
    # NO 'content' field - makes it detached!
})
```

**Result:**
- Creates .p7s file WITHOUT embedded manifest
- Verification requires separate manifest.json file
- Matches Italian authority expectations

---

### Option 2: Keep ENVELOPED but Store Both Files

```python
# Create P7M with embedded manifest
p7m_bytes = create_p7m_with_content(manifest_content, ...)

# Then extract and store separately:
# 1. Save manifest.json (extracted from P7M)
# 2. Save manifest.p7m (complete P7M)
```

**Problem:** This is redundant and not what authorities expect.

---

## InfoCert API Response Analysis

### What InfoCert Returns

```json
{
  "signatureResult": [{
    "isOk": true,
    "signedDocument": {
      "content": "base64-RAW-SIGNATURE-BYTES",  // <-- Raw signature, NOT P7M!
      "contentType": "application/octet-stream"
    }
  }]
}
```

**Key Point:** InfoCert returns **RAW signature bytes**, NOT a complete P7M/P7S structure.

### What We Do With It

1. Receive raw signature bytes
2. Fetch certificate from InfoCert
3. **Build our own P7M/P7S structure** using `p7m_service.py`

**Current Issue:** We're building it as ENVELOPED (P7M), should be DETACHED (P7S)

---

## Regulatory Compliance Requirements

### Italian Authorities Expect:

```
Submission Package:
├── manifest.json          // Original manifest file
└── manifest.p7s           // Detached CAdES signature
```

**Verification Process:**
1. Hash manifest.json with SHA-256
2. Verify signature in manifest.p7s matches hash
3. Extract certificate from manifest.p7s
4. Validate certificate chain and expiration

### What We're Currently Providing:

```
Submission Package:
└── manifest.p7m           // P7M with embedded manifest
```

**Problem:** Authorities can't verify this format correctly!

---

## Technical Differences

| Aspect | P7S (DETACHED) | P7M (ENVELOPED) |
|--------|----------------|-----------------|
| **Content Embedded** | ❌ No | ✅ Yes |
| **Files Required** | 2 (content + signature) | 1 (signature contains content) |
| **ContentInfo.content** | None/absent | OctetString(manifest) |
| **Italian Compliance** | ✅ Yes | ❌ No |
| **File Size** | Smaller | Larger (includes content) |
| **Verification** | Hash external file | Hash embedded content |

---

## Solution: Update P7M Service

### Current Code (WRONG)

```python
# app/services/p7m_service.py

encap_content_info = cms.ContentInfo({
    'content_type': cms.ContentType('data'),
    'content': core.OctetString(manifest_content)  # ❌ Creates ENVELOPED
})
```

### Fixed Code (CORRECT)

```python
# app/services/p7m_service.py

# For DETACHED signature (P7S), do NOT include content
encap_content_info = cms.EncapsulatedContentInfo({
    'content_type': cms.ContentType('data')
    # ✅ No 'content' field = DETACHED signature
})
```

---

## Verification Comparison

### With DETACHED (P7S) - What Authorities Do

```python
# 1. Load separate files
manifest_json = read_file("manifest.json")
signature_p7s = read_file("manifest.p7s")

# 2. Compute hash
manifest_hash = sha256(manifest_json)

# 3. Parse P7S and verify
p7s = parse_pkcs7(signature_p7s)
certificate = extract_certificate(p7s)
signature = extract_signature(p7s)

# 4. Verify
verify_signature(certificate.public_key, signature, manifest_hash)
```

### With ENVELOPED (P7M) - What We Provide

```python
# 1. Load single file
manifest_p7m = read_file("manifest.p7m")

# 2. Parse and extract embedded content
p7m = parse_pkcs7(manifest_p7m)
embedded_manifest = extract_content(p7m)  # <-- Gets embedded content
certificate = extract_certificate(p7m)
signature = extract_signature(p7m)

# 3. Compute hash of embedded content
manifest_hash = sha256(embedded_manifest)

# 4. Verify
verify_signature(certificate.public_key, signature, manifest_hash)
```

**Problem:** Italian authorities expect TWO files, not extraction from P7M!

---

## Impact on Storage

### Current (ENVELOPED)

```
S3 Structure:
signed/
└── document.p7m         (contains manifest + signature)
                          ~2KB for small manifest
```

### Proposed (DETACHED)

```
S3 Structure:
signed/
├── document.json        (manifest only, ~200 bytes)
└── document.p7s         (signature only, ~1.5KB)
```

**Storage:** Similar total size, but split into two files.

---

## Recommended Actions

### 1. Update `p7m_service.py` ✅ CRITICAL

Change from ENVELOPED to DETACHED:

```python
def create_p7s_from_signature(  # Rename method
    self, manifest_content: bytes, signature_bytes: bytes, cert_der_bytes: bytes
) -> bytes:
    # ...

    # CHANGE THIS:
    encap_content_info = cms.EncapsulatedContentInfo({
        'content_type': cms.ContentType('data')
        # Remove 'content' field for DETACHED
    })

    # Rest stays the same...
```

### 2. Update Storage Logic

Store TWO files:
- `signed/{basename}.json` - manifest
- `signed/{basename}.p7s` - detached signature

### 3. Update Documentation

- Change references from P7M to P7S
- Update file extension expectations
- Update validation instructions

### 4. Test with Italian Authorities

Verify the DETACHED format is accepted.

---

## Conclusion

**Current State:** Creating P7M (ENVELOPED) - manifest embedded in signature
**Required State:** Create P7S (DETACHED) - manifest separate from signature

**Fix:** Remove `content` field from `EncapsulatedContentInfo` to create DETACHED signature.

**Priority:** 🔴 CRITICAL - Affects regulatory compliance
