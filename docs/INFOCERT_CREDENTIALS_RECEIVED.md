# InfoCert Credentials Received

## Staging Environment

```bash
# User/Credential ID
INFOCERT_CREDENTIAL_ID=MA556902

# Certificate ID (different from credential ID!)
INFOCERT_CERTIFICATE_ID=CD6972A8922C0230B45C3F97B26891E3

# PIN
INFOCERT_PIN=11223344

# SAT Token (JWT - appears to be long-lived)
INFOCERT_SAT=eyJ4NXUiOiJodHRwczovL3RyaWFsLmV1LXNvdXRoLTEuY2xhdXMuaW5mb2NlcnQuaXQvY2VydGlmaWNhdGUiLCJhbGciOiJSUzI1NiJ9.eyJob2tUb1R5cGUiOiJsb25nVGVybVRva2VuIiwic2NvcGUiOm51bGwsImlhdCI6MTczNjQzOTIzNCwiZXhwIjoxODMxMTEyMDc4LCJqdGkiOiIzWFdrTXRIVDRSX29QNklmUE5oTDQ0ejIzUTBEXzVsMjZHemIxXzdiRU5vIiwic3ViIjoiSU5GT0NFUlRfTUE1NTY5MDIiLCJpc3MiOiJUUklBTCIsInRpZCI6IjYzN2ZmNWI2ZTkxY2RhNzEzZWUyZWExYyIsImF1dCI6IlNNU1AiLCJhdWQiOiJUUklBTF9JTkZPQ0VSVCIsInVhcCI6IkNENjk3MkE4OTIyQzAyMzBCNDVDM0Y5N0IyNjg5MUUzIiwiU0NPUEVfUEFSQU1FVEVSX01BUCI6eyJ1YXAiOiJDRDY5NzJBODkyMkMwMjMwQjQ1QzNGOTdCMjY4OTFFMyJ9fQ.PVbQ0x64c1kNoGGobOPg9DO8hf5_NICQAgfm_uPRQvH55FqC0jcQo-iIL7v8163Jtc9dsrCW8tYceXBhBFBoGYPKW5tJ8ZMbuoIOQHjmnrYsBHmv9MPs5KF8F54ZVgA_GFZ5ao91bB74xsvcSU2E3criWxDDzO4VpLNNLgFSjUbwvyHVPbwCiaHJGaPxbnUnj2YXysNTf6gYv_C3Lzrum8ZmIp9JWpUk78ybPeJGPRgZ3DH3fejKOhZPMhdZ1hRs2K80kJGDURRdDDPrTMh-DCPYKBCYBIPwTE_AOk4e8NXBKei083LzDk4JGUX7zhXzIG1JXQmRM325JedeOGT3w
```

## Key Findings

1. **User ID changed:** MA556902 (not MA678944 as initially provided)
2. **Certificate ID is different from Credential ID:**
   - Credential ID: MA556902
   - Certificate ID: CD6972A8922C0230B45C3F97B26891E3
3. **SAT Token:** JWT format, appears to be long-lived (exp: 1831112078 = ~2028)

## Questions

1. **Is this for STAGING or PRODUCTION?**
   - We were expecting MA678944 for staging
   - MA556902 is a different user ID

2. **Do we have production credentials?**
   - Or is this the only environment we're using?

3. **API URL:**
   - Should we use: `https://mtlsapistage.infocert.digital/signature/v1` (staging)
   - Or: `https://mtlsapi.infocert.digital/signature/v1` (production)

## SAT Token Details (Decoded JWT Payload)

From the token, I can see:
- Subject: INFOCERT_MA556902
- Issuer: TRIAL
- Audience: TRIAL_INFOCERT
- UAP (Certificate): CD6972A8922C0230B45C3F97B26891E3
- Token Type: longTermToken
- Expires: 2028 (long-lived!)
- Auth Type: SMSP

This appears to be a TRIAL/STAGING environment token.
