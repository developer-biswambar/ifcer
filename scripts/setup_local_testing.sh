#!/bin/bash

# Master setup script for local testing environment
# This script sets up everything needed to test IFCER locally

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo "=========================================="
echo "  IFCER Local Testing Setup"
echo "=========================================="
echo ""

# Check for required commands
echo "[1/6] Checking prerequisites..."

command -v python3 >/dev/null 2>&1 || { echo "  ✗ python3 is required but not installed."; exit 1; }
command -v openssl >/dev/null 2>&1 || { echo "  ✗ openssl is required but not installed."; exit 1; }
command -v aws >/dev/null 2>&1 || { echo "  ⚠️  aws CLI not found - you'll need to configure AWS manually"; }

PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
echo "  ✓ Python ${PYTHON_VERSION}"
echo "  ✓ OpenSSL $(openssl version | cut -d' ' -f2)"

# Check environment variables
if [ -z "$S3_BUCKET_NAME" ]; then
    echo ""
    echo "⚠️  S3_BUCKET_NAME environment variable not set"
    echo ""
    read -p "Enter your S3 bucket name: " S3_BUCKET_NAME
    export S3_BUCKET_NAME
fi

if [ -z "$AWS_REGION" ]; then
    export AWS_REGION="eu-south-1"
fi

echo ""
echo "Configuration:"
echo "  S3 Bucket: ${S3_BUCKET_NAME}"
echo "  AWS Region: ${AWS_REGION}"
echo ""

# Generate certificates
echo "[2/6] Generating self-signed certificates..."
if [ ! -d "${PROJECT_ROOT}/test_certs" ]; then
    bash "${SCRIPT_DIR}/generate_test_certs.sh"
else
    echo "  ℹ️  Certificates already exist in test_certs/"
    read -p "  Regenerate certificates? (y/N): " regenerate
    if [[ $regenerate =~ ^[Yy]$ ]]; then
        rm -rf "${PROJECT_ROOT}/test_certs"
        bash "${SCRIPT_DIR}/generate_test_certs.sh"
    else
        echo "  ✓ Using existing certificates"
    fi
fi

# Install Python dependencies
echo ""
echo "[3/6] Installing Python dependencies..."
cd "${PROJECT_ROOT}"

if [ ! -d "venv" ]; then
    echo "  Creating virtual environment..."
    python3 -m venv venv
fi

echo "  Activating virtual environment..."
source venv/bin/activate

echo "  Installing requirements..."
pip install -q --upgrade pip
pip install -q -r requirements.txt
pip install -q flask boto3

echo "  ✓ Dependencies installed"

# Create .env file
echo ""
echo "[4/6] Creating .env configuration..."

ENV_FILE="${PROJECT_ROOT}/.env"

if [ -f "$ENV_FILE" ]; then
    echo "  ℹ️  .env file already exists"
    read -p "  Overwrite with test configuration? (y/N): " overwrite
    if [[ ! $overwrite =~ ^[Yy]$ ]]; then
        echo "  ✓ Keeping existing .env file"
        skip_env=true
    fi
fi

if [ "$skip_env" != "true" ]; then
    cat > "$ENV_FILE" << EOF
# IFCER Local Testing Configuration
# Generated on $(date)

# Application Configuration
APP_NAME=IFCER Batch Service (TEST)
LOG_LEVEL=DEBUG

# AWS Configuration
AWS_REGION=${AWS_REGION}
S3_BUCKET_NAME=${S3_BUCKET_NAME}
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
EOF
    echo "  ✓ Created .env file"
fi

# Upload certificates to S3
echo ""
echo "[5/6] Uploading certificates to S3..."

aws s3 cp "${PROJECT_ROOT}/test_certs/client_cert.pem" "s3://${S3_BUCKET_NAME}/certs/client_cert.pem" 2>/dev/null && echo "  ✓ Uploaded client_cert.pem" || echo "  ⚠️  Failed to upload client_cert.pem"
aws s3 cp "${PROJECT_ROOT}/test_certs/client_key.pem" "s3://${S3_BUCKET_NAME}/certs/client_key.pem" 2>/dev/null && echo "  ✓ Uploaded client_key.pem" || echo "  ⚠️  Failed to upload client_key.pem"
aws s3 cp "${PROJECT_ROOT}/test_certs/ca_bundle.pem" "s3://${S3_BUCKET_NAME}/certs/ca_bundle.pem" 2>/dev/null && echo "  ✓ Uploaded ca_bundle.pem" || echo "  ⚠️  Failed to upload ca_bundle.pem"

# Create and upload test data
echo ""
echo "[6/6] Creating test data..."

python3 "${PROJECT_ROOT}/tests/setup_test_data.py"

# Final instructions
echo ""
echo "=========================================="
echo "  Setup Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo ""
echo "1. Create DynamoDB table (if not exists):"
echo "   aws dynamodb create-table \\"
echo "     --table-name ifcer-certifications-test \\"
echo "     --attribute-definitions \\"
echo "       AttributeName=file_key,AttributeType=S \\"
echo "       AttributeName=processing_timestamp,AttributeType=S \\"
echo "       AttributeName=filename,AttributeType=S \\"
echo "       AttributeName=date_partition,AttributeType=S \\"
echo "     --key-schema \\"
echo "       AttributeName=file_key,KeyType=HASH \\"
echo "       AttributeName=processing_timestamp,KeyType=RANGE \\"
echo "     --provisioned-throughput ReadCapacityUnits=5,WriteCapacityUnits=5 \\"
echo "     --region ${AWS_REGION}"
echo ""
echo "2. Start mock InfoCert API (Terminal 1):"
echo "   source venv/bin/activate"
echo "   python tests/mock_infocert_api.py"
echo ""
echo "3. Start IFCER service (Terminal 2):"
echo "   source venv/bin/activate"
echo "   uvicorn app.main:app --reload"
echo ""
echo "4. Test the service (Terminal 3):"
echo "   curl http://localhost:8000/api/v1/health"
echo ""
echo "See docs/LOCAL_TESTING.md for detailed instructions"
echo ""
