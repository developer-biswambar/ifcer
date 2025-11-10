#!/usr/bin/env python3
"""
Setup AWS Resources in Moto

Creates S3 bucket, DynamoDB table, and uploads test data to moto server.

Usage:
    # Start moto server first (in another terminal):
    python tests/run_moto_server.py

    # Then run this script:
    python tests/setup_moto_resources.py

Requirements:
    - Moto server running on http://localhost:5000
    - boto3 installed
"""

import os
import json
import boto3
from datetime import datetime
from pathlib import Path
from botocore.exceptions import ClientError


# Moto configuration
MOTO_ENDPOINT = os.getenv('AWS_ENDPOINT_URL', 'http://localhost:5000')
AWS_REGION = os.getenv('AWS_REGION', 'eu-south-1')
S3_BUCKET = os.getenv('S3_BUCKET_NAME', 'ifcer-test-bucket')
DYNAMODB_TABLE = os.getenv('DYNAMODB_TABLE_NAME', 'ifcer-certifications-test')


def get_boto3_client(service_name):
    """Create boto3 client configured for moto."""
    return boto3.client(
        service_name,
        endpoint_url=MOTO_ENDPOINT,
        region_name=AWS_REGION,
        aws_access_key_id='test',
        aws_secret_access_key='test'
    )


def create_s3_bucket():
    """Create S3 bucket in moto."""
    print(f"\n[S3] Creating bucket: {S3_BUCKET}")

    s3 = get_boto3_client('s3')

    try:
        # Check if bucket already exists
        s3.head_bucket(Bucket=S3_BUCKET)
        print(f"  ℹ️  Bucket already exists: {S3_BUCKET}")
        return s3
    except ClientError:
        pass

    try:
        # Create bucket
        if AWS_REGION == 'us-east-1':
            s3.create_bucket(Bucket=S3_BUCKET)
        else:
            s3.create_bucket(
                Bucket=S3_BUCKET,
                CreateBucketConfiguration={'LocationConstraint': AWS_REGION}
            )
        print(f"  ✓ Created bucket: {S3_BUCKET}")
        return s3
    except Exception as e:
        print(f"  ✗ Error creating bucket: {e}")
        raise


def create_dynamodb_table():
    """Create DynamoDB table in moto."""
    print(f"\n[DynamoDB] Creating table: {DYNAMODB_TABLE}")

    dynamodb = get_boto3_client('dynamodb')

    try:
        # Check if table already exists
        dynamodb.describe_table(TableName=DYNAMODB_TABLE)
        print(f"  ℹ️  Table already exists: {DYNAMODB_TABLE}")
        return dynamodb
    except ClientError:
        pass

    try:
        # Create table
        response = dynamodb.create_table(
            TableName=DYNAMODB_TABLE,
            AttributeDefinitions=[
                {'AttributeName': 'file_key', 'AttributeType': 'S'},
                {'AttributeName': 'processing_timestamp', 'AttributeType': 'S'},
                {'AttributeName': 'filename', 'AttributeType': 'S'},
                {'AttributeName': 'date_partition', 'AttributeType': 'S'}
            ],
            KeySchema=[
                {'AttributeName': 'file_key', 'KeyType': 'HASH'},
                {'AttributeName': 'processing_timestamp', 'KeyType': 'RANGE'}
            ],
            GlobalSecondaryIndexes=[
                {
                    'IndexName': 'filename-index',
                    'KeySchema': [
                        {'AttributeName': 'filename', 'KeyType': 'HASH'},
                        {'AttributeName': 'processing_timestamp', 'KeyType': 'RANGE'}
                    ],
                    'Projection': {'ProjectionType': 'ALL'},
                    'ProvisionedThroughput': {
                        'ReadCapacityUnits': 5,
                        'WriteCapacityUnits': 5
                    }
                },
                {
                    'IndexName': 'date-index',
                    'KeySchema': [
                        {'AttributeName': 'date_partition', 'KeyType': 'HASH'},
                        {'AttributeName': 'processing_timestamp', 'KeyType': 'RANGE'}
                    ],
                    'Projection': {'ProjectionType': 'ALL'},
                    'ProvisionedThroughput': {
                        'ReadCapacityUnits': 5,
                        'WriteCapacityUnits': 5
                    }
                }
            ],
            ProvisionedThroughput={
                'ReadCapacityUnits': 5,
                'WriteCapacityUnits': 5
            }
        )
        print(f"  ✓ Created table: {DYNAMODB_TABLE}")
        return dynamodb
    except Exception as e:
        print(f"  ✗ Error creating table: {e}")
        raise


def create_test_files():
    """Create sample test files."""
    print("\n[FILES] Creating test files")

    script_dir = Path(__file__).parent
    test_files_dir = script_dir / "test_files"
    test_files_dir.mkdir(exist_ok=True)

    files = []

    # XML file
    xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<TradeDeclaration>
    <DeclarationID>TD-2025-001</DeclarationID>
    <Trader>
        <Name>Test Company SRL</Name>
        <VatNumber>IT12345678901</VatNumber>
    </Trader>
    <Goods>
        <Description>Electronic Components</Description>
        <Value currency="EUR">15000.00</Value>
    </Goods>
    <Timestamp>2025-11-10T10:00:00Z</Timestamp>
</TradeDeclaration>"""

    xml_file = test_files_dir / "trade_declaration_001.xml"
    xml_file.write_text(xml_content)
    files.append(xml_file)
    print(f"  ✓ {xml_file.name}")

    # JSON file
    json_content = {
        "invoice_id": "INV-2025-12345",
        "date": "2025-11-10",
        "vendor": {"name": "Test Supplier SpA", "vat": "IT98765432109"},
        "total": 1500.00,
        "currency": "EUR"
    }

    json_file = test_files_dir / "invoice_12345.json"
    json_file.write_text(json.dumps(json_content, indent=2))
    files.append(json_file)
    print(f"  ✓ {json_file.name}")

    # TXT file
    txt_content = "OFFICIAL DOCUMENT - CERTIFICATION REQUIRED\n\nDocument Number: DOC-2025-5678\nDate: 2025-11-10\n"
    txt_file = test_files_dir / "document_5678.txt"
    txt_file.write_text(txt_content)
    files.append(txt_file)
    print(f"  ✓ {txt_file.name}")

    # CSV file
    csv_content = "transaction_id,date,amount,currency\nTXN-001,2025-11-10,1250.50,EUR\nTXN-002,2025-11-10,3400.00,EUR\n"
    csv_file = test_files_dir / "transactions.csv"
    csv_file.write_text(csv_content)
    files.append(csv_file)
    print(f"  ✓ {csv_file.name}")

    return files


def upload_test_files(s3_client, files):
    """Upload test files to S3."""
    print(f"\n[S3] Uploading test files to: {S3_BUCKET}")

    for file_path in files:
        s3_key = f"incoming/{file_path.name}"

        # Determine content type
        content_type = "application/octet-stream"
        if file_path.suffix == ".xml":
            content_type = "application/xml"
        elif file_path.suffix == ".json":
            content_type = "application/json"
        elif file_path.suffix == ".txt":
            content_type = "text/plain"
        elif file_path.suffix == ".csv":
            content_type = "text/csv"

        with open(file_path, 'rb') as f:
            s3_client.put_object(
                Bucket=S3_BUCKET,
                Key=s3_key,
                Body=f,
                ContentType=content_type
            )

        print(f"  ✓ {s3_key}")


def upload_test_certificates(s3_client):
    """Upload test certificates to S3."""
    print(f"\n[S3] Uploading test certificates to: {S3_BUCKET}")

    script_dir = Path(__file__).parent.parent
    cert_dir = script_dir / "test_certs"

    if not cert_dir.exists():
        print(f"  ⚠️  Certificate directory not found: {cert_dir}")
        print(f"  Run: bash scripts/generate_test_certs.sh")
        return

    cert_files = [
        ("client_cert.pem", "certs/client_cert.pem"),
        ("client_key.pem", "certs/client_key.pem"),
        ("ca_bundle.pem", "certs/ca_bundle.pem")
    ]

    for local_name, s3_key in cert_files:
        cert_path = cert_dir / local_name

        if not cert_path.exists():
            print(f"  ⚠️  Not found: {local_name}")
            continue

        with open(cert_path, 'rb') as f:
            s3_client.put_object(
                Bucket=S3_BUCKET,
                Key=s3_key,
                Body=f,
                ContentType="application/x-pem-file"
            )

        print(f"  ✓ {s3_key}")


def verify_setup(s3_client, dynamodb_client):
    """Verify all resources are created."""
    print("\n[VERIFY] Checking resources")

    # Check S3 bucket
    try:
        s3_client.head_bucket(Bucket=S3_BUCKET)
        print(f"  ✓ S3 bucket: {S3_BUCKET}")
    except Exception as e:
        print(f"  ✗ S3 bucket error: {e}")

    # List files
    try:
        response = s3_client.list_objects_v2(Bucket=S3_BUCKET, Prefix="incoming/")
        file_count = len(response.get('Contents', []))
        print(f"  ✓ Files in incoming/: {file_count}")
    except Exception as e:
        print(f"  ✗ Error listing files: {e}")

    # Check DynamoDB table
    try:
        response = dynamodb_client.describe_table(TableName=DYNAMODB_TABLE)
        status = response['Table']['TableStatus']
        print(f"  ✓ DynamoDB table: {DYNAMODB_TABLE} ({status})")
    except Exception as e:
        print(f"  ✗ DynamoDB table error: {e}")


def main():
    """Main setup function."""
    print("=" * 70)
    print("  Moto AWS Resources Setup")
    print("=" * 70)
    print()
    print("Configuration:")
    print(f"  Moto Endpoint: {MOTO_ENDPOINT}")
    print(f"  AWS Region: {AWS_REGION}")
    print(f"  S3 Bucket: {S3_BUCKET}")
    print(f"  DynamoDB Table: {DYNAMODB_TABLE}")

    try:
        # Test connection to moto
        print("\n[MOTO] Testing connection...")
        s3_test = get_boto3_client('s3')
        s3_test.list_buckets()
        print("  ✓ Moto server is running")
    except Exception as e:
        print(f"  ✗ Cannot connect to moto server: {e}")
        print("\nPlease start moto server first:")
        print("  python tests/run_moto_server.py")
        return

    # Create S3 bucket
    s3 = create_s3_bucket()

    # Create DynamoDB table
    dynamodb = create_dynamodb_table()

    # Create and upload test files
    files = create_test_files()
    upload_test_files(s3, files)

    # Upload test certificates
    upload_test_certificates(s3)

    # Verify setup
    verify_setup(s3, dynamodb)

    print("\n" + "=" * 70)
    print("  Setup Complete!")
    print("=" * 70)
    print("\nNext steps:")
    print()
    print("1. Start mock InfoCert API (Terminal 1):")
    print("   python tests/mock_infocert_api.py")
    print()
    print("2. Start IFCER service (Terminal 2):")
    print("   # Use .env.moto configuration")
    print("   uvicorn app.main:app --reload")
    print()
    print("3. Test the service:")
    print("   curl http://localhost:8000/api/v1/health")
    print()


if __name__ == '__main__':
    main()
