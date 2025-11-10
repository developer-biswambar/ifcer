# Testing Quick Start

Complete local testing of IFCER without Docker using **Moto** for AWS mocking.

## Prerequisites

```bash
# Install testing dependencies
pip install -r requirements-test.txt

# Generate self-signed certificates
bash scripts/generate_test_certs.sh
```

## 3-Terminal Setup

### Terminal 1: Moto Server (Mock AWS)

```bash
python tests/run_moto_server.py
```

This starts a mock AWS server on `http://localhost:5000` that emulates:
- S3 (file storage)
- DynamoDB (metadata storage)

### Terminal 2: Setup & Mock InfoCert API

```bash
# Create AWS resources in moto (S3 bucket, DynamoDB table, test files)
python tests/setup_moto_resources.py

# Start mock InfoCert Sign API
python tests/mock_infocert_api.py
```

### Terminal 3: IFCER Service

```bash
# Use moto configuration
cp .env.moto .env

# Start the service
uvicorn app.main:app --reload
```

## Test It!

```bash
# Health check
curl http://localhost:8000/api/v1/health

# Process batch
curl -X POST http://localhost:8000/api/v1/process \
  -H 'Content-Type: application/json' \
  -d '{
    "start_date": "2025-11-01T00:00:00Z",
    "end_date": "2025-11-30T23:59:59Z",
    "prefix": "incoming/"
  }'
```

## What You Get

✅ **Complete workflow** - Download → Hash → Sign → P7M → Upload → DB
✅ **Mock AWS (Moto)** - S3 and DynamoDB without Docker
✅ **Mock InfoCert API** - HTTPS with mTLS
✅ **Sample files** - 4 test files ready to process
✅ **Self-signed certs** - Working mTLS authentication
✅ **Full logging** - Monitor every step

## Architecture

```
┌─────────────────────┐
│   Test Files (4)    │ ← XML, JSON, TXT, CSV
│   in S3 (moto)      │
└──────────┬──────────┘
           │
           ↓
┌─────────────────────┐
│   IFCER Service     │ ← Your application
│   (localhost:8000)  │
└──────────┬──────────┘
           │
           ├→ Moto (localhost:5000)        ← S3 + DynamoDB mock
           │
           └→ Mock InfoCert (localhost:8443) ← Sign API mock
```

## Detailed Documentation

- **Full Guide**: [docs/MOTO_TESTING.md](docs/MOTO_TESTING.md)
- **Self-Signed Certs**: [docs/LOCAL_TESTING.md](docs/LOCAL_TESTING.md)

## Switching to Real AWS

Just remove or comment out these lines in `.env`:

```bash
# Remove these for production:
# AWS_ENDPOINT_URL=http://localhost:5000
# AWS_ACCESS_KEY_ID=test
# AWS_SECRET_ACCESS_KEY=test
```

The services will automatically use IAM role credentials and real AWS!
