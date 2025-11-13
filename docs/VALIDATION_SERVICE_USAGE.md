# Validation Service Usage Guide

The `ValidationService` provides independent signature validation functions that can be used anywhere in the codebase. It mimics regulatory authority validation processes.

## Features

- ✅ Manifest structure validation
- ✅ File hash verification (SHA256, SHA512, SHA1)
- ✅ P7M/PKCS#7 structure verification
- ✅ Cryptographic signature verification
- ✅ Certificate validation (expiration, validity dates)
- ✅ Can be used independently or integrated into workflows

## Basic Usage

### 1. Full Validation (Regulatory-Style)

```python
from app.services.validation_service import ValidationService
from app.services.s3_service import S3Service

# Initialize services
validator = ValidationService()
s3_service = S3Service()

# Download files from S3
original_file = s3_service.download_file("uploads/document.txt")
manifest_json = s3_service.download_file("signed/document.json")
p7s_signature = s3_service.download_file("signed/document.p7s")

# Perform full validation
result = validator.validate_signature(
    original_file_content=original_file,
    manifest_content=manifest_json,
    p7s_signature=p7s_signature,
    expected_filename="document.txt"  # Optional
)

# Check results
if result["valid"]:
    print("✓ Signature is valid!")
    print(f"Certificate: {result['certificate_info']['subject']}")
else:
    print("× Signature validation failed")
    print(f"Errors: {result['errors']}")
```

### 2. Quick Validation (Hash Only)

```python
from app.services.validation_service import ValidationService

validator = ValidationService()

# Just verify file hash matches manifest (fast)
is_valid = validator.quick_validate(
    original_file_content=original_file,
    manifest_content=manifest_json
)

if is_valid:
    print("✓ File hash matches manifest")
else:
    print("× Hash mismatch")
```

## Use Cases

### In Signature Service (Optional Verification)

```python
from app.services.validation_service import ValidationService

class SignatureService:
    def __init__(self):
        self.validator = ValidationService()

    def sign_and_validate(self, signature_request):
        # Perform signing
        response = self.sign_file_hash(signature_request)

        # Optional: Validate immediately after signing
        if settings.validate_after_signing:
            validation_result = self.validator.validate_signature(
                original_file_content=original_file,
                manifest_content=response.manifest_content,
                p7s_signature=response.p7m_content
            )

            if not validation_result["valid"]:
                raise ValueError("Post-signing validation failed")

        return response
```

### In Processing Workflow

```python
from app.services.validation_service import ValidationService

async def process_and_validate(file_key):
    # Download original
    original = s3_service.download_file(file_key)

    # Sign the file
    signature_response = await sign_file(file_key)

    # Validate signed file
    validator = ValidationService()
    result = validator.validate_signature(
        original_file_content=original,
        manifest_content=signature_response.manifest_content,
        p7s_signature=signature_response.p7m_content
    )

    # Store validation result in DynamoDB
    dynamodb_service.save_validation_result(file_key, result)

    return result
```

### As Standalone Verification Tool

```python
from app.services.validation_service import ValidationService
import sys

def verify_signed_file(original_path, manifest_path, p7s_path):
    """CLI tool to verify signed files."""
    validator = ValidationService()

    with open(original_path, 'rb') as f:
        original = f.read()

    with open(manifest_path, 'rb') as f:
        manifest = f.read()

    with open(p7s_path, 'rb') as f:
        p7s = f.read()

    result = validator.validate_signature(original, manifest, p7s)

    if result["valid"]:
        print("✓ VALID SIGNATURE")
        print(f"Signed by: {result['certificate_info']['subject']}")
        print(f"Valid until: {result['certificate_info']['not_valid_after']}")
        return 0
    else:
        print("× INVALID SIGNATURE")
        for error in result["errors"]:
            print(f"  - {error}")
        return 1

if __name__ == "__main__":
    sys.exit(verify_signed_file(sys.argv[1], sys.argv[2], sys.argv[3]))
```

## Validation Result Structure

```python
{
    "valid": bool,  # Overall validation result
    "checks": {
        "manifest_structure": bool,      # Manifest JSON valid
        "file_hash_match": bool,         # Hash matches
        "signature_structure": bool,     # P7M structure valid
        "signature_verified": bool,      # Cryptographic verification
        "certificate_valid": bool        # Certificate not expired
    },
    "manifest_data": {
        "fileName": "document.txt",
        "hash": "ABC123...",
        "algorithm": "SHA256",
        "timestamp": "2025-11-13T..."
    },
    "certificate_info": {
        "subject": "CN=...",
        "issuer": "CN=...",
        "serial_number": "123456",
        "not_valid_before": "2024-01-01T...",
        "not_valid_after": "2026-01-01T...",
        "signature_algorithm": "sha256WithRSAEncryption"
    },
    "certificate_details": {
        "expired": false,
        "not_yet_valid": false,
        "valid": true
    },
    "computed_file_hash": "ABC123...",
    "p7m_data": {
        "version": "v1",
        "digest_algorithms": ["sha256"],
        "certificate_count": 1,
        "signer_count": 1
    },
    "errors": [],  # List of error messages if validation fails
    "validation_timestamp": "2025-11-13T..."
}
```

## Integration Examples

### Add to Existing Endpoint

```python
@router.post("/validate-signature")
async def validate_signature_endpoint(request: ValidateRequest):
    """Endpoint to validate a signed file."""
    try:
        # Download files
        original = s3_service.download_file(request.original_file_key)
        manifest = s3_service.download_file(request.manifest_key)
        p7s = s3_service.download_file(request.p7s_key)

        # Validate
        validator = ValidationService()
        result = validator.validate_signature(original, manifest, p7s)

        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

### Batch Validation

```python
from app.services.validation_service import ValidationService

async def validate_batch(file_keys: List[str]):
    """Validate multiple signed files."""
    validator = ValidationService()
    results = []

    for file_key in file_keys:
        try:
            # Get certification record
            cert = dynamodb_service.get_certification(file_key)

            if not cert or cert["status"] != "completed":
                results.append({"file_key": file_key, "valid": False, "error": "Not signed"})
                continue

            # Download files
            original = s3_service.download_file(file_key)
            manifest = s3_service.download_file(cert["signed_file_key"].replace(".p7s", ".json"))
            p7s = s3_service.download_file(cert["signed_file_key"])

            # Validate
            result = validator.validate_signature(original, manifest, p7s)
            result["file_key"] = file_key
            results.append(result)

        except Exception as e:
            results.append({"file_key": file_key, "valid": False, "error": str(e)})

    return results
```

## Configuration Options

You can optionally enable automatic validation in your settings:

```python
# app/config.py
class Settings(BaseSettings):
    # ... other settings

    # Optional: Validate signatures after signing
    validate_after_signing: bool = False

    # Optional: Fail signing if validation fails
    fail_on_validation_error: bool = False
```

## Testing

```python
import pytest
from app.services.validation_service import ValidationService

def test_validation_service():
    validator = ValidationService()

    # Test with valid signature
    result = validator.validate_signature(
        original_file_content=test_file,
        manifest_content=test_manifest,
        p7s_signature=test_p7s
    )

    assert result["valid"] == True
    assert result["checks"]["file_hash_match"] == True
    assert result["checks"]["signature_verified"] == True
```

## Best Practices

1. **Use full validation for regulatory compliance** - The complete `validate_signature()` method
2. **Use quick validation for performance** - The `quick_validate()` method for hash-only checks
3. **Store validation results** - Save validation results in DynamoDB for audit trails
4. **Log validation failures** - Always log why validation failed
5. **Independent verification** - Keep validation separate from signing logic

## Notes

- **Independent Service**: Does not depend on `SignatureService`
- **Regulatory Compliance**: Mimics Italian authority validation process
- **Flexible Integration**: Can be used anywhere in the codebase
- **Comprehensive Checks**: Validates structure, cryptography, and certificates
- **Error Details**: Provides detailed error messages for debugging
