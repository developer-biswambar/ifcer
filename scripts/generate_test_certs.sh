#!/bin/bash

# Script to generate self-signed certificates for testing the IFCER batch service
# These certificates are for TESTING ONLY and should never be used in production

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CERTS_DIR="${SCRIPT_DIR}/../test_certs"

echo "=========================================="
echo "  Self-Signed Certificate Generator"
echo "  For TESTING ONLY"
echo "=========================================="
echo ""

# Create certs directory
mkdir -p "${CERTS_DIR}"
cd "${CERTS_DIR}"

echo "[1/4] Generating CA (Certificate Authority)..."
# Generate CA private key
openssl genrsa -out ca_key.pem 4096

# Generate CA certificate (valid for 10 years)
openssl req -new -x509 -days 3650 -key ca_key.pem -out ca_bundle.pem \
  -subj "/C=IT/ST=Lazio/L=Rome/O=IFCER Test CA/OU=Testing/CN=IFCER Test CA"

echo "✓ CA certificate generated: ca_bundle.pem"
echo ""

echo "[2/4] Generating Client Certificate and Key..."
# Generate client private key
openssl genrsa -out client_key.pem 4096

# Generate client certificate signing request
openssl req -new -key client_key.pem -out client.csr \
  -subj "/C=IT/ST=Lazio/L=Rome/O=IFCER Client/OU=Testing/CN=ifcer-client"

# Sign client certificate with CA (valid for 2 years)
openssl x509 -req -days 730 -in client.csr \
  -CA ca_bundle.pem -CAkey ca_key.pem -CAcreateserial \
  -out client_cert.pem

echo "✓ Client certificate generated: client_cert.pem"
echo "✓ Client key generated: client_key.pem"
echo ""

echo "[3/4] Generating Server Certificate for Mock API..."
# Generate server private key
openssl genrsa -out server_key.pem 4096

# Generate server certificate signing request
openssl req -new -key server_key.pem -out server.csr \
  -subj "/C=IT/ST=Lazio/L=Rome/O=Mock InfoCert/OU=Testing/CN=localhost"

# Create server certificate with SAN (Subject Alternative Name)
cat > server_cert_ext.cnf <<EOF
subjectAltName = DNS:localhost,DNS:mock-infocert,IP:127.0.0.1
extendedKeyUsage = serverAuth
EOF

# Sign server certificate with CA
openssl x509 -req -days 730 -in server.csr \
  -CA ca_bundle.pem -CAkey ca_key.pem -CAcreateserial \
  -out server_cert.pem -extfile server_cert_ext.cnf

echo "✓ Server certificate generated: server_cert.pem"
echo "✓ Server key generated: server_key.pem"
echo ""

echo "[4/4] Verifying certificates..."
# Verify client certificate
openssl verify -CAfile ca_bundle.pem client_cert.pem

# Verify server certificate
openssl verify -CAfile ca_bundle.pem server_cert.pem

echo ""
echo "=========================================="
echo "  Certificate Generation Complete!"
echo "=========================================="
echo ""
echo "Generated files in: ${CERTS_DIR}"
echo ""
echo "Client mTLS (for IFCER service):"
echo "  - client_cert.pem  (client certificate)"
echo "  - client_key.pem   (client private key)"
echo "  - ca_bundle.pem    (CA certificate)"
echo ""
echo "Server mTLS (for mock InfoCert API):"
echo "  - server_cert.pem  (server certificate)"
echo "  - server_key.pem   (server private key)"
echo "  - ca_bundle.pem    (CA certificate)"
echo ""
echo "To view certificate details:"
echo "  openssl x509 -in ${CERTS_DIR}/client_cert.pem -text -noout"
echo ""
echo "⚠️  WARNING: These are SELF-SIGNED certificates for TESTING ONLY"
echo "    DO NOT use in production!"
echo ""

# Clean up temporary files
rm -f client.csr server.csr server_cert_ext.cnf ca_bundle.srl

echo "Cleaned up temporary files."
echo ""
