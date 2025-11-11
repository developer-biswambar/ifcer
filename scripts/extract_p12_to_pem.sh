#!/bin/bash
# Script to extract PEM files from P12 certificate for InfoCert mTLS authentication
# Usage: ./scripts/extract_p12_to_pem.sh /path/to/your_cert.p12

set -e  # Exit on error

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo "========================================================================"
echo "  P12 to PEM Extraction Script for IFCER Service"
echo "  InfoCert mTLS Certificate Conversion"
echo "========================================================================"
echo ""

# Check if P12 file path is provided
if [ -z "$1" ]; then
    echo -e "${RED}Error: P12 file path not provided${NC}"
    echo ""
    echo "Usage: $0 /path/to/your_cert.p12 [output_directory]"
    echo ""
    echo "Example:"
    echo "  $0 ~/Downloads/infocert_cert.p12"
    echo "  $0 ~/Downloads/infocert_cert.p12 ./certs"
    echo ""
    exit 1
fi

P12_FILE="$1"
OUTPUT_DIR="${2:-./certs}"

# Check if P12 file exists
if [ ! -f "$P12_FILE" ]; then
    echo -e "${RED}Error: P12 file not found: $P12_FILE${NC}"
    exit 1
fi

# Check if openssl is installed
if ! command -v openssl &> /dev/null; then
    echo -e "${RED}Error: openssl is not installed${NC}"
    echo "Install it with:"
    echo "  macOS: brew install openssl"
    echo "  Linux: sudo apt-get install openssl"
    exit 1
fi

# Create output directory
mkdir -p "$OUTPUT_DIR"

echo -e "${YELLOW}Input P12 file:${NC} $P12_FILE"
echo -e "${YELLOW}Output directory:${NC} $OUTPUT_DIR"
echo ""

# Get P12 password
echo -e "${YELLOW}Enter P12 password:${NC}"
read -s P12_PASSWORD
echo ""

# Validate P12 file with password
echo "Validating P12 file..."
if ! echo "$P12_PASSWORD" | openssl pkcs12 -in "$P12_FILE" -passin stdin -noout &>/dev/null; then
    echo -e "${RED}Error: Invalid P12 file or incorrect password${NC}"
    exit 1
fi
echo -e "${GREEN}✓ P12 file validated${NC}"
echo ""

# Extract client certificate
echo "Extracting client certificate..."
echo "$P12_PASSWORD" | openssl pkcs12 -in "$P12_FILE" -clcerts -nokeys -out "$OUTPUT_DIR/client_cert.pem" -passin stdin -passout pass:
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Client certificate extracted: $OUTPUT_DIR/client_cert.pem${NC}"
else
    echo -e "${RED}✗ Failed to extract client certificate${NC}"
    exit 1
fi

# Extract private key (unencrypted - will be protected by S3 encryption)
echo "Extracting private key (unencrypted)..."
echo "$P12_PASSWORD" | openssl pkcs12 -in "$P12_FILE" -nocerts -nodes -out "$OUTPUT_DIR/client_key.pem" -passin stdin -passout pass:
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Private key extracted: $OUTPUT_DIR/client_key.pem${NC}"
    chmod 600 "$OUTPUT_DIR/client_key.pem"  # Restrict permissions
    echo -e "${YELLOW}  → Permissions set to 600 (owner read/write only)${NC}"
else
    echo -e "${RED}✗ Failed to extract private key${NC}"
    exit 1
fi

# Extract CA certificates (if any)
echo "Extracting CA certificates..."
echo "$P12_PASSWORD" | openssl pkcs12 -in "$P12_FILE" -cacerts -nokeys -out "$OUTPUT_DIR/ca_bundle.pem" -passin stdin -passout pass: 2>/dev/null
if [ -f "$OUTPUT_DIR/ca_bundle.pem" ] && [ -s "$OUTPUT_DIR/ca_bundle.pem" ]; then
    echo -e "${GREEN}✓ CA bundle extracted: $OUTPUT_DIR/ca_bundle.pem${NC}"
else
    echo -e "${YELLOW}⚠ No CA certificates found in P12 (this is optional)${NC}"
    rm -f "$OUTPUT_DIR/ca_bundle.pem"
fi

echo ""
echo "========================================================================"
echo -e "${GREEN}✓ Extraction Complete!${NC}"
echo "========================================================================"
echo ""
echo "Generated files:"
ls -lh "$OUTPUT_DIR"/*.pem 2>/dev/null || echo "No PEM files found"
echo ""

# Verify certificates
echo "Verifying extracted certificates..."
echo ""

# Check certificate validity
echo "Client Certificate Details:"
openssl x509 -in "$OUTPUT_DIR/client_cert.pem" -noout -subject -issuer -dates
echo ""

# Check if private key matches certificate
CERT_MODULUS=$(openssl x509 -in "$OUTPUT_DIR/client_cert.pem" -noout -modulus 2>/dev/null | openssl md5)
KEY_MODULUS=$(openssl rsa -in "$OUTPUT_DIR/client_key.pem" -noout -modulus 2>/dev/null | openssl md5)

if [ "$CERT_MODULUS" = "$KEY_MODULUS" ]; then
    echo -e "${GREEN}✓ Private key matches certificate${NC}"
else
    echo -e "${RED}✗ WARNING: Private key does NOT match certificate!${NC}"
fi
echo ""

echo "========================================================================"
echo "Next Steps:"
echo "========================================================================"
echo ""
echo "1. Upload certificates to S3:"
echo "   ${YELLOW}aws s3 cp $OUTPUT_DIR/client_cert.pem s3://YOUR-BUCKET/certs/${NC}"
echo "   ${YELLOW}aws s3 cp $OUTPUT_DIR/client_key.pem s3://YOUR-BUCKET/certs/${NC}"
if [ -f "$OUTPUT_DIR/ca_bundle.pem" ]; then
    echo "   ${YELLOW}aws s3 cp $OUTPUT_DIR/ca_bundle.pem s3://YOUR-BUCKET/certs/${NC}"
fi
echo ""
echo "2. Update your .env file:"
echo "   ${YELLOW}VENDOR_MTLS_CERT_S3_KEY=certs/client_cert.pem${NC}"
echo "   ${YELLOW}VENDOR_MTLS_KEY_S3_KEY=certs/client_key.pem${NC}"
if [ -f "$OUTPUT_DIR/ca_bundle.pem" ]; then
    echo "   ${YELLOW}VENDOR_MTLS_CA_S3_KEY=certs/ca_bundle.pem${NC}"
fi
echo ""
echo "3. Test the connection:"
echo "   ${YELLOW}curl --cert $OUTPUT_DIR/client_cert.pem --key $OUTPUT_DIR/client_key.pem https://your-infocert-api.com${NC}"
echo ""
echo "⚠️  SECURITY REMINDER:"
echo "   - Keep the private key secure (never commit to git)"
echo "   - Delete local copies after uploading to S3"
echo "   - Use S3 encryption at rest"
echo "   - Restrict S3 bucket access with IAM policies"
echo ""
