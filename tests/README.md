# Testing

This directory contains testing utilities for the IFCER batch service.

## Quick Start

```bash
# Complete automated setup
bash scripts/setup_local_testing.sh

# Or manual setup:

# 1. Generate certificates
bash scripts/generate_test_certs.sh

# 2. Create and upload test data
export S3_BUCKET_NAME=your-test-bucket
python tests/setup_test_data.py

# 3. Start mock API
python tests/mock_infocert_api.py

# 4. Run tests (in another terminal)
uvicorn app.main:app --reload
```

## Files

- **mock_infocert_api.py** - Mock InfoCert Sign API server with mTLS support
- **setup_test_data.py** - Creates and uploads sample files to S3
- **test_files/** - Generated sample files for testing

## Documentation

See [docs/LOCAL_TESTING.md](../docs/LOCAL_TESTING.md) for complete testing guide.

## Test Certificates

Test certificates are generated in `test_certs/` directory:
- Self-signed CA certificate
- Client certificate and key (for IFCER service)
- Server certificate and key (for mock API)

⚠️ **FOR TESTING ONLY** - Never use self-signed certificates in production!
