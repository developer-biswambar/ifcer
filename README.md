# IFCER - Italian File Certification and Registration Batch Service

A Python-based batch service for processing files from AWS S3, computing cryptographic hashes, and obtaining qualified digital signatures via **InfoCert's API** using a **manifest-based approach** with mTLS authentication. Creates P7M (CAdES) signed manifests for Italian register submission, fully compliant with eIDAS and AgID regulations.

## Overview

This service is designed to run as an AWS ECS task triggered by EventBridge. It implements a **manifest-based signing approach** where:

1. Fetches files from an S3 bucket based on a date range (upload date)
2. Computes SHA-256 hash for each file
3. Creates a manifest JSON containing file metadata and hash
4. Sends the manifest to InfoCert's Sign API using mTLS authentication
5. Receives CAdES-BES digital signatures (P7M of the manifest) from InfoCert
6. Stores original files + signed manifest P7M in S3 for Italian register submission
7. Maintains certification metadata in DynamoDB for audit trail

**Key Point**: The original file stays unchanged. The P7M contains a **signed manifest** that proves the file's integrity through its hash.

## Architecture

```
┌─────────────┐      ┌──────────────┐      ┌─────────────┐
│   AWS ECS   │─────▶│ IFCER Service│◀────▶│   AWS S3    │
│ EventBridge │      │   (FastAPI)  │      │   Bucket    │
└─────────────┘      └──────┬───────┘      └─────────────┘
                            │                      │
                            │ mTLS                 │
                            ▼                      ▼
                     ┌──────────────┐      ┌─────────────┐
                     │  InfoCert    │      │  DynamoDB   │
                     │  Sign API    │      │ (Metadata)  │
                     └──────────────┘      └─────────────┘
```

## Project Structure

```
ifcer/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI application entry point
│   ├── config.py            # Configuration management
│   ├── models/
│   │   ├── __init__.py
│   │   └── schemas.py       # Pydantic models
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── processing.py    # Processing endpoints (health, process, recertify)
│   │   └── files.py         # File query endpoints (file-details, files-list)
│   ├── services/
│   │   ├── __init__.py
│   │   ├── s3_service.py    # S3 operations
│   │   ├── hash_service.py  # File hashing
│   │   └── signature_service.py  # Vendor API integration (mTLS)
│   └── utils/
│       ├── __init__.py
│       └── logger.py        # Logging configuration
├── requirements.txt         # Python dependencies
├── Dockerfile              # Container definition
├── .env.example            # Environment variables template
└── README.md
```

## Requirements

- Python 3.11+
- Docker (for containerization)
- AWS Account with S3 and DynamoDB access
- Vendor mTLS certificates stored in S3 (cert, key, CA bundle)

## Configuration

All configuration is managed through environment variables. See `.env.example` for available options.

### Required Environment Variables

```bash
# AWS Configuration
AWS_REGION=eu-south-1
S3_BUCKET_NAME=your-bucket-name
DYNAMODB_TABLE_NAME=ifcer-certifications

# InfoCert API Configuration (mTLS)
# InfoCert's Manifest-Based Hash Signature API
# Certificates are stored in S3 and loaded during application startup
VENDOR_API_URL=https://sign.infocert.it/api/v1
INFOCERT_CREDENTIAL_ID=your-infocert-credential-id
VENDOR_MTLS_CERT_S3_KEY=certs/client_cert.pem
VENDOR_MTLS_KEY_S3_KEY=certs/client_key.pem
VENDOR_MTLS_CA_S3_KEY=certs/ca_bundle.pem
```

### Optional Environment Variables

```bash
# Application Settings
APP_NAME=IFCER Batch Service
LOG_LEVEL=INFO

# DynamoDB TTL (auto-delete old records)
DYNAMODB_TTL_DAYS=365

# Processing Settings
HASH_ALGORITHM=sha256
BATCH_SIZE=100
REQUEST_TIMEOUT=30
```

## Local Development

### Setup

1. Clone the repository:
```bash
git clone <repository-url>
cd ifcer
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Configure environment variables:
```bash
cp .env.example .env
# Edit .env with your configuration
```

5. Run the application:
```bash
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The API will be available at `http://localhost:8000`

### API Documentation

Once running, access the interactive API documentation:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Docker Deployment

### Build the Docker image

```bash
docker build -t ifcer-service:latest .
```

### Run the container

```bash
docker run -d \
  --name ifcer-service \
  -p 8000:8000 \
  -e AWS_REGION=eu-south-1 \
  -e S3_BUCKET_NAME=your-bucket-name \
  -e DYNAMODB_TABLE_NAME=ifcer-certifications \
  -e VENDOR_API_URL=https://sign.infocert.it/api/v1 \
  -e VENDOR_MTLS_CERT_S3_KEY=certs/client_cert.pem \
  -e VENDOR_MTLS_KEY_S3_KEY=certs/client_key.pem \
  -e VENDOR_MTLS_CA_S3_KEY=certs/ca_bundle.pem \
  ifcer-service:latest
```

**Note:** When running locally, ensure your AWS credentials are available via:
- AWS credentials file (`~/.aws/credentials`)
- Environment variables (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`)
- IAM role (when running in AWS)

### Using Docker Compose

Create a `docker-compose.yml`:

```yaml
version: '3.8'

services:
  ifcer:
    build: .
    ports:
      - "8000:8000"
    env_file:
      - .env
    environment:
      - AWS_REGION=${AWS_REGION:-eu-south-1}
      - S3_BUCKET_NAME=${S3_BUCKET_NAME}
      - DYNAMODB_TABLE_NAME=${DYNAMODB_TABLE_NAME:-ifcer-certifications}
      - VENDOR_API_URL=${VENDOR_API_URL:-https://sign.infocert.it/api/v1}
      - VENDOR_MTLS_CERT_S3_KEY=${VENDOR_MTLS_CERT_S3_KEY:-certs/client_cert.pem}
      - VENDOR_MTLS_KEY_S3_KEY=${VENDOR_MTLS_KEY_S3_KEY:-certs/client_key.pem}
      - VENDOR_MTLS_CA_S3_KEY=${VENDOR_MTLS_CA_S3_KEY:-certs/ca_bundle.pem}
    restart: unless-stopped
```

Run with:
```bash
docker-compose up -d
```

## API Endpoints

The API is organized into two main groups:
- **Processing**: Endpoints for file certification and processing
- **Files**: Endpoints for querying file status and certification information

### Health Check

```bash
GET /health
```

Checks connectivity to S3 and vendor API.

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2025-01-15T10:00:00Z",
  "version": "0.1.0"
}
```

---

## Processing Endpoints

### Recertify Single File

```bash
POST /recertify
Content-Type: application/json

{
  "file_key": "documents/2025/invoice_001.pdf"
}
```

Recertifies a single file from S3 by its key. Useful for:
- Recertifying files that previously failed
- Re-signing files that need updated timestamps
- Processing individual files on demand

**Response:**
```json
{
  "file_key": "documents/2025/invoice_001.pdf",
  "status": "completed",
  "file_hash": "a3b2c1d4e5f6...",
  "signature": "sig_xyz123...",
  "timestamp": "2025-01-15T10:30:00Z",
  "p7m_file_key": "signed/invoice_001.pdf.p7m",
  "error_message": null
}
```

**Note:** Signed P7M files are stored in the `signed/` folder in S3.

### Batch Process Files

```bash
POST /process
Content-Type: application/json

{
  "start_date": "2025-01-01T00:00:00Z",
  "end_date": "2025-01-31T23:59:59Z",
  "prefix": "documents/"
}
```

Processes all files in the S3 bucket uploaded between the specified dates.

**Response:**
```json
{
  "total_files": 100,
  "processed_files": 100,
  "successful_files": 98,
  "failed_files": 2,
  "results": [...],
  "processing_start": "2025-01-15T10:00:00Z",
  "processing_end": "2025-01-15T10:05:30Z",
  "duration_seconds": 330.5
}
```

---

## Files Query Endpoints

### Get File Details

```bash
POST /file-details
Content-Type: application/json

{
  "filename": "invoice_001.pdf"
}
```

Search for files by name and get their certification status. Returns all files matching the given filename.

**Response:**
```json
{
  "found": true,
  "total_matches": 2,
  "files": [
    {
      "original_file_key": "documents/2025/invoice_001.pdf",
      "original_file_size": 245632,
      "original_upload_date": "2025-01-10T08:30:00Z",
      "is_signed": true,
      "signed_file_key": "signed/invoice_001.pdf.p7m",
      "signed_file_size": 248192,
      "signing_timestamp": "2025-01-10T09:00:00Z",
      "file_hash": null,
      "signature": null
    }
  ]
}
```

### Get Files List with Signing Info (Paginated)

```bash
POST /files-list
Content-Type: application/json

{
  "start_date": "2025-01-01T00:00:00Z",
  "end_date": "2025-01-31T23:59:59Z",
  "prefix": "documents/",
  "signed_only": false,
  "page": 1,
  "page_size": 50
}
```

Get files in a date range with their certification status. Supports pagination for large result sets.

**Useful for:**
- Auditing which files have been certified
- Finding files that need recertification
- Generating compliance reports
- Processing large datasets efficiently

**Response:**
```json
{
  "total_files": 150,
  "signed_files": 145,
  "unsigned_files": 5,
  "page": 1,
  "page_size": 50,
  "total_pages": 3,
  "has_next": true,
  "has_previous": false,
  "files": [
    {
      "original_file_key": "documents/2025/invoice_001.pdf",
      "original_file_size": 245632,
      "original_upload_date": "2025-01-10T08:30:00Z",
      "is_signed": true,
      "signed_file_key": "signed/invoice_001.pdf.p7m",
      "signed_file_size": 248192,
      "signing_timestamp": "2025-01-10T09:00:00Z",
      "file_hash": null,
      "signature": null
    },
    {
      "original_file_key": "documents/2025/invoice_002.pdf",
      "original_file_size": 198432,
      "original_upload_date": "2025-01-11T14:20:00Z",
      "is_signed": false,
      "signed_file_key": null,
      "signed_file_size": null,
      "signing_timestamp": null,
      "file_hash": null,
      "signature": null
    }
  ]
}
```

**Request Parameters:**
- `start_date` (required): Start date for filtering files
- `end_date` (required): End date for filtering files
- `prefix` (optional): S3 prefix to filter files (e.g., "documents/")
- `signed_only` (optional, default: false): Set to `true` to only return signed files
- `page` (optional, default: 1): Page number (starting from 1)
- `page_size` (optional, default: 50, max: 1000): Number of items per page

**Response Fields:**
- `total_files`: Total count of files matching criteria (across all pages)
- `signed_files`: Total count of signed files (across all pages)
- `unsigned_files`: Total count of unsigned files (across all pages)
- `page`: Current page number
- `page_size`: Items per page
- `total_pages`: Total number of pages available
- `has_next`: Whether there is a next page available
- `has_previous`: Whether there is a previous page available
- `files`: Array of files for the current page

**Pagination Examples:**

Get first page (50 items):
```json
{
  "start_date": "2025-01-01T00:00:00Z",
  "end_date": "2025-01-31T23:59:59Z",
  "page": 1,
  "page_size": 50
}
```

Get second page:
```json
{
  "start_date": "2025-01-01T00:00:00Z",
  "end_date": "2025-01-31T23:59:59Z",
  "page": 2,
  "page_size": 50
}
```

Get all signed files with smaller page size:
```json
{
  "start_date": "2025-01-01T00:00:00Z",
  "end_date": "2025-01-31T23:59:59Z",
  "signed_only": true,
  "page": 1,
  "page_size": 100
}
```

---

## File Storage Structure

The service maintains a clean separation between original files and signed files in S3:

### Original Files
- Location: Anywhere in your S3 bucket (e.g., `documents/2025/invoice_001.pdf`)
- These files remain **unchanged** after processing
- Used as source files for certification

### Signed Files (P7M)
- Location: `signed/` folder in the same S3 bucket
- Naming: `signed/<original_filename>.p7m`
- Example: `signed/invoice_001.pdf.p7m`
- Content-Type: `application/pkcs7-mime`

### Example Structure After Processing

```
s3://your-bucket/
├── documents/
│   ├── 2025/
│   │   ├── invoice_001.pdf          ← Original file
│   │   ├── invoice_002.pdf          ← Original file
│   │   └── contract_001.pdf         ← Original file
│   └── archive/
│       └── old_doc.pdf              ← Original file
└── signed/
    ├── invoice_001.pdf.p7m          ← Signed/certified file
    ├── invoice_002.pdf.p7m          ← Signed/certified file
    ├── contract_001.pdf.p7m         ← Signed/certified file
    └── old_doc.pdf.p7m              ← Signed/certified file
```

This structure makes it easy to:
- Identify which files have been certified (check if corresponding file exists in `signed/`)
- Keep original files for reference
- Submit P7M files to the Italian register

---

## mTLS Certificate Setup

The vendor API requires mutual TLS (mTLS) authentication. The service loads certificates from S3 during startup.

### Required Certificates

1. **Client Certificate** (`client_cert.pem`): Your certificate for authentication
2. **Client Private Key** (`client_key.pem`): Private key for your certificate
3. **CA Bundle** (`ca_bundle.pem`): Certificate authority bundle to verify vendor's certificate

### Uploading Certificates to S3

Upload your mTLS certificates to the `certs/` folder in your S3 bucket:

```bash
# Upload client certificate
aws s3 cp client_cert.pem s3://your-bucket-name/certs/client_cert.pem

# Upload client private key
aws s3 cp client_key.pem s3://your-bucket-name/certs/client_key.pem

# Upload CA bundle
aws s3 cp ca_bundle.pem s3://your-bucket-name/certs/ca_bundle.pem
```

### Certificate Loading Process

When the application starts:
1. Downloads certificates from S3 using the configured S3 keys
2. Writes them to temporary files with secure permissions (read-only, 0o400)
3. Uses these temporary files for mTLS authentication with the vendor API

### S3 Bucket Security

Ensure your S3 bucket has appropriate security:

```bash
# Set bucket policy to prevent public access
aws s3api put-public-access-block \
    --bucket your-bucket-name \
    --public-access-block-configuration \
        "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"

# Encrypt certificates at rest (optional)
aws s3api put-bucket-encryption \
    --bucket your-bucket-name \
    --server-side-encryption-configuration \
        '{"Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}]}'
```

### IAM Permissions for Certificates

The ECS task role needs S3 read permissions for the certificates:

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
        "arn:aws:s3:::your-bucket-name/certs/*"
      ]
    }
  ]
}
```

### Custom Certificate Paths

To use different S3 keys for your certificates, set these environment variables:

```bash
VENDOR_MTLS_CERT_S3_KEY=custom/path/client_cert.pem
VENDOR_MTLS_KEY_S3_KEY=custom/path/client_key.pem
VENDOR_MTLS_CA_S3_KEY=custom/path/ca_bundle.pem
```

---

## DynamoDB Setup

The service uses DynamoDB to store certification metadata including file hashes, digital signatures, timestamps, and processing status.

### Table Schema

Create a DynamoDB table with the following configuration:

**Table Name:** `ifcer-certifications` (or custom name via `DYNAMODB_TABLE_NAME` env var)

**Primary Key:**
- **Partition Key:** `file_key` (String) - The S3 key of the original file
- **Sort Key:** `processing_timestamp` (String) - ISO8601 timestamp of when the file was processed

**Global Secondary Indexes (GSI):**

1. **filename-index** - For searching by filename
   - Partition Key: `filename` (String)
   - Sort Key: `processing_timestamp` (String)
   - Projection: ALL

2. **date-index** - For querying by date range
   - Partition Key: `date_partition` (String) - Format: YYYY-MM
   - Sort Key: `processing_timestamp` (String)
   - Projection: ALL

**Optional: TTL Configuration**
- Attribute: `ttl` (Number)
- Enable TTL to automatically delete old records (configure via `DYNAMODB_TTL_DAYS` env var)

### Attributes Stored

```json
{
  "file_key": "documents/2025/invoice_001.pdf",
  "processing_timestamp": "2025-01-15T10:30:00.000Z",
  "filename": "invoice_001.pdf",
  "date_partition": "2025-01",
  "file_hash": "a3b2c1d4e5f6...",
  "hash_algorithm": "sha256",
  "digital_signature": "sig_xyz123...",
  "vendor_timestamp": "2025-01-15T10:30:05.000Z",
  "signed_file_key": "signed/invoice_001.pdf.p7m",
  "file_size": 245632,
  "signed_file_size": 248192,
  "status": "completed",
  "ttl": 1735689000
}
```

### Creating the Table (AWS CLI)

```bash
# Create the main table
aws dynamodb create-table \
    --table-name ifcer-certifications \
    --attribute-definitions \
        AttributeName=file_key,AttributeType=S \
        AttributeName=processing_timestamp,AttributeType=S \
        AttributeName=filename,AttributeType=S \
        AttributeName=date_partition,AttributeType=S \
    --key-schema \
        AttributeName=file_key,KeyType=HASH \
        AttributeName=processing_timestamp,KeyType=RANGE \
    --billing-mode PAY_PER_REQUEST \
    --global-secondary-indexes \
        '[
            {
                "IndexName": "filename-index",
                "KeySchema": [
                    {"AttributeName": "filename", "KeyType": "HASH"},
                    {"AttributeName": "processing_timestamp", "KeyType": "RANGE"}
                ],
                "Projection": {"ProjectionType": "ALL"}
            },
            {
                "IndexName": "date-index",
                "KeySchema": [
                    {"AttributeName": "date_partition", "KeyType": "HASH"},
                    {"AttributeName": "processing_timestamp", "KeyType": "RANGE"}
                ],
                "Projection": {"ProjectionType": "ALL"}
            }
        ]' \
    --region eu-south-1

# Optional: Enable TTL for automatic record deletion
aws dynamodb update-time-to-live \
    --table-name ifcer-certifications \
    --time-to-live-specification \
        "Enabled=true,AttributeName=ttl" \
    --region eu-south-1
```

### IAM Permissions Required

The ECS task role needs these permissions:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject"
      ],
      "Resource": [
        "arn:aws:s3:::your-bucket-name/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::your-bucket-name"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "dynamodb:PutItem",
        "dynamodb:GetItem",
        "dynamodb:Query",
        "dynamodb:BatchGetItem",
        "dynamodb:DescribeTable"
      ],
      "Resource": [
        "arn:aws:dynamodb:eu-south-1:ACCOUNT_ID:table/ifcer-certifications",
        "arn:aws:dynamodb:eu-south-1:ACCOUNT_ID:table/ifcer-certifications/index/*"
      ]
    }
  ]
}
```

---

## AWS ECS Deployment

### Task Definition Example

```json
{
  "family": "ifcer-service",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "512",
  "memory": "1024",
  "executionRoleArn": "arn:aws:iam::ACCOUNT_ID:role/ecsTaskExecutionRole",
  "taskRoleArn": "arn:aws:iam::ACCOUNT_ID:role/ifcer-task-role",
  "containerDefinitions": [
    {
      "name": "ifcer-container",
      "image": "ACCOUNT_ID.dkr.ecr.REGION.amazonaws.com/ifcer-service:latest",
      "portMappings": [
        {
          "containerPort": 8000,
          "protocol": "tcp"
        }
      ],
      "environment": [
        {"name": "AWS_REGION", "value": "eu-south-1"},
        {"name": "S3_BUCKET_NAME", "value": "your-bucket-name"},
        {"name": "DYNAMODB_TABLE_NAME", "value": "ifcer-certifications"},
        {"name": "VENDOR_API_URL", "value": "https://sign.infocert.it/api/v1"},
        {"name": "VENDOR_MTLS_CERT_S3_KEY", "value": "certs/client_cert.pem"},
        {"name": "VENDOR_MTLS_KEY_S3_KEY", "value": "certs/client_key.pem"},
        {"name": "VENDOR_MTLS_CA_S3_KEY", "value": "certs/ca_bundle.pem"}
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/ifcer-service",
          "awslogs-region": "eu-south-1",
          "awslogs-stream-prefix": "ecs"
        }
      }
    }
  ]
}
```

### EventBridge Rule Example

```json
{
  "Name": "ifcer-daily-trigger",
  "ScheduleExpression": "cron(0 2 * * ? *)",
  "State": "ENABLED",
  "Targets": [
    {
      "Arn": "arn:aws:ecs:REGION:ACCOUNT_ID:cluster/your-cluster",
      "RoleArn": "arn:aws:iam::ACCOUNT_ID:role/ecsEventsRole",
      "EcsParameters": {
        "TaskDefinitionArn": "arn:aws:ecs:REGION:ACCOUNT_ID:task-definition/ifcer-service:1",
        "TaskCount": 1,
        "LaunchType": "FARGATE",
        "NetworkConfiguration": {
          "awsvpcConfiguration": {
            "Subnets": ["subnet-xxx"],
            "SecurityGroups": ["sg-xxx"],
            "AssignPublicIp": "ENABLED"
          }
        }
      }
    }
  ]
}
```

## Error Handling

The service includes comprehensive error handling and logging:

- All operations are logged with appropriate log levels
- Exceptions are caught and logged with full context
- Failed file processing is tracked in the response
- Individual file failures don't stop batch processing

## Security Considerations

1. **IAM Roles**: Use IAM roles for ECS tasks instead of hardcoded credentials (no AWS keys in environment)
2. **Certificate Security**: Store mTLS certificates in S3 with encryption at rest and restricted bucket access
3. **Temporary Files**: Certificates are stored in temporary files with read-only permissions (0o400) during runtime
4. **Network Security**: Use private subnets with NAT gateway for ECS tasks
5. **TLS**: All communication with vendor API uses mTLS authentication
6. **Non-root Container**: Docker container runs as non-root user
7. **S3 Bucket Policy**: Ensure S3 bucket blocks public access and uses encryption

## Monitoring and Logging

- All logs are output to stdout in JSON format
- Configure CloudWatch Logs for ECS tasks
- Health check endpoint for monitoring
- Processing metrics included in API responses

## TODO / Future Enhancements

- [ ] Implement actual P7M file creation logic (based on vendor specifications)
- [ ] Add retry logic with exponential backoff for failed operations
- [ ] Implement batch processing with configurable batch sizes
- [ ] Add metrics and monitoring (Prometheus, CloudWatch)
- [ ] Add integration tests
- [ ] Support for parallel processing of files
- [ ] Dead letter queue for failed files
- [ ] Notification service for processing completion

## InfoCert API Integration (Manifest-Based Approach)

This service implements a **manifest-based approach** using InfoCert's Sign API for obtaining qualified digital signatures compliant with Italian eIDAS and AgID regulations.

### Why Manifest-Based?

Since only the **hash** of the file is sent to InfoCert (not the full file), we cannot create an enveloping P7M that contains the original document. Instead:

- **Original file** stays unchanged in S3
- **Manifest file** (JSON) is created containing the file's hash and metadata
- **InfoCert signs the manifest** and returns a P7M of the signed manifest
- The P7M proves the integrity of the original file through the hash in the manifest

This approach is **tamper-evident** and **legally compliant** for Italian digital signatures.

### API Workflow

1. **Hash Computation**: Compute SHA-256 hash of the original document locally
   ```
   Hash: f2a7c53b8c9b80f47993e2c1bb0af2d7b73f92df3b7f1234567890abcdef
   ```

2. **Manifest Creation**: Create a JSON manifest file:
   ```json
   {
     "fileName": "trade_declaration.xml",
     "algorithm": "SHA256",
     "hash": "f2a7c53b8c9b80f47993e2c1bb0af2d7b73f92df3b7f1234567890abcdef",
     "timestamp": "2025-11-09T10:25:00Z"
   }
   ```

3. **Base64 Encoding**: Encode the manifest to Base64

4. **API Request**: Send manifest to InfoCert Sign API (`/sign/v2` endpoint):
   ```json
   {
     "credentialID": "your-credential-id",
     "signRequest": {
       "signFormat": "CAdES",
       "signatureLevel": "CAdES_BASELINE_B",
       "inputDocuments": [{
         "contentType": "BASE64",
         "content": "<base64-encoded-manifest>"
       }]
     }
   }
   ```

5. **API Response**: InfoCert returns:
   ```json
   {
     "signatureValue": "<base64-signature-bytes>",
     "signingCertificate": "<base64-cert-der>",
     "signingTime": "2025-11-09T10:25:05Z"
   }
   ```

6. **P7M Creation**: We create the P7M file ourselves using:
   - The manifest content
   - The signature from InfoCert
   - The signing certificate from InfoCert
   - Using `asn1crypto` library to build CAdES-BES/PKCS#7 structure

7. **P7M Storage**: Store the created P7M file in S3 `signed/` folder

### File Storage Structure

After processing, you have two files:

```
s3://your-bucket/
├── documents/
│   └── trade_declaration.xml          ← Original file (unchanged)
└── signed/
    └── trade_declaration.xml.p7m      ← Signed manifest (P7M)
```

The `.p7m` file contains the **signed manifest**, which includes:
- Original file name
- SHA-256 hash of the original file
- Hash algorithm used
- Timestamp of manifest creation

### P7M File Creation

Since InfoCert returns the **signature** and **certificate** (not a complete P7M), we create the P7M file ourselves:

**Libraries Used:**
- `asn1crypto`: For building PKCS#7/CMS structures
- `cryptography`: For certificate parsing

**P7M Structure (CAdES-BES):**
```
ContentInfo (PKCS#7)
└── SignedData
    ├── version: v1
    ├── digestAlgorithms: [SHA-256]
    ├── encapContentInfo:
    │   ├── contentType: data
    │   └── content: <manifest-json>
    ├── certificates: [InfoCert signer certificate]
    └── signerInfos:
        └── SignerInfo
            ├── version: v1
            ├── sid: IssuerAndSerialNumber
            ├── digestAlgorithm: SHA-256
            ├── signatureAlgorithm: sha256WithRSAEncryption
            └── signature: <signature-from-infocert>
```

This creates a standards-compliant CAdES-BES structure that:
- Contains the manifest as signed content
- Includes the digital signature from InfoCert's qualified certificate
- Embeds the signer's certificate for verification
- Is verifiable by any PKCS#7/CAdES validator

### Integrity Verification

To verify the file hasn't been tampered with:

1. Extract the hash from the signed manifest P7M
2. Compute the hash of the original file
3. Compare both hashes - if they match, file is authentic

### Configuration

Required environment variables:

```bash
VENDOR_API_URL=https://sign.infocert.it/api/v1
INFOCERT_CREDENTIAL_ID=your-infocert-credential-id
VENDOR_MTLS_CERT_S3_KEY=certs/client_cert.pem
VENDOR_MTLS_KEY_S3_KEY=certs/client_key.pem
VENDOR_MTLS_CA_S3_KEY=certs/ca_bundle.pem
```

The service automatically:
- Loads mTLS certificates from S3 during startup
- Creates manifest JSON from file metadata and hash
- Handles base64 encoding/decoding
- Validates P7M file structure (PKCS#7 format)

### Supported Hash Algorithms

- **SHA-256** (recommended and default)
- **SHA-512**
- **SHA-384**
- **SHA-224**
- **SHA-1** (deprecated, avoid using)

### CAdES Format

InfoCert returns signatures in **CAdES-BES/CAdES-BASELINE-B** format, which:
- Complies with ETSI TS 119 122-1 specification
- Is the standard for Italian qualified digital signatures
- Creates P7M files (PKCS#7 enveloping signature of the manifest)
- Includes the signer's qualified certificate in the signature container
- Is legally binding under eIDAS regulations

### Compliance

This manifest-based approach is fully compliant with:
- **eIDAS** (Electronic Identification, Authentication and Trust Services)
- **AgID** (Agenzia per l'Italia Digitale) standards
- **ETSI TS 119 122-1** (CAdES baseline profile)
- Italian regulations for digital document preservation

### Documentation

For more details, refer to:
- InfoCert Developers Portal: https://developers.infocert.digital/
- Sign API Documentation: https://developers.infocert.digital/e-signature-and-e-sealing/sign-api/

## License

[Your License Here]

## Support

For issues and questions, please contact [your-contact-info].
