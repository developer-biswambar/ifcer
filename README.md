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

### Health Check

```bash
GET /health
```

Checks connectivity to S3 and vendor API.

### Process Files

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

## mTLS Certificate Setup

The vendor API requires mutual TLS (mTLS) authentication. You need three files:

1. **Client Certificate** (`client_cert.pem`): Your certificate for authentication
2. **Client Private Key** (`client_key.pem`): Private key for your certificate
3. **CA Bundle** (`ca_bundle.pem`): Certificate authority bundle to verify vendor's certificate

Mount these files into the Docker container at `/certs/` or specify custom paths via environment variables.

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
