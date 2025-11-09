"""Configuration management using environment variables."""

from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Application settings
    app_name: str = "IFCER Batch Service"
    log_level: str = "INFO"

    # AWS settings
    # Note: AWS credentials are automatically provided by IAM role in ECS
    # No need to configure AWS_ACCESS_KEY_ID or AWS_SECRET_ACCESS_KEY
    aws_region: str = "eu-south-1"  # Italy region
    s3_bucket_name: str

    # AWS DynamoDB settings
    dynamodb_table_name: str = "ifcer-certifications"
    dynamodb_ttl_days: Optional[int] = None  # Optional: Auto-delete records after N days

    # InfoCert API settings (mTLS)
    # InfoCert's Manifest-Based Hash Signature API
    # Certificates are stored in S3 and loaded during application startup
    # API URL should point to InfoCert's Sign API base URL
    # Example: https://sign.infocert.it/api/v1
    vendor_api_url: str
    infocert_credential_id: str  # InfoCert credential ID for signing
    vendor_mtls_cert_s3_key: str = "certs/client_cert.pem"
    vendor_mtls_key_s3_key: str = "certs/client_key.pem"
    vendor_mtls_ca_s3_key: Optional[str] = "certs/ca_bundle.pem"

    # Processing settings
    hash_algorithm: str = "sha256"  # Best practice for file integrity
    batch_size: int = 100  # Number of files to process per batch
    request_timeout: int = 30  # Timeout for API requests in seconds

    class Config:
        env_file = ".env"
        case_sensitive = False


# Global settings instance
settings = Settings()
