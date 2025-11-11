# IFCER Scripts

Utility scripts for setting up and managing the IFCER Batch Service.

## Available Scripts

### `extract_p12_to_pem.sh`

Converts P12 (PKCS#12) certificates from InfoCert to PEM format for mTLS authentication.

**Usage:**
```bash
./scripts/extract_p12_to_pem.sh /path/to/your_cert.p12 [output_directory]
```

**Examples:**
```bash
# Extract to default ./certs directory
./scripts/extract_p12_to_pem.sh ~/Downloads/infocert_cert.p12

# Extract to custom directory
./scripts/extract_p12_to_pem.sh ~/Downloads/infocert_cert.p12 ./my_certs
```

**Output:**
- `client_cert.pem` - Client certificate
- `client_key.pem` - Private key (unencrypted)
- `ca_bundle.pem` - CA certificates (if present in P12)

**See:** [docs/P12_CERTIFICATE_SETUP.md](../docs/P12_CERTIFICATE_SETUP.md) for complete guide.

## Quick Start

```bash
# 1. Convert P12 to PEM
./scripts/extract_p12_to_pem.sh ~/Downloads/infocert_cert.p12

# 2. Upload to S3
export S3_BUCKET=your-ifcer-bucket
aws s3 cp certs/client_cert.pem s3://$S3_BUCKET/certs/ --sse AES256
aws s3 cp certs/client_key.pem s3://$S3_BUCKET/certs/ --sse AES256
aws s3 cp certs/ca_bundle.pem s3://$S3_BUCKET/certs/ --sse AES256

# 3. Configure environment
cp .env.example .env
# Edit .env with your values

# 4. Test
python -c "from app.services.signature_service import SignatureService; SignatureService()"
```

## Security Notes

- Never commit P12 files or private keys to git
- Delete local certificates after uploading to S3
- Use S3 server-side encryption (SSE-S3 or SSE-KMS)
- Restrict S3 bucket access with IAM policies
- Set private key file permissions to 600

## Troubleshooting

If the script fails:

1. **Check OpenSSL is installed:**
   ```bash
   openssl version
   ```

2. **Verify P12 file:**
   ```bash
   openssl pkcs12 -in your_cert.p12 -info -noout
   ```

3. **Check password:**
   Contact InfoCert if password is incorrect

## Documentation

- [P12 Certificate Setup Guide](../docs/P12_CERTIFICATE_SETUP.md) - Complete setup instructions
- [README.md](../README.md) - Main project documentation
