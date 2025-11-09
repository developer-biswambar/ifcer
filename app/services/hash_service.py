"""Hash service for computing file hashes."""

import hashlib
from datetime import datetime, timezone
from typing import BinaryIO
from app.config import settings
from app.models.schemas import FileHashInfo
from app.utils.logger import setup_logger, log_exception

logger = setup_logger(__name__)


class HashService:
    """Service for computing cryptographic hashes of files."""

    def __init__(self):
        """Initialize hash service with configured algorithm."""
        self.algorithm = settings.hash_algorithm
        logger.info(f"Hash service initialized with algorithm: {self.algorithm}")

    def compute_hash(self, file_content: bytes, file_key: str) -> FileHashInfo:
        """
        Compute hash of file content.

        Args:
            file_content: File content as bytes
            file_key: S3 file key for reference

        Returns:
            FileHashInfo object with hash details

        Raises:
            ValueError: If hash algorithm is not supported
            Exception: If hash computation fails
        """
        start_time = datetime.now(timezone.utc)
        try:
            file_size = len(file_content)
            logger.debug(
                f"[HASH COMPUTE] Starting hash computation | "
                f"File: {file_key} | "
                f"Algorithm: {self.algorithm.upper()} | "
                f"Size: {file_size:,} bytes"
            )

            # Create hash object based on configured algorithm
            if self.algorithm.lower() == "sha256":
                hash_obj = hashlib.sha256()
            elif self.algorithm.lower() == "sha512":
                hash_obj = hashlib.sha512()
            elif self.algorithm.lower() == "sha1":
                hash_obj = hashlib.sha1()
            elif self.algorithm.lower() == "md5":
                hash_obj = hashlib.md5()
            else:
                raise ValueError(f"Unsupported hash algorithm: {self.algorithm}")

            # Compute hash
            hash_obj.update(file_content)
            hash_value = hash_obj.hexdigest()

            elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()

            # Calculate throughput
            size_mb = file_size / (1024 * 1024)
            throughput_mbps = (size_mb / elapsed) if elapsed > 0 else 0

            logger.info(
                f"[HASH COMPUTE] ✓ Hash computed | "
                f"File: {file_key} | "
                f"Algorithm: {self.algorithm.upper()} | "
                f"Hash: {hash_value[:16]}... | "
                f"Size: {file_size:,} bytes ({size_mb:.2f} MB) | "
                f"Duration: {elapsed:.3f}s | "
                f"Throughput: {throughput_mbps:.2f} MB/s"
            )

            return FileHashInfo(
                file_key=file_key,
                hash_value=hash_value,
                hash_algorithm=self.algorithm,
                file_size=file_size,
            )

        except ValueError as e:
            elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
            log_exception(logger, e, f"[HASH COMPUTE] Invalid hash algorithm after {elapsed:.3f}s")
            raise
        except Exception as e:
            elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
            log_exception(logger, e, f"[HASH COMPUTE] Failed to compute hash for {file_key} after {elapsed:.3f}s")
            raise

    def compute_hash_from_stream(
        self, file_stream: BinaryIO, file_key: str, chunk_size: int = 8192
    ) -> FileHashInfo:
        """
        Compute hash of file content from stream (memory efficient for large files).

        Args:
            file_stream: File stream to read from
            file_key: S3 file key for reference
            chunk_size: Size of chunks to read at a time

        Returns:
            FileHashInfo object with hash details

        Raises:
            ValueError: If hash algorithm is not supported
            Exception: If hash computation fails
        """
        try:
            logger.debug(
                f"Computing {self.algorithm} hash from stream for: {file_key}"
            )

            # Create hash object based on configured algorithm
            if self.algorithm.lower() == "sha256":
                hash_obj = hashlib.sha256()
            elif self.algorithm.lower() == "sha512":
                hash_obj = hashlib.sha512()
            elif self.algorithm.lower() == "sha1":
                hash_obj = hashlib.sha1()
            elif self.algorithm.lower() == "md5":
                hash_obj = hashlib.md5()
            else:
                raise ValueError(f"Unsupported hash algorithm: {self.algorithm}")

            # Compute hash in chunks
            total_size = 0
            while True:
                chunk = file_stream.read(chunk_size)
                if not chunk:
                    break
                hash_obj.update(chunk)
                total_size += len(chunk)

            hash_value = hash_obj.hexdigest()

            logger.info(
                f"Computed hash from stream for {file_key}: {hash_value[:16]}... (length: {total_size} bytes)"
            )

            return FileHashInfo(
                file_key=file_key,
                hash_value=hash_value,
                hash_algorithm=self.algorithm,
                file_size=total_size,
            )

        except ValueError as e:
            log_exception(logger, e, "Invalid hash algorithm")
            raise
        except Exception as e:
            log_exception(
                logger, e, f"Failed to compute hash from stream for {file_key}"
            )
            raise

    def verify_hash(self, file_content: bytes, expected_hash: str) -> bool:
        """
        Verify file content against expected hash.

        Args:
            file_content: File content as bytes
            expected_hash: Expected hash value

        Returns:
            True if hash matches, False otherwise
        """
        try:
            if self.algorithm.lower() == "sha256":
                hash_obj = hashlib.sha256()
            elif self.algorithm.lower() == "sha512":
                hash_obj = hashlib.sha512()
            elif self.algorithm.lower() == "sha1":
                hash_obj = hashlib.sha1()
            elif self.algorithm.lower() == "md5":
                hash_obj = hashlib.md5()
            else:
                raise ValueError(f"Unsupported hash algorithm: {self.algorithm}")

            hash_obj.update(file_content)
            computed_hash = hash_obj.hexdigest()

            matches = computed_hash.lower() == expected_hash.lower()

            if matches:
                logger.debug("Hash verification successful")
            else:
                logger.warning("Hash verification failed")

            return matches

        except Exception as e:
            log_exception(logger, e, "Failed to verify hash")
            return False
