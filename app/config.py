"""Configuration management using environment variables.

All settings are loaded from environment variables or .env file.
Environment variables take precedence over .env file values.
This allows configuration via Docker environment variables or .env file.
"""

from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.

    Configuration sources (in order of precedence):
    1. Environment variables (e.g., Docker, ECS task definition)
    2. .env file (for local development)
    3. Default values (where specified)

    Required environment variables (no defaults):
    - S3_BUCKET_NAME: S3 bucket for file storage
    - INFOCERT_API_URL: InfoCert mTLS API base URL
    - INFOCERT_CREDENTIAL_ID: InfoCert credential ID for signing

    Optional environment variables (with defaults):
    - APP_NAME: Application name (default: "IFCER Batch Service")
    - LOG_LEVEL: Logging level (default: "INFO")
    - AWS_REGION: AWS region (default: "eu-south-1")
    - DYNAMODB_TABLE_NAME: DynamoDB table name (default: "ifcer-certifications")
    - DYNAMODB_TTL_DAYS: Record TTL in days (default: None)
    - VENDOR_MTLS_P12_S3_KEY: S3 key for P12 certificate (default: None)
    - VENDOR_MTLS_P12_PASSWORD: Password for P12 file (default: None)
    - VENDOR_MTLS_CERT_S3_KEY: S3 key for client certificate PEM (default: "certs/client_cert.pem")
    - VENDOR_MTLS_KEY_S3_KEY: S3 key for client key PEM (default: "certs/client_key.pem")
    - VENDOR_MTLS_CA_S3_KEY: S3 key for CA bundle (default: "certs/ca_bundle.pem")
    - HASH_ALGORITHM: Hash algorithm (default: "sha256")
    - BATCH_SIZE: Batch processing size (default: 100)
    - REQUEST_TIMEOUT: API request timeout in seconds (default: 30)
    """

    # ==================== Application Settings ====================
    # Loaded from: APP_NAME, LOG_LEVEL
    app_name: str = "IFCER Batch Service"
    log_level: str = "INFO"

    # ==================== AWS Settings ====================
    # Loaded from: AWS_REGION, S3_BUCKET_NAME, AWS_ENDPOINT_URL, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY
    # Note: AWS credentials (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY) are
    # automatically provided by IAM role in ECS. For local testing with moto,
    # set AWS_ENDPOINT_URL=http://localhost:5000 and use test credentials.
    aws_region: str = "eu-south-1"  # Italy region
    s3_bucket_name: str  # REQUIRED - No default
    aws_endpoint_url: Optional[str] = None  # For moto/LocalStack testing (e.g., http://localhost:5000)
    aws_access_key_id: Optional[str] = None  # For local testing (use 'test' with moto)
    aws_secret_access_key: Optional[str] = None  # For local testing (use 'test' with moto)

    # ==================== DynamoDB Settings ====================
    # Loaded from: DYNAMODB_TABLE_NAME, DYNAMODB_TTL_DAYS
    dynamodb_table_name: str = "ifcer-certifications"
    dynamodb_ttl_days: Optional[int] = None  # Optional: Auto-delete records after N days

    # ==================== InfoCert API Settings ====================
    # Loaded from: INFOCERT_API_URL, INFOCERT_CREDENTIAL_ID, INFOCERT_CERTIFICATE_ID,
    #              INFOCERT_PIN, INFOCERT_SAT,
    #              VENDOR_MTLS_P12_S3_KEY, VENDOR_MTLS_P12_PASSWORD (or PEM files)
    #
    # InfoCert uses mTLS API endpoint with hashSignatures for signing document hashes
    # Certificates are stored in S3 and loaded during application startup
    #
    # ENVIRONMENTS:
    #   STAGE:      https://mtlsapistage.infocert.digital/signature/v1
    #   PRODUCTION: https://mtlsapi.infocert.digital/signature/v1
    #
    # Signing endpoint: /certificates/{certificateId}/sign with hashSignatures
    #
    infocert_api_url: str  # REQUIRED - InfoCert mTLS API base URL
    infocert_credential_id: str  # REQUIRED - InfoCert credential ID (X-signer-id header, e.g., MA556902)
    infocert_certificate_id: str  # REQUIRED - Certificate ID for signing (path parameter)
    infocert_pin: str  # REQUIRED - PIN for automatic signature certificate
    infocert_sat: str  # REQUIRED - SAT (Signature Activation Token) - long-lived JWT token

    # OPTION 1: P12 certificate (recommended - simpler setup)
    vendor_mtls_p12_s3_key: Optional[str] = None  # S3 key for P12 file (e.g., certs/client_cert.p12)
    vendor_mtls_p12_password: Optional[str] = None  # Password for P12 file

    # OPTION 2: PEM certificates (if P12 is not provided)
    vendor_mtls_cert_s3_key: Optional[str] = "certs/client_cert.pem"
    vendor_mtls_key_s3_key: Optional[str] = "certs/client_key.pem"
    vendor_mtls_ca_s3_key: Optional[str] = "certs/ca_bundle.pem"

    # ==================== Processing Settings ====================
    # Loaded from: HASH_ALGORITHM, BATCH_SIZE, REQUEST_TIMEOUT, RETRY_MAX_ATTEMPTS,
    #              RETRY_BACKOFF_BASE, RETRY_BACKOFF_MAX, MAX_CONCURRENT_REQUESTS
    hash_algorithm: str = "sha256"  # Cryptographic hash algorithm (sha256, sha512, sha1, md5)
    batch_size: int = 100  # Number of files to process per batch
    request_timeout: int = 30  # Timeout for API requests in seconds

    # Retry configuration for recoverable errors (network issues, rate limiting, server overload)
    retry_max_attempts: int = 3  # Maximum retry attempts for recoverable errors
    retry_backoff_base: float = 1.0  # Base backoff time in seconds (exponential: 1s, 2s, 4s, 8s, 16s)
    retry_backoff_max: float = 32.0  # Maximum backoff time in seconds

    # Parallel processing configuration
    max_concurrent_requests: int = 10  # Maximum concurrent file processing operations

    # ==================== Notification Settings ====================
    # Loaded from: NOTIFICATION_SNS_TOPIC_ARN
    # SNS topic for batch completion notifications (optional)
    # If not set, notifications are disabled
    notification_sns_topic_arn: Optional[str] = None  # AWS SNS topic ARN for notifications

    # ==================== Certificate Caching Settings ====================
    # Loaded from: CERTIFICATE_CACHE_TTL_SECONDS
    # Cache signing certificate fetched from InfoCert to avoid repeated API calls
    # Default: 3600 seconds (1 hour)
    # Set to 0 to disable caching
    certificate_cache_ttl_seconds: int = 3600  # Cache TTL in seconds

    # ==================== Batch Signing Settings ====================
    # Loaded from: BATCH_SIGN_SIZE
    # Maximum number of files to send to InfoCert in a single batch API call
    # Default: 50 (conservative limit to avoid request size limits)
    # InfoCert may have undocumented limits - adjust based on testing
    # If batch processing has 200 files, it will be split into 4 batches of 50
    batch_sign_size: int = 50

    class Config:
        """Pydantic settings configuration."""
        # Load from .env file if it exists (for local development)
        # Environment variables always take precedence
        env_file = ".env"
        env_file_encoding = "utf-8"

        # Case-insensitive environment variable names
        # Allows APP_NAME, app_name, App_Name, etc.
        case_sensitive = False

        # Allow extra fields (for forward compatibility)
        extra = "ignore"


# Global settings instance
# All configuration is loaded when this module is imported
# Values are validated according to the field types defined above
settings = Settings()
