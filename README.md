# IFCER - Italian File Certification and Registration Batch Service

A Python-based batch service for processing files from AWS S3, computing cryptographic hashes, obtaining digital signatures with timestamps via vendor API using mTLS authentication, and creating P7M (PKCS#7) files for Italian register submission.

## Overview

This service is designed to run as an AWS ECS task triggered by EventBridge. It performs the following operations:

1. Fetches files from an S3 bucket based on a date range (upload date)
2. Computes SHA-256 hash for each file
3. Sends file hashes to a vendor API using mTLS authentication
4. Receives digital signatures and timestamps from the vendor
5. Creates P7M files for Italian register submission
6. Uploads P7M files back to S3

## Architecture

```
┌─────────────┐      ┌──────────────┐      ┌─────────────┐
│   AWS ECS   │─────▶│ IFCER Service│◀────▶│   AWS S3    │
│ EventBridge │      │   (FastAPI)  │      │   Bucket    │
└─────────────┘      └──────┬───────┘      └─────────────┘
                            │
                            │ mTLS
                            ▼
                     ┌──────────────┐
                     │  Vendor API  │
                     │  (Signature) │
                     └──────────────┘
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
- AWS Account with S3 access
- Vendor mTLS certificates (cert, key, CA bundle)

## Configuration

All configuration is managed through environment variables. See `.env.example` for available options.

### Required Environment Variables

```bash
# AWS Configuration
AWS_REGION=eu-south-1
S3_BUCKET_NAME=your-bucket-name

# Vendor API Configuration
VENDOR_API_URL=https://vendor-api.example.com
VENDOR_MTLS_CERT_PATH=/certs/client_cert.pem
VENDOR_MTLS_KEY_PATH=/certs/client_key.pem
VENDOR_MTLS_CA_PATH=/certs/ca_bundle.pem
```

### Optional Environment Variables

```bash
# Application Settings
APP_NAME=IFCER Batch Service
LOG_LEVEL=INFO

# AWS Credentials (if not using IAM role)
AWS_ACCESS_KEY_ID=your-access-key
AWS_SECRET_ACCESS_KEY=your-secret-key

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
  -v /path/to/certs:/certs:ro \
  -e AWS_REGION=eu-south-1 \
  -e S3_BUCKET_NAME=your-bucket-name \
  -e VENDOR_API_URL=https://vendor-api.example.com \
  -e VENDOR_MTLS_CERT_PATH=/certs/client_cert.pem \
  -e VENDOR_MTLS_KEY_PATH=/certs/client_key.pem \
  -e VENDOR_MTLS_CA_PATH=/certs/ca_bundle.pem \
  ifcer-service:latest
```

### Using Docker Compose

Create a `docker-compose.yml`:

```yaml
version: '3.8'

services:
  ifcer:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - ./certs:/certs:ro
    env_file:
      - .env
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

The vendor API requires mutual TLS (mTLS) authentication. You need three files:

1. **Client Certificate** (`client_cert.pem`): Your certificate for authentication
2. **Client Private Key** (`client_key.pem`): Private key for your certificate
3. **CA Bundle** (`ca_bundle.pem`): Certificate authority bundle to verify vendor's certificate

Mount these files into the Docker container at `/certs/` or specify custom paths via environment variables.

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

The ECS task role needs these DynamoDB permissions:

```json
{
  "Version": "2012-10-17",
  "Statement": [
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
        {"name": "VENDOR_API_URL", "value": "https://vendor-api.example.com"}
      ],
      "secrets": [
        {
          "name": "VENDOR_MTLS_CERT_PATH",
          "valueFrom": "arn:aws:secretsmanager:REGION:ACCOUNT_ID:secret:cert"
        }
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

1. **IAM Roles**: Use IAM roles for ECS tasks instead of hardcoded credentials
2. **Secrets Management**: Store mTLS certificates in AWS Secrets Manager
3. **Network Security**: Use private subnets with NAT gateway for ECS tasks
4. **TLS**: All communication with vendor API uses mTLS
5. **Non-root Container**: Docker container runs as non-root user

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

## Vendor API Integration

The vendor API endpoint structure is currently a placeholder. Update the following in `app/services/signature_service.py`:

1. API endpoint paths
2. Request payload format
3. Response parsing logic
4. P7M file creation (if not provided by vendor)

Refer to your vendor's API documentation for the exact specifications.

## License

[Your License Here]

## Support

For issues and questions, please contact [your-contact-info].
