# Local Testing Guide

This guide explains how to test the IFCER batch service locally without Docker, using self-signed certificates and a mock InfoCert API.

## Overview

The local testing setup includes:

1. **Self-signed certificates** for mTLS (mutual TLS)
2. **Mock InfoCert API server** that mimics the real InfoCert Sign API
3. **Sample test files** uploaded to S3
4. **IFCER batch service** running locally

## Prerequisites

### Required Software

- Python 3.11+
- OpenSSL (for certificate generation)
- AWS CLI (configured with credentials)
- boto3 (AWS SDK for Python)
- Flask (for mock API server)

### AWS Resources

You'll need:
- An S3 bucket (or use LocalStack for local S3)
- A DynamoDB table (or use LocalStack for local DynamoDB)
- AWS credentials with appropriate permissions

## Step-by-Step Setup

### Step 1: Generate Self-Signed Certificates

Generate test certificates for mTLS authentication:

```bash
# Make script executable
chmod +x scripts/generate_test_certs.sh

# Generate certificates
bash scripts/generate_test_certs.sh
```

This creates certificates in `test_certs/`:
- `client_cert.pem` - Client certificate (for IFCER service)
- `client_key.pem` - Client private key (for IFCER service)
- `server_cert.pem` - Server certificate (for mock API)
- `server_key.pem` - Server private key (for mock API)
- `ca_bundle.pem` - Certificate Authority bundle

**⚠️ WARNING:** These are self-signed certificates for **TESTING ONLY**. Never use in production!

### Step 2: Install Python Dependencies

```bash
# Install IFCER service dependencies
pip install -r requirements.txt

# Install testing dependencies
pip install flask
```

### Step 3: Upload Test Certificates to S3

```bash
# Set your S3 bucket name
export S3_BUCKET_NAME=your-test-bucket
export AWS_REGION=eu-south-1

# Upload certificates
aws s3 cp test_certs/client_cert.pem s3://$S3_BUCKET_NAME/certs/client_cert.pem
aws s3 cp test_certs/client_key.pem s3://$S3_BUCKET_NAME/certs/client_key.pem
aws s3 cp test_certs/ca_bundle.pem s3://$S3_BUCKET_NAME/certs/ca_bundle.pem
```

### Step 4: Create and Upload Test Data

```bash
# Run the test data setup script
python tests/setup_test_data.py
```

This script:
- Creates 4 sample files (XML, JSON, TXT, CSV)
- Uploads them to S3 in the `incoming/` folder
- Verifies the upload was successful

### Step 5: Configure Environment Variables

Create a `.env` file in the project root:

```bash
# Application Configuration
APP_NAME=IFCER Batch Service (TEST)
LOG_LEVEL=DEBUG

# AWS Configuration
AWS_REGION=eu-south-1
S3_BUCKET_NAME=your-test-bucket
DYNAMODB_TABLE_NAME=ifcer-certifications-test

# Mock InfoCert API Configuration
VENDOR_API_URL=https://127.0.0.1:8443
INFOCERT_CREDENTIAL_ID=test-credential-id
VENDOR_MTLS_CERT_S3_KEY=certs/client_cert.pem
VENDOR_MTLS_KEY_S3_KEY=certs/client_key.pem
VENDOR_MTLS_CA_S3_KEY=certs/ca_bundle.pem

# Processing Configuration
HASH_ALGORITHM=sha256
BATCH_SIZE=100
REQUEST_TIMEOUT=30
```

### Step 6: Create DynamoDB Table

Create a test DynamoDB table:

```bash
aws dynamodb create-table \
  --table-name ifcer-certifications-test \
  --attribute-definitions \
    AttributeName=file_key,AttributeType=S \
    AttributeName=processing_timestamp,AttributeType=S \
    AttributeName=filename,AttributeType=S \
    AttributeName=date_partition,AttributeType=S \
  --key-schema \
    AttributeName=file_key,KeyType=HASH \
    AttributeName=processing_timestamp,KeyType=RANGE \
  --global-secondary-indexes \
    '[{
      "IndexName": "filename-index",
      "KeySchema": [
        {"AttributeName": "filename", "KeyType": "HASH"},
        {"AttributeName": "processing_timestamp", "KeyType": "RANGE"}
      ],
      "Projection": {"ProjectionType": "ALL"},
      "ProvisionedThroughput": {"ReadCapacityUnits": 5, "WriteCapacityUnits": 5}
    },
    {
      "IndexName": "date-index",
      "KeySchema": [
        {"AttributeName": "date_partition", "KeyType": "HASH"},
        {"AttributeName": "processing_timestamp", "KeyType": "RANGE"}
      ],
      "Projection": {"ProjectionType": "ALL"},
      "ProvisionedThroughput": {"ReadCapacityUnits": 5, "WriteCapacityUnits": 5}
    }]' \
  --provisioned-throughput \
    ReadCapacityUnits=5,WriteCapacityUnits=5 \
  --region eu-south-1
```

Or use the AWS console to create the table manually.

## Running the Tests

### Terminal 1: Start Mock InfoCert API

```bash
# Make script executable
chmod +x tests/mock_infocert_api.py

# Start the mock API server
python tests/mock_infocert_api.py
```

You should see:
```
=============================================================
  Mock InfoCert Sign API Server
  FOR TESTING ONLY
=============================================================

[MOCK API] Certificate directory: /path/to/test_certs
[MOCK API] Loaded mock signing certificate
[MOCK API] mTLS enabled - requiring client certificate
[MOCK API] CA bundle: /path/to/test_certs/ca_bundle.pem

[MOCK API] Starting server...
[MOCK API] Host: 127.0.0.1
[MOCK API] Port: 8443
[MOCK API] Base URL: https://127.0.0.1:8443

Endpoints:
  GET  https://127.0.0.1:8443/health
  POST https://127.0.0.1:8443/sign/v2
```

### Terminal 2: Start IFCER Service

```bash
# Start the FastAPI application
uvicorn app.main:app --reload --port 8000
```

You should see:
```
INFO:     Uvicorn running on http://127.0.0.1:8000
INFO:     Application startup complete.
```

### Terminal 3: Test the Service

#### 1. Health Check

```bash
curl http://localhost:8000/api/v1/health
```

Expected response:
```json
{
  "status": "healthy",
  "timestamp": "2025-11-10T10:00:00.000000Z",
  "version": "1.0.0"
}
```

#### 2. Process Batch

```bash
curl -X POST http://localhost:8000/api/v1/process \
  -H 'Content-Type: application/json' \
  -d '{
    "start_date": "2025-11-01T00:00:00Z",
    "end_date": "2025-11-30T23:59:59Z",
    "prefix": "incoming/"
  }'
```

Expected response:
```json
{
  "total_files": 4,
  "processed_files": 4,
  "successful_files": 4,
  "failed_files": 0,
  "results": [
    {
      "file_key": "incoming/trade_declaration_001.xml",
      "status": "completed",
      "file_hash": "abc123...",
      "signature": "xyz789...",
      "timestamp": "2025-11-10T10:00:00Z",
      "p7m_file_key": "signed/trade_declaration_001.xml.p7m",
      "error_message": null
    },
    ...
  ],
  "processing_start": "2025-11-10T10:00:00Z",
  "processing_end": "2025-11-10T10:00:05Z",
  "duration_seconds": 5.2
}
```

#### 3. Recertify Single File

```bash
curl -X POST http://localhost:8000/api/v1/recertify \
  -H 'Content-Type: application/json' \
  -d '{
    "file_key": "incoming/invoice_12345.json"
  }'
```

## Monitoring and Logs

### IFCER Service Logs

The service logs will show detailed progress:

```
[BATCH START] Starting batch processing | Date range: 2025-11-01T00:00:00 to 2025-11-30T23:59:59 | Prefix: incoming/
[BATCH STEP 1/2] Listing files from S3...
[S3 LIST] ✓ File listing complete | Found: 4 files | Scanned: 4 objects | Pages: 1 | Total size: 2,456 bytes | Duration: 0.25s
[BATCH STEP 1/2] Found 4 files to process
[BATCH STEP 2/2] Processing 4 files...
[BATCH PROGRESS] Processing file 1/4 (25.0%) | File: incoming/trade_declaration_001.xml
[FILE PROCESS] Starting processing | File: incoming/trade_declaration_001.xml
[FILE STEP 1/5] Downloaded 756 bytes from S3
[FILE STEP 2/5] Hash computed | Algorithm: SHA256 | Hash: f2a7c53b8c9b80f4...
[FILE STEP 3/5] Requesting digital signature from InfoCert...
[SIGN START] File: trade_declaration_001.xml | Hash: f2a7c53b8c9b80f4... | Algorithm: sha256
[STEP 1/5] Created manifest: 234 bytes
[STEP 3/5] mTLS session established
[STEP 4/5] Sending manifest to InfoCert for signing...
[STEP 5/5] P7M file created: 3456 bytes
[SIGN COMPLETE] File: trade_declaration_001.xml | P7M size: 3456 bytes | Duration: 0.85s
[FILE STEP 4/5] P7M uploaded to S3 | Size: 3456 bytes
[FILE STEP 5/5] Metadata saved to DynamoDB
[FILE COMPLETE] ✓ Processing complete | Duration: 1.45s
```

### Mock API Logs

The mock API will show requests:

```
[MOCK API] Received signature request:
  Credential ID: test-credential-id
  Documents: 1

  Document 1:
    Filename: trade_declaration_001.xml
    Hash: f2a7c53b8c9b80f4...
    Algorithm: SHA256
    ✓ Generated mock signature: 9a8b7c6d5e4f3a2b...

[MOCK API] ✓ Returning 1 signature(s)
```

## Verifying Results

### Check S3 for P7M Files

```bash
# List signed files
aws s3 ls s3://$S3_BUCKET_NAME/signed/

# Download a signed file
aws s3 cp s3://$S3_BUCKET_NAME/signed/trade_declaration_001.xml.p7m ./
```

### Check DynamoDB for Metadata

```bash
# Query all certifications
aws dynamodb scan \
  --table-name ifcer-certifications-test \
  --region eu-south-1
```

### Inspect P7M File

```bash
# View P7M file structure
openssl pkcs7 -in trade_declaration_001.xml.p7m -inform DER -print -noout

# Extract signed content
openssl pkcs7 -in trade_declaration_001.xml.p7m -inform DER -print_certs
```

## Troubleshooting

### Certificate Errors

If you see certificate verification errors:

1. **Check certificates exist:**
   ```bash
   ls -la test_certs/
   ```

2. **Verify certificate validity:**
   ```bash
   openssl x509 -in test_certs/client_cert.pem -text -noout
   ```

3. **Check S3 certificate upload:**
   ```bash
   aws s3 ls s3://$S3_BUCKET_NAME/certs/
   ```

### Connection Errors

If the service can't connect to mock API:

1. **Verify mock API is running:**
   ```bash
   curl -k https://127.0.0.1:8443/health
   ```

2. **Check VENDOR_API_URL in .env:**
   ```bash
   grep VENDOR_API_URL .env
   ```

3. **Test mTLS connection:**
   ```bash
   curl -k \
     --cert test_certs/client_cert.pem \
     --key test_certs/client_key.pem \
     --cacert test_certs/ca_bundle.pem \
     https://127.0.0.1:8443/health
   ```

### S3/DynamoDB Errors

If you see AWS errors:

1. **Check AWS credentials:**
   ```bash
   aws sts get-caller-identity
   ```

2. **Verify bucket exists:**
   ```bash
   aws s3 ls s3://$S3_BUCKET_NAME
   ```

3. **Check DynamoDB table:**
   ```bash
   aws dynamodb describe-table --table-name ifcer-certifications-test
   ```

## Cleanup

### Remove Test Data

```bash
# Delete test files from S3
aws s3 rm s3://$S3_BUCKET_NAME/incoming/ --recursive
aws s3 rm s3://$S3_BUCKET_NAME/signed/ --recursive
aws s3 rm s3://$S3_BUCKET_NAME/certs/ --recursive

# Delete DynamoDB table
aws dynamodb delete-table --table-name ifcer-certifications-test

# Remove local test files
rm -rf tests/test_files
rm -rf test_certs
```

## Using LocalStack (Optional)

For completely local testing without real AWS:

### Install LocalStack

```bash
pip install localstack
```

### Start LocalStack

```bash
localstack start
```

### Configure AWS CLI for LocalStack

```bash
export AWS_ENDPOINT_URL=http://localhost:4566
export AWS_ACCESS_KEY_ID=test
export AWS_SECRET_ACCESS_KEY=test
export AWS_REGION=eu-south-1
```

### Update .env

```bash
# Add to .env
AWS_ENDPOINT_URL=http://localhost:4566
```

Then follow the same steps above - all AWS operations will use LocalStack instead of real AWS.

## Next Steps

- Review the [API Documentation](API.md)
- Understand the [Architecture](ARCHITECTURE.md)
- Deploy to production (see [DEPLOYMENT.md](DEPLOYMENT.md))
