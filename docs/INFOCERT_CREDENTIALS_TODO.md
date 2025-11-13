# InfoCert Credentials - FILL IN VALUES

## Staging Environment

```bash
INFOCERT_CREDENTIAL_ID=MA678944
INFOCERT_CERTIFICATE_ID=???  # Please provide
INFOCERT_PIN=???  # Please provide
INFOCERT_SAT=???  # Please provide
```

## Production Environment

```bash
INFOCERT_CREDENTIAL_ID=MOI56167
INFOCERT_CERTIFICATE_ID=???  # Please provide
INFOCERT_PIN=???  # Please provide
INFOCERT_SAT=???  # Please provide
```

## Questions:

1. **Is Certificate ID same as Credential ID?**
   - Or is it a different value?

2. **Is SAT token long-lived or per-request?**
   - Do we need to refresh it periodically?
   - Or is it a static value we can configure?

3. **Please provide the actual values above** so I can:
   - Update `.env.example`
   - Update configuration files
   - Update code to use hashSignatures with PIN and SAT
