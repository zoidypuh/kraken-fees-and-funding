# Kraken Dashboard Tests

This directory contains comprehensive tests for the Kraken Fees and Funding Dashboard.

## Test Structure

```
tests/
├── __init__.py                 # Test package initialization
├── test_kraken_client.py       # Tests for Kraken API client functions
├── test_dashboard_utils.py     # Tests for utility functions
├── test_app.py                 # Tests for Flask app endpoints
└── test_fee_info.py           # Tests for fee information functions
```

## Test Categories

### Unit Tests
- No external dependencies or API calls
- Test individual functions in isolation
- Fast execution
- Marked with `@pytest.mark.unit`

### Integration Tests
- Test actual API interactions
- Require valid Kraken API credentials in `.env` file
- May be rate-limited by the API
- Marked with `@pytest.mark.integration`

### Performance Tests
- Compare performance of different implementations
- Marked with `@pytest.mark.performance`

### Slow Tests
- Tests that take longer to execute
- Marked with `@pytest.mark.slow`

## Running Tests

### Prerequisites
1. Install test dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Set up API credentials in `.env` file:
   ```
   KRAKEN_API_KEY=your_api_key
   KRAKEN_API_SECRET=your_api_secret
   ```

### Using the Test Runner Script

The easiest way to run tests is using the provided test runner:

```bash
# Show available commands
python run_tests.py help

# Run quick tests (excludes slow and integration tests)
python run_tests.py quick

# Run all unit tests
python run_tests.py unit

# Run integration tests (requires API credentials)
python run_tests.py integration

# Run all tests
python run_tests.py all

# Run with coverage report
python run_tests.py coverage
```

### Using pytest directly

```bash
# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_kraken_client.py -v

# Run specific test
pytest tests/test_kraken_client.py::TestKrakenClientUnit::test_signature_generation_consistency -v

# Run tests by marker
pytest tests/ -v -m "unit"                    # Unit tests only
pytest tests/ -v -m "integration"             # Integration tests only
pytest tests/ -v -m "not slow"                # Exclude slow tests
pytest tests/ -v -m "not integration"         # Exclude integration tests

# Run with coverage
pytest tests/ --cov=. --cov-report=html
```

## Test Coverage

To generate a coverage report:

```bash
# Run tests with coverage
python -m coverage run -m pytest tests/

# Generate terminal report
python -m coverage report

# Generate HTML report
python -m coverage html
# Open htmlcov/index.html in browser
```

## Writing New Tests

### Test Structure Example

```python
import pytest
from module_to_test import function_to_test

@pytest.mark.unit
class TestMyFeature:
    """Test suite for my feature."""
    
    def test_basic_functionality(self):
        """Test basic functionality."""
        result = function_to_test("input")
        assert result == "expected_output"
    
    @pytest.mark.integration
    def test_api_interaction(self, api_credentials):
        """Test that requires API credentials."""
        # Test implementation
        pass
```

### Best Practices

1. **Use descriptive test names**: Test names should clearly describe what is being tested
2. **One assertion per test**: Keep tests focused on a single behavior
3. **Use fixtures**: Share common setup code using pytest fixtures
4. **Mock external dependencies**: Use `pytest-mock` for unit tests
5. **Mark tests appropriately**: Use markers to categorize tests
6. **Test edge cases**: Include tests for error conditions and edge cases

## Troubleshooting

### Common Issues

1. **API Rate Limiting**: If integration tests fail due to rate limiting, wait a few minutes before retrying
2. **Missing Credentials**: Ensure `.env` file exists with valid API credentials
3. **Import Errors**: Make sure you're running tests from the project root directory
4. **Slow Tests**: Use `-m "not slow"` to skip slow tests during development

### Debugging Tests

```bash
# Run with detailed output
pytest tests/ -vv

# Show print statements
pytest tests/ -s

# Stop on first failure
pytest tests/ -x

# Run with pdb debugger on failure
pytest tests/ --pdb
``` 