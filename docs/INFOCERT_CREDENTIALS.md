# InfoCert Credentials and Configuration

## Account Information

InfoCert has created an account with **unlimited timestamps** for signing.

**Password Reset:** https://idp.infocert.it/recovery

## Environments

### Production Environment
- **X-signer-id (User):** `MOI56167`
- **Nickname:** `JPMorgan_PROD.MT`
- **API URL:** `https://mtlsapi.infocert.digital/signature/v1`
- **P12 Certificate:** Production certificate provided separately
- **P12 Password:** Provided separately

### Staging Environment
- **X-signer-id (User):** `MA678944`
- **Nickname:** `JPMorgan_COLL.MT`
- **API URL:** `https://mtlsapistage.infocert.digital/signature/v1`
- **P12 Certificate:** Staging certificate provided separately
- **P12 Password:** Provided separately

## What We Have ✅

- ✅ X-signer-id for Production: `MOI56167`
- ✅ X-signer-id for Staging: `MA678944`
- ✅ P12 certificate files (both environments)
- ✅ P12 passwords (both environments)
- ✅ API URLs
- ✅ Unlimited timestamps enabled

## What We Still Need ❌

### 1. Certificate ID
- Is the Certificate ID the same as X-signer-id (MOI56167/MA678944)?
- Or do we need to call `GET /certificates` to retrieve it?

### 2. API Endpoint Confirmation
Which endpoint should we use for hash signing?
- `POST /certificates/{certificateId}/sign` with `cadesSignatures`?
- `POST /certificates/{certificateId}/sign` with `hashSignatures`?

### 3. Authentication Details
- Is a PIN required in the request body?
- Do we need to perform challenge/authorize flow?
- Or is mTLS authentication sufficient?

### 4. Request/Response Examples
- Complete working request example with all required fields
- Response structure (complete P7M or raw signature bytes)

### 5. Functional Differences
- What's the difference between `cadesSignatures` with digest vs `hashSignatures`?
- Which one returns a complete CAdES P7M file?

## Next Steps

1. **Update configuration files** with the X-signer-id values
2. **Send follow-up email** to InfoCert requesting the remaining technical details
3. **Test authentication** by calling `GET /certificates` with X-signer-id header
4. **Implement signing logic** once we have complete endpoint details

## Notes

- Account has **unlimited timestamps** - no need to worry about timestamp quotas
- Password can be reset via: https://idp.infocert.it/recovery
- Both staging and production environments are ready for use
