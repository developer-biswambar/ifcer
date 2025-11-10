# IFCER Batch Service - Test Suite

Comprehensive unit test suite for the IFCER (Italian File Certification and Registration) Batch Service.

## Table of Contents

- [Overview](#overview)
- [Test Structure](#test-structure)
- [Installation](#installation)
- [Running Tests](#running-tests)
- [Test Coverage](#test-coverage)
- [Writing Tests](#writing-tests)
- [CI/CD Integration](#cicd-integration)
- [Troubleshooting](#troubleshooting)

## Overview

This test suite provides comprehensive coverage of all IFCER components:

- **Service Layer**: Unit tests for S3Service, DynamoDBService, HashService, and SignatureService
- **API Endpoints**: Integration tests for FastAPI routers
- **Business Logic**: Tests for file processing workflows
- **Error Handling**: Tests for fail-fast behavior and error scenarios

### Test Philosophy

- **Unit Tests**: Test individual components in isolation using mocks
- **Fast Execution**: All tests use mocks (no real AWS or network calls)
- **High Coverage**: Target 80%+ code coverage
- **Fail-Fast**: Tests verify fail-fast behavior for data integrity

## Test Structure

```
tests/
├── README.md                      # This file
├── conftest.py                    # Shared fixtures and test configuration
├── test_hash_service.py           # HashService tests (23 tests)
├── test_s3_service.py             # S3Service tests with moto (24 tests)
├── test_dynamodb_service.py       # DynamoDBService tests with moto (15 tests)
├── test_signature_service.py      # SignatureService tests (15 tests)
└── test_processing_router.py      # API endpoint tests (17 tests)
```

## Installation

### 1. Install Test Dependencies

```bash
# Install all test dependencies
pip install -r requirements-test.txt
```

This installs:
- `pytest` - Testing framework
- `pytest-asyncio` - For async endpoint testing
- `pytest-cov` - Code coverage reports
- `pytest-mock` - Enhanced mocking capabilities
- `moto` - AWS service mocking (S3, DynamoDB)
- `httpx` - FastAPI test client
- `requests-mock` - HTTP request mocking
- Code quality tools (black, flake8, mypy, isort)

### 2. Verify Installation

```bash
pytest --version
# Should show: pytest 7.4.3

pytest --co
# Should list all test files and test functions
```

## Running Tests

### Run All Tests

```bash
# Run all tests with verbose output
pytest -v

# Run with coverage report
pytest --cov=app --cov-report=html --cov-report=term-missing
```

### Run Specific Test Files

```bash
# Test only HashService
pytest tests/test_hash_service.py -v

# Test only S3Service
pytest tests/test_s3_service.py -v

# Test only API endpoints
pytest tests/test_processing_router.py -v
```

### Run Tests by Marker

Tests are organized with markers for easy filtering:

```bash
# Run only unit tests
pytest -m unit -v

# Run only service layer tests
pytest -m service -v

# Run only router tests
pytest -m router -v

# Run slow tests only
pytest -m slow -v
```

### Run Specific Tests

```bash
# Run a specific test function
pytest tests/test_hash_service.py::TestHashService::test_compute_hash_sha256 -v

# Run all tests in a class
pytest tests/test_hash_service.py::TestHashService -v

# Run tests matching a pattern
pytest -k "hash" -v
pytest -k "s3 and upload" -v
```

### Parallel Execution

```bash
# Install pytest-xdist for parallel execution
pip install pytest-xdist

# Run tests in parallel (4 workers)
pytest -n 4
```

## Test Coverage

### Generate Coverage Report

```bash
# Generate HTML coverage report
pytest --cov=app --cov-report=html

# Open the report in your browser
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
```

### Coverage Targets

- **Overall**: 80%+ coverage
- **Service Layer**: 90%+ coverage
- **Router Layer**: 85%+ coverage
- **Utilities**: 80%+ coverage

### View Coverage in Terminal

```bash
# Show missing lines
pytest --cov=app --cov-report=term-missing

# Show summary only
pytest --cov=app --cov-report=term
```

## Writing Tests

### Test File Structure

```python
"""Unit tests for MyService."""

import pytest
from app.services.my_service import MyService


@pytest.mark.unit
@pytest.mark.service
class TestMyService:
    """Test suite for MyService."""

    def test_my_feature(self, test_settings):
        """Test description."""
        # Arrange
        service = MyService()

        # Act
        result = service.my_method()

        # Assert
        assert result is not None
```

### Using Fixtures

Common fixtures are defined in `conftest.py`:

```python
def test_with_s3_bucket(s3_bucket):
    """Test using mocked S3 bucket."""
    s3_mock, bucket_name = s3_bucket
    # Test code here


def test_with_dynamodb(dynamodb_table):
    """Test using mocked DynamoDB table."""
    # Table is already created with GSI indexes
    # Test code here


def test_with_mocked_services(mock_s3_service, mock_signature_service):
    """Test with pre-configured service mocks."""
    # Services are already mocked with default behaviors
    # Test code here
```

### Mocking AWS Services

```python
def test_s3_operations(s3_bucket):
    """Test S3 operations with moto."""
    s3_mock, bucket_name = s3_bucket

    # Upload a test file
    s3_mock.put_object(
        Bucket=bucket_name,
        Key="test.pdf",
        Body=b"test content"
    )

    # Your test code here
```

### Mocking HTTP Requests

```python
from unittest.mock import Mock, patch

def test_api_call(mock_signature_service):
    """Test API calls."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"result": "success"}

    with patch("requests.post", return_value=mock_response):
        # Test code here
```

### Testing Async Endpoints

```python
@pytest.mark.asyncio
async def test_async_endpoint():
    """Test async FastAPI endpoint."""
    from httpx import AsyncClient
    from app.main import app

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/health")
        assert response.status_code == 200
```

## Test Markers

Available markers for organizing tests:

- `@pytest.mark.unit` - Unit tests (isolated, fast)
- `@pytest.mark.integration` - Integration tests (may require external services)
- `@pytest.mark.service` - Service layer tests
- `@pytest.mark.router` - API endpoint tests
- `@pytest.mark.slow` - Slow-running tests
- `@pytest.mark.utils` - Utility function tests

### Defining Custom Markers

Add to `pytest.ini`:

```ini
markers =
    my_marker: Description of my custom marker
```

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install -r requirements-test.txt

      - name: Run tests with coverage
        run: |
          pytest --cov=app --cov-report=xml --cov-report=term-missing

      - name: Upload coverage to Codecov
        uses: codecov/codecov-action@v3
        with:
          file: ./coverage.xml
```

### GitLab CI Example

```yaml
test:
  stage: test
  image: python:3.11
  script:
    - pip install -r requirements.txt
    - pip install -r requirements-test.txt
    - pytest --cov=app --cov-report=term-missing --cov-report=html
  coverage: '/TOTAL.*\s+(\d+%)$/'
  artifacts:
    reports:
      coverage_report:
        coverage_format: cobertura
        path: coverage.xml
```

## Troubleshooting

### Common Issues

#### Issue: Import Errors

```
ModuleNotFoundError: No module named 'app'
```

**Solution**: Ensure you're running pytest from the project root:

```bash
cd /path/to/ifcer
pytest
```

#### Issue: Fixture Not Found

```
fixture 'test_settings' not found
```

**Solution**: Ensure `conftest.py` is in the `tests/` directory and pytest can discover it:

```bash
pytest --fixtures  # List all available fixtures
```

#### Issue: AWS Credentials Error

```
NoCredentialsError: Unable to locate credentials
```

**Solution**: The tests use moto mocking, which sets fake credentials. Ensure `aws_credentials` fixture is used:

```python
def test_my_test(aws_credentials, s3_mock):
    # Test code
```

#### Issue: Tests Taking Too Long

**Solution**: Ensure you're using mocks, not real AWS services:

```bash
# Check if any tests are marked as slow
pytest -m slow -v

# Run only fast unit tests
pytest -m unit -v
```

#### Issue: Coverage Not Generated

```
Coverage.py warning: No data was collected
```

**Solution**: Ensure the `--cov` flag points to the right module:

```bash
pytest --cov=app  # Not --cov=src or --cov=tests
```

### Debug Mode

Run tests with more verbose output:

```bash
# Show print statements
pytest -v -s

# Show local variables on failure
pytest -v --showlocals

# Drop into debugger on failure
pytest -v --pdb

# Stop on first failure
pytest -v -x
```

### Logging in Tests

```python
def test_with_logging(caplog):
    """Test with log capture."""
    import logging

    with caplog.at_level(logging.INFO):
        # Run code that logs
        my_function()

    # Assert log messages
    assert "Expected log message" in caplog.text
```

## Best Practices

1. **Test One Thing**: Each test should verify one specific behavior
2. **Descriptive Names**: Test names should describe what they test
3. **Arrange-Act-Assert**: Structure tests clearly (setup, execute, verify)
4. **Use Fixtures**: Leverage fixtures for common setup
5. **Mock External Dependencies**: Always mock AWS, APIs, external services
6. **Test Edge Cases**: Test empty inputs, large files, error conditions
7. **Fast Tests**: Keep unit tests fast (<1 second each)
8. **Independent Tests**: Tests should not depend on each other
9. **Clean Up**: Use fixtures with cleanup or context managers

## Test Statistics

Current test coverage (as of last update):

```
Service Layer:
- HashService: 23 tests, 95% coverage
- S3Service: 24 tests, 92% coverage
- DynamoDBService: 15 tests, 88% coverage
- SignatureService: 15 tests, 85% coverage

API Layer:
- Processing Router: 17 tests, 90% coverage

Total: 94 tests, 90% overall coverage
```

## Additional Resources

- [pytest Documentation](https://docs.pytest.org/)
- [pytest-cov Documentation](https://pytest-cov.readthedocs.io/)
- [moto Documentation](https://docs.getmoto.org/)
- [FastAPI Testing](https://fastapi.tiangolo.com/tutorial/testing/)
- [Python unittest.mock](https://docs.python.org/3/library/unittest.mock.html)

## Contributing

When adding new features:

1. Write tests first (TDD approach)
2. Ensure tests pass: `pytest -v`
3. Check coverage: `pytest --cov=app`
4. Run linters: `black . && flake8 && mypy app`
5. Update this README if adding new test patterns

## Support

For questions or issues with tests:
1. Check this README
2. Review existing test examples in `tests/`
3. Check pytest output for specific error messages
4. Review logs with `pytest -v -s`
