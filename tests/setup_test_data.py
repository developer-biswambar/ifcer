#!/usr/bin/env python3
"""
Test Data Setup Script

Creates sample files and uploads them to S3 for testing the IFCER batch service.

Usage:
    python tests/setup_test_data.py

Requirements:
    pip install boto3

Environment Variables:
    S3_BUCKET_NAME - S3 bucket to upload test files
    AWS_REGION - AWS region (default: eu-south-1)
    AWS_ACCESS_KEY_ID - AWS access key (optional if using IAM role)
    AWS_SECRET_ACCESS_KEY - AWS secret key (optional if using IAM role)
"""

import os
import json
import boto3
from datetime import datetime, timezone
from pathlib import Path
from typing import List


def create_sample_files(output_dir: Path) -> List[Path]:
    """Create sample test files."""
    print(f"\n[SETUP] Creating sample test files in: {output_dir}")

    output_dir.mkdir(parents=True, exist_ok=True)

    files = []

    # Sample 1: XML trade declaration
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
        <Origin>Italy</Origin>
    </Goods>
    <Timestamp>2025-11-10T10:00:00Z</Timestamp>
</TradeDeclaration>"""

    xml_file = output_dir / "trade_declaration_001.xml"
    xml_file.write_text(xml_content)
    files.append(xml_file)
    print(f"  ✓ Created: {xml_file.name} ({len(xml_content)} bytes)")

    # Sample 2: JSON invoice
    json_content = {
        "invoice_id": "INV-2025-12345",
        "date": "2025-11-10",
        "vendor": {
            "name": "Test Supplier SpA",
            "vat": "IT98765432109",
            "address": "Via Roma 123, Milan, Italy"
        },
        "customer": {
            "name": "Test Customer SRL",
            "vat": "IT11223344556"
        },
        "items": [
            {
                "description": "Professional Services",
                "quantity": 10,
                "unit_price": 150.00,
                "total": 1500.00
            }
        ],
        "total": 1500.00,
        "currency": "EUR"
    }

    json_file = output_dir / "invoice_12345.json"
    json_file.write_text(json.dumps(json_content, indent=2))
    files.append(json_file)
    print(f"  ✓ Created: {json_file.name} ({json_file.stat().st_size} bytes)")

    # Sample 3: Plain text document
    txt_content = """OFFICIAL DOCUMENT - CERTIFICATION REQUIRED

Document Number: DOC-2025-5678
Date: November 10, 2025

This document certifies that the shipment identified by tracking number
SHIP-IT-2025-9999 has been processed and cleared for customs.

Origin: Italy
Destination: France
Weight: 250 kg

Authorized by: Test Authority
Date: 2025-11-10T10:00:00Z

END OF DOCUMENT
"""

    txt_file = output_dir / "official_document_5678.txt"
    txt_file.write_text(txt_content)
    files.append(txt_file)
    print(f"  ✓ Created: {txt_file.name} ({len(txt_content)} bytes)")

    # Sample 4: CSV data file
    csv_content = """transaction_id,date,amount,currency,status
TXN-001,2025-11-10,1250.50,EUR,completed
TXN-002,2025-11-10,3400.00,EUR,completed
TXN-003,2025-11-10,875.25,EUR,pending
TXN-004,2025-11-10,5600.00,EUR,completed
"""

    csv_file = output_dir / "transactions_2025_11.csv"
    csv_file.write_text(csv_content)
    files.append(csv_file)
    print(f"  ✓ Created: {csv_file.name} ({len(csv_content)} bytes)")

    print(f"\n[SETUP] Created {len(files)} sample files")
    return files


def upload_files_to_s3(files: List[Path], bucket_name: str, region: str = "eu-south-1"):
    """Upload files to S3."""
    print(f"\n[SETUP] Uploading files to S3...")
    print(f"  Bucket: {bucket_name}")
    print(f"  Region: {region}")

    try:
        # Create S3 client
        s3_client = boto3.client('s3', region_name=region)

        # Check if bucket exists
        try:
            s3_client.head_bucket(Bucket=bucket_name)
            print(f"  ✓ Bucket '{bucket_name}' found")
        except Exception as e:
            print(f"  ✗ Error accessing bucket '{bucket_name}': {e}")
            print(f"\n  Creating bucket '{bucket_name}'...")
            try:
                if region == 'us-east-1':
                    s3_client.create_bucket(Bucket=bucket_name)
                else:
                    s3_client.create_bucket(
                        Bucket=bucket_name,
                        CreateBucketConfiguration={'LocationConstraint': region}
                    )
                print(f"  ✓ Bucket created successfully")
            except Exception as create_error:
                print(f"  ✗ Failed to create bucket: {create_error}")
                return

        # Upload each file
        uploaded_count = 0
        for file_path in files:
            s3_key = f"incoming/{file_path.name}"

            try:
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

                # Upload file
                with open(file_path, 'rb') as f:
                    s3_client.put_object(
                        Bucket=bucket_name,
                        Key=s3_key,
                        Body=f,
                        ContentType=content_type
                    )

                print(f"  ✓ Uploaded: {s3_key}")
                uploaded_count += 1

            except Exception as e:
                print(f"  ✗ Failed to upload {file_path.name}: {e}")

        print(f"\n[SETUP] Uploaded {uploaded_count}/{len(files)} files successfully")

        # List files in bucket to verify
        print(f"\n[SETUP] Verifying files in S3...")
        response = s3_client.list_objects_v2(
            Bucket=bucket_name,
            Prefix="incoming/"
        )

        if 'Contents' in response:
            print(f"  Found {len(response['Contents'])} file(s) in incoming/ folder:")
            for obj in response['Contents']:
                print(f"    - {obj['Key']} ({obj['Size']} bytes, {obj['LastModified']})")
        else:
            print(f"  No files found in incoming/ folder")

    except Exception as e:
        print(f"\n[SETUP] ✗ Error uploading to S3: {e}")
        raise


def upload_test_certificates(cert_dir: Path, bucket_name: str, region: str = "eu-south-1"):
    """Upload test certificates to S3."""
    print(f"\n[SETUP] Uploading test certificates to S3...")

    try:
        s3_client = boto3.client('s3', region_name=region)

        cert_files = [
            ("client_cert.pem", "certs/client_cert.pem"),
            ("client_key.pem", "certs/client_key.pem"),
            ("ca_bundle.pem", "certs/ca_bundle.pem")
        ]

        uploaded_count = 0
        for local_name, s3_key in cert_files:
            cert_path = cert_dir / local_name

            if not cert_path.exists():
                print(f"  ⚠️  Certificate not found: {cert_path}")
                continue

            try:
                with open(cert_path, 'rb') as f:
                    s3_client.put_object(
                        Bucket=bucket_name,
                        Key=s3_key,
                        Body=f,
                        ContentType="application/x-pem-file"
                    )

                print(f"  ✓ Uploaded: {s3_key}")
                uploaded_count += 1

            except Exception as e:
                print(f"  ✗ Failed to upload {local_name}: {e}")

        print(f"\n[SETUP] Uploaded {uploaded_count}/{len(cert_files)} certificates")

    except Exception as e:
        print(f"\n[SETUP] ✗ Error uploading certificates: {e}")


def main():
    """Main setup function."""
    print("=" * 70)
    print("  IFCER Test Data Setup")
    print("=" * 70)

    # Get configuration from environment
    bucket_name = os.getenv('S3_BUCKET_NAME')
    region = os.getenv('AWS_REGION', 'eu-south-1')

    if not bucket_name:
        print("\n⚠️  ERROR: S3_BUCKET_NAME environment variable is required")
        print("\nUsage:")
        print("  export S3_BUCKET_NAME=your-test-bucket")
        print("  export AWS_REGION=eu-south-1  # optional")
        print("  python tests/setup_test_data.py")
        print()
        return

    print(f"\nConfiguration:")
    print(f"  S3 Bucket: {bucket_name}")
    print(f"  AWS Region: {region}")

    # Create test files directory
    script_dir = Path(__file__).parent
    test_files_dir = script_dir / "test_files"

    # Create sample files
    files = create_sample_files(test_files_dir)

    # Upload to S3
    upload_files_to_s3(files, bucket_name, region)

    # Upload test certificates if they exist
    cert_dir = script_dir.parent / "test_certs"
    if cert_dir.exists():
        upload_test_certificates(cert_dir, bucket_name, region)
    else:
        print(f"\n⚠️  Test certificates not found in: {cert_dir}")
        print(f"  Run: bash scripts/generate_test_certs.sh")

    print("\n" + "=" * 70)
    print("  Setup Complete!")
    print("=" * 70)
    print("\nNext steps:")
    print("  1. Start mock InfoCert API:")
    print("     python tests/mock_infocert_api.py")
    print()
    print("  2. Update .env file with test configuration:")
    print(f"     VENDOR_API_URL=https://127.0.0.1:8443")
    print(f"     S3_BUCKET_NAME={bucket_name}")
    print()
    print("  3. Run the IFCER service:")
    print("     uvicorn app.main:app --reload")
    print()
    print("  4. Test the processing endpoint:")
    print("     curl -X POST http://localhost:8000/api/v1/process \\")
    print("       -H 'Content-Type: application/json' \\")
    print("       -d '{")
    print("         \"start_date\": \"2025-11-01T00:00:00Z\",")
    print("         \"end_date\": \"2025-11-30T23:59:59Z\",")
    print("         \"prefix\": \"incoming/\"")
    print("       }'")
    print()


if __name__ == '__main__':
    main()
