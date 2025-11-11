# Local Testing Guide - IFCER Batch Service with Real InfoCert API

Step-by-step guide for testing the IFCER service locally with actual InfoCert API integration.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Environment Setup](#environment-setup)
- [Upload Test Files to S3](#upload-test-files-to-s3)
- [Start the Service](#start-the-service)
- [Test API Endpoints](#test-api-endpoints)
- [Verify DynamoDB Records](#verify-dynamodb-records)
- [Troubleshooting](#troubleshooting)

---

## Prerequisites

### ✅ What You Need

- [x] P12 certificate from InfoCert
- [x] P12 file uploaded to S3 (or PEM files if already extracted)
- [x] P12 password
- [x] S3 bucket created
- [x] DynamoDB table created
- [x] InfoCert API URL (STAGE or PRODUCTION)
- [x] InfoCert Credential ID (X-signer-id)
- [x] Test PDF/XML files to process

### 📋 Check Your Setup

```bash
# 1. Verify S3 certificates exist
aws s3 ls s3://YOUR-BUCKET/certs/
# Should show either:
#   client_cert.p12 (P12 format - recommended)
# OR:
#   client_cert.pem, client_key.pem, ca_bundle.pem (PEM format)

# 2. Verify DynamoDB table exists
aws dynamodb describe-table --table-name ifcer-certifications
# Should show table details

# 3. Verify you have test files
ls ~/test-files/
# Should have some PDF or XML files to test
```

---

## Environment Setup

### Step 1: Create `.env` File

```bash
cd /path/to/ifcer

# Copy example
cp .env.example .env

# Edit .env with your actual values
nano .env
```

### Step 2: Configure `.env` with REAL Values

```bash
# ==================== Application ====================
APP_NAME=IFCER Batch Service
LOG_LEVEL=INFO

# ==================== AWS Configuration ====================
# Use your actual AWS region where you created resources
AWS_REGION=eu-south-1

# Your actual S3 bucket name
S3_BUCKET_NAME=your-actual-bucket-name

# Your actual DynamoDB table name
DYNAMODB_TABLE_NAME=ifcer-certifications

# Optional: Auto-delete records after N days
# DYNAMODB_TTL_DAYS=365

# ==================== InfoCert API (REAL) ====================
# InfoCert uses a single mTLS API endpoint for all operations
# (authentication, signing, etc.)
#
# ENVIRONMENTS:
#   STAGE:      https://mtlsapistage.infocert.digital/signature/v1
#   PRODUCTION: https://mtlsapi.infocert.digital/signature/v1
#
# Signing endpoint: /multi/sign
# Use STAGE for testing, PRODUCTION for live operations
INFOCERT_API_URL=https://mtlsapistage.infocert.digital/signature/v1

# Your InfoCert Credential ID (X-signer-id header)
# STAGING: MA678944, PRODUCTION: MOI56167
INFOCERT_CREDENTIAL_ID=MA678944

# ==================== mTLS Certificate Configuration ====================
# OPTION 1: Use P12 file directly (RECOMMENDED - simpler setup)
# Upload your P12 file to S3:
#   aws s3 cp your_cert.p12 s3://YOUR-BUCKET/certs/client_cert.p12
VENDOR_MTLS_P12_S3_KEY=certs/client_cert.p12
VENDOR_MTLS_P12_PASSWORD=your-p12-password

# OPTION 2: Use PEM files (if you already extracted them)
# Uncomment these if you're using PEM instead of P12:
# VENDOR_MTLS_CERT_S3_KEY=certs/client_cert.pem
# VENDOR_MTLS_KEY_S3_KEY=certs/client_key.pem
# VENDOR_MTLS_CA_S3_KEY=certs/ca_bundle.pem

# ==================== Processing Configuration ====================
HASH_ALGORITHM=sha256
BATCH_SIZE=100
REQUEST_TIMEOUT=30
```

### Step 3: Verify Environment Variables

```bash
# Load .env and verify
source .env

# Check critical variables
echo "S3 Bucket: $S3_BUCKET_NAME"
echo "DynamoDB Table: $DYNAMODB_TABLE_NAME"
echo "InfoCert API: $INFOCERT_API_URL"
echo "Credential ID: $INFOCERT_CREDENTIAL_ID"

# All should show your actual values (not "your-actual-...")
```

---

## Upload P12 Certificate to S3

### Step 1: Upload Your P12 File

```bash
# Set your bucket name
export S3_BUCKET=your-actual-bucket-name

# Upload P12 certificate
aws s3 cp /path/to/your_cert.p12 s3://$S3_BUCKET/certs/client_cert.p12

# Verify upload
aws s3 ls s3://$S3_BUCKET/certs/
# Should show: client_cert.p12
```

### Step 2: Update .env with P12 Password

```bash
# Edit .env file
nano .env

# Ensure these are set:
# VENDOR_MTLS_P12_S3_KEY=certs/client_cert.p12
# VENDOR_MTLS_P12_PASSWORD=your-actual-p12-password
```

**Note:** If you prefer to use PEM files instead, see `docs/P12_CERTIFICATE_SETUP.md` for extraction instructions.

---

## Upload Test Files to S3

### Step 1: Prepare Test Files

```bash
# Create test files directory
mkdir -p ~/test-files

# Create a test PDF (if you don't have one)
echo "This is a test document for IFCER certification" > ~/test-files/test_document.txt

# Or use actual PDF/XML files you want to certify
cp ~/Documents/important.pdf ~/test-files/
cp ~/Documents/invoice.xml ~/test-files/
```

### Step 2: Upload to S3

```bash
# Set your bucket name
export S3_BUCKET=your-actual-bucket-name

# Upload test files to the uploads/ prefix
aws s3 cp ~/test-files/test_document.txt s3://$S3_BUCKET/uploads/
aws s3 cp ~/test-files/important.pdf s3://$S3_BUCKET/uploads/
aws s3 cp ~/test-files/invoice.xml s3://$S3_BUCKET/uploads/

# Verify upload
aws s3 ls s3://$S3_BUCKET/uploads/
```

### Step 3: Note Upload Timestamps

```bash
# Get file details (you'll need timestamps for date range queries)
aws s3api head-object \
  --bucket $S3_BUCKET \
  --key uploads/test_document.txt \
  --query 'LastModified' \
  --output text

# Save this timestamp - you'll use it for testing
```

---

## Start the Service

### Step 1: Install Dependencies

```bash
# Make sure you're in the project directory
cd /path/to/ifcer

# Activate virtual environment (if using one)
source .venv/bin/activate  # or: conda activate your-env

# Install dependencies
pip install -r requirements.txt
```

### Step 2: Test Configuration

```bash
# Quick test - can we load settings?
python -c "from app.config import settings; print(f'✓ Bucket: {settings.s3_bucket_name}')"

# Test certificate loading
python -c "from app.services.signature_service import SignatureService; s = SignatureService(); print('✓ Certificates loaded from S3!')"

# If this works, you're ready to start the service!
```

### Step 3: Start the Service

```bash
# Start with uvicorn
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# You should see:
# INFO:     Application startup complete.
# INFO:     Uvicorn running on http://0.0.0.0:8000
```

**Keep this terminal running!** Open a new terminal for the next steps.

---

## Test API Endpoints

### 🏥 Test 1: Health Check

**What it does:** Verifies service is running and can connect to S3.

**Note:** InfoCert does not provide a health check endpoint, so only S3 connectivity is verified.

```bash
# Basic health check
curl -X GET http://localhost:8000/health \
  -H "Content-Type: application/json" \
  | jq

# Expected response:
# {
#   "status": "healthy",
#   "timestamp": "2024-01-15T10:30:00Z",
#   "version": "1.0.0"
# }
```

**If health check fails:**
- Check S3 bucket access
- Check AWS credentials are configured correctly
- Check logs in the uvicorn terminal

---

### 📄 Test 2: Process Single File

**What it does:** Takes a single file from S3, computes hash, sends to InfoCert for signature, creates P7M file, saves to DynamoDB.

```bash
# Recertify a single file
curl -X POST http://localhost:8000/recertify \
  -H "Content-Type: application/json" \
  -d '{
    "file_key": "uploads/test_document.txt"
  }' \
  | jq

# Expected response:
# {
#   "file_key": "uploads/test_document.txt",
#   "status": "completed",
#   "file_hash": "abc123...",
#   "signature": "xyz789...",
#   "timestamp": "2024-01-15T10:35:00Z",
#   "p7m_file_key": "signed/test_document.txt.p7m",
#   "error_message": null
# }
```

**What happens:**
1. Downloads `uploads/test_document.txt` from S3
2. Computes SHA256 hash
3. Creates manifest JSON with hash
4. Sends to InfoCert API for signature (uses your mTLS certs)
5. Creates P7M file with signed manifest
6. Uploads P7M to `s3://YOUR-BUCKET/signed/test_document.txt.p7m`
7. Saves metadata to DynamoDB

**Verify the result:**

```bash
# Check if P7M file was created in S3
aws s3 ls s3://$S3_BUCKET/signed/

# Download and inspect the P7M file
aws s3 cp s3://$S3_BUCKET/signed/test_document.txt.p7m ./
file test_document.txt.p7m
# Should show: "PKCS7 signature"

# Extract and view the signed manifest
openssl pkcs7 -in test_document.txt.p7m -inform DER -print_certs -text
```

---

### 📦 Test 3: Batch Processing by Date Range

**What it does:** Processes all files uploaded within a date range.

```bash
# Get current date for testing
START_DATE=$(date -u -v-1d +"%Y-%m-%dT%H:%M:%SZ")  # Yesterday (macOS)
# Or for Linux: START_DATE=$(date -u -d "yesterday" +"%Y-%m-%dT%H:%M:%SZ")

END_DATE=$(date -u +"%Y-%m-%dT%H:%M:%SZ")  # Now

echo "Date range: $START_DATE to $END_DATE"

# Process all files in date range
curl -X POST http://localhost:8000/process \
  -H "Content-Type: application/json" \
  -d "{
    \"start_date\": \"$START_DATE\",
    \"end_date\": \"$END_DATE\"
  }" \
  | jq

# Expected response:
# {
#   "total_files": 3,
#   "processed_files": 3,
#   "successful_files": 3,
#   "failed_files": 0,
#   "results": [
#     {
#       "file_key": "uploads/test_document.txt",
#       "status": "completed",
#       "file_hash": "...",
#       "signature": "...",
#       "timestamp": "...",
#       "p7m_file_key": "signed/test_document.txt.p7m"
#     },
#     ...
#   ],
#   "processing_start": "...",
#   "processing_end": "...",
#   "duration_seconds": 5.2
# }
```

**Batch Processing with Prefix Filter:**

```bash
# Process only PDF files
curl -X POST http://localhost:8000/process \
  -H "Content-Type: application/json" \
  -d "{
    \"start_date\": \"$START_DATE\",
    \"end_date\": \"$END_DATE\",
    \"prefix\": \"uploads/\"
  }" \
  | jq
```

---

### 🔍 Test 4: Query File Details

**What it does:** Get certification status for a specific file.

```bash
# Get details for a specific file
curl -X POST http://localhost:8000/file-details \
  -H "Content-Type: application/json" \
  -d '{
    "filename": "test_document.txt"
  }' \
  | jq

# Expected response:
# {
#   "found": true,
#   "total_matches": 1,
#   "files": [
#     {
#       "original_file_key": "uploads/test_document.txt",
#       "original_file_size": 1024,
#       "original_upload_date": "2024-01-15T09:00:00Z",
#       "is_signed": true,
#       "signed_file_key": "signed/test_document.txt.p7m",
#       "signed_file_size": 2048,
#       "signing_timestamp": "2024-01-15T10:35:00Z",
#       "processing_timestamp": "2024-01-15T10:35:01Z",
#       "file_hash": "abc123...",
#       "hash_algorithm": "sha256",
#       "signature": "xyz789...",
#       "status": "completed"
#     }
#   ]
# }
```

---

### 📋 Test 5: List All Files by Date

**What it does:** Get list of all files and their certification status.

```bash
# List all files (with pagination)
curl -X POST http://localhost:8000/files-list \
  -H "Content-Type: application/json" \
  -d "{
    \"start_date\": \"$START_DATE\",
    \"end_date\": \"$END_DATE\",
    \"page\": 1,
    \"page_size\": 10
  }" \
  | jq

# Expected response:
# {
#   "total_files": 3,
#   "signed_files": 3,
#   "unsigned_files": 0,
#   "page": 1,
#   "page_size": 10,
#   "total_pages": 1,
#   "has_next": false,
#   "has_previous": false,
#   "files": [...]
# }

# List only signed files
curl -X POST http://localhost:8000/files-list \
  -H "Content-Type: application/json" \
  -d "{
    \"start_date\": \"$START_DATE\",
    \"end_date\": \"$END_DATE\",
    \"signed_only\": true,
    \"page\": 1,
    \"page_size\": 10
  }" \
  | jq
```

---

## Verify DynamoDB Records

### Check Certification Records

```bash
# List all items in DynamoDB table
aws dynamodb scan \
  --table-name ifcer-certifications \
  --max-items 10 \
  | jq

# Get specific file certification
aws dynamodb query \
  --table-name ifcer-certifications \
  --key-condition-expression "file_key = :fk" \
  --expression-attribute-values '{":fk":{"S":"uploads/test_document.txt"}}' \
  | jq

# Expected to see:
# {
#   "file_key": "uploads/test_document.txt",
#   "processing_timestamp": "...",
#   "file_hash": "...",
#   "hash_algorithm": "sha256",
#   "digital_signature": "...",
#   "vendor_timestamp": "...",
#   "signed_file_key": "signed/test_document.txt.p7m",
#   "file_size": 1024,
#   "signed_file_size": 2048,
#   "status": "completed"
# }
```

---

## Complete Test Script

Save this as `test_local.sh`:

```bash
#!/bin/bash
# Complete local testing script

set -e

echo "========================================"
echo "IFCER Local Testing Script"
echo "========================================"
echo ""

# Configuration
BASE_URL="http://localhost:8000"
S3_BUCKET="your-actual-bucket-name"
TEST_FILE="uploads/test_document.txt"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

# Test 1: Health Check
echo "Test 1: Health Check"
RESPONSE=$(curl -s -X GET $BASE_URL/health)
if echo $RESPONSE | jq -e '.status == "healthy"' > /dev/null; then
    echo -e "${GREEN}✓ Health check passed${NC}"
else
    echo -e "${RED}✗ Health check failed${NC}"
    echo $RESPONSE | jq
    exit 1
fi
echo ""

# Test 2: Process Single File
echo "Test 2: Process Single File"
RESPONSE=$(curl -s -X POST $BASE_URL/recertify \
  -H "Content-Type: application/json" \
  -d "{\"file_key\": \"$TEST_FILE\"}")

if echo $RESPONSE | jq -e '.status == "completed"' > /dev/null; then
    echo -e "${GREEN}✓ Single file processing passed${NC}"
    P7M_FILE=$(echo $RESPONSE | jq -r '.p7m_file_key')
    echo "  P7M file: $P7M_FILE"
else
    echo -e "${RED}✗ Single file processing failed${NC}"
    echo $RESPONSE | jq
    exit 1
fi
echo ""

# Test 3: Verify S3 Upload
echo "Test 3: Verify P7M in S3"
if aws s3 ls s3://$S3_BUCKET/$P7M_FILE > /dev/null 2>&1; then
    echo -e "${GREEN}✓ P7M file exists in S3${NC}"
else
    echo -e "${RED}✗ P7M file not found in S3${NC}"
    exit 1
fi
echo ""

# Test 4: Verify DynamoDB Record
echo "Test 4: Verify DynamoDB Record"
DYNAMO_RESULT=$(aws dynamodb query \
  --table-name ifcer-certifications \
  --key-condition-expression "file_key = :fk" \
  --expression-attribute-values "{\":fk\":{\"S\":\"$TEST_FILE\"}}" \
  --output json)

if echo $DYNAMO_RESULT | jq -e '.Items | length > 0' > /dev/null; then
    echo -e "${GREEN}✓ DynamoDB record exists${NC}"
else
    echo -e "${RED}✗ DynamoDB record not found${NC}"
    exit 1
fi
echo ""

# Test 5: Query File Details
echo "Test 5: Query File Details"
FILENAME=$(basename $TEST_FILE)
RESPONSE=$(curl -s -X POST $BASE_URL/file-details \
  -H "Content-Type: application/json" \
  -d "{\"filename\": \"$FILENAME\"}")

if echo $RESPONSE | jq -e '.found == true' > /dev/null; then
    echo -e "${GREEN}✓ File details query passed${NC}"
else
    echo -e "${RED}✗ File details query failed${NC}"
    echo $RESPONSE | jq
    exit 1
fi
echo ""

echo "========================================"
echo -e "${GREEN}✓ All tests passed!${NC}"
echo "========================================"
```

**Run it:**

```bash
chmod +x test_local.sh
./test_local.sh
```

---

## Troubleshooting

### Issue: "Service dependencies are not accessible" (503)

```bash
# Check S3 access
aws s3 ls s3://$S3_BUCKET/certs/

# Check if service can reach InfoCert API
curl -v https://YOUR-INFOCERT-API-URL/health
```

### Issue: "SSL: CERTIFICATE_VERIFY_FAILED"

```bash
# Test mTLS connection directly
curl --cert certs/client_cert.pem \
     --key certs/client_key.pem \
     -v \
     https://YOUR-INFOCERT-API-URL/

# If this fails, you need CA bundle
```

### Issue: "File not found in S3"

```bash
# Verify file exists
aws s3 ls s3://$S3_BUCKET/uploads/

# Check IAM permissions
aws s3api get-bucket-policy --bucket $S3_BUCKET
```

### Issue: "DynamoDB table does not exist"

```bash
# Create the table
aws dynamodb create-table \
  --table-name ifcer-certifications \
  --attribute-definitions \
    AttributeName=file_key,AttributeType=S \
    AttributeName=processing_timestamp,AttributeType=S \
  --key-schema \
    AttributeName=file_key,KeyType=HASH \
    AttributeName=processing_timestamp,KeyType=RANGE \
  --billing-mode PAY_PER_REQUEST
```

### View Logs

```bash
# Service logs (in uvicorn terminal)
# Look for detailed error messages

# Or save logs to file
uvicorn app.main:app --reload --log-level debug > service.log 2>&1
tail -f service.log
```

---

## Success Checklist

- [ ] Health check returns "healthy"
- [ ] Single file processing completes successfully
- [ ] P7M file appears in `s3://BUCKET/signed/`
- [ ] DynamoDB record created with certification data
- [ ] File details query returns certification info
- [ ] Batch processing works for date range
- [ ] Downloaded P7M file is valid PKCS7 signature

---

## Next Steps

Once local testing is successful:

1. **Deploy to ECS** - Use your Terraform/CloudFormation
2. **Test in Staging** - Run same tests against staging environment
3. **Production Deployment** - Deploy to production
4. **Monitoring** - Set up CloudWatch alarms
5. **Schedule Batch Jobs** - Set up cron/EventBridge for automated processing

---

## Quick Reference

### Useful Commands

```bash
# Restart service
# Ctrl+C in uvicorn terminal, then:
uvicorn app.main:app --reload

# Clear DynamoDB table
aws dynamodb scan --table-name ifcer-certifications \
  --attributes-to-get file_key processing_timestamp \
  | jq -r '.Items[] | "\(.file_key.S) \(.processing_timestamp.S)"' \
  | while read key timestamp; do
      aws dynamodb delete-item \
        --table-name ifcer-certifications \
        --key "{\"file_key\":{\"S\":\"$key\"},\"processing_timestamp\":{\"S\":\"$timestamp\"}}"
    done

# View service logs with grep
tail -f service.log | grep -i error

# Check InfoCert API response
curl -X POST http://localhost:8000/recertify \
  -H "Content-Type: application/json" \
  -d '{"file_key": "uploads/test.pdf"}' \
  2>&1 | tee last_response.json
```

Good luck with testing! 🚀
