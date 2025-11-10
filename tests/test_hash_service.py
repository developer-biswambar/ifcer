"""Unit tests for HashService."""

import pytest
import hashlib
from io import BytesIO
from unittest.mock import patch, Mock

from app.services.hash_service import HashService
from app.models.schemas import FileHashInfo
from app.config import Settings


@pytest.mark.unit
@pytest.mark.service
class TestHashService:
    """Test suite for HashService."""

    def test_init(self, test_settings):
        """Test HashService initialization."""
        with patch("app.config.settings", test_settings):
            service = HashService()
            assert service.algorithm == test_settings.hash_algorithm

    def test_compute_hash_sha256(self, test_settings):
        """Test hash computation with SHA256."""
        test_settings.hash_algorithm = "sha256"

        with patch("app.config.settings", test_settings):
            service = HashService()
            content = b"Test file content"
            file_key = "test.pdf"

            result = service.compute_hash(content, file_key)

            # Verify result type and fields
            assert isinstance(result, FileHashInfo)
            assert result.file_key == file_key
            assert result.hash_algorithm == "sha256"
            assert result.file_size == len(content)

            # Verify hash is correct
            expected_hash = hashlib.sha256(content).hexdigest()
            assert result.hash_value == expected_hash

    def test_compute_hash_sha512(self, test_settings):
        """Test hash computation with SHA512."""
        test_settings.hash_algorithm = "sha512"

        with patch("app.config.settings", test_settings):
            service = HashService()
            content = b"Test file content for SHA512"
            file_key = "test_sha512.pdf"

            result = service.compute_hash(content, file_key)

            expected_hash = hashlib.sha512(content).hexdigest()
            assert result.hash_value == expected_hash
            assert result.hash_algorithm == "sha512"

    def test_compute_hash_sha1(self, test_settings):
        """Test hash computation with SHA1."""
        test_settings.hash_algorithm = "sha1"

        with patch("app.config.settings", test_settings):
            service = HashService()
            content = b"Test file content for SHA1"
            file_key = "test_sha1.pdf"

            result = service.compute_hash(content, file_key)

            expected_hash = hashlib.sha1(content).hexdigest()
            assert result.hash_value == expected_hash
            assert result.hash_algorithm == "sha1"

    def test_compute_hash_md5(self, test_settings):
        """Test hash computation with MD5."""
        test_settings.hash_algorithm = "md5"

        with patch("app.config.settings", test_settings):
            service = HashService()
            content = b"Test file content for MD5"
            file_key = "test_md5.pdf"

            result = service.compute_hash(content, file_key)

            expected_hash = hashlib.md5(content).hexdigest()
            assert result.hash_value == expected_hash
            assert result.hash_algorithm == "md5"

    def test_compute_hash_unsupported_algorithm(self, test_settings):
        """Test hash computation with unsupported algorithm."""
        test_settings.hash_algorithm = "unsupported"

        with patch("app.config.settings", test_settings):
            service = HashService()
            content = b"Test content"
            file_key = "test.pdf"

            with pytest.raises(ValueError, match="Unsupported hash algorithm"):
                service.compute_hash(content, file_key)

    def test_compute_hash_empty_file(self, test_settings):
        """Test hash computation with empty file."""
        with patch("app.config.settings", test_settings):
            service = HashService()
            content = b""
            file_key = "empty.pdf"

            result = service.compute_hash(content, file_key)

            assert result.file_size == 0
            # SHA256 hash of empty string
            expected_hash = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
            assert result.hash_value == expected_hash

    def test_compute_hash_large_file(self, test_settings):
        """Test hash computation with large file."""
        with patch("app.config.settings", test_settings):
            service = HashService()
            # Create 10MB test file
            content = b"A" * (10 * 1024 * 1024)
            file_key = "large_file.pdf"

            result = service.compute_hash(content, file_key)

            assert result.file_size == 10 * 1024 * 1024
            expected_hash = hashlib.sha256(content).hexdigest()
            assert result.hash_value == expected_hash

    def test_compute_hash_from_stream(self, test_settings):
        """Test hash computation from stream."""
        with patch("app.config.settings", test_settings):
            service = HashService()
            content = b"Test file content from stream"
            file_key = "stream_test.pdf"
            stream = BytesIO(content)

            result = service.compute_hash_from_stream(stream, file_key)

            assert isinstance(result, FileHashInfo)
            assert result.file_key == file_key
            assert result.file_size == len(content)
            expected_hash = hashlib.sha256(content).hexdigest()
            assert result.hash_value == expected_hash

    def test_compute_hash_from_stream_chunked(self, test_settings):
        """Test hash computation from stream with custom chunk size."""
        with patch("app.config.settings", test_settings):
            service = HashService()
            # Create content larger than default chunk size
            content = b"X" * 20000
            file_key = "chunked_stream.pdf"
            stream = BytesIO(content)

            result = service.compute_hash_from_stream(stream, file_key, chunk_size=4096)

            assert result.file_size == len(content)
            expected_hash = hashlib.sha256(content).hexdigest()
            assert result.hash_value == expected_hash

    def test_compute_hash_from_stream_empty(self, test_settings):
        """Test hash computation from empty stream."""
        with patch("app.config.settings", test_settings):
            service = HashService()
            stream = BytesIO(b"")
            file_key = "empty_stream.pdf"

            result = service.compute_hash_from_stream(stream, file_key)

            assert result.file_size == 0
            expected_hash = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
            assert result.hash_value == expected_hash

    def test_compute_hash_from_stream_unsupported_algorithm(self, test_settings):
        """Test hash computation from stream with unsupported algorithm."""
        test_settings.hash_algorithm = "invalid"

        with patch("app.config.settings", test_settings):
            service = HashService()
            stream = BytesIO(b"test")
            file_key = "test.pdf"

            with pytest.raises(ValueError, match="Unsupported hash algorithm"):
                service.compute_hash_from_stream(stream, file_key)

    def test_verify_hash_success(self, test_settings):
        """Test successful hash verification."""
        with patch("app.config.settings", test_settings):
            service = HashService()
            content = b"Test content for verification"
            expected_hash = hashlib.sha256(content).hexdigest()

            result = service.verify_hash(content, expected_hash)

            assert result is True

    def test_verify_hash_failure(self, test_settings):
        """Test failed hash verification."""
        with patch("app.config.settings", test_settings):
            service = HashService()
            content = b"Test content"
            wrong_hash = "0000000000000000000000000000000000000000000000000000000000000000"

            result = service.verify_hash(content, wrong_hash)

            assert result is False

    def test_verify_hash_case_insensitive(self, test_settings):
        """Test hash verification is case insensitive."""
        with patch("app.config.settings", test_settings):
            service = HashService()
            content = b"Test content"
            expected_hash = hashlib.sha256(content).hexdigest()

            # Test with uppercase hash
            result = service.verify_hash(content, expected_hash.upper())
            assert result is True

            # Test with lowercase hash
            result = service.verify_hash(content, expected_hash.lower())
            assert result is True

    def test_verify_hash_unsupported_algorithm(self, test_settings):
        """Test hash verification with unsupported algorithm."""
        test_settings.hash_algorithm = "unsupported"

        with patch("app.config.settings", test_settings):
            service = HashService()
            content = b"Test content"
            hash_value = "somehash"

            # Should return False on error, not raise
            result = service.verify_hash(content, hash_value)
            assert result is False

    def test_hash_consistency(self, test_settings):
        """Test that same content produces same hash."""
        with patch("app.config.settings", test_settings):
            service = HashService()
            content = b"Consistency test content"
            file_key = "consistent.pdf"

            # Compute hash multiple times
            result1 = service.compute_hash(content, file_key)
            result2 = service.compute_hash(content, file_key)
            result3 = service.compute_hash(content, file_key)

            # All hashes should be identical
            assert result1.hash_value == result2.hash_value == result3.hash_value

    def test_different_content_different_hash(self, test_settings):
        """Test that different content produces different hashes."""
        with patch("app.config.settings", test_settings):
            service = HashService()
            content1 = b"Content A"
            content2 = b"Content B"
            file_key = "test.pdf"

            result1 = service.compute_hash(content1, file_key)
            result2 = service.compute_hash(content2, file_key)

            assert result1.hash_value != result2.hash_value

    def test_stream_vs_bytes_same_hash(self, test_settings):
        """Test that stream and bytes produce same hash for same content."""
        with patch("app.config.settings", test_settings):
            service = HashService()
            content = b"Test content for comparison"
            file_key = "compare.pdf"

            # Compute from bytes
            result_bytes = service.compute_hash(content, file_key)

            # Compute from stream
            stream = BytesIO(content)
            result_stream = service.compute_hash_from_stream(stream, file_key)

            # Should produce same hash
            assert result_bytes.hash_value == result_stream.hash_value
            assert result_bytes.file_size == result_stream.file_size
