#!/usr/bin/env python3
"""
Mock InfoCert API Server for Local Testing

This server mimics the InfoCert Sign API for testing purposes.
It supports mTLS (mutual TLS) and returns mock signatures.

Usage:
    python tests/mock_infocert_api.py

Requirements:
    pip install flask

⚠️  FOR TESTING ONLY - DO NOT USE IN PRODUCTION
"""

import ssl
import json
import base64
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from flask import Flask, request, jsonify

app = Flask(__name__)

# Mock signing certificate (base64 encoded DER)
# This is a placeholder - in real scenario, InfoCert returns their signing certificate
MOCK_SIGNING_CERT_B64 = None


def generate_mock_signature(manifest_b64: str) -> str:
    """Generate a mock signature for testing."""
    # Decode manifest
    manifest_bytes = base64.b64decode(manifest_b64)

    # Create a mock signature (SHA-256 hash of manifest for testing)
    # In reality, this would be an RSA signature
    signature_hash = hashlib.sha256(manifest_bytes).digest()

    # Encode as base64
    return base64.b64encode(signature_hash).decode('ascii')


def load_mock_certificate(cert_path: Path) -> str:
    """Load certificate and return as base64 DER."""
    with open(cert_path, 'rb') as f:
        cert_pem = f.read()

    # Extract certificate content (remove PEM headers)
    cert_lines = cert_pem.decode('ascii').split('\n')
    cert_b64 = ''.join([line for line in cert_lines
                        if not line.startswith('-----')])

    return cert_b64


@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return jsonify({
        "status": "healthy",
        "service": "Mock InfoCert API",
        "timestamp": datetime.now(timezone.utc).isoformat()
    })


@app.route('/sign/v2', methods=['POST'])
def sign_manifest():
    """
    Mock InfoCert Sign API endpoint.

    Request format:
    {
        "credentialID": "string",
        "documents": [{
            "content": "base64-encoded-manifest"
        }]
    }

    Response format:
    {
        "signatures": [{
            "signatureValue": "base64-signature",
            "signingCertificate": "base64-der-certificate",
            "signingTime": "ISO-8601-timestamp"
        }]
    }
    """
    try:
        # Verify mTLS client certificate
        if not request.environ.get('SSL_CLIENT_VERIFY') == 'SUCCESS':
            client_dn = request.environ.get('SSL_CLIENT_S_DN', 'Unknown')
            print(f"[MOCK API] Client certificate verified: {client_dn}")

        # Parse request
        data = request.get_json()

        if not data:
            return jsonify({"error": "Invalid request body"}), 400

        credential_id = data.get('credentialID')
        documents = data.get('documents', [])

        if not credential_id:
            return jsonify({"error": "credentialID is required"}), 400

        if not documents:
            return jsonify({"error": "documents array is required"}), 400

        print(f"\n[MOCK API] Received signature request:")
        print(f"  Credential ID: {credential_id}")
        print(f"  Documents: {len(documents)}")

        # Process each document
        signatures = []
        for idx, doc in enumerate(documents):
            manifest_b64 = doc.get('content')

            if not manifest_b64:
                return jsonify({"error": f"Document {idx}: content is required"}), 400

            # Decode manifest to show what we're signing
            try:
                manifest_bytes = base64.b64decode(manifest_b64)
                manifest_json = json.loads(manifest_bytes)
                print(f"\n  Document {idx + 1}:")
                print(f"    Filename: {manifest_json.get('fileName')}")
                print(f"    Hash: {manifest_json.get('hash', '')[:16]}...")
                print(f"    Algorithm: {manifest_json.get('algorithm')}")
            except Exception as e:
                print(f"  Could not decode manifest: {e}")

            # Generate mock signature
            signature_value = generate_mock_signature(manifest_b64)

            # Create response
            signature_response = {
                "signatureValue": signature_value,
                "signingCertificate": MOCK_SIGNING_CERT_B64,
                "signingTime": datetime.now(timezone.utc).isoformat()
            }

            signatures.append(signature_response)
            print(f"    ✓ Generated mock signature: {signature_value[:32]}...")

        response = {
            "signatures": signatures
        }

        print(f"\n[MOCK API] ✓ Returning {len(signatures)} signature(s)\n")

        return jsonify(response), 200

    except Exception as e:
        print(f"[MOCK API] ✗ Error: {str(e)}")
        return jsonify({"error": str(e)}), 500


def create_ssl_context(cert_dir: Path):
    """Create SSL context for mTLS."""
    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)

    # Server certificate and key
    server_cert = cert_dir / "server_cert.pem"
    server_key = cert_dir / "server_key.pem"
    ca_bundle = cert_dir / "ca_bundle.pem"

    if not server_cert.exists() or not server_key.exists():
        raise FileNotFoundError(
            f"Server certificates not found in {cert_dir}\n"
            f"Run: bash scripts/generate_test_certs.sh"
        )

    # Load server certificate and key
    ssl_context.load_cert_chain(
        certfile=str(server_cert),
        keyfile=str(server_key)
    )

    # Require client certificate (mTLS)
    if ca_bundle.exists():
        ssl_context.verify_mode = ssl.CERT_REQUIRED
        ssl_context.load_verify_locations(cafile=str(ca_bundle))
        print(f"[MOCK API] mTLS enabled - requiring client certificate")
        print(f"[MOCK API] CA bundle: {ca_bundle}")
    else:
        print(f"[MOCK API] ⚠️  WARNING: CA bundle not found - mTLS disabled")
        ssl_context.verify_mode = ssl.CERT_NONE

    return ssl_context


def main():
    """Run the mock InfoCert API server."""
    print("=" * 60)
    print("  Mock InfoCert Sign API Server")
    print("  FOR TESTING ONLY")
    print("=" * 60)
    print()

    # Determine certificate directory
    script_dir = Path(__file__).parent.parent
    cert_dir = script_dir / "test_certs"

    print(f"[MOCK API] Certificate directory: {cert_dir}")

    # Check if certificates exist
    if not cert_dir.exists():
        print("\n⚠️  ERROR: Test certificates not found!")
        print(f"\nPlease generate certificates first:")
        print(f"  bash scripts/generate_test_certs.sh\n")
        return

    # Load mock signing certificate
    global MOCK_SIGNING_CERT_B64
    server_cert_path = cert_dir / "server_cert.pem"
    if server_cert_path.exists():
        MOCK_SIGNING_CERT_B64 = load_mock_certificate(server_cert_path)
        print(f"[MOCK API] Loaded mock signing certificate")

    # Create SSL context
    try:
        ssl_context = create_ssl_context(cert_dir)
    except FileNotFoundError as e:
        print(f"\n⚠️  ERROR: {e}\n")
        return

    # Server configuration
    host = "127.0.0.1"
    port = 8443  # Standard HTTPS port for testing

    print()
    print(f"[MOCK API] Starting server...")
    print(f"[MOCK API] Host: {host}")
    print(f"[MOCK API] Port: {port}")
    print(f"[MOCK API] Base URL: https://{host}:{port}")
    print()
    print("Endpoints:")
    print(f"  GET  https://{host}:{port}/health")
    print(f"  POST https://{host}:{port}/sign/v2")
    print()
    print("Press Ctrl+C to stop the server")
    print("=" * 60)
    print()

    # Run server with mTLS
    try:
        app.run(
            host=host,
            port=port,
            ssl_context=ssl_context,
            debug=False
        )
    except KeyboardInterrupt:
        print("\n\n[MOCK API] Server stopped by user")
    except Exception as e:
        print(f"\n[MOCK API] ✗ Error starting server: {e}")


if __name__ == '__main__':
    main()
