# Moto Testing Guide

Complete local testing setup using **Moto** to mock AWS services (S3, DynamoDB) **without Docker**.

## What is Moto?

Moto is a Python library that mocks AWS services for testing. It runs as a standalone HTTP server that mimics AWS API endpoints - no Docker required!

## Quick Start (3 Terminals)

```bash
# Terminal 1: Start Moto (AWS mock)
pip install -r requirements-test.txt
python tests/run_moto_server.py

# Terminal 2: Setup AWS resources and start mock InfoCert API
python tests/setup_moto_resources.py
python tests/mock_infocert_api.py

# Terminal 3: Start IFCER service
cp .env.moto .env  # Use moto configuration
uvicorn app.main:app --reload

# Terminal 4: Test
curl http://localhost:8000/api/v1/health
```

## Detailed Setup

### Step 1: Install Dependencies

```bash
# Install testing dependencies
pip install -r requirements-test.txt

# This installs:
# - moto[server,s3,dynamodb] - AWS mocking
# - Flask - For mock InfoCert API
# - requests - For HTTP testing
```

### Step 2: Generate Test Certificates

```bash
# Generate self-signed certificates for mTLS
bash scripts/generate_test_certs.sh
```

This creates certificates in `test_certs/`:
- `client_cert.pem` / `client_key.pem` - For IFCER service
- `server_cert.pem` / `server_key.pem` - For mock InfoCert API
- `ca_bundle.pem` - Certificate Authority

### Step 3: Start Moto Server

```bash
# Terminal 1
python tests/run_moto_server.py
```

You should see:
```
======================================================================
  Moto Server - Mock AWS Services
  (S3 + DynamoDB)
======================================================================

Starting moto server...

Configuration:
  Host: 0.0.0.0
  Port: 5000
  Services: S3, DynamoDB

Endpoint URL: http://localhost:5000

AWS CLI Configuration:
  export AWS_ENDPOINT_URL=http://localhost:5000
  export AWS_ACCESS_KEY_ID=test
  export AWS_SECRET_ACCESS_KEY=test
  export AWS_REGION=eu-south-1
```

**Moto is now running** and emulating AWS S3 and DynamoDB on `http://localhost:5000`!

### Step 4: Create AWS Resources in Moto

```bash
# Terminal 2
python tests/setup_moto_resources.py
```

This script:
- Creates S3 bucket (`ifcer-test-bucket`)
- Creates DynamoDB table (`ifcer-certifications-test`)
- Uploads 4 sample test files to S3
- Uploads test certificates to S3
- Verifies everything is set up correctly

Output:
```
======================================================================
  Moto AWS Resources Setup
======================================================================

[S3] Creating bucket: ifcer-test-bucket
  ✓ Created bucket: ifcer-test-bucket

[DynamoDB] Creating table: ifcer-certifications-test
  ✓ Created table: ifcer-certifications-test

[FILES] Creating test files
  ✓ trade_declaration_001.xml
  ✓ invoice_12345.json
  ✓ document_5678.txt
  ✓ transactions.csv

[S3] Uploading test files to: ifcer-test-bucket
  ✓ incoming/trade_declaration_001.xml
  ✓ incoming/invoice_12345.json
  ✓ incoming/document_5678.txt
  ✓ incoming/transactions.csv

[S3] Uploading test certificates to: ifcer-test-bucket
  ✓ certs/client_cert.pem
  ✓ certs/client_key.pem
  ✓ certs/ca_bundle.pem

[VERIFY] Checking resources
  ✓ S3 bucket: ifcer-test-bucket
  ✓ Files in incoming/: 4
  ✓ DynamoDB table: ifcer-certifications-test (ACTIVE)
```

### Step 5: Start Mock InfoCert API

```bash
# Terminal 2 (same terminal after setup)
python tests/mock_infocert_api.py
```

Output:
```
=============================================================
  Mock InfoCert Sign API Server
  FOR TESTING ONLY
=============================================================

[MOCK API] Starting server...
[MOCK API] Host: 127.0.0.1
[MOCK API] Port: 8443
[MOCK API] Base URL: https://127.0.0.1:8443

Endpoints:
  GET  https://127.0.0.1:8443/health
  POST https://127.0.0.1:8443/sign/v2
```

### Step 6: Configure IFCER Service for Moto

```bash
# Use the moto configuration
cp .env.moto .env

# Or manually create .env with these settings:
cat > .env << 'EOF'
# Moto Configuration
APP_NAME=IFCER Batch Service (MOTO TEST)
LOG_LEVEL=DEBUG

# Point to Moto server
AWS_ENDPOINT_URL=http://localhost:5000
AWS_ACCESS_KEY_ID=test
AWS_SECRET_ACCESS_KEY=test
AWS_REGION=eu-south-1

# S3 and DynamoDB
S3_BUCKET_NAME=ifcer-test-bucket
DYNAMODB_TABLE_NAME=ifcer-certifications-test

# Mock InfoCert API
VENDOR_API_URL=https://127.0.0.1:8443
INFOCERT_CREDENTIAL_ID=test-credential-id
VENDOR_MTLS_CERT_S3_KEY=certs/client_cert.pem
VENDOR_MTLS_KEY_S3_KEY=certs/client_key.pem
VENDOR_MTLS_CA_S3_KEY=certs/ca_bundle.pem

# Processing
HASH_ALGORITHM=sha256
BATCH_SIZE=100
REQUEST_TIMEOUT=30
EOF
```

### Step 7: Start IFCER Service

```bash
# Terminal 3
uvicorn app.main:app --reload
```

You should see:
```
INFO:     Uvicorn running on http://127.0.0.1:8000
INFO:     Application startup complete.
S3 client initialized for bucket: ifcer-test-bucket in region: eu-south-1 | Endpoint: http://localhost:5000
DynamoDB service initialized for table: ifcer-certifications-test in region: eu-south-1 | Endpoint: http://localhost:5000
```

**Notice**: The services are using `http://localhost:5000` (moto) instead of real AWS!

## Testing the Complete Workflow

### Health Check

```bash
curl http://localhost:8000/api/v1/health
```

Response:
```json
{
  "status": "healthy",
  "timestamp": "2025-11-10T10:00:00.000000Z",
  "version": "1.0.0"
}
```

### Process Batch of Files

```bash
curl -X POST http://localhost:8000/api/v1/process \
  -H 'Content-Type: application/json' \
  -d '{
    "start_date": "2025-11-01T00:00:00Z",
    "end_date": "2025-11-30T23:59:59Z",
    "prefix": "incoming/"
  }'
```

Response:
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

### Recertify Single File

```bash
curl -X POST http://localhost:8000/api/v1/recertify \
  -H 'Content-Type: application/json' \
  -d '{
    "file_key": "incoming/invoice_12345.json"
  }'
```

## Verifying Results in Moto

### Using AWS CLI with Moto

Configure AWS CLI to use moto:

```bash
export AWS_ENDPOINT_URL=http://localhost:5000
export AWS_ACCESS_KEY_ID=test
export AWS_SECRET_ACCESS_KEY=test
export AWS_REGION=eu-south-1
```

#### List S3 Files

```bash
# List incoming files
aws s3 ls s3://ifcer-test-bucket/incoming/

# List signed P7M files
aws s3 ls s3://ifcer-test-bucket/signed/

# Download a file
aws s3 cp s3://ifcer-test-bucket/signed/trade_declaration_001.xml.p7m ./
```

#### Query DynamoDB

```bash
# Scan all items
aws dynamodb scan --table-name ifcer-certifications-test

# Get specific file
aws dynamodb query \
  --table-name ifcer-certifications-test \
  --key-condition-expression "file_key = :fk" \
  --expression-attribute-values '{":fk":{"S":"incoming/invoice_12345.json"}}'
```

### Using Python boto3 with Moto

```python
import boto3

# Configure boto3 for moto
s3 = boto3.client(
    's3',
    endpoint_url='http://localhost:5000',
    aws_access_key_id='test',
    aws_secret_access_key='test',
    region_name='eu-south-1'
)

# List buckets
print(s3.list_buckets())

# List objects
print(s3.list_objects_v2(Bucket='ifcer-test-bucket', Prefix='incoming/'))
```

## Advantages of Moto

✅ **No Docker required** - Pure Python solution
✅ **Fast startup** - Instant, no container overhead
✅ **Lightweight** - Minimal resource usage
✅ **Persistent** - Data persists while server runs
✅ **Free** - Open source, no AWS costs
✅ **Realistic** - Mimics real AWS API behavior
✅ **Offline** - Works without internet

## Monitoring and Logs

### IFCER Service Logs

When using moto, you'll see endpoint information in the logs:

```
[INFO] S3 client initialized for bucket: ifcer-test-bucket in region: eu-south-1 | Endpoint: http://localhost:5000
[INFO] Using custom AWS endpoint: http://localhost:5000
[INFO] DynamoDB service initialized for table: ifcer-certifications-test in region: eu-south-1 | Endpoint: http://localhost:5000
```

### Moto Server Logs

Moto logs all API requests:

```
127.0.0.1 - - [10/Nov/2025 10:00:00] "GET / HTTP/1.1" 200 -
127.0.0.1 - - [10/Nov/2025 10:00:01] "PUT /ifcer-test-bucket HTTP/1.1" 200 -
127.0.0.1 - - [10/Nov/2025 10:00:02] "PUT /ifcer-test-bucket/incoming/test.xml HTTP/1.1" 200 -
```

### Mock InfoCert API Logs

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

## Troubleshooting

### Moto Server Not Starting

**Error**: `Address already in use`

**Solution**: Port 5000 is already in use. Kill the process or use a different port:

```bash
# Kill process on port 5000
lsof -ti:5000 | xargs kill -9

# Or edit run_moto_server.py to use a different port
```

### Cannot Connect to Moto

**Error**: `Connection refused`

**Check**:
1. Moto server is running: `curl http://localhost:5000`
2. `.env` has correct `AWS_ENDPOINT_URL=http://localhost:5000`
3. Firewall allows port 5000

### No Files Found

**Error**: `Found 0 files to process`

**Solution**: Run the setup script:

```bash
python tests/setup_moto_resources.py
```

### DynamoDB Table Not Found

**Error**: `Cannot do operations on a non-existent table`

**Solution**: Create the table:

```bash
python tests/setup_moto_resources.py
```

## Data Persistence

### Current Behavior

Moto data exists **only while the server is running**. When you stop moto, all data is lost.

### Making Data Persistent (Optional)

To persist data between runs, modify `run_moto_server.py`:

```python
# Add environment variable before starting server
import os
os.environ['MOTO_S3_CUSTOM_ENDPOINTS'] = 'http://localhost:5000'

# Data will be persisted to disk (feature in development)
```

Or use snapshot/restore scripts to save/load state.

## Cleanup

```bash
# Stop all services (Ctrl+C in each terminal)

# Remove test files
rm -rf tests/test_files

# Moto data is automatically cleared when server stops
```

## Comparison: Moto vs Real AWS vs LocalStack

| Feature | Moto | Real AWS | LocalStack |
|---------|------|----------|------------|
| **Setup** | `pip install` | AWS account | Docker required |
| **Cost** | Free | Pay per use | Free (limited) |
| **Speed** | Fast | Network latency | Medium |
| **Docker** | No | No | Yes |
| **Offline** | Yes | No | Yes |
| **Realistic** | Good | Perfect | Excellent |
| **Persistence** | Memory only | Permanent | Configurable |

## Next Steps

- **Production deployment**: Switch to real AWS (remove `AWS_ENDPOINT_URL`)
- **CI/CD**: Use moto in automated tests
- **Integration tests**: Write pytest tests using moto decorators

## Additional Resources

- [Moto Documentation](https://docs.getmoto.org/)
- [AWS CLI with Moto](https://docs.getmoto.org/en/latest/docs/getting_started.html#example-using-the-standalone-server-mode)
- [Pytest with Moto](https://docs.getmoto.org/en/latest/docs/getting_started.html#example-on-usage)
