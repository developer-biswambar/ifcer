# Validation Service Usage Guide

The `ValidationService` provides independent signature validation functions that can be used anywhere in the codebase. It mimics regulatory authority validation processes for P7M files with embedded content.

## Features

- ✅ P7M/PKCS#7 structure verification
- ✅ Embedded file extraction from P7M
- ✅ File integrity verification (embedded vs original)
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
p7m_file = s3_service.download_file("signed/document.p7m")

# Perform full validation
result = validator.validate_signature(
    original_file_content=original_file,
    p7m_file=p7m_file
)

# Check results
if result["valid"]:
    print("✓ Signature is valid!")
    print(f"Certificate: {result['certificate_info']['subject']}")
else:
    print("× Signature validation failed")
    print(f"Errors: {result['errors']}")
```

### 2. Quick Validation (Content Match Only)

```python
from app.services.validation_service import ValidationService

validator = ValidationService()

# Just verify embedded file matches original (fast)
is_valid = validator.quick_validate(
    original_file_content=original_file,
    p7m_file=p7m_file
)

if is_valid:
    print("✓ Embedded file matches original")
else:
    print("× Embedded file mismatch")
```

## Use Cases

### In Signature Service (Optional Verification)

```python
from app.services.validation_service import ValidationService

class SignatureService:
    def __init__(self):
        self.validator = ValidationService()

    def sign_and_validate(self, signature_request, original_file_content):
        # Perform signing
        response = self.sign_file_hash(signature_request, original_file_content)

        # Optional: Validate immediately after signing
        if settings.validate_after_signing:
            validation_result = self.validator.validate_signature(
                original_file_content=original_file_content,
                p7m_file=response.p7m_content
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
    signature_response = await sign_file(file_key, original)

    # Validate P7M file
    validator = ValidationService()
    result = validator.validate_signature(
        original_file_content=original,
        p7m_file=signature_response.p7m_content
    )

    # Store validation result in DynamoDB
    dynamodb_service.save_validation_result(file_key, result)

    return result
```

### As Standalone Verification Tool

```python
from app.services.validation_service import ValidationService
import sys

def verify_p7m_file(original_path, p7m_path):
    """CLI tool to verify P7M files."""
    validator = ValidationService()

    with open(original_path, 'rb') as f:
        original = f.read()

    with open(p7m_path, 'rb') as f:
        p7m = f.read()

    result = validator.validate_signature(original, p7m)

    if result["valid"]:
        print("✓ VALID P7M SIGNATURE")
        print(f"Signed by: {result['certificate_info']['subject']}")
        print(f"Valid until: {result['certificate_info']['not_valid_after']}")
        return 0
    else:
        print("× INVALID P7M SIGNATURE")
        for error in result["errors"]:
            print(f"  - {error}")
        return 1

if __name__ == "__main__":
    sys.exit(verify_p7m_file(sys.argv[1], sys.argv[2]))
```

## Validation Result Structure

```python
{
    "valid": bool,  # Overall validation result
    "checks": {
        "signature_structure": bool,      # P7M structure valid
        "embedded_file_extracted": bool,  # File extracted from P7M
        "embedded_file_match": bool,      # Embedded file matches original
        "signature_verified": bool,       # Cryptographic verification
        "certificate_valid": bool         # Certificate not expired
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
    "p7m_data": {
        "version": "v1",
        "digest_algorithms": ["sha256"],
        "certificate_count": 1,
        "signer_count": 1
    },
    "errors": [],  # List of error messages if validation fails
    "validation_timestamp": "2025-11-14T..."
}
```

## Integration Examples

### Add to Existing Endpoint

```python
@router.post("/validate-signature")
async def validate_signature_endpoint(request: ValidateRequest):
    """Endpoint to validate a P7M signed file."""
    try:
        # Download files
        original = s3_service.download_file(request.original_file_key)
        p7m = s3_service.download_file(request.p7m_key)

        # Validate
        validator = ValidationService()
        result = validator.validate_signature(original, p7m)

        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

### Batch Validation

```python
from app.services.validation_service import ValidationService

async def validate_batch(file_keys: List[str]):
    """Validate multiple P7M signed files."""
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
            p7m = s3_service.download_file(cert["signed_file_key"])

            # Validate
            result = validator.validate_signature(original, p7m)
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

    # Test with valid P7M file
    result = validator.validate_signature(
        original_file_content=test_file,
        p7m_file=test_p7m
    )

    assert result["valid"] == True
    assert result["checks"]["embedded_file_extracted"] == True
    assert result["checks"]["embedded_file_match"] == True
    assert result["checks"]["signature_verified"] == True
```

## Best Practices

1. **Use full validation for regulatory compliance** - The complete `validate_signature()` method
2. **Use quick validation for performance** - The `quick_validate()` method for embedded file comparison only
3. **Store validation results** - Save validation results in DynamoDB for audit trails
4. **Log validation failures** - Always log why validation failed
5. **Independent verification** - Keep validation separate from signing logic

## Notes

- **Independent Service**: Does not depend on `SignatureService`
- **Regulatory Compliance**: Mimics Italian authority P7M validation process
- **Flexible Integration**: Can be used anywhere in the codebase
- **Comprehensive Checks**: Validates P7M structure, embedded content, cryptography, and certificates
- **Error Details**: Provides detailed error messages for debugging
- **P7M Format**: Works with ENVELOPED signatures (original file embedded in P7M)
- **No Manifest**: Does not use separate manifest files - validates embedded content directly
