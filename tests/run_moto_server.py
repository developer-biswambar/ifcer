#!/usr/bin/env python3
"""
Moto Server - Mock AWS Services (S3, DynamoDB)

This server provides local AWS service mocking without Docker.
Uses the moto library to emulate S3 and DynamoDB.

Usage:
    python tests/run_moto_server.py

Requirements:
    pip install moto[server,s3,dynamodb]

Services Available:
    - S3:        http://localhost:5000
    - DynamoDB:  http://localhost:5000

Environment:
    AWS_ENDPOINT_URL=http://localhost:5000
    AWS_ACCESS_KEY_ID=test
    AWS_SECRET_ACCESS_KEY=test
    AWS_REGION=eu-south-1
"""

import sys
from moto.server import ThreadedMotoServer


def main():
    """Run the moto server for S3 and DynamoDB mocking."""
    print("=" * 70)
    print("  Moto Server - Mock AWS Services")
    print("  (S3 + DynamoDB)")
    print("=" * 70)
    print()
    print("Starting moto server...")
    print()
    print("Configuration:")
    print("  Host: 0.0.0.0")
    print("  Port: 5000")
    print("  Services: S3, DynamoDB")
    print()
    print("Endpoint URL: http://localhost:5000")
    print()
    print("AWS CLI Configuration:")
    print("  export AWS_ENDPOINT_URL=http://localhost:5000")
    print("  export AWS_ACCESS_KEY_ID=test")
    print("  export AWS_SECRET_ACCESS_KEY=test")
    print("  export AWS_REGION=eu-south-1")
    print()
    print("Python boto3 Configuration:")
    print("  boto3.client('s3', endpoint_url='http://localhost:5000')")
    print()
    print("Press Ctrl+C to stop the server")
    print("=" * 70)
    print()

    try:
        # Create and start the server
        # This runs S3 and DynamoDB on the same port
        server = ThreadedMotoServer(
            host="0.0.0.0",
            port=5000,
            verbose=True
        )

        server.run()

    except KeyboardInterrupt:
        print("\n\n[MOTO] Server stopped by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n[MOTO] Error starting server: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
