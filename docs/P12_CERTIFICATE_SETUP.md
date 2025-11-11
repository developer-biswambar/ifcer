# P12 Certificate Setup for InfoCert mTLS Authentication

This guide explains how to use your P12 certificate from InfoCert for mTLS authentication with the IFCER Batch Service.

> **📌 IMPORTANT UPDATE:** As of the latest version, the IFCER service **supports P12 files directly**! You can upload your P12 file to S3 and use it with a password - **no conversion required**.
>
> **Extraction to PEM is now OPTIONAL** and only needed if you prefer PEM format or have specific requirements.

## Table of Contents

- [Option 1: Use P12 Directly (Recommended)](#option-1-use-p12-directly-recommended)
- [Option 2: Extract to PEM Format (Legacy)](#option-2-extract-to-pem-format-legacy)
- [Configuration](#configuration)
- [Testing](#testing)
- [Troubleshooting](#troubleshooting)
- [Security Best Practices](#security-best-practices)

---

## Option 1: Use P12 Directly (Recommended)

**✅ Simplest approach - no conversion needed!**

### Overview

InfoCert provides P12 (PKCS#12) certificates for mTLS authentication. The IFCER service can now use these directly.

**What you need:**
- P12 certificate file from InfoCert (e.g., `infocert_cert.p12`)
- P12 password
- AWS S3 bucket for storing certificates

### Quick Start with P12

```bash
# 1. Upload P12 to S3
aws s3 cp ~/Downloads/infocert_cert.p12 s3://YOUR-BUCKET/certs/client_cert.p12

# 2. Update .env
cat >> .env << EOF
INFOCERT_API_URL=https://mtlsapistage.infocert.digital/signature/v1

INFOCERT_CREDENTIAL_ID=your-credential-id
VENDOR_MTLS_P12_S3_KEY=certs/client_cert.p12
VENDOR_MTLS_P12_PASSWORD=your-p12-password
EOF

# 3. Test
python -c "from app.services.signature_service import SignatureService; s = SignatureService(); print('✓ P12 certificate loaded successfully!')"
```

**That's it!** The service will automatically extract the certificate and key from P12 at startup.

---

## Option 2: Extract to PEM Format (Legacy)

**Use this option if:**
- You need to inspect certificates manually
- You have specific security requirements for key storage
- You prefer traditional PEM format

### Overview

Convert P12 certificates to PEM format for manual management.

**What you'll get after extraction:**
- `client_cert.pem` - Your client certificate
- `client_key.pem` - Your private key
- `ca_bundle.pem` - CA certificates (optional)

### Prerequisites for PEM Extraction

**Required Software:**

```bash
# macOS
brew install openssl awscli

# Linux (Ubuntu/Debian)
sudo apt-get install openssl awscli

# Verify installation
openssl version  # Should show OpenSSL 1.1.1 or later
aws --version    # Should show AWS CLI
```

**Required Access:**
- P12 file from InfoCert
- P12 password
- AWS credentials with S3 access
- S3 bucket created

### Quick Start with PEM Extraction

```bash
# 1. Extract PEM files from P12
./scripts/extract_p12_to_pem.sh ~/Downloads/infocert_cert.p12

# 2. Upload to S3
aws s3 cp certs/client_cert.pem s3://YOUR-BUCKET/certs/
aws s3 cp certs/client_key.pem s3://YOUR-BUCKET/certs/
aws s3 cp certs/ca_bundle.pem s3://YOUR-BUCKET/certs/  # If exists

# 3. Update .env (comment out P12 settings if present)
cat >> .env << EOF
INFOCERT_API_URL=https://mtlsapistage.infocert.digital/signature/v1

INFOCERT_CREDENTIAL_ID=your-credential-id
VENDOR_MTLS_CERT_S3_KEY=certs/client_cert.pem
VENDOR_MTLS_KEY_S3_KEY=certs/client_key.pem
VENDOR_MTLS_CA_S3_KEY=certs/ca_bundle.pem
EOF

# 4. Test
python -c "from app.services.signature_service import SignatureService; s = SignatureService(); print('✓ PEM certificates loaded successfully!')"
```

### Step-by-Step PEM Extraction

#### Step 1: Extract PEM Files

We provide an automated script:

```bash
cd /path/to/ifcer

# Run extraction script
./scripts/extract_p12_to_pem.sh ~/Downloads/infocert_cert.p12

# Or specify custom output directory
./scripts/extract_p12_to_pem.sh ~/Downloads/infocert_cert.p12 ./my_certs
```

**The script will:**
1. Prompt for P12 password
2. Validate the P12 file
3. Extract certificate, private key, and CA bundle
4. Verify the extracted files
5. Show next steps

**Output:**
```
✓ Client certificate extracted: ./certs/client_cert.pem
✓ Private key extracted: ./certs/client_key.pem
✓ CA bundle extracted: ./certs/ca_bundle.pem
✓ Private key matches certificate
```

### Step 2: Manual Extraction (Alternative)

If you prefer manual extraction:

```bash
# Create output directory
mkdir -p certs

# Extract client certificate
openssl pkcs12 -in infocert_cert.p12 -clcerts -nokeys -out certs/client_cert.pem

# Extract private key (unencrypted)
openssl pkcs12 -in infocert_cert.p12 -nocerts -nodes -out certs/client_key.pem

# Extract CA certificates
openssl pkcs12 -in infocert_cert.p12 -cacerts -nokeys -out certs/ca_bundle.pem

# Secure the private key
chmod 600 certs/client_key.pem
```

### Step 3: Verify Extraction

```bash
# View certificate details
openssl x509 -in certs/client_cert.pem -noout -text

# Check certificate validity dates
openssl x509 -in certs/client_cert.pem -noout -dates

# Verify private key matches certificate
openssl x509 -in certs/client_cert.pem -noout -modulus | openssl md5
openssl rsa -in certs/client_key.pem -noout -modulus | openssl md5
# The MD5 hashes should match
```

## Uploading to S3

### Option 1: AWS CLI (Recommended)

```bash
# Set your bucket name
export S3_BUCKET=your-ifcer-bucket

# Upload certificates with server-side encryption
aws s3 cp certs/client_cert.pem s3://$S3_BUCKET/certs/ --sse AES256
aws s3 cp certs/client_key.pem s3://$S3_BUCKET/certs/ --sse AES256
aws s3 cp certs/ca_bundle.pem s3://$S3_BUCKET/certs/ --sse AES256

# Verify upload
aws s3 ls s3://$S3_BUCKET/certs/
```

### Option 2: AWS Console

1. Go to AWS S3 Console
2. Navigate to your bucket
3. Create folder: `certs/`
4. Upload the three PEM files
5. Enable "Server-side encryption" during upload

### Option 3: Upload Script

```bash
# Create upload script
cat > upload_certs_to_s3.sh << 'EOF'
#!/bin/bash
set -e

S3_BUCKET="${1:-your-bucket-name}"
CERT_DIR="${2:-./certs}"

echo "Uploading certificates to s3://$S3_BUCKET/certs/"

aws s3 cp "$CERT_DIR/client_cert.pem" "s3://$S3_BUCKET/certs/" --sse AES256
aws s3 cp "$CERT_DIR/client_key.pem" "s3://$S3_BUCKET/certs/" --sse AES256

if [ -f "$CERT_DIR/ca_bundle.pem" ]; then
    aws s3 cp "$CERT_DIR/ca_bundle.pem" "s3://$S3_BUCKET/certs/" --sse AES256
fi

echo "✓ Upload complete!"
aws s3 ls "s3://$S3_BUCKET/certs/"
EOF

chmod +x upload_certs_to_s3.sh

# Run it
./upload_certs_to_s3.sh your-bucket-name
```

---

## Configuration

### Environment Variables

Choose **ONE** of the following configurations:

#### Option A: P12 Configuration (Recommended)

```bash
# S3 Bucket
S3_BUCKET_NAME=your-ifcer-bucket

# InfoCert API
# InfoCert uses a single mTLS API endpoint for all operations (authentication, signing, etc.)
# STAGE:      https://mtlsapistage.infocert.digital/signature/v1
# PRODUCTION: https://mtlsapi.infocert.digital/signature/v1
# Signing endpoint: /multi/sign
INFOCERT_API_URL=https://mtlsapistage.infocert.digital/signature/v1

INFOCERT_CREDENTIAL_ID=your-credential-id

# P12 Certificate (direct usage)
VENDOR_MTLS_P12_S3_KEY=certs/client_cert.p12
VENDOR_MTLS_P12_PASSWORD=your-p12-password
```

#### Option B: PEM Configuration (Legacy)

```bash
# S3 Bucket
S3_BUCKET_NAME=your-ifcer-bucket

# InfoCert API
INFOCERT_API_URL=https://mtlsapistage.infocert.digital/signature/v1

INFOCERT_CREDENTIAL_ID=your-credential-id

# PEM Certificates (extracted from P12)
VENDOR_MTLS_CERT_S3_KEY=certs/client_cert.pem
VENDOR_MTLS_KEY_S3_KEY=certs/client_key.pem
VENDOR_MTLS_CA_S3_KEY=certs/ca_bundle.pem
```

**Note:** If both P12 and PEM settings are provided, P12 takes precedence.

### Verify Configuration

```bash
# Check environment
cat .env | grep VENDOR

# Test certificate loading
python3 << 'EOF'
from app.config import settings
print(f"✓ Bucket: {settings.s3_bucket_name}")
print(f"✓ Cert key: {settings.vendor_mtls_cert_s3_key}")
print(f"✓ API URL: {settings.vendor_api_url}")
EOF
```

## Testing

### Test 1: Certificate Loading

```python
# Test if certificates load from S3
python3 << 'EOF'
from app.services.signature_service import SignatureService

print("Loading certificates from S3...")
service = SignatureService()
print("✓ SignatureService initialized successfully!")
print(f"✓ Certificate loaded from: {service.cert_path}")
print(f"✓ Private key loaded from: {service.key_path}")
EOF
```

### Test 2: Local mTLS Test

```bash
# Test with curl (using local certificates)
curl --cert certs/client_cert.pem \
     --key certs/client_key.pem \
     --cacert certs/ca_bundle.pem \
     -v \
     https://api.infocert.it/sign/v1/health

# Expected: 200 OK or valid response from InfoCert
```

### Test 3: Full Service Test

```bash
# Start the service
uvicorn app.main:app --reload

# In another terminal, test health check
curl http://localhost:8000/health

# Should show:
# {
#   "status": "healthy",
#   "timestamp": "...",
#   "version": "..."
# }
```

## Troubleshooting

### Issue: "Invalid P12 file or incorrect password"

```bash
# Verify P12 file is valid
openssl pkcs12 -in your_cert.p12 -info -noout

# If password is wrong, contact InfoCert for the correct password
```

### Issue: "Private key does NOT match certificate"

This means the P12 file is corrupted or contains multiple certificates. Try:

```bash
# List all certificates in P12
openssl pkcs12 -in your_cert.p12 -info

# Extract specific certificate by alias
openssl pkcs12 -in your_cert.p12 -clcerts -nokeys -name "YourCertAlias" -out client_cert.pem
```

### Issue: "NoSuchKey: The specified key does not exist" (S3 Error)

```bash
# Check if files exist in S3
aws s3 ls s3://your-bucket/certs/

# Check S3 key in config matches uploaded files
echo $VENDOR_MTLS_CERT_S3_KEY

# Verify IAM permissions for S3 access
aws s3api head-object --bucket your-bucket --key certs/client_cert.pem
```

### Issue: "SSL: CERTIFICATE_VERIFY_FAILED"

This means the CA bundle is missing or incorrect.

```bash
# Test without CA bundle first
# In .env, comment out:
# VENDOR_MTLS_CA_S3_KEY=certs/ca_bundle.pem

# Or provide InfoCert's CA certificate separately
```

### Issue: Certificate Expired

```bash
# Check certificate validity
openssl x509 -in certs/client_cert.pem -noout -dates

# Output:
# notBefore=Jan  1 00:00:00 2024 GMT
# notAfter=Dec 31 23:59:59 2025 GMT

# If expired, request new certificate from InfoCert
```

## Security Best Practices

### 1. Protect Private Keys

```bash
# Never commit private keys to git
echo "certs/" >> .gitignore
echo "*.pem" >> .gitignore
echo "*.p12" >> .gitignore

# Restrict file permissions
chmod 600 certs/client_key.pem
chmod 600 infocert_cert.p12

# Delete local copies after upload to S3
rm -f certs/client_key.pem  # After confirming S3 upload works
```

### 2. S3 Security

```bash
# Enable S3 encryption at rest
aws s3api put-bucket-encryption \
  --bucket your-bucket \
  --server-side-encryption-configuration '{
    "Rules": [{
      "ApplyServerSideEncryptionByDefault": {
        "SSEAlgorithm": "AES256"
      }
    }]
  }'

# Enable S3 versioning (for backup)
aws s3api put-bucket-versioning \
  --bucket your-bucket \
  --versioning-configuration Status=Enabled

# Block public access
aws s3api put-public-access-block \
  --bucket your-bucket \
  --public-access-block-configuration \
    BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
```

### 3. IAM Policy

Minimal IAM policy for ECS task:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject"
      ],
      "Resource": [
        "arn:aws:s3:::your-bucket/certs/*"
      ]
    }
  ]
}
```

### 4. Certificate Rotation

Set up reminders for certificate expiration:

```bash
# Check expiration date
openssl x509 -in certs/client_cert.pem -noout -enddate

# Set up CloudWatch alarm for certificate expiration
# (See AWS documentation for CloudWatch certificate monitoring)
```

### 5. Secrets Management

For production, consider:

- **AWS Secrets Manager** - Store P12 password
- **AWS Systems Manager Parameter Store** - Store certificate paths
- **AWS KMS** - Additional encryption layer

## Summary Checklist

- [ ] Extract PEM files from P12
- [ ] Verify certificates are valid
- [ ] Upload to S3 with encryption
- [ ] Update `.env` configuration
- [ ] Test certificate loading
- [ ] Test mTLS connection to InfoCert
- [ ] Delete local private key copies
- [ ] Add certs/ to .gitignore
- [ ] Document expiration date
- [ ] Set IAM permissions
- [ ] Test the full service

## Need Help?

- Check InfoCert documentation for API details
- Review `app/services/signature_service.py` for implementation
- Check logs: `tail -f logs/ifcer.log`
- Test with curl before testing with the service

## Reference

- [OpenSSL PKCS12 Documentation](https://www.openssl.org/docs/man1.1.1/man1/pkcs12.html)
- [AWS S3 Encryption](https://docs.aws.amazon.com/AmazonS3/latest/userguide/UsingEncryption.html)
- [InfoCert API Documentation](https://developers.infocert.digital/)
